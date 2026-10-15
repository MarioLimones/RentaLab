import base64
import binascii
from pathlib import Path
from typing import Literal

from argon2 import extract_parameters
from argon2.exceptions import InvalidHashError
from argon2.low_level import Type
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RENTALAB_",
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'data' / 'rentalab.db').as_posix()}"
    frontend_dist: Path | None = None
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=0, le=60000)
    operator_username: str | None = None
    operator_password_hash: SecretStr | None = None
    session_secret: SecretStr | None = None
    session_ttl_seconds: int = Field(default=3600, ge=1, le=86400)
    port: int = Field(default=8000, ge=1, le=65535)
    forwarded_allow_ips: str = Field(default="127.0.0.1", min_length=1, max_length=1024)

    def require_auth(self) -> None:
        """Validate application access without requiring it for migrations or CLI tools."""
        message = "La configuración de acceso está ausente o no es válida"
        if self.session_secret is None or len(self.session_secret.get_secret_value().strip()) < 32:
            raise ValueError(message)
        legacy_username = self.operator_username or ""
        legacy_hash = (
            self.operator_password_hash.get_secret_value()
            if self.operator_password_hash is not None
            else ""
        )
        if not legacy_username and not legacy_hash:
            return
        if (
            not legacy_username.strip()
            or len(legacy_username) > 120
            or "\x00" in legacy_username
            or not legacy_hash
        ):
            raise ValueError(message)
        try:
            encoded_hash = legacy_hash
            parameters = extract_parameters(encoded_hash)
            # extract_parameters parses settings but does not validate the encoded salt/digest.
            for component in encoded_hash.split("$")[-2:]:
                decoded = base64.b64decode(component + "=" * (-len(component) % 4), validate=True)
                if base64.b64encode(decoded).decode("ascii").rstrip("=") != component:
                    raise ValueError
        except (InvalidHashError, ValueError, TypeError, binascii.Error):
            raise ValueError(message) from None
        if (
            parameters.type is not Type.ID
            or parameters.version != 19
            or parameters.salt_len < 8
            or parameters.hash_len < 16
            or parameters.parallelism < 1
            or parameters.time_cost < 1
            or parameters.memory_cost < 8 * parameters.parallelism
        ):
            raise ValueError(message)
