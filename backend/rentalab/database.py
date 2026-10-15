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

SQLITE_MAX_INTEGER = 2**63 - 1


class Base(DeclarativeBase):
    pass


@contextmanager
def immediate_transaction(session: Session) -> Iterator[None]:
    # sqlite3 legacy mode does not emit BEGIN for SELECT. Lock before all decision reads.
    # Session.begin owns commit/rollback, including a failed BEGIN IMMEDIATE or COMMIT.
    # SQLite waits only up to the connection's busy timeout. Do not replay this body:
    # after a controlled 503 the caller can retry in a new transaction and recheck rules.
    with session.begin():
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        yield


def create_database_engine(database_url: str, *, busy_timeout_ms: int = 5000) -> Engine:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("RentaLab requires a SQLite database")
    if url.database and url.database != ":memory:":
        Path(url.database).resolve().parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        database_url, connect_args={"check_same_thread": False, "timeout": busy_timeout_ms / 1000}
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: SQLiteConnection, _record: ConnectionPoolEntry) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def is_sqlite_busy(error: OperationalError) -> bool:
    error_code = getattr(error.orig, "sqlite_errorcode", 0)
    return (error_code & 0xFF) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
