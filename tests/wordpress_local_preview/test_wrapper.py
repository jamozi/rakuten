from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
from collections.abc import Iterator

import pytest


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "changes/wordpress-local-preview-v1/bin/wordpress_preview.sh"


def _private_root(tmp_path: Path) -> Path:
    suffix = hashlib.sha256(str(tmp_path).encode()).hexdigest()[:16]
    return Path("/tmp") / f"raos-wordpress-preview-test.{suffix}"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


@pytest.fixture
def fake_runtime(tmp_path: Path) -> Iterator[dict[str, str]]:
    docker_log = tmp_path / "docker.log"
    fake_docker = tmp_path / "docker"
    fake_curl = tmp_path / "curl"
    _write_executable(
        fake_docker,
        """#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >>"$RAOS_FAKE_DOCKER_LOG"
if [[ "$*" == "compose version" ]]; then
  exit 0
fi
if [[ "${RAOS_FAKE_DOCKER_UP_FAIL:-0}" == 1 && "$*" == *" up --detach database wordpress gateway"* ]]; then
  exit 42
fi
if [[ "$*" == *" core is-installed"* && "${RAOS_FAKE_CORE_INSTALLED:-1}" == 0 ]]; then
  exit 1
fi
if [[ "$*" == *" option get home"* ]]; then
  printf '%s\\n' 'http://127.0.0.1:8888'
fi
if [[ "$*" == *" theme list --name=kurashinoshirube-child --field=status"* ]]; then
  printf '%s\\n' active
fi
exit 0
""",
    )
    _write_executable(fake_curl, "#!/usr/bin/env bash\nexit 0\n")
    private_root = _private_root(tmp_path)
    shutil.rmtree(private_root, ignore_errors=True)
    yield {
        "RAOS_FAKE_DOCKER_LOG": str(docker_log),
        "RAOS_WORDPRESS_PREVIEW_CURL_BIN": str(fake_curl),
        "RAOS_WORDPRESS_PREVIEW_DOCKER_BIN": str(fake_docker),
        "RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT": str(private_root),
    }
    shutil.rmtree(private_root, ignore_errors=True)


def _run(
    command: str,
    environment: dict[str, str],
    *,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(WRAPPER), command],
        cwd=ROOT,
        env={**os.environ, **environment},
        check=check,
        capture_output=True,
        text=True,
    )


def test_missing_docker_is_reported_without_creating_private_state(
    tmp_path: Path,
) -> None:
    private_root = _private_root(tmp_path)
    shutil.rmtree(private_root, ignore_errors=True)
    result = _run(
        "up",
        {
            "RAOS_WORDPRESS_PREVIEW_DOCKER_BIN": str(tmp_path / "missing-docker"),
            "RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT": str(private_root),
        },
    )
    assert result.returncode == 69
    assert result.stderr.strip() == "RAOS_WORDPRESS_PREVIEW_DOCKER_UNAVAILABLE"
    assert not private_root.exists()


def test_broad_private_root_override_is_rejected_before_docker(tmp_path: Path) -> None:
    result = _run(
        "up",
        {
            "RAOS_WORDPRESS_PREVIEW_DOCKER_BIN": str(tmp_path / "missing-docker"),
            "RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT": str(tmp_path),
        },
    )
    assert result.returncode == 69
    assert result.stderr.strip() == "RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT_INVALID"


def test_up_generates_private_credentials_and_runs_initial_seed(
    fake_runtime: dict[str, str],
) -> None:
    environment = {
        **fake_runtime,
        "RAOS_FAKE_CORE_INSTALLED": "0",
    }
    result = _run("up", environment, check=True)
    assert "WordPress preview: http://127.0.0.1:8888/" in result.stdout
    assert "raos-local-admin" in result.stdout
    credentials = (
        Path(environment["RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT"]) / "credentials.env"
    )
    assert stat.S_IMODE(credentials.stat().st_mode) == 0o600
    values = [line.split("=", 1)[1] for line in credentials.read_text().splitlines()]
    assert len(values) == 3
    assert len(set(values)) == 3
    assert all(len(value) == 64 for value in values)
    docker_log = Path(environment["RAOS_FAKE_DOCKER_LOG"]).read_text()
    assert "up --detach database wordpress gateway" in docker_log
    assert "core install" in docker_log
    assert "theme activate kurashinoshirube-child" in docker_log
    assert "RAOS_PREVIEW_SEED_MODE=initialize" in docker_log
    assert all(value not in docker_log for value in values)
    assert all(value not in result.stdout for value in values)


def test_up_propagates_compose_start_failure(fake_runtime: dict[str, str]) -> None:
    result = _run(
        "up",
        {**fake_runtime, "RAOS_FAKE_DOCKER_UP_FAIL": "1"},
    )
    assert result.returncode == 42
    docker_log = Path(fake_runtime["RAOS_FAKE_DOCKER_LOG"]).read_text()
    assert "up --detach database wordpress gateway" in docker_log
    assert "eval-file" not in docker_log


def test_down_preserves_named_volumes(fake_runtime: dict[str, str]) -> None:
    _run("up", fake_runtime, check=True)
    log_path = Path(fake_runtime["RAOS_FAKE_DOCKER_LOG"])
    log_path.write_text("", encoding="utf-8")
    result = _run("down", fake_runtime, check=True)
    assert "DATA_PRESERVED" in result.stdout
    docker_log = log_path.read_text()
    assert " down --remove-orphans" in docker_log
    assert "--volumes" not in docker_log


def test_sync_is_explicit_and_uses_sync_mode(fake_runtime: dict[str, str]) -> None:
    _run("up", fake_runtime, check=True)
    log_path = Path(fake_runtime["RAOS_FAKE_DOCKER_LOG"])
    log_path.write_text("", encoding="utf-8")
    _run("sync", fake_runtime, check=True)
    docker_log = log_path.read_text()
    assert "RAOS_PREVIEW_SEED_MODE=sync" in docker_log
    assert "RAOS_PREVIEW_SEED_MODE=initialize" not in docker_log


def test_reset_requires_confirmation_before_docker_access(tmp_path: Path) -> None:
    private_root = _private_root(tmp_path)
    shutil.rmtree(private_root, ignore_errors=True)
    result = _run(
        "reset",
        {
            "RAOS_WORDPRESS_PREVIEW_DOCKER_BIN": str(tmp_path / "missing-docker"),
            "RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT": str(private_root),
        },
    )
    assert result.returncode == 69
    assert result.stderr.strip() == "RAOS_WORDPRESS_PREVIEW_RESET_CONFIRMATION_REQUIRED"


def test_confirmed_reset_removes_only_compose_volumes_and_reseeds(
    fake_runtime: dict[str, str],
) -> None:
    _run("up", fake_runtime, check=True)
    log_path = Path(fake_runtime["RAOS_FAKE_DOCKER_LOG"])
    log_path.write_text("", encoding="utf-8")
    _run("reset", {**fake_runtime, "CONFIRM": "YES"}, check=True)
    docker_log = log_path.read_text()
    assert "down --volumes --remove-orphans" in docker_log
    assert "up --detach database wordpress gateway" in docker_log
    assert "RAOS_PREVIEW_SEED_MODE=initialize" in docker_log
