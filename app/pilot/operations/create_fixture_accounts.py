"""Create local fixture accounts using the shared domain."""
import asyncio
import os
from pathlib import Path

import asyncpg

from config import get_settings

ACCOUNTS = (
    ("TEACHER_1", "teacher"),
    ("TEACHER_2", "teacher"),
    ("STAFF", "staff"),
)


def fixture_credentials():
    entries = []
    for name, role in ACCOUNTS:
        prefix = f"PILOT_FIXTURE_{name}_"
        login = os.getenv(prefix + "LOGIN", "").strip()
        password = os.getenv(prefix + "PASSWORD", "")
        if not login or not password.strip():
            raise ValueError(f"Missing configuration for {prefix}LOGIN or {prefix}PASSWORD.")
        entries.append((login, password, role))
    if len({entry[0].casefold() for entry in entries}) != len(entries):
        raise ValueError("Fixture account logins must be distinct.")
    return entries


async def run() -> None:
    from pilot.domain.auth import ensure_account
    from pilot.domain.errors import DomainError
    from pilot.domain.services import create_services

    try:
        entries = fixture_credentials()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    try:
        settings = get_settings()
        if settings.pilot_transport != "fixture":
            raise SystemExit("Fixture accounts require PILOT_TRANSPORT=fixture.")
        async with asyncpg.create_pool(settings.database_url) as pool:
            root = Path(settings.pilot_storage_root)
            services = create_services(pool, root, settings)
            for login, password, role in entries:
                await ensure_account(services, login, password, role)
    except DomainError:
        raise SystemExit("Fixture account creation refused by the shared domain.") from None
    except (OSError, KeyError, ValueError, asyncpg.PostgresError):
        raise SystemExit("Fixture account setup failed. Check local configuration and migrations.") from None
    print("Fixture accounts are ready.")


if __name__ == "__main__":
    asyncio.run(run())
