from pilot.operations.create_fixture_accounts import ACCOUNTS, fixture_credentials
import pytest


def test_app_c03_session_cookie_and_exact_origin(adapter):
    client = adapter.client
    body = {"login": "synthetic_teacher", "password": "synthetic-fixture-only"}
    assert client.get("/api/auth/session").status_code == 401
    for origin in (None, "https://pilot.test.evil.invalid", "https://pilot.test/"):
        headers = {"Origin": origin} if origin else {}
        assert client.post("/api/auth/login", json=body, headers=headers).status_code == 403
    adapter.auth.authenticate.assert_not_awaited()

    assert client.post("/api/auth/login", json={**body, "role": "staff"}, headers={"Origin": "https://pilot.test"}).status_code == 422
    result = client.post("/api/auth/login", json=body, headers={"Origin": "https://pilot.test"})
    assert result.status_code == 200
    assert set(result.json()) == {"user_id", "role"}
    cookie = result.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" in cookie
    assert client.get("/api/auth/session").json() == result.json()

    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"Origin": "https://pilot.test"}).status_code == 204
    adapter.auth.revoke.assert_awaited_once()
    assert client.get("/api/auth/session").status_code == 401
    assert client.post("/api/auth/register", json=body).status_code == 404


def test_app_c02_seed_requires_three_distinct_environment_logins(monkeypatch):
    for index, (name, _role) in enumerate(ACCOUNTS):
        monkeypatch.setenv(f"PILOT_FIXTURE_{name}_LOGIN", f"synthetic-{index}")
        monkeypatch.setenv(f"PILOT_FIXTURE_{name}_PASSWORD", "synthetic-fixture-only")
    assert [entry[2] for entry in fixture_credentials()] == ["teacher", "teacher", "staff"]
    monkeypatch.setenv("PILOT_FIXTURE_STAFF_LOGIN", "SYNTHETIC-0")
    with pytest.raises(ValueError, match="distinct"):
        fixture_credentials()
    monkeypatch.delenv("PILOT_FIXTURE_STAFF_PASSWORD")
    with pytest.raises(ValueError, match="PILOT_FIXTURE_STAFF_PASSWORD"):
        fixture_credentials()
