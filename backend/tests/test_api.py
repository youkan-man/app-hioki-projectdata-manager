from __future__ import annotations

import io
import stat
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_zip(
    source_uuid: uuid.UUID,
    name: str = "Factory Inspection",
    extra: dict[str, bytes] | None = None,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{source_uuid}/{name}.gprj", b"gennect-project")
        for path, content in (extra or {}).items():
            archive.writestr(path, content)
    return output.getvalue()


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(
        Settings(
            database_url="sqlite://",
            archive_root=tmp_path / "archives",
            max_upload_bytes=10 * 1024 * 1024,
            max_archive_entries=5,
            max_uncompressed_bytes=20 * 1024 * 1024,
        )
    )
    with TestClient(app) as test_client:
        yield test_client, tmp_path


def import_project(client: TestClient, source_uuid: uuid.UUID, name: str = "Demo"):
    return client.post(
        "/api/projects/import",
        files={"archive": ("project.zip", make_zip(source_uuid, name), "application/zip")},
    )


def test_import_versions_download_and_soft_delete(client):
    test_client, tmp_path = client
    source_uuid = uuid.uuid4()
    first = import_project(test_client, source_uuid)
    assert first.status_code == 201, first.text
    assert first.json()["project_name"] == "Demo"
    assert first.json()["display_name"] == "Demo"
    assert first.json()["versions"][0]["version_number"] == 1

    second = import_project(test_client, source_uuid)
    assert second.status_code == 201, second.text
    versions = second.json()["versions"]
    assert [item["version_number"] for item in versions] == [2, 1]
    assert len(list((tmp_path / "archives").rglob("*.zip"))) == 2

    renamed = test_client.patch(
        f"/api/projects/{second.json()['id']}",
        json={"name": "Production label", "description": "Shared metadata"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["project_name"] == "Demo"
    assert renamed.json()["display_name"] == "Production label"

    project_id = second.json()["id"]
    version_id = versions[0]["id"]
    downloaded = test_client.get(
        f"/api/projects/{project_id}/versions/{version_id}/archive"
    )
    assert downloaded.status_code == 200
    assert downloaded.content == make_zip(source_uuid, "Demo")

    deleted = test_client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted_at"] is not None
    assert test_client.get("/api/projects").json()["total"] == 0
    assert test_client.get("/api/projects?include_deleted=true").json()["total"] == 1
    assert len(list((tmp_path / "archives").rglob("*.zip"))) == 2

    blocked = import_project(test_client, source_uuid)
    assert blocked.status_code == 409
    assert test_client.post(f"/api/projects/{project_id}/restore").status_code == 200


def test_archive_metadata_must_match(client):
    test_client, _ = client
    source_uuid = uuid.uuid4()
    response = test_client.post(
        "/api/projects/import",
        data={"source_uuid": str(uuid.uuid4()), "project_name": "Wrong"},
        files={"archive": ("project.zip", make_zip(source_uuid), "application/zip")},
    )
    assert response.status_code == 422
    assert test_client.get("/api/projects").json()["total"] == 0


@pytest.mark.parametrize(
    "builder,detail",
    [
        (
            lambda source_uuid: make_zip(
                source_uuid, extra={"../escape.txt": b"unsafe"}
            ),
            "unsafe path",
        ),
        (
            lambda source_uuid: make_zip(
                source_uuid, extra={f"{source_uuid}/second.gprj": b"duplicate"}
            ),
            "exactly one direct .gprj",
        ),
    ],
)
def test_rejects_unsafe_or_ambiguous_zip(client, builder, detail):
    test_client, _ = client
    response = test_client.post(
        "/api/projects/import",
        files={
            "archive": (
                "project.zip",
                builder(uuid.uuid4()),
                "application/zip",
            )
        },
    )
    assert response.status_code == 400
    assert detail in response.json()["detail"]


def test_rejects_symlink_zip_bomb_and_excess_entries(client):
    test_client, _ = client
    source_uuid = uuid.uuid4()

    symlink = io.BytesIO()
    with zipfile.ZipFile(symlink, "w") as archive:
        archive.writestr(f"{source_uuid}/Demo.gprj", b"project")
        link = zipfile.ZipInfo(f"{source_uuid}/shortcut")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "target")
    symlink_response = test_client.post(
        "/api/projects/import",
        files={"archive": ("symlink.zip", symlink.getvalue(), "application/zip")},
    )
    assert symlink_response.status_code == 400
    assert "symbolic links" in symlink_response.json()["detail"]

    bomb_response = test_client.post(
        "/api/projects/import",
        files={
            "archive": (
                "bomb.zip",
                make_zip(source_uuid, extra={f"{source_uuid}/zeros.bin": b"0" * 1_000_000}),
                "application/zip",
            )
        },
    )
    assert bomb_response.status_code == 400
    assert "compression ratio" in bomb_response.json()["detail"]

    too_many = {
        f"{source_uuid}/data-{number}.bin": b"x" for number in range(5)
    }
    entry_response = test_client.post(
        "/api/projects/import",
        files={
            "archive": (
                "many.zip",
                make_zip(source_uuid, extra=too_many),
                "application/zip",
            )
        },
    )
    assert entry_response.status_code == 400
    assert "too many entries" in entry_response.json()["detail"]


def test_rebuilds_database_index_from_archives(client):
    test_client, _ = client
    source_uuid = uuid.uuid4()
    imported = import_project(test_client, source_uuid)
    assert imported.status_code == 201
    app = test_client.app
    with app.state.session_factory.begin() as session:
        from app.models import Project, ProjectVersion

        session.query(ProjectVersion).delete()
        session.query(Project).delete()

    rebuilt = test_client.post("/api/admin/rebuild-index")
    assert rebuilt.status_code == 200, rebuilt.text
    assert rebuilt.json()["projects_created"] == 1
    assert rebuilt.json()["versions_created"] == 1
    listed = test_client.get("/api/projects").json()
    assert listed["total"] == 1
    assert listed["items"][0]["source_uuid"] == str(source_uuid)
