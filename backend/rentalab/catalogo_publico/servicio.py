from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from rentalab.catalogo_publico.esquemas import (
    PublicoCalendarioConsulta,
    PublicoCalendarioLectura,
    PublicoCatalogoFiltros,
    PublicoDisponibilidadLectura,
    PublicoEquipoLectura,
    PublicoFechaIntervalo,
    PublicoReservasLectura,
)
from rentalab.disponibilidad import DisponibilidadServicio
from rentalab.equipo.grupos import activo_producto_unidades, producto_clave
from rentalab.equipo.modelos import Equipo
from rentalab.equipo.servicio import EquipoNoEncontrado
from rentalab.reloj import HoyProveedor, madrid_hoy
from rentalab.reservas.esquemas import IntervaloFechas
from rentalab.reservas.repositorio import RepositorioReservas

IMAGEN_ALTERNATIVA_URL = "/api/public/images/equipment-placeholder.svg"


def publico_equipo(equipo: Equipo, numero_reservas_activas: int) -> PublicoEquipoLectura:
    # La asignación explícita de campos también protege las consultas administrativas a la API
    # pública.
    return PublicoEquipoLectura(
        id=equipo.id,
        nombre=equipo.nombre,
        categoria=equipo.categoria,
        descripcion_publica=equipo.descripcion_publica,
        caracteristicas_tecnicas=equipo.caracteristicas_tecnicas,
        url_imagen=equipo.url_imagen,
        url_imagen_alternativa=IMAGEN_ALTERNATIVA_URL,
        numero_reservas_activas=numero_reservas_activas,
    )


class ServicioCatalogoPublico:
    def __init__(instancia, sesion: Session, hoy: HoyProveedor = madrid_hoy) -> None:
        instancia.sesion = sesion
        instancia.hoy = hoy
        instancia.reservas = RepositorioReservas(sesion)
        instancia.disponibilidad = DisponibilidadServicio(instancia.reservas)

    def listar(instancia, filtros: PublicoCatalogoFiltros) -> list[PublicoEquipoLectura]:
        equipo = instancia.sesion.scalars(
            select(Equipo).where(Equipo.activo.is_(True)).order_by(Equipo.id)
        ).all()
        recuentos = instancia.reservas.activo_recuentos_por_equipo(
            [elemento.id for elemento in equipo], instancia.hoy()
        )
        consulta = (filtros.busqueda or "").casefold()
        categoria = (filtros.categoria or "").casefold()
        # NOCASE de SQLite solo cubre ASCII. Casefold conserva nombres y categorías Unicode,
        # y las comparaciones literales de Python no convierten % ni _ en comodines SQL.
        productos: dict[tuple[str, str], Equipo] = {}
        producto_recuentos: dict[tuple[str, str], int] = {}
        for elemento in equipo:
            clave = producto_clave(elemento)
            productos.setdefault(clave, elemento)
            producto_recuentos[clave] = producto_recuentos.get(clave, 0) + recuentos.get(
                elemento.id, 0
            )
        return [
            publico_equipo(elemento, producto_recuentos[producto_clave(elemento)])
            for elemento in sorted(
                productos.values(), key=lambda elemento: (elemento.nombre, elemento.id)
            )
            if (not consulta or consulta in elemento.nombre.casefold())
            and (not categoria or categoria == elemento.categoria.casefold())
        ]

    def obtener_activo(instancia, id_equipo: int) -> Equipo:
        equipo = instancia.sesion.get(Equipo, id_equipo)
        if equipo is None or not equipo.activo:
            raise EquipoNoEncontrado
        return equipo

    def obtener(instancia, id_equipo: int) -> PublicoEquipoLectura:
        equipo = instancia.obtener_activo(id_equipo)
        unidades = activo_producto_unidades(instancia.sesion, equipo)
        recuentos = instancia.reservas.activo_recuentos_por_equipo(
            [unidad.id for unidad in unidades], instancia.hoy()
        )
        return publico_equipo(unidades[0], sum(recuentos.values()))

    def comprobar_disponibilidad(
        instancia, id_equipo: int, fechas: PublicoFechaIntervalo
    ) -> PublicoDisponibilidadLectura:
        equipo = instancia.obtener_activo(id_equipo)
        fecha_intervalo = fechas.a_fecha_intervalo()
        if fecha_intervalo is None:
            return PublicoDisponibilidadLectura(
                id_equipo=id_equipo,
                fecha_inicio=None,
                fecha_fin=None,
                disponible=None,
                estado="select_dates",
            )
        disponible = any(
            instancia.disponibilidad.comprobar(unidad.id, fecha_intervalo).disponible
            for unidad in activo_producto_unidades(instancia.sesion, equipo)
        )
        # Los motivos, detalles de incidencias e identificadores de reserva permanecen privados.
        return PublicoDisponibilidadLectura(
            id_equipo=id_equipo,
            fecha_inicio=fecha_intervalo.fecha_inicio,
            fecha_fin=fecha_intervalo.fecha_fin,
            disponible=disponible,
            estado="available" if disponible else "unavailable",
        )

    def reserva_fechas(instancia, id_equipo: int) -> PublicoReservasLectura:
        equipo = instancia.obtener_activo(id_equipo)
        unidades = activo_producto_unidades(instancia.sesion, equipo)
        intervalos = instancia.reservas.activo_fecha_intervalos(
            [unidad.id for unidad in unidades], instancia.hoy()
        )
        return PublicoReservasLectura(
            id_equipo=unidades[0].id,
            reservas=[
                IntervaloFechas(fecha_inicio=arranque, fecha_fin=fin)
                for arranque, fin in intervalos
            ],
        )

    def calendario(
        instancia, id_equipo: int, fechas: PublicoCalendarioConsulta
    ) -> PublicoCalendarioLectura:
        equipo = instancia.obtener_activo(id_equipo)
        repositorio = RepositorioReservas(instancia.sesion)
        unidades = [
            unidad
            for unidad in activo_producto_unidades(instancia.sesion, equipo)
            if not repositorio.tiene_bloqueante_incidencia(unidad.id)
        ]
        consulta_arranque = min(fechas.fecha_inicio, fechas.inicio_reserva or fechas.fecha_inicio)
        unidad_intervalos = [
            repositorio.intervalos_ocupados(unidad.id, consulta_arranque, fechas.fecha_fin)
            for unidad in unidades
        ]
        ocupados: list[IntervaloFechas] = []
        fechas_fin_no_disponibles = []
        dia = fechas.fecha_inicio
        while dia < fechas.fecha_fin:
            # Un día está ocupado solo si todas las unidades utilizables están reservadas.
            if unidad_intervalos and all(
                any(arranque <= dia < fin for arranque, fin in intervalos)
                for intervalos in unidad_intervalos
            ):
                siguiente_dia = dia + timedelta(days=1)
                if ocupados and ocupados[-1].fecha_fin == dia:
                    ocupados[-1] = IntervaloFechas(
                        fecha_inicio=ocupados[-1].fecha_inicio, fecha_fin=siguiente_dia
                    )
                else:
                    ocupados.append(IntervaloFechas(fecha_inicio=dia, fecha_fin=siguiente_dia))
            # Las devoluciones requieren una misma unidad libre durante todo el intervalo elegido.
            if (
                fechas.inicio_reserva is not None
                and dia > fechas.inicio_reserva
                and not any(
                    not any(
                        arranque < dia and fin > fechas.inicio_reserva
                        for arranque, fin in intervalos
                    )
                    for intervalos in unidad_intervalos
                )
            ):
                fechas_fin_no_disponibles.append(dia)
            dia += timedelta(days=1)
        return PublicoCalendarioLectura(
            id_equipo=id_equipo,
            fecha_inicio=fechas.fecha_inicio,
            fecha_fin=fechas.fecha_fin,
            intervalos_ocupados=ocupados,
            puede_reservar=bool(unidades),
            fechas_fin_no_disponibles=fechas_fin_no_disponibles,
        )
