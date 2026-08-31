from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .archives import ArchiveValidationError, ValidatedArchive, validate_stored
from .config import Settings
from .models import Project, ProjectVersion
from .storage import ArchiveStorage


class ProjectDeletedError(RuntimeError):
    pass


def _lock_source_uuid(session: Session, source_uuid: uuid.UUID) -> None:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        lock_id = int.from_bytes(
            hashlib.sha256(source_uuid.bytes).digest()[:8], "big", signed=True
        )
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})


def import_archive(
    session: Session,
    storage: ArchiveStorage,
    archive: ValidatedArchive,
    note: str | None,
) -> Project:
    _lock_source_uuid(session, archive.source_uuid)
    project = session.scalar(
        select(Project)
        .where(Project.source_uuid == archive.source_uuid)
        .with_for_update()
    )
    if project is None:
        project = Project(
            source_uuid=archive.source_uuid,
            project_name=archive.project_name,
            display_name=archive.project_name,
        )
        session.add(project)
        session.flush()
    elif project.deleted_at is not None:
        raise ProjectDeletedError("Project is deleted; restore it before importing a version")
    elif project.project_name != archive.project_name:
        old_project_name = project.project_name
        project.project_name = archive.project_name
        if project.display_name == old_project_name:
            project.display_name = archive.project_name

    # Saving a new version is also the project's latest activity.
    project.updated_at = datetime.now(timezone.utc)

    current = session.scalar(
        select(func.max(ProjectVersion.version_number)).where(
            ProjectVersion.project_id == project.id
        )
    )
    version_number = (current or 0) + 1
    archive_key = (
        f"{archive.source_uuid}/{version_number:08d}-{archive.sha256}.zip"
    )
    storage.put_atomic(archive_key, archive.path)
    version = ProjectVersion(
        project=project,
        version_number=version_number,
        archive_key=archive_key,
        sha256=archive.sha256,
        size_bytes=archive.size_bytes,
        note=note,
    )
    session.add(version)
    session.flush()
    session.refresh(project)
    return project


@dataclass(slots=True)
class RebuildCounts:
    archives_seen: int = 0
    projects_created: int = 0
    versions_created: int = 0
    archives_skipped: int = 0


_KEY_VERSION = re.compile(r"^(?P<version>[0-9]{8})-[0-9a-f]{64}\.zip$")


def rebuild_index(
    session: Session, storage: ArchiveStorage, settings: Settings
) -> RebuildCounts:
    counts = RebuildCounts()
    for key in storage.iter_keys():
        counts.archives_seen += 1
        key_parts = key.split("/")
        match = _KEY_VERSION.match(key_parts[-1])
        if len(key_parts) != 2 or match is None:
            counts.archives_skipped += 1
            continue
        try:
            source_uuid = uuid.UUID(key_parts[0])
            if key_parts[0] != str(source_uuid):
                raise ValueError("Archive key UUID is not canonical")
            with storage.open(key) as archive_file:
                validated = validate_stored(archive_file, settings, source_uuid)
            expected_digest = key_parts[-1][9:-4]
            if expected_digest != validated.sha256:
                counts.archives_skipped += 1
                continue
            version_number = int(match.group("version"))
            _lock_source_uuid(session, validated.source_uuid)
            project = session.scalar(
                select(Project)
                .where(Project.source_uuid == validated.source_uuid)
                .with_for_update()
            )
            if project is None:
                project = Project(
                    source_uuid=validated.source_uuid,
                    project_name=validated.project_name,
                    display_name=validated.project_name,
                )
                session.add(project)
                session.flush()
                counts.projects_created += 1
            existing = session.scalar(
                select(ProjectVersion).where(ProjectVersion.archive_key == key)
            )
            number_taken = session.scalar(
                select(ProjectVersion.id).where(
                    ProjectVersion.project_id == project.id,
                    ProjectVersion.version_number == version_number,
                )
            )
            if existing is not None or number_taken is not None:
                counts.archives_skipped += 1
                continue
            session.add(
                ProjectVersion(
                    project=project,
                    version_number=version_number,
                    archive_key=key,
                    sha256=validated.sha256,
                    size_bytes=validated.size_bytes,
                    note="Recovered from archive storage",
                )
            )
            session.flush()
            counts.versions_created += 1
        except (ArchiveValidationError, OSError, ValueError):
            counts.archives_skipped += 1
        finally:
            if "validated" in locals():
                validated.path.unlink(missing_ok=True)
                del validated
    return counts
