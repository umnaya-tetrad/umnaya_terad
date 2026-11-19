"""Generated portable DTO types; validate all untrusted data with JSON Schema."""

from __future__ import annotations

from typing import Literal, Optional, TypedDict, Union



class CheckerError(TypedDict):
    photo_index: int
    wrong_latex: str
    rule: str
    explanation: str
    corrected_latex: str

class CheckerEvidence(TypedDict):
    photo_index: int
    latex: str

class CheckerTask(TypedDict):
    task_id: str
    locator: str
    photo_indices: list[int]
    condition: str
    result: Literal['all_steps_correct', 'first_error_found', 'not_assessed']
    completeness: Literal['complete', 'incomplete', 'unknown']
    detail_level: Literal['sufficient', 'omitted_steps', 'partial', 'unknown']
    omitted_steps_note: str
    completeness_note: str
    evidence: list[CheckerEvidence]
    first_error: Optional[CheckerError]
    uncheckable_reason: str

class CheckerReport(TypedDict):
    schema_version: Literal['page-check/1.2']
    status: Literal['ok', 'uncheckable']
    tasks: list[CheckerTask]
    message: str

class ClassSummary(TypedDict):
    schema_version: Literal['class-summary/1']
    notebooks: ClassSummaryNotebooks
    average_errors_per_notebook: Union[float, None]
    incomplete_tasks: int
    disputed_tasks: int
    unassessed_tasks: int
    top_errors: list[ClassSummaryTopErrorsitem]

class ClassSummaryNotebooks(TypedDict):
    total: int
    with_errors: int
    without_errors: int
    partial: int
    empty: int

class ClassSummaryTopErrorsitem(TypedDict):
    rule: str
    task_ids: list[str]

class Error(TypedDict):
    code: Literal['invalid_input', 'unauthenticated', 'forbidden', 'not_found', 'revision_conflict', 'idempotency_conflict', 'invalid_state', 'completion_blocked', 'stale_analysis', 'processing_unavailable']
    message: str
    current_revision: Optional[int]

class ErrorResponse(TypedDict):
    error: Error

class Login(TypedDict):
    login: str
    password: str

class Session(TypedDict):
    user_id: str
    role: Literal['teacher', 'staff']

class Title(TypedDict):
    title: str

class Photo(TypedDict):
    id: str
    media_type: Literal['image/jpeg', 'image/png', 'image/webp']

class InputVersion(TypedDict):
    id: str
    state: Literal['draft', 'sealed']
    photos: list[Photo]

class PhotoOrder(TypedDict):
    photo_ids: list[str]

class VersionCreate(TypedDict):
    photo_ids: list[str]

class Submit(TypedDict):
    input_version_id: str

class ReviewWrite(TypedDict):
    analysis_id: str
    state: Literal['confirmed', 'system_error']
    comment: str

class Review(TypedDict):
    state: Literal['confirmed', 'system_error']
    comment: str

class AnalysisTarget(TypedDict):
    analysis_id: str

class InputTarget(TypedDict):
    input_version_id: str

class TaskAnalysis(TypedDict):
    task_id: str
    analysis_id: str
    analysis: CheckerTask
    review: Optional[Review]
    skipped: bool

class Job(TypedDict):
    id: str
    kind: Literal['page_check', 'class_analytics']
    input_id: str
    state: Literal['queued', 'running', 'retry_wait', 'blocked', 'unknown', 'succeeded', 'failed', 'cancelled', 'superseded']
    reason: Optional[Literal['funds_unavailable', 'service_paused', 'provider_outcome_unknown', 'temporary_failure', 'provider_rejected', 'invalid_response', 'input_uncheckable', 'deleted', 'replaced', 'skipped']]
    can_retry: bool

class BundleReport(TypedDict):
    id: str
    input_version_id: str
    report: CheckerReport

class Bundle(TypedDict):
    id: str
    draft: Optional[InputVersion]
    current_input: Optional[InputVersion]
    job: Optional[Job]
    result: Optional[BundleReport]
    tasks: list[TaskAnalysis]
    skipped: bool

class Notebook(TypedDict):
    id: str
    number: int
    bundles: list[Bundle]

class Completion(TypedDict):
    pending_jobs: int
    unreviewed_tasks: int
    unresolved_tasks: int
    unresolved_bundles: int
    unsent_drafts: int
    can_finalize: bool

class Summary(TypedDict):
    state: Literal['not_started', 'queued', 'running', 'retry_wait', 'blocked', 'unknown', 'succeeded', 'failed', 'cancelled', 'superseded']
    stale: bool
    snapshot_id: Optional[str]
    job_id: Optional[str]
    data_revision: Optional[int]
    can_retry: bool
    can_refresh: bool
    result: Optional[ClassSummary]

class CheckListItem(TypedDict):
    id: str
    title: str
    phase: Literal['editing', 'review', 'finalized']
    revision: int
    created_at: str

class Check(TypedDict):
    id: str
    title: str
    phase: Literal['editing', 'review', 'finalized']
    revision: int
    created_at: str
    data_revision: int
    notebooks: list[Notebook]
    completion: Completion
    summary: Summary

class Checks(TypedDict):
    items: list[CheckListItem]
    next_cursor: Optional[str]

class Owner(TypedDict):
    user_id: str
    login: str

class StaffCheckListItem(TypedDict):
    owner: Owner
    check: CheckListItem

class StaffChecks(TypedDict):
    items: list[StaffCheckListItem]
    next_cursor: Optional[str]

class StaffCheck(TypedDict):
    owner: Owner
    check: Check

class Mutation(TypedDict):
    check_id: str
    check_revision: int
    entity_id: Optional[str]
    job: Optional[Job]

class HistoryRun(TypedDict):
    job: Job
    result: Optional[BundleReport]
    tasks: list[TaskAnalysis]
    deleted_task_ids: list[str]

class HistoryVersion(TypedDict):
    input: InputVersion
    runs: list[HistoryRun]

class BundleHistory(TypedDict):
    bundle_id: str
    versions: list[HistoryVersion]

class SummaryHistoryItem(TypedDict):
    created_at: str
    summary: Summary

class SummaryHistory(TypedDict):
    items: list[SummaryHistoryItem]

class Event(TypedDict):
    id: str
    session_id: str
    occurred_at: str
    name: Literal['capture_opened', 'photo_selected', 'result_opened', 'result_closed', 'app_visible', 'app_hidden', 'heartbeat']
    check_id: Optional[str]
    entity_id: Optional[str]

class Events(TypedDict):
    events: list[Event]

class EventsAccepted(TypedDict):
    accepted_ids: list[str]
