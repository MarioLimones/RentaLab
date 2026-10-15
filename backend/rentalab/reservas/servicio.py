from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date

from sqlalchemy.exc import IntegrityError

from rentalab.disponibilidad import DisponibilidadServicio
from rentalab.equipo.grupos import activo_producto_unidades, producto_clave
from rentalab.equipo.servicio import EquipoNoEncontrado
from rentalab.reservas.esquemas import (
    CrearReserva,
    DisponibilidadLectura,
    FiltrosReservas,
    IntervaloFechas,
    ReservaEstado,
    ReservaOrigen,
    ReservaPorCodigo,
)
from rentalab.reservas.modelos import (
    ClienteReservaSolicitud,
    Reserva,
    ReservaSolicitudReserva,
)
from rentalab.reservas.repositorio import RepositorioReservas


class ReservaNoEncontrada(Exception):
    pass


class ConflictoReserva(Exception):
    pass


@dataclass(frozen=True)
class ReservaImportacionResultado:
    reserva: Reserva
    creados: bool


class ServicioReservas:
    def __init__(instancia, repositorio: RepositorioReservas) -> None:
        instancia.repositorio = repositorio
        instancia.disponibilidad_servicio = DisponibilidadServicio(repositorio)

    def obtener(instancia, id_reserva: int) -> Reserva:
        reserva = instancia.repositorio.obtener(id_reserva)
        if reserva is None:
            raise ReservaNoEncontrada
        return reserva

    def listar(instancia, filtros: FiltrosReservas) -> Sequence[Reserva]:
        if (
            filtros.id_equipo is not None
            and instancia.repositorio.obtener_equipo(filtros.id_equipo) is None
        ):
            raise EquipoNoEncontrado
        return instancia.repositorio.listar(filtros)

    def disponibilidad(
        instancia, id_equipo: int, fecha_intervalo: IntervaloFechas
    ) -> DisponibilidadLectura:
        return instancia.disponibilidad_servicio.comprobar(id_equipo, fecha_intervalo)

    def crear(instancia, datos: CrearReserva) -> Reserva:
        with instancia._escritura_transaccion():
            reserva = instancia._crear_comprobado(datos)
        return reserva

    def crear_para_cliente(
        instancia,
        datos: CrearReserva,
        *,
        id_usuario_cliente: int,
        hoy: Callable[[], date],
        inicial_estado: ReservaEstado = "confirmed",
        asignar_producto_unidad: bool = False,
        clave_idempotencia: str | None = None,
    ) -> Reserva:
        # La política del cliente y la disponibilidad compartida se evalúan bajo el mismo bloqueo.
        with instancia._escritura_transaccion():
            solicitado = datos
            repetir = instancia._repetir_cliente_solicitud(
                [solicitado], id_usuario_cliente, clave_idempotencia, operacion="single"
            )
            if repetir is not None:
                return repetir[0]
            if datos.fecha_inicio < hoy():
                raise ConflictoReserva("La fecha de inicio no puede ser anterior a hoy")
            try:
                # El cliente del portal elige un producto y la reserva pertenece a una misma
                # unidad física durante todo el intervalo. Las reservas de demostración conservan
                # la unidad solicitada salvo que se active explícitamente la asignación.
                if asignar_producto_unidad:
                    datos = instancia._asignar_producto_unidad(datos)
                reserva = instancia._crear_comprobado(
                    datos, id_usuario_cliente=id_usuario_cliente, origen="portal"
                )
                # La demostración local explícita puede insertar su ejemplo cancelado en esta misma
                # transacción. Las entradas HTTP no aceptan ni proporcionan un estado inicial.
                reserva.estado = inicial_estado
                instancia._registro_cliente_solicitud(
                    [solicitado],
                    [reserva],
                    id_usuario_cliente,
                    clave_idempotencia,
                    operacion="single",
                )
            except ConflictoReserva as error:
                # El cliente puede consultar la disponibilidad sin conocer los
                # motivos de bloqueos internos.
                raise ConflictoReserva(
                    "El equipo no está disponible para esas fechas; "
                    "consulta la disponibilidad y elige otro intervalo"
                ) from error
        return reserva

    def _asignar_producto_unidad(instancia, datos: CrearReserva) -> CrearReserva:
        equipo = instancia.repositorio.obtener_equipo(datos.id_equipo)
        if equipo is None:
            raise EquipoNoEncontrado
        if not equipo.activo:
            raise ConflictoReserva("El equipo está inactivo")
        fecha_intervalo = IntervaloFechas(
            fecha_inicio=datos.fecha_inicio, fecha_fin=datos.fecha_fin
        )
        for unidad in activo_producto_unidades(instancia.repositorio.sesion, equipo):
            if instancia.disponibilidad(unidad.id, fecha_intervalo).disponible:
                return datos.model_copy(update={"id_equipo": unidad.id})
        raise ConflictoReserva("No hay ninguna unidad disponible para todo el intervalo")

    def crear_conjunto_para_cliente(
        instancia,
        datos: Sequence[CrearReserva],
        *,
        id_usuario_cliente: int,
        hoy: Callable[[], date],
        clave_idempotencia: str | None = None,
    ) -> list[Reserva]:
        # Todos los productos comparten el bloqueo de las reservas individuales, de
        # gestión e importadas.
        # Un fallo posterior revierte todas las asignaciones e inserciones anteriores.
        with instancia._escritura_transaccion():
            repetir = instancia._repetir_cliente_solicitud(
                datos, id_usuario_cliente, clave_idempotencia, operacion="batch"
            )
            if repetir is not None:
                return repetir
            negocio_dia = hoy()
            if any(elemento.fecha_inicio < negocio_dia for elemento in datos):
                raise ConflictoReserva("La fecha de inicio no puede ser anterior a hoy")
            productos: set[tuple[str, str]] = set()
            for elemento in datos:
                equipo = instancia.repositorio.obtener_equipo(elemento.id_equipo)
                if equipo is None:
                    raise EquipoNoEncontrado
                clave = producto_clave(equipo)
                if clave in productos:
                    raise ConflictoReserva(
                        "Incluye cada producto una sola vez en la reserva conjunta"
                    )
                productos.add(clave)
            try:
                reservas = [
                    instancia._crear_comprobado(
                        instancia._asignar_producto_unidad(elemento),
                        id_usuario_cliente=id_usuario_cliente,
                        origen="portal",
                    )
                    for elemento in datos
                ]
                instancia._registro_cliente_solicitud(
                    datos, reservas, id_usuario_cliente, clave_idempotencia, operacion="batch"
                )
            except ConflictoReserva as error:
                raise ConflictoReserva(
                    "Uno de los productos no está disponible para esas fechas; "
                    "no se ha creado ninguna reserva. "
                    "Consulta la disponibilidad y elige otro intervalo"
                ) from error
        return reservas

    def _repetir_cliente_solicitud(
        instancia,
        datos: Sequence[CrearReserva],
        id_usuario_cliente: int,
        clave_idempotencia: str | None,
        *,
        operacion: str,
    ) -> list[Reserva] | None:
        if clave_idempotencia is None:
            return None
        anterior = instancia.repositorio.obtener_reserva_solicitud(
            id_usuario_cliente, clave_idempotencia
        )
        if anterior is None:
            return None
        if (
            anterior.operacion != operacion
            or [elemento.id_equipo_solicitado for elemento in anterior.elementos]
            != [elemento.id_equipo for elemento in datos]
            or anterior.fecha_inicio != datos[0].fecha_inicio
            or anterior.fecha_fin != datos[0].fecha_fin
        ):
            raise ConflictoReserva(
                "Esta solicitud de reserva ya se utilizó con otros datos; "
                "inicia una nueva solicitud para cambiar equipo o fechas"
            )
        # La repetición precede a fecha, actividad y disponibilidad actuales, incluso tras cancelar.
        reservas = instancia.repositorio.reservas_para_reserva_solicitud(
            id_usuario_cliente, clave_idempotencia
        )
        if len(reservas) != len(datos):
            raise ReservaNoEncontrada
        return reservas

    def _registro_cliente_solicitud(
        instancia,
        datos: Sequence[CrearReserva],
        reservas: Sequence[Reserva],
        id_usuario_cliente: int,
        clave_idempotencia: str | None,
        *,
        operacion: str,
    ) -> None:
        if clave_idempotencia is None:
            return
        instancia.repositorio.agregar_reserva_solicitud(
            ClienteReservaSolicitud(
                id_usuario_cliente=id_usuario_cliente,
                clave_idempotencia=clave_idempotencia,
                operacion=operacion,
                fecha_inicio=datos[0].fecha_inicio,
                fecha_fin=datos[0].fecha_fin,
                elementos=[
                    ReservaSolicitudReserva(
                        posicion=posicion,
                        id_equipo_solicitado=solicitado.id_equipo,
                        reserva=reserva,
                    )
                    for posicion, (solicitado, reserva) in enumerate(
                        zip(datos, reservas, strict=True)
                    )
                ],
            )
        )

    def crear_desde_codigo(instancia, datos: ReservaPorCodigo) -> ReservaImportacionResultado:
        with instancia._escritura_transaccion():
            existentes = instancia.repositorio.obtener_por_referencia(datos.referencia_externa)
            equipo = instancia.repositorio.obtener_equipo_por_codigo(datos.codigo_equipo)
            if existentes is not None:
                identico = equipo is not None and (
                    existentes.id_equipo == equipo.id
                    and existentes.nombre_cliente == datos.nombre_cliente
                    and existentes.correo_cliente == datos.correo_cliente
                    and existentes.fecha_inicio == datos.fecha_inicio
                    and existentes.fecha_fin == datos.fecha_fin
                )
                if not identico:
                    raise ConflictoReserva(
                        "La referencia externa ya existe con datos distintos; "
                        "no se modifica la reserva."
                    )
                desenlace = ReservaImportacionResultado(existentes, creados=False)
            else:
                if equipo is None:
                    raise EquipoNoEncontrado
                reserva = instancia._crear_comprobado(
                    CrearReserva(
                        id_equipo=equipo.id,
                        **datos.model_dump(exclude={"codigo_equipo"}),
                    ),
                    origen="csv",
                )
                desenlace = ReservaImportacionResultado(reserva, creados=True)
        return desenlace

    def _crear_comprobado(
        instancia,
        datos: CrearReserva,
        *,
        id_usuario_cliente: int | None = None,
        origen: ReservaOrigen = "admin",
    ) -> Reserva:
        disponibilidad = instancia.disponibilidad(
            datos.id_equipo,
            IntervaloFechas(
                fecha_inicio=datos.fecha_inicio,
                fecha_fin=datos.fecha_fin,
            ),
        )
        if not disponibilidad.disponible:
            if disponibilidad.motivo == "equipment_inactive":
                raise ConflictoReserva("El equipo está inactivo")
            if disponibilidad.motivo == "blocking_incident":
                raise ConflictoReserva("El equipo tiene una incidencia bloqueante sin resolver")
            raise ConflictoReserva("El equipo ya tiene una reserva confirmada en ese intervalo")
        if datos.referencia_externa is not None and instancia.repositorio.referencia_existe(
            datos.referencia_externa
        ):
            raise ConflictoReserva("La referencia externa ya está asociada a una reserva")
        reserva = Reserva(
            **datos.model_dump(),
            estado="confirmed",
            id_usuario_cliente=id_usuario_cliente,
            origen=origen,
        )
        instancia.repositorio.agregar(reserva)
        return reserva

    @contextmanager
    def _escritura_transaccion(instancia) -> Iterator[None]:
        try:
            with instancia.repositorio.escritura_transaccion():
                yield
        except IntegrityError as error:
            if getattr(error.orig, "sqlite_errorcode", None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE:
                raise ConflictoReserva(
                    "La referencia externa ya está asociada a una reserva"
                ) from error
            raise

    def cancelar(instancia, id_reserva: int) -> Reserva:
        with instancia.repositorio.escritura_transaccion():
            reserva = instancia.obtener(id_reserva)
            reserva.estado = "cancelled"
        return reserva

    def obtener_para_cliente(instancia, id_reserva: int, id_usuario_cliente: int) -> Reserva:
        reserva = instancia.repositorio.obtener_para_cliente(id_reserva, id_usuario_cliente)
        if reserva is None:
            raise ReservaNoEncontrada
        return reserva

    def listar_para_cliente(instancia, id_usuario_cliente: int) -> Sequence[Reserva]:
        return instancia.repositorio.listar_para_cliente(id_usuario_cliente)

    def cancelar_para_cliente(
        instancia, id_reserva: int, *, id_usuario_cliente: int, hoy: Callable[[], date]
    ) -> Reserva:
        with instancia.repositorio.escritura_transaccion():
            reserva = instancia.obtener_para_cliente(id_reserva, id_usuario_cliente)
            # Cancelar de nuevo devuelve la reserva existente, incluso después del día de inicio.
            if reserva.estado == "cancelled":
                return reserva
            if hoy() >= reserva.fecha_inicio:
                raise ConflictoReserva(
                    "Solo puedes cancelar una reserva antes de su fecha de inicio"
                )
            reserva.estado = "cancelled"
        return reserva
