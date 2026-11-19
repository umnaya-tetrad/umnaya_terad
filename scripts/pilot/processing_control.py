"""Trusted host wrapper for pause/resume and budget status.

Runs the container-side facade (``python -m pilot.operations.processing_cli``)
next to the local Compose project. It does not open a database connection on the
host, does not create a second ledger and is not reachable over HTTP.

Usage::

    python scripts/pilot/processing_control.py status
    python scripts/pilot/processing_control.py pause --reason "provider issue"
    python scripts/pilot/processing_control.py resume --reason "provider restored"

``--operator-ref`` (or ``PILOT_OPERATOR_REF``) is written to the domain audit;
no secret or material content is copied there.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OPERATOR = "local-cli"
OPERATOR_ENV = "PILOT_OPERATOR_REF"


class ControlError(Exception):
    """A safe, user-facing configuration failure."""


def operator_ref(explicit: str | None) -> str:
    value = (explicit or os.getenv(OPERATOR_ENV) or DEFAULT_OPERATOR).strip()
    if not value:
        raise ControlError("operator_ref must not be empty.")
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


def run_container(command: str, *, operator: str, reason: str | None, request_id: UUID) -> int:
    args = ["exec", "-T", "backend", "python", "-m", "pilot.operations.processing_cli",
            command, "--operator-ref", operator, "--request-id", str(request_id)]
    if command != "status":
        args.extend(["--reason", reason or ""])
    result = subprocess.run(compose(*args), cwd=ROOT, capture_output=True, text=True, check=False)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0 and result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/pilot/processing_control.py",
        description="Trusted local pause/resume for the pilot worker (no HTTP API).",
    )
    parser.add_argument("--operator-ref", default=None, help="Who performs the action (audit only).")
    parser.add_argument("--request-id", type=UUID, default=None, help="Reuse one audit request id.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show pause state, funds and unknown attempts.")
    for name in ("pause", "resume"):
        item = commands.add_parser(name, help=f"{name.capitalize()} new dispatches.")
        item.add_argument("--reason", required=True, help="Short operational reason (audited).")
    return parser


def main(argv: list[str] | None = None) -> int:
    options = build_parser().parse_args(argv)
    try:
        operator = operator_ref(options.operator_ref)
    except ControlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if options.command != "status" and not (options.reason or "").strip():
        print("error: a non-empty --reason is required", file=sys.stderr)
        return 2
    request_id = options.request_id or uuid4()
    if options.command == "status" and options.request_id is None:
        request_id = UUID(int=0)
    return run_container(
        options.command,
        operator=operator,
        reason=getattr(options, "reason", None),
        request_id=request_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
