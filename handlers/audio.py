"""
Хендлер приёма и обработки аудиофайлов / голосовых сообщений.
"""
import asyncio
import logging
import os
import tempfile

from aiogram import Bot, Router, F
from aiogram.types import Message

from config import Config
from database import (
    MeetingStatus,
    async_session,
    create_meeting,
    get_or_create_user,
    update_meeting,
    update_user_minutes,
)
from services.transcription import TranscriptionError, transcribe_audio
from services.summarizer import SummarizationError, summarize_transcript
from services.cloud_download import (
    CloudDownloadError,
    detect_cloud_type,
    download_from_cloud,
    extract_cloud_link,
)

logger = logging.getLogger(__name__)
router = Router(name="audio")

# Допустимые MIME-типы и расширения
ALLOWED_EXTENSIONS = {".mp3", ".m4a", ".ogg", ".wav", ".oga", ".opus"}
MAX_TELEGRAM_MESSAGE_LENGTH = 4096

# Лимит Telegram Bot API на скачивание файлов
TELEGRAM_DOWNLOAD_LIMIT_BYTES = 20 * 1024 * 1024  # 20 МБ





async def _download_file(bot: Bot, file_id: str, dest_path: str) -> None:
    """Скачать файл из Telegram по file_id."""
    file = await bot.get_file(file_id)
    await bot.download_file(file.file_path, dest_path)


async def _send_long_message(message: Message, text: str) -> None:
    """
    Отправить длинный текст, разбивая на части по 4096 символов.
    Разбиение происходит по границе строки, чтобы не резать слова.
    """
    while text:
        if len(text) <= MAX_TELEGRAM_MESSAGE_LENGTH:
            await message.answer(text, parse_mode="HTML")
            break

        # Ищем последний перенос строки в пределах лимита
        split_pos = text.rfind("\n", 0, MAX_TELEGRAM_MESSAGE_LENGTH)
        if split_pos == -1:
            # Если нет переноса строки — режем по пробелу
            split_pos = text.rfind(" ", 0, MAX_TELEGRAM_MESSAGE_LENGTH)
        if split_pos == -1:
            split_pos = MAX_TELEGRAM_MESSAGE_LENGTH

        chunk = text[:split_pos]
        text = text[split_pos:].lstrip()

        await message.answer(chunk, parse_mode="HTML")
        await asyncio.sleep(0.3)  # небольшая пауза между сообщениями


# ────────────────────── Голосовое сообщение ──────────────────────


@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot, config: Config) -> None:
    """Обработка голосового сообщения."""
    await _process_audio(
        message=message,
        bot=bot,
        config=config,
        file_id=message.voice.file_id,
        file_size=message.voice.file_size,
        file_name="voice.ogg",
    )


# ────────────────────── Аудиофайл / документ ──────────────────────


@router.message(F.audio)
async def handle_audio(message: Message, bot: Bot, config: Config) -> None:
    """Обработка аудиофайла (отправлен как «аудио»)."""
    audio = message.audio
    file_name = audio.file_name or "audio.mp3"

    # Проверяем расширение
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        await message.answer(
            f"❌ Формат <b>{ext}</b> не поддерживается.\n"
            f"Принимаю: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            parse_mode="HTML",
        )
        return

    await _process_audio(
        message=message,
        bot=bot,
        config=config,
        file_id=audio.file_id,
        file_size=audio.file_size,
        file_name=file_name,
    )


@router.message(F.document)
async def handle_document(message: Message, bot: Bot, config: Config) -> None:
    """Обработка документа (аудиофайл отправлен как файл)."""
    doc = message.document
    file_name = doc.file_name or "file"

    ext = os.path.splitext(file_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        # Это не аудиофайл — игнорируем молча или подсказываем
        await message.answer(
            "🤔 Этот файл не похож на аудиозапись.\n"
            f"Я принимаю форматы: {', '.join(sorted(ALLOWED_EXTENSIONS))}\n\n"
            "Отправьте аудиозапись совещания, и я создам отчёт.",
            parse_mode="HTML",
        )
        return

    await _process_audio(
        message=message,
        bot=bot,
        config=config,
        file_id=doc.file_id,
        file_size=doc.file_size,
        file_name=file_name,
    )


# ────────────────────── Основная логика обработки ──────────────────────


async def _process_audio(
    message: Message,
    bot: Bot,
    config: Config,
    file_id: str,
    file_size: int | None,
    file_name: str,
) -> None:
    """
    Общая логика обработки аудио:
    1. Проверка размера
    2. Скачивание файла
    3. Транскрибация через AssemblyAI
    4. Суммаризация через OpenRouter
    5. Отправка отчёта пользователю
    """

    # Проверяем размер файла
    max_bytes = config.max_file_size_mb * 1024 * 1024
    if file_size and file_size > max_bytes:
        await message.answer(
            f"❌ Файл слишком большой ({file_size // (1024*1024)} МБ).\n"
            f"Максимум: {config.max_file_size_mb} МБ.",
        )
        return

    # Проверяем лимит Telegram Bot API (20 МБ)
    if file_size and file_size > TELEGRAM_DOWNLOAD_LIMIT_BYTES:
        size_mb = file_size / (1024 * 1024)
        await message.answer(
            f"⚠️ Файл слишком большой для прямой загрузки через Telegram "
            f"({size_mb:.1f} МБ, лимит — 20 МБ).\n\n"
            "📎 Загрузите запись на <b>Google Drive</b> или <b>Яндекс Диск</b> "
            "и отправьте мне ссылку.\n\n"
            "<i>Убедитесь, что доступ по ссылке открыт (\"Все, у кого есть ссылка\").</i>",
            parse_mode="HTML",
        )
        return

    # Уведомляем пользователя о начале обработки
    status_msg = await message.answer(
        "⏳ Принял запись. Обрабатываю, это займёт несколько минут..."
    )

    # Создаём запись в БД
    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        # Check balance
        if user.minutes_balance <= 0:
            await message.answer(
                "❌ Недостаточно минут для обработки. Пожалуйста, пополните баланс.",
                reply_markup=__import__("aiogram.types", fromlist=["InlineKeyboardMarkup"]).InlineKeyboardMarkup(inline_keyboard=[[
                    __import__("aiogram.types", fromlist=["InlineKeyboardButton"]).InlineKeyboardButton(text="🛒 Купить пакет", callback_data="buy_menu_placeholder")
                ]])
            )
            # Send simplified message telling them to use /buy
            await message.answer("Для пополнения баланса используйте команду /buy")
            return
            
        meeting = await create_meeting(session, user_id=user.id)
        meeting_id = meeting.id

    # Скачиваем файл во временную директорию
    ext = os.path.splitext(file_name)[1] or ".ogg"
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    tmp_path = tmp_file.name
    tmp_file.close()

    try:
        await _download_file(bot, file_id, tmp_path)
        logger.info("Файл скачан: %s (%s)", file_name, tmp_path)

        # ── Шаг 1: транскрибация ──
        await status_msg.edit_text("🎙 Транскрибирую аудио (разделение по спикерам)...")

        transcript_result = await transcribe_audio(tmp_path, config.assemblyai_api_key)

        if not transcript_result.text.strip():
            await status_msg.edit_text(
                "⚠️ Не удалось распознать речь в записи. "
                "Убедитесь, что аудио содержит разборчивую речь."
            )
            async with async_session() as session:
                await update_meeting(session, meeting_id, status=MeetingStatus.ERROR)
            return

        # ── Шаг 2: суммаризация ──
        await status_msg.edit_text("🤖 Анализирую транскрипт и составляю отчёт...")

        report = await summarize_transcript(
            transcript=transcript_result.text,
            api_key=config.openrouter_api_key,
            model=config.openrouter_model,
        )

        # ── Шаг 3: обновляем БД ──
        duration_minutes = max(1, transcript_result.duration_seconds // 60)
        async with async_session() as session:
            await update_meeting(
                session,
                meeting_id,
                status=MeetingStatus.DONE,
                duration_seconds=transcript_result.duration_seconds,
                word_count=transcript_result.word_count,
            )
            # Deduct minutes from user
            await update_user_minutes(session, user.id, added_balance=-duration_minutes, added_used=duration_minutes)
            user_balance = (await get_or_create_user(session, telegram_id=message.from_user.id, username=message.from_user.username)).minutes_balance


        # ── Шаг 4: отправляем отчёт ──
        await status_msg.edit_text("✅ Готово!")

        # Форматируем длительность
        duration_min = transcript_result.duration_seconds // 60
        duration_sec = transcript_result.duration_seconds % 60
        if duration_min > 0:
            duration_str = f"{duration_min} мин {duration_sec} сек"
        else:
            duration_str = f"{duration_sec} сек"

        # Добавляем статистику в конец отчёта
        footer = (
            f"\n\n{'─' * 30}\n"
            f"⏱️ Длительность записи: {duration_str} | "
            f"🔤 Слов в транскрипте: {transcript_result.word_count}\n"
            f"💰 Остаток баланса: {user_balance} минут"
        )

        full_report = report + footer
        await _send_long_message(message, full_report)

        logger.info(
            "Отчёт отправлен пользователю %d (встреча #%d)",
            message.from_user.id, meeting_id,
        )

    except TranscriptionError as exc:
        logger.exception("Ошибка транскрибации для встречи #%d", meeting_id)
        await status_msg.edit_text(
            f"❌ Ошибка при транскрибации аудио:\n<code>{exc}</code>\n\n"
            "Попробуйте отправить файл ещё раз или в другом формате.",
            parse_mode="HTML",
        )
        async with async_session() as session:
            await update_meeting(session, meeting_id, status=MeetingStatus.ERROR)

    except SummarizationError as exc:
        logger.exception("Ошибка суммаризации для встречи #%d", meeting_id)
        await status_msg.edit_text(
            f"❌ Ошибка при анализе транскрипта:\n<code>{exc}</code>\n\n"
            "Попробуйте ещё раз позже.",
            parse_mode="HTML",
        )
        async with async_session() as session:
            await update_meeting(session, meeting_id, status=MeetingStatus.ERROR)

    except Exception as exc:
        logger.exception("Непредвиденная ошибка для встречи #%d", meeting_id)
        await status_msg.edit_text(
            "❌ Произошла непредвиденная ошибка. Попробуйте позже."
        )
        async with async_session() as session:
            await update_meeting(session, meeting_id, status=MeetingStatus.ERROR)

    finally:
        # Удаляем временный файл
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ────────────────────── Обработка ссылок на облачные хранилища ──────────────────────


@router.message(F.text)
async def handle_cloud_link(message: Message, bot: Bot, config: Config) -> None:
    """
    Обработка текстового сообщения со ссылкой на Google Drive / Яндекс Диск.
    Скачивает файл напрямую из облака, минуя ограничения Telegram.
    """
    text = message.text.strip()

    # Извлекаем ссылку из текста
    link = extract_cloud_link(text)
    if not link:
        return  # не облачная ссылка — игнорируем

    cloud_type = detect_cloud_type(link)
    if not cloud_type:
        return  # не поддерживаемый сервис

    service_name = "Google Drive" if cloud_type == "gdrive" else "Яндекс Диск"
    logger.info("Получена ссылка на %s от пользователя %d", service_name, message.from_user.id)

    await _process_cloud_link(message, config, link, service_name)


async def _process_cloud_link(
    message: Message,
    config: Config,
    link: str,
    service_name: str,
) -> None:
    """
    Скачать файл из облака и запустить обработку (транскрибация + суммаризация).
    """
    status_msg = await message.answer(
        f"☁️ Скачиваю файл с {service_name}..."
    )

    # Создаём запись в БД
    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        if user.minutes_balance <= 0:
            await message.answer(
                "❌ Недостаточно минут для обработки. Пожалуйста, пополните баланс.",
                reply_markup=__import__("aiogram.types", fromlist=["InlineKeyboardMarkup"]).InlineKeyboardMarkup(inline_keyboard=[[
                    __import__("aiogram.types", fromlist=["InlineKeyboardButton"]).InlineKeyboardButton(text="🛒 Купить пакет", callback_data="buy_menu_placeholder")
                ]])
            )
            await message.answer("Для пополнения баланса используйте команду /buy")
            return
            
        meeting = await create_meeting(session, user_id=user.id)
        meeting_id = meeting.id

    tmp_path = None
    try:
        # Скачиваем из облака
        tmp_path, file_name = await download_from_cloud(link)
        logger.info("Файл скачан из облака: %s → %s", file_name, tmp_path)

        # ── Шаг 1: транскрибация ──
        await status_msg.edit_text("🎙 Транскрибирую аудио (разделение по спикерам)...")

        transcript_result = await transcribe_audio(tmp_path, config.assemblyai_api_key)

        if not transcript_result.text.strip():
            await status_msg.edit_text(
                "⚠️ Не удалось распознать речь в записи. "
                "Убедитесь, что аудио содержит разборчивую речь."
            )
            async with async_session() as session:
                await update_meeting(session, meeting_id, status=MeetingStatus.ERROR)
            return

        # ── Шаг 2: суммаризация ──
        await status_msg.edit_text("🤖 Анализирую транскрипт и составляю отчёт...")

        report = await summarize_transcript(
            transcript=transcript_result.text,
            api_key=config.openrouter_api_key,
            model=config.openrouter_model,
        )

        # ── Шаг 3: обновляем БД ──
        duration_minutes = max(1, transcript_result.duration_seconds // 60)
        async with async_session() as session:
            await update_meeting(
                session,
                meeting_id,
                status=MeetingStatus.DONE,
                duration_seconds=transcript_result.duration_seconds,
                word_count=transcript_result.word_count,
            )
            await update_user_minutes(session, user.id, added_balance=-duration_minutes, added_used=duration_minutes)
            user_balance = (await get_or_create_user(session, telegram_id=message.from_user.id, username=message.from_user.username)).minutes_balance


        # ── Шаг 4: отправляем отчёт ──
        await status_msg.edit_text("✅ Готово!")

        duration_min = transcript_result.duration_seconds // 60
        duration_sec = transcript_result.duration_seconds % 60
        if duration_min > 0:
            duration_str = f"{duration_min} мин {duration_sec} сек"
        else:
            duration_str = f"{duration_sec} сек"

        footer = (
            f"\n\n{'─' * 30}\n"
            f"☁️ Источник: {service_name} | "
            f"⏱️ Длительность: {duration_str} | "
            f"🔤 Слов: {transcript_result.word_count}\n"
            f"💰 Остаток баланса: {user_balance} минут"
        )

        full_report = report + footer
        await _send_long_message(message, full_report)

        logger.info(
            "Отчёт отправлен пользователю %d (встреча #%d, источник: %s)",
            message.from_user.id, meeting_id, service_name,
        )

    except CloudDownloadError as exc:
        logger.exception("Ошибка скачивания из облака для встречи #%d", meeting_id)
        await status_msg.edit_text(
            f"❌ Не удалось скачать файл с {service_name}:\n"
            f"<code>{exc}</code>\n\n"
            "Проверьте, что ссылка публичная и файл существует.",
            parse_mode="HTML",
        )
        async with async_session() as session:
            await update_meeting(session, meeting_id, status=MeetingStatus.ERROR)

    except TranscriptionError as exc:
        logger.exception("Ошибка транскрибации для встречи #%d", meeting_id)
        await status_msg.edit_text(
            f"❌ Ошибка при транскрибации аудио:\n<code>{exc}</code>\n\n"
            "Попробуйте отправить файл ещё раз или в другом формате.",
            parse_mode="HTML",
        )
        async with async_session() as session:
            await update_meeting(session, meeting_id, status=MeetingStatus.ERROR)

    except SummarizationError as exc:
        logger.exception("Ошибка суммаризации для встречи #%d", meeting_id)
        await status_msg.edit_text(
            f"❌ Ошибка при анализе транскрипта:\n<code>{exc}</code>\n\n"
            "Попробуйте ещё раз позже.",
            parse_mode="HTML",
        )
        async with async_session() as session:
            await update_meeting(session, meeting_id, status=MeetingStatus.ERROR)

    except Exception as exc:
        logger.exception("Непредвиденная ошибка для встречи #%d", meeting_id)
        await status_msg.edit_text(
            "❌ Произошла непредвиденная ошибка. Попробуйте позже."
        )
        async with async_session() as session:
            await update_meeting(session, meeting_id, status=MeetingStatus.ERROR)

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
