#!/usr/bin/env python3
"""Verify two-JSON editing and opaque-entry preservation via the public API.

Run only against a disposable environment. The created project is soft-deleted,
but its immutable archive versions intentionally remain in archive storage.
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import sys
import uuid
import zipfile
from pathlib import Path
from typing import Any

from verify_zip_layout import Api, expect_status, make_zip


JsonObject = dict[str, Any]
JsonPath = tuple[str | int, ...]


def fixture_entries(directory: Path) -> dict[str, bytes]:
    if not directory.is_dir():
        raise AssertionError(f"fixture directory does not exist: {directory}")
    entries = {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }
    if not entries:
        raise AssertionError("fixture directory contains no files")
    return entries


def zip_entries(payload: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        files = [item for item in archive.infolist() if not item.is_dir()]
        names = [item.filename for item in files]
        if len(names) != len(set(names)):
            raise AssertionError("downloaded ZIP contains duplicate entry names")
        return {item.filename: archive.read(item) for item in files}


def root_member(entries: dict[str, bytes], suffix_or_name: str) -> str:
    matches = [
        name
        for name in entries
        if "/" not in name
        and (
            name.casefold() == suffix_or_name.casefold()
            or name.casefold().endswith(suffix_or_name.casefold())
        )
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one root member matching {suffix_or_name}, got {matches}"
        )
    return matches[0]


def parse_object(payload: bytes, label: str) -> JsonObject:
    value = json.loads(payload.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise AssertionError(f"{label} must be a JSON object")
    return value


def changed_scalar(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 1.0
    if isinstance(value, str):
        return value + " [E2E edit]"
    if value is None:
        return "E2E edit"
    raise TypeError("not a JSON scalar")


def mutate_one_scalar(document: JsonObject) -> tuple[JsonObject, JsonPath]:
    edited = copy.deepcopy(document)

    def visit(value: Any, path: JsonPath) -> JsonPath | None:
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, (dict, list)):
                    changed = visit(child, path + (key,))
                    if changed is not None:
                        return changed
                else:
                    value[key] = changed_scalar(child)
                    return path + (key,)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                if isinstance(child, (dict, list)):
                    changed = visit(child, path + (index,))
                    if changed is not None:
                        return changed
                else:
                    value[index] = changed_scalar(child)
                    return path + (index,)
        return None

    changed_path = visit(edited, ())
    if changed_path is None:
        raise AssertionError("JSON fixture has no scalar value to edit")
    return edited, changed_path


def differing_paths(before: Any, after: Any, path: JsonPath = ()) -> list[JsonPath]:
    if type(before) is not type(after):
        return [path]
    if isinstance(before, dict):
        if before.keys() != after.keys():
            return [path]
        return [
            changed
            for key in before
            for changed in differing_paths(before[key], after[key], path + (key,))
        ]
    if isinstance(before, list):
        if len(before) != len(after):
            return [path]
        return [
            changed
            for index, item in enumerate(before)
            for changed in differing_paths(item, after[index], path + (index,))
        ]
    return [] if before == after else [path]


def version_ids(project: object) -> dict[int, str]:
    if not isinstance(project, dict) or not isinstance(project.get("versions"), list):
        raise AssertionError("project response has no versions")
    result: dict[int, str] = {}
    for version in project["versions"]:
        if not isinstance(version, dict):
            raise AssertionError("invalid version response")
        number, identifier = version.get("version_number"), version.get("id")
        if not isinstance(number, int) or not isinstance(identifier, str):
            raise AssertionError("version response has invalid coordinates")
        result[number] = identifier
    return result


def verify(api: Api, fixture_dir: Path) -> None:
    original_entries = fixture_entries(fixture_dir)
    gprj_name = root_member(original_entries, ".gprj")
    layout_name = root_member(original_entries, "layout.lay")
    set_names = [name for name in original_entries if name.casefold().endswith(".set")]
    if not set_names:
        raise AssertionError("fixture must contain at least one .set file")

    source_uuid = str(uuid.uuid4())
    original_project = parse_object(original_entries[gprj_name], gprj_name)
    # The backend intentionally checks the gprj identity against source_uuid.
    # Use a fresh identity so this verifier can be rerun in one disposable stack.
    if "id" in original_project:
        original_project["id"] = source_uuid
        original_entries[gprj_name] = json.dumps(
            original_project,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    original_layout = parse_object(original_entries[layout_name], layout_name)
    edited_project, project_path = mutate_one_scalar(original_project)
    edited_layout, layout_path = mutate_one_scalar(original_layout)
    if differing_paths(original_project, edited_project) != [project_path]:
        raise AssertionError("project fixture mutation is not exactly one logical value")
    if differing_paths(original_layout, edited_layout) != [layout_path]:
        raise AssertionError("layout fixture mutation is not exactly one logical value")

    project_id: str | None = None
    try:
        imported = api.upload(
            f"{source_uuid}.zip", make_zip(original_entries), source_uuid=None
        )
        expect_status(imported, 201, "fixture import")
        imported_payload = imported.json()
        if not isinstance(imported_payload, dict) or not isinstance(
            imported_payload.get("id"), str
        ):
            raise AssertionError("import response has no project id")
        project_id = imported_payload["id"]
        initial_versions = version_ids(imported_payload)
        if set(initial_versions) != {1}:
            raise AssertionError(f"expected version 1, got {sorted(initial_versions)}")

        current = api.request("GET", f"/api/projects/{project_id}/configuration")
        expect_status(current, 200, "configuration fetch")
        state = current.json()
        if not isinstance(state, dict) or state.get("version") != 1:
            raise AssertionError("configuration fetch did not return version 1")
        if state.get("project") != {"filename": gprj_name, "config": original_project}:
            raise AssertionError("fetched project JSON differs from fixture")
        if state.get("layout") != {"filename": layout_name, "config": original_layout}:
            raise AssertionError("fetched layout JSON differs from fixture")

        update_body = json.dumps(
            {
                "project": edited_project,
                "layout": edited_layout,
                "note": "independent two-JSON preservation E2E",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        updated = api.request(
            "PUT",
            f"/api/projects/{project_id}/configuration",
            update_body,
            {"Content-Type": "application/json", "Content-Length": str(len(update_body))},
        )
        expect_status(updated, 200, "configuration update")
        updated_versions = version_ids(updated.json())
        if set(updated_versions) != {1, 2}:
            raise AssertionError(
                f"expected immutable versions 1 and 2, got {sorted(updated_versions)}"
            )

        downloads: dict[int, dict[str, bytes]] = {}
        for number, identifier in updated_versions.items():
            response = api.request(
                "GET", f"/api/projects/{project_id}/versions/{identifier}/archive"
            )
            expect_status(response, 200, f"version {number} download")
            downloads[number] = zip_entries(response.body)

        if downloads[1] != original_entries:
            raise AssertionError("version 1 entries or payload bytes changed")
        if downloads[2].keys() != original_entries.keys():
            raise AssertionError("version 2 entry paths differ from version 1")
        if downloads[2][gprj_name] == original_entries[gprj_name]:
            raise AssertionError("version 2 gprj payload did not change")
        if downloads[2][layout_name] == original_entries[layout_name]:
            raise AssertionError("version 2 layout payload did not change")
        if parse_object(downloads[2][gprj_name], gprj_name) != edited_project:
            raise AssertionError("version 2 gprj JSON differs from requested edit")
        if parse_object(downloads[2][layout_name], layout_name) != edited_layout:
            raise AssertionError("version 2 layout JSON differs from requested edit")

        editable = {gprj_name, layout_name}
        for name, payload in original_entries.items():
            if name not in editable and downloads[2][name] != payload:
                raise AssertionError(f"opaque payload changed: {name}")
        for name in set_names:
            if downloads[2][name] != original_entries[name]:
                raise AssertionError(f".set payload changed: {name}")

        print(f"PASS fetched version 1 and edited one value in {gprj_name}: {project_path}")
        print(f"PASS edited one value in {layout_name}: {layout_path}")
        print("PASS created version 2 while all version 1 entry payloads remained unchanged")
        print(f"PASS preserved {len(original_entries) - 2} opaque payload(s), including {len(set_names)} .set file(s)")
    finally:
        if project_id is not None:
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
        "--fixture-dir",
        type=Path,
        default=Path(".example/de795586-5cdb-4ca9-a472-938a1fbfb341"),
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification for a disposable self-signed HTTPS environment.",
    )
    arguments = parser.parse_args()
    try:
        verify(Api(arguments.base_url, arguments.insecure), arguments.fixture_dir)
    except Exception as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    print("Configuration editing contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
