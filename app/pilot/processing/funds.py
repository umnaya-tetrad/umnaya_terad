"""Atomic, mode-isolated reservations and append-only monetary evidence."""

from dataclasses import dataclass, asdict
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4
import hashlib, json, re
from ..domain.errors import DomainError, invalid
from ..domain import repository as r
from ..events.audit import audit


@dataclass(frozen=True)
class FundsEvidence:
    reference: str
    sha256: str
    profile_id: str


def finite_amount(value, *, positive=False):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise DomainError(422, "invalid_input", "Недопустимая сумма.")
    if not amount.is_finite() or amount < 0 or (positive and amount <= 0):
        raise DomainError(422, "invalid_input", "Недопустимая сумма.")
    return amount


def evidence_dict(evidence):
    d = (
        asdict(evidence)
        if hasattr(evidence, "__dataclass_fields__")
        else dict(evidence)
    )
    if not d.get("reference") or not re.fullmatch(
        "[a-fA-F0-9]{64}", str(d.get("sha256", ""))
    ):
        raise DomainError(
            422, "invalid_input", "Нужно проверенное подтверждение операции."
        )
    return {k: str(v) if isinstance(v, (Decimal, UUID)) else v for k, v in d.items()}


def digest(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


async def fund_wallet(
    svc, *, operation, amount_rub, evidence, operator_ref, request_id
):
    from .control import get_processing_control

    if operation not in ("initialize", "topup"):
        raise DomainError(422, "invalid_input", "Недопустимая операция.")
    amount = finite_amount(amount_rub, positive=operation == "topup")
    ev = evidence_dict(evidence)
    if not ev.get("profile_id") or not operator_ref:
        raise DomainError(422, "invalid_input", "Нужен профиль и оператор.")
    payload = {
        "operation": operation,
        "amount": str(amount),
        "evidence": ev,
        "operator_ref": operator_ref,
        "mode": svc.mode,
    }
    hashed = digest(payload)
    async with svc.pool.acquire() as con, con.transaction():
        await con.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1))",
            "pilot-ledger:" + str(request_id),
        )
        wallet = await con.fetchrow(
            "SELECT * FROM pilot_funds WHERE mode=$1 FOR UPDATE", svc.mode
        )
        old = await con.fetchrow(
            "SELECT payload_hash FROM pilot_fund_ledger WHERE request_id=$1", request_id
        )
        if old:
            if old["payload_hash"] != hashed:
                invalid(
                    "Подтверждение операции уже использовано.", "idempotency_conflict"
                )
        else:
            if operation == "initialize" and wallet["initialized"]:
                invalid("Кошелек уже инициализирован.")
            if operation == "topup" and not wallet["initialized"]:
                invalid("Сначала подтвердите начальный остаток.")
            # Top-ups pay explicitly recorded outstanding liabilities first.
            debt = wallet["outstanding_debt_rub"]
            pay = min(amount, debt)
            credit = amount - pay
            await con.execute(
                "UPDATE pilot_funds SET balance_rub=balance_rub+$2,outstanding_debt_rub=outstanding_debt_rub-$3,initialized=true,profile_id=$4 WHERE mode=$1",
                svc.mode,
                credit,
                pay,
                ev["profile_id"],
            )
            await con.execute(
                "INSERT INTO pilot_fund_ledger(id,mode,request_id,operation,amount_rub,payload_hash,evidence) VALUES($1,$2,$3,$4,$5,$6,$7::jsonb)",
                uuid4(),
                svc.mode,
                request_id,
                operation,
                amount,
                hashed,
                json.dumps(ev),
            )
            await audit(
                con,
                "fund_" + operation,
                request_id=request_id,
                payload={"mode": svc.mode, "operator_ref": operator_ref},
            )
    return await get_processing_control(svc)


async def reserve(con, svc, attempt_id, bound, wallet):
    if bound is None or wallet["paused"]:
        return False
    amount = finite_amount(bound)
    if wallet["spend_limit_rub"] - wallet["spent_rub"] - wallet["held_rub"] < amount:
        return False
    await con.execute(
        "UPDATE pilot_processing_budget SET held_rub=held_rub+$2 WHERE mode=$1",
        svc.mode,
        amount,
    )
    await con.execute(
        "INSERT INTO pilot_fund_reservations(attempt_id,mode,amount_rub) VALUES($1,$2,$3)",
        attempt_id,
        svc.mode,
        amount,
    )
    return True


async def observe_unknown_cost(con, attempt_id, amount):
    """A larger late observation enlarges its hold, without fabricating a debit."""
    amount = finite_amount(amount)
    reservation = await con.fetchrow(
        "SELECT * FROM pilot_fund_reservations WHERE attempt_id=$1", attempt_id
    )
    if (
        not reservation
        or not reservation["active"]
        or amount <= reservation["amount_rub"]
    ):
        return
    await con.fetchrow(
        "SELECT mode FROM pilot_processing_budget WHERE mode=$1 FOR UPDATE",
        reservation["mode"],
    )
    await con.execute(
        "UPDATE pilot_processing_budget SET held_rub=held_rub+$2 WHERE mode=$1",
        reservation["mode"],
        amount - reservation["amount_rub"],
    )
    await con.execute(
        "UPDATE pilot_fund_reservations SET amount_rub=$2 WHERE attempt_id=$1",
        attempt_id,
        amount,
    )
    await audit(con, "cost_bound_observation", entity_id=attempt_id)


async def settle(
    con,
    attempt_id,
    actual_cost,
    *,
    request_id=None,
    evidence=None,
    rejected=False,
    mode=None
):
    """Finalize execution separately from billing; null cost never means free."""
    amount = finite_amount(actual_cost) if actual_cost is not None else None
    a = await con.fetchrow(
        "SELECT * FROM pilot_attempts WHERE id=$1 FOR UPDATE", attempt_id
    )
    reservation = await con.fetchrow(
        "SELECT * FROM pilot_fund_reservations WHERE attempt_id=$1", attempt_id
    )
    mode = a["transport_mode"] or (reservation["mode"] if reservation else mode)
    if mode not in ("fixture", "polza"):
        invalid("Неизвестен режим попытки.")
    await con.fetchrow(
        "SELECT mode FROM pilot_processing_budget WHERE mode=$1 FOR UPDATE", mode
    )
    old = await con.fetchrow(
        "SELECT amount_rub FROM pilot_fund_ledger WHERE attempt_id=$1 AND operation='settlement'",
        attempt_id,
    )
    changed = False
    if old:
        if amount is not None and old["amount_rub"] != amount:
            invalid("Стоимость уже сверена с другим значением.")
        amount = old["amount_rub"]
    elif amount is not None:
        await con.execute(
            "INSERT INTO pilot_fund_ledger(id,mode,request_id,attempt_id,operation,amount_rub,payload_hash,evidence) VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb)",
            uuid4(),
            mode,
            request_id or uuid4(),
            attempt_id,
            "settlement",
            amount,
            digest({"attempt_id": str(attempt_id), "amount": str(amount)}),
            json.dumps(evidence or {}),
        )
        await con.execute(
            "UPDATE pilot_processing_budget SET spent_rub=spent_rub+$2 WHERE mode=$1",
            mode,
            amount,
        )
        changed = True
    if amount is not None and reservation and reservation["active"]:
        await con.execute(
            "UPDATE pilot_processing_budget SET held_rub=held_rub-$2 WHERE mode=$1",
            mode,
            reservation["amount_rub"],
        )
        await con.execute(
            "UPDATE pilot_fund_reservations SET active=false WHERE attempt_id=$1",
            attempt_id,
        )
        changed = True
    state = "rejected" if rejected else "settled"
    billing = "settled" if amount is not None else "unknown"
    if (
        a["state"] != state
        or a["billing_state"] != billing
        or a["actual_cost_rub"] != amount
    ):
        changed = True
    await con.execute(
        "UPDATE pilot_attempts SET state=$2,billing_state=$3,actual_cost_rub=$4 WHERE id=$1",
        attempt_id,
        state,
        billing,
        amount,
    )
    if changed:
        await audit(
            con,
            "attempt_settled",
            entity_id=attempt_id,
            payload={"cost_known": amount is not None},
        )
    return changed
