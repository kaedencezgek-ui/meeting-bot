"""
Конфигурация приложения — загрузка переменных из .env
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    """Все настройки приложения собраны в одном месте."""

    # Telegram
    bot_token: str

    # AssemblyAI
    assemblyai_api_key: str

    # OpenAI
    openai_api_key: str
    openai_model: str

    lava_api_key: str
    webhook_url: str

    admin_telegram_id: int

    # Прокси (опционально, для обхода блокировки Telegram API)
    proxy_url: str | None = None

    # Лимиты
    max_file_size_mb: int = 500  # максимальный размер файла в МБ


def load_config() -> Config:
    """Загрузить конфиг из переменных окружения."""
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise ValueError("BOT_TOKEN не задан в .env")

    assemblyai_api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not assemblyai_api_key:
        raise ValueError("ASSEMBLYAI_API_KEY не задан в .env")

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY не задан в .env")

    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o")
    proxy_url = os.getenv("PROXY_URL")  # опционально
    
    lava_api_key = os.getenv("LAVA_API_KEY", "")
    webhook_url = os.getenv("WEBHOOK_URL", "")

    admin_telegram_id = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

    return Config(
        bot_token=bot_token,
        assemblyai_api_key=assemblyai_api_key,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        proxy_url=proxy_url,
        lava_api_key=lava_api_key,
        webhook_url=webhook_url,
        admin_telegram_id=admin_telegram_id,
    )
