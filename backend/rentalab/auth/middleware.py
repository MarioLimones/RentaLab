import re
from hmac import compare_digest

from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rentalab.auth.dependencies import ROLE_ERROR, SESSION_ERROR, has_admin_role
from rentalab.auth.service import AuthService
from rentalab.database import is_sqlite_busy
from rentalab.public_catalogue.media import PUBLIC_ASSET_PATHS

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_ERROR = "El token de seguridad no es válido; vuelve a intentarlo"


def public_catalogue_path(path: str) -> bool:
    return (
        path == "/api/public/equipment"
        or path in PUBLIC_ASSET_PATHS
        or re.fullmatch(
            r"/api/public/equipment/[^/]+(?:/availability|/calendar|/reservations)?", path
        )
        is not None
    )


def customer_operation_path(path: str) -> bool:
    return path == "/api/me" or path.startswith("/api/me/")


class AuthGuardMiddleware:
    def __init__(self, app: ASGIApp, auth_service: AuthService) -> None:
        self.app = app
        self.auth_service = auth_service

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not (path == "/api" or path.startswith("/api/")):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        try:
            identity = await run_in_threadpool(
                self.auth_service.find_session, request.session.get("sid")
            )
        except OperationalError as error:
            if not is_sqlite_busy(error):
                raise
            await JSONResponse(
                {"detail": "La base de datos está ocupada; vuelve a intentarlo"},
                status_code=503,
                headers={"Retry-After": "1", "Cache-Control": "no-store"},
            )(scope, receive, send)
            return
        if identity is None and "sid" in request.session:
            request.session.clear()
        scope.setdefault("state", {})["auth_identity"] = identity
        normalized_path = path.rstrip("/")
        is_public_auth = (
            normalized_path in {"/api/auth/login", "/api/auth/register"}
            and request.method == "POST"
        )
        is_public = is_public_auth or (
            request.method == "GET"
            and (
                normalized_path in {"/api/auth/csrf", "/api/auth/session"}
                or public_catalogue_path(normalized_path)
            )
        )
        if not is_public and identity is None:
            await JSONResponse(
                {"detail": SESSION_ERROR}, status_code=401, headers={"Cache-Control": "no-store"}
            )(scope, receive, send)
            return
        is_shared = normalized_path in {
            "/api/auth/session",
            "/api/auth/logout",
        } or customer_operation_path(normalized_path)
        if (
            not is_public
            and not is_shared
            and identity is not None
            and not has_admin_role(identity)
        ):
            await JSONResponse(
                {"detail": ROLE_ERROR}, status_code=403, headers={"Cache-Control": "no-store"}
            )(scope, receive, send)
            return
        if request.method not in SAFE_METHODS:
            expected = request.session.get("csrf")
            provided = request.headers.get("X-CSRF-Token")
            if (
                not isinstance(expected, str)
                or not provided
                or not compare_digest(expected.encode("utf-8"), provided.encode("utf-8"))
            ):
                await JSONResponse(
                    {"detail": CSRF_ERROR},
                    status_code=403,
                    headers={"Cache-Control": "no-store"},
                )(scope, receive, send)
                return

        async def send_no_store(message: Message) -> None:
            # Protected API data and CSRF responses must not be retained by shared caches.
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_no_store)
