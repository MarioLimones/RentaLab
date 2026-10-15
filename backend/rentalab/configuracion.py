import base64
import binascii
from pathlib import Path
from typing import Literal

from argon2 import extract_parameters
from argon2.exceptions import InvalidHashError
from argon2.low_level import Type
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROYECTO_RAIZ = Path(__file__).resolve().parents[2]


class Configuracion(BaseSettings):
    model_config = SettingsConfigDict(
        populate_by_name=True,
        env_prefix="RENTALAB_",
        env_file=PROYECTO_RAIZ / ".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    entorno: Literal["development", "test", "production"] = Field(
        validation_alias="RENTALAB_ENVIRONMENT", default="development"
    )
    url_base_datos: str = Field(
        validation_alias="RENTALAB_DATABASE_URL",
        default=f"sqlite:///{(PROYECTO_RAIZ / 'data' / 'rentalab.db').as_posix()}",
    )
    interfaz_compilada: Path | None = Field(validation_alias="RENTALAB_FRONTEND_DIST", default=None)
    espera_sqlite_ocupado_ms: int = Field(
        validation_alias="RENTALAB_SQLITE_BUSY_TIMEOUT_MS", default=5000, ge=0, le=60000
    )
    usuario_operador: str | None = Field(
        validation_alias="RENTALAB_OPERATOR_USERNAME", default=None
    )
    hash_contrasena_operador: SecretStr | None = Field(
        validation_alias="RENTALAB_OPERATOR_PASSWORD_HASH", default=None
    )
    secreto_sesion: SecretStr | None = Field(
        validation_alias="RENTALAB_SESSION_SECRET", default=None
    )
    vigencia_sesion_segundos: int = Field(
        validation_alias="RENTALAB_SESSION_TTL_SECONDS", default=3600, ge=1, le=86400
    )
    puerto: int = Field(validation_alias="RENTALAB_PORT", default=8000, ge=1, le=65535)
    ips_reenviadas_permitidas: str = Field(
        validation_alias="RENTALAB_FORWARDED_ALLOW_IPS",
        default="127.0.0.1",
        min_length=1,
        max_length=1024,
    )

    def exigir_autenticacion(instancia) -> None:
        """
        Valida el acceso a la aplicación sin exigirlo para migraciones o herramientas de
        consola.
        """
        mensaje = "La configuración de acceso está ausente o no es válida"
        if (
            instancia.secreto_sesion is None
            or len(instancia.secreto_sesion.get_secret_value().strip()) < 32
        ):
            raise ValueError(mensaje)
        heredado_nombre_usuario = instancia.usuario_operador or ""
        heredado_hash = (
            instancia.hash_contrasena_operador.get_secret_value()
            if instancia.hash_contrasena_operador is not None
            else ""
        )
        if not heredado_nombre_usuario and not heredado_hash:
            return
        if (
            not heredado_nombre_usuario.strip()
            or len(heredado_nombre_usuario) > 120
            or "\x00" in heredado_nombre_usuario
            or not heredado_hash
        ):
            raise ValueError(mensaje)
        try:
            codificado_hash = heredado_hash
            parametros = extract_parameters(codificado_hash)
            # extract_parameters analiza los ajustes, pero no valida la sal ni el
            # resumen codificados.
            for componente in codificado_hash.split("$")[-2:]:
                decodificado = base64.b64decode(
                    componente + "=" * (-len(componente) % 4), validate=True
                )
                if base64.b64encode(decodificado).decode("ascii").rstrip("=") != componente:
                    raise ValueError
        except (InvalidHashError, ValueError, TypeError, binascii.Error):
            raise ValueError(mensaje) from None
        if (
            parametros.type is not Type.ID
            or parametros.version != 19
            or parametros.salt_len < 8
            or parametros.hash_len < 16
            or parametros.parallelism < 1
            or parametros.time_cost < 1
            or parametros.memory_cost < 8 * parametros.parallelism
        ):
            raise ValueError(mensaje)
