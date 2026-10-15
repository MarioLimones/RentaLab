from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from rentalab.base_datos import crear_base_datos_motor
from rentalab.configuracion import Configuracion
from rentalab.equipo.esquemas import CrearEquipo
from rentalab.equipo.modelos import Equipo

DEMOSTRACION_EQUIPO = (
    CrearEquipo(
        codigo="CAM-001",
        url_imagen="/api/public/images/demo-camera.jpg",
        nombre="Cámara Aurora S4",
        categoria="Cámaras",
        descripcion="Unidad ficticia de cámara de estudio.",
        descripcion_publica="Cámara ficticia para entrevistas y grabación en estudio.",
        caracteristicas_tecnicas={"Resolución": "4K UHD", "Montura": "Aurora A", "Peso": "1,2 kg"},
    ),
    CrearEquipo(
        codigo="CAM-002",
        url_imagen="/api/public/images/demo-camera.jpg",
        nombre="Cámara Aurora S4",
        categoria="Cámaras",
        descripcion="Segunda unidad física del mismo modelo ficticio.",
        descripcion_publica="Segunda cámara ficticia para rodajes con varias perspectivas.",
        caracteristicas_tecnicas={"Resolución": "4K UHD", "Montura": "Aurora A", "Peso": "1,2 kg"},
    ),
    CrearEquipo(
        codigo="AUD-001",
        url_imagen="/api/public/images/demo-microphone.jpg",
        nombre="Micrófono Brisa M2",
        categoria="Audio",
        descripcion="Micrófono ficticio para entrevistas.",
        descripcion_publica="Micrófono ficticio para voz, entrevistas y grabación de pódcast.",
        caracteristicas_tecnicas={"Patrón polar": "Cardioide", "Conexión": "XLR", "Peso": "320 g"},
    ),
    CrearEquipo(
        codigo="LGT-001",
        url_imagen="/api/public/images/demo-light.jpg",
        nombre="Panel Lumen P60",
        categoria="Iluminación",
        descripcion="Panel LED ficticio para rodajes.",
        descripcion_publica="Panel LED ficticio regulable para entrevistas y pequeños rodajes.",
        caracteristicas_tecnicas={
            "Potencia": "60 W",
            "Temperatura de color": "3200–5600 K",
            "Alimentación": "Red eléctrica",
        },
    ),
)


def cargar_datos_equipo(sesion: Session) -> int:
    creados = 0
    for equipo in DEMOSTRACION_EQUIPO:
        resultado = sesion.execute(
            insert(Equipo)
            .values(**equipo.model_dump())
            .on_conflict_do_nothing(index_elements=["code"])
        )
        creados += resultado.rowcount
    return creados


def principal() -> None:
    motor = crear_base_datos_motor(Configuracion().url_base_datos)
    try:
        with Session(motor) as sesion, sesion.begin():
            creados = cargar_datos_equipo(sesion)
        print(f"Carga ficticia completada: {creados} equipos nuevos.")
    finally:
        motor.dispose()


if __name__ == "__main__":
    principal()
