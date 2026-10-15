import secrets

from fastapi import APIRouter, HTTPException, Request

from rentalab.auth.dependencies import CurrentUser
from rentalab.auth.schemas import (
    AuthSessionRead,
    CsrfTokenRead,
    LoginRequest,
    LogoutRead,
    RegisterRequest,
    UserRead,
)
from rentalab.auth.service import AuthService, DuplicateUserEmail
from rentalab.http import ErrorResponse

router = APIRouter(prefix="/api/auth", tags=["Acceso"])


@router.get(
    "/session",
    response_model=AuthSessionRead,
    summary="Consultar la sesión actual",
    responses={401: {"model": ErrorResponse, "description": "Sesión ausente o caducada"}},
)
def current_session(identity: CurrentUser) -> AuthSessionRead:
    return identity.to_response()


@router.get("/csrf", response_model=CsrfTokenRead, summary="Obtener el token CSRF de la sesión")
def csrf_token(request: Request) -> CsrfTokenRead:
    token = request.session.get("csrf")
    if not isinstance(token, str):
        token = secrets.token_hex(32)
        request.session["csrf"] = token
    return CsrfTokenRead(csrf_token=token)


@router.post(
    "/login",
    response_model=AuthSessionRead,
    summary="Iniciar sesión de usuario o del operador de transición",
    responses={
        401: {"model": ErrorResponse, "description": "Credenciales incorrectas"},
        403: {"model": ErrorResponse, "description": "Token CSRF ausente o inválido"},
    },
)
def login(data: LoginRequest, request: Request) -> AuthSessionRead:
    service: AuthService = request.app.state.auth_service
    identity = service.login(
        data.username, data.password.get_secret_value(), request.session.get("sid")
    )
    if identity is None:
        raise HTTPException(status_code=401, detail="El usuario o la contraseña no son correctos")
    request.session.clear()
    request.session.update({"sid": identity.id, "csrf": secrets.token_hex(32)})
    return identity.to_response()


@router.post(
    "/register",
    status_code=201,
    response_model=UserRead,
    summary="Registrar un cliente sin iniciar sesión automáticamente",
    responses={
        403: {"model": ErrorResponse, "description": "Token CSRF ausente o inválido"},
        409: {"model": ErrorResponse, "description": "Correo ya registrado"},
    },
)
def register(data: RegisterRequest, request: Request) -> UserRead:
    service: AuthService = request.app.state.auth_service
    try:
        return service.register(data)
    except DuplicateUserEmail as error:
        raise HTTPException(
            status_code=409, detail="Ya existe un usuario con ese correo"
        ) from error


@router.post(
    "/logout",
    response_model=LogoutRead,
    summary="Cerrar y revocar la sesión actual",
    responses={
        401: {"model": ErrorResponse, "description": "Sesión ausente o caducada"},
        403: {"model": ErrorResponse, "description": "Token CSRF ausente o inválido"},
    },
)
def logout(request: Request, identity: CurrentUser) -> LogoutRead:
    service: AuthService = request.app.state.auth_service
    service.revoke_session(identity.id)
    request.session.clear()
    return LogoutRead()
