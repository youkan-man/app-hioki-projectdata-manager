from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    sha256: str
    size_bytes: int
    note: str | None
    created_at: datetime


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_uuid: uuid.UUID
    project_name: str
    display_name: str
    description: str | None
    access_scope: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    versions: list[VersionRead]


class ProjectList(BaseModel):
    items: list[ProjectRead]
    total: int


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)


class RebuildResult(BaseModel):
    archives_seen: int
    projects_created: int
    versions_created: int
    archives_skipped: int
