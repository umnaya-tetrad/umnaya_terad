"""Independent requirement cases for saved LLM analytics contracts."""
import importlib.util
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("analytics_validate", HERE / "validate.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def pair(name="oracle"):
    return (module.load(HERE / "fixtures" / f"{name}.input.json"), module.load(HERE / "fixtures" / f"{name}.result.json"))


@pytest.mark.parametrize("name", ["oracle", "zero-denominator", "mixed", "synonyms"])
def test_saved_cases(name):
    module.validate_pair(*pair(name))


def test_partial_notebook_error_not_in_average_but_in_top():
    snapshot, result = pair()
    assert result["average_errors_per_notebook"] == 0.5
    assert sum(len(g["task_ids"]) for g in result["top_errors"]) == 2
    result["average_errors_per_notebook"] = 1
    with pytest.raises(ValueError, match="average"):
        module.validate_pair(snapshot, result)


def test_empty_denominator_is_not_zero():
    snapshot, result = pair("zero-denominator")
    result["average_errors_per_notebook"] = 0
    with pytest.raises(ValueError, match="null"):
        module.validate_pair(snapshot, result)


def test_disputed_error_cannot_become_top_reference():
    snapshot, result = pair()
    disputed = snapshot["notebooks"][2]["tasks"][1]["task_id"]
    result["top_errors"][0]["task_ids"] = [disputed]
    with pytest.raises(ValueError, match="reference"):
        module.validate_pair(snapshot, result)


def test_not_assessed_does_not_fully_confirm_notebook():
    snapshot, result = pair("mixed")
    snapshot["notebooks"][0]["tasks"][1]["review_state"] = "confirmed"
    module.validate_pair(snapshot, result)


def test_duplicate_task_ids_rejected():
    snapshot, result = pair()
    snapshot["notebooks"][1]["tasks"][0]["task_id"] = snapshot["notebooks"][0]["tasks"][0]["task_id"]
    with pytest.raises(ValueError, match="Duplicate"):
        module.validate_pair(snapshot, result)


def test_top_task_cannot_belong_to_two_rules():
    snapshot, result = pair()
    result["top_errors"][1]["task_ids"] = result["top_errors"][0]["task_ids"][:]
    with pytest.raises(ValueError, match="duplicate"):
        module.validate_pair(snapshot, result)


def test_comment_is_not_accepted_in_analytics_snapshot():
    snapshot, result = pair()
    snapshot["notebooks"][0]["tasks"][0]["comment"] = "Support only"
    with pytest.raises(ValidationError):
        module.validate_pair(snapshot, result)


def test_unknown_result_field_rejected():
    snapshot, result = pair()
    result["confidence"] = 0.9
    with pytest.raises(ValidationError):
        module.validate_pair(snapshot, result)


def test_changed_review_invalidates_old_numbers():
    snapshot, result = pair()
    snapshot["notebooks"][0]["tasks"][0]["review_state"] = "system_error"
    with pytest.raises(ValueError, match="counts"):
        module.validate_pair(snapshot, result)


def test_unresolved_bundle_prevents_false_zero_work():
    snapshot, result = pair()
    snapshot["notebooks"][1]["unresolved_bundles"] = 1
    with pytest.raises(ValueError, match="counts"):
        module.validate_pair(snapshot, result)


def test_checker_error_invariant_kept():
    snapshot, result = pair()
    snapshot["notebooks"][0]["tasks"][0]["analysis"]["first_error"] = None
    with pytest.raises(ValueError, match="mismatch"):
        module.validate_pair(snapshot, result)
