from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi import Path as ParametroRuta
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Match
from starlette.types import Scope

from rentalab.autenticacion.intermediario import IntermediarioAutenticacion
from rentalab.autenticacion.openapi import agregar_autenticacion_openapi
from rentalab.autenticacion.rutas import enrutador as autenticacion_enrutador
from rentalab.autenticacion.servicio import ServicioAutenticacion
from rentalab.base_datos import crear_base_datos_motor, es_sqlite_ocupado
from rentalab.catalogo_publico.rutas import enrutador as publico_catalogo_enrutador
from rentalab.compatibilidad import ModeloApi
from rentalab.configuracion import Configuracion
from rentalab.cuenta.incidencias import enrutador as cuenta_incidencia_enrutador
from rentalab.cuenta.productos_guardados import enrutador as cuenta_guardados_productos_enrutador
from rentalab.cuenta.reservas import enrutador as cuenta_reserva_enrutador
from rentalab.equipo.rutas import enrutador
from rentalab.equipo.servicio import CodigoEquipoDuplicado, EquipoNoEncontrado
from rentalab.importaciones.rutas import enrutador as importacion_enrutador
from rentalab.incidencias.rutas import enrutador as incidencia_enrutador
from rentalab.incidencias.servicio import ConflictoIncidencia, IncidenciaNoEncontrada
from rentalab.reservas.rutas import disponibilidad_enrutador
from rentalab.reservas.rutas import enrutador as reserva_enrutador
from rentalab.reservas.servicio import ConflictoReserva, ReservaNoEncontrada


class RespuestaSalud(ModeloApi):
    estado: Literal["ok"] = "ok"


class RutaInterfaz(APIRoute):
    """Excluye rutas del servidor y conserva sus errores 404/405 y cabeceras Allow."""

    def matches(instancia, ambito: Scope) -> tuple[Match, Scope]:
        coincidencia, hijo_ambito = super().matches(ambito)
        completa_ruta = hijo_ambito.get("path_params", {}).get("full_path", "")
        if completa_ruta.split("/", 1)[0] in {"api", "health", "docs", "redoc", "openapi.json"}:
            return Match.NONE, {}
        return coincidencia, hijo_ambito


def crear_aplicacion(ajustes: Configuracion | None = None) -> FastAPI:
    configuracion = ajustes or Configuracion()
    configuracion.exigir_autenticacion()

    @asynccontextmanager
    async def ciclo_vida(aplicacion: FastAPI) -> AsyncIterator[None]:
        yield
        aplicacion.state.motor.dispose()

    aplicacion = FastAPI(
        title="RentaLab API",
        version="0.1.0",
        description="Equipos, incidencias, reservas y disponibilidad de alquiler audiovisual.",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
        lifespan=ciclo_vida,
    )
    aplicacion.state.motor = crear_base_datos_motor(
        configuracion.url_base_datos, ocupado_espera_ms=configuracion.espera_sqlite_ocupado_ms
    )
    aplicacion.state.fabrica_sesiones = sessionmaker(aplicacion.state.motor, expire_on_commit=False)
    aplicacion.state.ajustes = configuracion
    aplicacion.state.autenticacion_servicio = ServicioAutenticacion(
        configuracion, aplicacion.state.fabrica_sesiones
    )
    aplicacion.add_middleware(
        IntermediarioAutenticacion, autenticacion_servicio=aplicacion.state.autenticacion_servicio
    )
    assert configuracion.secreto_sesion is not None
    aplicacion.add_middleware(
        SessionMiddleware,
        secret_key=configuracion.secreto_sesion.get_secret_value(),
        session_cookie="rentalab_session",
        max_age=configuracion.vigencia_sesion_segundos,
        same_site="lax",
        https_only=configuracion.entorno == "production",
    )
    aplicacion.include_router(autenticacion_enrutador)
    aplicacion.include_router(cuenta_reserva_enrutador)
    aplicacion.include_router(cuenta_incidencia_enrutador)
    aplicacion.include_router(cuenta_guardados_productos_enrutador)
    aplicacion.include_router(publico_catalogo_enrutador)
    aplicacion.include_router(enrutador)
    aplicacion.include_router(reserva_enrutador)
    aplicacion.include_router(disponibilidad_enrutador)
    aplicacion.include_router(incidencia_enrutador)
    aplicacion.include_router(importacion_enrutador)

    @aplicacion.exception_handler(RequestValidationError)
    async def validacion_error(solicitud: Request, error: RequestValidationError) -> JSONResponse:
        if solicitud.url.path.rstrip("/") in {"/api/auth/login", "/api/auth/register"}:
            # FastAPI devolvería el cuerpo recibido dentro de los detalles de validación.
            return JSONResponse(
                status_code=422,
                content={
                    "detail": [
                        {"type": elemento["type"], "loc": elemento["loc"], "msg": elemento["msg"]}
                        for elemento in error.errors()
                    ]
                },
            )
        return await request_validation_exception_handler(solicitud, error)

    @aplicacion.exception_handler(EquipoNoEncontrado)
    async def equipo_no_encontrado(_solicitud: Request, _error: EquipoNoEncontrado) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "El equipo no existe"})

    @aplicacion.exception_handler(CodigoEquipoDuplicado)
    async def duplicado_codigo(_solicitud: Request, _error: CodigoEquipoDuplicado) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"detail": "Ya existe un equipo con ese código"}
        )

    @aplicacion.exception_handler(ReservaNoEncontrada)
    async def reserva_no_encontrado(
        _solicitud: Request, _error: ReservaNoEncontrada
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "La reserva no existe"})

    @aplicacion.exception_handler(ConflictoReserva)
    async def reserva_conflicto(_solicitud: Request, error: ConflictoReserva) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @aplicacion.exception_handler(IncidenciaNoEncontrada)
    async def incidencia_no_encontrado(
        _solicitud: Request, _error: IncidenciaNoEncontrada
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "La incidencia no existe"})

    @aplicacion.exception_handler(ConflictoIncidencia)
    async def incidencia_conflicto(_solicitud: Request, error: ConflictoIncidencia) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @aplicacion.exception_handler(OperationalError)
    async def base_datos_ocupado(_solicitud: Request, error: OperationalError) -> JSONResponse:
        if not es_sqlite_ocupado(error):
            raise error
        return JSONResponse(
            status_code=503,
            content={"detail": "La base de datos está ocupada; vuelve a intentarlo"},
            headers={"Retry-After": "1"},
        )

    @aplicacion.get(
        "/health", response_model=RespuestaSalud, tags=["Sistema"], summary="Estado HTTP"
    )
    def salud() -> RespuestaSalud:
        return RespuestaSalud()

    if configuracion.interfaz_compilada is not None:
        agregar_interfaz_rutas(aplicacion, configuracion.interfaz_compilada)
    agregar_autenticacion_openapi(aplicacion)
    return aplicacion


def agregar_interfaz_rutas(aplicacion: FastAPI, interfaz_compilada: Path) -> None:
    compilacion = interfaz_compilada.resolve()
    if not (compilacion / "index.html").is_file():
        raise ValueError("RENTALAB_FRONTEND_DIST must contain a built index.html")

    def interfaz(completa_ruta: Annotated[str, ParametroRuta(alias="full_path")]) -> FileResponse:
        partes = completa_ruta.split("/")
        prefijo = partes[0]
        # La URL usa barras normales en todas las plataformas, incluido Windows.
        if (
            "\\" in completa_ruta
            or "\x00" in completa_ruta
            or any(parte.startswith(".") for parte in partes)
        ):
            raise HTTPException(status_code=404, detail="Archivo no encontrado")
        candidato = (compilacion / completa_ruta).resolve()
        if not candidato.is_relative_to(compilacion):
            raise HTTPException(status_code=404, detail="Archivo no encontrado")
        if candidato.is_file():
            cabeceras = (
                {"Cache-Control": "no-cache"} if candidato == compilacion / "index.html" else None
            )
            return FileResponse(candidato, headers=cabeceras)
        # Un directorio compilado real sirve contenido estático, incluso sin extensión.
        # Las otras rutas sin extensión corresponden a React, incluida su página de error 404.
        if completa_ruta and (
            prefijo == "assets"
            or (compilacion / prefijo).is_dir()
            or any(Path(parte).suffix for parte in partes)
        ):
            raise HTTPException(status_code=404, detail="Archivo no encontrado")
        return FileResponse(compilacion / "index.html", headers={"Cache-Control": "no-cache"})

    aplicacion.router.add_api_route(
        "/{full_path:path}",
        interfaz,
        methods=["GET", "HEAD"],
        include_in_schema=False,
        route_class_override=RutaInterfaz,
    )


aplicacion = crear_aplicacion()
