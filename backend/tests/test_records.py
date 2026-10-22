"""Synthetic container/CSV fixtures verify our contracts, NOT HIOKI native compatibility."""
import io
import json
import sqlite3
import uuid
import zipfile
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.models import Project
from app.record_data import DataError, Table, csv_chunks, instant, inspect_record, read_csv, safe_csv_cell, select_rows


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(database_url="sqlite+pysqlite:///:memory:", archive_root=tmp_path / "archives", max_upload_bytes=2 * 1024 * 1024))
    with TestClient(app) as c:
        yield c


def add_project(client, name="測定A"):
    with client.app.state.session_factory.begin() as session:
        item = Project(source_uuid=uuid.uuid4(), project_name=name, display_name=name)
        session.add(item); session.flush()
        return str(item.id)


def upload(client, name="測定A.grcd", data=b"unrecognized-native-bytes", project_id=None):
    return client.post("/api/records/import", files={"record": (name, data, "application/octet-stream")}, data={"project_id": project_id} if project_id else {})


def test_opaque_preserved_and_matched(client):
    pid = add_project(client)
    content = b"\x00\xffPRIVATE-NATIVE-FORMAT"
    response = upload(client, data=content)
    assert response.status_code == 201
    item = response.json()["record"]
    assert item["project_id"] == pid
    assert item["inspection"]["status"] == "unavailable"
    assert item["started_at"] is None
    assert client.get(f"/api/records/{item['id']}/original").content == content
    assert client.get(f"/api/records/{item['id']}/tables/0/csv").status_code == 422
    assert upload(client, data=content).json()["duplicate"] is True
    assert client.get("/api/records").json()["total"] == 1


def test_ambiguous_project_requires_choice(client):
    one, two = add_project(client), add_project(client)
    result = upload(client).json()
    assert result["record"]["project_id"] is None
    assert {p["id"] for p in result["association_candidates"]} == {one, two}
    item = result["record"]
    response = client.patch(f"/api/records/{item['id']}", json={"revision": item["revision"], "project_id": two})
    assert response.status_code == 200 and response.json()["project_id"] == two


def test_unicode_and_case_insensitive_filename(client):
    pid = add_project(client, "café")
    item = upload(client, name="CAFE\u0301.GRCD").json()["record"]
    assert item["project_id"] == pid


def test_project_delete_keeps_record_and_original(client):
    pid = add_project(client)
    item = upload(client).json()["record"]
    assert client.delete(f"/api/projects/{pid}").status_code == 200
    result = client.get(f"/api/records/{item['id']}").json()
    assert result["project_deleted"] is True
    assert client.get(f"/api/records/{item['id']}/original").status_code == 200


def test_companion_csv_dates_query_export_and_original(client):
    item = upload(client).json()["record"]
    data = 'timestamp,温度 [°C],メモ\r\n2026-10-22T10:00:00+09:00,23.000000001,通常\r\n2026-10-22T10:01:00+09:00,-2.5,=1+1\r\n'.encode('utf-8-sig')
    response = client.post(f"/api/records/{item['id']}/companion-csv", files={"data": ("data.csv", data)}, data={"revision": item["revision"], "time_column": "timestamp"})
    assert response.status_code == 200
    updated = response.json()
    assert updated["started_at"].startswith("2026-10-22T01:00:00")
    assert updated["duration_seconds"] == 60
    assert updated["time_source"] == "companion-csv"
    rows = client.get(f"/api/records/{item['id']}/tables/0/rows?column=1").json()
    assert rows["rows"][0][1] == "-2.5"
    out = client.get(f"/api/records/{item['id']}/tables/0/csv?column=1")
    assert out.content.startswith(b"\xef\xbb\xbf")
    assert "'=1+1" in out.text and "23.000000001" in out.text
    assert client.get(f"/api/records/{item['id']}/companion-csv/original").content == data
    assert client.get(f"/api/records/{item['id']}/original").content == b"unrecognized-native-bytes"
    filtered = client.get(f"/api/records/{item['id']}/tables/0/rows", params={"after": "2026-10-22T01:00:30Z"}).json()
    assert filtered["total"] == 1 and filtered["rows"][0][1] == "-2.5"


def test_naive_csv_timezone_requires_explicit_choice(client):
    item = upload(client).json()["record"]
    args = {"files": {"data": ("data.csv", b"timestamp,value\n2026-10-22 10:00:00,42\n")}, "data": {"revision": item["revision"], "time_column": "timestamp"}}
    assert client.post(f"/api/records/{item['id']}/companion-csv", **args).status_code == 422
    args["data"]["zone"] = "Asia/Tokyo"
    result = client.post(f"/api/records/{item['id']}/companion-csv", **args)
    assert result.status_code == 200
    assert result.json()["started_at"].startswith("2026-10-22T01:00:00")


def test_companion_failure_keeps_existing_data(client):
    item = upload(client).json()["record"]
    bad = client.post(f"/api/records/{item['id']}/companion-csv", files={"data": ("data.csv", b"a,b\n1,2,3\n")}, data={"revision": item["revision"]})
    assert bad.status_code == 422
    result = client.get(f"/api/records/{item['id']}").json()
    assert result["revision"] == item["revision"] and not result["has_companion_csv"]


def test_metadata_conflict_delete_restore(client):
    item = upload(client).json()["record"]
    path = f"/api/records/{item['id']}"
    edited = client.patch(path, json={"revision": item["revision"], "name": "変更", "note": "note"})
    assert edited.status_code == 200
    assert client.patch(path, json={"revision": item["revision"], "name": "stale"}).status_code == 409
    item = edited.json()
    assert client.delete(path, params={"revision": item["revision"]}).status_code == 200
    assert client.get("/api/records").json()["total"] == 0
    deleted = client.get(path).json()
    assert client.get("/api/records?include_deleted=true").json()["total"] == 1
    assert client.patch(path, json={"revision": deleted["revision"], "name": "no"}).status_code == 409
    assert client.post(path + "/restore", params={"revision": deleted["revision"]}).status_code == 200
    assert client.get("/api/records").json()["total"] == 1


def test_manual_dates_utc_and_invalid_interval(client):
    item = upload(client).json()["record"]
    path = f"/api/records/{item['id']}"
    update = {"revision": item["revision"], "started_at": "2026-10-22T10:00:00+09:00", "ended_at": "2026-10-22T10:10:00+09:00"}
    result = client.patch(path, json=update)
    assert result.status_code == 200
    current = client.get(path).json()
    assert current["started_at"].startswith("2026-10-22T01:00:00")
    assert current["duration_seconds"] == 600
    assert client.patch(path, json={"revision": current["revision"], "ended_at": "2020-01-01T00:00:00Z"}).status_code == 422
    assert client.patch(path, json={"revision": current["revision"], "started_at": "2026-10-22T10:00:00"}).status_code == 422


def test_sorting_unknown_last_pagination_and_search_literal(client):
    unknown = upload(client, "unknown.grcd", b"unknown").json()["record"]
    for name, start in (("late%", "2026-10-23T00:00:00Z"), ("early", "2026-10-21T00:00:00Z")):
        item = upload(client, name + ".grcd", name.encode()).json()["record"]
        assert client.patch(f"/api/records/{item['id']}", json={"revision": item["revision"], "started_at": start}).status_code == 200
    for descending, expected in (("true", ["late%", "early", "unknown"]), ("false", ["early", "late%", "unknown"])):
        result = client.get("/api/records", params={"descending": descending}).json()
        assert [i["name"] for i in result["items"]] == expected
    assert client.get("/api/records?search=%25").json()["total"] == 1
    assert client.get("/api/records?offset=2&limit=1").json()["items"][0]["id"] == unknown["id"]
    assert client.get("/api/records?sort=sha256").status_code == 422


@pytest.mark.parametrize("filename,data,status", [("x.txt", b"x", 422), ("../x.grcd", b"x", 422), ("x.grcd", b"", 400), ("x.grcd", b"x" * (2 * 1024 * 1024 + 1), 413)])
def test_upload_validation(client, filename, data, status):
    assert upload(client, filename, data).status_code == status


def test_json_container_tables_preserve_large_integer(client):
    data = json.dumps({"readings": [{"timestamp": "2026-10-22T00:00:00Z", "value": 9007199254740993}]}).encode()
    item = upload(client, data=data).json()["record"]
    assert item["inspection"]["format"] == "json" and item["inspection"]["status"] == "ready"
    rows = client.get(f"/api/records/{item['id']}/tables/0/rows").json()
    assert rows["rows"][0][1] == "9007199254740993"


def test_sqlite_readonly_container(tmp_path):
    path = tmp_path / "record.grcd"
    with sqlite3.connect(path) as db:
        db.execute('create table "r" (timestamp TEXT, value REAL, raw BLOB)')
        db.execute('insert into r values (?, ?, ?)', ('2026-10-22T00:00:00Z', -2.75, b'\x00\xff'))
    original = path.read_bytes()
    result = inspect_record(path)
    assert result.status == "ready" and result.tables[0].rows[0][1:] == ["-2.75", "hex:00ff"]
    assert path.read_bytes() == original


def test_zip_path_validation_and_tables(tmp_path):
    path = tmp_path / 'record.grcd'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('readings.csv', 'time,value\n2026-10-22T00:00:00Z,1\n')
    assert inspect_record(path).status == 'ready'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('../escape.csv', 'x\n1\n')
    assert inspect_record(path).status == 'unavailable'
    assert not (tmp_path.parent / 'escape.csv').exists()


@pytest.mark.parametrize('text', ['timestamp,x\n2026-11-01T01:30:00,1\n', 'timestamp,x\n2026-03-08T02:30:00,1\n'])
def test_dst_ambiguous_or_nonexistent_rejected(text):
    with pytest.raises(DataError):
        read_csv(text.encode(), time_column='timestamp', zone='America/New_York')


@pytest.mark.parametrize('value', ['=WEBSERVICE("x")', ' +CMD', '-1+2', '@SUM(A1)', '\t=1+1', '\n=1'])
def test_csv_injection_defense(value):
    assert safe_csv_cell(value).startswith("'")


@pytest.mark.parametrize('value', ['-2.5', '0', '1.230000000001', '-1e-12', '+42'])
def test_csv_numeric_precision_preserved(value):
    assert safe_csv_cell(value) == value


def test_cp932_and_duplicate_headers():
    table = read_csv('日時,温度\n2026-10-22T10:00:00,20.1\n'.encode('cp932'), encoding='cp932', time_column='日時', zone='Asia/Tokyo')
    assert table.times == ['2026-10-22T01:00:00+00:00']
    with pytest.raises(DataError):
        read_csv(b'x,x\n1,2\n')


def test_csv_quoting_pagination_and_empty_values():
    table = Table('x', ['a', 'b'], [['2', 'a,b'], ['', 'x'], ['10', 'line\nquote"']])
    assert select_rows(table, column=0, descending=True) == [2, 0, 1]
    output = b''.join(csv_chunks(table, [0, 2])).decode('utf-8-sig')
    assert '"a,b"' in output and '"line\nquote"""' in output
    with pytest.raises(DataError):
        select_rows(table, after=datetime.now(timezone.utc))
