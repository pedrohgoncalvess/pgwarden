"""Run the actual Bash installer with mocked Git and Docker, without deployment."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
if os.name == "nt" and Path("C:/Program Files/Git/bin/bash.exe").exists():
    BASH = "C:/Program Files/Git/bin/bash.exe"
pytestmark = pytest.mark.skipif(not BASH, reason="Bash required")


@pytest.fixture
def environment(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for name in ["collector", "docker", "scripts"]:
        (source / name).mkdir()
    for name in [
        "config.yaml",
        "docker-compose.yaml",
        "collector/main.py",
        "collector/config.sqlite.example.yaml",
        "docker/.env.collector.example",
    ]:
        shutil.copyfile(ROOT / name, source / name)
    # An external downloaded installer must clone, rather than reuse its own root.
    script = tmp_path / "install.sh"
    shutil.copyfile(ROOT / "scripts/install.sh", script)
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    (mock_bin / "git").write_text(
        """#!/usr/bin/env bash
set -eu
printf 'git %s\\n' "$*" >> "$CALL_LOG"
if [[ "$1" == clone ]]; then
  destination="${@: -1}"
  cp -R -- "$FIXTURE_REPO" "$destination"
fi
""",
        newline="\n",
    )
    (mock_bin / "docker").write_text(
        """#!/usr/bin/env bash
set -eu
printf 'docker %s\\n' "$*" >> "$CALL_LOG"
if [[ "$1" == run ]]; then
  while [[ "$1" != python:3.13-slim ]]; do shift; done
  shift 2
  exec "$TEST_PYTHON" "$@"
fi
""",
        newline="\n",
    )
    for program in mock_bin.iterdir():
        program.chmod(0o755)
    env = os.environ.copy()
    bin_path = mock_bin.as_posix()
    if os.name == "nt":
        bin_path = "/" + bin_path[0].lower() + bin_path[2:]
    env.update(
        FIXTURE_REPO=source.as_posix(),
        CALL_LOG=(tmp_path / "calls.log").as_posix(),
        TEST_PYTHON=Path(sys.executable).as_posix(),
        MOCK_BIN=bin_path,
    )

    # Use Bash to set its own POSIX PATH, including on Windows/Git Bash.
    def run(mode, directory, *options):
        return subprocess.run(
            [
                BASH,
                "-c",
                'export PATH="$MOCK_BIN:$PATH"; exec bash "$@"',
                "test",
                script.as_posix(),
                mode,
                "--dir",
                directory.as_posix(),
                *options,
            ],
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
        )

    return run, tmp_path, env


@pytest.mark.parametrize("mode", ["full", "server"])
def test_clone_generate_start_and_preserve_existing_secrets(environment, mode):
    run, path, env = environment
    destination = path / "install with spaces"
    result = run(mode, destination)
    assert result.returncode == 0, result.stdout + result.stderr
    secret = (destination / ".env").read_bytes()
    assert b"replace-with" not in secret
    if mode == "full":
        assert (destination / "config.local.yaml").exists()
    result = run(mode, destination)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (destination / ".env").read_bytes() == secret
    calls = Path(env["CALL_LOG"]).read_text()
    assert calls.count("git clone ") == 1
    assert "up -d --build" in calls
    assert "git pull" not in calls
    expected = (
        "docker-compose.yaml" if mode == "full" else "docker/docker-compose.server.yaml"
    )
    assert f"-f {expected}" in calls


def test_collector_requires_configuration_before_start(environment):
    run, path, env = environment
    destination = path / "collector"
    result = run("collector", destination, "--configure-only")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (destination / ".env.sqlite").exists()
    assert (destination / "config.sqlite.yaml").exists()
    result = run("collector", destination)
    assert result.returncode != 0
    assert "Edit .env.sqlite" in result.stderr
    assert "up -d --build" not in Path(env["CALL_LOG"]).read_text()
    config = destination / "config.sqlite.yaml"
    config.write_text(
        config.read_text()
        .replace("postgres.internal", "postgres.lan")
        .replace("replace-with-monitor-password", "local-password")
    )
    config = destination / ".env.sqlite"
    config.write_text(
        config.read_text()
        .replace("https://pgwarden.example.com", "https://warden.lan")
        .replace("pgw_replace-with-project-ingestion-key", "pgw_real_project_key")
    )
    result = run("collector", destination)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        "-p pgwarden-local -f docker/docker-compose.collector-sqlite.yaml"
        in Path(env["CALL_LOG"]).read_text()
    )
