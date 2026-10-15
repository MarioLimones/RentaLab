"""Consistent SQLite snapshots. Restore requires every application process to be stopped."""

import argparse
import os
import sqlite3
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from rentalab.config import Settings


class BackupError(Exception):
    """An actionable backup error without database content or internal exception details."""


def _database_path(settings: Settings) -> Path:
    try:
        url = make_url(settings.database_url)
    except ArgumentError:
        raise BackupError("La configuración debe indicar un archivo SQLite.") from None
    if (
        url.get_backend_name() != "sqlite"
        or not url.database
        or url.database == ":memory:"
        or url.query
    ):
        raise BackupError("La configuración debe indicar un archivo SQLite.")
    return Path(url.database).resolve()


def _validate_source(path: Path) -> None:
    if not path.is_file():
        raise BackupError("No existe el archivo SQLite de origen.")
    with path.open("rb") as stream:
        if stream.read(16) != b"SQLite format 3\x00":
            raise BackupError("El origen no es un archivo SQLite válido.")


def _copy(source: sqlite3.Connection, destination: sqlite3.Connection, timeout_ms: int) -> None:
    deadline = time.monotonic() + timeout_ms / 1000

    def progress(status: int, _remaining: int, _total: int) -> None:
        # sqlite3.backup otherwise retries SQLITE_BUSY indefinitely, beyond connect(timeout).
        if status != sqlite3.SQLITE_DONE and time.monotonic() >= deadline:
            raise BackupError("La base está bloqueada o la copia agotó el tiempo de espera.")

    source.backup(destination, pages=256, progress=progress, sleep=0.05)


def _validate_snapshot(connection: sqlite3.Connection) -> None:
    if (
        connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
        or connection.execute("PRAGMA foreign_key_check").fetchone() is not None
    ):
        raise BackupError("La copia no supera las comprobaciones de integridad de SQLite.")


@contextmanager
def _snapshot(source: Path, directory: Path, timeout_ms: int) -> Iterator[Path]:
    _validate_source(source)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".rentalab-backup-", dir=directory)
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        # mode=ro never creates a missing source; SQLite reads committed WAL pages itself.
        with (
            closing(sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True, timeout=0)) as origin,
            closing(sqlite3.connect(temporary_path, timeout=0)) as destination,
        ):
            _copy(origin, destination, timeout_ms)
            _validate_snapshot(destination)
            # Publish a standalone snapshot, with no auxiliary files to transport.
            destination.execute("PRAGMA journal_mode=DELETE")
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)


def create_backup(settings: Settings, destination: Path) -> None:
    """Back up a live database to a new file, never replacing an existing backup."""
    source = _database_path(settings)
    destination = destination.absolute()
    try:
        if os.path.lexists(destination):
            raise BackupError("El archivo de destino ya existe; elige un nombre nuevo.")
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with _snapshot(source, destination.parent, settings.sqlite_busy_timeout_ms) as snapshot:
            # Link atomically publishes the completed file and fails if a concurrent writer won.
            os.link(snapshot, destination)
    except FileExistsError:
        raise BackupError("El archivo de destino ya existe; elige un nombre nuevo.") from None
    except (OSError, sqlite3.Error):
        raise BackupError(
            "No se pudo crear la copia; revisa el origen, directorio y permisos."
        ) from None


def restore_backup(settings: Settings, source: Path, *, app_stopped: bool = False) -> None:
    """Restore through SQLite's atomic backup transaction, without touching live sidecars."""
    if not app_stopped:
        raise BackupError("Detén la aplicación y confirma con --app-stopped que está detenida.")
    destination = _database_path(settings)
    source = source.resolve()
    if source == destination:
        raise BackupError("El origen y el destino no pueden ser el mismo archivo.")
    created = False
    try:
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with _snapshot(source, destination.parent, settings.sqlite_busy_timeout_ms) as snapshot:
            try:
                # Reserving a new target identifies precisely which empty file cleanup owns.
                descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                created = True
                os.close(descriptor)
            except FileExistsError:
                pass
            with (
                closing(sqlite3.connect(snapshot, timeout=0)) as origin,
                closing(sqlite3.connect(destination, timeout=0)) as target,
            ):
                # SQLite rolls back an incomplete backup. Never replace just the main file
                # while ignoring its WAL, and never unlink a destination's -wal/-shm files.
                _copy(origin, target, settings.sqlite_busy_timeout_ms)
    except (BackupError, OSError, sqlite3.Error) as error:
        if created:
            destination.unlink(missing_ok=True)
        if isinstance(error, BackupError):
            raise
        raise BackupError(
            "No se pudo restaurar la copia; revisa archivos, permisos y bloqueo."
        ) from None


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Copia y restauración coherente de SQLite.")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Crear una copia en un archivo nuevo.")
    create.add_argument("destination", type=Path)
    restore = commands.add_parser("restore", help="Restaurar a RENTALAB_DATABASE_URL.")
    restore.add_argument("source", type=Path)
    restore.add_argument(
        "--app-stopped", action="store_true", help="Confirma que la aplicación está detenida."
    )
    arguments = parser.parse_args()
    try:
        settings = Settings()
        if arguments.command == "create":
            create_backup(settings, arguments.destination)
            print("Copia SQLite creada y validada.")
        else:
            restore_backup(settings, arguments.source, app_stopped=arguments.app_stopped)
            print("Copia SQLite restaurada. Aplica las migraciones antes de iniciar la aplicación.")
    except BackupError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except ValidationError:
        print("Error: la configuración del entorno no es válida.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
