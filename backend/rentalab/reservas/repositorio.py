from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rentalab.base_datos import inmediata_transaccion
from rentalab.equipo.modelos import Equipo
from rentalab.incidencias.modelos import Incidencia
from rentalab.reservas.esquemas import FiltrosReservas
from rentalab.reservas.modelos import (
    ClienteReservaSolicitud,
    Reserva,
    ReservaSolicitudReserva,
)


class RepositorioReservas:
    def __init__(instancia, sesion: Session) -> None:
        instancia.sesion = sesion

    def escritura_transaccion(instancia) -> AbstractContextManager[None]:
        return inmediata_transaccion(instancia.sesion)

    def tiene_bloqueante_incidencia(instancia, id_equipo: int) -> bool:
        return (
            instancia.sesion.scalar(
                select(Incidencia.id)
                .where(
                    Incidencia.id_equipo == id_equipo,
                    Incidencia.bloqueante.is_(True),
                    Incidencia.estado.in_(("open", "in_progress")),
                )
                .limit(1)
            )
            is not None
        )

    def obtener_equipo(instancia, id_equipo: int) -> Equipo | None:
        return instancia.sesion.get(Equipo, id_equipo)

    def obtener_equipo_por_codigo(instancia, codigo: str) -> Equipo | None:
        return instancia.sesion.scalar(select(Equipo).where(Equipo.codigo == codigo))

    def obtener_por_referencia(instancia, referencia: str) -> Reserva | None:
        return instancia.sesion.scalar(
            select(Reserva).where(Reserva.referencia_externa == referencia)
        )

    def obtener(instancia, id_reserva: int) -> Reserva | None:
        return instancia.sesion.get(Reserva, id_reserva)

    def obtener_para_cliente(instancia, id_reserva: int, id_usuario_cliente: int) -> Reserva | None:
        return instancia.sesion.scalar(
            select(Reserva).where(
                Reserva.id == id_reserva,
                Reserva.id_usuario_cliente == id_usuario_cliente,
            )
        )

    def obtener_reserva_solicitud(
        instancia, id_usuario_cliente: int, clave_idempotencia: str
    ) -> ClienteReservaSolicitud | None:
        return instancia.sesion.get(
            ClienteReservaSolicitud, (id_usuario_cliente, clave_idempotencia)
        )

    def agregar_reserva_solicitud(instancia, solicitud: ClienteReservaSolicitud) -> None:
        instancia.sesion.add(solicitud)

    def reservas_para_reserva_solicitud(
        instancia, id_usuario_cliente: int, clave_idempotencia: str
    ) -> list[Reserva]:
        return list(
            instancia.sesion.scalars(
                select(Reserva)
                .join(
                    ReservaSolicitudReserva,
                    ReservaSolicitudReserva.id_reserva == Reserva.id,
                )
                .where(
                    ReservaSolicitudReserva.id_usuario_cliente == id_usuario_cliente,
                    ReservaSolicitudReserva.clave_idempotencia == clave_idempotencia,
                    Reserva.id_usuario_cliente == id_usuario_cliente,
                )
                .order_by(ReservaSolicitudReserva.posicion)
            )
        )

    def listar_para_cliente(instancia, id_usuario_cliente: int) -> Sequence[Reserva]:
        return instancia.sesion.scalars(
            select(Reserva)
            .where(Reserva.id_usuario_cliente == id_usuario_cliente)
            .order_by(Reserva.fecha_inicio, Reserva.id)
        ).all()

    def listar(instancia, filtros: FiltrosReservas) -> Sequence[Reserva]:
        sentencia = select(Reserva).order_by(Reserva.fecha_inicio, Reserva.id)
        if filtros.id_equipo is not None:
            sentencia = sentencia.where(Reserva.id_equipo == filtros.id_equipo)
        if filtros.estado is not None:
            sentencia = sentencia.where(Reserva.estado == filtros.estado)
        if filtros.id_usuario_cliente is not None:
            sentencia = sentencia.where(Reserva.id_usuario_cliente == filtros.id_usuario_cliente)
        if filtros.origen is not None:
            sentencia = sentencia.where(Reserva.origen == filtros.origen)
        if filtros.fecha_inicio is not None and filtros.fecha_fin is not None:
            sentencia = sentencia.where(
                Reserva.fecha_inicio < filtros.fecha_fin,
                Reserva.fecha_fin > filtros.fecha_inicio,
            )
        reservas = instancia.sesion.scalars(sentencia).all()
        if filtros.cliente is None:
            return reservas
        # NOCASE de SQLite solo trata ASCII. Como en el catálogo público, casefold permite
        # comparaciones literales Unicode; '%' y '_' nunca se convierten en comodines.
        consulta = filtros.cliente.casefold()
        return [
            elemento
            for elemento in reservas
            if consulta in elemento.nombre_cliente.casefold()
            or consulta in elemento.correo_cliente.casefold()
        ]

    def en_conflicto_ids(
        instancia, id_equipo: int, fecha_inicio: date, fecha_fin: date
    ) -> list[int]:
        return list(
            instancia.sesion.scalars(
                select(Reserva.id)
                .where(
                    Reserva.id_equipo == id_equipo,
                    Reserva.estado == "confirmed",
                    Reserva.fecha_inicio < fecha_fin,
                    Reserva.fecha_fin > fecha_inicio,
                )
                .order_by(Reserva.id)
            )
        )

    def activo_recuentos_por_equipo(
        instancia, ids_equipos: Sequence[int], hoy: date
    ) -> dict[int, int]:
        if not ids_equipos:
            return {}
        # Agrupa en una consulta sin cargar registros privados de reservas ni clientes.
        # Los alquileres usan [inicio, fin): una devolución de hoy ya queda fuera del alquiler.
        return dict(
            instancia.sesion.execute(
                select(Reserva.id_equipo, func.count(Reserva.id))
                .where(
                    Reserva.id_equipo.in_(ids_equipos),
                    Reserva.estado == "confirmed",
                    Reserva.fecha_fin > hoy,
                )
                .group_by(Reserva.id_equipo)
            ).all()
        )

    def intervalos_ocupados(
        instancia, id_equipo: int, fecha_inicio: date, fecha_fin: date
    ) -> list[tuple[date, date]]:
        # Selecciona solo fechas: el calendario no necesita clientes ni identificadores de reserva.
        return [
            (fila.fecha_inicio, fila.fecha_fin)
            for fila in instancia.sesion.execute(
                select(Reserva.fecha_inicio, Reserva.fecha_fin)
                .where(
                    Reserva.id_equipo == id_equipo,
                    Reserva.estado == "confirmed",
                    Reserva.fecha_inicio < fecha_fin,
                    Reserva.fecha_fin > fecha_inicio,
                )
                .order_by(Reserva.fecha_inicio, Reserva.fecha_fin)
            )
        ]

    def activo_fecha_intervalos(
        instancia, ids_equipos: Sequence[int], hoy: date
    ) -> list[tuple[date, date]]:
        if not ids_equipos:
            return []
        # Conserva un intervalo por reserva, incluidas las coincidentes en unidades distintas.
        # Solo se seleccionan fechas: las consultas públicas no cargan registros privados
        # de reservas.
        return [
            (fila.fecha_inicio, fila.fecha_fin)
            for fila in instancia.sesion.execute(
                select(Reserva.fecha_inicio, Reserva.fecha_fin)
                .where(
                    Reserva.id_equipo.in_(ids_equipos),
                    Reserva.estado == "confirmed",
                    Reserva.fecha_fin > hoy,
                )
                .order_by(Reserva.fecha_inicio, Reserva.fecha_fin, Reserva.id)
            )
        ]

    def referencia_existe(instancia, referencia_externa: str) -> bool:
        return (
            instancia.sesion.scalar(
                select(Reserva.id).where(Reserva.referencia_externa == referencia_externa).limit(1)
            )
            is not None
        )

    def agregar(instancia, reserva: Reserva) -> None:
        instancia.sesion.add(reserva)
