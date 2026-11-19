import base64, json
from decimal import Decimal
from uuid import UUID, uuid4
import pytest
from pilot.processing.transport import TransportResult
from ..harness import png
from ..scenarios import wallet, report, tasks


@pytest.mark.asyncio
async def test_general_logs_exclude_sensitive_materials_and_staff_actor_is_real(
    h, caplog
):
    markers = {
        k: "PRIVATE-" + k.upper() + "-MARKER-7391"
        for k in ("password", "cookie", "key", "raw_report", "comment")
    }
    markers["base64"] = base64.b64encode(png()).decode()
    await h.call(
        "login",
        actor="anon",
        payload={"login": "test_t1", "password": markers["password"]},
        expected=401,
    )
    await wallet(h.svc)
    ids = await h.create()
    h.svc.settings.polza_api_key = markers["key"]

    async def provider(job, payload):
        return TransportResult(
            "success",
            payload=report(),
            actual_cost_rub=Decimal(".01"),
            raw=markers["raw_report"],
            usage={"prompt_tokens": 12, "private_text": markers["cookie"]},
            error_code=markers["password"],
        )

    h.svc.transport = provider
    await h.submit(ids[2], ids[3], expected=202)
    await h.run()
    task = tasks(await h.check())[0]
    await h.call(
        "saveReview",
        task_id=task["task_id"],
        payload={
            "analysis_id": task["analysis_id"],
            "state": "confirmed",
            "comment": markers["comment"],
        },
        expected=200,
    )
    await h.call("getBundleHistory", actor="staff", bundle_id=ids[2], expected=200)
    photo = (await h.check())["notebooks"][0]["bundles"][0]["current_input"]["photos"][
        0
    ]["id"]
    await h.call("getPhoto", actor="staff", photo_id=photo, expected=200)
    staff = await h.svc.pool.fetch(
        "SELECT actor_id,role FROM pilot_audit WHERE name LIKE 'staff_read%'"
    )
    assert len(staff) >= 2 and all(
        str(row["actor_id"]) == h.ids["staff"] and row["role"] == "staff"
        for row in staff
    )
    audit = json.dumps(
        [
            dict(row)
            for row in await h.svc.pool.fetch("SELECT name,payload FROM pilot_audit")
        ],
        default=str,
    )
    diag = await h.svc.pool.fetchval("SELECT diagnostics FROM pilot_attempts")
    for marker in markers.values():
        assert marker not in caplog.text and marker not in audit and marker not in diag
    assert (
        await h.svc.pool.fetchval("SELECT raw_response FROM pilot_attempts")
        == markers["raw_report"]
    )
