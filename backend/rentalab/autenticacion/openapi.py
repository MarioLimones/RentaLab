from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from rentalab.autenticacion.intermediario import cliente_operacion_ruta, publico_catalogo_ruta


def agregar_autenticacion_openapi(aplicacion: FastAPI) -> None:
    def openapi() -> dict:
        if aplicacion.openapi_schema is not None:
            return aplicacion.openapi_schema
        esquema = get_openapi(
            title=aplicacion.title,
            version=aplicacion.version,
            description=aplicacion.description,
            routes=aplicacion.routes,
        )
        esquema.setdefault("components", {}).setdefault("securitySchemes", {}).update(
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
        for ruta, operaciones in esquema["paths"].items():
            for metodo, operacion in operaciones.items():
                if metodo not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    continue
                if ruta.startswith("/api/"):
                    operacion.setdefault("responses", {}).setdefault(
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
                                    "schema": {"$ref": "#/components/schemas/RespuestaError"}
                                }
                            },
                        },
                    )
                catalogo_publico = metodo == "get" and (
                    publico_catalogo_ruta(ruta.replace("{equipment_id}", "1"))
                )
                if ruta in {"/health", "/api/auth/csrf"} or catalogo_publico:
                    operacion["security"] = []
                    continue
                inseguro = metodo not in {"get", "head", "options"}
                anonimo_autenticacion = ruta in {"/api/auth/login", "/api/auth/register"}
                requisitos = {} if anonimo_autenticacion else {"SessionCookie": []}
                if inseguro:
                    requisitos["CSRFToken"] = []
                operacion["security"] = [requisitos]
                respuestas = operacion.setdefault("responses", {})
                if ruta != "/api/auth/register":
                    respuestas.setdefault(
                        "401",
                        {
                            "description": "Sesión ausente o caducada",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/RespuestaError"}
                                }
                            },
                        },
                    )
                cliente_operacion = cliente_operacion_ruta(ruta)
                administrador_solo = (
                    not anonimo_autenticacion
                    and not cliente_operacion
                    and not ruta.startswith("/api/auth/")
                )
                if administrador_solo:
                    operacion["description"] = (
                        operacion.get("description", "") + "\n\nRequiere el rol admin vigente."
                    ).strip()
                if cliente_operacion:
                    operacion["description"] = (
                        operacion.get("description", "")
                        + "\n\nSólo cliente activo; recursos propios según la sesión."
                    ).strip()
                if inseguro or administrador_solo or cliente_operacion:
                    respuestas.setdefault(
                        "403",
                        {
                            "description": "Rol insuficiente o token CSRF ausente o inválido",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/RespuestaError"}
                                }
                            },
                        },
                    )
        aplicacion.openapi_schema = esquema
        return esquema

    aplicacion.openapi = openapi
