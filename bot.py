"""
AI Секретарь — Telegram-бот для обработки записей совещаний.

Точка входа: запуск бота и инициализация компонентов.
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from config import load_config
from database import init_db
from handlers import start, audio


def setup_logging() -> None:
    """Настроить логирование: консоль + файл ошибок."""
    # Основной логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Формат логов
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Вывод в консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)
    root_logger.addHandler(console_handler)

    # Ошибки в файл errors.log
    file_handler = logging.FileHandler("errors.log", encoding="utf-8")
    file_handler.setLevel(logging.ERROR)
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)


async def main() -> None:
    """Главная функция — запуск бота."""
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

    # Запускаем polling
    logger.info("AI Секретарь запущен!")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
