"""Trusted host wrapper for reconciling an unknown attempt.

Reads and hashes the evidence file on the host, then calls the container-side
facade (``python -m pilot.operations.reconcile_cli``) with the digest. The raw
provider document never enters a container, a log or the audit trail.

Evidence file (JSON, kept outside Git)::

    {
      "reference": "provider-receipt-2026-11-19-001",
      "actual_cost_rub": "1.2345",
      "provider_request_id": "optional-provider-id"
    }

Usage::

    python scripts/pilot/reconcile_attempt.py --attempt-id <uuid> \\
        --outcome settled --evidence-file ~/evidence/receipt.json
    python scripts/pilot/reconcile_attempt.py --attempt-id <uuid> \\
        --outcome rejected --evidence-file ~/evidence/absence.json

``--outcome rejected`` demands proven absence of charges. Repeating the same
``--request-id`` with the same evidence is a no-op; different evidence under the
same request id exits non-zero as a conflict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OPERATOR = "local-cli"
OPERATOR_ENV = "PILOT_OPERATOR_REF"


class ReconcileError(Exception):
    """A safe, user-facing evidence or configuration failure."""


def operator_ref(explicit: str | None) -> str:
    value = (explicit or os.getenv(OPERATOR_ENV) or DEFAULT_OPERATOR).strip()
    if not value:
        raise ReconcileError("operator_ref must not be empty.")
    return value


def compose_env_file() -> str | None:
    explicit = os.getenv("PILOT_ENV_FILE")
    if explicit:
        return explicit
    candidate = Path.home() / ".config/smartnote/pilot.env"
    return str(candidate) if candidate.is_file() else None


def compose(*args: str) -> list[str]:
    command = ["docker", "compose", "-f", str(ROOT / "compose.yaml")]
    env_file = compose_env_file()
    if env_file:
        command.extend(["--env-file", env_file])
    return [*command, *args]


def read_evidence(path: Path) -> dict:
    """Hash the exact evidence bytes and read the documented fields."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ReconcileError(f"cannot read evidence file: {exc}") from None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ReconcileError("evidence file must be UTF-8 JSON") from None
    if not isinstance(payload, dict):
        raise ReconcileError("evidence file must contain a JSON object")
    reference = str(payload.get("reference") or "").strip()
    if not reference:
        raise ReconcileError("evidence needs a non-empty reference")
    cost = payload.get("actual_cost_rub")
    if cost is not None:
        try:
            amount = Decimal(str(cost))
        except (InvalidOperation, ValueError):
            raise ReconcileError("actual_cost_rub must be a decimal number") from None
        if not amount.is_finite() or amount < 0:
            raise ReconcileError("actual_cost_rub must be a finite non-negative number")
    provider = payload.get("provider_request_id")
    if provider is not None and not isinstance(provider, str):
        raise ReconcileError("provider_request_id must be a string")
    return {
        "reference": reference,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "actual_cost_rub": None if cost is None else str(cost),
        "provider_request_id": provider,
    }


def run_container(options: argparse.Namespace, evidence: dict, operator: str, request_id: UUID) -> int:
    args = [
        "exec", "-T", "backend", "python", "-m", "pilot.operations.reconcile_cli",
        "--attempt-id", str(options.attempt_id),
        "--outcome", options.outcome,
        "--reference", evidence["reference"],
        "--sha256", evidence["sha256"],
        "--operator-ref", operator,
        "--request-id", str(request_id),
    ]
    if evidence["actual_cost_rub"] is not None:
        args.extend(["--actual-cost-rub", str(evidence["actual_cost_rub"])])
    if evidence["provider_request_id"]:
        args.extend(["--provider-request-id", evidence["provider_request_id"]])
    result = subprocess.run(compose(*args), cwd=ROOT, capture_output=True, text=True, check=False)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0 and result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/pilot/reconcile_attempt.py",
        description="Trusted local reconciliation of an unknown attempt (no HTTP API).",
    )
    parser.add_argument("--attempt-id", type=UUID, required=True)
    parser.add_argument("--outcome", choices=("settled", "rejected"), required=True)
    parser.add_argument("--evidence-file", type=Path, required=True)
    parser.add_argument("--operator-ref", default=None)
    parser.add_argument("--reason", default=None, help="Short operational note for the operator.")
    parser.add_argument("--request-id", type=UUID, default=None,
                        help="Retry the same reconciliation without duplicating it.")
    return parser


def main(argv: list[str] | None = None) -> int:
    options = build_parser().parse_args(argv)
    try:
        operator = operator_ref(options.operator_ref)
        evidence = read_evidence(options.evidence_file)
        if options.outcome == "rejected":
            cost = evidence.get("actual_cost_rub")
            if cost is not None and Decimal(str(cost)) != 0:
                raise ReconcileError("rejected requires proven absence of charges (cost 0 or null)")
            evidence["actual_cost_rub"] = "0"
    except ReconcileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    request_id = options.request_id or uuid4()
    return run_container(options, evidence, operator, request_id)


if __name__ == "__main__":
    raise SystemExit(main())
