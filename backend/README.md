# GENNECT Project Manager API

FastAPI service for storing canonical GENNECT project ZIPs and PostgreSQL metadata.

Configuration:

- `DATABASE_URL` (default: `postgresql+psycopg://gennect:gennect@postgres:5432/gennect`)
- `ARCHIVE_ROOT` (default: `./data/archives`; Docker Compose sets `/data/archives`)
- `STORAGE_BACKEND` (`filesystem` for now; the application depends on `ArchiveStorage`)
- `REBUILD_INDEX_ON_STARTUP=true` to recover missing metadata from stored archives
- `MAX_UPLOAD_BYTES`, `MAX_ARCHIVE_ENTRIES`, `MAX_UNCOMPRESSED_BYTES`, `MAX_COMPRESSION_RATIO`

The accepted ZIP shape is one canonical UUID top-level directory containing exactly
one direct `*.gprj` file. Imports reject traversal, backslashes, Windows-unsafe names,
symlinks, encryption, duplicate paths, corrupt members, excessive entry counts,
expanded sizes, and compression ratios.

Run locally:

```bash
pip install -e '.[test]'
pytest
uvicorn app.main:app --reload
```
