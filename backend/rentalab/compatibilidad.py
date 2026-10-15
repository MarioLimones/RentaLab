"""Mantiene los contratos JSON existentes al usar nombres internos en español."""

from pydantic import BaseModel, BeforeValidator, ConfigDict

_ALIAS_JSON = {
    "equipo_creados": "equipment_created",
    "reservas_creados": "reservations_created",
    "reservas_existentes": "reservations_existing",
    "omitidas": "skipped",
    "entorno": "environment",
    "url_base_datos": "database_url",
    "interfaz_compilada": "frontend_dist",
    "espera_sqlite_ocupado_ms": "sqlite_busy_timeout_ms",
    "usuario_operador": "operator_username",
    "hash_contrasena_operador": "operator_password_hash",
    "secreto_sesion": "session_secret",
    "vigencia_sesion_segundos": "session_ttl_seconds",
    "puerto": "port",
    "ips_reenviadas_permitidas": "forwarded_allow_ips",
    "nombre": "name",
    "correo": "email",
    "contrasena": "password",
    "rol": "role",
    "referencia": "reference",
    "cuenta_indice": "account_index",
    "codigo_equipo": "equipment_code",
    "arranque_desplazamiento": "start_offset",
    "fin_desplazamiento": "end_offset",
    "canceladas": "cancelled",
    "base_fecha": "base_date",
    "cuentas_creados": "accounts_created",
    "detalle": "detail",
    "estado": "status",
    "hash_contrasena": "password_hash",
    "activo": "active",
    "caduca_en": "expires_at",
    "credencial_version": "credential_version",
    "id_usuario": "user_id",
    "nombre_usuario": "username",
    "autenticado": "authenticated",
    "usuario": "user",
    "codigo": "code",
    "categoria": "category",
    "descripcion": "description",
    "descripcion_publica": "public_description",
    "caracteristicas_tecnicas": "technical_specs",
    "url_imagen": "image_url",
    "linea": "line",
    "valores": "values",
    "referencia_externa": "external_reference",
    "reserva": "reservation",
    "mensaje": "message",
    "aceptadas": "accepted",
    "ya_importadas": "already_imported",
    "rechazadas": "rejected",
    "totales": "totals",
    "filas": "rows",
    "id_equipo": "equipment_id",
    "id_usuario_autor": "author_user_id",
    "id_reserva": "reservation_id",
    "titulo": "title",
    "prioridad": "priority",
    "bloqueante": "blocking",
    "resolucion": "resolution",
    "respuesta_publica": "public_response",
    "notas_internas": "internal_notes",
    "ids_reservas_confirmadas": "confirmed_reservation_ids",
    "aviso": "warning",
    "id_usuario_cliente": "customer_user_id",
    "ids_equipos": "equipment_ids",
    "busqueda": "q",
    "fecha_inicio": "start_date",
    "fecha_fin": "end_date",
    "url_imagen_alternativa": "image_fallback_url",
    "numero_reservas_activas": "active_reservations_count",
    "disponible": "available",
    "reservas": "reservations",
    "intervalos_ocupados": "occupied_ranges",
    "puede_reservar": "can_book",
    "fechas_fin_no_disponibles": "unavailable_end_dates",
    "inicio_reserva": "booking_start",
    "nombre_cliente": "customer_name",
    "correo_cliente": "customer_email",
    "origen": "origin",
    "clave_idempotencia": "idempotency_key",
    "operacion": "operation",
    "elementos": "items",
    "posicion": "position",
    "id_equipo_solicitado": "requested_equipment_id",
    "cliente": "customer",
    "motivo": "reason",
    "ids_reservas_en_conflicto": "conflicting_reservation_ids",
    "creados": "created",
}

_NOMBRES_INTERNOS = {externo: nombre for nombre, externo in _ALIAS_JSON.items()}


def alias_json(nombre: str) -> str:
    return _ALIAS_JSON.get(nombre, nombre)


class ModeloApi(BaseModel):
    model_config = ConfigDict(alias_generator=alias_json, populate_by_name=True)


def entrada_http(modelo: type[ModeloApi]) -> BeforeValidator:
    """Acepta solo las claves públicas sin limitar los constructores internos."""

    def validar(valor: object) -> object:
        if isinstance(valor, dict):
            return modelo.model_validate(valor, by_alias=True, by_name=False)
        return valor

    return BeforeValidator(validar)


def nombre_interno(alias: str) -> str:
    return _NOMBRES_INTERNOS.get(alias, alias)
