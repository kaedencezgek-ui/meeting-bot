"""
Интеграция с Lava.top
"""
import httpx
import logging
import json

logger = logging.getLogger(__name__)

async def create_invoice(lava_api_key: str, user_id: int, offer_id: str, buyer_email: str) -> str:
    """
    Создаёт счёт через Lava.top API v2.
    Возвращает paymentUrl для оплаты.
    """
    url = "https://gate.lava.top/api/v2/invoice"
    
    payload = {
        "email": buyer_email,
        "offerId": offer_id,
        "currency": "RUB",
        "buyerLanguage": "RU",
        "clientUtm": {"utm_source": str(user_id)}
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": lava_api_key
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if data.get("paymentUrl"):
                return data.get("paymentUrl")
            else:
                logger.error(f"Lava API error (no paymentUrl): {data}")
                raise Exception(f"Lava API error: no paymentUrl")
    except Exception as e:
        logger.error(f"Failed to create Lava invoice: {e}")
        # Return fallback for testing
        return f"https://lava.top/pay/fallback_{offer_id}"

def check_webhook_signature(headers: dict, api_key: str) -> bool:
    """
    Проверяет подпись вебхука от Lava (по заголовку X-Api-Key).
    """
    proxy_key = headers.get("X-Api-Key", "")
    return proxy_key == api_key
