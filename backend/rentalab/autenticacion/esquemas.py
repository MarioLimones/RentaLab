from datetime import datetime
from typing import Annotated, Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, ConfigDict, Field, SecretStr, StringConstraints

from rentalab.compatibilidad import ModeloApi

RolUsuario = Literal["customer", "admin"]
UsuarioNombre = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=120, pattern=r"^[^\x00]*$"
    ),
]


def normalizar_correo(valor: str) -> str:
    try:
        normalizado = validate_email(
            valor, check_deliverability=False, test_environment=True
        ).normalized.casefold()
    except EmailNotValidError as error:
        raise ValueError("El correo no es válido") from error
    if len(normalizado) > 254:
        raise ValueError("El correo no es válido")
    return normalizado


UsuarioCorreo = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=3, max_length=254),
    AfterValidator(normalizar_correo),
    Field(json_schema_extra={"format": "email"}),
]


class SolicitudRegistro(ModeloApi):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    nombre: UsuarioNombre
    correo: UsuarioCorreo
    contrasena: Annotated[SecretStr, Field(min_length=8, max_length=1024)]


class LecturaUsuario(ModeloApi):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    correo: str
    rol: RolUsuario
    activo: bool


class SolicitudAcceso(ModeloApi):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    nombre_usuario: Annotated[
        str,
        StringConstraints(
            strict=True, strip_whitespace=True, min_length=1, max_length=254, pattern=r"^[^\x00]*$"
        ),
    ]
    contrasena: Annotated[SecretStr, Field(min_length=1, max_length=1024)]


class AutenticacionSesionLectura(ModeloApi):
    autenticado: Literal[True] = True
    nombre_usuario: str
    caduca_en: datetime
    rol: RolUsuario
    usuario: LecturaUsuario | None


class CsrfTokenLectura(ModeloApi):
    csrf_token: str


class LecturaCierreSesion(ModeloApi):
    autenticado: Literal[False] = False
