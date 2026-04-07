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
from handlers import start, audio, payments
from services.payments import check_webhook_signature

...

async def lava_webhook(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]
    config = request.app["config"]
    
    try:
        payload = await request.json()
    except Exception:
        return web.Response(status=400)
        
    if not check_webhook_signature(request.headers, config.lava_api_key):
        return web.Response(status=403, text="Invalid signature")
    
    # We match by clientUtm.utm_source (user_id) and offerId from the invoice if available.
    # Alternatively we can find pending payment by offer_id and user_id. Let's do that.
    # We will need to write custom query if multiple pendings exist, but let's assume the user has 1 pending for this offer.
    # Wait, the instruction says: Находит payment по clientUtm.utm_source (user_id) и сумме/offer.
    
    invoice = payload.get("invoice", payload) # Depends on their payload structure
    status = invoice.get("status")
    
    if status == "COMPLETED" or status == "success":
        client_utm = invoice.get("clientUtm", {})
        user_id_str = client_utm.get("utm_source")
        offer_id = invoice.get("offerId")
        
        if user_id_str and offer_id:
            user_id = int(user_id_str)
            from sqlalchemy import select
            async with async_session() as session:
                from database import Payment
                # Find pending payment by user_id and offer_id
                stmt = select(Payment).where(Payment.user_id == user_id, Payment.order_id == offer_id, Payment.status == "pending")
                payment = (await session.execute(stmt)).scalars().first()
                
                if payment:
                    await update_payment_status(session, payment.id, "paid")
                    await update_user_minutes(session, user_id, added_balance=payment.minutes_added, is_trial=False)
                    
                    user = await get_user_by_id(session, user_id)
                    if user:
                        await bot.send_message(user.telegram_id, f"✅ Оплата прошла успешно! Вам начислено {payment.minutes_added} минут.")
                    
    return web.json_response({"status": "ok"})


async def main() -> None:
    """Главная функция — запуск бота и вебхук сервера."""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Загружаем конфигурацию
    config = load_config()
    logger.info("Конфигурация загружена (модель: %s)", config.openrouter_model)

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
    dp.include_router(start.router)
    dp.include_router(audio.router)
    dp.include_router(payments.router)
    
    # Инициализируем aiohttp web server
    app = web.Application()
    app["bot"] = bot
    app["config"] = config
    app.router.add_post("/webhook/lava", lava_webhook)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logger.info("Webhook-сервер запущен на порту 8080")

    # Запускаем polling
    logger.info("AI Секретарь запущен (polling)!")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
