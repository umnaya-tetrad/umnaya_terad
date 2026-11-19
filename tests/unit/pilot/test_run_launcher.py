"""Exercise the real Bash launcher with a Docker function that cannot run Docker."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PASSWORDS = ("SyntheticTeacher1Password", "SyntheticTeacher2Password", "SyntheticStaffPassword")
API_KEY = "SyntheticPolzaKeyNeverUsed"

DOCKER_STUB = r'''
docker() {
  printf '%s\n' COMMAND "$@" END >> "$STUB_LOG"
  local joined="$*"
  case "$joined" in
    *"python -c"*)
      printf '%s\n' "LOGIN:$LOGIN" "PASSWORD:$PASSWORD" >> "$STUB_ENV_LOG"
      if [ "$LOGIN_FAILURE" = 1 ] && [ ! -f "$STUB_RESET_FILE" ]; then return 1; fi ;;
    *"manage_accounts --operator-ref run.sh reset"*)
      printf '%s\n' "RESET:$PILOT_ACCOUNT_PASSWORD" >> "$STUB_ENV_LOG"
      : > "$STUB_RESET_FILE" ;;
    *" ps "*) printf '%s\n' 'postgres healthy' 'backend healthy' 'worker healthy' 'frontend healthy' ;;
  esac
  return 0
}
export -f docker
exec "$BASH" "$RUN_SCRIPT" "$RUN_COMMAND"
'''


@pytest.fixture
def launcher(tmp_path):
    if os.name == "nt":
        bash = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Git/bin/bash.exe"
        if not bash.is_file():
            pytest.fail("Git Bash is required for launcher regression tests on Windows")
    else:
        bash = shutil.which("bash")
        assert bash, "Bash is required for launcher regression tests"

    env_file = tmp_path / "private" / "pilot.env"
    env_file.parent.mkdir()
    env_file.write_text("\n".join((
        "PILOT_TRANSPORT=fixture",
        "POSTGRES_PASSWORD=SyntheticDatabasePassword",
        "VISITOR_COOKIE_SECRET=" + "SyntheticCookieSecret" * 3,
        "POLZA_API_KEY=" + API_KEY,
        "PILOT_FIXTURE_TEACHER_1_LOGIN=existing-teacher",
        "PILOT_FIXTURE_TEACHER_1_PASSWORD=" + PASSWORDS[0],
        "PILOT_FIXTURE_TEACHER_2_LOGIN=second-teacher",
        "PILOT_FIXTURE_TEACHER_2_PASSWORD=" + PASSWORDS[1],
        "PILOT_FIXTURE_STAFF_LOGIN=existing-staff",
        "PILOT_FIXTURE_STAFF_PASSWORD=" + PASSWORDS[2],
        "",
    )))
    logs = tmp_path / "docker-argv.log"
    secrets = tmp_path / "docker-child-env.log"
    environment = dict(os.environ)
    # Never read a developer's saved credentials or allow inherited secret aliases.
    for key in tuple(environment):
        if key.startswith(("PILOT_", "POLZA_", "POSTGRES_", "VISITOR_")) or key in (
            "PASSWORD", "TEACHER2_PASSWORD", "STAFF_PASSWORD", "LOGIN", "TEACHER2_LOGIN",
            "STAFF_LOGIN", "MODE", "PROJECT", "PORT", "COMPOSE_PROJECT_NAME",
        ):
            environment.pop(key)
    environment.update({
        "MODE": "fixture", "PROJECT": "smartnote-launcher-unit-only",
        "PILOT_ENV_FILE": env_file.as_posix(), "RUN_SCRIPT": (ROOT / "run.sh").as_posix(),
        "STUB_LOG": logs.as_posix(), "STUB_ENV_LOG": secrets.as_posix(),
        "STUB_RESET_FILE": (tmp_path / "did-reset").as_posix(), "LOGIN_FAILURE": "0",
    })

    def run(command, **updates):
        result = subprocess.run(
            [str(bash), "--noprofile", "--norc", "-c", DOCKER_STUB],
            env={**environment, "RUN_COMMAND": command, **updates},
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        return result, logs.read_text() if logs.exists() else "", secrets.read_text() if secrets.exists() else ""

    return run, env_file


def assert_no_secret_arguments_or_output(result, arguments):
    for secret in (*PASSWORDS, API_KEY, "SyntheticDatabasePassword", "SyntheticCookieSecret"):
        assert secret not in arguments
        assert secret not in result.stdout + result.stderr
    assert "PASSWORD=" not in arguments
    assert "PILOT_ACCOUNT_PASSWORD=" not in arguments


def test_up_passes_passwords_by_environment_name_and_keeps_existing_credentials(launcher):
    run, env_file = launcher
    result, arguments, child_environment = run("up")
    assert result.returncode == 0, result.stderr
    assert_no_secret_arguments_or_output(result, arguments)
    assert "\n-e\nPASSWORD\n" in arguments
    assert "\n-p\nsmartnote-launcher-unit-only\n" in arguments
    assert "LOGIN:existing-teacher" in child_environment
    for secret in PASSWORDS:
        assert f"PASSWORD:{secret}" in child_environment
        assert secret in env_file.read_text()
    assert "reset\n" not in arguments
    assert "Готово." in result.stdout


def test_up_refuses_password_mismatch_without_resetting_account(launcher):
    run, _ = launcher
    result, arguments, child_environment = run("up", LOGIN_FAILURE="1")
    assert result.returncode != 0
    assert_no_secret_arguments_or_output(result, arguments)
    assert "./run.sh reset" in result.stderr
    assert "reset\n" not in arguments
    assert "RESET:" not in child_environment
    assert "Готово." not in result.stdout


def test_explicit_reset_passes_password_in_environment_only(launcher):
    run, _ = launcher
    result, arguments, child_environment = run("reset", LOGIN_FAILURE="1")
    assert result.returncode == 0, result.stderr
    assert_no_secret_arguments_or_output(result, arguments)
    assert "\n-e\nPILOT_ACCOUNT_PASSWORD\n" in arguments
    assert f"RESET:{PASSWORDS[0]}" in child_environment
    assert "\n--operator-ref\nrun.sh\nreset\n--login\nexisting-teacher\n" in arguments


@pytest.mark.parametrize("command", ["stop", "status", "restart", "budget", "pause", "help"])
def test_existing_local_commands_remain_available(launcher, command):
    run, _ = launcher
    result, arguments, _ = run(command)
    assert result.returncode == 0, result.stderr
    assert_no_secret_arguments_or_output(result, arguments)


def test_environment_secret_aliases_are_supported_without_argv_leak(launcher):
    run, env_file = launcher
    result, arguments, child_environment = run("up", PASSWORD="SyntheticOverridePassword")
    assert result.returncode == 0, result.stderr
    assert "PASSWORD:SyntheticOverridePassword" in child_environment
    assert "SyntheticOverridePassword" in env_file.read_text()
    assert "SyntheticOverridePassword" not in arguments + result.stdout + result.stderr
