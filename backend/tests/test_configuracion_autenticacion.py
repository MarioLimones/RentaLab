import os
import subprocess
import sys
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from conftest import PRUEBA_CONTRASENA_HASH, PRUEBA_NOMBRE_USUARIO, PRUEBA_SESION_SECRETO
from pydantic import SecretStr

from rentalab.compatibilidad import nombre_interno
from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion


@pytest.mark.parametrize(
    "ausente", ["OPERATOR_USERNAME", "OPERATOR_PASSWORD_HASH", "SESSION_SECRET"]
)
def test_ausente_requerido_configuracion_falla_antes_abrir_la_base_datos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ausente: str
) -> None:
    monkeypatch.delenv(f"RENTALAB_{ausente}")
    base_datos = tmp_path / "must-not-be-created.sqlite3"
    ajustes = Configuracion(_env_file=None, url_base_datos=f"sqlite:///{base_datos.as_posix()}")
    with pytest.raises(ValueError) as error:
        crear_aplicacion(ajustes)
    assert "configuración" in str(error.value)
    assert PRUEBA_CONTRASENA_HASH not in str(error.value)
    assert PRUEBA_SESION_SECRETO not in str(error.value)
    assert not base_datos.exists()


@pytest.mark.parametrize(
    "cambiar",
    [
        {"operator_username": "   "},
        {"operator_username": "invalid\x00username"},
        {"operator_password_hash": SecretStr("not-an-argon2-hash")},
        {
            "operator_password_hash": SecretStr(
                "$argon2id$v=19$m=1024,t=1,p=1$M0uxu008I9cVMtVI1lJVI!$"
                "TWtoGdyQCFGn+imYQmWNS0CGuDzuMqgyVlKVyZeVvn!"
            )
        },
        {"session_secret": SecretStr("too-short")},
        {"session_secret": SecretStr(" " * 32)},
    ],
)
def test_configuracion_de_acceso_invalida_no_imprime_secretos(
    ajustes: Configuracion, cambiar: dict[str, object]
) -> None:
    invalido = ajustes.model_copy(
        update={nombre_interno(clave): valor for clave, valor in cambiar.items()}
    )
    with pytest.raises(ValueError) as error:
        crear_aplicacion(invalido)
    assert str(error.value) == "La configuración de acceso está ausente o no es válida"
    for secreto in [
        PRUEBA_SESION_SECRETO,
        PRUEBA_CONTRASENA_HASH,
        "not-an-argon2-hash",
        "too-short",
    ]:
        assert secreto not in str(error.value)


def test_configuracion_puede_ser_cargada_sin_autenticacion_para_migraciones_y_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for nombre in ["OPERATOR_USERNAME", "OPERATOR_PASSWORD_HASH", "SESSION_SECRET"]:
        monkeypatch.delenv(f"RENTALAB_{nombre}")
    ajustes = Configuracion(_env_file=None)
    assert ajustes.usuario_operador is None
    assert ajustes.hash_contrasena_operador is None
    assert ajustes.secreto_sesion is None


def test_configuracion_repr_oculta_contrasena_hash_y_sesion_secreto(
    ajustes: Configuracion,
) -> None:
    representacion = repr(ajustes)
    assert PRUEBA_NOMBRE_USUARIO in representacion
    assert PRUEBA_CONTRASENA_HASH not in representacion
    assert PRUEBA_SESION_SECRETO not in representacion


def test_contrasena_hash_comando_lecturas_y_confirma_interactivamente_sin_configuracion(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from rentalab.autenticacion import hash_contrasena

    for nombre in ["OPERATOR_USERNAME", "OPERATOR_PASSWORD_HASH", "SESSION_SECRET"]:
        monkeypatch.delenv(f"RENTALAB_{nombre}")
    contrasena = "contraseña-interactiva-ficticia"
    respuestas = iter([contrasena, contrasena])
    mensajes: list[str] = []

    def lectura_contrasena(mensaje: str) -> str:
        mensajes.append(mensaje)
        return next(respuestas)

    monkeypatch.setattr(hash_contrasena.sys, "argv", ["rentalab.autenticacion.hash_contrasena"])
    monkeypatch.setattr(hash_contrasena.getpass, "getpass", lectura_contrasena)
    assert hash_contrasena.principal() == 0
    salida = capsys.readouterr()
    codificado = salida.out.strip()
    assert codificado.startswith("$argon2id$")
    assert PasswordHasher().verify(codificado, contrasena)
    assert len(mensajes) == 2
    assert contrasena not in salida.out + salida.err


@pytest.mark.parametrize("respuestas", [["", ""], ["one", "two"]])
def test_contrasena_hash_comando_rechaza_vacio_o_sin_confirmar_contrasenas(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    respuestas: list[str],
) -> None:
    from rentalab.autenticacion import hash_contrasena

    valores = iter(respuestas)
    monkeypatch.setattr(hash_contrasena.sys, "argv", ["rentalab.autenticacion.hash_contrasena"])
    monkeypatch.setattr(hash_contrasena.getpass, "getpass", lambda _mensaje: next(valores))
    assert hash_contrasena.principal() == 1
    salida = capsys.readouterr()
    assert "$argon2" not in salida.out
    assert salida.err


def test_comando_hash_rechaza_argumentos_y_funciona_sin_configuracion() -> None:
    entorno = {
        nombre: valor for nombre, valor in os.environ.items() if not nombre.startswith("RENTALAB_")
    }
    resultado = subprocess.run(
        [
            sys.executable,
            "-m",
            "rentalab.autenticacion.hash_contrasena",
            "do-not-print-this-password",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=entorno,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert resultado.returncode == 1
    assert "argumentos" in resultado.stderr
    assert "do-not-print-this-password" not in resultado.stdout + resultado.stderr
    assert "Traceback" not in resultado.stderr
