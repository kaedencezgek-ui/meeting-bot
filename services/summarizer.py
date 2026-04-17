"""
Сервис суммаризации транскриптов через OpenAI (GPT).
"""
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

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
    Отправить транскрипт в OpenAI и получить структурированный отчёт.

    Args:
        transcript: текст транскрипта с разметкой спикеров
        api_key: ключ OpenAI
        model: название модели (например, gpt-4o)

    Returns:
        Готовый отчёт о встрече
    """
    client = AsyncOpenAI(api_key=api_key)
    user_prompt = USER_PROMPT_TEMPLATE.format(transcript=transcript)

    logger.info("Отправляю транскрипт в OpenAI (модель: %s)", model)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=4096,
            temperature=0.3,
        )
        content = response.choices[0].message.content
    except Exception as exc:
        logger.error("Ошибка OpenAI: %s", exc)
        raise SummarizationError(f"OpenAI вернул ошибку: {exc}")

    logger.info("Суммаризация завершена, длина отчёта: %d символов", len(content))
    return content


class SummarizationError(Exception):
    """Ошибка при суммаризации транскрипта."""
    pass
