from model_catalog import DEFAULT_POLZA_MODEL, get_application_model_options


def test_application_model_reuses_successful_gemini_smoke_parameters() -> None:
    options = get_application_model_options(DEFAULT_POLZA_MODEL)

    assert options.response_format_type == "json_object"
    assert options.temperature == 0
    assert options.max_completion_tokens == 4000
