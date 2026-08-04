"""Maintained wrapper tests using an isolated fake Docker client."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
from typing import Any

import pytest

from conftest import REPOSITORY_ROOT


WRAPPER = REPOSITORY_ROOT / "scripts/postgres_service.sh"
EXPECTED_IMAGE = (
    "postgres:18.4-bookworm@sha256:"
    "1961f96e6029a02c3812d7cb329a3b03a3ac2bb067058dec17b0f5596aca9296"
)
EXPECTED_CONFIG_DIGEST = (
    "sha256:0a314d409a9633cff4f89dc18482262625c0ee78cb1aa2ff8e47bc6da0251e1b"
)


def _fake_docker(tmp_path: Path, mode: str = "ok") -> tuple[Path, Path]:
    executable = tmp_path / f"docker-{mode}"
    log = tmp_path / f"docker-{mode}.jsonl"
    program = f"""#!/usr/bin/python3
import json
import os
from pathlib import Path
import sys

mode = {mode!r}
log = Path({str(log)!r})
args = sys.argv[1:]
password_path = os.environ.get("RAOS_POSTGRES_PASSWORD_FILE", "")
metadata = None
if password_path and Path(password_path).is_file():
    item = Path(password_path).stat()
    metadata = {{"mode": oct(item.st_mode & 0o777), "size": item.st_size}}
with log.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({{
        "argv": args,
        "password_file": password_path,
        "password_metadata": metadata,
        "port": os.environ.get("RAOS_POSTGRES_PORT"),
        "docker_config": os.environ.get("DOCKER_CONFIG"),
        "home": os.environ.get("HOME"),
        "forbidden_environment_present": any(
            key in os.environ
            for key in ("COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "DOCKER_CONTEXT", "POSTGRES_PASSWORD")
        ),
    }}, sort_keys=True) + "\\n")

if args == ["--version"]:
    if mode == "not_docker":
        print("not docker")
    else:
        print("Docker version 28.3.0, build fake")
    raise SystemExit(0)

if len(args) < 3 or args[:2] != ["--host", "unix:///var/run/docker.sock"]:
    print("unexpected Docker transport", file=sys.stderr)
    raise SystemExit(91)
payload = args[2:]
if payload == ["compose", "version", "--short"]:
    print("2.20.0" if mode == "old_compose" else "2.40.0")
    raise SystemExit(0)
if payload and payload[0] == "inspect":
    template = payload[payload.index("--format") + 1]
    if ".Config.Image" in template:
        print("postgres:latest" if mode == "wrong_image" else {EXPECTED_IMAGE!r})
    elif ".Image" in template:
        print("sha256:" + "f" * 64 if mode == "wrong_config" else {EXPECTED_CONFIG_DIGEST!r})
    else:
        print("starting" if mode == "unhealthy" else "healthy")
    raise SystemExit(0)
if payload[:2] == ["image", "inspect"]:
    print("linux/arm64" if mode == "wrong_platform" else "linux/amd64")
    raise SystemExit(0)
if not payload or payload[0] != "compose":
    print("unexpected Docker operation", file=sys.stderr)
    raise SystemExit(92)
operation = next((item for item in payload if item in {{"config", "up", "ps", "exec", "down"}}), "")
if operation == "up" and mode == "fail_up":
    print("injected up failure", file=sys.stderr)
    raise SystemExit(42)
if operation == "down" and mode == "fail_down":
    print("injected down failure", file=sys.stderr)
    raise SystemExit(43)
if operation == "down" and mode == "noisy_down":
    print("compose cleanup progress")
    print("compose cleanup detail", file=sys.stderr)
if operation == "config" and "--services" in payload:
    print("postgres\\nrogue" if mode == "extra_service" else "postgres")
elif operation == "ps" and "--services" in payload:
    print("postgres\\nrogue" if mode == "extra_running" else "postgres")
elif operation == "ps" and "--quiet" in payload:
    print("a" * 64)
elif operation == "exec":
    print("180003" if mode == "wrong_version" else "180004")
raise SystemExit(0)
"""
    executable.write_text(program, encoding="utf-8")
    executable.chmod(0o755)
    return executable, log


def _secret(tmp_path: Path, content: bytes = b"private-test-password\n") -> Path:
    path = tmp_path / "postgres_password"
    path.write_bytes(content)
    path.chmod(0o600)
    return path


def _run(
    docker: Path,
    command: str,
    tmp_path: Path,
    *,
    password_path: Path | None = None,
    port: str = "55432",
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "TMPDIR": str(tmp_path),
        "RAOS_POSTGRES_PASSWORD_FILE": str(password_path or _secret(tmp_path)),
        "RAOS_POSTGRES_PORT": port,
        "COMPOSE_FILE": "/tmp/untrusted-compose.yml",
        "COMPOSE_PROJECT_NAME": "untrusted-project",
        "DOCKER_CONTEXT": "remote-context",
        "DOCKER_HOST": "tcp://example.invalid:2375",
        "POSTGRES_PASSWORD": "must-not-propagate",
    }
    if extra_env:
        environment.update(extra_env)
    return subprocess.run(
        [str(WRAPPER), "--docker", str(docker), command],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def _rows(log: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _compose_operation(row: dict[str, Any]) -> str | None:
    for item in row["argv"]:
        if item in {"config", "up", "ps", "exec", "down"}:
            return str(item)
    return None


def test_bash_syntax_is_valid() -> None:
    result = subprocess.run(
        ["/bin/bash", "-n", str(WRAPPER)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr


def test_config_uses_fixed_local_socket_file_and_project(tmp_path: Path) -> None:
    docker, log = _fake_docker(tmp_path)
    result = _run(docker, "config", tmp_path)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert json.loads(result.stdout) == {
        "formal_tst_008": "NOT_EXECUTED",
        "mode": "config",
        "status": "PASS",
        "story_id": "ST-0201",
    }
    rows = _rows(log)
    config = next(row for row in rows if _compose_operation(row) == "config")
    assert config["argv"][:3] == [
        "--host",
        "unix:///var/run/docker.sock",
        "compose",
    ]
    assert "--project-directory" in config["argv"]
    assert str(REPOSITORY_ROOT) in config["argv"]
    assert "--file" in config["argv"]
    assert str(REPOSITORY_ROOT / "docker-compose.yml") in config["argv"]
    assert "--project-name" in config["argv"]
    assert "raos-st0201-local" in config["argv"]
    assert all(row["forbidden_environment_present"] is False for row in rows)


def test_wrapper_rejects_compose_digest_drift_before_invoking_docker(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "drifted-repository"
    wrapper = repository / "scripts/postgres_service.sh"
    manifest = repository / "changes/st-0201/manifest.yaml"
    compose = repository / "docker-compose.yml"
    wrapper.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)
    shutil.copy2(WRAPPER, wrapper)
    shutil.copy2(REPOSITORY_ROOT / "changes/st-0201/manifest.yaml", manifest)
    compose.write_bytes(
        (REPOSITORY_ROOT / "docker-compose.yml").read_bytes() + b"# drift\n"
    )
    docker, log = _fake_docker(tmp_path)

    result = subprocess.run(
        [str(wrapper), "--docker", str(docker), "test"],
        cwd=repository,
        env={**os.environ, "TMPDIR": str(tmp_path)},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )

    assert result.returncode == 69
    assert "Compose file digest differs" in result.stderr
    assert "PASS" not in result.stdout
    assert not log.exists()


def test_up_waits_pulls_checks_health_image_and_exact_version(tmp_path: Path) -> None:
    docker, log = _fake_docker(tmp_path)
    result = _run(docker, "up", tmp_path)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert json.loads(result.stdout)["server_version_num"] == "180004"
    rows = _rows(log)
    up = next(row for row in rows if _compose_operation(row) == "up")
    assert up["argv"][-6:] == [
        "up",
        "--detach",
        "--wait",
        "--pull",
        "always",
        "postgres",
    ]
    assert any(row["argv"][2:3] == ["inspect"] for row in rows)
    exec_row = next(row for row in rows if _compose_operation(row) == "exec")
    assert "-T" in exec_row["argv"]
    assert "--no-TTY" not in exec_row["argv"]
    assert "SHOW server_version_num;" in exec_row["argv"]
    assert "psql" in exec_row["argv"]


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("unhealthy", "not healthy"),
        ("wrong_image", "image reference differs"),
        ("wrong_config", "image config digest differs"),
        ("wrong_platform", "image platform differs"),
        ("wrong_version", "differs from the exact 18.4 contract"),
        ("extra_running", "not the sole requested running service"),
    ],
)
def test_runtime_assertions_fail_closed(
    tmp_path: Path, mode: str, message: str
) -> None:
    docker, _ = _fake_docker(tmp_path, mode)
    result = _run(docker, "up", tmp_path)
    assert result.returncode != 0
    assert message in result.stderr
    assert "PASS" not in result.stdout


def test_compose_model_rejects_an_additional_service(tmp_path: Path) -> None:
    docker, _ = _fake_docker(tmp_path, "extra_service")
    result = _run(docker, "config", tmp_path)
    assert result.returncode != 0
    assert "must contain exactly the PostgreSQL service" in result.stderr
    assert "PASS" not in result.stdout


def test_down_preserves_local_named_volume(tmp_path: Path) -> None:
    docker, log = _fake_docker(tmp_path)
    result = _run(docker, "down", tmp_path)
    assert result.returncode == 0
    assert json.loads(result.stdout)["preserved_volume"] is True
    down = next(row for row in _rows(log) if _compose_operation(row) == "down")
    assert "--volumes" not in down["argv"]
    assert "--remove-orphans" in down["argv"]


def test_disposable_test_uses_private_secret_unique_project_and_cleans_volume(
    tmp_path: Path,
) -> None:
    docker, log = _fake_docker(tmp_path)
    result = _run(docker, "test", tmp_path)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert json.loads(result.stdout) == {
        "formal_tst_008": "NOT_EXECUTED",
        "mode": "test",
        "runtime": "LOCAL_PASS",
        "server_version_num": "180004",
        "status": "PASS",
        "story_id": "ST-0201",
    }
    rows = _rows(log)
    up = next(row for row in rows if _compose_operation(row) == "up")
    project_index = up["argv"].index("--project-name") + 1
    assert up["argv"][project_index].startswith("raos-st0201-test-")
    assert up["password_metadata"]["mode"] == "0o600"
    assert 1 <= up["password_metadata"]["size"] <= 1024
    assert up["port"] == ""
    down = [row for row in rows if _compose_operation(row) == "down"][-1]
    assert "--volumes" in down["argv"]
    assert "--remove-orphans" in down["argv"]
    assert not Path(up["password_file"]).exists()


def test_disposable_test_cleans_its_project_after_up_failure(tmp_path: Path) -> None:
    docker, log = _fake_docker(tmp_path, "fail_up")
    result = _run(docker, "test", tmp_path)
    assert result.returncode == 42
    rows = _rows(log)
    assert any(_compose_operation(row) == "up" for row in rows)
    down = [row for row in rows if _compose_operation(row) == "down"]
    assert len(down) == 1
    assert "--volumes" in down[0]["argv"]
    up = next(row for row in rows if _compose_operation(row) == "up")
    assert not Path(up["password_file"]).exists()


def test_disposable_test_does_not_claim_pass_when_volume_cleanup_fails(
    tmp_path: Path,
) -> None:
    docker, log = _fake_docker(tmp_path, "fail_down")
    result = _run(docker, "test", tmp_path)
    assert result.returncode == 1
    assert (
        "unable to remove the disposable PostgreSQL project and volume" in result.stderr
    )
    assert "PASS" not in result.stdout
    down = [row for row in _rows(log) if _compose_operation(row) == "down"]
    assert len(down) == 2
    assert all("--volumes" in row["argv"] for row in down)


def test_disposable_cleanup_progress_cannot_contaminate_json_stdout(
    tmp_path: Path,
) -> None:
    docker, _ = _fake_docker(tmp_path, "noisy_down")
    result = _run(docker, "test", tmp_path)
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "PASS"
    assert "cleanup progress" not in result.stdout
    assert "compose cleanup progress" in result.stderr
    assert "compose cleanup detail" in result.stderr


@pytest.mark.parametrize("mode", [0o000, 0o200, 0o400, 0o700, 0o606, 0o644, 0o660])
def test_local_secret_mode_other_than_exact_0600_is_rejected(
    tmp_path: Path, mode: int
) -> None:
    docker, _ = _fake_docker(tmp_path)
    password_file = _secret(tmp_path)
    password_file.chmod(mode)
    result = _run(docker, "config", tmp_path, password_path=password_file)
    assert result.returncode == 69
    assert "mode must be exactly 0600" in result.stderr


@pytest.mark.parametrize("content", [b"", b"x" * 1025])
def test_local_secret_size_is_bounded(tmp_path: Path, content: bytes) -> None:
    docker, _ = _fake_docker(tmp_path)
    password_file = _secret(tmp_path, content)
    result = _run(docker, "config", tmp_path, password_path=password_file)
    assert result.returncode == 69
    assert "between 1 and 1024 bytes" in result.stderr


def test_local_secret_symlink_is_rejected(tmp_path: Path) -> None:
    docker, _ = _fake_docker(tmp_path)
    target = _secret(tmp_path)
    link = tmp_path / "password-link"
    link.symlink_to(target)
    result = _run(docker, "config", tmp_path, password_path=link)
    assert result.returncode == 69
    assert "every ancestor must be non-symlinked" in result.stderr


@pytest.mark.parametrize("port", ["", "0", "1023", "65536", "5432x", "-1"])
def test_local_port_is_strictly_validated(tmp_path: Path, port: str) -> None:
    docker, _ = _fake_docker(tmp_path)
    result = _run(docker, "config", tmp_path, port=port)
    if port == "":
        # An unset/empty value intentionally selects the reviewed default 5432.
        assert result.returncode == 0
    else:
        assert result.returncode == 64
        assert "RAOS_POSTGRES_PORT" in result.stderr


def test_old_compose_and_non_docker_executable_are_rejected(tmp_path: Path) -> None:
    old, _ = _fake_docker(tmp_path, "old_compose")
    old_result = _run(old, "config", tmp_path)
    assert old_result.returncode == 69
    assert "Compose >=2.24.4" in old_result.stderr
    wrong, _ = _fake_docker(tmp_path, "not_docker")
    wrong_result = _run(wrong, "config", tmp_path)
    assert wrong_result.returncode == 69
    assert "did not identify itself" in wrong_result.stderr


def test_wrapper_rejects_relative_docker_path_and_unknown_command() -> None:
    relative = subprocess.run(
        [str(WRAPPER), "--docker", "docker", "config"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert relative.returncode == 64
    assert "usage:" in relative.stderr
    unknown = subprocess.run(
        [str(WRAPPER), "--docker", "/bin/true", "destroy"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert unknown.returncode == 64
    assert "usage:" in unknown.stderr


def test_real_docker_runtime_or_explicit_environment_skip(tmp_path: Path) -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip(
            "Docker is unavailable; ST-0201 runtime and formal TST-008 remain NOT_EXECUTED"
        )
    compose = subprocess.run(
        [docker, "compose", "version", "--short"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    if compose.returncode != 0:
        pytest.skip("Docker Compose is unavailable; runtime remains NOT_EXECUTED")
    daemon = subprocess.run(
        [
            docker,
            "--host",
            "unix:///var/run/docker.sock",
            "info",
            "--format",
            "{{.ID}}",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    if daemon.returncode != 0:
        pytest.skip("Local Docker daemon is unavailable; runtime remains NOT_EXECUTED")
    result = subprocess.run(
        [str(WRAPPER), "--docker", str(Path(docker).resolve()), "test"],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "TMPDIR": str(tmp_path)},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert json.loads(result.stdout)["server_version_num"] == "180004"


def test_wrapper_source_is_executable_and_not_group_writable() -> None:
    metadata = WRAPPER.stat()
    assert WRAPPER.is_file()
    assert not WRAPPER.is_symlink()
    assert stat.S_IMODE(metadata.st_mode) == 0o755
