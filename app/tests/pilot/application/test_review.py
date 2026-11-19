from uuid import UUID, uuid4

from .conftest import mutation_headers


def test_app_c17_review_passes_only_selected_analysis_and_supports_empty_comment(adapter):
    adapter.teacher()
    task, analysis = str(uuid4()), str(uuid4())
    review = {"analysis_id": analysis, "state": "system_error", "comment": ""}
    result = adapter.client.put(f"/api/tasks/{task}/review", json=review, headers=mutation_headers())
    assert result.status_code == 200
    assert adapter.mutations.save_review.await_args.args[-2:] == (UUID(task), review)
