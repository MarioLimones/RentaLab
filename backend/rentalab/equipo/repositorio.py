from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from rentalab.equipo.modelos import Equipo


class RepositorioEquipos:
    def __init__(instancia, sesion: Session) -> None:
        instancia.sesion = sesion

    def listar(instancia, activo: bool | None = None) -> Sequence[Equipo]:
        sentencia = select(Equipo).order_by(Equipo.codigo)
        if activo is not None:
            sentencia = sentencia.where(Equipo.activo == activo)
        return instancia.sesion.scalars(sentencia).all()

    def obtener(instancia, id_equipo: int) -> Equipo | None:
        return instancia.sesion.get(Equipo, id_equipo)

    def buscar_por_codigo(instancia, codigo: str) -> Equipo | None:
        return instancia.sesion.scalar(select(Equipo).where(Equipo.codigo == codigo))

    def agregar(instancia, equipo: Equipo) -> None:
        instancia.sesion.add(equipo)

    def confirmar(instancia) -> None:
        instancia.sesion.commit()
