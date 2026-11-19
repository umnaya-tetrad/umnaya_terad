"""Test-only provider boundary; real worker/queue/transport/settlement/publication.

Copied explicitly into a fixture container by the integration harness. Production
never imports this file. HTTPX MockTransport forbids any external connection.
PostgreSQL tables below contain only synthetic controls and safe call metadata.
"""
from __future__ import annotations

import asyncio
import base64
import copy
import json
import sys
from pathlib import Path

import asyncpg
import httpx

sys.path.insert(0, "/app")

from config import get_settings
from pilot.domain.services import create_services
from pilot.processing.providers import build_request
from pilot.processing.transport import send_once
from pilot.processing.worker import run_once


async def main():
    settings = get_settings()
    if settings.pilot_transport != "fixture":
        raise RuntimeError("Controlled acceptance worker requires explicit fixture mode")
    # Synthetic value used only by the in-process mock HTTP adapter.
    settings.polza_api_key = "synthetic-offline-acceptance-key"
    settings.polza_base_url = "https://fixture.invalid/v1"
    async with asyncpg.create_pool(settings.database_url, min_size=1, max_size=4) as pool:
        svc = create_services(pool, Path(settings.pilot_storage_root), settings)

        async def gateway(job, payload):
            control = await pool.fetchrow("SELECT * FROM release_test_jobs WHERE job_id=$1", job["id"])
            if control is None:
                raise AssertionError("Controlled worker claimed an unregistered job")
            ordinal = await pool.fetchval("SELECT count(*)+1 FROM release_test_posts WHERE job_id=$1", job["id"])
            outcomes = json.loads(control["outcomes"])
            if ordinal > len(outcomes):
                raise AssertionError("Unexpected additional provider attempt")
            outcome = outcomes[ordinal - 1]

            async def respond(request):
                assert request.method == "POST" and request.url.host == "fixture.invalid"
                body = json.loads(request.content)
                images = [part["image_url"]["url"] for message in body["messages"] if message["role"] == "user"
                          for part in message["content"] if part["type"] == "image_url"]
                assert len(images) == len(payload["images"]) > 0
                assert [base64.b64decode(value.split(",", 1)[1], validate=True) for value in images] == [path.read_bytes() for path in payload["images"]]
                slots = await pool.fetchval("SELECT count(*) FROM pilot_slots WHERE attempt_id IS NOT NULL")
                assert 1 <= slots <= 2
                identity = await pool.fetchval(
                    "INSERT INTO release_test_posts(job_id,input_id,ordinal,method,outcome,active_slots,image_count) "
                    "VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING id",
                    job["id"], job["input_version_id"], ordinal, request.method, outcome, slots, len(images),
                )
                while not await pool.fetchval("SELECT released FROM release_test_jobs WHERE job_id=$1", job["id"]):
                    await asyncio.sleep(0.02)
                await asyncio.sleep(control["delay_ms"] / 1000)
                if outcome == "temporary_failure":
                    response = httpx.Response(429, json={"error": {"message": "synthetic pre-inference rejection"}})
                else:
                    template = json.loads((Path("/app/pilot/analytics/assets/fixtures/oracle.input.json")).read_text(encoding="utf-8"))
                    first = next(t["analysis"] for n in template["notebooks"] for t in n["tasks"] if t["analysis"]["result"] == "first_error_found")
                    tasks = []
                    for index in range(control["task_count"]):
                        task = copy.deepcopy(first)
                        task["task_id"] = f"synthetic_{index + 1}"
                        task["photo_indices"] = [1]
                        for evidence in task["evidence"]:
                            evidence["photo_index"] = 1
                        task["first_error"]["photo_index"] = 1
                        tasks.append(task)
                    report = {"schema_version": "page-check/1.2", "status": "ok", "message": "Synthetic controlled acceptance", "tasks": tasks}
                    response = httpx.Response(200, json={
                        "id": f"acceptance-{identity}", "usage": {"cost_rub": "0.01"},
                        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(report)}}],
                    })
                await pool.execute("UPDATE release_test_posts SET ended_at=clock_timestamp(),http_status=$2 WHERE id=$1", identity, response.status_code)
                return response

            request, config = build_request(svc, job, payload)
            return await send_once(request, config=config, transport=httpx.MockTransport(respond))

        svc.transport = gateway
        if sys.argv[1] == "once":
            print(json.dumps({"claimed": bool(await run_once(svc))}))
        elif sys.argv[1] == "drain":
            while await pool.fetchval("SELECT EXISTS(SELECT 1 FROM pilot_jobs j JOIN release_test_jobs t ON t.job_id=j.id WHERE j.state IN ('queued','running','retry_wait','blocked'))"):
                if not await run_once(svc):
                    await asyncio.sleep(0.05)
        else:
            raise ValueError("Unknown controlled worker command")


if __name__ == "__main__":
    asyncio.run(main())
