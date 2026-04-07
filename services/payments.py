"""
Интеграция с Lava.top
"""
import logging
import httpx

logger = logging.getLogger(__name__)

def check_webhook_signature(headers: dict, api_key: str) -> bool:
    """
    Проверяет подпись вебхука от Lava (по заголовку X-Api-Key).
    """
    proxy_key = headers.get("X-Api-Key", "")
    return proxy_key == api_key
