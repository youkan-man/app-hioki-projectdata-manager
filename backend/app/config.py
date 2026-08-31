from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    archive_root: Path
    storage_backend: str = "filesystem"
    rebuild_index_on_startup: bool = False
    max_upload_bytes: int = 2 * 1024 * 1024 * 1024
    max_archive_entries: int = 20_000
    max_uncompressed_bytes: int = 8 * 1024 * 1024 * 1024
    max_compression_ratio: int = 250
    max_configuration_bytes: int = 16 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql+psycopg://gennect:gennect@postgres:5432/gennect",
            ),
            archive_root=Path(os.getenv("ARCHIVE_ROOT", "./data/archives")),
            storage_backend=os.getenv("STORAGE_BACKEND", "filesystem"),
            rebuild_index_on_startup=_bool_env("REBUILD_INDEX_ON_STARTUP"),
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(2 * 1024**3))),
            max_archive_entries=int(os.getenv("MAX_ARCHIVE_ENTRIES", "20000")),
            max_uncompressed_bytes=int(
                os.getenv("MAX_UNCOMPRESSED_BYTES", str(8 * 1024**3))
            ),
            max_compression_ratio=int(os.getenv("MAX_COMPRESSION_RATIO", "250")),
            max_configuration_bytes=int(
                os.getenv("MAX_CONFIGURATION_BYTES", str(16 * 1024**2))
            ),
        )
        if settings.storage_backend != "filesystem":
            raise ValueError(
                f"Unsupported STORAGE_BACKEND: {settings.storage_backend!r}"
            )
        if min(
            settings.max_upload_bytes,
            settings.max_archive_entries,
            settings.max_uncompressed_bytes,
            settings.max_compression_ratio,
            settings.max_configuration_bytes,
        ) <= 0:
            raise ValueError("Archive safety limits must be positive")
        return settings
