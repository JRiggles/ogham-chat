from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column, delete, func, or_
from sqlmodel import Field, Session, SQLModel, col, create_engine, select

from backend.core.message import ChatMessage


class ChatMessageRow(SQLModel, table=True):  # type: ignore[call-arg]
    """SQLModel row representation for persisted chat messages."""

    __tablename__ = 'chat_messages'  # type: ignore[assignment]

    message_id: UUID = Field(primary_key=True, index=True)
    sender: str = Field(index=True, max_length=64)
    recipient: str = Field(index=True, max_length=64)
    content: str = Field(max_length=4096)
    created_at: datetime = Field(index=True)
    is_system: bool = Field(default=False)
    metadata_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column('metadata_json', JSON, nullable=True),
    )


def _normalize_database_url(database_url: str) -> str:
    """Normalize Postgres URLs to the SQLAlchemy psycopg v3 driver format."""
    if database_url.startswith(('postgres://', 'postgresql://')):
        suffix = database_url.split('://', 1)[1]
        return f'postgresql+psycopg://{suffix}'
    return database_url


def _normalize_timestamp(created_at: datetime) -> datetime:
    """Convert naive or timezone-aware timestamps into UTC timestamps."""
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=UTC)
    return created_at.astimezone(UTC)


class SQLMessageStore:
    """SQL-backed implementation of chat message persistence and queries."""

    def __init__(self, database_url: str) -> None:
        """Create the SQL engine and ensure message tables exist."""
        normalized_db_url = _normalize_database_url(database_url)
        self.engine = create_engine(normalized_db_url, pool_pre_ping=True)
        SQLModel.metadata.create_all(self.engine)

    def add(self, message: ChatMessage) -> None:
        """Persist one message row to the database."""
        row = ChatMessageRow(
            message_id=message.message_id,
            sender=message.sender,
            recipient=message.to,
            content=message.content,
            created_at=message.created_at,
            is_system=message.is_system,
            metadata_json=message.metadata,
        )
        with Session(self.engine) as session:
            session.add(row)
            session.commit()

    def purge_expired(
        self,
        *,
        retention_days: int = 180,
        now: datetime | None = None,
    ) -> int:
        """Delete rows older than retention and return the number removed."""
        effective_now = _normalize_timestamp(now or datetime.now(UTC))
        cutoff = effective_now - timedelta(days=retention_days)
        expires_before = col(ChatMessageRow.created_at) <= cutoff

        with Session(self.engine) as session:
            deleted_count = session.exec(
                select(func.count())
                .select_from(ChatMessageRow)
                .where(expires_before)
            ).one()

            if deleted_count:
                session.exec(delete(ChatMessageRow).where(expires_before))

            session.commit()

        return int(deleted_count)

    def get_for_user(self, user_id: str) -> list[ChatMessage]:
        """Return all messages addressed to a specific user."""
        return self.get_for_user_after(user_id=user_id, after=None)

    def get_for_user_after(
        self, user_id: str, after: datetime | None = None
    ) -> list[ChatMessage]:
        """Return user-directed messages newer than an optional timestamp."""
        statement = select(ChatMessageRow).where(
            ChatMessageRow.recipient == user_id
        )
        if after is not None:
            statement = statement.where(ChatMessageRow.created_at > after)
        statement = statement.order_by(col(ChatMessageRow.created_at))

        with Session(self.engine) as session:
            rows = session.exec(statement).all()

        return [
            ChatMessage(
                message_id=row.message_id,
                sender=row.sender,
                to=row.recipient,
                content=row.content,
                created_at=_normalize_timestamp(row.created_at),
                is_system=row.is_system,
                metadata=row.metadata_json,
            )
            for row in rows
        ]

    def get_conversation(
        self,
        user_id: str,
        peer_id: str,
        after: datetime | None = None,
    ) -> list[ChatMessage]:
        """Return ordered direct messages exchanged between two users."""
        statement = select(ChatMessageRow).where(
            or_(
                (
                    (col(ChatMessageRow.sender) == user_id)
                    & (col(ChatMessageRow.recipient) == peer_id)
                ),
                (
                    (col(ChatMessageRow.sender) == peer_id)
                    & (col(ChatMessageRow.recipient) == user_id)
                ),
            )
        )
        if after is not None:
            statement = statement.where(ChatMessageRow.created_at > after)
        statement = statement.order_by(col(ChatMessageRow.created_at))

        with Session(self.engine) as session:
            rows = session.exec(statement).all()

        return [
            ChatMessage(
                message_id=row.message_id,
                sender=row.sender,
                to=row.recipient,
                content=row.content,
                created_at=_normalize_timestamp(row.created_at),
                is_system=row.is_system,
                metadata=row.metadata_json,
            )
            for row in rows
        ]
