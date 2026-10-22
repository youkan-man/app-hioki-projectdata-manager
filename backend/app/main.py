from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .archives import (
    ArchiveIdentityError,
    ArchiveValidationError,
    SourceUuidRequiredError,
    prepare_flat_download,
    receive_and_validate,
)
from .config import Settings
from .db import Base, make_engine, make_session_factory, session_dependency
from .models import Project, ProjectVersion
from .record_routes import register_record_routes
from .schemas import (
    ConfigurationRead,
    ConfigurationFileRead,
    ConfigurationUpdate,
    ProjectList,
    ProjectRead,
    ProjectUpdate,
    RebuildResult,
)
from .service import (
    ProjectDeletedError,
    ProjectHasNoVersionsError,
    ProjectNotFoundError,
    get_latest_configuration,
    import_archive,
    rebuild_index,
    update_latest_configuration,
)
from .storage import FilesystemArchiveStorage


_ARCHIVE_FILENAME = re.compile(
    r"^(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"(?:-v[0-9]+)?\.zip$",
    re.IGNORECASE,
)


def _source_uuid_from_request(raw: str | None, filename: str | None) -> uuid.UUID | None:
    candidate = raw
    if not candidate and filename:
        # Canonical uploads use <uuid>.zip; downloaded versions use <uuid>-vN.zip.
        match = _ARCHIVE_FILENAME.fullmatch(filename)
        candidate = match.group("uuid") if match else None
    if not candidate:
        return None
    try:
        parsed = uuid.UUID(candidate)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="source_uuid is invalid") from exc
    if raw is not None and candidate.lower() != str(parsed):
        raise HTTPException(status_code=422, detail="source_uuid must use canonical form")
    return parsed


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    storage = FilesystemArchiveStorage(settings.archive_root)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        Base.metadata.create_all(engine)
        if settings.rebuild_index_on_startup:
            with session_factory.begin() as session:
                rebuild_index(session, storage, settings)
        yield

    app = FastAPI(title="GENNECT Project Manager API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.storage = storage
    app.state.session_factory = session_factory
    get_session = session_dependency(session_factory)
    register_record_routes(app)

    def load_project(session: Session, project_id: uuid.UUID) -> Project:
        project = session.scalar(
            select(Project)
            .where(Project.id == project_id)
            .options(selectinload(Project.versions))
        )
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/projects", response_model=ProjectList)
    def list_projects(
        include_deleted: Annotated[bool, Query()] = False,
        session: Session = Depends(get_session),
    ) -> ProjectList:
        statement = select(Project).options(selectinload(Project.versions))
        if not include_deleted:
            statement = statement.where(Project.deleted_at.is_(None))
        items = list(session.scalars(statement.order_by(Project.updated_at.desc())))
        return ProjectList(items=items, total=len(items))

    @app.post(
        "/api/projects/import",
        response_model=ProjectRead,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_project(
        archive: Annotated[UploadFile, File()],
        source_uuid: Annotated[str | None, Form()] = None,
        project_name: Annotated[str | None, Form()] = None,
        note: Annotated[str | None, Form(max_length=10_000)] = None,
        session: Session = Depends(get_session),
    ) -> Project:
        supplied_uuid = _source_uuid_from_request(source_uuid, archive.filename)
        try:
            validated = await receive_and_validate(archive, settings, supplied_uuid)
        except (ArchiveIdentityError, SourceUuidRequiredError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ArchiveValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            if project_name is not None and project_name != validated.project_name:
                raise HTTPException(
                    status_code=422,
                    detail="project_name does not match the archive .gprj filename",
                )
            try:
                with session.begin():
                    project = import_archive(session, storage, validated, note)
            except ProjectDeletedError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            session.refresh(project)
            return load_project(session, project.id)
        finally:
            validated.path.unlink(missing_ok=True)

    @app.patch("/api/projects/{project_id}", response_model=ProjectRead)
    def update_project(
        project_id: uuid.UUID,
        update: ProjectUpdate,
        session: Session = Depends(get_session),
    ) -> Project:
        if not update.model_fields_set:
            raise HTTPException(status_code=422, detail="No fields supplied")
        with session.begin():
            project = load_project(session, project_id)
            if update.name is not None:
                project.display_name = update.name
            if "description" in update.model_fields_set:
                project.description = update.description
        return load_project(session, project_id)

    @app.get(
        "/api/projects/{project_id}/configuration",
        response_model=ConfigurationRead,
    )
    def get_configuration(
        project_id: uuid.UUID, session: Session = Depends(get_session)
    ) -> ConfigurationRead:
        try:
            state = get_latest_configuration(
                session, storage, settings, project_id
            )
        except (ProjectNotFoundError, ProjectHasNoVersionsError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ProjectDeletedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ArchiveValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (ArchiveIdentityError, OSError) as exc:
            raise HTTPException(
                status_code=409,
                detail="Project version archive identity is inconsistent",
            ) from exc
        return ConfigurationRead(
            version=state.version_number,
            project=ConfigurationFileRead(
                filename=state.document.project.filename,
                config=state.document.project.config,
            ),
            layout=(
                ConfigurationFileRead(
                    filename=state.document.layout.filename,
                    config=state.document.layout.config,
                )
                if state.document.layout is not None
                else None
            ),
        )

    @app.put(
        "/api/projects/{project_id}/configuration",
        response_model=ProjectRead,
    )
    def put_configuration(
        project_id: uuid.UUID,
        update: ConfigurationUpdate,
        session: Session = Depends(get_session),
    ) -> Project:
        try:
            with session.begin():
                project = update_latest_configuration(
                    session,
                    storage,
                    settings,
                    project_id,
                    update.project,
                    update.layout,
                    update.note,
                )
        except (ProjectNotFoundError, ProjectHasNoVersionsError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ProjectDeletedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ArchiveValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (ArchiveIdentityError, OSError) as exc:
            raise HTTPException(
                status_code=409,
                detail="Project version archive identity is inconsistent",
            ) from exc
        session.refresh(project)
        return load_project(session, project_id)

    @app.delete("/api/projects/{project_id}", response_model=ProjectRead)
    def delete_project(
        project_id: uuid.UUID, session: Session = Depends(get_session)
    ) -> Project:
        with session.begin():
            project = load_project(session, project_id)
            if project.deleted_at is None:
                project.deleted_at = datetime.now(timezone.utc)
        return load_project(session, project_id)

    @app.post("/api/projects/{project_id}/restore", response_model=ProjectRead)
    def restore_project(
        project_id: uuid.UUID, session: Session = Depends(get_session)
    ) -> Project:
        with session.begin():
            project = load_project(session, project_id)
            project.deleted_at = None
        return load_project(session, project_id)

    @app.get("/api/projects/{project_id}/versions/{version_id}/archive")
    def download_archive(
        project_id: uuid.UUID,
        version_id: uuid.UUID,
        session: Session = Depends(get_session),
    ) -> StreamingResponse:
        version = session.scalar(
            select(ProjectVersion)
            .join(Project)
            .where(Project.id == project_id, ProjectVersion.id == version_id)
        )
        if version is None:
            raise HTTPException(status_code=404, detail="Project version not found")

        try:
            with storage.open(version.archive_key) as archive_file:
                download_path = prepare_flat_download(
                    archive_file, settings, version.project.source_uuid
                )
        except (ArchiveValidationError, ArchiveIdentityError, OSError) as exc:
            raise HTTPException(
                status_code=500, detail="Stored project archive is invalid"
            ) from exc

        def stream():
            try:
                with download_path.open("rb") as archive_file:
                    while chunk := archive_file.read(1024 * 1024):
                        yield chunk
            finally:
                download_path.unlink(missing_ok=True)

        filename = f"{version.project.source_uuid}-v{version.version_number}.zip"
        return StreamingResponse(
            stream(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/admin/rebuild-index", response_model=RebuildResult)
    def rebuild(session: Session = Depends(get_session)) -> RebuildResult:
        with session.begin():
            counts = rebuild_index(session, storage, settings)
        return RebuildResult(**asdict(counts))

    return app


app = create_app()
