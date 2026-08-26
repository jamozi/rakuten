"""Deterministic visible-WSLg boundary evidence for approved ST-0101."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
from typing import Any, Iterator

import pytest

from scripts import chatgpt_pro_orchestrator as orchestrator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WRAPPER_PATH = REPOSITORY_ROOT / "scripts/chatgpt_pro_mcp.sh"
MAKEFILE_PATH = REPOSITORY_ROOT / "Makefile"
OUTER_NETWORK_SANDBOX = os.environ.get("RAOS_NETWORK_DENIED") == "1"
PATHNAME_UNIX_SOCKET_REASON = (
    "requires direct unsandboxed execution to create and bind a pathname Unix "
    "socket; ci-network-assert already validates the real network-denial guard "
    "before pytest runs through scripts/run_network_denied.sh"
)
requires_pathname_unix_socket = pytest.mark.skipif(
    OUTER_NETWORK_SANDBOX,
    reason=PATHNAME_UNIX_SOCKET_REASON,
)


@contextmanager
def bound_unix_socket(path: Path) -> Iterator[None]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(path))
        yield


def assert_refused_before_popen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expected_code: str,
) -> None:
    popen_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def unexpected_popen(*args: Any, **kwargs: Any) -> None:
        popen_calls.append((args, kwargs))
        raise AssertionError("Popen must not run after WSLg validation refusal")

    monkeypatch.setattr(orchestrator.subprocess, "Popen", unexpected_popen)
    with pytest.raises(orchestrator.TransportUnavailable) as unavailable:
        orchestrator.StdioMcpTransport(
            orchestrator.DEFAULT_WRAPPER,
            tmp_path / "unused-secret.env",
            "edge",
        )

    assert unavailable.value.code == expected_code
    assert popen_calls == []


def test_wslg_display_and_socket_are_fixed() -> None:
    assert orchestrator.FIXED_WSLG_DISPLAY == ":0"
    assert orchestrator.FIXED_WSLG_X11_SOCKET == Path("/tmp/.X11-unix/X0")


@requires_pathname_unix_socket
@pytest.mark.parametrize(
    "display",
    [None, "", ":1", "localhost:0", " :0", ":0 "],
    ids=["missing", "empty", "other", "remote", "leading-space", "trailing-space"],
)
def test_orchestrator_refuses_nonexact_parent_display_before_popen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    display: str | None,
) -> None:
    socket_path = tmp_path / "X0"
    monkeypatch.setattr(orchestrator, "FIXED_WSLG_X11_SOCKET", socket_path)
    if display is None:
        monkeypatch.delenv("DISPLAY", raising=False)
    else:
        monkeypatch.setenv("DISPLAY", display)

    with bound_unix_socket(socket_path):
        assert_refused_before_popen(
            tmp_path, monkeypatch, expected_code="WSLG_DISPLAY_INVALID"
        )


def test_orchestrator_refuses_absent_x11_endpoint_before_popen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(orchestrator, "DEFAULT_WRAPPER", WRAPPER_PATH)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(orchestrator, "FIXED_WSLG_X11_SOCKET", tmp_path / "absent-X0")

    assert_refused_before_popen(
        tmp_path, monkeypatch, expected_code="WSLG_X11_SOCKET_INVALID"
    )


def test_orchestrator_refuses_regular_x11_endpoint_before_popen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(orchestrator, "DEFAULT_WRAPPER", WRAPPER_PATH)
    socket_path = tmp_path / "X0"
    socket_path.write_text("not a socket", encoding="utf-8")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(orchestrator, "FIXED_WSLG_X11_SOCKET", socket_path)

    assert_refused_before_popen(
        tmp_path, monkeypatch, expected_code="WSLG_X11_SOCKET_INVALID"
    )


@requires_pathname_unix_socket
def test_orchestrator_refuses_symlinked_x11_endpoint_before_popen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_socket_path = tmp_path / "real-X0"
    socket_path = tmp_path / "X0"
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(orchestrator, "FIXED_WSLG_X11_SOCKET", socket_path)

    with bound_unix_socket(real_socket_path):
        socket_path.symlink_to(real_socket_path)
        assert_refused_before_popen(
            tmp_path, monkeypatch, expected_code="WSLG_X11_SOCKET_INVALID"
        )


@pytest.mark.parametrize(
    "display",
    [None, "", ":1", "localhost:0", " :0", ":0 "],
    ids=["missing", "empty", "other", "remote", "leading-space", "trailing-space"],
)
def test_wrapper_refuses_nonexact_display(display: str | None) -> None:
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "RAOS_CHATGPT_BROWSER": "edge",
    }
    if display is not None:
        environment["DISPLAY"] = display

    process = subprocess.run(
        ["/bin/bash", str(WRAPPER_PATH)],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert process.returncode == 64
    assert process.stdout == ""
    assert process.stderr == (
        "chatgpt-pro-mcp: fail-closed launch refusal (invalid-display)\n"
    )


def test_visible_boundary_has_no_ambient_desktop_or_hidden_browser_option() -> None:
    orchestrator_source = (
        REPOSITORY_ROOT / "scripts/chatgpt_pro_orchestrator.py"
    ).read_text(encoding="utf-8")
    wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
    for prohibited in (
        "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR",
        "DBUS_SESSION_BUS_ADDRESS",
        "PULSE_SERVER",
        "--headless",
        "--cdp-endpoint",
        "--extension",
        "--storage-state",
    ):
        assert prohibited not in orchestrator_source
        assert prohibited not in wrapper

    assert "readonly WSLG_DISPLAY=:0" in wrapper
    assert 'test "${DISPLAY:-}" = "$WSLG_DISPLAY" || fail invalid-display' in wrapper

    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "PRO_REQUEST_FILE" not in makefile
    assert "pro-ask:" not in makefile


def test_documentation_requires_chatgpt_only_login_without_edge_sync() -> None:
    readme = (REPOSITORY_ROOT / "changes/st-0101/README.md").read_text(encoding="utf-8")
    assert "Microsoft" in readme
    assert "sync" in readme.lower()
    assert "ChatGPT" in readme
    assert "do not close" in readme


@pytest.mark.raos_owner_private
def test_owner_private_skill_requires_chatgpt_only_login_without_edge_sync() -> None:
    skill = Path("/home/minami/.codex/skills/raos-ask-pro/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "Microsoft" in skill
    assert "sync" in skill.lower()
    assert "ChatGPT" in skill
    assert "do not close" in skill
