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

    # OpenRouter
    openrouter_api_key: str
    openrouter_model: str

    # Lava.top
    lava_api_key: str
    lava_shop_id: str
    webhook_url: str

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

    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY не задан в .env")

    openrouter_model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
    proxy_url = os.getenv("PROXY_URL")  # опционально
    
    lava_api_key = os.getenv("LAVA_API_KEY", "")
    lava_shop_id = os.getenv("LAVA_SHOP_ID", "")
    webhook_url = os.getenv("WEBHOOK_URL", "")

    return Config(
        bot_token=bot_token,
        assemblyai_api_key=assemblyai_api_key,
        openrouter_api_key=openrouter_api_key,
        openrouter_model=openrouter_model,
        proxy_url=proxy_url,
        lava_api_key=lava_api_key,
        lava_shop_id=lava_shop_id,
        webhook_url=webhook_url,
    )
