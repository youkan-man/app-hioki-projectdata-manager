from __future__ import annotations

import hashlib
import io
import json
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
        archive.writestr(
            f"{name}.gprj",
            json.dumps({"id": str(source_uuid), "name": name}).encode("utf-8"),
        )
        for path, content in (extra or {}).items():
            archive.writestr(path, content)
    return output.getvalue()


def make_legacy_zip(source_uuid: uuid.UUID, name: str = "Legacy") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"{source_uuid}/{name}.gprj",
            json.dumps({"id": str(source_uuid), "name": name}).encode("utf-8"),
        )
        archive.writestr(f"{source_uuid}/attachments/readme.txt", b"legacy-data")
    return output.getvalue()


def make_configuration_zip(
    name: str,
    project: object,
    layout: object | None = None,
    extra: dict[str, bytes] | None = None,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"{name}.gprj",
            json.dumps(project, ensure_ascii=False).encode("utf-8"),
        )
        if layout is not None:
            archive.writestr(
                "layout.lay",
                json.dumps(layout, ensure_ascii=False).encode("utf-8"),
            )
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
            max_configuration_bytes=1024,
        )
    )
    with TestClient(app) as test_client:
        yield test_client, tmp_path


def import_project(client: TestClient, source_uuid: uuid.UUID, name: str = "Demo"):
    return client.post(
        "/api/projects/import",
        data={"source_uuid": str(source_uuid)},
        files={
            "archive": (f"{source_uuid}.zip", make_zip(source_uuid, name), "application/zip")
        },
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
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert archive.namelist() == ["Demo.gprj"]
        assert json.loads(archive.read("Demo.gprj")) == {
            "id": str(source_uuid),
            "name": "Demo",
        }

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
    assert response.status_code == 400
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
                source_uuid, extra={"second.gprj": b"duplicate"}
            ),
            "exactly one root-level .gprj",
        ),
    ],
)
def test_rejects_unsafe_or_ambiguous_zip(client, builder, detail):
    test_client, _ = client
    source_uuid = uuid.uuid4()
    response = test_client.post(
        "/api/projects/import",
        data={"source_uuid": str(source_uuid)},
        files={
            "archive": (
                "project.zip",
                builder(source_uuid),
                "application/zip",
            )
        },
    )
    assert response.status_code == 400
    assert detail in response.json()["detail"]


def test_uuid_can_be_inferred_and_legacy_wrapper_is_normalized(client):
    test_client, tmp_path = client
    source_uuid = uuid.uuid4()
    inferred = test_client.post(
        "/api/projects/import",
        files={
            "archive": (
                f"{source_uuid}.zip",
                make_zip(source_uuid, "Inferred"),
                "application/zip",
            )
        },
    )
    assert inferred.status_code == 201, inferred.text
    assert inferred.json()["source_uuid"] == str(source_uuid)

    legacy_uuid = uuid.uuid4()
    legacy = test_client.post(
        "/api/projects/import",
        files={
            "archive": (
                "legacy.zip",
                make_legacy_zip(legacy_uuid),
                "application/zip",
            )
        },
    )
    assert legacy.status_code == 201, legacy.text
    stored_path = next(
        (tmp_path / "archives" / str(legacy_uuid)).glob("*.zip")
    )
    with zipfile.ZipFile(stored_path) as archive:
        assert sorted(archive.namelist()) == ["Legacy.gprj", "attachments/readme.txt"]
    version_id = legacy.json()["versions"][0]["id"]
    downloaded = test_client.get(
        f"/api/projects/{legacy.json()['id']}/versions/{version_id}/archive"
    )
    assert downloaded.status_code == 200
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert sorted(archive.namelist()) == ["Legacy.gprj", "attachments/readme.txt"]

    mismatch = test_client.post(
        "/api/projects/import",
        data={"source_uuid": str(uuid.uuid4())},
        files={
            "archive": (
                "legacy.zip",
                make_legacy_zip(legacy_uuid),
                "application/zip",
            )
        },
    )
    assert mismatch.status_code == 422
    assert "does not match" in mismatch.json()["detail"]


def test_rejects_symlink_zip_bomb_and_excess_entries(client):
    test_client, _ = client
    source_uuid = uuid.uuid4()

    symlink = io.BytesIO()
    with zipfile.ZipFile(symlink, "w") as archive:
        archive.writestr("Demo.gprj", b"project")
        link = zipfile.ZipInfo("shortcut")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "target")
    symlink_response = test_client.post(
        "/api/projects/import",
        data={"source_uuid": str(source_uuid)},
        files={"archive": ("symlink.zip", symlink.getvalue(), "application/zip")},
    )
    assert symlink_response.status_code == 400
    assert "symbolic links" in symlink_response.json()["detail"]

    bomb_response = test_client.post(
        "/api/projects/import",
        files={
            "archive": (
                "bomb.zip",
                make_zip(source_uuid, extra={"zeros.bin": b"0" * 1_000_000}),
                "application/zip",
            )
        },
        data={"source_uuid": str(source_uuid)},
    )
    assert bomb_response.status_code == 400
    assert "compression ratio" in bomb_response.json()["detail"]

    too_many = {
        f"data-{number}.bin": b"x" for number in range(5)
    }
    entry_response = test_client.post(
        "/api/projects/import",
        data={"source_uuid": str(source_uuid)},
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


def test_rebuilds_and_downloads_legacy_stored_archive(client):
    test_client, tmp_path = client
    source_uuid = uuid.uuid4()
    legacy_bytes = make_legacy_zip(source_uuid, "Recovered Legacy")
    digest = hashlib.sha256(legacy_bytes).hexdigest()
    archive_path = (
        tmp_path
        / "archives"
        / str(source_uuid)
        / f"00000001-{digest}.zip"
    )
    archive_path.parent.mkdir(parents=True)
    archive_path.write_bytes(legacy_bytes)

    rebuilt = test_client.post("/api/admin/rebuild-index")
    assert rebuilt.status_code == 200, rebuilt.text
    assert rebuilt.json()["projects_created"] == 1
    assert rebuilt.json()["versions_created"] == 1

    project = test_client.get("/api/projects").json()["items"][0]
    downloaded = test_client.get(
        f"/api/projects/{project['id']}/versions/{project['versions'][0]['id']}/archive"
    )
    assert downloaded.status_code == 200
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert sorted(archive.namelist()) == [
            "Recovered Legacy.gprj",
            "attachments/readme.txt",
        ]
        assert all(not name.startswith(f"{source_uuid}/") for name in archive.namelist())


def test_reads_and_edits_project_and_layout_as_one_new_version(client):
    test_client, tmp_path = client
    source_uuid = uuid.uuid4()
    original_project = {
        "id": str(source_uuid),
        "instrument": "MR6000",
        "channels": [1, 2],
    }
    original_layout = {"panels": [{"id": "main", "x": 10}]}
    preserved = {
        "settings/device.set": b"\x00\xff\x01device-settings",
        "layouts/secondary.lay": b"not-the-root-layout",
    }
    original_zip = make_configuration_zip(
        "Editable", original_project, original_layout, preserved
    )
    imported = test_client.post(
        "/api/projects/import",
        data={"source_uuid": str(source_uuid)},
        files={"archive": (f"{source_uuid}.zip", original_zip, "application/zip")},
    )
    assert imported.status_code == 201, imported.text
    project_id = imported.json()["id"]
    version_one_id = imported.json()["versions"][0]["id"]

    current = test_client.get(f"/api/projects/{project_id}/configuration")
    assert current.status_code == 200, current.text
    assert current.json() == {
        "version": 1,
        "project": {"filename": "Editable.gprj", "config": original_project},
        "layout": {"filename": "layout.lay", "config": original_layout},
    }

    edited_project = {
        "id": str(source_uuid),
        "instrument": "MR6000",
        "channels": [2, 4],
        "enabled": True,
    }
    edited_layout = {"panels": [{"id": "main", "x": 42}], "theme": "dark"}
    edited = test_client.put(
        f"/api/projects/{project_id}/configuration",
        json={
            "project": edited_project,
            "layout": edited_layout,
            "note": "edited JSON configuration",
        },
    )
    assert edited.status_code == 200, edited.text
    assert [item["version_number"] for item in edited.json()["versions"]] == [2, 1]
    assert edited.json()["versions"][0]["note"] == "edited JSON configuration"
    assert len(list((tmp_path / "archives" / str(source_uuid)).glob("*.zip"))) == 2

    latest = test_client.get(f"/api/projects/{project_id}/configuration")
    assert latest.json()["version"] == 2
    assert latest.json()["project"]["config"] == edited_project
    assert latest.json()["layout"]["config"] == edited_layout

    old_download = test_client.get(
        f"/api/projects/{project_id}/versions/{version_one_id}/archive"
    )
    assert old_download.content == original_zip
    version_two_id = edited.json()["versions"][0]["id"]
    new_download = test_client.get(
        f"/api/projects/{project_id}/versions/{version_two_id}/archive"
    )
    with zipfile.ZipFile(io.BytesIO(new_download.content)) as archive:
        assert json.loads(archive.read("Editable.gprj")) == edited_project
        assert json.loads(archive.read("layout.lay")) == edited_layout
        for path, content in preserved.items():
            assert archive.read(path) == content


def test_missing_layout_is_null_and_can_be_created(client):
    test_client, _ = client
    source_uuid = uuid.uuid4()
    imported = test_client.post(
        "/api/projects/import",
        data={"source_uuid": str(source_uuid)},
        files={
            "archive": (
                f"{source_uuid}.zip",
                make_configuration_zip(
                    "NoLayout", {"id": str(source_uuid), "sample": 1}
                ),
                "application/zip",
            )
        },
    )
    project_id = imported.json()["id"]
    assert test_client.get(f"/api/projects/{project_id}/configuration").json()[
        "layout"
    ] is None

    unchanged_missing = test_client.put(
        f"/api/projects/{project_id}/configuration",
        json={"project": {"id": str(source_uuid), "sample": 2}, "layout": None},
    )
    assert unchanged_missing.status_code == 200, unchanged_missing.text
    assert test_client.get(f"/api/projects/{project_id}/configuration").json()[
        "layout"
    ] is None

    created = test_client.put(
        f"/api/projects/{project_id}/configuration",
        json={
            "project": {"id": str(source_uuid), "sample": 3},
            "layout": {"created": True},
        },
    )
    assert created.status_code == 200, created.text
    configuration = test_client.get(
        f"/api/projects/{project_id}/configuration"
    ).json()
    assert configuration["version"] == 3
    assert configuration["layout"] == {
        "filename": "layout.lay",
        "config": {"created": True},
    }


def test_configuration_boundaries_and_deleted_project(client):
    test_client, _ = client
    source_uuid = uuid.uuid4()
    imported = test_client.post(
        "/api/projects/import",
        data={"source_uuid": str(source_uuid)},
        files={
            "archive": (
                f"{source_uuid}.zip",
                make_configuration_zip(
                    "Boundary",
                    {"id": str(source_uuid), "ok": True},
                    {"layout": True},
                ),
                "application/zip",
            )
        },
    )
    project_id = imported.json()["id"]

    non_object = test_client.put(
        f"/api/projects/{project_id}/configuration",
        json={"project": [], "layout": {}},
    )
    assert non_object.status_code == 422
    changed_id = test_client.put(
        f"/api/projects/{project_id}/configuration",
        json={"project": {"id": str(uuid.uuid4())}, "layout": {}},
    )
    assert changed_id.status_code == 422
    missing_existing_layout = test_client.put(
        f"/api/projects/{project_id}/configuration",
        json={"project": {"id": str(source_uuid)}, "layout": None},
    )
    assert missing_existing_layout.status_code == 422
    oversized = test_client.put(
        f"/api/projects/{project_id}/configuration",
        json={
            "project": {"id": str(source_uuid), "data": "x" * 2000},
            "layout": {},
        },
    )
    assert oversized.status_code == 422

    test_client.delete(f"/api/projects/{project_id}")
    deleted_configuration = test_client.get(
        f"/api/projects/{project_id}/configuration"
    )
    assert deleted_configuration.status_code == 200
    blocked = test_client.put(
        f"/api/projects/{project_id}/configuration",
        json={
            "project": {"id": str(source_uuid), "changed": True},
            "layout": {},
        },
    )
    assert blocked.status_code == 409
    listed = test_client.get("/api/projects?include_deleted=true").json()["items"][0]
    assert len(listed["versions"]) == 1


def test_get_configuration_rejects_stored_project_id_mismatch(client):
    test_client, _ = client
    source_uuid = uuid.uuid4()
    imported = test_client.post(
        "/api/projects/import",
        data={"source_uuid": str(source_uuid)},
        files={
            "archive": (
                f"{source_uuid}.zip",
                make_configuration_zip(
                    "WrongIdentity", {"id": str(uuid.uuid4()), "value": 1}
                ),
                "application/zip",
            )
        },
    )
    assert imported.status_code == 400
    assert "does not match" in imported.json()["detail"]
