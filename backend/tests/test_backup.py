import os
import sqlite3
import stat
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from rentalab import backup
from rentalab.backup import BackupError, create_backup, restore_backup
from rentalab.config import Settings


def backup_settings(path: Path, *, timeout_ms: int = 100) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{path.as_posix()}",
        sqlite_busy_timeout_ms=timeout_ms,
    )


def create_database(path: Path, label: str = "Original") -> None:
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("CREATE TABLE equipment (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        connection.execute(
            "CREATE TABLE reservations (id INTEGER PRIMARY KEY, equipment_id INTEGER "
            "REFERENCES equipment(id))"
        )
        connection.execute("CREATE TABLE auth_sessions (id TEXT PRIMARY KEY, expires_at INTEGER)")
        connection.execute("INSERT INTO equipment VALUES (1, ?)", (label,))
        connection.execute("INSERT INTO reservations VALUES (1, 1)")
        connection.execute("INSERT INTO auth_sessions VALUES ('demo-session', 2000000000)")


def rows(path: Path, table: str = "equipment") -> list[tuple[object, ...]]:
    assert table in {"equipment", "reservations", "auth_sessions"}
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "live.sqlite3"
    create_database(path)
    return path


@pytest.fixture
def wal_source(source: Path) -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(source)) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("INSERT INTO equipment VALUES (2, 'Committed in WAL')")
        connection.commit()
        yield connection


def test_backup_includes_uncheckpointed_wal_without_changing_live_data(
    source: Path, wal_source: sqlite3.Connection, tmp_path: Path
) -> None:
    destination = tmp_path / "backup.sqlite3"
    main_bytes = source.read_bytes()
    assert Path(f"{source}-wal").stat().st_size > 0

    create_backup(backup_settings(source), destination)

    assert rows(destination) == [(1, "Original"), (2, "Committed in WAL")]
    assert rows(destination, "reservations") == [(1, 1)]
    assert rows(destination, "auth_sessions") == [("demo-session", 2000000000)]
    assert source.read_bytes() == main_bytes
    assert wal_source.execute("SELECT COUNT(*) FROM equipment").fetchone() == (2,)
    assert not Path(f"{destination}-wal").exists()
    assert not Path(f"{destination}-shm").exists()


def test_backup_does_not_overwrite_existing_file(source: Path, tmp_path: Path) -> None:
    destination = tmp_path / "existing.sqlite3"
    destination.write_bytes(b"Keep the existing backup")

    with pytest.raises(BackupError, match="existe"):
        create_backup(backup_settings(source), destination)

    assert destination.read_bytes() == b"Keep the existing backup"


def test_backup_creates_its_destination_directory(source: Path, tmp_path: Path) -> None:
    destination = tmp_path / "backups" / "nested" / "backup.sqlite3"

    create_backup(backup_settings(source), destination)

    assert rows(destination) == [(1, "Original")]


@pytest.mark.skipif(
    os.name == "nt", reason="Windows uses filesystem ACLs instead of POSIX mode bits."
)
def test_new_backup_and_restore_files_are_private(source: Path, tmp_path: Path) -> None:
    destination = tmp_path / "backups" / "backup.sqlite3"
    restored = tmp_path / "restored" / "rentalab.db"
    previous_umask = os.umask(0)
    try:
        create_backup(backup_settings(source), destination)
        restore_backup(backup_settings(restored), destination, app_stopped=True)
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert stat.S_IMODE(destination.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(restored.stat().st_mode) == 0o600
    assert stat.S_IMODE(restored.parent.stat().st_mode) == 0o700


def test_backup_rejects_same_database(source: Path) -> None:
    with pytest.raises(BackupError, match="mismo|existe"):
        create_backup(backup_settings(source), source)
    assert rows(source) == [(1, "Original")]


@pytest.mark.parametrize("contents", [None, b"", b"not a SQLite database"])
def test_invalid_source_leaves_no_backup(tmp_path: Path, contents: bytes | None) -> None:
    source = tmp_path / "invalid.sqlite3"
    if contents is not None:
        source.write_bytes(contents)
    destination = tmp_path / "backup.sqlite3"

    with pytest.raises(BackupError):
        create_backup(backup_settings(source), destination)

    assert not destination.exists()
    assert set(tmp_path.iterdir()) <= {source}


def test_backup_rejects_foreign_key_violations(source: Path, tmp_path: Path) -> None:
    with closing(sqlite3.connect(source)) as connection, connection:
        connection.execute("INSERT INTO reservations VALUES (2, 999)")
    destination = tmp_path / "backup.sqlite3"

    with pytest.raises(BackupError, match="integridad"):
        create_backup(backup_settings(source), destination)

    assert not destination.exists()
    assert rows(source, "reservations") == [(1, 1), (2, 999)]


def test_restore_requires_explicit_stopped_application(source: Path, tmp_path: Path) -> None:
    destination = tmp_path / "restored.sqlite3"
    with pytest.raises(BackupError, match="detenida|app-stopped"):
        restore_backup(backup_settings(destination), source)
    assert not destination.exists()


def test_restore_to_new_database_preserves_all_tables(source: Path, tmp_path: Path) -> None:
    destination = tmp_path / "restored.sqlite3"

    restore_backup(backup_settings(destination), source, app_stopped=True)

    assert rows(destination) == rows(source)
    assert rows(destination, "reservations") == rows(source, "reservations")
    assert rows(destination, "auth_sessions") == rows(source, "auth_sessions")
    with closing(sqlite3.connect(destination)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_restore_replaces_existing_database_transactionally(source: Path, tmp_path: Path) -> None:
    destination = tmp_path / "restored.sqlite3"
    create_database(destination, "Previous target")

    restore_backup(backup_settings(destination), source, app_stopped=True)

    assert rows(destination) == [(1, "Original")]
    assert rows(source) == [(1, "Original")]
    assert {path.name for path in tmp_path.iterdir()} == {source.name, destination.name}


def test_restore_replaces_existing_wal_without_replaying_old_pages(
    source: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "destination.sqlite3"
    create_database(destination, "Old main database")
    with closing(sqlite3.connect(destination)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("INSERT INTO equipment VALUES (2, 'Old committed WAL')")
        connection.commit()
        assert Path(f"{destination}-wal").stat().st_size > 0

        restore_backup(backup_settings(destination), source, app_stopped=True)

        assert connection.execute("SELECT * FROM equipment").fetchall() == [(1, "Original")]
    assert rows(destination) == [(1, "Original")]


def test_interrupted_restore_rolls_back_destination_pages(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "destination.sqlite3"
    create_database(destination, "Preserve this target")
    original_copy = backup._copy
    copies = 0

    def interrupt_restoration(
        origin: sqlite3.Connection, target: sqlite3.Connection, timeout_ms: int
    ) -> None:
        nonlocal copies
        copies += 1
        if copies == 1:
            original_copy(origin, target, timeout_ms)
            return

        def interrupt(status: int, _remaining: int, _total: int) -> None:
            assert status == sqlite3.SQLITE_OK  # A real page transfer, before COMMIT.
            raise BackupError("Copia interrumpida durante la restauración.")

        origin.backup(target, pages=1, progress=interrupt)

    monkeypatch.setattr(backup, "_copy", interrupt_restoration)
    with pytest.raises(BackupError, match="interrumpida"):
        restore_backup(backup_settings(destination), source, app_stopped=True)

    assert rows(destination) == [(1, "Preserve this target")]
    assert rows(destination, "reservations") == [(1, 1)]
    assert {path.name for path in tmp_path.iterdir()} == {source.name, destination.name}


def test_restore_invalid_source_preserves_existing_destination(
    source: Path, tmp_path: Path
) -> None:
    invalid = tmp_path / "invalid.sqlite3"
    invalid.write_bytes(b"private invalid content")
    original_bytes = source.read_bytes()

    with pytest.raises(BackupError):
        restore_backup(backup_settings(source), invalid, app_stopped=True)

    assert source.read_bytes() == original_bytes
    assert rows(source) == [(1, "Original")]


def test_restore_rejects_itself(source: Path) -> None:
    with pytest.raises(BackupError, match="mismo"):
        restore_backup(backup_settings(source), source, app_stopped=True)
    assert rows(source) == [(1, "Original")]


def test_busy_backup_is_bounded_and_does_not_publish_partial_file(
    source: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "backup.sqlite3"
    with closing(sqlite3.connect(source)) as blocker:
        blocker.execute("BEGIN EXCLUSIVE")
        started = time.monotonic()
        with pytest.raises(BackupError, match="bloquead"):
            create_backup(backup_settings(source, timeout_ms=50), destination)
        assert time.monotonic() - started < 2
        blocker.rollback()

    assert not destination.exists()
    assert rows(source) == [(1, "Original")]


def test_busy_restore_preserves_destination_and_its_committed_wal(
    source: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "destination.sqlite3"
    create_database(destination, "Previous target")
    with closing(sqlite3.connect(destination)) as blocker:
        blocker.execute("PRAGMA journal_mode=WAL")
        blocker.execute("PRAGMA wal_autocheckpoint=0")
        blocker.execute("INSERT INTO equipment VALUES (2, 'Target WAL')")
        blocker.commit()
        wal_bytes = Path(f"{destination}-wal").read_bytes()
        blocker.execute("BEGIN IMMEDIATE")
        started = time.monotonic()

        with pytest.raises(BackupError, match="bloquead"):
            restore_backup(backup_settings(destination, timeout_ms=50), source, app_stopped=True)

        assert time.monotonic() - started < 2
        assert Path(f"{destination}-wal").read_bytes() == wal_bytes
        blocker.rollback()
        assert blocker.execute("SELECT * FROM equipment ORDER BY id").fetchall() == [
            (1, "Previous target"),
            (2, "Target WAL"),
        ]


@pytest.mark.parametrize("url", ["sqlite:///:memory:", "postgresql://localhost/demo"])
def test_only_file_sqlite_is_supported(url: str, tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="SQLite|archivo"):
        create_backup(Settings(_env_file=None, database_url=url), tmp_path / "backup.sqlite3")


def test_cli_creates_and_restores_backup(source: Path, tmp_path: Path) -> None:
    destination = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored.sqlite3"
    environment = dict(os.environ, RENTALAB_DATABASE_URL=backup_settings(source).database_url)
    created = subprocess.run(
        [sys.executable, "-m", "rentalab.backup", "create", str(destination)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    environment["RENTALAB_DATABASE_URL"] = backup_settings(restored).database_url
    restored_result = subprocess.run(
        [sys.executable, "-m", "rentalab.backup", "restore", str(destination), "--app-stopped"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert restored_result.returncode == 0, restored_result.stderr
    assert rows(restored) == [(1, "Original")]


def test_cli_errors_are_controlled_without_internal_trace(source: Path, tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.sqlite3"
    invalid.write_bytes(b"private invalid content")
    result = subprocess.run(
        [sys.executable, "-m", "rentalab.backup", "restore", str(invalid), "--app-stopped"],
        capture_output=True,
        text=True,
        env=dict(os.environ, RENTALAB_DATABASE_URL=backup_settings(source).database_url),
        check=False,
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "private invalid content" not in result.stderr
    assert rows(source) == [(1, "Original")]
