from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager

from sqlalchemy import select
from sqlalchemy.orm import Session

from rentalab.base_datos import inmediata_transaccion
from rentalab.equipo.modelos import Equipo
from rentalab.incidencias.esquemas import IncidenciaFiltros
from rentalab.incidencias.modelos import Incidencia
from rentalab.reservas.modelos import Reserva


class RepositorioIncidencias:
    def __init__(instancia, sesion: Session) -> None:
        instancia.sesion = sesion

    def escritura_transaccion(instancia) -> AbstractContextManager[None]:
        return inmediata_transaccion(instancia.sesion)

    def obtener_equipo(instancia, id_equipo: int) -> Equipo | None:
        return instancia.sesion.get(Equipo, id_equipo)

    def obtener(instancia, id_incidencia: int) -> Incidencia | None:
        return instancia.sesion.get(Incidencia, id_incidencia)

    def obtener_propia_reserva(instancia, id_reserva: int, id_usuario: int) -> Reserva | None:
        return instancia.sesion.scalar(
            select(Reserva).where(
                Reserva.id == id_reserva, Reserva.id_usuario_cliente == id_usuario
            )
        )

    def obtener_cliente_incidencia(
        instancia, id_incidencia: int, id_usuario: int
    ) -> Incidencia | None:
        return instancia.sesion.scalar(
            instancia._cliente_incidencias(id_usuario).where(Incidencia.id == id_incidencia)
        )

    def listar_cliente_incidencias(instancia, id_usuario: int) -> Sequence[Incidencia]:
        return instancia.sesion.scalars(
            instancia._cliente_incidencias(id_usuario).order_by(Incidencia.id)
        ).all()

    @staticmethod
    def _cliente_incidencias(id_usuario: int):
        # La autoría por sí sola no permite ver reservas sin propietario ni de otros clientes.
        return (
            select(Incidencia)
            .join(Reserva, Incidencia.id_reserva == Reserva.id)
            .where(
                Incidencia.id_usuario_autor == id_usuario, Reserva.id_usuario_cliente == id_usuario
            )
        )

    def listar(instancia, filtros: IncidenciaFiltros) -> Sequence[Incidencia]:
        sentencia = select(Incidencia).order_by(Incidencia.id)
        if filtros.id_equipo is not None:
            sentencia = sentencia.where(Incidencia.id_equipo == filtros.id_equipo)
        if filtros.estado is not None:
            sentencia = sentencia.where(Incidencia.estado == filtros.estado)
        if filtros.prioridad is not None:
            sentencia = sentencia.where(Incidencia.prioridad == filtros.prioridad)
        if filtros.bloqueante is not None:
            sentencia = sentencia.where(Incidencia.bloqueante == filtros.bloqueante)
        return instancia.sesion.scalars(sentencia).all()

    def ids_reservas_confirmadas(instancia, id_equipo: int) -> list[int]:
        return list(
            instancia.sesion.scalars(
                select(Reserva.id)
                .where(Reserva.id_equipo == id_equipo, Reserva.estado == "confirmed")
                .order_by(Reserva.id)
            )
        )

    def agregar(instancia, incidencia: Incidencia) -> None:
        instancia.sesion.add(incidencia)

    def sincronizar(instancia) -> None:
        instancia.sesion.flush()
