"""Pilot replacement of the source headerless-CLI origin exception.

The unmodified source auth unit tests are preserved alongside this file.
Legacy landing/register/anonymous analysis/quota HTTP tests require the old
application bootstrap and are outside the processing-only application surface.
"""

import pytest
from starlette.requests import Request
from config import Settings
from security import write_origin_allowed


def request(origin=None, **extra):
    headers = {**extra}
    if origin is not None:
        headers["origin"] = origin
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        }
    )


@pytest.mark.parametrize(
    "origin",
    [None, "null", "https://evil.example", "https://umnaya-tetrad.ru.evil.example"],
)
def test_pilot_requires_exact_origin_including_login(origin):
    assert not write_origin_allowed(request(origin), Settings())


@pytest.mark.parametrize(
    "origin",
    [
        "https://umnaya-tetrad.ru",
        "https://www.umnaya-tetrad.ru",
        "http://localhost:5173",
    ],
)
def test_source_configured_exact_origins_remain_allowed(origin):
    assert write_origin_allowed(request(origin), Settings())


def test_source_cross_site_browser_metadata_stays_denied():
    assert not write_origin_allowed(
        request("https://umnaya-tetrad.ru", **{"Sec-Fetch-Site": "cross-site"}),
        Settings(),
    )
