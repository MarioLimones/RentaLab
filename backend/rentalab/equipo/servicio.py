import sqlite3
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError

from rentalab.equipo.esquemas import ActualizarEquipo, CrearEquipo
from rentalab.equipo.modelos import Equipo
from rentalab.equipo.repositorio import RepositorioEquipos


class EquipoNoEncontrado(Exception):
    pass


class CodigoEquipoDuplicado(Exception):
    pass


class ServicioEquipos:
    def __init__(instancia, repositorio: RepositorioEquipos) -> None:
        instancia.repositorio = repositorio

    def listar(instancia, activo: bool | None = None) -> Sequence[Equipo]:
        return instancia.repositorio.listar(activo)

    def obtener(instancia, id_equipo: int) -> Equipo:
        equipo = instancia.repositorio.obtener(id_equipo)
        if equipo is None:
            raise EquipoNoEncontrado
        return equipo

    def crear(instancia, datos: CrearEquipo) -> Equipo:
        instancia._asegurar_unico_codigo(datos.codigo)
        equipo = Equipo(**datos.model_dump())
        instancia.repositorio.agregar(equipo)
        instancia._confirmar()
        return equipo

    def actualizar(instancia, id_equipo: int, datos: CrearEquipo | ActualizarEquipo) -> Equipo:
        equipo = instancia.obtener(id_equipo)
        cambios = datos.model_dump(exclude_unset=isinstance(datos, ActualizarEquipo))
        if "codigo" in cambios:
            instancia._asegurar_unico_codigo(cambios["codigo"], id_equipo)
        for campo, valor in cambios.items():
            setattr(equipo, campo, valor)
        instancia._confirmar()
        return equipo

    def _asegurar_unico_codigo(instancia, codigo: str, id_equipo: int | None = None) -> None:
        existentes = instancia.repositorio.buscar_por_codigo(codigo)
        if existentes is not None and existentes.id != id_equipo:
            raise CodigoEquipoDuplicado

    def _confirmar(instancia) -> None:
        try:
            instancia.repositorio.confirmar()
        except IntegrityError as error:
            instancia.repositorio.sesion.rollback()
            if getattr(error.orig, "sqlite_errorcode", None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE:
                raise CodigoEquipoDuplicado from error
            raise
