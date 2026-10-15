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

from rentalab import copias_seguridad
from rentalab.configuracion import Configuracion
from rentalab.copias_seguridad import (
    CopiasSeguridadError,
    crear_copias_seguridad,
    restaurar_copias_seguridad,
)


def copias_seguridad_configuracion(ruta: Path, *, espera_ms: int = 100) -> Configuracion:
    return Configuracion(
        _env_file=None,
        url_base_datos=f"sqlite:///{ruta.as_posix()}",
        espera_sqlite_ocupado_ms=espera_ms,
    )


def crear_base_datos(ruta: Path, etiqueta: str = "Original") -> None:
    with closing(sqlite3.connect(ruta)) as conexion, conexion:
        conexion.execute("PRAGMA foreign_keys=ON")
        conexion.execute("CREATE TABLE equipment (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        conexion.execute(
            "CREATE TABLE reservations (id INTEGER PRIMARY KEY, equipment_id INTEGER "
            "REFERENCES equipment(id))"
        )
        conexion.execute("CREATE TABLE auth_sessions (id TEXT PRIMARY KEY, expires_at INTEGER)")
        conexion.execute("INSERT INTO equipment VALUES (1, ?)", (etiqueta,))
        conexion.execute("INSERT INTO reservations VALUES (1, 1)")
        conexion.execute("INSERT INTO auth_sessions VALUES ('demo-session', 2000000000)")


def filas(ruta: Path, tabla: str = "equipment") -> list[tuple[object, ...]]:
    assert tabla in {"equipment", "reservations", "auth_sessions"}
    with closing(sqlite3.connect(ruta)) as conexion:
        return conexion.execute(f"SELECT * FROM {tabla} ORDER BY 1").fetchall()


@pytest.fixture
def fuente(tmp_path: Path) -> Path:
    ruta = tmp_path / "live.sqlite3"
    crear_base_datos(ruta)
    return ruta


@pytest.fixture
def wal_origen(fuente: Path) -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(fuente)) as conexion:
        assert conexion.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        conexion.execute("PRAGMA wal_autocheckpoint=0")
        conexion.execute("INSERT INTO equipment VALUES (2, 'Committed in WAL')")
        conexion.commit()
        yield conexion


def test_copias_seguridad_incluye_sin_consolidar_wal_sin_cambiando_vigente_datos(
    fuente: Path, wal_origen: sqlite3.Connection, tmp_path: Path
) -> None:
    destino = tmp_path / "backup.sqlite3"
    principal_bytes = fuente.read_bytes()
    assert Path(f"{fuente}-wal").stat().st_size > 0

    crear_copias_seguridad(copias_seguridad_configuracion(fuente), destino)

    assert filas(destino) == [(1, "Original"), (2, "Committed in WAL")]
    assert filas(destino, "reservations") == [(1, 1)]
    assert filas(destino, "auth_sessions") == [("demo-session", 2000000000)]
    assert fuente.read_bytes() == principal_bytes
    assert wal_origen.execute("SELECT COUNT(*) FROM equipment").fetchone() == (2,)
    assert not Path(f"{destino}-wal").exists()
    assert not Path(f"{destino}-shm").exists()


def test_copias_seguridad_hace_no_sobrescribir_existentes_archivo(
    fuente: Path, tmp_path: Path
) -> None:
    destino = tmp_path / "existing.sqlite3"
    destino.write_bytes(b"Keep the existing backup")

    with pytest.raises(CopiasSeguridadError, match="existe"):
        crear_copias_seguridad(copias_seguridad_configuracion(fuente), destino)

    assert destino.read_bytes() == b"Keep the existing backup"


def test_copias_seguridad_crea_su_destino_directorio(fuente: Path, tmp_path: Path) -> None:
    destino = tmp_path / "backups" / "nested" / "backup.sqlite3"

    crear_copias_seguridad(copias_seguridad_configuracion(fuente), destino)

    assert filas(destino) == [(1, "Original")]


@pytest.mark.skipif(
    os.name == "nt", reason="Windows usa permisos ACL en lugar de bits de modo POSIX."
)
def test_nuevo_copias_seguridad_y_restaurar_archivos_son_privado(
    fuente: Path, tmp_path: Path
) -> None:
    destino = tmp_path / "backups" / "backup.sqlite3"
    restaurado = tmp_path / "restored" / "rentalab.db"
    anterior_umask = os.umask(0)
    try:
        crear_copias_seguridad(copias_seguridad_configuracion(fuente), destino)
        restaurar_copias_seguridad(
            copias_seguridad_configuracion(restaurado), destino, aplicacion_detenida=True
        )
    finally:
        os.umask(anterior_umask)

    assert stat.S_IMODE(destino.stat().st_mode) == 0o600
    assert stat.S_IMODE(destino.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(restaurado.stat().st_mode) == 0o600
    assert stat.S_IMODE(restaurado.parent.stat().st_mode) == 0o700


def test_copias_seguridad_rechaza_mismo_base_datos(fuente: Path) -> None:
    with pytest.raises(CopiasSeguridadError, match="mismo|existe"):
        crear_copias_seguridad(copias_seguridad_configuracion(fuente), fuente)
    assert filas(fuente) == [(1, "Original")]


@pytest.mark.parametrize("contenidos", [None, b"", b"not a SQLite database"])
def test_invalido_origen_deja_sin_copias_seguridad(
    tmp_path: Path, contenidos: bytes | None
) -> None:
    fuente = tmp_path / "invalid.sqlite3"
    if contenidos is not None:
        fuente.write_bytes(contenidos)
    destino = tmp_path / "backup.sqlite3"

    with pytest.raises(CopiasSeguridadError):
        crear_copias_seguridad(copias_seguridad_configuracion(fuente), destino)

    assert not destino.exists()
    assert set(tmp_path.iterdir()) <= {fuente}


def test_copias_seguridad_rechaza_ajena_clave_infracciones(fuente: Path, tmp_path: Path) -> None:
    with closing(sqlite3.connect(fuente)) as conexion, conexion:
        conexion.execute("INSERT INTO reservations VALUES (2, 999)")
    destino = tmp_path / "backup.sqlite3"

    with pytest.raises(CopiasSeguridadError, match="integridad"):
        crear_copias_seguridad(copias_seguridad_configuracion(fuente), destino)

    assert not destino.exists()
    assert filas(fuente, "reservations") == [(1, 1), (2, 999)]


def test_restaurar_requiere_explicito_detenida_aplicacion(fuente: Path, tmp_path: Path) -> None:
    destino = tmp_path / "restored.sqlite3"
    with pytest.raises(CopiasSeguridadError, match="detenida|app-stopped"):
        restaurar_copias_seguridad(copias_seguridad_configuracion(destino), fuente)
    assert not destino.exists()


def test_restaurar_a_nuevo_base_datos_preserva_todos_tablas(fuente: Path, tmp_path: Path) -> None:
    destino = tmp_path / "restored.sqlite3"

    restaurar_copias_seguridad(
        copias_seguridad_configuracion(destino), fuente, aplicacion_detenida=True
    )

    assert filas(destino) == filas(fuente)
    assert filas(destino, "reservations") == filas(fuente, "reservations")
    assert filas(destino, "auth_sessions") == filas(fuente, "auth_sessions")
    with closing(sqlite3.connect(destino)) as conexion:
        assert conexion.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert conexion.execute("PRAGMA foreign_key_check").fetchall() == []


def test_restaurar_reemplaza_existentes_base_datos_transaccionalmente(
    fuente: Path, tmp_path: Path
) -> None:
    destino = tmp_path / "restored.sqlite3"
    crear_base_datos(destino, "Previous target")

    restaurar_copias_seguridad(
        copias_seguridad_configuracion(destino), fuente, aplicacion_detenida=True
    )

    assert filas(destino) == [(1, "Original")]
    assert filas(fuente) == [(1, "Original")]
    assert {ruta.name for ruta in tmp_path.iterdir()} == {fuente.name, destino.name}


def test_restaurar_reemplaza_existentes_wal_sin_repitiendo_antiguo_paginas(
    fuente: Path, tmp_path: Path
) -> None:
    destino = tmp_path / "destination.sqlite3"
    crear_base_datos(destino, "Old main database")
    with closing(sqlite3.connect(destino)) as conexion:
        conexion.execute("PRAGMA journal_mode=WAL")
        conexion.execute("PRAGMA wal_autocheckpoint=0")
        conexion.execute("INSERT INTO equipment VALUES (2, 'Old committed WAL')")
        conexion.commit()
        assert Path(f"{destino}-wal").stat().st_size > 0

        restaurar_copias_seguridad(
            copias_seguridad_configuracion(destino), fuente, aplicacion_detenida=True
        )

        assert conexion.execute("SELECT * FROM equipment").fetchall() == [(1, "Original")]
    assert filas(destino) == [(1, "Original")]


def test_interrumpida_restaurar_revierte_regreso_destino_paginas(
    fuente: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destino = tmp_path / "destination.sqlite3"
    crear_base_datos(destino, "Preserve this target")
    original_copiar = copias_seguridad._copiar
    copias = 0

    def interrumpir_restauracion(
        origen: sqlite3.Connection, objetivo: sqlite3.Connection, espera_ms: int
    ) -> None:
        nonlocal copias
        copias += 1
        if copias == 1:
            original_copiar(origen, objetivo, espera_ms)
            return

        def interrumpir(estado: int, _restantes: int, _total: int) -> None:
            assert estado == sqlite3.SQLITE_OK  # Una transferencia real de páginas antes de COMMIT.
            raise CopiasSeguridadError("Copia interrumpida durante la restauración.")

        origen.backup(objetivo, pages=1, progress=interrumpir)

    monkeypatch.setattr(copias_seguridad, "_copiar", interrumpir_restauracion)
    with pytest.raises(CopiasSeguridadError, match="interrumpida"):
        restaurar_copias_seguridad(
            copias_seguridad_configuracion(destino), fuente, aplicacion_detenida=True
        )

    assert filas(destino) == [(1, "Preserve this target")]
    assert filas(destino, "reservations") == [(1, 1)]
    assert {ruta.name for ruta in tmp_path.iterdir()} == {fuente.name, destino.name}


def test_restaurar_invalido_origen_preserva_existentes_destino(
    fuente: Path, tmp_path: Path
) -> None:
    invalido = tmp_path / "invalid.sqlite3"
    invalido.write_bytes(b"private invalid content")
    original_bytes = fuente.read_bytes()

    with pytest.raises(CopiasSeguridadError):
        restaurar_copias_seguridad(
            copias_seguridad_configuracion(fuente), invalido, aplicacion_detenida=True
        )

    assert fuente.read_bytes() == original_bytes
    assert filas(fuente) == [(1, "Original")]


def test_restaurar_rechaza_si_mismo(fuente: Path) -> None:
    with pytest.raises(CopiasSeguridadError, match="mismo"):
        restaurar_copias_seguridad(
            copias_seguridad_configuracion(fuente), fuente, aplicacion_detenida=True
        )
    assert filas(fuente) == [(1, "Original")]


def test_ocupado_copias_seguridad_es_limitado_y_hace_no_publicar_parcial_archivo(
    fuente: Path, tmp_path: Path
) -> None:
    destino = tmp_path / "backup.sqlite3"
    with closing(sqlite3.connect(fuente)) as bloqueador:
        bloqueador.execute("BEGIN EXCLUSIVE")
        iniciado = time.monotonic()
        with pytest.raises(CopiasSeguridadError, match="bloquead"):
            crear_copias_seguridad(copias_seguridad_configuracion(fuente, espera_ms=50), destino)
        assert time.monotonic() - iniciado < 2
        bloqueador.rollback()

    assert not destino.exists()
    assert filas(fuente) == [(1, "Original")]


def test_ocupado_restaurar_preserva_destino_y_su_confirmado_wal(
    fuente: Path, tmp_path: Path
) -> None:
    destino = tmp_path / "destination.sqlite3"
    crear_base_datos(destino, "Previous target")
    with closing(sqlite3.connect(destino)) as bloqueador:
        bloqueador.execute("PRAGMA journal_mode=WAL")
        bloqueador.execute("PRAGMA wal_autocheckpoint=0")
        bloqueador.execute("INSERT INTO equipment VALUES (2, 'Target WAL')")
        bloqueador.commit()
        wal_bytes = Path(f"{destino}-wal").read_bytes()
        bloqueador.execute("BEGIN IMMEDIATE")
        iniciado = time.monotonic()

        with pytest.raises(CopiasSeguridadError, match="bloquead"):
            restaurar_copias_seguridad(
                copias_seguridad_configuracion(destino, espera_ms=50),
                fuente,
                aplicacion_detenida=True,
            )

        assert time.monotonic() - iniciado < 2
        assert Path(f"{destino}-wal").read_bytes() == wal_bytes
        bloqueador.rollback()
        assert bloqueador.execute("SELECT * FROM equipment ORDER BY id").fetchall() == [
            (1, "Previous target"),
            (2, "Target WAL"),
        ]


@pytest.mark.parametrize("url", ["sqlite:///:memory:", "postgresql://localhost/demo"])
def test_solo_archivo_sqlite_es_compatible(url: str, tmp_path: Path) -> None:
    with pytest.raises(CopiasSeguridadError, match="SQLite|archivo"):
        crear_copias_seguridad(
            Configuracion(_env_file=None, url_base_datos=url), tmp_path / "backup.sqlite3"
        )


def test_cli_crea_y_restaura_copias_seguridad(fuente: Path, tmp_path: Path) -> None:
    destino = tmp_path / "backup.sqlite3"
    restaurado = tmp_path / "restored.sqlite3"
    entorno = dict(
        os.environ, RENTALAB_DATABASE_URL=copias_seguridad_configuracion(fuente).url_base_datos
    )
    creados = subprocess.run(
        [sys.executable, "-m", "rentalab.copias_seguridad", "create", str(destino)],
        capture_output=True,
        text=True,
        env=entorno,
        check=False,
    )
    assert creados.returncode == 0, creados.stderr
    entorno["RENTALAB_DATABASE_URL"] = copias_seguridad_configuracion(restaurado).url_base_datos
    restaurado_resultado = subprocess.run(
        [
            sys.executable,
            "-m",
            "rentalab.copias_seguridad",
            "restore",
            str(destino),
            "--app-stopped",
        ],
        capture_output=True,
        text=True,
        env=entorno,
        check=False,
    )
    assert restaurado_resultado.returncode == 0, restaurado_resultado.stderr
    assert filas(restaurado) == [(1, "Original")]


def test_cli_errores_son_controlados_sin_internas_traza(fuente: Path, tmp_path: Path) -> None:
    invalido = tmp_path / "invalid.sqlite3"
    invalido.write_bytes(b"private invalid content")
    resultado = subprocess.run(
        [
            sys.executable,
            "-m",
            "rentalab.copias_seguridad",
            "restore",
            str(invalido),
            "--app-stopped",
        ],
        capture_output=True,
        text=True,
        env=dict(
            os.environ, RENTALAB_DATABASE_URL=copias_seguridad_configuracion(fuente).url_base_datos
        ),
        check=False,
    )
    assert resultado.returncode != 0
    assert "Traceback" not in resultado.stderr
    assert "private invalid content" not in resultado.stderr
    assert filas(fuente) == [(1, "Original")]
