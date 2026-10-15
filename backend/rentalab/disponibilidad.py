from rentalab.equipo.servicio import EquipoNoEncontrado
from rentalab.reservas.esquemas import DisponibilidadLectura, IntervaloFechas
from rentalab.reservas.repositorio import RepositorioReservas


class DisponibilidadServicio:
    """Una política de disponibilidad para consultas y todas las vías de creación de reservas."""

    def __init__(instancia, repositorio: RepositorioReservas) -> None:
        instancia.repositorio = repositorio

    def comprobar(
        instancia, id_equipo: int, fecha_intervalo: IntervaloFechas
    ) -> DisponibilidadLectura:
        equipo = instancia.repositorio.obtener_equipo(id_equipo)
        if equipo is None:
            raise EquipoNoEncontrado
        conflictos: list[int] = []
        if not equipo.activo:
            motivo = "equipment_inactive"
        elif instancia.repositorio.tiene_bloqueante_incidencia(id_equipo):
            motivo = "blocking_incident"
        else:
            conflictos = instancia.repositorio.en_conflicto_ids(
                id_equipo, fecha_intervalo.fecha_inicio, fecha_intervalo.fecha_fin
            )
            motivo = "reservation_overlap" if conflictos else None
        return DisponibilidadLectura(
            id_equipo=id_equipo,
            **fecha_intervalo.model_dump(),
            disponible=motivo is None,
            motivo=motivo,
            ids_reservas_en_conflicto=conflictos,
        )
