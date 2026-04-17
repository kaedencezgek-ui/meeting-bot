"""
AI Секретарь — Telegram-бот для обработки записей совещаний.

Точка входа: запуск бота и инициализация компонентов.
"""
import asyncio
import logging
import sys

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from config import load_config
from database import init_db, async_session, get_payment_by_order_id, update_payment_status, get_user_by_id, update_user_minutes
from handlers import start, audio, payments, admin
from services.payments import check_webhook_signature

def setup_logging() -> None:
    """Настроить логирование: консоль + файл ошибок."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)
    root_logger.addHandler(console_handler)

    file_handler = logging.FileHandler("errors.log", encoding="utf-8")
    file_handler.setLevel(logging.ERROR)
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)

    # Подавляем спам от aiohttp (сканеры, 404 и т.д.)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.server").setLevel(logging.WARNING)


@web.middleware
async def security_middleware(request: web.Request, handler) -> web.Response:
    """
    Middleware для защиты от сканеров:
    - Пропускает только запросы на /webhook/lava
    - Всё остальное — тихий 403
    """
    if request.path != "/webhook/lava":
        # Тихо отклоняем мусорные запросы от сканеров
        return web.Response(status=403)
    return await handler(request)


async def lava_webhook(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]
    config = request.app["config"]
    
    try:
        payload = await request.json()
    except Exception:
        return web.Response(status=400)
        
    if not check_webhook_signature(request.headers, config.lava_api_key):
        return web.Response(status=403, text="Invalid signature")
    
    invoice = payload.get("invoice", payload)
    status = invoice.get("status")
    
    if status == "COMPLETED" or status == "success":
        client_utm = invoice.get("clientUtm", {})
        utm_source = client_utm.get("utm_source", "")
        
        # Determine package logic (can fall back by sum or product_id)
        invoice_id = invoice.get("id")
        amount = float(invoice.get("sum", 0))
        
        minutes_added = 0
        package_name = "Unknown"
        if amount >= 3990:
            minutes_added = 1500
            package_name = "L"
        elif amount >= 1790:
            minutes_added = 600
            package_name = "M"
        elif amount >= 990:
            minutes_added = 300
            package_name = "S"
            
        if utm_source.startswith("tg_") and minutes_added > 0:
            user_id_str = utm_source.replace("tg_", "")
            if user_id_str.isdigit():
                user_id = int(user_id_str)
                from sqlalchemy import select
                async with async_session() as session:
                    from database import Payment, create_payment
                    # Check if this invoice was already processed
                    stmt = select(Payment).where(Payment.lava_invoice_id == str(invoice_id), Payment.status == "paid")
                    existing = (await session.execute(stmt)).scalars().first()
                    
                    if not existing:
                        # Create payment record
                        await create_payment(
                            session, user_id, str(invoice_id) or "direct", package_name,
                            int(amount), minutes_added, str(invoice_id)
                        )
                        # Find the just created payment and set to paid
                        new_payment_stmt = select(Payment).where(Payment.lava_invoice_id == str(invoice_id))
                        new_payment = (await session.execute(new_payment_stmt)).scalars().first()
                        if new_payment:
                            await update_payment_status(session, new_payment.id, "paid")
                        
                        await update_user_minutes(session, user_id, added_balance=minutes_added, is_trial=False)
                        
                        user = await get_user_by_id(session, user_id)
                        if user:
                            await bot.send_message(user.telegram_id, f"✅ Оплата прошла успешно! Вам начислено {minutes_added} минут.")
                    
    return web.json_response({"status": "ok"})


async def main() -> None:
    """Главная функция — запуск бота и вебхук сервера."""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Загружаем конфигурацию
    config = load_config()
    logger.info("Конфигурация загружена (модель: %s)", config.openai_model)

    # Инициализируем базу данных
    await init_db()
    logger.info("База данных инициализирована")

    # Создаём сессию с прокси (если задан)
    session = None
    if config.proxy_url:
        session = AiohttpSession(proxy=config.proxy_url)
        logger.info("Используется прокси: %s", config.proxy_url)

    # Создаём бота
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    dp = Dispatcher()

    # Сохраняем конфиг в workflow data диспетчера — он будет доступен в хендлерах
    dp["config"] = config

    # Подключаем роутеры
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(payments.router)
    dp.include_router(audio.router)
    
    # Инициализируем aiohttp web server
    app = web.Application(middlewares=[security_middleware])
    app["bot"] = bot
    app["config"] = config
    app.router.add_post("/webhook/lava", lava_webhook)
    
    runner = web.AppRunner(app, handle_signals=False)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logger.info("Webhook-сервер запущен на порту 8080")
    logger.info("Webhook URL: http://0.0.0.0:8080/webhook/lava")

    # Запускаем polling
    logger.info("AI Секретарь запущен (polling)!")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
