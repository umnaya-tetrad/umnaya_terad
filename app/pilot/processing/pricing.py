"""Conservative request ceiling from verified Polza model metadata, 2026-11-19.

Model context 1048576, route prompt/image <=50 RUB/M, completion <=250 RUB/M.
Actual observed route prices were 45.4064625/227.0323125 RUB/M. We reserve
ceilings over full model input context plus the actual completion cap, never a
benchmark mean. Metadata GET was free; it is not a new mathematical benchmark.
"""

from .transport import MODEL, PROVIDER


def default_pricing_profile():
    return {
        "verified": True,
        "profile_id": "polza-gemini38-flex-20261119",
        "model": MODEL,
        "provider": PROVIDER,
        "max_input_tokens": 1048576,
        "max_output_tokens": 25000,
        "prompt_rub_per_million": "50",
        "image_rub_per_million": "50",
        "completion_rub_per_million": "250",
        "request_rub": "0",
    }
