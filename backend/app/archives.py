from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from fastapi import UploadFile

from .config import Settings


class ArchiveValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedArchive:
    path: Path
    source_uuid: uuid.UUID
    project_name: str
    sha256: str
    size_bytes: int


_WINDOWS_INVALID = re.compile(r'[<>:"|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def _validate_windows_segment(segment: str) -> None:
    if not segment or segment in {".", ".."}:
        raise ArchiveValidationError("Archive contains an invalid path segment")
    if segment.endswith((" ", ".")) or _WINDOWS_INVALID.search(segment):
        raise ArchiveValidationError("Archive path is not safe on Windows")
    if segment.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
        raise ArchiveValidationError("Archive path uses a reserved Windows name")


def _validate_zip(path: Path, settings: Settings) -> tuple[uuid.UUID, str]:
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchiveValidationError("Uploaded file is not a valid ZIP archive") from exc

    with archive:
        entries = archive.infolist()
        if not entries:
            raise ArchiveValidationError("ZIP archive is empty")
        if len(entries) > settings.max_archive_entries:
            raise ArchiveValidationError("ZIP archive contains too many entries")

        roots: set[str] = set()
        seen: set[str] = set()
        gprj_names: list[str] = []
        total_uncompressed = 0
        total_compressed = 0

        for info in entries:
            original = getattr(info, "orig_filename", info.filename)
            if "\x00" in original or "\\" in original:
                raise ArchiveValidationError("ZIP archive contains an unsafe path")
            path_name = PurePosixPath(info.filename)
            if path_name.is_absolute() or ".." in path_name.parts or not path_name.parts:
                raise ArchiveValidationError("ZIP archive contains an unsafe path")
            for segment in path_name.parts:
                _validate_windows_segment(segment)

            normalized = path_name.as_posix().rstrip("/").casefold()
            if normalized in seen:
                raise ArchiveValidationError("ZIP archive contains duplicate paths")
            seen.add(normalized)
            roots.add(path_name.parts[0])

            unix_mode = (info.external_attr >> 16) & 0xFFFF
            if unix_mode and stat.S_ISLNK(unix_mode):
                raise ArchiveValidationError("ZIP archive may not contain symbolic links")
            if info.flag_bits & 0x1:
                raise ArchiveValidationError("Encrypted ZIP entries are not supported")

            if not info.is_dir():
                total_uncompressed += info.file_size
                total_compressed += info.compress_size
                if len(path_name.parts) == 2 and path_name.suffix.casefold() == ".gprj":
                    gprj_names.append(path_name.stem)

        if len(roots) != 1:
            raise ArchiveValidationError(
                "ZIP must contain exactly one top-level UUID directory"
            )
        root = next(iter(roots))
        try:
            source_uuid = uuid.UUID(root)
        except ValueError as exc:
            raise ArchiveValidationError("Top-level directory name must be a UUID") from exc
        if str(source_uuid) != root.lower():
            raise ArchiveValidationError("Top-level UUID directory must use canonical form")
        if len(gprj_names) != 1:
            raise ArchiveValidationError(
                "UUID directory must contain exactly one direct .gprj file"
            )
        if total_uncompressed > settings.max_uncompressed_bytes:
            raise ArchiveValidationError("ZIP expands beyond the configured size limit")
        if total_uncompressed and (
            total_compressed == 0
            or total_uncompressed > total_compressed * settings.max_compression_ratio
        ):
            raise ArchiveValidationError("ZIP compression ratio exceeds the safety limit")

        # Reading every file makes zipfile verify CRCs and rejects truncated payloads.
        try:
            for info in entries:
                if info.is_dir():
                    continue
                with archive.open(info, "r") as member:
                    while member.read(1024 * 1024):
                        pass
        except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
            raise ArchiveValidationError("ZIP entry data is corrupt or unsupported") from exc

        return source_uuid, gprj_names[0]


async def receive_and_validate(upload: UploadFile, settings: Settings) -> ValidatedArchive:
    suffix = ".zip"
    descriptor, temporary_name = tempfile.mkstemp(prefix="gennect-upload-", suffix=suffix)
    path = Path(temporary_name)
    digest = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(descriptor, "wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise ArchiveValidationError("ZIP upload exceeds the configured size limit")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        source_uuid, project_name = _validate_zip(path, settings)
        return ValidatedArchive(
            path=path,
            source_uuid=source_uuid,
            project_name=project_name,
            sha256=digest.hexdigest(),
            size_bytes=size,
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


def validate_stored(file_object: BinaryIO, settings: Settings) -> ValidatedArchive:
    descriptor, temporary_name = tempfile.mkstemp(prefix="gennect-rebuild-", suffix=".zip")
    path = Path(temporary_name)
    digest = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(descriptor, "wb") as output:
            while chunk := file_object.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise ArchiveValidationError("Stored archive exceeds size limit")
                digest.update(chunk)
                output.write(chunk)
        source_uuid, project_name = _validate_zip(path, settings)
        return ValidatedArchive(
            path=path,
            source_uuid=source_uuid,
            project_name=project_name,
            sha256=digest.hexdigest(),
            size_bytes=size,
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise

