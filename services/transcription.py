"""
Сервис транскрибации аудио через AssemblyAI с разделением по спикерам.
"""
import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass

import assemblyai as aai

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Результат транскрибации."""
    text: str                # полный текст с разметкой спикеров
    duration_seconds: int    # длительность записи в секундах
    word_count: int          # количество слов в транскрипте


async def transcribe_audio(file_path: str, api_key: str) -> TranscriptionResult:
    """
    Транскрибировать аудиофайл через AssemblyAI.

    Использует speaker diarization для разделения по спикерам.
    Выполняется в отдельном потоке, чтобы не блокировать event loop.
    """
    # Настраиваем API-ключ
    aai.settings.api_key = api_key

    # Конфигурация транскрибации
    config = aai.TranscriptionConfig(
        speech_model=aai.SpeechModel.best,  # "universal-3-pro"
        language_code="ru",
        speaker_labels=True,   # разделение по спикерам
        punctuate=True,
        format_text=True,
    )

    # Запускаем синхронный SDK в отдельном потоке
    result = await asyncio.to_thread(_run_transcription, file_path, config)
    return result


def _run_transcription(file_path: str, config: aai.TranscriptionConfig) -> TranscriptionResult:
    """
    Синхронная обёртка для AssemblyAI SDK (запускается через to_thread).
    """
    transcriber = aai.Transcriber()

    logger.info("Начинаю загрузку файла в AssemblyAI: %s", file_path)
    transcript = transcriber.transcribe(file_path, config=config)

    # Проверяем статус
    if transcript.status == aai.TranscriptStatus.error:
        error_msg = transcript.error or "Неизвестная ошибка AssemblyAI"
        logger.error("Ошибка транскрибации: %s", error_msg)
        raise TranscriptionError(error_msg)

    # Собираем текст с разметкой спикеров
    speaker_text = _format_speaker_text(transcript)

    # Считаем длительность (в миллисекундах → секунды)
    duration_ms = transcript.audio_duration or 0
    duration_seconds = int(duration_ms)

    # Считаем количество слов
    word_count = len(speaker_text.split()) if speaker_text else 0

    logger.info(
        "Транскрибация завершена: %d сек, %d слов",
        duration_seconds, word_count
    )

    return TranscriptionResult(
        text=speaker_text,
        duration_seconds=duration_seconds,
        word_count=word_count,
    )


def _format_speaker_text(transcript: aai.Transcript) -> str:
    """
    Форматировать транскрипт с разметкой спикеров.
    Результат: "Спикер A: текст\nСпикер B: текст\n..."
    """
    utterances = transcript.utterances
    if not utterances:
        # Если diarization не вернул utterances — отдаём plain text
        return transcript.text or ""

    # Маппинг букв для спикеров (A, B, C, ...)
    speaker_map: dict[str, str] = {}
    current_letter = ord("A")

    lines: list[str] = []
    for utterance in utterances:
        speaker_id = utterance.speaker
        if speaker_id not in speaker_map:
            speaker_map[speaker_id] = chr(current_letter)
            current_letter += 1

        label = f"Спикер {speaker_map[speaker_id]}"
        lines.append(f"{label}: {utterance.text}")

    return "\n".join(lines)


class TranscriptionError(Exception):
    """Ошибка при транскрибации аудио."""
    pass
