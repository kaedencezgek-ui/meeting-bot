"""
Модели базы данных и CRUD-операции (SQLAlchemy async + SQLite).
"""
import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Integer,
    String,
    ForeignKey,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ────────────────────────── Модели ──────────────────────────


class Base(DeclarativeBase):
    pass


class MeetingStatus(str, PyEnum):
    """Статус обработки записи встречи."""
    PENDING = "pending"
    DONE = "done"
    ERROR = "error"


class User(Base):
    """Таблица пользователей Telegram."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    meetings: Mapped[list["Meeting"]] = relationship(back_populates="user")


class Meeting(Base):
    """Таблица записей встреч."""
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(MeetingStatus), default=MeetingStatus.PENDING
    )

    user: Mapped["User"] = relationship(back_populates="meetings")


# ────────────────────── Инициализация БД ──────────────────────


engine = create_async_engine("sqlite+aiosqlite:///bot.db", echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Создать все таблицы при первом запуске."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ────────────────────── CRUD-операции ──────────────────────


async def get_or_create_user(
    session: AsyncSession, telegram_id: int, username: str | None
) -> User:
    """Получить пользователя по telegram_id или создать нового."""
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user


async def create_meeting(session: AsyncSession, user_id: int) -> Meeting:
    """Создать запись о новой встрече со статусом PENDING."""
    meeting = Meeting(user_id=user_id, status=MeetingStatus.PENDING)
    session.add(meeting)
    await session.commit()
    await session.refresh(meeting)
    return meeting


async def update_meeting(
    session: AsyncSession,
    meeting_id: int,
    *,
    status: MeetingStatus | None = None,
    duration_seconds: int | None = None,
    word_count: int | None = None,
) -> None:
    """Обновить запись встречи (статус, длительность, кол-во слов)."""
    stmt = select(Meeting).where(Meeting.id == meeting_id)
    result = await session.execute(stmt)
    meeting = result.scalar_one_or_none()
    if meeting is None:
        return

    if status is not None:
        meeting.status = status
    if duration_seconds is not None:
        meeting.duration_seconds = duration_seconds
    if word_count is not None:
        meeting.word_count = word_count

    await session.commit()
