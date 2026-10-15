"""
Instantáneas coherentes de SQLite. Restaurar exige detener todos los procesos de la aplicación.
"""

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

from rentalab.configuracion import Configuracion


class CopiasSeguridadError(Exception):
    """Error de copia comprensible sin datos de la base ni detalles internos de la excepción."""


def _base_datos_ruta(ajustes: Configuracion) -> Path:
    try:
        url = make_url(ajustes.url_base_datos)
    except ArgumentError:
        raise CopiasSeguridadError("La configuración debe indicar un archivo SQLite.") from None
    if (
        url.get_backend_name() != "sqlite"
        or not url.database
        or url.database == ":memory:"
        or url.query
    ):
        raise CopiasSeguridadError("La configuración debe indicar un archivo SQLite.")
    return Path(url.database).resolve()


def _validar_origen(ruta: Path) -> None:
    if not ruta.is_file():
        raise CopiasSeguridadError("No existe el archivo SQLite de origen.")
    with ruta.open("rb") as flujo:
        if flujo.read(16) != b"SQLite format 3\x00":
            raise CopiasSeguridadError("El origen no es un archivo SQLite válido.")


def _copiar(fuente: sqlite3.Connection, destino: sqlite3.Connection, espera_ms: int) -> None:
    limite_temporal = time.monotonic() + espera_ms / 1000

    def progreso(estado: int, _restantes: int, _total: int) -> None:
        # sqlite3.backup reintenta SQLITE_BUSY indefinidamente si no se limita el tiempo aquí.
        if estado != sqlite3.SQLITE_DONE and time.monotonic() >= limite_temporal:
            raise CopiasSeguridadError(
                "La base está bloqueada o la copia agotó el tiempo de espera."
            )

    fuente.backup(destino, pages=256, progress=progreso, sleep=0.05)


def _validar_instantanea(conexion: sqlite3.Connection) -> None:
    if (
        conexion.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
        or conexion.execute("PRAGMA foreign_key_check").fetchone() is not None
    ):
        raise CopiasSeguridadError("La copia no supera las comprobaciones de integridad de SQLite.")


@contextmanager
def _instantanea(fuente: Path, directorio: Path, espera_ms: int) -> Iterator[Path]:
    _validar_origen(fuente)
    descriptor, temporal_nombre = tempfile.mkstemp(prefix=".rentalab-backup-", dir=directorio)
    os.close(descriptor)
    temporal_ruta = Path(temporal_nombre)
    try:
        # mode=ro no crea un origen ausente; SQLite lee las páginas confirmadas del WAL.
        with (
            closing(sqlite3.connect(f"{fuente.as_uri()}?mode=ro", uri=True, timeout=0)) as origen,
            closing(sqlite3.connect(temporal_ruta, timeout=0)) as destino,
        ):
            _copiar(origen, destino, espera_ms)
            _validar_instantanea(destino)
            # Publica una instantánea autónoma, sin archivos auxiliares que transportar.
            destino.execute("PRAGMA journal_mode=DELETE")
        yield temporal_ruta
    finally:
        temporal_ruta.unlink(missing_ok=True)


def crear_copias_seguridad(ajustes: Configuracion, destino: Path) -> None:
    """Copia una base activa a un archivo nuevo sin sustituir una copia existente."""
    fuente = _base_datos_ruta(ajustes)
    destino = destino.absolute()
    try:
        if os.path.lexists(destino):
            raise CopiasSeguridadError("El archivo de destino ya existe; elige un nombre nuevo.")
        destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with _instantanea(fuente, destino.parent, ajustes.espera_sqlite_ocupado_ms) as instantanea:
            # El enlace publica el archivo completo atómicamente y falla si otro
            # escritor se adelanta.
            os.link(instantanea, destino)
    except FileExistsError:
        raise CopiasSeguridadError(
            "El archivo de destino ya existe; elige un nombre nuevo."
        ) from None
    except (OSError, sqlite3.Error):
        raise CopiasSeguridadError(
            "No se pudo crear la copia; revisa el origen, directorio y permisos."
        ) from None


def restaurar_copias_seguridad(
    ajustes: Configuracion, fuente: Path, *, aplicacion_detenida: bool = False
) -> None:
    """Restaura con la transacción atómica de SQLite sin tocar los archivos auxiliares activos."""
    if not aplicacion_detenida:
        raise CopiasSeguridadError(
            "Detén la aplicación y confirma con --app-stopped que está detenida."
        )
    destino = _base_datos_ruta(ajustes)
    fuente = fuente.resolve()
    if fuente == destino:
        raise CopiasSeguridadError("El origen y el destino no pueden ser el mismo archivo.")
    creados = False
    try:
        destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with _instantanea(fuente, destino.parent, ajustes.espera_sqlite_ocupado_ms) as instantanea:
            try:
                # Reservar un destino nuevo identifica el archivo vacío que puede
                # eliminarse al fallar.
                descriptor = os.open(destino, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                creados = True
                os.close(descriptor)
            except FileExistsError:
                pass
            with (
                closing(sqlite3.connect(instantanea, timeout=0)) as origen,
                closing(sqlite3.connect(destino, timeout=0)) as objetivo,
            ):
                # SQLite revierte una copia incompleta. Nunca sustituyas solo el archivo principal
                # ignorando su WAL ni elimines los archivos -wal/-shm del destino.
                _copiar(origen, objetivo, ajustes.espera_sqlite_ocupado_ms)
    except (CopiasSeguridadError, OSError, sqlite3.Error) as error:
        if creados:
            destino.unlink(missing_ok=True)
        if isinstance(error, CopiasSeguridadError):
            raise
        raise CopiasSeguridadError(
            "No se pudo restaurar la copia; revisa archivos, permisos y bloqueo."
        ) from None


def principal() -> int:
    os.umask(0o077)
    analizador = argparse.ArgumentParser(description="Copia y restauración coherente de SQLite.")
    comandos = analizador.add_subparsers(dest="accion", required=True)
    crear = comandos.add_parser("create", help="Crear una copia en un archivo nuevo.")
    crear.add_argument("destino", type=Path)
    restaurar = comandos.add_parser("restore", help="Restaurar a RENTALAB_DATABASE_URL.")
    restaurar.add_argument("fuente", type=Path)
    restaurar.add_argument(
        "--app-stopped",
        dest="aplicacion_detenida",
        action="store_true",
        help="Confirma que la aplicación está detenida.",
    )
    argumentos = analizador.parse_args()
    try:
        ajustes = Configuracion()
        if argumentos.accion == "create":
            crear_copias_seguridad(ajustes, argumentos.destino)
            print("Copia SQLite creada y validada.")
        else:
            restaurar_copias_seguridad(
                ajustes, argumentos.fuente, aplicacion_detenida=argumentos.aplicacion_detenida
            )
            print("Copia SQLite restaurada. Aplica las migraciones antes de iniciar la aplicación.")
    except CopiasSeguridadError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except ValidationError:
        print("Error: la configuración del entorno no es válida.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
