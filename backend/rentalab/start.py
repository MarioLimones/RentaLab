"""Container startup: validate configuration, migrate, then replace with one HTTP worker."""

import os
import sys
import tempfile
from pathlib import Path

from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from alembic import command
from rentalab.config import Settings


class StartupError(Exception):
    """An actionable startup failure safe to show without configuration values."""


def prepare_startup(settings: Settings) -> None:
    # Validate credentials before even creating the data directory or changing the schema.
    settings.require_auth()
    if settings.frontend_dist is None or not (settings.frontend_dist / "index.html").is_file():
        raise StartupError("Falta el frontend compilado; comprueba RENTALAB_FRONTEND_DIST")
    try:
        url = make_url(settings.database_url)
    except (ArgumentError, ValueError):
        raise StartupError(
            "El arranque requiere una base SQLite persistente en un archivo"
        ) from None
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise StartupError("El arranque requiere una base SQLite persistente en un archivo")

    database = Path(url.database).resolve()
    try:
        database.parent.mkdir(parents=True, exist_ok=True)
        # SQLite needs to create rollback journals/WAL beside the database, not just edit .db.
        with tempfile.NamedTemporaryFile(prefix=".rentalab-write-", dir=database.parent):
            pass
        if database.exists():
            with database.open("r+b"):
                pass
    except OSError:
        raise StartupError(
            "Revisa los permisos de escritura del archivo SQLite y su directorio"
        ) from None

    backend_root = Path(__file__).resolve().parents[1]
    migration_config = Config(str(backend_root / "alembic.ini"))
    migration_config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    try:
        command.upgrade(migration_config, "head")
    except Exception:
        raise StartupError(
            "No se pudieron aplicar las migraciones; el servicio no se ha iniciado"
        ) from None


def main() -> int:
    # New databases, backups and SQLite auxiliary files are private to the service user.
    os.umask(0o077)
    try:
        settings = Settings()
        prepare_startup(settings)
    except ValidationError:
        print("La configuración de arranque está ausente o no es válida", file=sys.stderr)
        return 1
    except (StartupError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1

    arguments = [
        sys.executable,
        "-m",
        "uvicorn",
        "rentalab.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(settings.port),
        "--workers",
        "1",
        "--proxy-headers",
        "--forwarded-allow-ips",
        settings.forwarded_allow_ips,
    ]
    try:
        # Replace PID 1 rather than leaving a shell between Docker and Uvicorn signals.
        os.execv(sys.executable, arguments)
    except OSError:
        print("No se pudo iniciar el servicio HTTP", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
