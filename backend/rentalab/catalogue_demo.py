"""Opt-in catalogue expansion: twenty illustrated units and ten owned bookings."""

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from rentalab.auth.models import User
from rentalab.clock import madrid_today
from rentalab.config import Settings
from rentalab.database import create_database_engine
from rentalab.demo import iso_date
from rentalab.equipment.models import Equipment
from rentalab.equipment.schemas import EquipmentCreate
from rentalab.reservations.models import Reservation
from rentalab.reservations.repository import ReservationRepository
from rentalab.reservations.schemas import ReservationCreate
from rentalab.reservations.service import ReservationConflict, ReservationService


def _equipment(
    index: int, code: str, name: str, category: str, description: str, specs: dict[str, str]
) -> EquipmentCreate:
    return EquipmentCreate(
        code=code,
        name=name,
        category=category,
        description="Unidad ficticia de demostración. Fotografía ilustrativa de su categoría.",
        public_description=description,
        technical_specs=specs,
        image_url=f"/api/public/images/catalogue-{index:02d}.{'png' if index == 2 else 'jpg'}",
    )


CATALOGUE_EQUIPMENT = (
    _equipment(
        1,
        "CAM-003",
        "Cámara Boreal C8",
        "Cámaras",
        "Cámara de óptica intercambiable para sesiones de fotografía, entrevistas "
        "y contenido digital.",
        {"Tipo": "Óptica intercambiable", "Uso": "Fotografía y vídeo", "Formato": "Portátil"},
    ),
    _equipment(
        2,
        "CAM-004",
        "Videocámara Prisma V4",
        "Cámaras",
        "Videocámara para grabar eventos, conferencias y producciones con un equipo reducido.",
        {"Tipo": "Videocámara", "Uso": "Eventos y entrevistas", "Soporte": "Mano o trípode"},
    ),
    _equipment(
        3,
        "CAM-005",
        "Cámara de acción Vértice A2",
        "Cámaras",
        "Cámara compacta para planos en movimiento, actividades al aire libre y tomas de recurso.",
        {"Tipo": "Cámara de acción", "Formato": "Compacto", "Uso": "Tomas en movimiento"},
    ),
    _equipment(
        4,
        "OBJ-001",
        "Objetivo Órbita 50",
        "Ópticas",
        "Objetivo fotográfico para retratos, entrevistas y planos de detalle.",
        {"Tipo": "Objetivo fotográfico", "Uso": "Retrato y detalle", "Enfoque": "Ajustable"},
    ),
    _equipment(
        5,
        "AUD-002",
        "Micrófono Nexo D1",
        "Audio",
        "Micrófono de mano para voces, presentaciones y entrevistas en directo.",
        {"Tipo": "Micrófono de mano", "Aplicación": "Voz", "Uso": "Escenario y entrevistas"},
    ),
    _equipment(
        6,
        "AUD-003",
        "Micrófono de condensador Nube C2",
        "Audio",
        "Micrófono de estudio para locuciones, pódcast y grabación de instrumentos.",
        {"Tipo": "Condensador", "Aplicación": "Voz e instrumentos", "Uso": "Estudio"},
    ),
    _equipment(
        7,
        "AUD-004",
        "Micrófono de solapa Hilo L1",
        "Audio",
        "Micrófono discreto de solapa para entrevistas y presentaciones con las manos libres.",
        {"Tipo": "Solapa", "Colocación": "Pinza en la ropa", "Aplicación": "Voz hablada"},
    ),
    _equipment(
        8,
        "AUD-005",
        "Grabadora portátil Eco R4",
        "Audio",
        "Grabadora autónoma para recoger entrevistas, ambientes y sonido durante el rodaje.",
        {"Tipo": "Grabadora de audio", "Formato": "Portátil", "Uso": "Entrevistas y ambientes"},
    ),
    _equipment(
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
    _equipment(
        10,
        "AUD-007",
        "Auriculares de estudio Pulso H2",
        "Audio",
        "Auriculares para escuchar y revisar el sonido durante entrevistas, rodajes y edición.",
        {"Tipo": "Auriculares de estudio", "Formato": "Diadema", "Uso": "Monitorización de audio"},
    ),
    _equipment(
        11,
        "AUD-008",
        "Altavoz activo Onda S12",
        "Audio",
        "Altavoz para reforzar la voz y la música en presentaciones y eventos de pequeño formato.",
        {"Tipo": "Altavoz", "Aplicación": "Refuerzo sonoro", "Uso": "Eventos y presentaciones"},
    ),
    _equipment(
        12,
        "LGT-002",
        "Panel LED Alba P100",
        "Iluminación",
        "Panel de iluminación continua para entrevistas, producto y creación de contenido.",
        {"Tipo": "Panel LED", "Luz": "Continua", "Uso": "Entrevistas y producto"},
    ),
    _equipment(
        13,
        "LGT-003",
        "Foco Fresnel Sol F200",
        "Iluminación",
        "Foco de estudio con haz orientable para dar forma a la iluminación de una escena.",
        {"Tipo": "Fresnel", "Iluminación": "Direccional", "Uso": "Rodaje y estudio"},
    ),
    _equipment(
        14,
        "LGT-004",
        "Softbox Difusa SB90",
        "Iluminación",
        "Modificador para suavizar la luz en retratos, entrevistas y fotografía de producto.",
        {"Tipo": "Softbox", "Función": "Difusión de luz", "Uso": "Retrato y producto"},
    ),
    _equipment(
        15,
        "LGT-005",
        "Aro de luz Halo R45",
        "Iluminación",
        "Iluminación circular para presentaciones a cámara, tutoriales y primeros planos.",
        {"Tipo": "Aro de luz", "Luz": "Continua", "Uso": "Primeros planos y tutoriales"},
    ),
    _equipment(
        16,
        "SUP-001",
        "Trípode de vídeo Atlas T6",
        "Soportes",
        "Soporte de cámara para planos estables, entrevistas y grabaciones de larga duración.",
        {"Tipo": "Trípode", "Apoyo": "Tres patas", "Uso": "Cámara y vídeo"},
    ),
    _equipment(
        17,
        "SUP-002",
        "Estabilizador Gimbal Axis G3",
        "Soportes",
        "Estabilizador para acompañar la acción y conseguir movimientos de cámara más suaves.",
        {"Tipo": "Gimbal", "Uso": "Cámara en movimiento", "Formato": "De mano"},
    ),
    _equipment(
        18,
        "SUP-003",
        "Monopie Lince M1",
        "Soportes",
        "Apoyo ligero para trabajar con cámara en eventos y espacios donde se necesita movilidad.",
        {"Tipo": "Monopie", "Apoyo": "Una pata", "Uso": "Fotografía y vídeo"},
    ),
    _equipment(
        19,
        "PRJ-001",
        "Proyector Horizonte P5",
        "Proyección",
        "Proyector para mostrar presentaciones y contenido audiovisual en salas y encuentros.",
        {"Tipo": "Proyector de vídeo", "Uso": "Presentaciones", "Instalación": "Sobremesa"},
    ),
    _equipment(
        20,
        "LGT-006",
        "Flash de estudio Destello S400",
        "Iluminación",
        "Flash de estudio para sesiones de retrato y fotografía de producto con luz controlada.",
        {"Tipo": "Flash de estudio", "Luz": "Destello", "Uso": "Retrato y producto"},
    ),
)

# Reserve half the new catalogue, spread across its categories.
BOOKING_EQUIPMENT_CODES = (
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
class CatalogueSeedResult:
    equipment_created: int
    reservations_created: int
    reservations_existing: int
    skipped: tuple[str, ...]


def seed_catalogue_demo(
    settings: Settings,
    *,
    base_date: date | None = None,
    today: Callable[[], date] = madrid_today,
) -> CatalogueSeedResult:
    """Add missing demo data without changing existing units, accounts or bookings."""
    if settings.environment == "production":
        raise ValueError("La carga de demostración está prohibida en production")
    current_day = today()
    base = base_date or current_day
    if base < current_day:
        raise ValueError("La fecha base no puede ser anterior a hoy en Europe/Madrid")
    try:
        ranges = [
            (base + timedelta(days=index), base + timedelta(days=index + 3 + index % 3))
            for index in range(len(BOOKING_EQUIPMENT_CODES))
        ]
    except OverflowError:
        raise ValueError(
            "La fecha base no permite calcular los intervalos de demostración"
        ) from None

    engine = create_database_engine(
        settings.database_url, busy_timeout_ms=settings.sqlite_busy_timeout_ms
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    equipment_created = reservations_created = reservations_existing = 0
    skipped: list[str] = []
    try:
        # Reuse up to four existing customers, without creating or changing accounts.
        with factory() as session, session.begin():
            users = session.scalars(
                select(User)
                .where(User.active.is_(True), User.role == "customer")
                .order_by(User.id)
                .limit(4)
            ).all()
            if not users:
                raise ValueError(
                    "Se necesita al menos un cliente activo antes de cargar las reservas"
                )
            customers = [(user.id, user.name, user.email) for user in users]
            for equipment in CATALOGUE_EQUIPMENT:
                result = session.execute(
                    insert(Equipment)
                    .values(**equipment.model_dump())
                    .on_conflict_do_nothing(index_elements=["code"])
                )
                equipment_created += result.rowcount

        for index, (code, (start, end)) in enumerate(
            zip(BOOKING_EQUIPMENT_CODES, ranges, strict=True)
        ):
            reference = f"RENTALAB-CATALOGUE-{index + 1:02d}"
            with factory() as session:
                if (
                    session.scalar(
                        select(Reservation.id).where(Reservation.external_reference == reference)
                    )
                    is not None
                ):
                    reservations_existing += 1
                    continue
                equipment_id = session.scalar(select(Equipment.id).where(Equipment.code == code))
                assert equipment_id is not None
            user_id, name, email = customers[index % len(customers)]
            data = ReservationCreate(
                equipment_id=equipment_id,
                customer_name=name,
                customer_email=email,
                start_date=start,
                end_date=end,
                external_reference=reference,
            )
            try:
                with factory() as session:
                    ReservationService(ReservationRepository(session)).create_for_customer(
                        data, customer_user_id=user_id, today=lambda: current_day
                    )
                reservations_created += 1
            except ReservationConflict as error:
                skipped.append(f"{reference}: {error}")
        return CatalogueSeedResult(
            equipment_created, reservations_created, reservations_existing, tuple(skipped)
        )
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--base-date", type=iso_date, help="Fecha base YYYY-MM-DD")
    args = parser.parse_args(argv)
    try:
        result = seed_catalogue_demo(Settings(), base_date=args.base_date)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "No se pudo completar la carga; comprueba la base y sus migraciones.", file=sys.stderr
        )
        return 1
    print(
        f"Equipos nuevos: {result.equipment_created}; "
        f"reservas nuevas: {result.reservations_created}; "
        f"reservas conservadas: {result.reservations_existing}."
    )
    for reason in result.skipped:
        print(f"Omitida {reason}", file=sys.stderr)
    return 1 if result.skipped else 0


if __name__ == "__main__":
    raise SystemExit(main())
