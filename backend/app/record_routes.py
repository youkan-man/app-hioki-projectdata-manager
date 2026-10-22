"""HTTP and persistence boundary for record files and their derived tables."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from .db import session_dependency
from .models import Project
from .record_models import RecordFile
from .record_data import (MAX_BYTES, DataError, Inspection, Table, bounds, csv_chunks,
                          inspect_record, normalized_stem, read_csv, select_rows)
from .storage import FilesystemArchiveStorage


class RecordUpdate(BaseModel):
    revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=10_000)
    project_id: uuid.UUID | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @model_validator(mode="after")
    def dates(self):
        for value in (self.started_at, self.ended_at):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("日時にはタイムゾーンが必要です。")
        if self.started_at and self.ended_at and self.started_at > self.ended_at:
            raise ValueError("終了日時は開始日時以降にしてください。")
        if self.name is not None and not self.name.strip():
            raise ValueError("名前を入力してください。")
        if self.note is None and "note" in self.model_fields_set:
            raise ValueError("メモは文字列で指定してください。")
        return self


def utc(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def register_record_routes(app) -> None:
    settings = app.state.settings
    storage = FilesystemArchiveStorage(settings.archive_root / "record-files")
    get_session = session_dependency(app.state.session_factory)

    def serialize(item: RecordFile, project: Project | None = None) -> dict:
        start, end = utc(item.started_at), utc(item.ended_at)
        return {"id": str(item.id), "project_id": str(item.project_id) if item.project_id else None,
                "project_name": project.display_name if project else None,
                "project_deleted": bool(project and project.deleted_at),
                "filename": item.filename, "name": item.name, "note": item.note,
                "sha256": item.sha256, "size_bytes": item.size_bytes,
                "started_at": start, "ended_at": end,
                "duration_seconds": (end - start).total_seconds() if start and end else None,
                "time_source": item.time_source, "created_at": utc(item.created_at),
                "deleted_at": utc(item.deleted_at), "revision": item.revision,
                "inspection": item.inspection, "has_companion_csv": item.csv_key is not None}

    def load(session: Session, record_id: uuid.UUID, editable: bool = False) -> RecordFile:
        item = session.get(RecordFile, record_id)
        if item is None:
            raise HTTPException(404, "記録がありません。")
        if editable and item.deleted_at:
            raise HTTPException(409, "削除済みの記録は先に復帰してください。")
        return item

    def project(session: Session, project_id: uuid.UUID | None) -> Project | None:
        if project_id is None:
            return None
        item = session.get(Project, project_id)
        if item is None or item.deleted_at:
            raise HTTPException(422, "関連付け先のプロジェクトが存在しないか削除済みです。")
        return item

    def commit(session: Session) -> None:
        try:
            session.commit()
        except (IntegrityError, StaleDataError) as exc:
            session.rollback()
            raise HTTPException(409, "別の操作と競合しました。一覧を更新してください。") from exc

    def save_file(path: Path, suffix: str) -> str:
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        key = f"{digest[:2]}/{digest}.{suffix}"
        storage.put_atomic(key, path)
        return key

    def save_tables(inspection: Inspection) -> str | None:
        if not inspection.tables:
            return None
        descriptor, name = tempfile.mkstemp(prefix="grcd-tables-")
        path = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump([asdict(t) for t in inspection.tables], output, ensure_ascii=False, allow_nan=False)
            return save_file(path, "json")
        finally:
            path.unlink(missing_ok=True)

    def receive(upload: UploadFile, limit: int) -> Path:
        descriptor, name = tempfile.mkstemp(prefix="grcd-upload-")
        path = Path(name)
        try:
            size = 0
            with os.fdopen(descriptor, "wb") as output:
                while chunk := upload.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, "アップロード上限を超えています。")
                    output.write(chunk)
            if size == 0:
                raise HTTPException(400, "空のファイルは登録できません。")
            return path
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def table_for(item: RecordFile, index: int) -> Table:
        if not item.data_key:
            raise HTTPException(422, "解析済みの表がありません。CSVの関連付けを確認してください。")
        try:
            with storage.open(item.data_key) as stream:
                tables = json.load(stream)
            if index < 0 or index >= len(tables):
                raise HTTPException(404, "表がありません。")
            return Table(**tables[index])
        except (OSError, ValueError, TypeError) as exc:
            raise HTTPException(409, "解析データが破損または欠落しています。原本から再登録してください。") from exc

    @app.get("/api/records")
    def list_records(project_id: uuid.UUID | None = None, unlinked: bool = False,
                     include_deleted: bool = False, search: str = Query("", max_length=255),
                     sort: Literal["started_at", "ended_at", "created_at", "name", "size_bytes"] = "started_at",
                     descending: bool = True, offset: int = Query(0, ge=0),
                     limit: int = Query(50, ge=1, le=200), session: Session = Depends(get_session)):
        statement = select(RecordFile)
        if not include_deleted:
            statement = statement.where(RecordFile.deleted_at.is_(None))
        if project_id:
            statement = statement.where(RecordFile.project_id == project_id)
        if unlinked:
            statement = statement.where(RecordFile.project_id.is_(None))
        if search:
            statement = statement.where(RecordFile.name.icontains(search, autoescape=True) | RecordFile.filename.icontains(search, autoescape=True) | RecordFile.note.icontains(search, autoescape=True))
        total = session.scalar(select(func.count()).select_from(statement.subquery()))
        column = getattr(RecordFile, sort)
        order = column.desc() if descending else column.asc()
        items = session.scalars(statement.order_by(column.is_(None), order, RecordFile.id).offset(offset).limit(limit)).all()
        ids = {x.project_id for x in items if x.project_id}
        projects = {p.id: p for p in session.scalars(select(Project).where(Project.id.in_(ids)))} if ids else {}
        return {"items": [serialize(x, projects.get(x.project_id)) for x in items], "total": total}

    @app.post("/api/records/import", status_code=201)
    def import_record(record: UploadFile = File(), project_id: uuid.UUID | None = Form(None),
                      session: Session = Depends(get_session)):
        filename = record.filename or ""
        if not filename.lower().endswith(".grcd") or len(filename) > 255 or any(c in filename for c in ("/", "\\", "\x00", "\r", "\n")):
            raise HTTPException(422, "パスを含まない.grcdファイル名を指定してください。")
        chosen = project(session, project_id)
        candidates = []
        if chosen is None:
            candidates = [p for p in session.scalars(select(Project).where(Project.deleted_at.is_(None)))
                          if normalized_stem(p.project_name + ".gprj") == normalized_stem(filename)]
            if len(candidates) == 1:
                chosen = candidates[0]
        path = receive(record, min(settings.max_upload_bytes, 256 * 1024 * 1024))
        try:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            existing = session.scalar(select(RecordFile).where(RecordFile.sha256 == digest))
            if existing:
                return {"record": serialize(existing, session.get(Project, existing.project_id) if existing.project_id else None), "duplicate": True, "association_candidates": []}
            inspection = inspect_record(path)
            start, end = bounds(inspection.tables)
            item = RecordFile(filename=filename, name=Path(filename).stem,
                              project_id=chosen.id if chosen else None, sha256=digest,
                              size_bytes=path.stat().st_size, original_key=save_file(path, "grcd"),
                              data_key=save_tables(inspection), inspection=inspection.summary(),
                              started_at=start, ended_at=end, time_source="table" if start else "unknown")
            session.add(item)
            commit(session)
            return {"record": serialize(item, chosen), "duplicate": False,
                    "association_candidates": [{"id": str(p.id), "name": p.display_name} for p in candidates] if len(candidates) > 1 else []}
        finally:
            path.unlink(missing_ok=True)

    @app.get("/api/records/{record_id}")
    def detail(record_id: uuid.UUID, session: Session = Depends(get_session)):
        item = load(session, record_id)
        return serialize(item, session.get(Project, item.project_id) if item.project_id else None)

    @app.patch("/api/records/{record_id}")
    def update(record_id: uuid.UUID, update: RecordUpdate, session: Session = Depends(get_session)):
        item = load(session, record_id, True)
        if item.revision != update.revision:
            raise HTTPException(409, "別の操作で更新されています。一覧を更新してください。")
        fields = update.model_fields_set - {"revision"}
        if not fields:
            raise HTTPException(422, "変更項目がありません。")
        if "project_id" in fields:
            project(session, update.project_id)
        start = update.started_at if "started_at" in fields else utc(item.started_at)
        end = update.ended_at if "ended_at" in fields else utc(item.ended_at)
        if start and end and start > end:
            raise HTTPException(422, "終了日時は開始日時以降にしてください。")
        for key in fields:
            value = getattr(update, key)
            if key == "name" and value is None:
                raise HTTPException(422, "名前は空欄にできません。")
            setattr(item, key, value)
        if fields & {"started_at", "ended_at"}:
            item.time_source = "manual"
        commit(session)
        return serialize(item, session.get(Project, item.project_id) if item.project_id else None)

    @app.post("/api/records/{record_id}/companion-csv")
    def companion(record_id: uuid.UUID, data: UploadFile = File(), revision: int = Form(),
                  encoding: Literal["utf-8-sig", "cp932"] = Form("utf-8-sig"),
                  time_column: str | None = Form(None), zone: str | None = Form(None),
                  session: Session = Depends(get_session)):
        item = load(session, record_id, True)
        if revision != item.revision:
            raise HTTPException(409, "別の操作で更新されています。")
        path = receive(data, min(MAX_BYTES, settings.max_upload_bytes))
        try:
            try:
                table = read_csv(path.read_bytes(), "関連付けCSV", encoding, time_column, zone)
            except DataError as exc:
                raise HTTPException(422, str(exc)) from exc
            inspection = Inspection("companion-csv", "ready", tables=[table], warnings=["表示データは関連付けCSVです。GRCDのバイナリを直接変換した結果ではありません。"])
            item.csv_key = save_file(path, "csv")
            item.data_key = save_tables(inspection)
            item.inspection = inspection.summary()
            item.started_at, item.ended_at = bounds(inspection.tables)
            item.time_source = "companion-csv" if item.started_at else "unknown"
            commit(session)
            return serialize(item, session.get(Project, item.project_id) if item.project_id else None)
        finally:
            path.unlink(missing_ok=True)

    def download(key: str, filename: str, media_type: str):
        try:
            with storage.open(key):
                pass
        except OSError as exc:
            raise HTTPException(409, "保存ファイルが見つかりません。") from exc
        def chunks():
            with storage.open(key) as stream:
                while chunk := stream.read(1024 * 1024):
                    yield chunk
        return StreamingResponse(chunks(), media_type=media_type,
                                 headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe="")})

    @app.get("/api/records/{record_id}/original")
    def original(record_id: uuid.UUID, session: Session = Depends(get_session)):
        item = load(session, record_id)
        return download(item.original_key, item.filename, "application/octet-stream")

    @app.get("/api/records/{record_id}/companion-csv/original")
    def original_csv(record_id: uuid.UUID, session: Session = Depends(get_session)):
        item = load(session, record_id)
        if not item.csv_key:
            raise HTTPException(404, "関連付けCSVがありません。")
        return download(item.csv_key, item.name + ".csv", "text/csv")

    def query_rows(item, table_index, search, column, descending, after, before):
        table = table_for(item, table_index)
        for value in (after, before):
            if value and value.tzinfo is None:
                raise HTTPException(422, "日時にはタイムゾーンが必要です。")
        if after and before and after > before:
            raise HTTPException(422, "終了日時は開始日時以降にしてください。")
        try:
            return table, select_rows(table, search, column, descending, after, before)
        except DataError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/records/{record_id}/tables/{table_index}/rows")
    def rows(record_id: uuid.UUID, table_index: int, search: str = Query("", max_length=255),
             column: int | None = None, descending: bool = False,
             after: datetime | None = None, before: datetime | None = None,
             offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
             session: Session = Depends(get_session)):
        table, indices = query_rows(load(session, record_id), table_index, search, column, descending, after, before)
        return {"columns": table.columns, "rows": [table.rows[i] for i in indices[offset:offset + limit]], "total": len(indices), "offset": offset}

    @app.get("/api/records/{record_id}/tables/{table_index}/csv")
    def export(record_id: uuid.UUID, table_index: int, search: str = Query("", max_length=255),
               column: int | None = None, descending: bool = False,
               after: datetime | None = None, before: datetime | None = None,
               session: Session = Depends(get_session)):
        table, indices = query_rows(load(session, record_id), table_index, search, column, descending, after, before)
        return StreamingResponse(csv_chunks(table, indices), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{record_id}-{table_index}.csv"'})

    @app.delete("/api/records/{record_id}")
    def remove(record_id: uuid.UUID, revision: int = Query(ge=1), session: Session = Depends(get_session)):
        item = load(session, record_id)
        if item.revision != revision:
            raise HTTPException(409, "別の操作で更新されています。")
        if not item.deleted_at:
            item.deleted_at = datetime.now(timezone.utc)
            commit(session)
        return {"id": str(item.id), "deleted": True}

    @app.post("/api/records/{record_id}/restore")
    def restore(record_id: uuid.UUID, revision: int = Query(ge=1), session: Session = Depends(get_session)):
        item = load(session, record_id)
        if item.revision != revision:
            raise HTTPException(409, "別の操作で更新されています。")
        if item.deleted_at:
            item.deleted_at = None
            commit(session)
        return serialize(item, session.get(Project, item.project_id) if item.project_id else None)
