from typing import Annotated

from fastapi import Depends, HTTPException, Request

from rentalab.autenticacion.servicio import IdentidadSesion

SESION_ERROR = "La sesión no es válida o ha caducado"
ROL_ERROR = "No tienes permisos para realizar esta operación"


def tiene_administrador_rol(identidad: IdentidadSesion) -> bool:
    return identidad.activo and identidad.rol == "admin"


def obtener_actual_usuario(solicitud: Request) -> IdentidadSesion:
    identidad: IdentidadSesion | None = getattr(solicitud.state, "identidad_autenticacion", None)
    if identidad is None:
        raise HTTPException(status_code=401, detail=SESION_ERROR)
    return identidad


ActualUsuario = Annotated[IdentidadSesion, Depends(obtener_actual_usuario)]


def exigir_administrador(identidad: ActualUsuario) -> IdentidadSesion:
    if not tiene_administrador_rol(identidad):
        raise HTTPException(status_code=403, detail=ROL_ERROR)
    return identidad


AdministradorUsuario = Annotated[IdentidadSesion, Depends(exigir_administrador)]


def exigir_cliente(identidad: ActualUsuario) -> IdentidadSesion:
    if not identidad.activo or identidad.rol != "customer" or identidad.id_usuario is None:
        raise HTTPException(status_code=403, detail=ROL_ERROR)
    return identidad


ClienteUsuario = Annotated[IdentidadSesion, Depends(exigir_cliente)]
