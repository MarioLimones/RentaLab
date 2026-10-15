import os
import subprocess
import sys
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from conftest import TEST_PASSWORD_HASH, TEST_SESSION_SECRET, TEST_USERNAME
from pydantic import SecretStr

from rentalab.config import Settings
from rentalab.main import create_app


@pytest.mark.parametrize(
    "missing", ["OPERATOR_USERNAME", "OPERATOR_PASSWORD_HASH", "SESSION_SECRET"]
)
def test_missing_required_configuration_fails_before_opening_the_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.delenv(f"RENTALAB_{missing}")
    database = tmp_path / "must-not-be-created.sqlite3"
    settings = Settings(_env_file=None, database_url=f"sqlite:///{database.as_posix()}")
    with pytest.raises(ValueError) as error:
        create_app(settings)
    assert "configuración" in str(error.value)
    assert TEST_PASSWORD_HASH not in str(error.value)
    assert TEST_SESSION_SECRET not in str(error.value)
    assert not database.exists()


@pytest.mark.parametrize(
    "change",
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
def test_invalid_access_configuration_does_not_print_secrets(
    settings: Settings, change: dict[str, object]
) -> None:
    invalid = settings.model_copy(update=change)
    with pytest.raises(ValueError) as error:
        create_app(invalid)
    assert str(error.value) == "La configuración de acceso está ausente o no es válida"
    for secret in [TEST_SESSION_SECRET, TEST_PASSWORD_HASH, "not-an-argon2-hash", "too-short"]:
        assert secret not in str(error.value)


def test_settings_can_be_loaded_without_auth_for_migrations_and_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ["OPERATOR_USERNAME", "OPERATOR_PASSWORD_HASH", "SESSION_SECRET"]:
        monkeypatch.delenv(f"RENTALAB_{name}")
    settings = Settings(_env_file=None)
    assert settings.operator_username is None
    assert settings.operator_password_hash is None
    assert settings.session_secret is None


def test_settings_repr_masks_password_hash_and_session_secret(settings: Settings) -> None:
    representation = repr(settings)
    assert TEST_USERNAME in representation
    assert TEST_PASSWORD_HASH not in representation
    assert TEST_SESSION_SECRET not in representation


def test_password_hash_command_reads_and_confirms_interactively_without_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from rentalab.auth import hash_password

    for name in ["OPERATOR_USERNAME", "OPERATOR_PASSWORD_HASH", "SESSION_SECRET"]:
        monkeypatch.delenv(f"RENTALAB_{name}")
    password = "contraseña-interactiva-ficticia"
    answers = iter([password, password])
    prompts: list[str] = []

    def read_password(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(hash_password.sys, "argv", ["rentalab.auth.hash_password"])
    monkeypatch.setattr(hash_password.getpass, "getpass", read_password)
    assert hash_password.main() == 0
    output = capsys.readouterr()
    encoded = output.out.strip()
    assert encoded.startswith("$argon2id$")
    assert PasswordHasher().verify(encoded, password)
    assert len(prompts) == 2
    assert password not in output.out + output.err


@pytest.mark.parametrize("answers", [["", ""], ["one", "two"]])
def test_password_hash_command_rejects_empty_or_unconfirmed_passwords(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    answers: list[str],
) -> None:
    from rentalab.auth import hash_password

    values = iter(answers)
    monkeypatch.setattr(hash_password.sys, "argv", ["rentalab.auth.hash_password"])
    monkeypatch.setattr(hash_password.getpass, "getpass", lambda _prompt: next(values))
    assert hash_password.main() == 1
    output = capsys.readouterr()
    assert "$argon2" not in output.out
    assert output.err


def test_hash_command_rejects_password_arguments_and_does_not_need_app_configuration() -> None:
    environment = {
        name: value for name, value in os.environ.items() if not name.startswith("RENTALAB_")
    }
    result = subprocess.run(
        [sys.executable, "-m", "rentalab.auth.hash_password", "do-not-print-this-password"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1
    assert "argumentos" in result.stderr
    assert "do-not-print-this-password" not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr
