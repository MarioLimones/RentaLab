import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from sqlite3 import Connection as SQLiteConnection

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import ConnectionPoolEntry

SQLITE_ENTERO_MAXIMO = 2**63 - 1


class Base(DeclarativeBase):
    pass


@contextmanager
def inmediata_transaccion(sesion: Session) -> Iterator[None]:
    # El modo heredado de sqlite3 no emite BEGIN para SELECT: bloquea antes de decidir.
    # Session.begin controla la confirmación/reversión, incluso si BEGIN IMMEDIATE o COMMIT falla.
    # SQLite limita la espera de la conexión ocupada. No repitas este cuerpo:
    # tras un 503 controlado puede abrirse otra transacción y comprobar de nuevo las reglas.
    with sesion.begin():
        sesion.connection().exec_driver_sql("BEGIN IMMEDIATE")
        yield


def crear_base_datos_motor(url_base_datos: str, *, ocupado_espera_ms: int = 5000) -> Engine:
    url = make_url(url_base_datos)
    if url.get_backend_name() != "sqlite":
        raise ValueError("RentaLab requires a SQLite database")
    if url.database and url.database != ":memory:":
        Path(url.database).resolve().parent.mkdir(parents=True, exist_ok=True)
    motor = create_engine(
        url_base_datos,
        connect_args={"check_same_thread": False, "timeout": ocupado_espera_ms / 1000},
    )

    @event.listens_for(motor, "connect")
    def activar_ajena_claves(conexion: SQLiteConnection, _registro: ConnectionPoolEntry) -> None:
        cursor = conexion.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return motor


def es_sqlite_ocupado(error: OperationalError) -> bool:
    error_codigo = getattr(error.orig, "sqlite_errorcode", 0)
    return (error_codigo & 0xFF) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
