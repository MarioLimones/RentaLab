import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from hmac import compare_digest
from typing import cast

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from rentalab.auth.models import AuthSession, User
from rentalab.auth.schemas import (
    AuthSessionRead,
    RegisterRequest,
    UserRead,
    UserRole,
    normalize_email,
)
from rentalab.config import Settings
from rentalab.database import immediate_transaction


def current_timestamp() -> int:
    return int(time.time())


def user_credential_version(user: User) -> str:
    # Roles and profile fields are read afresh; a password change revokes sessions.
    return hashlib.sha256(json.dumps([user.id, user.password_hash]).encode("utf-8")).hexdigest()


class DuplicateUserEmail(Exception):
    pass


@dataclass(frozen=True)
class SessionIdentity:
    id: str
    username: str
    expires_at: int
    user_id: int | None = None
    name: str | None = None
    email: str | None = None
    role: UserRole = "admin"
    active: bool = True

    def to_response(self) -> AuthSessionRead:
        user = None
        if self.user_id is not None:
            assert self.name is not None and self.email is not None
            user = UserRead(
                id=self.user_id,
                name=self.name,
                email=self.email,
                role=self.role,
                active=self.active,
            )
        return AuthSessionRead(
            username=self.username,
            expires_at=datetime.fromtimestamp(self.expires_at, tz=UTC),
            role=self.role,
            user=user,
        )


class AuthService:
    def __init__(self, settings: Settings, session_factory: sessionmaker[Session]) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.username = (settings.operator_username or "").strip()
        self.password_hash = (
            settings.operator_password_hash.get_secret_value()
            if settings.operator_password_hash is not None
            and settings.operator_password_hash.get_secret_value()
            else None
        )
        # Preserve the exact 0005 fingerprint and legacy operator sessions.
        self.credential_version = hashlib.sha256(
            json.dumps([self.username, self.password_hash]).encode("utf-8")
        ).hexdigest()
        self.hasher = PasswordHasher()
        try:
            self.legacy_email = normalize_email(self.username) if self.password_hash else None
        except ValueError:
            self.legacy_email = None
        # Unknown addresses still perform an expensive verification.
        self.dummy_hash = self.password_hash or self.hasher.hash(secrets.token_urlsafe(32))

    def identity(self, record: AuthSession, user: User | None) -> SessionIdentity:
        if user is None:
            return SessionIdentity(record.id, self.username, record.expires_at)
        return SessionIdentity(
            record.id,
            user.email,
            record.expires_at,
            user.id,
            user.name,
            user.email,
            cast(UserRole, user.role),
            user.active,
        )

    def find_session(self, session_id: object) -> SessionIdentity | None:
        if (
            not isinstance(session_id, str)
            or len(session_id) != 64
            or any(character not in "0123456789abcdef" for character in session_id)
        ):
            return None
        with self.session_factory() as database_session:
            record = database_session.get(AuthSession, session_id)
            if record is None or record.expires_at <= current_timestamp():
                return None
            user = None
            version = self.credential_version
            if record.user_id is not None:
                user = database_session.get(User, record.user_id)
                if user is None or not user.active or user.role not in {"admin", "customer"}:
                    return None
                version = user_credential_version(user)
            elif self.password_hash is None:
                return None
            if not compare_digest(record.credential_version, version):
                return None
            return self.identity(record, user)

    def login(self, username: str, password: str, previous_id: object) -> SessionIdentity | None:
        try:
            email = normalize_email(username)
        except ValueError:
            email = ""
        with self.session_factory() as database_session:
            user = database_session.scalar(select(User).where(User.email == email))
            # The explicit legacy operator keeps precedence during migration.
            legacy = self.password_hash is not None and compare_digest(
                username.encode("utf-8"), self.username.encode("utf-8")
            )
            password_hash = (
                self.password_hash if legacy else user.password_hash if user else self.dummy_hash
            )
            assert password_hash is not None
            try:
                matches = self.hasher.verify(password_hash, password)
            except (VerificationError, InvalidHashError):
                matches = False
            if not matches or (not legacy and (user is None or not user.active)):
                return None
            user_id = None if legacy else user.id
            version = self.credential_version if legacy else user_credential_version(user)
        now = current_timestamp()
        with self.session_factory() as database_session:
            with immediate_transaction(database_session):
                # Recheck persistent credentials under the write lock before issuing a session.
                user = database_session.get(User, user_id) if user_id is not None else None
                if user_id is not None and (
                    user is None
                    or not user.active
                    or not compare_digest(user_credential_version(user), version)
                ):
                    return None
                database_session.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
                if isinstance(previous_id, str):
                    database_session.execute(
                        delete(AuthSession).where(AuthSession.id == previous_id)
                    )
                record = AuthSession(
                    id=secrets.token_hex(32),
                    expires_at=now + self.settings.session_ttl_seconds,
                    credential_version=version,
                    user_id=user_id,
                )
                database_session.add(record)
                return self.identity(record, user)

    def register(self, data: RegisterRequest, *, role: UserRole = "customer") -> UserRead:
        # A legacy operator named with an email must not shadow a newly registered account.
        if data.email == self.legacy_email:
            raise DuplicateUserEmail
        password_hash = self.hasher.hash(data.password.get_secret_value())
        try:
            with self.session_factory() as database_session:
                with immediate_transaction(database_session):
                    if database_session.scalar(select(User.id).where(User.email == data.email)):
                        raise DuplicateUserEmail
                    user = User(
                        name=data.name,
                        email=data.email,
                        password_hash=password_hash,
                        role=role,
                        active=True,
                    )
                    database_session.add(user)
                    database_session.flush()
                    result = UserRead.model_validate(user)
                return result
        except IntegrityError as error:
            if "UNIQUE constraint failed: users.email" in str(error.orig):
                raise DuplicateUserEmail from error
            raise

    def revoke_session(self, session_id: str) -> None:
        with self.session_factory() as database_session:
            with immediate_transaction(database_session):
                database_session.execute(delete(AuthSession).where(AuthSession.id == session_id))
