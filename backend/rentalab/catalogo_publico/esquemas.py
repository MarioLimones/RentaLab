from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from rentalab.compatibilidad import ModeloApi
from rentalab.reservas.esquemas import IntervaloFechas, IsoFecha

BusquedaTexto = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=120, pattern=r"^[^\x00]*$"),
]
CategoriaFiltro = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=80, pattern=r"^[^\x00]*$"),
]


class PublicoCatalogoFiltros(ModeloApi):
    model_config = ConfigDict(extra="forbid")

    busqueda: BusquedaTexto | None = Field(
        default=None,
        description="Fragmento literal del nombre, sin distinguir mayúsculas y minúsculas",
    )
    categoria: CategoriaFiltro | None = Field(
        default=None,
        description="Categoría exacta, sin distinguir mayúsculas y minúsculas",
    )


class PublicoFechaIntervalo(ModeloApi):
    model_config = ConfigDict(extra="forbid")

    fecha_inicio: IsoFecha | None = Field(default=None, description="Inicio incluido, YYYY-MM-DD")
    fecha_fin: IsoFecha | None = Field(default=None, description="Fin excluido, YYYY-MM-DD")

    @model_validator(mode="after")
    def exigir_completo_positivo_intervalo(instancia) -> Self:
        if (instancia.fecha_inicio is None) != (instancia.fecha_fin is None):
            raise ValueError("Envía start_date y end_date juntos para consultar disponibilidad")
        if instancia.fecha_inicio is not None and instancia.fecha_fin is not None:
            IntervaloFechas(fecha_inicio=instancia.fecha_inicio, fecha_fin=instancia.fecha_fin)
        return instancia

    def a_fecha_intervalo(instancia) -> IntervaloFechas | None:
        if instancia.fecha_inicio is None or instancia.fecha_fin is None:
            return None
        return IntervaloFechas(fecha_inicio=instancia.fecha_inicio, fecha_fin=instancia.fecha_fin)


class PublicoEquipoLectura(ModeloApi):
    """Campos permitidos: el catálogo público nunca usa serializadores administrativos."""

    model_config = ConfigDict(extra="forbid")

    id: int
    nombre: str
    categoria: str
    descripcion_publica: str
    caracteristicas_tecnicas: dict[str, str]
    url_imagen: str | None
    url_imagen_alternativa: str = Field(
        description="Imagen local disponible sin servicios externos"
    )
    numero_reservas_activas: int = Field(
        ge=0,
        description=(
            "Reservas confirmadas en curso o futuras de las unidades activas del modelo. "
            "No incluye canceladas ni las que terminan hoy en Europe/Madrid (fin excluido)."
        ),
    )


class PublicoDisponibilidadLectura(ModeloApi):
    model_config = ConfigDict(extra="forbid")

    id_equipo: int
    fecha_inicio: IsoFecha | None
    fecha_fin: IsoFecha | None
    disponible: bool | None = Field(
        description="null sin fechas; orientativa, se vuelve a comprobar al confirmar una reserva"
    )
    estado: Literal["select_dates", "available", "unavailable"]


class PublicoReservasConsulta(ModeloApi):
    model_config = ConfigDict(extra="forbid")


class PublicoReservasLectura(ModeloApi):
    model_config = ConfigDict(extra="forbid")

    id_equipo: int
    reservas: list[IntervaloFechas] = Field(
        description=(
            "Fechas originales [inicio, fin) de cada reserva confirmada en curso o futura, "
            "ordenadas por inicio y fin, sin agrupar, recortar ni revelar datos privados. "
            "Se excluyen las que terminan hoy en Europe/Madrid."
        )
    )


class PublicoCalendarioIntervalo(IntervaloFechas):
    @model_validator(mode="after")
    def limitar_calendario_ventana(instancia) -> Self:
        if (instancia.fecha_fin - instancia.fecha_inicio).days > 366:
            raise ValueError("El calendario admite como máximo 366 días por consulta")
        return instancia


class PublicoCalendarioLectura(PublicoCalendarioIntervalo):
    id_equipo: int
    intervalos_ocupados: list[IntervaloFechas] = Field(
        description="Días ocupados [inicio, fin), agrupados y recortados al rango consultado"
    )
    puede_reservar: bool = Field(
        description=(
            "El equipo admite reservas; los rangos ocupados siguen sin estar disponibles. "
            "La confirmación vuelve a comprobar las reglas de forma atómica."
        )
    )
    fechas_fin_no_disponibles: list[IsoFecha] = Field(
        default_factory=list,
        description="Devoluciones sin una unidad libre para todo el intervalo desde booking_start",
    )


class PublicoCalendarioConsulta(PublicoCalendarioIntervalo):
    inicio_reserva: IsoFecha | None = Field(
        default=None, description="Recogida seleccionada para comprobar devoluciones del calendario"
    )

    @model_validator(mode="after")
    def limitar_reserva_ventana(instancia) -> Self:
        if (
            instancia.inicio_reserva is not None
            and (instancia.fecha_fin - instancia.inicio_reserva).days > 366
        ):
            raise ValueError("El calendario admite como máximo 366 días desde la recogida")
        return instancia
