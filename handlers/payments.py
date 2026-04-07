import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery

from config import Config
from database import async_session, get_or_create_user

logger = logging.getLogger(__name__)
router = Router(name="payments")

PACKAGES = {
    "S": {"minutes": 300, "price": 990, "product_id": "573da90a-64ee-4793-afd2-28b0087557d4"},
    "M": {"minutes": 600, "price": 1790, "product_id": "c3311a57-e4f5-422d-8ac0-af0d765a106e"},
    "L": {"minutes": 1500, "price": 3990, "product_id": "3e4879a6-84b5-442a-a614-fbdeed0c5845"},
}

@router.message(Command("buy"))
async def cmd_buy(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 300 мин — 990 ₽", callback_data="buy_S")],
        [InlineKeyboardButton(text="📦 600 мин — 1790 ₽", callback_data="buy_M")],
        [InlineKeyboardButton(text="📦 1500 мин — 3990 ₽", callback_data="buy_L")],
    ])
    await message.answer("Выберите пакет:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("buy_"))
async def process_buy_callback(callback: CallbackQuery, config: Config):
    package_name = callback.data.split("_")[1]
    if package_name not in PACKAGES:
        await callback.answer("Пакет не найден", show_alert=True)
        return
        
    pkg = PACKAGES[package_name]
    
    # We prefix telegram_id with 'tg_' as per requirements for clientUtm.utm_source
    payment_url = f"https://app.lava.top/products/{pkg['product_id']}?utm_source=tg_{callback.from_user.id}"
    
    await callback.message.answer(
        f"Оплата пакета {package_name} ({pkg['minutes']} минут).\n\n"
        f"Оплатите по ссылке:\n{payment_url}\n\n"
        f"После оплаты минуты зачислятся автоматически ✅"
    )
    await callback.answer()

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    async with async_session() as session:
        user = await get_or_create_user(session, telegram_id=message.from_user.id, username=message.from_user.username)
        
        trial_status = "да" if user.is_trial else "нет"
        
        msg = (
            f"💳 Ваш баланс: {user.minutes_balance} минут\n"
            f"📊 Всего обработано: {user.minutes_used} минут\n"
            f"🎁 Пробный период: {trial_status}"
        )
        await message.answer(msg)
