from __future__ import annotations

import hashlib
import os
import re
import shutil
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


class ArchiveIdentityError(ValueError):
    pass


class SourceUuidRequiredError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedArchive:
    path: Path
    source_uuid: uuid.UUID
    project_name: str
    sha256: str
    size_bytes: int
    legacy_wrapped: bool = False


@dataclass(frozen=True, slots=True)
class ArchiveLayout:
    project_name: str
    wrapped_uuid: uuid.UUID | None


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


def _validate_zip(path: Path, settings: Settings) -> ArchiveLayout:
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

        seen: set[str] = set()
        entry_paths: list[PurePosixPath] = []
        file_paths: list[PurePosixPath] = []
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
            entry_paths.append(path_name)

            normalized = path_name.as_posix().rstrip("/").casefold()
            if normalized in seen:
                raise ArchiveValidationError("ZIP archive contains duplicate paths")
            seen.add(normalized)
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            if unix_mode and stat.S_ISLNK(unix_mode):
                raise ArchiveValidationError("ZIP archive may not contain symbolic links")
            if info.flag_bits & 0x1:
                raise ArchiveValidationError("Encrypted ZIP entries are not supported")

            if not info.is_dir():
                file_paths.append(path_name)
                total_uncompressed += info.file_size
                total_compressed += info.compress_size
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

        flat_gprj = [
            member.stem
            for member in file_paths
            if len(member.parts) == 1 and member.suffix.casefold() == ".gprj"
        ]
        if len(flat_gprj) == 1:
            return ArchiveLayout(project_name=flat_gprj[0], wrapped_uuid=None)

        roots = {member.parts[0] for member in entry_paths}
        if len(roots) == 1:
            root = next(iter(roots))
            try:
                wrapped_uuid = uuid.UUID(root)
            except ValueError:
                wrapped_uuid = None
            legacy_gprj = [
                member.stem
                for member in file_paths
                if len(member.parts) == 2
                and member.suffix.casefold() == ".gprj"
            ]
            if (
                wrapped_uuid is not None
                and root.lower() == str(wrapped_uuid)
                and len(legacy_gprj) == 1
            ):
                return ArchiveLayout(
                    project_name=legacy_gprj[0], wrapped_uuid=wrapped_uuid
                )

        raise ArchiveValidationError(
            "ZIP must contain exactly one root-level .gprj file; a legacy archive "
            "may instead contain one canonical UUID wrapper directory"
        )


def _digest_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as archive_file:
        while chunk := archive_file.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _flatten_legacy_archive(path: Path, settings: Settings) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="gennect-canonical-", suffix=".zip"
    )
    os.close(descriptor)
    output_path = Path(temporary_name)
    try:
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(
            output_path, "w", allowZip64=True
        ) as output:
            for info in source.infolist():
                relative_parts = PurePosixPath(info.filename).parts[1:]
                if not relative_parts:
                    continue
                relative_name = "/".join(relative_parts)
                if info.is_dir():
                    relative_name += "/"
                target = zipfile.ZipInfo(relative_name, date_time=info.date_time)
                target.compress_type = info.compress_type
                target.comment = info.comment
                target.external_attr = info.external_attr
                target.create_system = info.create_system
                if info.is_dir():
                    output.writestr(target, b"")
                    continue
                with source.open(info, "r") as source_member, output.open(
                    target, "w", force_zip64=True
                ) as target_member:
                    shutil.copyfileobj(source_member, target_member, length=1024 * 1024)
        if output_path.stat().st_size > settings.max_upload_bytes:
            raise ArchiveValidationError(
                "Normalized ZIP exceeds the configured size limit"
            )
        return output_path
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError) as exc:
        output_path.unlink(missing_ok=True)
        raise ArchiveValidationError(
            "Legacy ZIP could not be normalized to the canonical flat layout"
        ) from exc
    except Exception:
        output_path.unlink(missing_ok=True)
        raise


def _canonicalize(archive: ValidatedArchive, settings: Settings) -> ValidatedArchive:
    if not archive.legacy_wrapped:
        return archive
    canonical_path = _flatten_legacy_archive(archive.path, settings)
    try:
        digest, size = _digest_file(canonical_path)
    except Exception:
        canonical_path.unlink(missing_ok=True)
        raise
    archive.path.unlink(missing_ok=True)
    return ValidatedArchive(
        path=canonical_path,
        source_uuid=archive.source_uuid,
        project_name=archive.project_name,
        sha256=digest,
        size_bytes=size,
        legacy_wrapped=False,
    )


async def receive_and_validate(
    upload: UploadFile, settings: Settings, source_uuid: uuid.UUID | None
) -> ValidatedArchive:
    suffix = ".zip"
    descriptor, temporary_name = tempfile.mkstemp(prefix="gennect-upload-", suffix=suffix)
    path = Path(temporary_name)
    size = 0
    try:
        with os.fdopen(descriptor, "wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise ArchiveValidationError("ZIP upload exceeds the configured size limit")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        layout = _validate_zip(path, settings)
        if layout.wrapped_uuid is not None:
            if source_uuid is not None and source_uuid != layout.wrapped_uuid:
                raise ArchiveIdentityError(
                    "source_uuid does not match the legacy ZIP wrapper directory"
                )
            resolved_uuid = layout.wrapped_uuid
        elif source_uuid is None:
            raise SourceUuidRequiredError(
                "source_uuid is required for a flat ZIP when its filename does not identify it"
            )
        else:
            resolved_uuid = source_uuid
        digest, stored_size = _digest_file(path)
        validated = ValidatedArchive(
            path=path,
            source_uuid=resolved_uuid,
            project_name=layout.project_name,
            sha256=digest,
            size_bytes=stored_size,
            legacy_wrapped=layout.wrapped_uuid is not None,
        )
        return _canonicalize(validated, settings)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


def validate_stored(
    file_object: BinaryIO, settings: Settings, source_uuid: uuid.UUID
) -> ValidatedArchive:
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
        layout = _validate_zip(path, settings)
        if layout.wrapped_uuid is not None and layout.wrapped_uuid != source_uuid:
            raise ArchiveIdentityError(
                "Stored ZIP wrapper UUID does not match its storage key"
            )
        return ValidatedArchive(
            path=path,
            source_uuid=source_uuid,
            project_name=layout.project_name,
            sha256=digest.hexdigest(),
            size_bytes=size,
            legacy_wrapped=layout.wrapped_uuid is not None,
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise


def prepare_flat_download(
    file_object: BinaryIO, settings: Settings, source_uuid: uuid.UUID
) -> Path:
    """Copy a stored archive to a temporary canonical flat ZIP for download."""
    validated = validate_stored(file_object, settings, source_uuid)
    return _canonicalize(validated, settings).path
