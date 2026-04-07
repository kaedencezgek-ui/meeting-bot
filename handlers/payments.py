import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from config import Config
from database import async_session, get_or_create_user
from services.payments import create_invoice

logger = logging.getLogger(__name__)
router = Router(name="payments")

PACKAGES = {
    "S": {"minutes": 300, "price": 990},
    "M": {"minutes": 600, "price": 1790},
    "L": {"minutes": 1500, "price": 3990},
}

@router.message(Command("buy"))
async def cmd_buy(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="300 мин — 990 ₽", callback_data="buy_S")],
        [InlineKeyboardButton(text="600 мин — 1790 ₽", callback_data="buy_M")],
        [InlineKeyboardButton(text="1500 мин — 3990 ₽", callback_data="buy_L")],
    ])
    await message.answer("Выберите пакет:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("buy_"))
async def process_buy_callback(callback: CallbackQuery, config: Config):
    package_name = callback.data.split("_")[1]
    if package_name not in PACKAGES:
        await callback.answer("Пакет не найден", show_alert=True)
        return
    
    pkg = PACKAGES[package_name]
    
    async with async_session() as session:
        user = await get_or_create_user(session, telegram_id=callback.from_user.id, username=callback.from_user.username)
        # Import moved to inside function to avoid circular or early deps if any
        from database import create_payment
        
        invoice_data = await create_invoice(
            config.lava_api_key, config.lava_shop_id, config.webhook_url,
            user.id, package_name, pkg["price"], pkg["minutes"]
        )
        
        await create_payment(
            session, user.id, invoice_data["order_id"], package_name,
            pkg["price"], pkg["minutes"], invoice_data["invoice_id"]
        )

    await callback.message.answer(
        f"Выбран пакет {package_name} ({pkg['minutes']} минут). "
        f"Оплатите по ссылке:\n{invoice_data['url']}"
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
