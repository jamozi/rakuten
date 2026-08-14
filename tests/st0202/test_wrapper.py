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
EXPECTED_EPHEMERAL_OVERRIDE = b"""services:
  object-storage:
    ports: !override
      - target: 8333
        host_ip: 127.0.0.1
        protocol: tcp
    networks: !override
      - object_storage_internal
      - object_storage_disposable_publish
networks:
  object_storage_disposable_publish:
    driver: bridge
    internal: false
    driver_opts:
      com.docker.network.bridge.enable_ip_masquerade: "false"
"""
EXPECTED_EPHEMERAL_OVERRIDE_DIGEST = (
    "92e141f0c1b96ef47cf79855951d6cadaec509b9796cc03067186ff44dd27239"
)


def _fake_docker(tmp_path: Path, mode: str = "ok") -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    executable = tmp_path / f"docker-{mode}"
    log = tmp_path / f"docker-{mode}.jsonl"
    program = f"""#!/usr/bin/python3
import hashlib
import json
import os
from pathlib import Path
import signal
import sys

mode = {mode!r}
log = Path({str(log)!r})
sandbox = Path({str(tmp_path)!r})
args = sys.argv[1:]
config_path = os.environ.get("RAOS_OBJECT_STORAGE_S3_CONFIG_FILE", "")
requested_port = os.environ.get("RAOS_OBJECT_STORAGE_PORT", "")
published_port = requested_port or "49153"
if mode == "zero_assigned_port":
    published_port = "0"
elif mode == "privileged_assigned_port":
    published_port = "1023"
elif mode == "lower_port_boundary":
    published_port = "1024"
elif mode == "upper_port_boundary":
    published_port = "65535"
elif mode == "high_assigned_port":
    published_port = "65536"
elif mode == "overflow_assigned_port":
    published_port = "18446744073709559949"
elif mode == "non_decimal_port":
    published_port = "not-a-port"
metadata = None
if config_path and Path(config_path).is_file():
    item = Path(config_path).stat()
    metadata = {{"mode": oct(item.st_mode & 0o777), "size": item.st_size}}
override_candidates = sorted(
    sandbox.glob(
        "raos-st0202-test.*/object-storage-disposable-port.override.*.yml"
    )
)
override_metadata = None
override_path = ""
if len(override_candidates) == 1:
    override = override_candidates[0]
    item = override.lstat()
    content = override.read_bytes() if override.is_file() else b""
    override_path = str(override)
    override_metadata = {{
        "digest": hashlib.sha256(content).hexdigest(),
        "is_symlink": override.is_symlink(),
        "mode": oct(item.st_mode & 0o777),
        "owner": item.st_uid,
        "size": len(content),
    }}
compose_files = [
    args[index + 1]
    for index, item in enumerate(args[:-1])
    if item == "--file"
]
with log.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({{
        "argv": args,
        "config_file": config_path,
        "config_metadata": metadata,
        "port": os.environ.get("RAOS_OBJECT_STORAGE_PORT"),
        "docker_config": os.environ.get("DOCKER_CONFIG"),
        "home": os.environ.get("HOME"),
        "override_candidates": [str(item) for item in override_candidates],
        "override_metadata": override_metadata,
        "override_path": override_path,
        "compose_files": compose_files,
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
    if override_path and mode in {{
        "override_parent_mode",
        "override_parent_symlink",
        "override_mode",
        "override_symlink",
        "override_partial",
        "override_digest",
    }}:
        override = Path(override_path)
        if mode == "override_parent_mode":
            override.parent.chmod(0o777)
        elif mode == "override_parent_symlink":
            parent = override.parent
            target = parent.with_name(parent.name + ".real")
            parent.rename(target)
            parent.symlink_to(target, target_is_directory=True)
        elif mode == "override_mode":
            override.chmod(0o640)
        elif mode == "override_symlink":
            target = sandbox / "replacement-override.yml"
            target.write_bytes(override.read_bytes())
            override.unlink()
            override.symlink_to(target)
        elif mode == "override_partial":
            override.write_bytes(b"services:\\n")
        else:
            changed = override.read_bytes().replace(
                b"127.0.0.1", b"127.0.0.2", 1
            )
            override.write_bytes(changed)
    print("not docker" if mode == "not_docker" else "Docker version 28.3.0, build fake")
    raise SystemExit(0)
if len(args) < 3 or args[:2] != ["--host", "unix:///var/run/docker.sock"]:
    print("unexpected Docker transport", file=sys.stderr)
    raise SystemExit(91)
payload = args[2:]
if payload == ["compose", "version", "--short"]:
    if override_path and mode == "override_digest_after_compose_version":
        override = Path(override_path)
        changed = override.read_bytes().replace(b"127.0.0.1", b"127.0.0.2", 1)
        override.write_bytes(changed)
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
if operation == "up" and mode in {{"signal_hup", "signal_int", "signal_term"}}:
    selected = {{
        "signal_hup": signal.SIGHUP,
        "signal_int": signal.SIGINT,
        "signal_term": signal.SIGTERM,
    }}[mode]
    os.kill(os.getppid(), selected)
    raise SystemExit(0)
if operation == "config" and "--format" in payload:
    port = {{
        "target": 8333,
        "host_ip": "127.0.0.1",
        "protocol": "tcp",
    }}
    if not override_path:
        port["published"] = requested_port
    object_storage_networks = {{"object_storage_internal": None}}
    networks = {{
        "postgres_internal": {{
            "name": "project_postgres_internal",
            "driver": "bridge",
            "internal": True,
        }},
        "object_storage_internal": {{
            "name": "project_object_storage_internal",
            "driver": "bridge",
            "internal": True,
        }},
    }}
    if override_path:
        object_storage_networks["object_storage_disposable_publish"] = None
        networks["object_storage_disposable_publish"] = {{
            "name": "project_object_storage_disposable_publish",
            "driver": "bridge",
            "internal": False,
            "driver_opts": {{
                "com.docker.network.bridge.enable_ip_masquerade": "false",
            }},
        }}
    services = {{
        "postgres": {{}},
        "object-storage": {{
            "ports": [port],
            "networks": object_storage_networks,
        }},
    }}
    if mode == "extra_service":
        services["rogue"] = {{}}
    elif mode == "model_absent_port":
        services["object-storage"]["ports"] = []
    elif mode == "model_duplicate_port":
        services["object-storage"]["ports"] = [port, dict(port)]
    elif mode == "model_public_port":
        port["host_ip"] = "0.0.0.0"
    elif mode == "model_ipv6_port":
        port["host_ip"] = "::1"
    elif mode == "model_wrong_target":
        port["target"] = 8334
    elif mode == "model_published_present":
        port["published"] = "0"
    elif mode == "model_published_numeric_zero":
        port["published"] = 0
    elif mode == "model_published_range":
        port["published"] = "49152-65535"
    elif mode == "model_udp":
        port["protocol"] = "udp"
    elif mode == "model_service_publish_network_absent":
        del object_storage_networks["object_storage_disposable_publish"]
    elif mode == "model_service_internal_network_absent":
        del object_storage_networks["object_storage_internal"]
    elif mode == "model_service_network_options":
        object_storage_networks["object_storage_disposable_publish"] = {{
            "priority": 1,
        }}
    elif mode == "model_publish_network_absent":
        del networks["object_storage_disposable_publish"]
    elif mode == "model_publish_network_internal":
        networks["object_storage_disposable_publish"]["internal"] = True
    elif mode == "model_publish_network_wrong_driver":
        networks["object_storage_disposable_publish"]["driver"] = "host"
    elif mode == "model_publish_network_masquerade":
        networks["object_storage_disposable_publish"]["driver_opts"][
            "com.docker.network.bridge.enable_ip_masquerade"
        ] = "true"
    elif mode == "model_publish_network_extra_option":
        networks["object_storage_disposable_publish"]["driver_opts"][
            "com.docker.network.bridge.enable_icc"
        ] = "true"
    elif mode == "model_publish_network_external":
        networks["object_storage_disposable_publish"]["external"] = True
    elif mode == "model_publish_network_attachable":
        networks["object_storage_disposable_publish"]["attachable"] = True
    elif mode == "model_publish_network_ipv6":
        networks["object_storage_disposable_publish"]["enable_ipv6"] = True
    elif mode == "model_internal_network_weakened":
        networks["object_storage_internal"]["internal"] = False
    elif mode == "model_extra_network":
        networks["rogue"] = {{"driver": "bridge"}}
    if mode == "model_malformed_json":
        print("{{")
    else:
        print(json.dumps({{"networks": networks, "services": services}}, sort_keys=True))
elif operation == "config" and "--services" in payload:
    print("postgres\\nobject-storage\\nrogue" if mode == "extra_service" else "postgres\\nobject-storage")
elif operation == "ps" and "--services" in payload:
    print("object-storage\\npostgres" if mode == "extra_running" else "object-storage")
elif operation == "ps" and "--quiet" in payload:
    print("a" * 64)
elif operation == "port":
    if mode == "absent_port":
        print("")
    elif mode == "duplicate_port":
        print("127.0.0.1:49152\\n127.0.0.1:65535")
    elif mode == "public_port":
        print("0.0.0.0:" + published_port)
    elif mode == "ipv6_port":
        print("[::1]:" + published_port)
    elif mode == "malformed_port":
        print("127.0.0.1:" + published_port + "/tcp")
    else:
        print("127.0.0.1:" + published_port)
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
    if row["argv"][2:3] != ["compose"]:
        return None
    for item in row["argv"][3:]:
        if item in {"config", "up", "ps", "exec", "port", "down"}:
            return str(item)
    return None


def _is_model_gate(row: dict[str, Any]) -> bool:
    return _compose_operation(row) == "config" and row["argv"][-3:] == [
        "config",
        "--format",
        "json",
    ]


def _test_directories(tmp_path: Path) -> list[Path]:
    return sorted(tmp_path.glob("raos-st0202-test.*"))


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
    assert config["compose_files"] == [str(COMPOSE)]
    assert all(row["override_candidates"] == [] for row in rows)


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


def test_test_command_passes_base_then_ephemeral_files_only(
    tmp_path: Path,
) -> None:
    wrapper, fixture_log = _isolated_repository(tmp_path)
    docker, docker_log = _fake_docker(tmp_path)
    result = _run(wrapper, docker, "test", tmp_path)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert json.loads(result.stdout)["runtime"] == "LOCAL_CANDIDATE_PASS"
    rows = _rows(docker_log)
    expected_compose = wrapper.parents[1] / "docker-compose.yml"
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
    assert all(row["port"] is None for row in rows)
    project_compose_rows = [row for row in rows if _compose_operation(row) is not None]
    assert project_compose_rows
    override_paths = {row["compose_files"][1] for row in project_compose_rows}
    assert len(override_paths) == 1
    for row in project_compose_rows:
        assert row["compose_files"][0] == str(expected_compose)
        assert len(row["compose_files"]) == 2
    first = rows[0]
    assert first["argv"] == ["--version"]
    assert first["override_metadata"] == {
        "digest": EXPECTED_EPHEMERAL_OVERRIDE_DIGEST,
        "is_symlink": False,
        "mode": "0o600",
        "owner": os.geteuid(),
        "size": len(EXPECTED_EPHEMERAL_OVERRIDE),
    }
    assert _test_directories(tmp_path) == []


@pytest.mark.parametrize(
    "mode",
    [
        "absent_port",
        "duplicate_port",
        "public_port",
        "ipv6_port",
        "zero_assigned_port",
        "privileged_assigned_port",
        "high_assigned_port",
        "overflow_assigned_port",
        "non_decimal_port",
        "malformed_port",
    ],
)
def test_observed_mapping_rejects_invalid_cardinality_host_and_range(
    tmp_path: Path, mode: str
) -> None:
    wrapper, fixture_log = _isolated_repository(tmp_path)
    docker, log = _fake_docker(tmp_path, mode)
    result = _run(wrapper, docker, "test", tmp_path)
    assert result.returncode != 0
    assert "not published on one bounded loopback port" in result.stderr
    rows = _rows(log)
    assert all(row["port"] is None for row in rows)
    down = [row for row in rows if _compose_operation(row) == "down"]
    assert len(down) == 1
    assert "--volumes" in down[0]["argv"]
    assert "acceptance" not in [row["argv"][0] for row in _rows(fixture_log)]
    assert _test_directories(tmp_path) == []


@pytest.mark.parametrize("mode", ["lower_port_boundary", "upper_port_boundary"])
def test_runtime_selected_port_accepts_exact_contract_boundaries(
    tmp_path: Path, mode: str
) -> None:
    wrapper, _fixture_log = _isolated_repository(tmp_path)
    docker, log = _fake_docker(tmp_path, mode)
    result = _run(wrapper, docker, "test", tmp_path)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    rows = _rows(log)
    assert all(row["port"] is None for row in rows)
    down = [row for row in rows if _compose_operation(row) == "down"]
    assert len(down) == 1
    assert "--volumes" in down[0]["argv"]
    assert _test_directories(tmp_path) == []


def test_ephemeral_template_is_exact_382_bytes_and_digest_bound(
    tmp_path: Path,
) -> None:
    assert len(EXPECTED_EPHEMERAL_OVERRIDE) == 382
    assert hashlib.sha256(EXPECTED_EPHEMERAL_OVERRIDE).hexdigest() == (
        EXPECTED_EPHEMERAL_OVERRIDE_DIGEST
    )
    wrapper, _fixture_log = _isolated_repository(tmp_path)
    docker, log = _fake_docker(tmp_path)
    result = _run(wrapper, docker, "test", tmp_path)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert _rows(log)[0]["override_metadata"]["digest"] == (
        EXPECTED_EPHEMERAL_OVERRIDE_DIGEST
    )


def test_test_command_creates_override_before_first_docker_call(
    tmp_path: Path,
) -> None:
    wrapper, _fixture_log = _isolated_repository(tmp_path)
    docker, log = _fake_docker(tmp_path)
    result = _run(wrapper, docker, "test", tmp_path)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    first = _rows(log)[0]
    assert first["argv"] == ["--version"]
    assert first["override_metadata"]["digest"] == EXPECTED_EPHEMERAL_OVERRIDE_DIGEST


def _assert_ephemeral_override_rejected(
    tmp_path: Path, mode: str, message: str, *, expected_docker_rows: int = 1
) -> None:
    wrapper, _fixture_log = _isolated_repository(tmp_path)
    docker, log = _fake_docker(tmp_path, mode)
    result = _run(wrapper, docker, "test", tmp_path)
    assert result.returncode == 69
    assert message in result.stderr
    assert "PASS" not in result.stdout
    assert len(_rows(log)) == expected_docker_rows
    assert _test_directories(tmp_path) == []


def test_ephemeral_override_rejects_non_0600_mode(tmp_path: Path) -> None:
    _assert_ephemeral_override_rejected(
        tmp_path, "override_mode", "mode must be exactly 0600"
    )


def test_ephemeral_override_rejects_parent_mode_drift(tmp_path: Path) -> None:
    _assert_ephemeral_override_rejected(
        tmp_path,
        "override_parent_mode",
        "test directory mode must be exactly 0700",
    )


def test_ephemeral_override_rejects_parent_symlink_substitution(
    tmp_path: Path,
) -> None:
    wrapper, _fixture_log = _isolated_repository(tmp_path)
    docker, log = _fake_docker(tmp_path, "override_parent_symlink")
    result = _run(wrapper, docker, "test", tmp_path)
    leftovers = _test_directories(tmp_path)
    try:
        assert result.returncode == 69
        assert "regular non-symlink directory" in result.stderr
        assert "PASS" not in result.stdout
        assert len(_rows(log)) == 1
        assert len(leftovers) == 2
        assert sum(path.is_symlink() for path in leftovers) == 1
    finally:
        for path in leftovers:
            if path.is_symlink():
                path.unlink()
            elif path.exists():
                shutil.rmtree(path)


def test_ephemeral_override_rejects_symlink_substitution(tmp_path: Path) -> None:
    _assert_ephemeral_override_rejected(
        tmp_path, "override_symlink", "regular non-symlink file"
    )


def test_ephemeral_override_rejects_partial_or_truncated_content(
    tmp_path: Path,
) -> None:
    _assert_ephemeral_override_rejected(tmp_path, "override_partial", "size differs")


def test_ephemeral_override_rejects_same_size_digest_drift(tmp_path: Path) -> None:
    _assert_ephemeral_override_rejected(tmp_path, "override_digest", "digest differs")


def test_ephemeral_override_revalidates_before_every_compose_use(
    tmp_path: Path,
) -> None:
    _assert_ephemeral_override_rejected(
        tmp_path,
        "override_digest_after_compose_version",
        "digest differs",
        expected_docker_rows=2,
    )


@pytest.mark.parametrize(
    "mode",
    [
        "model_absent_port",
        "model_duplicate_port",
        "model_public_port",
        "model_ipv6_port",
        "model_wrong_target",
        "model_published_present",
        "model_published_numeric_zero",
        "model_published_range",
        "model_udp",
        "model_service_publish_network_absent",
        "model_service_internal_network_absent",
        "model_service_network_options",
        "model_publish_network_absent",
        "model_publish_network_internal",
        "model_publish_network_wrong_driver",
        "model_publish_network_masquerade",
        "model_publish_network_extra_option",
        "model_publish_network_external",
        "model_publish_network_attachable",
        "model_publish_network_ipv6",
        "model_internal_network_weakened",
        "model_extra_network",
        "model_malformed_json",
    ],
)
def test_normalized_compose_model_rejects_hostile_port_or_network_before_up(
    tmp_path: Path, mode: str
) -> None:
    wrapper, fixture_log = _isolated_repository(tmp_path)
    docker, log = _fake_docker(tmp_path, mode)
    result = _run(wrapper, docker, "test", tmp_path)
    assert result.returncode == 69
    assert "normalized Compose model differs" in result.stderr
    rows = _rows(log)
    assert any(_is_model_gate(row) for row in rows)
    assert not any(_compose_operation(row) == "up" for row in rows)
    assert "acceptance" not in [row["argv"][0] for row in _rows(fixture_log)]
    assert _test_directories(tmp_path) == []


def test_normalized_compose_model_gate_precedes_every_project_compose_use(
    tmp_path: Path,
) -> None:
    wrapper, _fixture_log = _isolated_repository(tmp_path)
    docker, log = _fake_docker(tmp_path)
    result = _run(wrapper, docker, "test", tmp_path)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    rows = _rows(log)
    project_uses = [
        index
        for index, row in enumerate(rows)
        if _compose_operation(row) is not None and not _is_model_gate(row)
    ]
    assert project_uses
    assert all(index > 0 and _is_model_gate(rows[index - 1]) for index in project_uses)


def test_ephemeral_override_rejects_owner_mismatch_by_exact_source_guard() -> None:
    source = WRAPPER.read_text(encoding="utf-8")
    assert "owner=$(stat --format='%u' -- \"$ephemeral_override_file\")" in source
    assert '[[ $owner != "$(id -u)" ]]' in source


def test_ephemeral_validation_order_precedes_validate_docker_client() -> None:
    source = WRAPPER.read_text(encoding="utf-8")
    assert (
        "/usr/bin/mktemp \\\n"
        '      "$test_directory/object-storage-disposable-port.override.XXXXXXXX.yml"'
    ) in source
    assert '/usr/bin/mktemp -d "${TMPDIR:-/tmp}/raos-st0202-test.XXXXXXXX"' in source
    assert source.index("validate_ephemeral_override\nfi\nvalidate_docker_client") < (
        source.index("validate_docker_client\n\nif [[ $command == test ]]")
    )


@pytest.mark.parametrize("command", ["config", "up", "check", "down"])
@pytest.mark.parametrize("port", ["1024", "49151", "65535"])
def test_persistent_commands_accept_fixed_range_without_ephemeral_override(
    tmp_path: Path, command: str, port: str
) -> None:
    wrapper, _fixture_log = _isolated_repository(tmp_path)
    docker, log = _fake_docker(tmp_path)
    result = _run(wrapper, docker, command, tmp_path, port=port)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    rows = _rows(log)
    expected_compose = wrapper.parents[1] / "docker-compose.yml"
    assert all(row["override_candidates"] == [] for row in rows)
    assert all(
        row["port"] == port for row in rows if _compose_operation(row) is not None
    )
    for row in rows:
        if _compose_operation(row) is not None:
            assert row["compose_files"] == [str(expected_compose)]
    assert _test_directories(tmp_path) == []


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
    assert "normalized Compose model differs" in result.stderr


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
    assert _test_directories(tmp_path) == []


@pytest.mark.parametrize(
    ("mode", "expected_status"),
    [
        ("ok", 0),
        ("fail_up", 42),
        ("signal_hup", 129),
        ("signal_int", 130),
        ("signal_term", 143),
    ],
)
def test_ephemeral_override_cleanup_runs_after_success_failure_and_signal(
    tmp_path: Path, mode: str, expected_status: int
) -> None:
    wrapper, _fixture_log = _isolated_repository(tmp_path)
    docker, _log = _fake_docker(tmp_path, mode)
    result = _run(wrapper, docker, "test", tmp_path)
    assert result.returncode == expected_status
    assert _test_directories(tmp_path) == []
