"""Contract artifact tests, not substitutes for runtime/PostgreSQL acceptance."""
import copy
import importlib.util
import sys
from pathlib import Path

import pytest
from jsonschema import ValidationError

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import validate as contract

CASES = contract.read(HERE / "fixtures/lifecycle.json")


def load_analytics_validator():
    spec = importlib.util.spec_from_file_location("smartnote_analytics_contract_validator", HERE.parent / "analytics/validate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def as_snapshot(check):
    notebooks = []
    for notebook in check["notebooks"]:
        unresolved = 0
        tasks = []
        for bundle in notebook["bundles"]:
            if bundle["current_input"]:
                report = bundle["result"]["report"] if bundle["result"] else None
                unresolved += int(bundle["skipped"] or report is None or report["status"] != "ok" or not report["tasks"])
            for task in bundle["tasks"]:
                tasks.append({"task_id": task["task_id"], "analysis_id": task["analysis_id"],
                              "review_state": task["review"]["state"] if task["review"] else None, "analysis": task["analysis"]})
        notebooks.append({"notebook_id": notebook["id"], "unresolved_bundles": unresolved, "tasks": tasks})
    return {"schema_version": "summary-input/1", "snapshot_id": "3417a6f7-22da-496b-bdb2-2097f85e182b",
            "check_id": check["id"], "data_revision": check["data_revision"], "notebooks": notebooks}


def tasks(check):
    return [t for n in check["notebooks"] for b in n["bundles"] for t in b["tasks"]]


def test_formal_openapi_all_http_and_frozen_examples():
    contract.run()


def test_generated_types_and_schemas_do_not_drift():
    from build_contract import check_generated
    check_generated()
    compile((HERE / "contracts.py").read_text(encoding="utf-8"), "contracts.py", "exec")


def test_history_preserves_two_successful_generations_of_same_input():
    fixtures = contract.read(HERE / "fixtures/http.json")
    history = next(item for item in fixtures if item["name"] == "getBundleHistory")["response"]["body"]
    contract.validate_history(history)
    version = history["versions"][0]
    old, new = version["runs"]
    assert old["job"]["input_id"] == new["job"]["input_id"] == version["input"]["id"]
    assert old["job"]["id"] != new["job"]["id"]
    assert old["result"] != new["result"]
    assert old["tasks"][0]["review"] != new["tasks"][0]["review"]
    assert old["deleted_task_ids"] and not new["deleted_task_ids"]


def test_no_unused_rename_routes_and_notebook_creation_has_no_input_name():
    document = contract.read(HERE / "openapi.json")
    assert "patch" not in document["paths"]["/api/checks/{check_id}"]
    assert "patch" not in document["paths"]["/api/notebooks/{notebook_id}"]
    assert "requestBody" not in document["paths"]["/api/checks/{check_id}/notebooks"]["post"]
    with pytest.raises(ValidationError):
        contract.domain({"id": "3417a6f7-22da-496b-bdb2-2097f85e182b", "label": "Имя ученика", "bundles": []}, "Notebook")
    with pytest.raises(ValidationError):
        contract.domain({"id": "3417a6f7-22da-496b-bdb2-2097f85e182b", "number": 0, "bundles": []}, "Notebook")


def test_synthetic_png_meets_frozen_adapter_edge_and_crc():
    assert contract.validate_png(HERE / "fixtures/synthetic-photo.png") == (64, 64)


@pytest.mark.parametrize("case", contract.read(HERE / "fixtures/summary-guards.json"))
def test_refresh_and_retry_guards_have_explicit_server_context(case):
    # This is a contract oracle for the future transactional service, not that service.
    terminal = case["state"] in ("succeeded", "failed", "cancelled", "superseded")
    unsent = case["state"] in ("queued", "blocked") and not case["has_provider_attempt"]
    assert case["can_refresh"] == (case["phase"] == "finalized" and case["stale"] and (terminal or unsent))
    assert case["can_retry"] == (case["phase"] == "finalized" and not case["stale"] and case["state"] == "failed" and case["declared_safe"])


def test_running_stale_summary_cannot_advertise_refresh_and_blocked_cannot_retry():
    running = copy.deepcopy(CASES["stale-analytics-running"])
    running["summary"]["can_refresh"] = True
    with pytest.raises(AssertionError, match="unsafe summary refresh"):
        contract.validate_check(running)
    blocked = copy.deepcopy(CASES["stale-analytics-blocked"])
    blocked["summary"].update(stale=False, data_revision=blocked["data_revision"], can_retry=True, can_refresh=False)
    with pytest.raises(AssertionError, match="unsafe summary retry"):
        contract.validate_check(blocked)
    fixtures = contract.read(HERE / "fixtures/http.json")
    jobs = {item["name"]: item["response"]["body"]["job"] for item in fixtures if item["name"] in ("finalizeCheck", "refreshSummary", "retrySummary")}
    assert jobs["refreshSummary"]["input_id"] != jobs["finalizeCheck"]["input_id"]
    assert jobs["retrySummary"]["input_id"] == jobs["finalizeCheck"]["input_id"]
    assert len({value["id"] for value in jobs.values()}) == 3


@pytest.mark.parametrize("case", sorted(CASES))
def test_every_lifecycle_snapshot(case):
    contract.validate_check(CASES[case])
    load_analytics_validator().validate_input(as_snapshot(CASES[case]))


def test_saved_llm_summary_uses_exact_snapshot_formulas():
    value = CASES["saved-analytics"]
    load_analytics_validator().validate_pair(as_snapshot(value), value["summary"]["result"])


def test_unknown_unapproved_field_is_rejected():
    value = copy.deepcopy(CASES["multi-task-confirmed"])
    value["confidence"] = 0.9
    with pytest.raises(ValidationError):
        contract.domain(value, "Check")


def test_uuid_is_checked_not_only_string_type():
    value = copy.deepcopy(CASES["multi-task-confirmed"])
    value["id"] = "check-example"
    with pytest.raises(ValidationError):
        contract.domain(value, "Check")


def test_frozen_error_consistency_and_photo_membership():
    report = copy.deepcopy(CASES["multi-task-confirmed"]["notebooks"][0]["bundles"][0]["result"]["report"])
    report["tasks"][0]["first_error"] = None
    with pytest.raises(AssertionError, match="first_error/result"):
        contract.validate_report(report, 1)
    report = copy.deepcopy(CASES["two-photo-continuation"]["notebooks"][0]["bundles"][0]["result"]["report"])
    report["tasks"][0]["evidence"][0]["photo_index"] = 9
    with pytest.raises(AssertionError, match="outside"):
        contract.validate_report(report, 2)


def test_mixed_skip_does_not_confirm_unassessed_or_exclude_neighbor():
    value = copy.deepcopy(CASES["mixed-skip-only-one-task"])
    first, second = tasks(value)
    assert first["review"]["state"] == "confirmed" and second["skipped"] and second["review"] is None
    assert value["completion"]["can_finalize"]
    second["review"] = {"state": "confirmed", "comment": ""}
    with pytest.raises(AssertionError, match="not mathematical confirmation"):
        contract.validate_check(value)


def test_false_zero_after_failed_or_unknown_skipped_input_is_rejected():
    validator = load_analytics_validator()
    for name in ("skipped-failed-bundle-stays-partial", "skipped-unknown-attempt-reserve-retained"):
        snapshot = as_snapshot(CASES[name])
        assert snapshot["notebooks"][0]["unresolved_bundles"] == 1
        fake = {"schema_version": "class-summary/1", "notebooks": {"total": 1, "with_errors": 0, "without_errors": 1, "partial": 0, "empty": 0},
                "average_errors_per_notebook": 0, "incomplete_tasks": 0, "disputed_tasks": 0, "unassessed_tasks": 0, "top_errors": []}
        with pytest.raises(ValueError):
            validator.validate_pair(snapshot, fake)


def test_unreviewed_and_nonempty_draft_block_final_agreement():
    for name in ("completion-waits-checker", "unsent-draft-blocks-finalize", "new-segmentation-two-to-three"):
        value = copy.deepcopy(CASES[name])
        value["completion"]["can_finalize"] = True
        with pytest.raises(AssertionError, match="completion"):
            contract.validate_check(value)


def test_red_is_resolved_but_not_confirmed():
    value = CASES["red-resolves-review-excluded-from-math"]
    assert value["completion"]["can_finalize"] and sum(t["review"]["state"] == "confirmed" for t in tasks(value)) == 1


def test_new_segmentation_has_no_old_ids_or_review_inheritance():
    old = tasks(CASES["multi-task-confirmed"])
    new = tasks(CASES["new-segmentation-two-to-three"])
    assert len(old) == 2 and len(new) == 3
    assert not ({t["task_id"] for t in old} & {t["task_id"] for t in new})
    assert not ({t["analysis_id"] for t in old} & {t["analysis_id"] for t in new})
    assert all(t["review"] is None for t in new)


def test_tombstone_excludes_task_without_rewriting_original_report():
    old = CASES["multi-task-confirmed"]["notebooks"][0]["bundles"][0]
    deleted = CASES["task-deleted-report-retained"]["notebooks"][0]["bundles"][0]
    assert old["result"] == deleted["result"]
    assert old["tasks"][0]["task_id"] not in {t["task_id"] for t in deleted["tasks"]}
    assert len(deleted["tasks"]) == 1


def test_comment_changes_guard_but_not_math_revision_or_freshness():
    old, changed = CASES["saved-analytics"], CASES["comment-keeps-analytics-current"]
    assert changed["revision"] > old["revision"]
    assert changed["data_revision"] == old["data_revision"] and not changed["summary"]["stale"]
    assert as_snapshot(changed) == as_snapshot(old)


def test_review_state_changes_snapshot_and_stales_saved_result():
    old, changed = CASES["saved-analytics"], CASES["review-change-stales-analytics"]
    assert changed["data_revision"] > old["data_revision"] and changed["summary"]["stale"]
    assert as_snapshot(changed) != as_snapshot(old)


def test_offline_registry_rejects_network_and_outside_repo():
    with pytest.raises(ValueError):
        contract.retrieve("https://example.org/remote-schema.json")
    with pytest.raises(ValueError):
        contract.retrieve((HERE.anchor and Path(HERE.anchor) / "outside-schema.json").as_uri())
