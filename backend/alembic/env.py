from sqlalchemy import Connection

from alembic import context
from rentalab.autenticacion import modelos as autenticacion_modelos  # noqa: F401
from rentalab.base_datos import Base, crear_base_datos_motor
from rentalab.configuracion import Configuracion
from rentalab.cuenta import modelos as cuenta_modelos  # noqa: F401
from rentalab.equipo import modelos  # noqa: F401
from rentalab.incidencias import modelos as incidencia_modelos  # noqa: F401
from rentalab.reservas import modelos as reserva_modelos  # noqa: F401

configuracion = context.config
metadatos_objetivo = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=configuracion.get_main_option("sqlalchemy.url") or Configuracion().url_base_datos,
        target_metadata=metadatos_objetivo,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def migrate(conexion: Connection) -> None:
    context.configure(connection=conexion, target_metadata=metadatos_objetivo, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conexion = configuracion.attributes.get("connection")
    if conexion is not None:
        migrate(conexion)
        return
    ajustes = Configuracion()
    motor = crear_base_datos_motor(
        configuracion.get_main_option("sqlalchemy.url") or ajustes.url_base_datos,
        ocupado_espera_ms=ajustes.espera_sqlite_ocupado_ms,
    )
    with motor.connect() as conexion:
        migrate(conexion)
    motor.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
