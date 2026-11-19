"""Trusted, container-side reconciliation of an unknown attempt.

Invoked through the host wrapper ``scripts/pilot/reconcile_attempt.py``, which
reads and hashes the evidence file locally and passes the digest here. So the
raw provider document never enters a container log or the audit trail.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from decimal import Decimal, InvalidOperation
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


async def run(options: argparse.Namespace) -> int:
    from pilot.domain.errors import DomainError
    from pilot.domain.services import create_services
    from pilot.processing.reconciliation import ReconciliationEvidence, reconcile_attempt

    try:
        cost = None if options.actual_cost_rub is None else Decimal(options.actual_cost_rub)
    except InvalidOperation:
        print("error: --actual-cost-rub must be a decimal number", file=sys.stderr)
        return 2

    settings = get_settings()
    pool = await asyncpg.create_pool(settings.database_url)
    try:
        services = create_services(pool, Path(settings.pilot_storage_root), settings)
        try:
            result = await reconcile_attempt(
                services,
                attempt_id=options.attempt_id,
                outcome=options.outcome,
                evidence=ReconciliationEvidence(
                    reference=options.reference,
                    sha256=options.sha256,
                    actual_cost_rub=cost,
                    provider_request_id=options.provider_request_id,
                ),
                operator_ref=options.operator_ref,
                request_id=options.request_id or uuid4(),
            )
        except DomainError as exc:
            print(f"refused: {exc.code} {exc.message}", file=sys.stderr)
            return 1
    finally:
        await pool.close()
    print(json.dumps({
        "attempt_id": str(result.attempt_id),
        "state": result.state,
        "held_rub": str(result.held_rub),
        "changed": result.changed,
        "request_id": str(options.request_id or ""),
        "mode": services.mode,
    }, default=_json, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pilot.operations.reconcile_cli")
    parser.add_argument("--attempt-id", type=UUID, required=True)
    parser.add_argument("--outcome", choices=("settled", "rejected"), required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--actual-cost-rub", default=None)
    parser.add_argument("--provider-request-id", default=None)
    parser.add_argument("--operator-ref", required=True)
    parser.add_argument("--request-id", type=UUID, default=None)
    options = parser.parse_args(argv)
    if options.outcome == "rejected":
        if options.actual_cost_rub not in (None, "0", "0.0", "0.00"):
            print("error: rejected requires proven absence of charges", file=sys.stderr)
            return 2
        options.actual_cost_rub = "0"
    return asyncio.run(run(options))


if __name__ == "__main__":
    raise SystemExit(main())
