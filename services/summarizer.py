"""
Сервис суммаризации транскриптов через OpenRouter (LLM).
"""
import logging

import httpx

logger = logging.getLogger(__name__)

# Эндпоинт OpenRouter
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Системный промпт для LLM
SYSTEM_PROMPT = (
    "Ты профессиональный бизнес-секретарь. Анализируй транскрипты "
    "деловых встреч и создавай чёткие структурированные отчёты на русском языке."
)

# Шаблон пользовательского промпта
USER_PROMPT_TEMPLATE = """\
Вот транскрипт встречи с разметкой спикеров:
{transcript}

Создай отчёт по структуре:
📋 КРАТКОЕ РЕЗЮМЕ (2-3 предложения о чём была встреча)
👥 УЧАСТНИКИ (список спикеров если можно определить роли)
✅ ПРИНЯТЫЕ РЕШЕНИЯ (нумерованный список)
📌 ЗАДАЧИ И ДЕДЛАЙНЫ (кто, что, когда — если упоминалось)
❓ ОТКРЫТЫЕ ВОПРОСЫ (что осталось нерешённым)
🔜 СЛЕДУЮЩИЕ ШАГИ"""


async def summarize_transcript(
    transcript: str,
    api_key: str,
    model: str,
) -> str:
    """
    Отправить транскрипт в OpenRouter и получить структурированный отчёт.

    Args:
        transcript: текст транскрипта с разметкой спикеров
        api_key: ключ OpenRouter
        model: название модели (например, anthropic/claude-3.5-sonnet)

    Returns:
        Готовый отчёт о встрече
    """
    user_prompt = USER_PROMPT_TEMPLATE.format(transcript=transcript)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 4096,
        "temperature": 0.3,  # низкая температура для более точного отчёта
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/ai_secretary_bot",
        "X-Title": "AI Secretary Bot",
    }

    logger.info("Отправляю транскрипт в OpenRouter (модель: %s)", model)

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            OPENROUTER_API_URL,
            json=payload,
            headers=headers,
        )

        if response.status_code != 200:
            error_text = response.text
            logger.error(
                "Ошибка OpenRouter [%d]: %s", response.status_code, error_text
            )
            raise SummarizationError(
                f"OpenRouter вернул ошибку {response.status_code}: {error_text}"
            )

        data = response.json()

    # Извлекаем ответ модели
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        logger.error("Неожиданный формат ответа OpenRouter: %s", data)
        raise SummarizationError("Не удалось разобрать ответ от LLM") from exc

    logger.info("Суммаризация завершена, длина отчёта: %d символов", len(content))
    return content


class SummarizationError(Exception):
    """Ошибка при суммаризации транскрипта."""
    pass
