"""Hot cumulative spend cap shared by checker, analytics and every teacher."""

from dataclasses import dataclass, asdict
from decimal import Decimal
from uuid import UUID, uuid4
from pathlib import Path
import argparse, asyncio, json
from .funds import finite_amount, digest
from ..events.audit import audit
from ..domain.errors import invalid


@dataclass(frozen=True)
class BudgetState:
    spend_limit_rub: Decimal
    spent_rub: Decimal
    held_rub: Decimal
    available_rub: Decimal
    paused: bool


async def get_budget(svc):
    row = await svc.pool.fetchrow(
        "SELECT * FROM pilot_processing_budget WHERE mode=$1", svc.mode
    )
    return BudgetState(
        row["spend_limit_rub"],
        row["spent_rub"],
        row["held_rub"],
        max(row["spend_limit_rub"] - row["spent_rub"] - row["held_rub"], Decimal(0)),
        row["paused"],
    )


async def set_spend_limit(
    svc, *, spend_limit_rub, operator_ref="container-shell", request_id=None
):
    amount = finite_amount(spend_limit_rub)
    request_id = request_id or uuid4()
    payload = {
        "mode": svc.mode,
        "spend_limit_rub": str(amount),
        "operator_ref": operator_ref,
    }
    hashed = digest(payload)
    async with svc.pool.acquire() as con, con.transaction():
        await con.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1))",
            "pilot-budget:" + str(request_id),
        )
        row = await con.fetchrow(
            "SELECT * FROM pilot_processing_budget WHERE mode=$1 FOR UPDATE", svc.mode
        )
        old = await con.fetchrow(
            "SELECT payload_hash FROM pilot_budget_changes WHERE request_id=$1",
            request_id,
        )
        if old:
            if old["payload_hash"] != hashed:
                invalid(
                    "Это изменение лимита уже использовано с другими данными.",
                    "idempotency_conflict",
                )
        else:
            await con.execute(
                "UPDATE pilot_processing_budget SET spend_limit_rub=$2 WHERE mode=$1",
                svc.mode,
                amount,
            )
            await con.execute(
                "INSERT INTO pilot_budget_changes(request_id,mode,payload_hash,spend_limit_rub) VALUES($1,$2,$3,$4)",
                request_id,
                svc.mode,
                hashed,
                amount,
            )
            await audit(
                con,
                "spend_limit_changed",
                request_id=request_id,
                payload={"mode": svc.mode, "operator_ref": operator_ref},
            )
    return await get_budget(svc)


async def main():
    import asyncpg
    from config import get_settings
    from ..domain.services import create_services

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    setter = sub.add_parser("set-limit")
    setter.add_argument("--rub", required=True)
    setter.add_argument("--operator-ref", default="container-shell")
    setter.add_argument("--request-id", type=UUID)
    args = parser.parse_args()
    settings = get_settings()
    pool = await asyncpg.create_pool(settings.database_url)
    svc = create_services(pool, Path(settings.pilot_storage_root), settings)
    try:
        state = (
            await get_budget(svc)
            if args.command == "status"
            else await set_spend_limit(
                svc,
                spend_limit_rub=args.rub,
                operator_ref=args.operator_ref,
                request_id=args.request_id,
            )
        )
        print(json.dumps(asdict(state), default=str))
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
