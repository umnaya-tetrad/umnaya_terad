"""Explicit local UX fixture worker. Never imported by the production worker.

Only this development entrypoint attaches a canned transport to Services. The
normal durable queue, validation, settlement and publication remain unchanged.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path

import asyncpg

from config import get_settings
from pilot.domain.services import create_services
from pilot.processing.fixture_transport import run_fixture
from pilot.processing.transport import TransportResult
from pilot.processing.worker import run_forever


def require_fixture(settings) -> None:
    """Reject live configuration before opening a database or installing hooks."""
    if settings.pilot_transport != "fixture" or settings.polza_api_key:
        raise ValueError("UX workbench requires fixture mode and an empty model key")


def load_catalog(root: Path) -> dict:
    value = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if value.get("schema_version") != "ux-workbench/1":
        raise ValueError("Unsupported UX fixture catalog")
    return value


def report_for(root: Path, scenario: str, image_count: int) -> dict:
    name = "unassessed" if scenario == "unassessed" else "continuation" if image_count > 1 else "normal"
    value = json.loads((root / "reports" / (name + ".json")).read_text(encoding="utf-8"))
    from pilot.processing.checker import validate_result
    return validate_result(value, image_count)


def scenario_for(title: str, photo_hashes: list[str], catalog: dict) -> str:
    if title.startswith(("[UX 04]", "[UX RUN retry]")):
        return "retry"
    if title.startswith(("[UX 03]", "[UX RUN unassessed]")):
        return "unassessed"
    # A known demo photograph also works when uploaded into a fresh user Check.
    for scenario in catalog["scenarios"]:
        if scenario["id"] in {"unassessed", "retry"}:
            known = {catalog["asset_sha256"][path] for path in scenario["photos"]}
            if known.intersection(photo_hashes):
                return scenario["id"]
    return "mixed"


class LocalTransport:
    def __init__(self, svc, root: Path, delay_seconds: float = 4):
        require_fixture(svc.settings)
        if not 0 <= delay_seconds <= 30:
            raise ValueError("UX fixture delay must be between 0 and 30 seconds")
        self.svc, self.root, self.delay = svc, root, delay_seconds
        self.catalog = load_catalog(root)

    async def __call__(self, job, payload):
        require_fixture(self.svc.settings)
        await asyncio.sleep(self.delay)
        if job["kind"] == "class_analytics":
            # The existing explicitly labelled mock summary validates the real
            # saved snapshot; it is not a substitute for a live analytics call.
            result = await run_fixture(job, payload)
            result.actual_cost_rub = Decimal(0)
            return result
        title = await self.svc.pool.fetchval("SELECT title FROM pilot_checks WHERE id=$1", job["check_id"])
        rows = await self.svc.pool.fetch(
            "SELECT a.sha256 FROM pilot_version_photos v JOIN pilot_photo_assets a ON a.id=v.photo_id "
            "WHERE v.version_id=$1 ORDER BY v.position", job["input_version_id"],
        )
        scenario = scenario_for(title or "", [row["sha256"] for row in rows], self.catalog)
        if scenario == "retry":
            generation_jobs = await self.svc.pool.fetchval(
                "SELECT count(*) FROM pilot_jobs WHERE kind='page_check' AND bundle_id=$1 AND input_version_id=$2",
                job["bundle_id"], job["input_version_id"],
            )
            if generation_jobs == 1:
                # Safely rejected, zero cost, no automatic retry. A teacher's
                # explicit retry creates another Job and then succeeds.
                return TransportResult("rejected", actual_cost_rub=Decimal(0), error_code="ux_safe_failure")
        result = report_for(self.root, scenario, len(payload["images"]))
        return TransportResult("success", payload=result, actual_cost_rub=Decimal(0),
                               provider_request_id="ux-workbench-local", raw=json.dumps(result, ensure_ascii=False))


async def run_worker(settings, root: Path, delay_seconds: float = 4):
    require_fixture(settings)
    load_catalog(root)
    async with asyncpg.create_pool(settings.database_url, min_size=1, max_size=6) as pool:
        svc = create_services(pool, Path(settings.pilot_storage_root), settings)
        svc.transport = LocalTransport(svc, root, delay_seconds)
        # Two ordinary production worker loops share the normal global slots.
        await asyncio.gather(run_forever(svc), run_forever(svc))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["api", "worker"])
    parser.add_argument("--delay-seconds", type=float, default=4)
    parser.add_argument("--fixtures-root", type=Path,
                        default=Path(os.getenv("PILOT_UX_FIXTURES_ROOT", "/opt/smartnote-ux")))
    args = parser.parse_args()
    settings = get_settings()
    require_fixture(settings)
    if args.command == "api":
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8000)
    else:
        asyncio.run(run_worker(settings, args.fixtures_root, args.delay_seconds))


if __name__ == "__main__":
    main()
