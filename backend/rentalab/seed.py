from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from rentalab.config import Settings
from rentalab.database import create_database_engine
from rentalab.equipment.models import Equipment
from rentalab.equipment.schemas import EquipmentCreate

DEMO_EQUIPMENT = (
    EquipmentCreate(
        code="CAM-001",
        image_url="/api/public/images/demo-camera.jpg",
        name="Cámara Aurora S4",
        category="Cámaras",
        description="Unidad ficticia de cámara de estudio.",
        public_description="Cámara ficticia para entrevistas y grabación en estudio.",
        technical_specs={"Resolución": "4K UHD", "Montura": "Aurora A", "Peso": "1,2 kg"},
    ),
    EquipmentCreate(
        code="CAM-002",
        image_url="/api/public/images/demo-camera.jpg",
        name="Cámara Aurora S4",
        category="Cámaras",
        description="Segunda unidad física del mismo modelo ficticio.",
        public_description="Segunda cámara ficticia para rodajes con varias perspectivas.",
        technical_specs={"Resolución": "4K UHD", "Montura": "Aurora A", "Peso": "1,2 kg"},
    ),
    EquipmentCreate(
        code="AUD-001",
        image_url="/api/public/images/demo-microphone.jpg",
        name="Micrófono Brisa M2",
        category="Audio",
        description="Micrófono ficticio para entrevistas.",
        public_description="Micrófono ficticio para voz, entrevistas y grabación de pódcast.",
        technical_specs={"Patrón polar": "Cardioide", "Conexión": "XLR", "Peso": "320 g"},
    ),
    EquipmentCreate(
        code="LGT-001",
        image_url="/api/public/images/demo-light.jpg",
        name="Panel Lumen P60",
        category="Iluminación",
        description="Panel LED ficticio para rodajes.",
        public_description="Panel LED ficticio regulable para entrevistas y pequeños rodajes.",
        technical_specs={
            "Potencia": "60 W",
            "Temperatura de color": "3200–5600 K",
            "Alimentación": "Red eléctrica",
        },
    ),
)


def seed_equipment(session: Session) -> int:
    created = 0
    for equipment in DEMO_EQUIPMENT:
        result = session.execute(
            insert(Equipment)
            .values(**equipment.model_dump())
            .on_conflict_do_nothing(index_elements=["code"])
        )
        created += result.rowcount
    return created


def main() -> None:
    engine = create_database_engine(Settings().database_url)
    try:
        with Session(engine) as session, session.begin():
            created = seed_equipment(session)
        print(f"Carga ficticia completada: {created} equipos nuevos.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
