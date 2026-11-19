"""Trusted, container-side pause/resume and budget inspection.

Invoked through the host wrapper ``scripts/pilot/processing_control.py``, which
runs it inside the backend container. It calls the shared processing facade and
never opens its own ledger, slots or SQL.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg

from config import get_settings


def _json(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(type(value))


def emit(payload: dict) -> None:
    print(json.dumps(payload, default=_json, ensure_ascii=False, sort_keys=True))


async def run(options: argparse.Namespace) -> int:
    from pilot.domain.errors import DomainError
    from pilot.domain.services import create_services
    from pilot.processing.budget import get_budget
    from pilot.processing.control import get_processing_control, set_processing_paused

    settings = get_settings()
    pool = await asyncpg.create_pool(settings.database_url)
    try:
        services = create_services(pool, Path(settings.pilot_storage_root), settings)
        try:
            if options.command == "status":
                control = await get_processing_control(services)
                budget = await get_budget(services)
                emit({
                    "paused": control.paused,
                    "available_rub": control.available_rub,
                    "held_rub": control.held_rub,
                    "spend_limit_rub": budget.spend_limit_rub,
                    "spent_rub": budget.spent_rub,
                    "unknown_attempt_ids": list(control.unknown_attempt_ids),
                    "mode": services.mode,
                })
                return 0
            paused = options.command == "pause"
            state = await set_processing_paused(
                services,
                paused=paused,
                operator_ref=options.operator_ref,
                reason=options.reason,
                request_id=options.request_id or uuid4(),
            )
            emit({
                "paused": state.paused,
                "available_rub": state.available_rub,
                "held_rub": state.held_rub,
                "unknown_attempt_ids": list(state.unknown_attempt_ids),
                "mode": services.mode,
            })
            return 0
        except DomainError as exc:
            print(f"refused: {exc.code} {exc.message}", file=sys.stderr)
            return 1
    finally:
        await pool.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pilot.operations.processing_cli")
    parser.add_argument("command", choices=("status", "pause", "resume"))
    parser.add_argument("--operator-ref", required=True)
    parser.add_argument("--reason", default=None)
    parser.add_argument("--request-id", type=UUID, default=None)
    options = parser.parse_args(argv)
    if options.command != "status" and not (options.reason or "").strip():
        print("error: a non-empty --reason is required", file=sys.stderr)
        return 2
    return asyncio.run(run(options))


if __name__ == "__main__":
    raise SystemExit(main())
