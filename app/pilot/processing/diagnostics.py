"""Allowlisted durable timing/usage. Provider content never enters safe facts."""

import math
from decimal import Decimal, InvalidOperation

ERROR_CODES = {
    "invalid_request_configuration",
    "invalid_analysis",
    "invalid_envelope",
    "missing_choice",
    "output_limit",
    "incomplete_response",
    "invalid_json",
    "worker_exception",
    "lease_expired",
    "fixture_snapshot_mismatch",
    "fixture_temporary_failure",
    "fixture_rejected",
    "fixture_unknown",
    "fixture_invalid_response",
    "ConnectError",
    "ConnectTimeout",
    "PoolTimeout",
    "ReadTimeout",
    "ReadError",
    "WriteTimeout",
    "WriteError",
    "RemoteProtocolError",
    "LocalProtocolError",
    "ProtocolError",
    "ProxyError",
    "TimeoutException",
    "RequestError",
    "NetworkError",
    "CloseError",
    "DecodingError",
    "TooManyRedirects",
    "UnsupportedProtocol",
}
FINISH_REASONS = {
    "stop",
    "length",
    "max_tokens",
    "max_output_tokens",
    "content_filter",
    "tool_calls",
}


def safe_diagnostics(result):
    usage = {}
    if isinstance(result.usage, dict):
        for key in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "reasoning_tokens",
        ):
            value = result.usage.get(key)
            if type(value) is int and 0 <= value <= 2**63 - 1:
                usage[key] = value
    status = (
        result.http_status
        if type(result.http_status) is int and 100 <= result.http_status <= 599
        else None
    )
    elapsed = result.elapsed_seconds
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        elapsed = None
    code = result.error_code
    if code not in ERROR_CODES and code != f"http_{status}":
        code = "other_transport_error" if code else None
    try:
        amount = Decimal(str(result.actual_cost_rub))
        cost = str(amount) if amount.is_finite() and amount >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        cost = None
    return {
        "outcome": (
            result.outcome
            if result.outcome
            in (
                "success",
                "temporary_failure",
                "rejected",
                "unknown",
                "invalid_response",
            )
            else "unknown"
        ),
        "http_status": status,
        "elapsed_seconds": elapsed,
        "finish_reason": (
            result.finish_reason if result.finish_reason in FINISH_REASONS else None
        ),
        "error_code": code,
        "usage": usage,
        "actual_cost_rub": cost,
    }
