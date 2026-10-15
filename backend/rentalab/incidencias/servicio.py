from rentalab.equipo.servicio import EquipoNoEncontrado
from rentalab.incidencias.esquemas import (
    IncidenciaActualizar,
    IncidenciaCrear,
    IncidenciaEstadoCambiar,
    IncidenciaFiltros,
    IncidenciaLectura,
)
from rentalab.incidencias.modelos import Incidencia
from rentalab.incidencias.repositorio import RepositorioIncidencias


class IncidenciaNoEncontrada(Exception):
    pass


class ConflictoIncidencia(Exception):
    pass


PERMITIDOS_TRANSICIONES = {
    "open": frozenset({"in_progress", "resolved"}),
    "in_progress": frozenset({"resolved"}),
    "resolved": frozenset(),
}


class ServicioIncidencias:
    def __init__(instancia, repositorio: RepositorioIncidencias) -> None:
        instancia.repositorio = repositorio

    def obtener(instancia, id_incidencia: int) -> IncidenciaLectura:
        return instancia._lectura(instancia._obtener_incidencia(id_incidencia))

    def listar(instancia, filtros: IncidenciaFiltros) -> list[IncidenciaLectura]:
        if (
            filtros.id_equipo is not None
            and instancia.repositorio.obtener_equipo(filtros.id_equipo) is None
        ):
            raise EquipoNoEncontrado
        return [
            instancia._lectura(incidencia) for incidencia in instancia.repositorio.listar(filtros)
        ]

    def crear(
        instancia, datos: IncidenciaCrear, *, id_usuario_autor: int | None = None
    ) -> IncidenciaLectura:
        with instancia.repositorio.escritura_transaccion():
            if instancia.repositorio.obtener_equipo(datos.id_equipo) is None:
                raise EquipoNoEncontrado
            incidencia = Incidencia(
                **datos.model_dump(),
                estado="open",
                resolucion="",
                id_usuario_autor=id_usuario_autor,
            )
            instancia.repositorio.agregar(incidencia)
            instancia.repositorio.sincronizar()
            respuesta = instancia._lectura(incidencia)
        return respuesta

    def cambiar_estado(
        instancia, id_incidencia: int, datos: IncidenciaEstadoCambiar
    ) -> IncidenciaLectura:
        with instancia.repositorio.escritura_transaccion():
            incidencia = instancia._obtener_incidencia(id_incidencia)
            if datos.estado not in PERMITIDOS_TRANSICIONES[incidencia.estado]:
                raise ConflictoIncidencia(
                    f"No se permite pasar de {incidencia.estado} a {datos.estado}"
                )
            incidencia.estado = datos.estado
            incidencia.resolucion = datos.resolucion or ""
            instancia.repositorio.sincronizar()
            respuesta = instancia._lectura(incidencia)
        return respuesta

    def actualizar(instancia, id_incidencia: int, datos: IncidenciaActualizar) -> IncidenciaLectura:
        # Los cambios de gestión comparten el bloqueo de reservas: una decisión de bloqueo y
        # una reserva no pueden decidir a partir de una disponibilidad anterior sin bloqueo.
        with instancia.repositorio.escritura_transaccion():
            incidencia = instancia._obtener_incidencia(id_incidencia)
            for campo, valor in datos.model_dump(exclude_unset=True).items():
                setattr(incidencia, campo, valor)
            instancia.repositorio.sincronizar()
            respuesta = instancia._lectura(incidencia)
        return respuesta

    def _obtener_incidencia(instancia, id_incidencia: int) -> Incidencia:
        incidencia = instancia.repositorio.obtener(id_incidencia)
        if incidencia is None:
            raise IncidenciaNoEncontrada
        return incidencia

    def _lectura(instancia, incidencia: Incidencia) -> IncidenciaLectura:
        confirmadas_ids = instancia.repositorio.ids_reservas_confirmadas(incidencia.id_equipo)
        return IncidenciaLectura(
            id=incidencia.id,
            id_reserva=incidencia.id_reserva,
            id_usuario_autor=incidencia.id_usuario_autor,
            id_equipo=incidencia.id_equipo,
            titulo=incidencia.titulo,
            descripcion=incidencia.descripcion,
            prioridad=incidencia.prioridad,
            bloqueante=incidencia.bloqueante,
            estado=incidencia.estado,
            resolucion=incidencia.resolucion,
            respuesta_publica=incidencia.respuesta_publica,
            notas_internas=incidencia.notas_internas,
            ids_reservas_confirmadas=confirmadas_ids,
            aviso=(
                "El equipo tiene reservas confirmadas. "
                "La incidencia no las cancela ni las modifica."
                if confirmadas_ids
                else None
            ),
        )
