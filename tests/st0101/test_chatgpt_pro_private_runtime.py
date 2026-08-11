"""Deterministic private-runtime evidence for approved Story ST-0101."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import stat
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import chatgpt_pro_orchestrator as orchestrator


def private_root(tmp_path: Path) -> Path:
    root = tmp_path / ".secrets"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    return root


def runtime_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source = tmp_path / "runtime-source"
    source.mkdir()
    package_bytes = json.dumps(
        {
            "private": True,
            "dependencies": {
                orchestrator.MCP_PACKAGE_NAME: orchestrator.MCP_PACKAGE_VERSION
            },
        }
    ).encode()
    lock_bytes = json.dumps(
        {
            "name": "chatgpt_pro_mcp_runtime",
            "lockfileVersion": 3,
            "requires": True,
            "packages": {
                "": {
                    "dependencies": {
                        orchestrator.MCP_PACKAGE_NAME: (
                            orchestrator.MCP_PACKAGE_VERSION
                        )
                    }
                },
                "node_modules/@playwright/mcp": {
                    "version": orchestrator.MCP_PACKAGE_VERSION,
                    "integrity": "sha512-deterministic-fixture",
                },
            },
        }
    ).encode()
    (source / "package.json").write_bytes(package_bytes)
    (source / "package-lock.json").write_bytes(lock_bytes)
    expected_root = tmp_path / "expected-runtime"
    expected_root.mkdir()
    (expected_root / "package.json").write_bytes(package_bytes)
    (expected_root / "package-lock.json").write_bytes(lock_bytes)
    (expected_root / orchestrator.RUNTIME_USER_NPMRC_NAME).write_bytes(b"")
    (expected_root / orchestrator.RUNTIME_GLOBAL_NPMRC_NAME).write_bytes(b"")
    fake_npm_install(
        node=tmp_path / "node",
        npm_cli=tmp_path / "npm-cli.js",
        stage=expected_root,
        cache=tmp_path / orchestrator.RUNTIME_CACHE_NAME,
    )
    orchestrator._privatize_runtime_tree(expected_root)
    (source / orchestrator.RUNTIME_EXPECTED_INVENTORY_NAME).write_text(
        json.dumps(
            {
                "schema": orchestrator.RUNTIME_EXPECTED_INVENTORY_SCHEMA,
                "story_id": orchestrator.STORY_ID,
                "package": orchestrator.MCP_PACKAGE_NAME,
                "version": orchestrator.MCP_PACKAGE_VERSION,
                "node_version": orchestrator.NODE_VERSION,
                "npm_version": orchestrator.NPM_VERSION,
                "package_lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
                "inventory": orchestrator._runtime_inventory(expected_root),
            }
        ),
        encoding="utf-8",
    )
    for path in source.iterdir():
        path.chmod(0o644)
    monkeypatch.setattr(orchestrator, "DEFAULT_RUNTIME_SOURCE", source)
    monkeypatch.setattr(
        orchestrator, "_require_runtime_toolchain", lambda *_args, **_kwargs: None
    )
    return source


def fake_npm_install(*, node: Path, npm_cli: Path, stage: Path, cache: Path) -> None:
    del node, npm_cli
    assert cache == stage.parent / orchestrator.RUNTIME_CACHE_NAME
    package_root = stage / "node_modules" / "@playwright" / "mcp"
    package_root.mkdir(parents=True)
    (package_root / "package.json").write_text(
        json.dumps(
            {
                "name": orchestrator.MCP_PACKAGE_NAME,
                "version": orchestrator.MCP_PACKAGE_VERSION,
            }
        ),
        encoding="utf-8",
    )
    (package_root / "cli.js").write_text("// deterministic CLI\n", encoding="utf-8")
    (stage / "node_modules" / "sibling.js").write_text(
        "// global sort evidence\n", encoding="utf-8"
    )


def install_fixture_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, dict[str, Any]]:
    root = private_root(tmp_path)
    source = runtime_source(tmp_path, monkeypatch)
    monkeypatch.setattr(orchestrator, "_run_npm_runtime_install", fake_npm_install)
    result = orchestrator.runtime_install(
        private_root=root,
        node=tmp_path / "node",
        npm_cli=tmp_path / "npm-cli.js",
        source=source,
    )
    return root, source, result


def test_private_runtime_install_is_exact_private_and_shared_cache_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared_cache = tmp_path / "shared-home" / ".npm" / "_npx" / "mutable"
    shared_cache.mkdir(parents=True)
    (shared_cache / "package.json").write_text(
        '{"name":"@playwright/mcp","version":"0.0.79"}', encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(tmp_path / "shared-home"))

    root, source, result = install_fixture_runtime(tmp_path, monkeypatch)
    runtime = root / orchestrator.RUNTIME_ROOT_NAME

    assert result["status"] == "PRO_RUNTIME_INSTALLED"
    assert result["version"] == "0.0.78"
    assert result["next_action"] == "pro-doctor"
    assert (
        shared_cache.joinpath("package.json")
        .read_text(encoding="utf-8")
        .endswith('"0.0.79"}')
    )
    assert all(".npm/_npx" not in str(path) for path in runtime.rglob("*"))
    verified = orchestrator._verify_runtime_at(
        runtime,
        source=source,
        node=tmp_path / "node",
    )
    assert verified["version"] == "0.0.78"
    for path in runtime.rglob("*"):
        mode = stat.S_IMODE(path.lstat().st_mode)
        assert mode == (0o700 if path.is_dir() else 0o600)


def test_interrupted_stage_is_removed_before_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = private_root(tmp_path)
    stage = root / orchestrator.RUNTIME_STAGE_NAME
    stage.mkdir(mode=0o700)
    stage.chmod(0o700)
    stale = stage / "stale"
    stale.write_text("interrupted", encoding="utf-8")
    stale.chmod(0o600)
    source = runtime_source(tmp_path, monkeypatch)
    monkeypatch.setattr(orchestrator, "_run_npm_runtime_install", fake_npm_install)

    result = orchestrator.runtime_install(
        private_root=root,
        node=tmp_path / "node",
        npm_cli=tmp_path / "npm-cli.js",
        source=source,
    )

    assert result["status"] == "PRO_RUNTIME_INSTALLED"
    assert not stage.exists()
    assert not (root / orchestrator.RUNTIME_ROOT_NAME / "stale").exists()


def test_failed_reinstall_preserves_verified_runtime_and_cleans_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, source, _result = install_fixture_runtime(tmp_path, monkeypatch)
    runtime = root / orchestrator.RUNTIME_ROOT_NAME
    original_manifest = (runtime / orchestrator.RUNTIME_MANIFEST_NAME).read_bytes()

    def interrupted_install(**_arguments: object) -> None:
        raise orchestrator.OrchestrationRefusal("PRO_RUNTIME_INSTALL_FAILED")

    monkeypatch.setattr(orchestrator, "_run_npm_runtime_install", interrupted_install)
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.runtime_install(
            private_root=root,
            node=tmp_path / "node",
            npm_cli=tmp_path / "npm-cli.js",
            source=source,
        )

    assert captured.value.code == "PRO_RUNTIME_INSTALL_FAILED"
    assert (
        runtime / orchestrator.RUNTIME_MANIFEST_NAME
    ).read_bytes() == original_manifest
    assert not (root / orchestrator.RUNTIME_STAGE_NAME).exists()
    assert (
        orchestrator._verify_runtime_at(runtime, source=source, node=tmp_path / "node")[
            "status"
        ]
        == "PRO_RUNTIME_READY"
    )


@pytest.mark.parametrize("existing_kind", ["unsafe-mode", "root-symlink"])
def test_runtime_install_repairs_doctor_directed_root_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    existing_kind: str,
) -> None:
    root, source, _result = install_fixture_runtime(tmp_path, monkeypatch)
    runtime = root / orchestrator.RUNTIME_ROOT_NAME
    preserved: Path | None = None
    if existing_kind == "unsafe-mode":
        runtime.chmod(0o755)
    else:
        preserved = tmp_path / "preserved-old-runtime"
        runtime.rename(preserved)
        runtime.symlink_to(preserved, target_is_directory=True)

    result = orchestrator.runtime_install(
        private_root=root,
        node=tmp_path / "node",
        npm_cli=tmp_path / "npm-cli.js",
        source=source,
    )

    assert result["status"] == "PRO_RUNTIME_INSTALLED"
    assert runtime.is_dir() and not runtime.is_symlink()
    assert not (root / orchestrator.RUNTIME_STAGE_NAME).exists()
    assert (
        orchestrator._verify_runtime_at(runtime, source=source, node=tmp_path / "node")[
            "status"
        ]
        == "PRO_RUNTIME_READY"
    )
    if preserved is not None:
        assert preserved.is_dir()


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("tamper", "PRO_RUNTIME_DRIFTED"),
        ("mode", "PRO_RUNTIME_MODE"),
        ("nested-symlink", "PRO_RUNTIME_SYMLINK"),
        ("root-symlink", "PRO_RUNTIME_SYMLINK"),
        ("source-lock", "PRO_RUNTIME_SOURCE_INVALID"),
    ],
)
def test_runtime_tamper_mode_symlink_and_source_drift_refuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_code: str,
) -> None:
    root, source, _result = install_fixture_runtime(tmp_path, monkeypatch)
    runtime = root / orchestrator.RUNTIME_ROOT_NAME
    cli = runtime / orchestrator.RUNTIME_CLI_RELATIVE
    if mutation == "tamper":
        cli.write_text("// tampered\n", encoding="utf-8")
    elif mutation == "mode":
        cli.chmod(0o644)
    elif mutation == "nested-symlink":
        cli.unlink()
        cli.symlink_to(source / "package.json")
    elif mutation == "root-symlink":
        saved = root / "saved-runtime"
        runtime.rename(saved)
        runtime.symlink_to(saved, target_is_directory=True)
    else:
        lock_path = source / "package-lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lock["packages"]["node_modules/@playwright/mcp"]["integrity"] = (
            "sha512-source-drift"
        )
        lock_path.write_text(json.dumps(lock), encoding="utf-8")
        lock_path.chmod(0o644)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._verify_runtime_at(runtime, source=source, node=tmp_path / "node")

    assert captured.value.code == expected_code


def test_recomputed_runtime_manifest_cannot_bypass_committed_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, source, _result = install_fixture_runtime(tmp_path, monkeypatch)
    runtime = root / orchestrator.RUNTIME_ROOT_NAME
    cli = runtime / orchestrator.RUNTIME_CLI_RELATIVE
    cli.write_text("// tampered and re-manifested\n", encoding="utf-8")
    cli.chmod(0o600)
    manifest_path = runtime / orchestrator.RUNTIME_MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["inventory"] = orchestrator._runtime_inventory(runtime)
    orchestrator._atomic_private_json(manifest_path, manifest)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._verify_runtime_at(runtime, source=source, node=tmp_path / "node")

    assert captured.value.code == "PRO_RUNTIME_DRIFTED"


def test_missing_runtime_is_distinct(tmp_path: Path) -> None:
    root = private_root(tmp_path)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._verify_runtime_at(root / orchestrator.RUNTIME_ROOT_NAME)

    assert captured.value.code == "PRO_RUNTIME_MISSING"


def test_unsafe_interrupted_stage_symlink_is_never_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = private_root(tmp_path)
    source = runtime_source(tmp_path, monkeypatch)
    target = tmp_path / "outside"
    target.mkdir()
    stage = root / orchestrator.RUNTIME_STAGE_NAME
    stage.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(orchestrator, "_run_npm_runtime_install", fake_npm_install)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.runtime_install(
            private_root=root,
            node=tmp_path / "node",
            npm_cli=tmp_path / "npm-cli.js",
            source=source,
        )

    assert captured.value.code == "PRO_RUNTIME_INSTALL_UNSAFE"
    assert stage.is_symlink()
    assert target.is_dir()


def test_npm_install_uses_distinct_private_configs_and_no_lifecycle_scripts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / "stage"
    cache = tmp_path / "cache"
    stage.mkdir()
    cache.mkdir()
    user_config = stage / orchestrator.RUNTIME_USER_NPMRC_NAME
    global_config = stage / orchestrator.RUNTIME_GLOBAL_NPMRC_NAME
    user_config.write_bytes(b"")
    global_config.write_bytes(b"")
    captured: dict[str, Any] = {}

    def run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(orchestrator.subprocess, "run", run)
    orchestrator._run_npm_runtime_install(
        node=tmp_path / "node",
        npm_cli=tmp_path / "npm-cli.js",
        stage=stage,
        cache=cache,
    )

    command = captured["command"]
    environment = captured["environment"]
    assert command[command.index("--userconfig") + 1] == str(user_config)
    assert command[command.index("--globalconfig") + 1] == str(global_config)
    assert user_config != global_config
    assert "--ignore-scripts" in command
    assert "--bin-links=false" in command
    assert environment["NPM_CONFIG_IGNORE_SCRIPTS"] == "true"
    assert environment["NPM_CONFIG_CACHE"] == str(cache)
    assert all("_npx" not in item for item in command)


def setup_state(root: Path) -> None:
    layout = orchestrator._ensure_layout(root)
    orchestrator._atomic_private_json(
        orchestrator._setup_state_path(root),
        {
            "schema_version": orchestrator.ORCHESTRATION_SCHEMA_VERSION,
            "story_id": orchestrator.STORY_ID,
            "status": "LOGIN_NOT_VERIFIED",
            "browser": "edge",
            "browser_executable": str(orchestrator.DEFAULT_EDGE),
            "profile": layout["edge_profile"].name,
            "updated_at": "2026-08-10T00:00:00Z",
        },
    )


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("PRO_RUNTIME_MISSING", "PRO_RUNTIME_MISSING"),
        ("PRO_RUNTIME_DRIFTED", "PRO_RUNTIME_DRIFTED"),
        ("PRO_RUNTIME_MODE", "PRO_RUNTIME_DRIFTED"),
        ("PRO_RUNTIME_SYMLINK", "PRO_RUNTIME_DRIFTED"),
        ("PRO_RUNTIME_TOOLCHAIN_INVALID", "PRO_RUNTIME_DRIFTED"),
    ],
)
def test_doctor_maps_runtime_failures_to_install_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    status: str,
) -> None:
    root = private_root(tmp_path)
    setup_state(root)

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise orchestrator.OrchestrationRefusal(code)

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "_verify_private_runtime", unavailable)
    result = orchestrator.doctor(
        private_root=root,
        fake_scenario=None,
        wrapper=orchestrator.DEFAULT_WRAPPER,
    )

    assert result["status"] == status
    assert result["reason_code"] == code
    assert result["next_action"] == "pro-runtime-install"


@pytest.mark.parametrize("code", ["MCP_START_FAILED", "MCP_DISCONNECTED"])
def test_doctor_keeps_transport_failures_distinct_from_runtime_and_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
) -> None:
    root = private_root(tmp_path)
    setup_state(root)

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise orchestrator.TransportUnavailable(code)

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(
        orchestrator, "_verify_private_runtime", lambda _root: {"status": "ready"}
    )
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", unavailable)
    result = orchestrator.doctor(
        private_root=root,
        fake_scenario=None,
        wrapper=orchestrator.DEFAULT_WRAPPER,
    )

    assert result["status"] == "PRO_UNAVAILABLE"
    assert result["reason_code"] == code
    assert result["next_action"] == "pro-doctor"


def test_doctor_reports_missing_runtime_before_missing_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = private_root(tmp_path)
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)

    result = orchestrator.doctor(
        private_root=root,
        fake_scenario=None,
        wrapper=orchestrator.DEFAULT_WRAPPER,
    )

    assert result == {
        "story_id": orchestrator.STORY_ID,
        "mode": "LIVE",
        "status": "PRO_RUNTIME_MISSING",
        "reason_code": "PRO_RUNTIME_MISSING",
        "next_action": "pro-runtime-install",
    }


def test_stdio_transport_verifies_runtime_before_process_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(orchestrator, "_require_visible_wslg_display", lambda: None)

    def missing(_root: Path) -> None:
        calls.append("verify")
        raise orchestrator.OrchestrationRefusal("PRO_RUNTIME_MISSING")

    def unexpected_popen(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("process must not start before runtime verification")

    monkeypatch.setattr(orchestrator, "_verify_private_runtime", missing)
    monkeypatch.setattr(orchestrator.subprocess, "Popen", unexpected_popen)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.StdioMcpTransport(
            orchestrator.DEFAULT_WRAPPER,
            orchestrator.DEFAULT_PRIVATE_ROOT / "unused.env",
            "edge",
        )

    assert captured.value.code == "PRO_RUNTIME_MISSING"
    assert calls == ["verify"]


def test_stdio_transport_uses_fixed_path_despite_hostile_ambient_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class CapturedProcess(Exception):
        pass

    def capture_popen(*_args: object, **kwargs: Any) -> None:
        captured["environment"] = kwargs["env"]
        raise CapturedProcess

    monkeypatch.setenv("PATH", "/tmp/hostile-bin:/usr/bin:/bin")
    monkeypatch.setenv("PYTHONPATH", "/tmp/hostile-python")
    monkeypatch.setattr(orchestrator, "_require_visible_wslg_display", lambda: None)
    monkeypatch.setattr(
        orchestrator, "_verify_private_runtime", lambda _root: {"status": "ready"}
    )
    monkeypatch.setattr(orchestrator.subprocess, "Popen", capture_popen)

    with pytest.raises(CapturedProcess):
        orchestrator.StdioMcpTransport(
            orchestrator.DEFAULT_WRAPPER,
            orchestrator.DEFAULT_PRIVATE_ROOT / "unused.env",
            "edge",
        )

    environment = captured["environment"]
    assert environment["PATH"] == "/usr/bin:/bin"
    assert "PYTHONPATH" not in environment


def test_stdio_transport_cleans_process_when_initialize_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Process:
        def __init__(self) -> None:
            self.stdin = io.StringIO()
            self.stdout = io.StringIO()
            self.terminated = False

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, *, timeout: int) -> int:
            assert timeout == 5
            return 0

        def kill(self) -> None:
            raise AssertionError("a clean termination must not require kill")

    process = Process()
    monkeypatch.setattr(orchestrator, "_require_visible_wslg_display", lambda: None)
    monkeypatch.setattr(
        orchestrator, "_verify_private_runtime", lambda _root: {"status": "ready"}
    )
    monkeypatch.setattr(orchestrator.subprocess, "Popen", lambda *_a, **_k: process)

    def fail_initialize(*_args: object, **_kwargs: object) -> None:
        raise orchestrator.TransportUnavailable("MCP_DISCONNECTED")

    monkeypatch.setattr(orchestrator.StdioMcpTransport, "_request", fail_initialize)

    with pytest.raises(orchestrator.TransportUnavailable):
        orchestrator.StdioMcpTransport(
            orchestrator.DEFAULT_WRAPPER,
            orchestrator.DEFAULT_PRIVATE_ROOT / "unused.env",
            "edge",
        )

    assert process.stdin.closed
    assert process.terminated is True


def test_orchestrator_and_wrapper_require_matching_exact_tool_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_tool = tmp_path / "node"
    owner_tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    owner_tool.chmod(0o750)
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._require_regular_tool(owner_tool, "PRO_RUNTIME_TOOLCHAIN_INVALID")
    assert captured.value.code == "PRO_RUNTIME_TOOLCHAIN_INVALID"

    browser = tmp_path / "browser"
    browser.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    browser.chmod(0o750)
    monkeypatch.setattr(orchestrator, "DEFAULT_EDGE", browser)
    assert orchestrator._browser_probe("edge") == "invalid"


def test_wrapper_and_runtime_resources_never_reference_shared_npx() -> None:
    paths = [
        orchestrator.DEFAULT_WRAPPER,
        orchestrator.DEFAULT_RUNTIME_SOURCE / "verify_runtime.py",
        orchestrator.DEFAULT_RUNTIME_SOURCE / "package.json",
        orchestrator.DEFAULT_RUNTIME_SOURCE / "package-lock.json",
        orchestrator.DEFAULT_RUNTIME_SOURCE
        / orchestrator.RUNTIME_EXPECTED_INVENTORY_NAME,
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "/.npm/_npx" not in combined
    assert "@playwright/mcp@0.0.79" not in combined
    assert '"@playwright/mcp": "0.0.78"' in combined
    wrapper = orchestrator.DEFAULT_WRAPPER.read_text(encoding="utf-8")
    assert "export PATH=/usr/bin:/bin" in wrapper
    assert '"$PYTHON_BIN" -I -B "$MCP_RUNTIME_VERIFIER"' in wrapper
    assert (
        hashlib.sha256(
            (
                orchestrator.DEFAULT_RUNTIME_SOURCE
                / orchestrator.RUNTIME_EXPECTED_INVENTORY_NAME
            ).read_bytes()
        ).hexdigest()
        == "9b0ab842a6b4d67a7cb0ef85f51c526555dd6d5878198646ab8bf040b3fa70c1"
    )
    assert (
        hashlib.sha256(
            (
                orchestrator.DEFAULT_RUNTIME_SOURCE
                / orchestrator.RUNTIME_PACKAGE_LOCK_NAME
            ).read_bytes()
        ).hexdigest()
        == "67d5785a7b401c97a352098cb646013f7677014e934521e4aad6dc4986bdadb2"
    )
