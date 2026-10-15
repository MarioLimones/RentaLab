from sqlalchemy import Connection

from alembic import context
from rentalab.auth import models as auth_models  # noqa: F401
from rentalab.config import Settings
from rentalab.database import Base, create_database_engine
from rentalab.equipment import models  # noqa: F401
from rentalab.incidents import models as incident_models  # noqa: F401
from rentalab.me import models as me_models  # noqa: F401
from rentalab.reservations import models as reservation_models  # noqa: F401

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url") or Settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def migrate(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        migrate(connection)
        return
    settings = Settings()
    engine = create_database_engine(
        config.get_main_option("sqlalchemy.url") or settings.database_url,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
    )
    with engine.connect() as connection:
        migrate(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
