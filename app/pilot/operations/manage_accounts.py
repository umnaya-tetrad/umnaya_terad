"""Trusted local account provisioning and password reset.

The CLI is a thin wrapper over the shared processing domain: it never writes its
own SQL, never re-implements password hashing and never accepts a password from
argv (it would land in the shell history and process list). Passwords come from
a hidden prompt or from the ``PILOT_ACCOUNT_PASSWORD`` environment variable.

Commands (run inside the local stack, for example with
``docker compose exec backend ...``)::

    python -m pilot.operations.manage_accounts seed
    python -m pilot.operations.manage_accounts create --login teacher-3 --role teacher
    python -m pilot.operations.manage_accounts reset --login teacher-one

Every call is audited by the domain with ``operator_ref`` and ``request_id``;
neither secret nor password hash is printed or logged.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path
from typing import Iterable
from uuid import UUID, uuid4

import asyncpg

from config import get_settings

ACCOUNTS = (
    ("TEACHER_1", "teacher"),
    ("TEACHER_2", "teacher"),
    ("STAFF", "staff"),
)
PASSWORD_ENV = "PILOT_ACCOUNT_PASSWORD"
OPERATOR_ENV = "PILOT_OPERATOR_REF"
DEFAULT_OPERATOR = "local-cli"
ROLES = ("teacher", "staff")


class AccountError(Exception):
    """A safe, user-facing configuration or domain failure."""


def fixture_credentials() -> list[tuple[str, str, str]]:
    """Read the three local fixture accounts from the environment."""
    entries: list[tuple[str, str, str]] = []
    for name, role in ACCOUNTS:
        prefix = f"PILOT_FIXTURE_{name}_"
        login = os.getenv(prefix + "LOGIN", "").strip()
        password = os.getenv(prefix + "PASSWORD", "")
        if not login or not password.strip():
            raise AccountError(f"Missing configuration for {prefix}LOGIN or {prefix}PASSWORD.")
        entries.append((login, password, role))
    logins = [entry[0].casefold() for entry in entries]
    if len(set(logins)) != len(logins):
        raise AccountError("Fixture account logins must be distinct.")
    return entries


def read_password(*, confirm: bool) -> str:
    """Take the password from the environment or a hidden interactive prompt."""
    value = os.getenv(PASSWORD_ENV)
    if value is not None:
        if not value:
            raise AccountError(f"{PASSWORD_ENV} is set but empty.")
        return value
    if not sys.stdin.isatty():
        raise AccountError(
            f"Set {PASSWORD_ENV} or run the command in an interactive terminal for hidden input."
        )
    first = getpass.getpass("Новый пароль: ")
    if confirm:
        second = getpass.getpass("Повторите пароль: ")
        if first != second:
            raise AccountError("Пароли не совпадают.")
    if not first:
        raise AccountError("Пустой пароль недопустим.")
    return first


def operator_ref(explicit: str | None) -> str:
    value = (explicit or os.getenv(OPERATOR_ENV) or DEFAULT_OPERATOR).strip()
    if not value:
        raise AccountError("operator_ref must not be empty.")
    return value


def normalise_login(value: str) -> str:
    login = value.strip()
    if not login:
        raise AccountError("Логин не может быть пустым.")
    return login


def print_result(action: str, login: str, result: dict, request_id: UUID) -> None:
    """Print only non-secret identifiers for an audit trail."""
    print(
        f"{action}: login={login} role={result.get('role')} "
        f"user_id={result.get('user_id')} request_id={request_id}"
    )


async def run_seed(operator: str) -> int:
    from pilot.domain.auth import ensure_account

    entries: Iterable[tuple[str, str, str]] = fixture_credentials()
    async with _services() as (services, _settings):
        for login, password, role in entries:
            request_id = uuid4()
            result = await ensure_account(
                services,
                login,
                password,
                role,
                operator_ref=operator,
                request_id=request_id,
            )
            print_result("seeded", login, result, request_id)
    return 0


async def run_create(login: str, role: str, password: str, operator: str) -> int:
    from pilot.domain.auth import ensure_account

    if role not in ROLES:
        raise AccountError(f"Роль должна быть одной из: {', '.join(ROLES)}.")
    async with _services() as (services, _settings):
        request_id = uuid4()
        result = await ensure_account(
            services,
            login,
            password,
            role,
            operator_ref=operator,
            request_id=request_id,
        )
        print_result("created", login, result, request_id)
    return 0


async def run_reset(login: str, password: str, operator: str) -> int:
    from pilot.domain.auth import reset_account_password

    async with _services() as (services, _settings):
        request_id = uuid4()
        result = await reset_account_password(
            services,
            login=login,
            password=password,
            operator_ref=operator,
            request_id=request_id,
        )
        print_result("reset", login, result, request_id)
    return 0


class _services:
    """Create services on a short-lived pool and always close it."""

    def __init__(self) -> None:
        self._pool = None

    async def __aenter__(self):
        from pilot.domain.services import create_services

        settings = get_settings()
        self._pool = await asyncpg.create_pool(settings.database_url)
        return create_services(self._pool, Path(settings.pilot_storage_root), settings), settings

    async def __aexit__(self, *exc_info) -> None:
        if self._pool is not None:
            await self._pool.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pilot.operations.manage_accounts",
        description="Trusted local account provisioning and password reset.",
    )
    parser.add_argument("--operator-ref", default=None, help="Who performs the operation (audit only).")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("seed", help="Create the three local fixture accounts from PILOT_FIXTURE_* env.")

    create = commands.add_parser("create", help="Create one account; an existing one is a no-op.")
    create.add_argument("--login", required=True)
    create.add_argument("--role", required=True, choices=ROLES)

    reset = commands.add_parser("reset", help="Replace the password and revoke that account's sessions.")
    reset.add_argument("--login", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    options = parser.parse_args(argv)
    try:
        operator = operator_ref(options.operator_ref)
        if options.command == "seed":
            return asyncio.run(_guarded(run_seed(operator)))
        login = normalise_login(options.login)
        password = read_password(confirm=True)
        if options.command == "create":
            return asyncio.run(_guarded(run_create(login, options.role, password, operator)))
        if options.command == "reset":
            return asyncio.run(_guarded(run_reset(login, password, operator)))
    except AccountError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


async def _guarded(coroutine) -> int:
    from pilot.domain.errors import DomainError

    try:
        return await coroutine
    except DomainError as exc:
        print(f"refused: {exc.code} {exc.message}", file=sys.stderr)
        return 1
    except (OSError, KeyError, ValueError, asyncpg.PostgresError):
        print("error: account operation failed; check local configuration and migrations.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
