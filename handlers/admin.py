"""
Хендлер для команд администратора.
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select, func

from config import Config
from database import User, Meeting, Payment, async_session, MeetingStatus

router = Router(name="admin")


@router.message(Command("admin"))
async def admin_handler(message: Message, config: Config) -> None:
    """Показать статистику по боту для администратора."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        "ADMIN CHECK: from_user.id=%s (%s), config.admin_telegram_id=%s (%s)",
        message.from_user.id, type(message.from_user.id).__name__,
        config.admin_telegram_id, type(config.admin_telegram_id).__name__,
    )
    if message.from_user.id != config.admin_telegram_id:
        await message.answer(
            f"⛔ Команда только для администратора.\n"
            f"Твой ID: <code>{message.from_user.id}</code>\n"
            f"ID админа в конфиге: <code>{config.admin_telegram_id}</code>"
        )
        return

    async with async_session() as session:
        # Всего пользователей
        users_count_result = await session.execute(select(func.count(User.id)))
        users_count = users_count_result.scalar_one()

        # Встреч обработано
        meetings_count_result = await session.execute(
            select(func.count(Meeting.id)).where(Meeting.status == MeetingStatus.DONE)
        )
        meetings_count = meetings_count_result.scalar_one()

        # Минут обработано всего (по длительности встреч)
        minutes_total_result = await session.execute(
            select(func.sum(Meeting.duration_seconds)).where(Meeting.status == MeetingStatus.DONE)
        )
        total_seconds = minutes_total_result.scalar_one() or 0
        minutes_count = total_seconds // 60

        # Платежей выполнено
        payments_count_result = await session.execute(
            select(func.count(Payment.id)).where(Payment.status == "paid")
        )
        payments_count = payments_count_result.scalar_one()

    text = (
        "👑 Режим администратора\n"
        f"👥 Пользователей всего: {users_count}\n"
        f"📊 Встреч обработано: {meetings_count}\n"
        f"⏱ Минут обработано всего: {minutes_count}\n"
        f"💰 Платежей выполнено: {payments_count}"
    )
    
    await message.answer(text)
