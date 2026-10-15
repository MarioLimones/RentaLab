from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Match
from starlette.types import Scope

from rentalab.auth.middleware import AuthGuardMiddleware
from rentalab.auth.openapi import add_auth_openapi
from rentalab.auth.routes import router as auth_router
from rentalab.auth.service import AuthService
from rentalab.config import Settings
from rentalab.database import create_database_engine, is_sqlite_busy
from rentalab.equipment.routes import router
from rentalab.equipment.service import DuplicateEquipmentCode, EquipmentNotFound
from rentalab.imports.routes import router as import_router
from rentalab.incidents.routes import router as incident_router
from rentalab.incidents.service import IncidentConflict, IncidentNotFound
from rentalab.me.incidents import router as me_incident_router
from rentalab.me.reservations import router as me_reservation_router
from rentalab.me.saved_products import router as me_saved_products_router
from rentalab.public_catalogue.routes import router as public_catalogue_router
from rentalab.reservations.routes import availability_router
from rentalab.reservations.routes import router as reservation_router
from rentalab.reservations.service import ReservationConflict, ReservationNotFound


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class FrontendRoute(APIRoute):
    """Exclude server paths during routing, preserving their 404/405 and Allow headers."""

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        match, child_scope = super().matches(scope)
        full_path = child_scope.get("path_params", {}).get("full_path", "")
        if full_path.split("/", 1)[0] in {"api", "health", "docs", "redoc", "openapi.json"}:
            return Match.NONE, {}
        return match, child_scope


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    config.require_auth()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        yield
        application.state.engine.dispose()

    application = FastAPI(
        title="RentaLab API",
        version="0.1.0",
        description="Equipos, incidencias, reservas y disponibilidad de alquiler audiovisual.",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
        lifespan=lifespan,
    )
    application.state.engine = create_database_engine(
        config.database_url, busy_timeout_ms=config.sqlite_busy_timeout_ms
    )
    application.state.session_factory = sessionmaker(
        application.state.engine, expire_on_commit=False
    )
    application.state.settings = config
    application.state.auth_service = AuthService(config, application.state.session_factory)
    application.add_middleware(AuthGuardMiddleware, auth_service=application.state.auth_service)
    assert config.session_secret is not None
    application.add_middleware(
        SessionMiddleware,
        secret_key=config.session_secret.get_secret_value(),
        session_cookie="rentalab_session",
        max_age=config.session_ttl_seconds,
        same_site="lax",
        https_only=config.environment == "production",
    )
    application.include_router(auth_router)
    application.include_router(me_reservation_router)
    application.include_router(me_incident_router)
    application.include_router(me_saved_products_router)
    application.include_router(public_catalogue_router)
    application.include_router(router)
    application.include_router(reservation_router)
    application.include_router(availability_router)
    application.include_router(incident_router)
    application.include_router(import_router)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        if request.url.path.rstrip("/") in {"/api/auth/login", "/api/auth/register"}:
            # FastAPI otherwise echoes the received body in validation details.
            return JSONResponse(
                status_code=422,
                content={
                    "detail": [
                        {"type": item["type"], "loc": item["loc"], "msg": item["msg"]}
                        for item in error.errors()
                    ]
                },
            )
        return await request_validation_exception_handler(request, error)

    @application.exception_handler(EquipmentNotFound)
    async def equipment_not_found(_request: Request, _error: EquipmentNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "El equipo no existe"})

    @application.exception_handler(DuplicateEquipmentCode)
    async def duplicate_code(_request: Request, _error: DuplicateEquipmentCode) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"detail": "Ya existe un equipo con ese código"}
        )

    @application.exception_handler(ReservationNotFound)
    async def reservation_not_found(_request: Request, _error: ReservationNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "La reserva no existe"})

    @application.exception_handler(ReservationConflict)
    async def reservation_conflict(_request: Request, error: ReservationConflict) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @application.exception_handler(IncidentNotFound)
    async def incident_not_found(_request: Request, _error: IncidentNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "La incidencia no existe"})

    @application.exception_handler(IncidentConflict)
    async def incident_conflict(_request: Request, error: IncidentConflict) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @application.exception_handler(OperationalError)
    async def database_busy(_request: Request, error: OperationalError) -> JSONResponse:
        if not is_sqlite_busy(error):
            raise error
        return JSONResponse(
            status_code=503,
            content={"detail": "La base de datos está ocupada; vuelve a intentarlo"},
            headers={"Retry-After": "1"},
        )

    @application.get(
        "/health", response_model=HealthResponse, tags=["Sistema"], summary="Estado HTTP"
    )
    def health() -> HealthResponse:
        return HealthResponse()

    if config.frontend_dist is not None:
        add_frontend_routes(application, config.frontend_dist)
    add_auth_openapi(application)
    return application


def add_frontend_routes(application: FastAPI, frontend_dist: Path) -> None:
    dist = frontend_dist.resolve()
    if not (dist / "index.html").is_file():
        raise ValueError("RENTALAB_FRONTEND_DIST must contain a built index.html")

    def frontend(full_path: str) -> FileResponse:
        parts = full_path.split("/")
        prefix = parts[0]
        # The URL uses forward slashes on every platform, including Windows.
        if "\\" in full_path or "\x00" in full_path or any(part.startswith(".") for part in parts):
            raise HTTPException(status_code=404, detail="Archivo no encontrado")
        candidate = (dist / full_path).resolve()
        if not candidate.is_relative_to(dist):
            raise HTTPException(status_code=404, detail="Archivo no encontrado")
        if candidate.is_file():
            headers = {"Cache-Control": "no-cache"} if candidate == dist / "index.html" else None
            return FileResponse(candidate, headers=headers)
        # A real dist directory is a static namespace, even for extensionless files.
        # Other extensionless paths belong to React, including its not-found page.
        if full_path and (
            prefix == "assets"
            or (dist / prefix).is_dir()
            or any(Path(part).suffix for part in parts)
        ):
            raise HTTPException(status_code=404, detail="Archivo no encontrado")
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    application.router.add_api_route(
        "/{full_path:path}",
        frontend,
        methods=["GET", "HEAD"],
        include_in_schema=False,
        route_class_override=FrontendRoute,
    )


app = create_app()
