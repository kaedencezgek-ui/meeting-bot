import logging
import re
import uuid
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import Config
from database import async_session, get_or_create_user
from services.payments import create_invoice

logger = logging.getLogger(__name__)
router = Router(name="payments")

class PaymentStates(StatesGroup):
    waiting_for_email = State()

PACKAGES = {
    "S": {"minutes": 300, "price": 990, "offer_id": "16e112bb-ff55-43a0-8a44-2a54ebeddcd0"},
    "M": {"minutes": 600, "price": 1790, "offer_id": "4b472933-8384-46fb-94f5-21cf427d132f"},
    "L": {"minutes": 1500, "price": 3990, "offer_id": "12ae0849-8972-4bb4-8320-6c9706c8d812"},
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
async def process_buy_callback(callback: CallbackQuery, state: FSMContext):
    package_name = callback.data.split("_")[1]
    if package_name not in PACKAGES:
        await callback.answer("Пакет не найден", show_alert=True)
        return
    
    await state.update_data(package_name=package_name)
    await state.set_state(PaymentStates.waiting_for_email)
    
    await callback.message.answer(
        "Пожалуйста, введите ваш email для выставления счёта (требование платёжной системы):"
    )
    await callback.answer()

@router.message(PaymentStates.waiting_for_email)
async def process_email(message: Message, state: FSMContext, config: Config):
    email = message.text.strip()
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        await message.answer("Пожалуйста, введите корректный email адрес.")
        return
        
    data = await state.get_data()
    package_name = data["package_name"]
    pkg = PACKAGES[package_name]
    
    await state.clear()
    wait_msg = await message.answer("⏳ Создаю счёт...")
    
    async with async_session() as session:
        user = await get_or_create_user(session, telegram_id=message.from_user.id, username=message.from_user.username)
        from database import create_payment
        
        try:
            payment_url = await create_invoice(
                config.lava_api_key, user.id, pkg["offer_id"], email
            )
            
            order_id = str(uuid.uuid4())
            await create_payment(
                session, user.id, order_id, package_name,
                pkg["price"], pkg["minutes"], pkg["offer_id"]
            )
            
            await wait_msg.edit_text(
                f"Оплатите по ссылке: {payment_url}\n"
                f"После оплаты минуты зачислятся автоматически ✅"
            )
        except Exception as e:
            logger.error(f"Error creating invoice: {e}")
            await wait_msg.edit_text("❌ Произошла ошибка при создании счёта. Попробуйте позже.")


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
