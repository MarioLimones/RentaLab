import re
from hmac import compare_digest

from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rentalab.autenticacion.dependencias import ROL_ERROR, SESION_ERROR, tiene_administrador_rol
from rentalab.autenticacion.servicio import ServicioAutenticacion
from rentalab.base_datos import es_sqlite_ocupado
from rentalab.catalogo_publico.medio import PUBLICO_RECURSO_RUTAS

SEGURO_METODOS = {"GET", "HEAD", "OPTIONS"}
CSRF_ERROR = "El token de seguridad no es válido; vuelve a intentarlo"


def publico_catalogo_ruta(ruta: str) -> bool:
    return (
        ruta == "/api/public/equipment"
        or ruta in PUBLICO_RECURSO_RUTAS
        or re.fullmatch(
            r"/api/public/equipment/[^/]+(?:/availability|/calendar|/reservations)?", ruta
        )
        is not None
    )


def cliente_operacion_ruta(ruta: str) -> bool:
    return ruta == "/api/me" or ruta.startswith("/api/me/")


class IntermediarioAutenticacion:
    def __init__(instancia, app: ASGIApp, autenticacion_servicio: ServicioAutenticacion) -> None:
        instancia.aplicacion = app
        instancia.autenticacion_servicio = autenticacion_servicio

    async def __call__(instancia, ambito: Scope, recibir: Receive, enviar: Send) -> None:
        ruta = ambito.get("path", "")
        if ambito["type"] != "http" or not (ruta == "/api" or ruta.startswith("/api/")):
            await instancia.aplicacion(ambito, recibir, enviar)
            return

        solicitud = Request(ambito)
        try:
            identidad = await run_in_threadpool(
                instancia.autenticacion_servicio.buscar_sesion, solicitud.session.get("sid")
            )
        except OperationalError as error:
            if not es_sqlite_ocupado(error):
                raise
            await JSONResponse(
                {"detail": "La base de datos está ocupada; vuelve a intentarlo"},
                status_code=503,
                headers={"Retry-After": "1", "Cache-Control": "no-store"},
            )(ambito, recibir, enviar)
            return
        if identidad is None and "sid" in solicitud.session:
            solicitud.session.clear()
        ambito.setdefault("state", {})["identidad_autenticacion"] = identidad
        normalizado_ruta = ruta.rstrip("/")
        es_publico_autenticacion = (
            normalizado_ruta in {"/api/auth/login", "/api/auth/register"}
            and solicitud.method == "POST"
        )
        es_publico = es_publico_autenticacion or (
            solicitud.method == "GET"
            and (
                normalizado_ruta in {"/api/auth/csrf", "/api/auth/session"}
                or publico_catalogo_ruta(normalizado_ruta)
            )
        )
        if not es_publico and identidad is None:
            await JSONResponse(
                {"detail": SESION_ERROR}, status_code=401, headers={"Cache-Control": "no-store"}
            )(ambito, recibir, enviar)
            return
        es_compartido = normalizado_ruta in {
            "/api/auth/session",
            "/api/auth/logout",
        } or cliente_operacion_ruta(normalizado_ruta)
        if (
            not es_publico
            and not es_compartido
            and identidad is not None
            and not tiene_administrador_rol(identidad)
        ):
            await JSONResponse(
                {"detail": ROL_ERROR}, status_code=403, headers={"Cache-Control": "no-store"}
            )(ambito, recibir, enviar)
            return
        if solicitud.method not in SEGURO_METODOS:
            esperado = solicitud.session.get("csrf")
            proporcionado = solicitud.headers.get("X-CSRF-Token")
            if (
                not isinstance(esperado, str)
                or not proporcionado
                or not compare_digest(esperado.encode("utf-8"), proporcionado.encode("utf-8"))
            ):
                await JSONResponse(
                    {"detail": CSRF_ERROR},
                    status_code=403,
                    headers={"Cache-Control": "no-store"},
                )(ambito, recibir, enviar)
                return

        async def enviar_sin_almacenar(mensaje: Message) -> None:
            # Las cachés compartidas no deben conservar datos protegidos de API ni respuestas CSRF.
            if mensaje["type"] == "http.response.start":
                cabeceras = MutableHeaders(scope=mensaje)
                cabeceras["Cache-Control"] = "no-store"
            await enviar(mensaje)

        await instancia.aplicacion(ambito, recibir, enviar_sin_almacenar)
