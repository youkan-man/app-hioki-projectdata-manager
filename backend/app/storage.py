from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import BinaryIO, ContextManager, Protocol


class ArchiveStorage(Protocol):
    def put_atomic(self, key: str, source: Path) -> None: ...

    def open(self, key: str) -> ContextManager[BinaryIO]: ...

    def iter_keys(self) -> Iterator[str]: ...


class FilesystemArchiveStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        relative = PurePosixPath(key)
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise ValueError("Invalid archive storage key")
        candidate = self.root.joinpath(*relative.parts).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("Archive storage key escapes root")
        return candidate

    def put_atomic(self, key: str, source: Path) -> None:
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent, prefix=".upload-", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_name, destination)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass

    @contextmanager
    def open(self, key: str) -> Iterator[BinaryIO]:
        with self._path(key).open("rb") as archive:
            yield archive

    def iter_keys(self) -> Iterator[str]:
        for path in sorted(self.root.rglob("*.zip")):
            if path.is_file():
                yield path.relative_to(self.root).as_posix()
