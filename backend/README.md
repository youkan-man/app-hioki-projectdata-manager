# GENNECT Project Manager API

FastAPI service for storing canonical GENNECT project ZIPs and PostgreSQL metadata.

Configuration:

- `DATABASE_URL` (default: `postgresql+psycopg://gennect:gennect@postgres:5432/gennect`)
- `ARCHIVE_ROOT` (default: `./data/archives`; Docker Compose sets `/data/archives`)
- `STORAGE_BACKEND` (`filesystem` for now; the application depends on `ArchiveStorage`)
- `REBUILD_INDEX_ON_STARTUP=true` to recover missing metadata from stored archives
- `MAX_UPLOAD_BYTES`, `MAX_ARCHIVE_ENTRIES`, `MAX_UNCOMPRESSED_BYTES`, `MAX_COMPRESSION_RATIO`

The canonical ZIP contains the project folder's contents directly at ZIP root, including
exactly one root-level `*.gprj` file. The UUID travels as the multipart `source_uuid`
(or is inferred from a canonical `<uuid>.zip` / `<uuid>-vN.zip` filename). Legacy ZIPs
with one UUID wrapper directory are still accepted and normalized before storage; legacy
archives already present in storage are normalized when downloaded. Restoring therefore
never creates a duplicated UUID directory. Imports reject
traversal, backslashes, Windows-unsafe names,
symlinks, encryption, duplicate paths, corrupt members, excessive entry counts,
expanded sizes, and compression ratios.

Run locally:

```bash
pip install -e '.[test]'
pytest
uvicorn app.main:app --reload
```
