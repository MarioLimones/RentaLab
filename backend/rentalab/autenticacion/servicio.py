import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from hmac import compare_digest
from typing import cast

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from rentalab.autenticacion.esquemas import (
    AutenticacionSesionLectura,
    LecturaUsuario,
    RolUsuario,
    SolicitudRegistro,
    normalizar_correo,
)
from rentalab.autenticacion.modelos import SesionAutenticacion, Usuario
from rentalab.base_datos import inmediata_transaccion
from rentalab.configuracion import Configuracion


def actual_marca_temporal() -> int:
    return int(time.time())


def usuario_credencial_version(usuario: Usuario) -> str:
    # Los roles y perfiles se consultan de nuevo; cambiar la contraseña revoca las sesiones.
    return hashlib.sha256(
        json.dumps([usuario.id, usuario.hash_contrasena]).encode("utf-8")
    ).hexdigest()


class DuplicadoUsuarioCorreo(Exception):
    pass


@dataclass(frozen=True)
class IdentidadSesion:
    id: str
    nombre_usuario: str
    caduca_en: int
    id_usuario: int | None = None
    nombre: str | None = None
    correo: str | None = None
    rol: RolUsuario = "admin"
    activo: bool = True

    def a_respuesta(instancia) -> AutenticacionSesionLectura:
        usuario = None
        if instancia.id_usuario is not None:
            assert instancia.nombre is not None and instancia.correo is not None
            usuario = LecturaUsuario(
                id=instancia.id_usuario,
                nombre=instancia.nombre,
                correo=instancia.correo,
                rol=instancia.rol,
                activo=instancia.activo,
            )
        return AutenticacionSesionLectura(
            nombre_usuario=instancia.nombre_usuario,
            caduca_en=datetime.fromtimestamp(instancia.caduca_en, tz=UTC),
            rol=instancia.rol,
            usuario=usuario,
        )


class ServicioAutenticacion:
    def __init__(
        instancia, ajustes: Configuracion, fabrica_sesiones: sessionmaker[Session]
    ) -> None:
        instancia.ajustes = ajustes
        instancia.fabrica_sesiones = fabrica_sesiones
        instancia.nombre_usuario = (ajustes.usuario_operador or "").strip()
        instancia.hash_contrasena = (
            ajustes.hash_contrasena_operador.get_secret_value()
            if ajustes.hash_contrasena_operador is not None
            and ajustes.hash_contrasena_operador.get_secret_value()
            else None
        )
        # Conserva la huella exacta de 0005 y las sesiones del operador heredado.
        instancia.credencial_version = hashlib.sha256(
            json.dumps([instancia.nombre_usuario, instancia.hash_contrasena]).encode("utf-8")
        ).hexdigest()
        instancia.calculador_hash = PasswordHasher()
        try:
            instancia.heredado_correo = (
                normalizar_correo(instancia.nombre_usuario) if instancia.hash_contrasena else None
            )
        except ValueError:
            instancia.heredado_correo = None
        # Las direcciones desconocidas también ejecutan una verificación costosa.
        instancia.hash_ficticio = instancia.hash_contrasena or instancia.calculador_hash.hash(
            secrets.token_urlsafe(32)
        )

    def identidad(
        instancia, registro: SesionAutenticacion, usuario: Usuario | None
    ) -> IdentidadSesion:
        if usuario is None:
            return IdentidadSesion(registro.id, instancia.nombre_usuario, registro.caduca_en)
        return IdentidadSesion(
            registro.id,
            usuario.correo,
            registro.caduca_en,
            usuario.id,
            usuario.nombre,
            usuario.correo,
            cast(RolUsuario, usuario.rol),
            usuario.activo,
        )

    def buscar_sesion(instancia, sesion_id: object) -> IdentidadSesion | None:
        if (
            not isinstance(sesion_id, str)
            or len(sesion_id) != 64
            or any(caracter not in "0123456789abcdef" for caracter in sesion_id)
        ):
            return None
        with instancia.fabrica_sesiones() as base_datos_sesion:
            registro = base_datos_sesion.get(SesionAutenticacion, sesion_id)
            if registro is None or registro.caduca_en <= actual_marca_temporal():
                return None
            usuario = None
            version = instancia.credencial_version
            if registro.id_usuario is not None:
                usuario = base_datos_sesion.get(Usuario, registro.id_usuario)
                if (
                    usuario is None
                    or not usuario.activo
                    or usuario.rol not in {"admin", "customer"}
                ):
                    return None
                version = usuario_credencial_version(usuario)
            elif instancia.hash_contrasena is None:
                return None
            if not compare_digest(registro.credencial_version, version):
                return None
            return instancia.identidad(registro, usuario)

    def iniciar_sesion(
        instancia, nombre_usuario: str, contrasena: str, anterior_id: object
    ) -> IdentidadSesion | None:
        try:
            correo = normalizar_correo(nombre_usuario)
        except ValueError:
            correo = ""
        with instancia.fabrica_sesiones() as base_datos_sesion:
            usuario = base_datos_sesion.scalar(select(Usuario).where(Usuario.correo == correo))
            # El operador heredado explícito conserva la prioridad durante la migración.
            heredado = instancia.hash_contrasena is not None and compare_digest(
                nombre_usuario.encode("utf-8"), instancia.nombre_usuario.encode("utf-8")
            )
            hash_contrasena = (
                instancia.hash_contrasena
                if heredado
                else usuario.hash_contrasena
                if usuario
                else instancia.hash_ficticio
            )
            assert hash_contrasena is not None
            try:
                coincide = instancia.calculador_hash.verify(hash_contrasena, contrasena)
            except (VerificationError, InvalidHashError):
                coincide = False
            if not coincide or (not heredado and (usuario is None or not usuario.activo)):
                return None
            id_usuario = None if heredado else usuario.id
            version = (
                instancia.credencial_version if heredado else usuario_credencial_version(usuario)
            )
        ahora = actual_marca_temporal()
        with instancia.fabrica_sesiones() as base_datos_sesion:
            with inmediata_transaccion(base_datos_sesion):
                # Vuelve a comprobar las credenciales bajo bloqueo de escritura
                # antes de emitir la sesión.
                usuario = (
                    base_datos_sesion.get(Usuario, id_usuario) if id_usuario is not None else None
                )
                if id_usuario is not None and (
                    usuario is None
                    or not usuario.activo
                    or not compare_digest(usuario_credencial_version(usuario), version)
                ):
                    return None
                base_datos_sesion.execute(
                    delete(SesionAutenticacion).where(SesionAutenticacion.caduca_en <= ahora)
                )
                if isinstance(anterior_id, str):
                    base_datos_sesion.execute(
                        delete(SesionAutenticacion).where(SesionAutenticacion.id == anterior_id)
                    )
                registro = SesionAutenticacion(
                    id=secrets.token_hex(32),
                    caduca_en=ahora + instancia.ajustes.vigencia_sesion_segundos,
                    credencial_version=version,
                    id_usuario=id_usuario,
                )
                base_datos_sesion.add(registro)
                return instancia.identidad(registro, usuario)

    def registrar(
        instancia, datos: SolicitudRegistro, *, rol: RolUsuario = "customer"
    ) -> LecturaUsuario:
        # Un operador heredado con nombre de correo no debe ocultar una cuenta recién registrada.
        if datos.correo == instancia.heredado_correo:
            raise DuplicadoUsuarioCorreo
        hash_contrasena = instancia.calculador_hash.hash(datos.contrasena.get_secret_value())
        try:
            with instancia.fabrica_sesiones() as base_datos_sesion:
                with inmediata_transaccion(base_datos_sesion):
                    if base_datos_sesion.scalar(
                        select(Usuario.id).where(Usuario.correo == datos.correo)
                    ):
                        raise DuplicadoUsuarioCorreo
                    usuario = Usuario(
                        nombre=datos.nombre,
                        correo=datos.correo,
                        hash_contrasena=hash_contrasena,
                        rol=rol,
                        activo=True,
                    )
                    base_datos_sesion.add(usuario)
                    base_datos_sesion.flush()
                    resultado = LecturaUsuario.model_validate(usuario)
                return resultado
        except IntegrityError as error:
            if "UNIQUE constraint failed: users.email" in str(error.orig):
                raise DuplicadoUsuarioCorreo from error
            raise

    def revocar_sesion(instancia, sesion_id: str) -> None:
        with instancia.fabrica_sesiones() as base_datos_sesion:
            with inmediata_transaccion(base_datos_sesion):
                base_datos_sesion.execute(
                    delete(SesionAutenticacion).where(SesionAutenticacion.id == sesion_id)
                )
