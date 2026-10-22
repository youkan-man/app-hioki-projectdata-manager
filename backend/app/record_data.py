"""Bounded, read-only inspection. This is NOT an undocumented HIOKI binary decoder.

Only self-describing JSON tables, ordinary SQLite tables and CSV members of ZIP
containers are interpreted. Unknown bytes are preserved, never guessed as samples.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
import sqlite3
import stat
import tempfile
import time
import unicodedata
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

MAX_BYTES = 32 * 1024 * 1024
MAX_ROWS = 100_000
MAX_COLUMNS = 256
MAX_CELLS = 2_000_000
MAX_TABLES = 64
MAX_CELL_BYTES = 64 * 1024


class DataError(ValueError):
    pass


@dataclass
class Table:
    name: str
    columns: list[str]
    rows: list[list[str]]
    time_column: str | None = None
    times: list[str] | None = None


@dataclass
class Inspection:
    format: str
    status: str
    message: str = ""
    tables: list[Table] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        result = asdict(self)
        result["tables"] = [
            {"index": i, "name": t.name, "columns": t.columns,
             "row_count": len(t.rows), "time_column": t.time_column}
            for i, t in enumerate(self.tables)
        ]
        return result


def normalized_stem(filename: str) -> str:
    return unicodedata.normalize("NFC", Path(filename).stem).casefold()


def instant(value: str, zone: str | None = None) -> datetime:
    try:
        # Never infer epoch units, Excel serial dates, or locale-dependent dates.
        if not re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value):
            raise ValueError("ISO date-time required")
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            if not zone:
                raise ValueError("timezone required")
            tz = ZoneInfo(zone)
            first, second = parsed.replace(tzinfo=tz, fold=0), parsed.replace(tzinfo=tz, fold=1)
            if first.utcoffset() != second.utcoffset():
                raise ValueError("ambiguous or nonexistent local time")
            parsed = first
        return parsed.astimezone(timezone.utc)
    except (ValueError, KeyError, OverflowError) as exc:
        raise DataError("日時はタイムゾーン付きISO形式で指定してください。曖昧な現地時刻は使用できません。") from exc


def cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        result = "hex:" + value.hex()
    elif isinstance(value, (dict, list)):
        result = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    elif isinstance(value, bool):
        result = "true" if value else "false"
    else:
        if isinstance(value, float) and not math.isfinite(value):
            raise DataError("非有限の数値は解析できません。")
        result = str(value)
    if len(result.encode("utf-8")) > MAX_CELL_BYTES:
        raise DataError("セルが64 KiBを超えています。")
    return result


def validate_table(table: Table) -> Table:
    if not table.columns or len(table.columns) > MAX_COLUMNS:
        raise DataError("列数は1〜256列にしてください。")
    if len(set(table.columns)) != len(table.columns) or any(not x.strip() for x in table.columns):
        raise DataError("列名は空欄・重複にできません。")
    if len(table.rows) > MAX_ROWS or len(table.rows) * len(table.columns) > MAX_CELLS:
        raise DataError("解析上限（10万行・200万セル）を超えています。")
    if any(len(row) != len(table.columns) for row in table.rows):
        raise DataError("列数が一致しない行があります。")
    if table.time_column is None:
        for name in ("timestamp", "datetime", "time", "日時", "記録日時"):
            if name in table.columns and table.rows:
                try:
                    attach_times(table, name, None)
                except DataError:
                    pass
                break
    return table


def attach_times(table: Table, column: str, zone: str | None) -> None:
    if column not in table.columns:
        raise DataError("指定した日時列がありません。")
    index = table.columns.index(column)
    parsed = [instant(row[index], zone).isoformat() for row in table.rows]
    table.time_column, table.times = column, parsed


def read_csv(data: bytes, name: str = "CSV", encoding: str = "utf-8-sig",
             time_column: str | None = None, zone: str | None = None) -> Table:
    if len(data) > MAX_BYTES:
        raise DataError("CSV解析上限は32 MiBです。")
    if encoding not in ("utf-8-sig", "cp932"):
        raise DataError("未対応の文字コードです。")
    try:
        text = data.decode(encoding)
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        headers = next(reader, None)
        if headers is None:
            raise DataError("CSVが空です。")
        headers = [cell(x) for x in headers]
        rows: list[list[str]] = []
        if len(headers) > MAX_COLUMNS:
            raise DataError("列数の上限は256列です。")
        for row in reader:
            if len(rows) >= MAX_ROWS or (len(rows) + 1) * len(headers) > MAX_CELLS:
                raise DataError("CSVの行数またはセル数が上限を超えています。")
            rows.append([cell(x) for x in row])
        table = validate_table(Table(name, headers, rows))
        if time_column:
            attach_times(table, time_column, zone)
        return table
    except (UnicodeError, csv.Error) as exc:
        raise DataError("CSVを読み取れません。文字コードと区切り（カンマ）を確認してください。") from exc


def _json_tables(data: bytes) -> list[Table]:
    def invalid_constant(_: str):
        raise DataError("JSONに非有限の数値があります。")
    obj = json.loads(data.decode("utf-8-sig"), parse_constant=invalid_constant)
    groups = [("records", obj)] if isinstance(obj, list) else list(obj.items()) if isinstance(obj, dict) else []
    tables: list[Table] = []
    for name, rows in groups:
        if not isinstance(rows, list) or not rows:
            continue
        if not all(isinstance(r, dict) for r in rows):
            continue
        if len(rows) > MAX_ROWS:
            raise DataError("JSONの行数が上限を超えています。")
        columns = list(dict.fromkeys(k for row in rows for k in row))
        if len(columns) > MAX_COLUMNS:
            raise DataError("JSONの列数が上限を超えています。")
        tables.append(validate_table(Table(str(name), columns, [[cell(r.get(c)) for c in columns] for r in rows])))
        if len(tables) > MAX_TABLES:
            raise DataError("テーブル数が上限を超えています。")
    return tables


def _sqlite_tables(data: bytes) -> list[Table]:
    # Temporary private file; no user-supplied filename, SQL, extension or URI.
    with tempfile.TemporaryDirectory(prefix="grcd-sqlite-") as directory:
        path = Path(directory) / "input.sqlite"
        path.write_bytes(data)
        connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
        try:
            connection.enable_load_extension(False)
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            deadline = time.monotonic() + 5
            connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_BYTES)
            connection.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, MAX_COLUMNS)
            entries = connection.execute("SELECT name, sql FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchmany(MAX_TABLES + 1)
            if len(entries) > MAX_TABLES:
                raise DataError("SQLiteのテーブル数が上限を超えています。")
            tables: list[Table] = []
            for name, definition in entries:
                if not definition or re.search(r"CREATE\s+VIRTUAL\s+TABLE", definition, re.IGNORECASE):
                    raise DataError("仮想テーブルは読み取り対象にできません。")
                quoted = '"' + name.replace('"', '""') + '"'
                cursor = connection.execute("SELECT * FROM " + quoted + " LIMIT ?", (MAX_ROWS + 1,))
                columns = [item[0] for item in cursor.description]
                rows: list[list[str]] = []
                for row in cursor:
                    if len(rows) >= MAX_ROWS or (len(rows) + 1) * len(columns) > MAX_CELLS:
                        raise DataError("SQLiteの行数またはセル数が上限を超えています。")
                    rows.append([cell(x) for x in row])
                tables.append(validate_table(Table(name, columns, rows)))
            return tables
        finally:
            connection.close()


def inspect_record(path: Path) -> Inspection:
    if path.stat().st_size > MAX_BYTES:
        return Inspection("binary", "unavailable", "原本は保存済みです。32 MiBを超えるファイルの内部解析には未対応です。")
    data = path.read_bytes()
    kind = "binary"
    try:
        if data.startswith(b"SQLite format 3\x00"):
            kind, tables = "sqlite", _sqlite_tables(data)
        elif data.lstrip(b"\xef\xbb\xbf \r\n\t").startswith((b"{", b"[")):
            kind, tables = "json", _json_tables(data)
        elif zipfile.is_zipfile(io.BytesIO(data)):
            kind, tables = "zip", []
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > 256 or sum(e.file_size for e in entries) > MAX_BYTES:
                    raise DataError("ZIPの展開サイズまたはファイル数が上限を超えています。")
                names: set[str] = set()
                for entry in entries:
                    p = PurePosixPath(entry.filename)
                    if p.is_absolute() or ".." in p.parts or "\\" in entry.filename or ":" in entry.filename or stat.S_ISLNK(entry.external_attr >> 16):
                        raise DataError("ZIPに安全でないパスが含まれています。")
                    if entry.filename in names or entry.flag_bits & 1:
                        raise DataError("ZIPの重複名・暗号化エントリーには未対応です。")
                    names.add(entry.filename)
                    if entry.is_dir():
                        continue
                    if entry.file_size > max(1, entry.compress_size) * 250:
                        raise DataError("ZIPの圧縮率が上限を超えています。")
                    if p.suffix.lower() == ".csv":
                        tables.append(read_csv(archive.read(entry), entry.filename))
                    elif p.suffix.lower() == ".json":
                        for table in _json_tables(archive.read(entry)):
                            table.name = entry.filename + ":" + table.name
                            tables.append(table)
            if len(tables) > MAX_TABLES:
                raise DataError("テーブル数が上限を超えています。")
        else:
            return Inspection(kind, "unavailable", "このGRCDのバイナリ形式は未対応です。原本は保存されています。GENNECTから出力したCSVを関連付けると閲覧できます。")
        if sum(len(t.rows) * len(t.columns) for t in tables) > MAX_CELLS:
            raise DataError("全テーブルのセル数が上限を超えています。")
        if not tables:
            return Inspection(kind, "unavailable", "読み取り可能な表データがありません。原本は保存されています。")
        warnings = ["自己記述された表のみを表示しています。HIOKI独自バイナリの数値・単位変換は行っていません。"]
        if kind == "zip":
            warnings.append("ZIP内のJSON/CSV表のみが対象です。その他のファイルは原本に保持されています。")
        return Inspection(kind, "ready", tables=tables, warnings=warnings)
    except (DataError, ValueError, UnicodeError, sqlite3.Error, zipfile.BadZipFile, RuntimeError, RecursionError, OverflowError) as exc:
        return Inspection(kind, "unavailable", "内部解析に失敗しました。原本は保存済みです: " + str(exc)[:300])


def bounds(tables: list[Table]) -> tuple[datetime | None, datetime | None]:
    times = [v for table in tables for v in (table.times or [])]
    return (instant(min(times)), instant(max(times))) if times else (None, None)


def select_rows(table: Table, search: str = "", column: int | None = None,
                descending: bool = False, after: datetime | None = None,
                before: datetime | None = None) -> list[int]:
    if (after or before) and table.times is None:
        raise DataError("期間の絞り込みには日時列が必要です。")
    needle = search.casefold()
    indices = [i for i, row in enumerate(table.rows)
               if (not needle or any(needle in c.casefold() for c in row))
               and (after is None or instant(table.times[i]) >= after)
               and (before is None or instant(table.times[i]) <= before)]
    if column is not None:
        if column < 0 or column >= len(table.columns):
            raise DataError("並べ替え列が範囲外です。")
        values = {i: table.rows[i][column] for i in indices}
        present = [i for i in indices if values[i] != ""]
        missing = [i for i in indices if values[i] == ""]
        try:
            numbers = {i: Decimal(values[i]) for i in present}
            if not all(n.is_finite() for n in numbers.values()):
                raise InvalidOperation
            present.sort(key=lambda i: numbers[i], reverse=descending)
        except InvalidOperation:
            if table.time_column == table.columns[column] and table.times:
                present.sort(key=lambda i: table.times[i], reverse=descending)
            else:
                present.sort(key=lambda i: values[i].casefold(), reverse=descending)
        indices = present + missing
    return indices


def safe_csv_cell(value: str) -> str:
    stripped = value.lstrip()
    if value.startswith(("\t", "\r", "\n")) or stripped.startswith(("=", "+", "-", "@")):
        try:
            number = Decimal(value)
            if number.is_finite() and re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value):
                return value
        except InvalidOperation:
            pass
        return "'" + value
    return value


def csv_chunks(table: Table, indices: list[int]):
    yield "\ufeff".encode("utf-8")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    for row in [table.columns]:
        writer.writerow([safe_csv_cell(c) for c in row])
        yield output.getvalue().encode("utf-8")
        output.seek(0); output.truncate(0)
    for index in indices:
        writer.writerow([safe_csv_cell(c) for c in table.rows[index]])
        yield output.getvalue().encode("utf-8")
        output.seek(0); output.truncate(0)
