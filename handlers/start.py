"""
Хендлеры команд /start и /help.
"""
import logging

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from database import async_session, get_or_create_user

logger = logging.getLogger(__name__)
router = Router(name="start")

# Текст приветствия
WELCOME_TEXT = (
    "👋 <b>Привет! Я AI Секретарь</b>\n\n"
    "Я помогу вам обработать записи деловых встреч.\n\n"
    "📝 <b>Как это работает:</b>\n"
    "1. Отправьте мне аудиозапись совещания (голосовое сообщение или файл)\n"
    "2. Я транскрибирую запись с разделением по спикерам\n"
    "3. AI проанализирует текст и составит структурированный отчёт\n\n"
    "📎 <b>Поддерживаемые форматы:</b> mp3, m4a, ogg, wav\n"
    "📏 <b>Макс. размер:</b> 500 МБ (записи до 1+ часа)\n\n"
    "Просто отправьте аудиофайл, и я начну работу! 🚀"
)

HELP_TEXT = (
    "ℹ️ <b>AI Секретарь — справка</b>\n\n"
    "<b>Команды:</b>\n"
    "/start — начать работу с ботом\n"
    "/help — показать эту справку\n\n"
    "<b>Как использовать:</b>\n"
    "• Отправьте голосовое сообщение или аудиофайл с записью встречи\n"
    "• Бот транскрибирует аудио и создаст отчёт\n\n"
    "<b>Отчёт включает:</b>\n"
    "📋 Краткое резюме встречи\n"
    "👥 Список участников\n"
    "✅ Принятые решения\n"
    "📌 Задачи и дедлайны\n"
    "❓ Открытые вопросы\n"
    "🔜 Следующие шаги\n\n"
    "При возникновении проблем попробуйте отправить файл ещё раз."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Обработка команды /start — приветствие и регистрация пользователя."""
    async with async_session() as session:
        await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

    logger.info(
        "Новый пользователь: %s (id=%d)",
        message.from_user.username or "—",
        message.from_user.id,
    )

    await message.answer(WELCOME_TEXT, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Обработка команды /help — справочная информация."""
    await message.answer(HELP_TEXT, parse_mode="HTML")
