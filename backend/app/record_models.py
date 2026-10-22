"""Record catalog owns associations; original and derived files are immutable."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator
from .db import Base


class UTCDateTime(TypeDecorator):
    """Preserve the same instant on PostgreSQL and SQLite (which drops tzinfo)."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Record timestamps require a timezone")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class RecordFile(Base):
    __tablename__ = "record_files"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    note: Mapped[str] = mapped_column(Text, default="")
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    size_bytes: Mapped[int] = mapped_column()
    original_key: Mapped[str] = mapped_column(String(1024))
    data_key: Mapped[str | None] = mapped_column(String(1024))
    csv_key: Mapped[str | None] = mapped_column(String(1024))
    inspection: Mapped[dict] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    time_source: Mapped[str] = mapped_column(String(32), default="unknown")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now(), index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": revision}
