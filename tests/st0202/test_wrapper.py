"""Maintained orchestration tests for the ST-0202 service wrapper."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

import pytest

from scripts import object_storage_fixture as fixture

from conftest import REPOSITORY_ROOT


WRAPPER = REPOSITORY_ROOT / "scripts/object_storage_service.sh"
COMPOSE = REPOSITORY_ROOT / "docker-compose.yml"
EXPECTED_IMAGE = (
    "docker.io/chrislusf/seaweedfs:4.29@sha256:"
    "d47c7ee99fcb951351d7194915f4e3a5ea604a8e8871183d713907dec4fb9bf5"
)
EXPECTED_CONFIG_DIGEST = (
    "sha256:10b004ca7cc8ee13615dbe670e1be047270ab30a742a5944e82330017d64d8fd"
)


def _fake_docker(tmp_path: Path, mode: str = "ok") -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
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
config_path = os.environ.get("RAOS_OBJECT_STORAGE_S3_CONFIG_FILE", "")
requested_port = os.environ.get("RAOS_OBJECT_STORAGE_PORT", "")
published_port = (
    "49153" if requested_port == "49152-65535" else (requested_port or "49153")
)
metadata = None
if config_path and Path(config_path).is_file():
    item = Path(config_path).stat()
    metadata = {{"mode": oct(item.st_mode & 0o777), "size": item.st_size}}
with log.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({{
        "argv": args,
        "config_file": config_path,
        "config_metadata": metadata,
        "port": os.environ.get("RAOS_OBJECT_STORAGE_PORT"),
        "docker_config": os.environ.get("DOCKER_CONFIG"),
        "home": os.environ.get("HOME"),
        "raw_credentials_present": any(
            key in os.environ
            for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
        ),
        "forbidden_environment_present": any(
            key in os.environ
            for key in ("COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "DOCKER_CONTEXT")
        ),
    }}, sort_keys=True) + "\\n")

if args == ["--version"]:
    print("not docker" if mode == "not_docker" else "Docker version 28.3.0, build fake")
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
        print("seaweedfs:latest" if mode == "wrong_image" else {EXPECTED_IMAGE!r})
    elif ".Image" in template:
        print("sha256:" + "f" * 64 if mode == "wrong_config" else {EXPECTED_CONFIG_DIGEST!r})
    else:
        print("starting" if mode == "unhealthy" else "healthy")
    raise SystemExit(0)
if payload[:2] == ["image", "inspect"]:
    template = payload[payload.index("--format") + 1]
    if ".Os" in template:
        print("linux/arm64" if mode == "wrong_platform" else "linux/amd64")
    elif "revision" in template:
        print("bad-revision" if mode == "wrong_labels" else "1355c7a102194d6c461baf090eff50367b575afb")
    elif "version" in template:
        print("4.28" if mode == "wrong_labels" else "4.29")
    elif "licenses" in template:
        print("unknown" if mode == "wrong_labels" else "Apache-2.0")
    elif "source" in template:
        print("https://example.invalid" if mode == "wrong_labels" else "https://github.com/seaweedfs/seaweedfs")
    raise SystemExit(0)
if payload and payload[0] == "port":
    if mode == "extra_port":
        print(f"8333/tcp -> 127.0.0.1:{{published_port}}\\n9333/tcp -> 0.0.0.0:9333")
    else:
        print(f"8333/tcp -> 127.0.0.1:{{published_port}}")
    raise SystemExit(0)
if not payload or payload[0] != "compose":
    print("unexpected Docker operation", file=sys.stderr)
    raise SystemExit(92)
operation = next(
    (item for item in payload if item in {{"config", "up", "ps", "exec", "port", "down"}}),
    "",
)
if operation == "up" and mode == "fail_up":
    print("injected up failure", file=sys.stderr)
    raise SystemExit(42)
if operation == "down" and mode == "fail_down":
    print("injected down failure", file=sys.stderr)
    raise SystemExit(43)
if operation == "config" and "--services" in payload:
    print("postgres\\nobject-storage\\nrogue" if mode == "extra_service" else "postgres\\nobject-storage")
elif operation == "ps" and "--services" in payload:
    print("object-storage\\npostgres" if mode == "extra_running" else "object-storage")
elif operation == "ps" and "--quiet" in payload:
    print("a" * 64)
elif operation == "port":
    if mode == "low_assigned_port":
        published_port = "1023"
    elif mode == "below_disposable_range":
        published_port = "49151"
    elif mode == "high_assigned_port":
        published_port = "65536"
    elif mode == "overflow_assigned_port":
        published_port = "18446744073709559949"
    print(
        "0.0.0.0:" + published_port
        if mode == "public_port"
        else "127.0.0.1:" + published_port
    )
elif operation == "exec" and "/usr/bin/weed" in payload:
    print("version 8000GB 4.28 bad linux amd64" if mode == "wrong_version" else "version 8000GB 4.29 1355c7a linux amd64")
elif operation == "exec" and "/bin/sh" in payload:
    print("0" if mode == "root_process" else "1000")
raise SystemExit(0)
"""
    executable.write_text(program, encoding="utf-8")
    executable.chmod(0o755)
    return executable, log


def _identity(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "object-storage-s3-config.json"
    fixture.create_identity_config(path)
    return path


def _run(
    wrapper: Path,
    docker: Path,
    command: str,
    tmp_path: Path,
    *,
    config_path: Path | None = None,
    port: str = "58333",
) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "TMPDIR": str(tmp_path),
        "RAOS_OBJECT_STORAGE_S3_CONFIG_FILE": str(config_path or _identity(tmp_path)),
        "RAOS_OBJECT_STORAGE_PORT": port,
        "AWS_ACCESS_KEY_ID": "must-not-propagate",
        "AWS_SECRET_ACCESS_KEY": "must-not-propagate",
        "COMPOSE_FILE": "/tmp/untrusted-compose.yml",
        "COMPOSE_PROJECT_NAME": "untrusted-project",
        "DOCKER_CONTEXT": "remote-context",
        "DOCKER_HOST": "tcp://example.invalid:2375",
    }
    return subprocess.run(
        [str(wrapper), "--docker", str(docker), command],
        cwd=wrapper.parents[1],
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
        if item in {"config", "up", "ps", "exec", "port", "down"}:
            return str(item)
    return None


def _isolated_repository(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "isolated-repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    wrapper = scripts / "object_storage_service.sh"
    shutil.copy2(WRAPPER, wrapper)
    compose = repository / "docker-compose.yml"
    shutil.copy2(COMPOSE, compose)
    fixture_log = tmp_path / "fixture-calls.jsonl"
    client = scripts / "object_storage_fixture.py"
    client.write_text(
        f"""#!/usr/bin/python3
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
command = args[0]
with Path({str(fixture_log)!r}).open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({{"argv": args}}, sort_keys=True) + "\\n")
if command == "create-config":
    output = Path(args[args.index("--output") + 1])
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(descriptor, b'{{"identities":[{{"name":"stub"}}]}}\\n')
    os.close(descriptor)
print(json.dumps({{"mode": command, "status": "PASS"}}, sort_keys=True))
""",
        encoding="utf-8",
    )
    client.chmod(0o755)
    wrapper_text = wrapper.read_text(encoding="utf-8")
    wrapper_text = re.sub(
        r"readonly expected_compose_sha256='[^']+'",
        f"readonly expected_compose_sha256='{hashlib.sha256(compose.read_bytes()).hexdigest()}'",
        wrapper_text,
        count=1,
    )
    wrapper_text = re.sub(
        r"readonly expected_fixture_sha256='[^']+'",
        f"readonly expected_fixture_sha256='{hashlib.sha256(client.read_bytes()).hexdigest()}'",
        wrapper_text,
        count=1,
    )
    wrapper.write_text(wrapper_text, encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper, fixture_log


def test_bash_syntax_is_valid() -> None:
    result = subprocess.run(
        ["/bin/bash", "-n", str(WRAPPER)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr


def test_config_uses_fixed_local_transport_and_passes_only_secret_path(
    tmp_path: Path,
) -> None:
    docker, log = _fake_docker(tmp_path)
    result = _run(WRAPPER, docker, "config", tmp_path)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert json.loads(result.stdout) == {
        "formal_tst_014": "NOT_EXECUTED",
        "mode": "config",
        "status": "PASS",
        "story_id": "ST-0202",
    }
    rows = _rows(log)
    assert all(row["raw_credentials_present"] is False for row in rows)
    assert all(row["forbidden_environment_present"] is False for row in rows)
    config = next(row for row in rows if _compose_operation(row) == "config")
    assert config["argv"][:3] == ["--host", "unix:///var/run/docker.sock", "compose"]
    assert "--project-name" in config["argv"]
    assert "raos-st0202-local" in config["argv"]
    assert config["config_metadata"]["mode"] == "0o600"
    assert config["port"] == "58333"
    assert all(row["port"] != "49152-65535" for row in rows)


def test_wrapper_rejects_compose_or_fixture_digest_drift_before_docker(
    tmp_path: Path,
) -> None:
    wrapper, _fixture_log = _isolated_repository(tmp_path)
    docker, log = _fake_docker(tmp_path)
    compose = wrapper.parents[1] / "docker-compose.yml"
    compose.write_bytes(compose.read_bytes() + b"# drift\n")
    result = _run(wrapper, docker, "test", tmp_path)
    assert result.returncode == 69
    assert "Compose file digest differs" in result.stderr
    assert not log.exists()

    wrapper, _fixture_log = _isolated_repository(tmp_path / "client-case")
    docker, log = _fake_docker(tmp_path / "client-case")
    client = wrapper.parent / "object_storage_fixture.py"
    client.write_bytes(client.read_bytes() + b"# drift\n")
    result = _run(wrapper, docker, "test", tmp_path / "client-case")
    assert result.returncode == 69
    assert "fixture client digest differs" in result.stderr
    assert not log.exists()


def test_disposable_test_targets_only_object_service_and_removes_volume(
    tmp_path: Path,
) -> None:
    wrapper, fixture_log = _isolated_repository(tmp_path)
    docker, docker_log = _fake_docker(tmp_path)
    result = _run(wrapper, docker, "test", tmp_path)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert json.loads(result.stdout)["runtime"] == "LOCAL_CANDIDATE_PASS"
    rows = _rows(docker_log)
    up = next(row for row in rows if _compose_operation(row) == "up")
    assert up["argv"][-6:] == [
        "up",
        "--detach",
        "--wait",
        "--pull",
        "always",
        "object-storage",
    ]
    down = [row for row in rows if _compose_operation(row) == "down"]
    assert len(down) == 1
    assert "--volumes" in down[0]["argv"]
    calls = _rows(fixture_log)
    assert [call["argv"][0] for call in calls] == [
        "create-config",
        "validate-config",
        "acceptance",
    ]
    assert all(row["raw_credentials_present"] is False for row in rows)
    assert {row["port"] for row in rows if row["port"] is not None} == {"49152-65535"}
    compose_port = next(row for row in rows if _compose_operation(row) == "port")
    assert compose_port["port"] == "49152-65535"
    container_port = next(row for row in rows if row["argv"][2:3] == ["port"])
    assert container_port["port"] == "49152-65535"


@pytest.mark.parametrize(
    "mode", ["low_assigned_port", "high_assigned_port", "overflow_assigned_port"]
)
def test_disposable_random_port_must_resolve_to_bounded_loopback_port(
    tmp_path: Path, mode: str
) -> None:
    wrapper, _fixture_log = _isolated_repository(tmp_path)
    docker, log = _fake_docker(tmp_path, mode)
    result = _run(wrapper, docker, "test", tmp_path)
    assert result.returncode != 0
    assert "not published on one bounded loopback port" in result.stderr
    rows = _rows(log)
    assert {row["port"] for row in rows if row["port"] is not None} == {"49152-65535"}
    down = [row for row in rows if _compose_operation(row) == "down"]
    assert len(down) == 1
    assert "--volumes" in down[0]["argv"]


def test_disposable_random_port_must_remain_in_reviewed_range(
    tmp_path: Path,
) -> None:
    wrapper, _fixture_log = _isolated_repository(tmp_path)
    docker, log = _fake_docker(tmp_path, "below_disposable_range")
    result = _run(wrapper, docker, "test", tmp_path)
    assert result.returncode != 0
    assert "escaped the reviewed random host-port range" in result.stderr
    rows = _rows(log)
    assert {row["port"] for row in rows if row["port"] is not None} == {"49152-65535"}
    down = [row for row in rows if _compose_operation(row) == "down"]
    assert len(down) == 1
    assert "--volumes" in down[0]["argv"]


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("unhealthy", "not healthy"),
        ("wrong_image", "image reference differs"),
        ("wrong_config", "image config digest differs"),
        ("wrong_platform", "platform differs"),
        ("wrong_labels", "image labels differ"),
        ("public_port", "not published on one bounded loopback port"),
        ("extra_port", "publishes an unexpected host port"),
        ("root_process", "did not drop to UID 1000"),
        ("wrong_version", "runtime version differs"),
        ("extra_running", "not the sole requested running service"),
    ],
)
def test_runtime_identity_failures_are_rejected(
    tmp_path: Path, mode: str, message: str
) -> None:
    wrapper, _fixture_log = _isolated_repository(tmp_path)
    docker, _log = _fake_docker(tmp_path, mode)
    result = _run(wrapper, docker, "up", tmp_path)
    assert result.returncode != 0
    assert message in result.stderr
    assert "PASS" not in result.stdout


def test_unreviewed_compose_service_is_rejected(tmp_path: Path) -> None:
    wrapper, _fixture_log = _isolated_repository(tmp_path)
    docker, _log = _fake_docker(tmp_path, "extra_service")
    result = _run(wrapper, docker, "config", tmp_path)
    assert result.returncode != 0
    assert "unreviewed service: rogue" in result.stderr


def test_invalid_port_mode_and_symlink_are_rejected(tmp_path: Path) -> None:
    docker, log = _fake_docker(tmp_path)
    result = _run(WRAPPER, docker, "config", tmp_path, port="8333x")
    assert result.returncode == 64
    assert "decimal integer" in result.stderr

    result = _run(WRAPPER, docker, "config", tmp_path / "zero-port", port="0")
    assert result.returncode == 64
    assert "decimal integer from 1024 through 65535" in result.stderr
    assert all(row["port"] != "0" for row in _rows(log))

    result = _run(
        WRAPPER,
        docker,
        "config",
        tmp_path / "range-port",
        port="49152-65535",
    )
    assert result.returncode == 64
    assert "decimal integer from 1024 through 65535" in result.stderr
    assert all(row["port"] != "49152-65535" for row in _rows(log))

    weak = _identity(tmp_path / "weak")
    weak.chmod(0o640)
    result = _run(WRAPPER, docker, "config", tmp_path, config_path=weak)
    assert result.returncode == 69
    assert "mode must be exactly 0600" in result.stderr

    target = _identity(tmp_path / "target")
    link = tmp_path / "identity-link.json"
    link.symlink_to(target)
    result = _run(WRAPPER, docker, "config", tmp_path, config_path=link)
    assert result.returncode == 69
    assert "non-symlinked" in result.stderr


@pytest.mark.parametrize("port", ["65536", "18446744073709559949"])
def test_out_of_range_fixed_port_is_rejected_before_compose(
    tmp_path: Path, port: str
) -> None:
    docker, log = _fake_docker(tmp_path)
    result = _run(WRAPPER, docker, "config", tmp_path, port=port)
    assert result.returncode == 64
    assert "decimal integer from 1024 through 65535" in result.stderr
    assert all(row["port"] != port for row in _rows(log))


def test_failed_disposable_start_still_attempts_volume_cleanup(tmp_path: Path) -> None:
    wrapper, _fixture_log = _isolated_repository(tmp_path)
    docker, log = _fake_docker(tmp_path, "fail_up")
    result = _run(wrapper, docker, "test", tmp_path)
    assert result.returncode == 42
    rows = _rows(log)
    down = [row for row in rows if _compose_operation(row) == "down"]
    assert len(down) == 1
    assert "--volumes" in down[0]["argv"]
