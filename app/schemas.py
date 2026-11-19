from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(StrictModel):
    username: Annotated[str, Field(min_length=1, max_length=64)]
    password: Annotated[str, Field(min_length=1, max_length=256)]


class AnalysisStatus(str, Enum):
    OK = "ok"
    NEEDS_CLEARER_PHOTO = "needs_clearer_photo"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    NOT_A_MATH_SOLUTION = "not_a_math_solution"
    PROCESSING_ERROR = "processing_error"


class AnalysisResultKind(str, Enum):
    FIRST_ERROR_FOUND = "first_error_found"
    ALL_STEPS_CORRECT = "all_steps_correct"
    NOT_ASSESSED = "not_assessed"


class StepStatus(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"


class ErrorCode(str, Enum):
    SIGN_ERROR = "sign_error"
    ARITHMETIC_ERROR = "arithmetic_error"
    FORMULA_ERROR = "formula_error"
    INVALID_TRANSFORMATION = "invalid_transformation"
    DOMAIN_OR_CONDITION = "domain_or_condition"
    LOGICAL_GAP = "logical_gap"
    OTHER = "other"


class Problem(StrictModel):
    latex: Annotated[str, Field(max_length=4000)]
    text: Annotated[str, Field(max_length=4000)]
    topic: Annotated[str, Field(max_length=100)]


class StepError(StrictModel):
    code: ErrorCode
    label: Annotated[str, Field(max_length=100)]
    explanation: Annotated[str, Field(max_length=500)]
    corrected_latex: Annotated[str | None, Field(max_length=4000)]


class AnalysisStep(StrictModel):
    number: Annotated[int, Field(ge=1)]
    latex: Annotated[str, Field(min_length=1, max_length=4000)]
    status: StepStatus
    confidence: Annotated[float, Field(ge=0, le=1)]
    error: StepError | None


class AnalysisResponse(StrictModel):
    schema_version: Literal["1.0"]
    status: AnalysisStatus
    overall_confidence: Annotated[float, Field(ge=0, le=1)]
    problem: Problem | None
    result: AnalysisResultKind
    first_incorrect_step_number: int | None
    steps: Annotated[list[AnalysisStep], Field(max_length=30)]

    @model_validator(mode="after")
    def validate_contract_invariants(self) -> "AnalysisResponse":
        if self.status is not AnalysisStatus.OK:
            if self.result is not AnalysisResultKind.NOT_ASSESSED:
                raise ValueError("Для статуса отказа result должен быть not_assessed.")
            if self.steps or self.first_incorrect_step_number is not None:
                raise ValueError("Для статуса отказа шаги и номер ошибки должны быть пустыми.")
            return self

        if self.problem is None:
            raise ValueError("В успешном разборе должно быть условие задачи.")
        if not self.steps:
            raise ValueError("В успешном разборе должен быть хотя бы один шаг.")

        expected_numbers = list(range(1, len(self.steps) + 1))
        if [step.number for step in self.steps] != expected_numbers:
            raise ValueError("Номера шагов должны идти подряд с 1.")

        if self.result is AnalysisResultKind.ALL_STEPS_CORRECT:
            if self.first_incorrect_step_number is not None:
                raise ValueError("У корректного решения не может быть номера первой ошибки.")
            if any(step.status is not StepStatus.CORRECT or step.error is not None for step in self.steps):
                raise ValueError("В корректном решении все шаги должны быть корректными без ошибки.")
            return self

        if self.result is AnalysisResultKind.FIRST_ERROR_FOUND:
            last_step = self.steps[-1]
            if self.first_incorrect_step_number != last_step.number:
                raise ValueError("Номер первой ошибки должен совпадать с последним возвращённым шагом.")
            if last_step.status is not StepStatus.INCORRECT or last_step.error is None:
                raise ValueError("Последний шаг при ошибке должен быть некорректным с пояснением.")
            if any(step.status is not StepStatus.CORRECT or step.error is not None for step in self.steps[:-1]):
                raise ValueError("До первого ошибочного шага могут быть только корректные шаги.")
            return self

        raise ValueError("Для успешного разбора нужен результат с ошибкой или все корректные шаги.")
