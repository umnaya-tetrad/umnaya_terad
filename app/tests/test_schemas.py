from pydantic import ValidationError
import pytest

from schemas import AnalysisResponse


def valid_response() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "status": "ok",
        "overall_confidence": 0.95,
        "problem": {"latex": "2x + 5 = 13", "text": "Решить уравнение", "topic": "equation"},
        "result": "first_error_found",
        "first_incorrect_step_number": 2,
        "steps": [
            {"number": 1, "latex": "2x = 8", "status": "correct", "confidence": 0.99, "error": None},
            {
                "number": 2,
                "latex": "x = 8",
                "status": "incorrect",
                "confidence": 0.98,
                "error": {
                    "code": "arithmetic_error",
                    "label": "Деление выполнено неверно",
                    "explanation": "Нужно разделить обе части на 2.",
                    "corrected_latex": "x = 4",
                },
            },
        ],
    }


def test_validates_first_error_response() -> None:
    response = AnalysisResponse.model_validate(valid_response())
    assert response.steps[-1].error is not None


def test_rejects_steps_after_first_error() -> None:
    payload = valid_response()
    payload["steps"].append(  # type: ignore[union-attr]
        {"number": 3, "latex": "x = 4", "status": "correct", "confidence": 0.99, "error": None}
    )
    with pytest.raises(ValidationError):
        AnalysisResponse.model_validate(payload)
