"""
Сервис скачивания файлов по ссылкам из Google Drive и Яндекс Диска.

Позволяет обойти ограничение Telegram на размер файла (20 МБ):
пользователь загружает аудио в облако и отправляет боту ссылку.
"""
import logging
import os
import re
import tempfile
from urllib.parse import urlparse, parse_qs

import httpx

logger = logging.getLogger(__name__)

# Паттерны для распознавания облачных ссылок
GDRIVE_PATTERNS = [
    # https://drive.google.com/file/d/FILE_ID/view
    re.compile(r"https?://drive\.google\.com/file/d/([a-zA-Z0-9_-]+)"),
    # https://drive.google.com/open?id=FILE_ID
    re.compile(r"https?://drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)"),
    # https://docs.google.com/uc?id=FILE_ID
    re.compile(r"https?://docs\.google\.com/uc\?.*id=([a-zA-Z0-9_-]+)"),
]

YADISK_PATTERNS = [
    # https://disk.yandex.ru/d/HASH or https://disk.yandex.ru/i/HASH
    re.compile(r"https?://disk\.yandex\.\w+/[di]/[\w-]+"),
    # https://yadi.sk/d/HASH or https://yadi.sk/i/HASH
    re.compile(r"https?://yadi\.sk/[di]/[\w-]+"),
]

# Допустимые аудио-расширения
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".ogg", ".wav", ".oga", ".opus", ".webm", ".aac", ".flac"}

# URL для распознавания ссылки в тексте
CLOUD_LINK_PATTERN = re.compile(
    r"https?://(?:drive\.google\.com|docs\.google\.com|disk\.yandex\.\w+|yadi\.sk)/\S+"
)

# Максимальный размер скачиваемого файла (500 МБ)
MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024


class CloudDownloadError(Exception):
    """Ошибка при скачивании файла из облака."""
    pass


def extract_cloud_link(text: str) -> str | None:
    """Извлечь облачную ссылку из текста сообщения."""
    match = CLOUD_LINK_PATTERN.search(text)
    return match.group(0) if match else None


def detect_cloud_type(url: str) -> str | None:
    """
    Определить тип облака по URL.
    Возвращает 'gdrive', 'yadisk' или None.
    """
    for pattern in GDRIVE_PATTERNS:
        if pattern.search(url):
            return "gdrive"
    for pattern in YADISK_PATTERNS:
        if pattern.search(url):
            return "yadisk"
    return None


def _extract_gdrive_file_id(url: str) -> str:
    """Извлечь file_id из ссылки на Google Drive."""
    for pattern in GDRIVE_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    raise CloudDownloadError("Не удалось извлечь ID файла из ссылки Google Drive.")


async def _download_from_gdrive(url: str, dest_path: str) -> str:
    """
    Скачать файл с Google Drive по публичной ссылке.
    Возвращает имя файла (из Content-Disposition или сгенерированное).
    """
    file_id = _extract_gdrive_file_id(url)
    # Google Drive прямая ссылка для скачивания
    download_url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"

    async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
        async with client.stream("GET", download_url) as response:
            if response.status_code != 200:
                raise CloudDownloadError(
                    f"Google Drive вернул ошибку {response.status_code}. "
                    "Убедитесь, что файл доступен по ссылке (настройте общий доступ)."
                )

            # Проверяем Content-Type — если HTML, значит доступ закрыт
            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type:
                raise CloudDownloadError(
                    "Файл недоступен для скачивания. "
                    "Откройте доступ по ссылке в настройках Google Drive."
                )

            # Извлекаем имя файла
            file_name = _parse_filename_from_headers(
                response.headers, fallback=f"gdrive_{file_id}.mp3"
            )

            # Скачиваем с прогрессом
            downloaded = 0
            with open(dest_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    downloaded += len(chunk)
                    if downloaded > MAX_DOWNLOAD_BYTES:
                        raise CloudDownloadError(
                            f"Файл слишком большой (более {MAX_DOWNLOAD_BYTES // (1024*1024)} МБ)."
                        )
                    f.write(chunk)

    logger.info("Скачан файл с Google Drive: %s (%d байт)", file_name, downloaded)
    return file_name


async def _download_from_yadisk(url: str, dest_path: str) -> str:
    """
    Скачать файл с Яндекс Диска по публичной ссылке.
    Использует публичный API Яндекс Диска.
    Возвращает имя файла.
    """
    api_url = "https://cloud-api.yandex.net/v1/disk/public/resources/download"

    async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
        # Шаг 1: получаем прямую ссылку на скачивание через API
        resp = await client.get(api_url, params={"public_key": url})

        if resp.status_code != 200:
            error_detail = ""
            try:
                data = resp.json()
                error_detail = data.get("message", "")
            except Exception:
                pass
            raise CloudDownloadError(
                f"Яндекс Диск вернул ошибку {resp.status_code}. {error_detail}\n"
                "Убедитесь, что ссылка публичная и файл существует."
            )

        data = resp.json()
        download_href = data.get("href")
        if not download_href:
            raise CloudDownloadError("Не удалось получить ссылку для скачивания с Яндекс Диска.")

        # Извлекаем имя файла из URL
        parsed = urlparse(download_href)
        params = parse_qs(parsed.query)
        file_name = params.get("filename", [None])[0]
        if not file_name:
            file_name = "yadisk_audio.mp3"

        # Шаг 2: скачиваем файл
        async with client.stream("GET", download_href) as response:
            if response.status_code != 200:
                raise CloudDownloadError(
                    f"Ошибка при скачивании файла с Яндекс Диска: HTTP {response.status_code}"
                )

            downloaded = 0
            with open(dest_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    downloaded += len(chunk)
                    if downloaded > MAX_DOWNLOAD_BYTES:
                        raise CloudDownloadError(
                            f"Файл слишком большой (более {MAX_DOWNLOAD_BYTES // (1024*1024)} МБ)."
                        )
                    f.write(chunk)

    logger.info("Скачан файл с Яндекс Диска: %s (%d байт)", file_name, downloaded)
    return file_name


async def download_from_cloud(url: str) -> tuple[str, str]:
    """
    Скачать файл из облака (Google Drive или Яндекс Диск).

    Args:
        url: публичная ссылка на файл

    Returns:
        Кортеж (путь_к_файлу, имя_файла)

    Raises:
        CloudDownloadError: если не удалось скачать файл
    """
    cloud_type = detect_cloud_type(url)
    if not cloud_type:
        raise CloudDownloadError(
            "Не удалось определить облачный сервис. "
            "Поддерживаются Google Drive и Яндекс Диск."
        )

    # Создаём временный файл
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".tmp")
    tmp_path = tmp_file.name
    tmp_file.close()

    try:
        if cloud_type == "gdrive":
            file_name = await _download_from_gdrive(url, tmp_path)
        else:
            file_name = await _download_from_yadisk(url, tmp_path)

        # Проверяем расширение файла
        ext = os.path.splitext(file_name)[1].lower()
        if ext not in AUDIO_EXTENSIONS:
            os.unlink(tmp_path)
            raise CloudDownloadError(
                f"Файл \"{file_name}\" не похож на аудиозапись (расширение: {ext}).\n"
                f"Поддерживаемые форматы: {', '.join(sorted(AUDIO_EXTENSIONS))}"
            )

        # Переименовываем временный файл с правильным расширением
        final_path = tmp_path + ext
        os.rename(tmp_path, final_path)

        return final_path, file_name

    except CloudDownloadError:
        # Удаляем временный файл при ошибке
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    except Exception as exc:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise CloudDownloadError(f"Ошибка при скачивании: {exc}") from exc


def _parse_filename_from_headers(headers: httpx.Headers, fallback: str) -> str:
    """Извлечь имя файла из заголовка Content-Disposition."""
    cd = headers.get("content-disposition", "")
    if cd:
        # filename*=UTF-8''...
        match = re.search(r"filename\*=(?:UTF-8''|utf-8'')(.+?)(?:;|$)", cd, re.IGNORECASE)
        if match:
            from urllib.parse import unquote
            return unquote(match.group(1).strip())

        # filename="..."
        match = re.search(r'filename="?([^";\n]+)"?', cd)
        if match:
            return match.group(1).strip()

    return fallback
