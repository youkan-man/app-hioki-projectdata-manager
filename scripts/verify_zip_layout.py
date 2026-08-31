#!/usr/bin/env python3
"""Verify the canonical ZIP layout through the public HTTP API.

Run only against a disposable environment. Created projects are soft-deleted,
but their immutable archive files intentionally remain in archive storage.
"""

from __future__ import annotations

import argparse
import io
import json
import ssl
import sys
import uuid
import zipfile
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    headers: object

    def json(self) -> object:
        return json.loads(self.body)


def make_zip(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in entries.items():
            archive.writestr(path, content)
    return output.getvalue()


def multipart(filename: str, archive: bytes, source_uuid: str | None) -> tuple[bytes, str]:
    boundary = f"codex-zip-layout-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    def add(value: str) -> None:
        chunks.append(value.encode("utf-8"))

    if source_uuid is not None:
        add(f"--{boundary}\r\n")
        add('Content-Disposition: form-data; name="source_uuid"\r\n\r\n')
        add(f"{source_uuid}\r\n")
    add(f"--{boundary}\r\n")
    add(
        'Content-Disposition: form-data; name="archive"; '
        f'filename="{filename}"\r\n'
    )
    add("Content-Type: application/zip\r\n\r\n")
    chunks.append(archive)
    add(f"\r\n--{boundary}--\r\n")
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


class Api:
    def __init__(self, base_url: str, insecure: bool) -> None:
        self.base_url = base_url.rstrip("/")
        self.context = ssl._create_unverified_context() if insecure else None

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        request = Request(
            f"{self.base_url}{path}", data=body, headers=headers or {}, method=method
        )
        try:
            with urlopen(request, timeout=30, context=self.context) as response:
                return Response(response.status, response.read(), response.headers)
        except HTTPError as error:
            return Response(error.code, error.read(), error.headers)

    def upload(
        self, filename: str, archive: bytes, source_uuid: str | None = None
    ) -> Response:
        body, content_type = multipart(filename, archive, source_uuid)
        return self.request(
            "POST",
            "/api/projects/import",
            body,
            {"Content-Type": content_type, "Content-Length": str(len(body))},
        )


def expect_status(response: Response, expected: int, label: str) -> None:
    if response.status != expected:
        detail = response.body.decode("utf-8", errors="replace")
        raise AssertionError(f"{label}: expected HTTP {expected}, got {response.status}: {detail}")


def assert_flat(archive_bytes: bytes, expected: dict[str, bytes], label: str) -> None:
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        names = {item.filename for item in archive.infolist() if not item.is_dir()}
        if names != set(expected):
            raise AssertionError(
                f"{label}: expected flat entries {sorted(expected)}, got {sorted(names)}"
            )
        for path, content in expected.items():
            if archive.read(path) != content:
                raise AssertionError(f"{label}: content differs for {path}")


def imported_coordinates(response: Response, label: str) -> tuple[str, str]:
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
        raise AssertionError(f"{label}: response has no project id")
    versions = payload.get("versions")
    if not isinstance(versions, list) or not versions or not isinstance(versions[0], dict):
        raise AssertionError(f"{label}: response has no version")
    version_id = versions[0].get("id")
    if not isinstance(version_id, str):
        raise AssertionError(f"{label}: response has no version id")
    return payload["id"], version_id


def verify(api: Api) -> None:
    created_projects: list[str] = []
    try:
        flat_uuid = str(uuid.uuid4())
        flat_entries = {
            "Flat.gprj": b"flat-project",
            "measurements/data.bin": b"flat-data",
        }
        flat_response = api.upload(
            f"{flat_uuid}.zip", make_zip(flat_entries), source_uuid=None
        )
        expect_status(flat_response, 201, "flat upload with filename UUID inference")
        flat_project, flat_version = imported_coordinates(flat_response, "flat upload")
        created_projects.append(flat_project)
        flat_download = api.request(
            "GET", f"/api/projects/{flat_project}/versions/{flat_version}/archive"
        )
        expect_status(flat_download, 200, "flat download")
        assert_flat(flat_download.body, flat_entries, "flat download")
        print("PASS flat input -> flat download (filename UUID inference)")

        legacy_uuid = str(uuid.uuid4())
        legacy_flat_entries = {
            "Legacy.gprj": b"legacy-project",
            "measurements/data.bin": b"legacy-data",
        }
        legacy_wrapped_entries = {
            f"{legacy_uuid}/{path}": content
            for path, content in legacy_flat_entries.items()
        }
        legacy_response = api.upload(
            "legacy.zip", make_zip(legacy_wrapped_entries), source_uuid=legacy_uuid
        )
        expect_status(legacy_response, 201, "legacy wrapped upload")
        legacy_project, legacy_version = imported_coordinates(
            legacy_response, "legacy wrapped upload"
        )
        created_projects.append(legacy_project)
        legacy_download = api.request(
            "GET", f"/api/projects/{legacy_project}/versions/{legacy_version}/archive"
        )
        expect_status(legacy_download, 200, "legacy normalized download")
        assert_flat(
            legacy_download.body, legacy_flat_entries, "legacy normalized download"
        )
        print("PASS legacy UUID wrapper input -> flat download")

        nested_uuid = str(uuid.uuid4())
        double_wrapped = make_zip(
            {f"{nested_uuid}/{nested_uuid}/Nested.gprj": b"double-wrapper"}
        )
        rejected = api.upload(
            "double-wrapped.zip", double_wrapped, source_uuid=nested_uuid
        )
        expect_status(rejected, 400, "double UUID wrapper rejection")
        print("PASS double UUID wrapper rejected")
    finally:
        for project_id in created_projects:
            response = api.request("DELETE", f"/api/projects/{project_id}")
            if response.status != 200:
                print(
                    f"WARN cleanup failed for {project_id}: HTTP {response.status}",
                    file=sys.stderr,
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification for a disposable self-signed HTTPS environment.",
    )
    arguments = parser.parse_args()
    try:
        verify(Api(arguments.base_url, arguments.insecure))
    except Exception as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    print("ZIP layout contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
