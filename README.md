# 🤖 AI Секретарь — Telegram-бот

Telegram-бот, который обрабатывает аудиозаписи совещаний: транскрибирует с разделением по спикерам и создаёт структурированный отчёт.

## Возможности

- 🎙 Транскрибация аудио с разделением по спикерам (AssemblyAI)
- 📋 Автоматический анализ и структурирование отчёта (LLM через OpenRouter)
- 👥 Определение участников и их ролей
- ✅ Выделение решений, задач и дедлайнов
- 📊 Статистика: длительность записи, количество слов

## Стек технологий

| Компонент | Технология |
|-----------|-----------|
| Telegram API | aiogram 3.x |
| Транскрибация | AssemblyAI (diarization) |
| LLM | OpenRouter (Claude, GPT и др.) |
| HTTP-клиент | httpx |
| База данных | SQLite + SQLAlchemy (async) |
| Конфигурация | python-dotenv |

## Быстрый старт

### 1. Клонируйте и установите зависимости

```bash
cd meeting_bot
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Настройте переменные окружения

Скопируйте шаблон и заполните ключи:

```bash
cp .env.example .env
```

Откройте `.env` и заполните:

```env
BOT_TOKEN=123456:ABC-DEF...        # токен от @BotFather
ASSEMBLYAI_API_KEY=ваш_ключ       # от assemblyai.com
OPENROUTER_API_KEY=ваш_ключ       # от openrouter.ai
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet  # или другая модель
```

**Где получить ключи:**
- `BOT_TOKEN` — создайте бота через [@BotFather](https://t.me/BotFather)
- `ASSEMBLYAI_API_KEY` — зарегистрируйтесь на [assemblyai.com](https://www.assemblyai.com/)
- `OPENROUTER_API_KEY` — зарегистрируйтесь на [openrouter.ai](https://openrouter.ai/)

### 3. Запустите бота

```bash
python bot.py
```

## Использование

1. Откройте бота в Telegram
2. Нажмите `/start`
3. Отправьте аудиозапись совещания (голосовое, mp3, m4a, ogg, wav)
4. Дождитесь обработки (несколько минут в зависимости от длительности)
5. Получите структурированный отчёт

## Структура отчёта

```
📋 КРАТКОЕ РЕЗЮМЕ
👥 УЧАСТНИКИ
✅ ПРИНЯТЫЕ РЕШЕНИЯ
📌 ЗАДАЧИ И ДЕДЛАЙНЫ
❓ ОТКРЫТЫЕ ВОПРОСЫ
🔜 СЛЕДУЮЩИЕ ШАГИ

⏱️ Длительность: X мин | 🔤 Слов: X
```

## Структура проекта

```
meeting_bot/
├── bot.py                  # точка входа
├── config.py               # загрузка .env
├── database.py             # модели SQLAlchemy и CRUD
├── handlers/
│   ├── start.py            # /start, /help
│   └── audio.py            # приём и обработка аудио
├── services/
│   ├── transcription.py    # логика AssemblyAI
│   └── summarizer.py       # логика OpenRouter
├── .env.example            # шаблон переменных
├── requirements.txt        # зависимости
└── README.md               # этот файл
```

## Ограничения

- Максимальный размер файла: 500 МБ
- Поддерживаемые форматы: mp3, m4a, ogg, wav, oga, opus
- Язык распознавания: русский
