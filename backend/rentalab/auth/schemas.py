from datetime import datetime
from typing import Annotated, Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr, StringConstraints

UserRole = Literal["customer", "admin"]
UserName = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=120, pattern=r"^[^\x00]*$"
    ),
]


def normalize_email(value: str) -> str:
    try:
        normalized = validate_email(
            value, check_deliverability=False, test_environment=True
        ).normalized.casefold()
    except EmailNotValidError as error:
        raise ValueError("El correo no es válido") from error
    if len(normalized) > 254:
        raise ValueError("El correo no es válido")
    return normalized


UserEmail = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=3, max_length=254),
    AfterValidator(normalize_email),
    Field(json_schema_extra={"format": "email"}),
]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    name: UserName
    email: UserEmail
    password: Annotated[SecretStr, Field(min_length=8, max_length=1024)]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: UserRole
    active: bool


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    username: Annotated[
        str,
        StringConstraints(
            strict=True, strip_whitespace=True, min_length=1, max_length=254, pattern=r"^[^\x00]*$"
        ),
    ]
    password: Annotated[SecretStr, Field(min_length=1, max_length=1024)]


class AuthSessionRead(BaseModel):
    authenticated: Literal[True] = True
    username: str
    expires_at: datetime
    role: UserRole
    user: UserRead | None


class CsrfTokenRead(BaseModel):
    csrf_token: str


class LogoutRead(BaseModel):
    authenticated: Literal[False] = False
