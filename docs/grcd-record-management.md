# GRCD record management — implementation and acceptance scope

## Status

Implementation branch: `feature/grcd-record-management`. Native HIOKI binary decoding is **not verified and not claimed**. The official sample request returned HTTP 503 on 2026-10-22. Synthetic JSON/SQLite/CSV fixtures test generic containers and application contracts; they are not native GRCD fixtures.

## User workflow

The new **レコードデータ** view accepts up to 20 `.grcd` files per selection. Selecting a project explicitly associates imports with that project. Otherwise, the original project name and GRCD filename stem are compared using Unicode NFC and case-insensitive comparison. Exactly one active match is automatically associated. No match or multiple matches remains unlinked. The edit action allows explicit linking, relinking, and unlinking.

Right click, the visible ellipsis button, and Shift+F10/ContextMenu open one action menu. Arrow/Home/End navigation, Escape, outside dismissal and focus return are supported. Record actions include data inspection, metadata/project editing, companion CSV attachment, original download, CSV export, soft deletion, and restoration.

List sorting: recording start, recording end, import date, name and size, ascending/descending. Missing timestamps stay last in either direction. Stable UUID ties and pagination avoid unstable ordering. Search covers name, original filename and notes. Project and unlinked filters are available. Deleted projects retain their record associations; deleting a record does not delete either its project or its files.

## Source data and parsing boundary

GRCD originals are immutable SHA-256-addressed blobs. An identical original is deduplicated; re-import never silently changes its association. If the matching record is deleted, restore it from the deleted view. Keep the database and the complete archive volume together for backups. The existing ZIP-only rebuild command does not rebuild the record catalog; database backup is required.

Generic read-only inspection supports self-describing JSON object arrays, ordinary SQLite tables, and JSON/CSV tables inside safe ZIP containers. This does not interpret proprietary HIOKI binary layouts, units, scaling factors or epoch timestamps. SQLite BLOBs are displayed as hexadecimal, not guessed as measurement arrays. JSON/CSV numeric strings are returned as strings to avoid JavaScript integer rounding.

Unsupported, damaged or excessive data is still preserved as an original with an explicit unavailable status. It cannot be exported as fabricated/empty measurement CSV. A GENNECT-exported CSV can instead be explicitly attached. The UI and API identify it as `companion-csv`, not as a direct GRCD conversion. Attaching a CSV replaces the derived table/time metadata, not the original GRCD. The companion's exact original is separately downloadable.

CSV input: a comma-separated header row, unique nonempty column names, UTF-8/BOM or explicitly selected CP932. Optional timestamp mapping accepts ISO date-time strings. Naive timestamps require an explicit IANA time zone. DST ambiguity and nonexistent local times are rejected. Aware timestamps are normalized to UTC; the UI identifies the browser's display zone. Manual metadata dates require a time zone and an ordered interval. Metadata-only dates do not invent row timestamps.

Table viewing supports literal search, typed numeric/lexical sorting, paging and timestamp intervals where an identified timestamp column exists. CSV export applies the same filter and sort to all matching rows, not just the visible page. Exports use UTF-8 BOM, CRLF and CSV quoting. Spreadsheet formula prefixes in text are neutralized; ordinary signed decimal/scientific values are preserved. Download the companion original when exact input bytes are required.

## Ownership and invariants

- `record_models.py`: record association, metadata, revision-based optimistic concurrency and lifecycle.
- `record_data.py`: bounded container decoding, timestamp rules, table selection and safe CSV serialization. No database or network access.
- `record_routes.py`: upload/storage, transaction and HTTP orchestration. Storage keys are generated, never supplied by uploaded paths. Originals and derived files are immutable; database commits publish references. Failed transactions can leave unreferenced blobs, which must not be deleted without a reference-aware maintenance procedure.
- `frontend/src/records`: record API, contextual actions, focused metadata dialogs, and a persistent list plus data detail view. The existing project workspace is retained.

Storage limits: original upload at most the lower of the configured upload limit and 256 MiB. Generic parsing and companion CSV at most 32 MiB, 100,000 rows per table, 256 columns, 64 tables, 2,000,000 aggregate cells, and 64 KiB per cell. ZIP inspection additionally limits entry count, expanded size and compression ratio and refuses traversal, symlinks, encrypted or duplicate entries. These conservative limits are explicit, not silent truncation. Large native measurement decoding remains a separate acceptance gap.

## Skill application record

The local skill server returned approved default version 1 bundles. SHA-256 was checked before extraction. Per-skill priorities were retained; the catalog omitted the shared `application_priority_policy`, so policy completeness is unverified.

Applied/evaluated in priority order:

| Priority | Skill | Application |
| --- | --- | --- |
| always | ask-zeus-for-token | No new credential infrastructure. Gateway credentials stay outside the guest and repository. No token disclosure. |
| always | infra-agents-wiki-record | Evidence-oriented knowledge recording and read-back required before claiming a Wiki publication. |
| proactive | design-code-boundaries | Original storage, pure table transformations, persistence, HTTP and UI separated by ownership. |
| proactive | frontend-ui-constraints | Compact comparative tables, visible/touch/keyboard menu entry, focused dialogs, actual screenshot validation required. |
| proactive | refactor-code-boundaries | Evaluated; broad existing-code refactoring deferred because the task is feature development. |
| appropriate | roadmap-driven-development | Existing repository requirements/roadmap used. Its external Baseline/approved-node framework is absent here; no IDs, approvals or independent-review verdicts are invented. |
| appropriate | sandbox-control-plane | Disposable managed Sandbox; credential-free pinned source; HTTP-only operations through the requested transport Gateway. CLI-specific execution is not claimed. |
| recommended | infra-agents-wiki-search | Internal knowledge lookup before claiming native format compatibility. |

## Acceptance checklist

- [ ] Existing backend and frontend tests and frontend build pass on final committed source.
- [ ] Record association, duplicate uploads, missing/deleted projects, lifecycle and concurrent revision conflicts are verified.
- [ ] Unknown dates sort last; time-zone conversion, interval validation, CSV precision and formula neutralization are verified.
- [ ] Native HIOKI GRCD fixture and corresponding GENNECT CSV are compared (currently blocked; generic fixtures are not a substitute).
- [ ] Desktop/mobile running UI screenshots are captured and visually reviewed; menus, dialog keyboard behavior and state continuity are exercised.
- [ ] Evidence, exact commit, test counts and remaining gaps are recorded in verification documentation.
