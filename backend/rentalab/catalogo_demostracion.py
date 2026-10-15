"""Ampliación opcional del catálogo: veinte unidades ilustradas y diez reservas con propietario."""

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from rentalab.autenticacion.modelos import Usuario
from rentalab.base_datos import crear_base_datos_motor
from rentalab.configuracion import Configuracion
from rentalab.demostracion import iso_fecha
from rentalab.equipo.esquemas import CrearEquipo
from rentalab.equipo.modelos import Equipo
from rentalab.reloj import madrid_hoy
from rentalab.reservas.esquemas import CrearReserva
from rentalab.reservas.modelos import Reserva
from rentalab.reservas.repositorio import RepositorioReservas
from rentalab.reservas.servicio import ConflictoReserva, ServicioReservas


def _equipo(
    indice: int,
    codigo: str,
    nombre: str,
    categoria: str,
    descripcion: str,
    caracteristicas: dict[str, str],
) -> CrearEquipo:
    return CrearEquipo(
        codigo=codigo,
        nombre=nombre,
        categoria=categoria,
        descripcion="Unidad ficticia de demostración. Fotografía ilustrativa de su categoría.",
        descripcion_publica=descripcion,
        caracteristicas_tecnicas=caracteristicas,
        url_imagen=f"/api/public/images/catalogue-{indice:02d}.{'png' if indice == 2 else 'jpg'}",
    )


CATALOGO_EQUIPO = (
    _equipo(
        1,
        "CAM-003",
        "Cámara Boreal C8",
        "Cámaras",
        "Cámara de óptica intercambiable para sesiones de fotografía, entrevistas "
        "y contenido digital.",
        {"Tipo": "Óptica intercambiable", "Uso": "Fotografía y vídeo", "Formato": "Portátil"},
    ),
    _equipo(
        2,
        "CAM-004",
        "Videocámara Prisma V4",
        "Cámaras",
        "Videocámara para grabar eventos, conferencias y producciones con un equipo reducido.",
        {"Tipo": "Videocámara", "Uso": "Eventos y entrevistas", "Soporte": "Mano o trípode"},
    ),
    _equipo(
        3,
        "CAM-005",
        "Cámara de acción Vértice A2",
        "Cámaras",
        "Cámara compacta para planos en movimiento, actividades al aire libre y tomas de recurso.",
        {"Tipo": "Cámara de acción", "Formato": "Compacto", "Uso": "Tomas en movimiento"},
    ),
    _equipo(
        4,
        "OBJ-001",
        "Objetivo Órbita 50",
        "Ópticas",
        "Objetivo fotográfico para retratos, entrevistas y planos de detalle.",
        {"Tipo": "Objetivo fotográfico", "Uso": "Retrato y detalle", "Enfoque": "Ajustable"},
    ),
    _equipo(
        5,
        "AUD-002",
        "Micrófono Nexo D1",
        "Audio",
        "Micrófono de mano para voces, presentaciones y entrevistas en directo.",
        {"Tipo": "Micrófono de mano", "Aplicación": "Voz", "Uso": "Escenario y entrevistas"},
    ),
    _equipo(
        6,
        "AUD-003",
        "Micrófono de condensador Nube C2",
        "Audio",
        "Micrófono de estudio para locuciones, pódcast y grabación de instrumentos.",
        {"Tipo": "Condensador", "Aplicación": "Voz e instrumentos", "Uso": "Estudio"},
    ),
    _equipo(
        7,
        "AUD-004",
        "Micrófono de solapa Hilo L1",
        "Audio",
        "Micrófono discreto de solapa para entrevistas y presentaciones con las manos libres.",
        {"Tipo": "Solapa", "Colocación": "Pinza en la ropa", "Aplicación": "Voz hablada"},
    ),
    _equipo(
        8,
        "AUD-005",
        "Grabadora portátil Eco R4",
        "Audio",
        "Grabadora autónoma para recoger entrevistas, ambientes y sonido durante el rodaje.",
        {"Tipo": "Grabadora de audio", "Formato": "Portátil", "Uso": "Entrevistas y ambientes"},
    ),
    _equipo(
        9,
        "AUD-006",
        "Mezclador de audio Delta M8",
        "Audio",
        "Mesa de mezclas para controlar varias fuentes de audio en pequeños eventos y grabaciones.",
        {
            "Tipo": "Mesa de mezclas",
            "Control": "Canales independientes",
            "Uso": "Directo y estudio",
        },
    ),
    _equipo(
        10,
        "AUD-007",
        "Auriculares de estudio Pulso H2",
        "Audio",
        "Auriculares para escuchar y revisar el sonido durante entrevistas, rodajes y edición.",
        {"Tipo": "Auriculares de estudio", "Formato": "Diadema", "Uso": "Monitorización de audio"},
    ),
    _equipo(
        11,
        "AUD-008",
        "Altavoz activo Onda S12",
        "Audio",
        "Altavoz para reforzar la voz y la música en presentaciones y eventos de pequeño formato.",
        {"Tipo": "Altavoz", "Aplicación": "Refuerzo sonoro", "Uso": "Eventos y presentaciones"},
    ),
    _equipo(
        12,
        "LGT-002",
        "Panel LED Alba P100",
        "Iluminación",
        "Panel de iluminación continua para entrevistas, producto y creación de contenido.",
        {"Tipo": "Panel LED", "Luz": "Continua", "Uso": "Entrevistas y producto"},
    ),
    _equipo(
        13,
        "LGT-003",
        "Foco Fresnel Sol F200",
        "Iluminación",
        "Foco de estudio con haz orientable para dar forma a la iluminación de una escena.",
        {"Tipo": "Fresnel", "Iluminación": "Direccional", "Uso": "Rodaje y estudio"},
    ),
    _equipo(
        14,
        "LGT-004",
        "Softbox Difusa SB90",
        "Iluminación",
        "Modificador para suavizar la luz en retratos, entrevistas y fotografía de producto.",
        {"Tipo": "Softbox", "Función": "Difusión de luz", "Uso": "Retrato y producto"},
    ),
    _equipo(
        15,
        "LGT-005",
        "Aro de luz Halo R45",
        "Iluminación",
        "Iluminación circular para presentaciones a cámara, tutoriales y primeros planos.",
        {"Tipo": "Aro de luz", "Luz": "Continua", "Uso": "Primeros planos y tutoriales"},
    ),
    _equipo(
        16,
        "SUP-001",
        "Trípode de vídeo Atlas T6",
        "Soportes",
        "Soporte de cámara para planos estables, entrevistas y grabaciones de larga duración.",
        {"Tipo": "Trípode", "Apoyo": "Tres patas", "Uso": "Cámara y vídeo"},
    ),
    _equipo(
        17,
        "SUP-002",
        "Estabilizador Gimbal Axis G3",
        "Soportes",
        "Estabilizador para acompañar la acción y conseguir movimientos de cámara más suaves.",
        {"Tipo": "Gimbal", "Uso": "Cámara en movimiento", "Formato": "De mano"},
    ),
    _equipo(
        18,
        "SUP-003",
        "Monopie Lince M1",
        "Soportes",
        "Apoyo ligero para trabajar con cámara en eventos y espacios donde se necesita movilidad.",
        {"Tipo": "Monopie", "Apoyo": "Una pata", "Uso": "Fotografía y vídeo"},
    ),
    _equipo(
        19,
        "PRJ-001",
        "Proyector Horizonte P5",
        "Proyección",
        "Proyector para mostrar presentaciones y contenido audiovisual en salas y encuentros.",
        {"Tipo": "Proyector de vídeo", "Uso": "Presentaciones", "Instalación": "Sobremesa"},
    ),
    _equipo(
        20,
        "LGT-006",
        "Flash de estudio Destello S400",
        "Iluminación",
        "Flash de estudio para sesiones de retrato y fotografía de producto con luz controlada.",
        {"Tipo": "Flash de estudio", "Luz": "Destello", "Uso": "Retrato y producto"},
    ),
)

# Reserva la mitad del catálogo nuevo, distribuida entre sus categorías.
RESERVA_EQUIPO_CODIGOS = (
    "CAM-003",
    "CAM-005",
    "OBJ-001",
    "AUD-002",
    "AUD-005",
    "AUD-007",
    "LGT-002",
    "LGT-004",
    "SUP-001",
    "PRJ-001",
)


@dataclass(frozen=True)
class CatalogoCargarDatosResultado:
    equipo_creados: int
    reservas_creados: int
    reservas_existentes: int
    omitidas: tuple[str, ...]


def cargar_datos_catalogo_demostracion(
    ajustes: Configuracion,
    *,
    base_fecha: date | None = None,
    hoy: Callable[[], date] = madrid_hoy,
) -> CatalogoCargarDatosResultado:
    """Añade datos ficticios ausentes sin cambiar unidades, cuentas ni reservas existentes."""
    if ajustes.entorno == "production":
        raise ValueError("La carga de demostración está prohibida en production")
    actual_dia = hoy()
    base = base_fecha or actual_dia
    if base < actual_dia:
        raise ValueError("La fecha base no puede ser anterior a hoy en Europe/Madrid")
    try:
        intervalos = [
            (base + timedelta(days=indice), base + timedelta(days=indice + 3 + indice % 3))
            for indice in range(len(RESERVA_EQUIPO_CODIGOS))
        ]
    except OverflowError:
        raise ValueError(
            "La fecha base no permite calcular los intervalos de demostración"
        ) from None

    motor = crear_base_datos_motor(
        ajustes.url_base_datos, ocupado_espera_ms=ajustes.espera_sqlite_ocupado_ms
    )
    fabrica = sessionmaker(motor, expire_on_commit=False)
    equipo_creados = reservas_creados = reservas_existentes = 0
    omitidas: list[str] = []
    try:
        # Reutiliza hasta cuatro clientes existentes sin crear ni cambiar cuentas.
        with fabrica() as sesion, sesion.begin():
            usuarios = sesion.scalars(
                select(Usuario)
                .where(Usuario.activo.is_(True), Usuario.rol == "customer")
                .order_by(Usuario.id)
                .limit(4)
            ).all()
            if not usuarios:
                raise ValueError(
                    "Se necesita al menos un cliente activo antes de cargar las reservas"
                )
            clientes = [(usuario.id, usuario.nombre, usuario.correo) for usuario in usuarios]
            for equipo in CATALOGO_EQUIPO:
                resultado = sesion.execute(
                    insert(Equipo)
                    .values(**equipo.model_dump())
                    .on_conflict_do_nothing(index_elements=["code"])
                )
                equipo_creados += resultado.rowcount

        for indice, (codigo, (arranque, fin)) in enumerate(
            zip(RESERVA_EQUIPO_CODIGOS, intervalos, strict=True)
        ):
            referencia = f"RENTALAB-CATALOGUE-{indice + 1:02d}"
            with fabrica() as sesion:
                if (
                    sesion.scalar(
                        select(Reserva.id).where(Reserva.referencia_externa == referencia)
                    )
                    is not None
                ):
                    reservas_existentes += 1
                    continue
                id_equipo = sesion.scalar(select(Equipo.id).where(Equipo.codigo == codigo))
                assert id_equipo is not None
            id_usuario, nombre, correo = clientes[indice % len(clientes)]
            datos = CrearReserva(
                id_equipo=id_equipo,
                nombre_cliente=nombre,
                correo_cliente=correo,
                fecha_inicio=arranque,
                fecha_fin=fin,
                referencia_externa=referencia,
            )
            try:
                with fabrica() as sesion:
                    ServicioReservas(RepositorioReservas(sesion)).crear_para_cliente(
                        datos, id_usuario_cliente=id_usuario, hoy=lambda: actual_dia
                    )
                reservas_creados += 1
            except ConflictoReserva as error:
                omitidas.append(f"{referencia}: {error}")
        return CatalogoCargarDatosResultado(
            equipo_creados, reservas_creados, reservas_existentes, tuple(omitidas)
        )
    finally:
        motor.dispose()


def principal(argumentos: list[str] | None = None) -> int:
    analizador = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    analizador.add_argument(
        "--base-date", dest="base_fecha", type=iso_fecha, help="Fecha base YYYY-MM-DD"
    )
    argumentos = analizador.parse_args(argumentos)
    try:
        resultado = cargar_datos_catalogo_demostracion(
            Configuracion(), base_fecha=argumentos.base_fecha
        )
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "No se pudo completar la carga; comprueba la base y sus migraciones.", file=sys.stderr
        )
        return 1
    print(
        f"Equipos nuevos: {resultado.equipo_creados}; "
        f"reservas nuevas: {resultado.reservas_creados}; "
        f"reservas conservadas: {resultado.reservas_existentes}."
    )
    for motivo in resultado.omitidas:
        print(f"Omitida {motivo}", file=sys.stderr)
    return 1 if resultado.omitidas else 0


if __name__ == "__main__":
    raise SystemExit(principal())
