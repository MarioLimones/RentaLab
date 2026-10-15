from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from rentalab.auth.middleware import customer_operation_path, public_catalogue_path


def add_auth_openapi(application: FastAPI) -> None:
    def openapi() -> dict:
        if application.openapi_schema is not None:
            return application.openapi_schema
        schema = get_openapi(
            title=application.title,
            version=application.version,
            description=application.description,
            routes=application.routes,
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {}).update(
            {
                "SessionCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "rentalab_session",
                    "description": (
                        "Cookie HttpOnly firmada; requiere sesión vigente para datos privados."
                    ),
                },
                "CSRFToken": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-CSRF-Token",
                    "description": (
                        "Obtener /api/auth/csrf con la misma cookie; renovar después del acceso."
                    ),
                },
            }
        )
        for path, operations in schema["paths"].items():
            for method, operation in operations.items():
                if method not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    continue
                if path.startswith("/api/"):
                    operation.setdefault("responses", {}).setdefault(
                        "503",
                        {
                            "description": (
                                "SQLite temporalmente ocupada; reintentar de forma explícita"
                            ),
                            "headers": {
                                "Retry-After": {
                                    "schema": {"type": "integer"},
                                    "description": "Segundos antes de volver a intentarlo",
                                }
                            },
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    )
                public_catalogue = method == "get" and (
                    public_catalogue_path(path.replace("{equipment_id}", "1"))
                )
                if path in {"/health", "/api/auth/csrf"} or public_catalogue:
                    operation["security"] = []
                    continue
                unsafe = method not in {"get", "head", "options"}
                anonymous_auth = path in {"/api/auth/login", "/api/auth/register"}
                requirements = {} if anonymous_auth else {"SessionCookie": []}
                if unsafe:
                    requirements["CSRFToken"] = []
                operation["security"] = [requirements]
                responses = operation.setdefault("responses", {})
                if path != "/api/auth/register":
                    responses.setdefault(
                        "401",
                        {
                            "description": "Sesión ausente o caducada",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    )
                customer_operation = customer_operation_path(path)
                admin_only = (
                    not anonymous_auth
                    and not customer_operation
                    and not path.startswith("/api/auth/")
                )
                if admin_only:
                    operation["description"] = (
                        operation.get("description", "") + "\n\nRequiere el rol admin vigente."
                    ).strip()
                if customer_operation:
                    operation["description"] = (
                        operation.get("description", "")
                        + "\n\nSólo cliente activo; recursos propios según la sesión."
                    ).strip()
                if unsafe or admin_only or customer_operation:
                    responses.setdefault(
                        "403",
                        {
                            "description": "Rol insuficiente o token CSRF ausente o inválido",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    )
        application.openapi_schema = schema
        return schema

    application.openapi = openapi
