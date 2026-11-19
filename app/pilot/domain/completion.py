"""Completion counts and immutable server-built analytics input."""


def completion(c):
    counts = dict(
        pending_jobs=0,
        unreviewed_tasks=0,
        unresolved_tasks=0,
        unresolved_bundles=0,
        unsent_drafts=0,
    )
    active = 0
    for n in c["graph"]["notebooks"]:
        for b in n["bundles"]:
            if b["draft"] and b["draft"]["photos"]:
                counts["unsent_drafts"] += 1
            if not b["current_input"]:
                continue
            active += 1
            if b["skipped"]:
                continue
            state = b["job"]["state"] if b["job"] else None
            if state in ("queued", "running", "retry_wait", "blocked", "unknown"):
                counts["pending_jobs"] += 1
                continue
            result = b["result"]
            if (
                state != "succeeded"
                or not result
                or result["report"]["status"] == "uncheckable"
                or not result["report"]["tasks"]
            ):
                counts["unresolved_bundles"] += 1
                continue
            for t in b["tasks"]:
                if t["analysis"]["result"] == "not_assessed":
                    if not t["skipped"]:
                        counts["unresolved_tasks"] += 1
                elif t["review"] is None:
                    counts["unreviewed_tasks"] += 1
    return {
        **counts,
        "can_finalize": c["phase"] == "review"
        and active > 0
        and not any(counts.values()),
    }


def build_snapshot(c, snapshot_id):
    notebooks = []
    for n in c["graph"]["notebooks"]:
        tasks = []
        unresolved = 0
        for b in n["bundles"]:
            if not b["current_input"]:
                continue
            r = b["result"]
            valid = bool(
                b["job"]
                and b["job"]["state"] == "succeeded"
                and r
                and r["report"]["status"] == "ok"
                and r["report"]["tasks"]
                and not b["skipped"]
            )
            if not valid:
                unresolved += 1
                continue
            for t in b["tasks"]:
                tasks.append(
                    {
                        "task_id": t["task_id"],
                        "analysis_id": t["analysis_id"],
                        "analysis": t["analysis"],
                        "review_state": t["review"]["state"] if t["review"] else None,
                    }
                )
        notebooks.append(
            {"notebook_id": n["id"], "unresolved_bundles": unresolved, "tasks": tasks}
        )
    return {
        "schema_version": "summary-input/1",
        "snapshot_id": str(snapshot_id),
        "check_id": str(c["id"]),
        "data_revision": c["data_revision"],
        "notebooks": notebooks,
    }
