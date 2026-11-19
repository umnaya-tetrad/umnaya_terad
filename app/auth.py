"""Minimal password authentication for the gated pilot.

Passwords never leave this module in clear text after request parsing.  The
database contains a salted scrypt verifier and an HMAC of each opaque session
token, not a browser cookie or a password.
"""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import scrypt
import hmac
import re
import secrets
from uuid import UUID, uuid4

import asyncpg

from config import Settings


USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")
PASSWORD_MIN_LENGTH = 8
SESSION_COOKIE_NAME = "smartnote_session"


class AuthenticationError(ValueError):
    """The supplied credentials are invalid or the account cannot be created."""


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    username: str


def normalise_username(username: str) -> str:
    value = username.strip().lower()
    if not USERNAME_RE.fullmatch(value):
        raise AuthenticationError("Логин: 3–32 символа, латинские буквы, цифры, точка, дефис или _.")
    return value


def validate_password(password: str) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise AuthenticationError("Пароль должен содержать не меньше 8 символов.")
    if len(password) > 256:
        raise AuthenticationError("Пароль слишком длинный.")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1${}${}".format(
        urlsafe_b64encode(salt).decode("ascii"), urlsafe_b64encode(digest).decode("ascii")
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_encoded, digest_encoded = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = urlsafe_b64decode(salt_encoded.encode("ascii"))
        expected = urlsafe_b64decode(digest_encoded.encode("ascii"))
        actual = scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


class AuthService:
    def __init__(self, pool: asyncpg.Pool, settings: Settings) -> None:
        self._pool = pool
        self._session_secret = settings.visitor_cookie_secret.encode("utf-8")
        self._session_days = settings.auth_session_days

    def _token_hash(self, token: str) -> str:
        return hmac.new(self._session_secret, token.encode("ascii"), "sha256").hexdigest()

    async def register(self, username: str, password: str) -> tuple[AuthenticatedUser, str]:
        username = normalise_username(username)
        validate_password(password)
        user = AuthenticatedUser(id=uuid4(), username=username)
        try:
            await self._pool.execute(
                """
                INSERT INTO users (id, username, password_hash)
                VALUES ($1, $2, $3)
                """,
                user.id,
                user.username,
                hash_password(password),
            )
        except asyncpg.UniqueViolationError as error:
            raise AuthenticationError("Этот логин уже занят.") from error
        return user, await self.create_session(user)

    async def authenticate(self, username: str, password: str) -> tuple[AuthenticatedUser, str]:
        # A generic error avoids exposing which part of a credential pair failed.
        try:
            username = normalise_username(username)
        except AuthenticationError as error:
            raise AuthenticationError("Неверный логин или пароль.") from error

        record = await self._pool.fetchrow(
            "SELECT id, username, password_hash FROM users WHERE username = $1 AND is_active = TRUE", username
        )
        if record is None or not verify_password(password, record["password_hash"]):
            raise AuthenticationError("Неверный логин или пароль.")
        user = AuthenticatedUser(id=record["id"], username=record["username"])
        return user, await self.create_session(user)

    async def create_session(self, user: AuthenticatedUser) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=self._session_days)
        await self._pool.execute(
            """
            INSERT INTO auth_sessions (token_hash, user_id, expires_at)
            VALUES ($1, $2, $3)
            """,
            self._token_hash(token),
            user.id,
            expires_at,
        )
        return token

    async def user_for_token(self, token: str | None) -> AuthenticatedUser | None:
        if not token or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            return None
        record = await self._pool.fetchrow(
            """
            SELECT users.id, users.username
            FROM auth_sessions
            JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.token_hash = $1
              AND auth_sessions.expires_at > NOW()
              AND auth_sessions.revoked_at IS NULL
              AND users.is_active = TRUE
            """,
            self._token_hash(token),
        )
        if record is None:
            return None
        return AuthenticatedUser(id=record["id"], username=record["username"])

    async def revoke(self, token: str | None) -> None:
        if token and re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            await self._pool.execute(
                "UPDATE auth_sessions SET revoked_at = NOW() WHERE token_hash = $1 AND revoked_at IS NULL",
                self._token_hash(token),
            )
