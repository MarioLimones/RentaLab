import secrets
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request

from rentalab.autenticacion.dependencias import ActualUsuario
from rentalab.autenticacion.esquemas import (
    AutenticacionSesionLectura,
    CsrfTokenLectura,
    LecturaCierreSesion,
    LecturaUsuario,
    SolicitudAcceso,
    SolicitudRegistro,
)
from rentalab.autenticacion.servicio import DuplicadoUsuarioCorreo, ServicioAutenticacion
from rentalab.compatibilidad import entrada_http
from rentalab.respuestas_http import RespuestaError

enrutador = APIRouter(prefix="/api/auth", tags=["Acceso"])


@enrutador.get(
    "/session",
    response_model=AutenticacionSesionLectura,
    summary="Consultar la sesión actual",
    responses={401: {"model": RespuestaError, "description": "Sesión ausente o caducada"}},
)
def actual_sesion(identidad: ActualUsuario) -> AutenticacionSesionLectura:
    return identidad.a_respuesta()


@enrutador.get(
    "/csrf", response_model=CsrfTokenLectura, summary="Obtener el token CSRF de la sesión"
)
def csrf_token(solicitud: Request) -> CsrfTokenLectura:
    token = solicitud.session.get("csrf")
    if not isinstance(token, str):
        token = secrets.token_hex(32)
        solicitud.session["csrf"] = token
    return CsrfTokenLectura(csrf_token=token)


@enrutador.post(
    "/login",
    response_model=AutenticacionSesionLectura,
    summary="Iniciar sesión de usuario o del operador de transición",
    responses={
        401: {"model": RespuestaError, "description": "Credenciales incorrectas"},
        403: {"model": RespuestaError, "description": "Token CSRF ausente o inválido"},
    },
)
def iniciar_sesion(
    datos: Annotated[SolicitudAcceso, entrada_http(SolicitudAcceso)], solicitud: Request
) -> AutenticacionSesionLectura:
    servicio: ServicioAutenticacion = solicitud.app.state.autenticacion_servicio
    identidad = servicio.iniciar_sesion(
        datos.nombre_usuario, datos.contrasena.get_secret_value(), solicitud.session.get("sid")
    )
    if identidad is None:
        raise HTTPException(status_code=401, detail="El usuario o la contraseña no son correctos")
    solicitud.session.clear()
    solicitud.session.update({"sid": identidad.id, "csrf": secrets.token_hex(32)})
    return identidad.a_respuesta()


@enrutador.post(
    "/register",
    status_code=201,
    response_model=LecturaUsuario,
    summary="Registrar un cliente sin iniciar sesión automáticamente",
    responses={
        403: {"model": RespuestaError, "description": "Token CSRF ausente o inválido"},
        409: {"model": RespuestaError, "description": "Correo ya registrado"},
    },
)
def registrar(
    datos: Annotated[SolicitudRegistro, entrada_http(SolicitudRegistro)], solicitud: Request
) -> LecturaUsuario:
    servicio: ServicioAutenticacion = solicitud.app.state.autenticacion_servicio
    try:
        return servicio.registrar(datos)
    except DuplicadoUsuarioCorreo as error:
        raise HTTPException(
            status_code=409, detail="Ya existe un usuario con ese correo"
        ) from error


@enrutador.post(
    "/logout",
    response_model=LecturaCierreSesion,
    summary="Cerrar y revocar la sesión actual",
    responses={
        401: {"model": RespuestaError, "description": "Sesión ausente o caducada"},
        403: {"model": RespuestaError, "description": "Token CSRF ausente o inválido"},
    },
)
def cerrar_sesion(solicitud: Request, identidad: ActualUsuario) -> LecturaCierreSesion:
    servicio: ServicioAutenticacion = solicitud.app.state.autenticacion_servicio
    servicio.revocar_sesion(identidad.id)
    solicitud.session.clear()
    return LecturaCierreSesion()
