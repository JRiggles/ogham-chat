from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column
from sqlmodel import Field, Session, SQLModel, col, create_engine, select

from backend.core.message import ChatMessage


class ChatMessageRow(SQLModel, table=True):  # type: ignore[call-arg]
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
    if database_url.startswith(('postgres://', 'postgresql://')):
        suffix = database_url.split('://', 1)[1]
        return f'postgresql+psycopg://{suffix}'
    return database_url


class SQLMessageStore:
    def __init__(self, database_url: str) -> None:
        normalized_db_url = _normalize_database_url(database_url)
        self.engine = create_engine(normalized_db_url, pool_pre_ping=True)
        SQLModel.metadata.create_all(self.engine)

    def add(self, message: ChatMessage) -> None:
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

    def get_for_user(self, user_id: str) -> list[ChatMessage]:
        return self.get_for_user_after(user_id=user_id, after=None)

    def get_for_user_after(
        self, user_id: str, after: datetime | None = None
    ) -> list[ChatMessage]:
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
                created_at=row.created_at,
                is_system=row.is_system,
                metadata=row.metadata_json,
            )
            for row in rows
        ]
