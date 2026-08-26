"""Deterministic Edge-first browser evidence for the approved ST-0101 addendum."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import stat
import subprocess
from typing import Any

import pytest

from scripts import chatgpt_pro_orchestrator as orchestrator
from scripts import chatgpt_pro_workflow as workflow


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
EXPECTED_TOOLS = [
    "browser_navigate",
    "browser_click",
    "browser_click",
    "browser_type",
    "browser_click",
    "browser_wait_for",
]


def private_root(tmp_path: Path) -> Path:
    root = tmp_path / ".secrets"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    return root


def private_request(root: Path, name: str = "request.txt") -> Path:
    request_root = root / "chatgpt-pro-requests"
    request_root.mkdir(mode=0o700, exist_ok=True)
    request_root.chmod(0o700)
    path = request_root / name
    path.write_text(
        "Review only the approved ST-0101 browser boundary.", encoding="utf-8"
    )
    path.chmod(0o600)
    return path


def write_setup_state(root: Path, browser: str) -> None:
    layout = orchestrator._ensure_layout(root)
    orchestrator._atomic_private_json(
        orchestrator._setup_state_path(root),
        {
            "schema_version": orchestrator.ORCHESTRATION_SCHEMA_VERSION,
            "story_id": orchestrator.STORY_ID,
            "status": "LOGIN_NOT_VERIFIED",
            "browser": browser,
            "browser_executable": str(orchestrator._browser_executable(browser)),
            "profile": layout[f"{browser}_profile"].name,
            "updated_at": "2026-08-04T00:00:00Z",
        },
    )


def observation(
    state: str,
    *,
    model_label: str | None = None,
    effort_label: str | None = None,
    option_labels: list[str] | None = None,
    refs: dict[str, list[str]] | None = None,
    generating: bool | None = None,
    response_complete: bool = False,
) -> dict[str, Any]:
    return {
        "state": state,
        "url": "https://chatgpt.com/c/fake-edge-selection",
        "authenticated": True,
        "stop_state": None,
        "model_label": model_label,
        "effort_label": effort_label,
        "option_labels": [] if option_labels is None else option_labels,
        "refs": {} if refs is None else refs,
        "generating": generating,
        "response_complete": response_complete,
    }


def transcript() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "profile_id": "pro-extended-combined-v1",
        "observations": [
            observation("landing", refs={"model_picker": ["e1"]}),
            observation(
                "model_menu",
                option_labels=["Pro Standard", "Pro Extended"],
                refs={"target_model": ["e2"]},
            ),
            observation(
                "ready",
                model_label="Pro Extended",
                effort_label="Pro Extended",
                refs={"composer": ["e3"], "send": ["e4"]},
            ),
            observation(
                "submitted",
                model_label="Pro Extended",
                effort_label="Pro Extended",
                generating=True,
            ),
            observation(
                "complete",
                model_label="Pro Extended",
                effort_label="Pro Extended",
                generating=False,
                response_complete=True,
                refs={"assistant_response": ["e5"]},
            ),
        ],
    }


def advice() -> str:
    return json.dumps(
        {
            "schema": "PRO_ADVICE_V1",
            "summary": "Keep the selected browser bound to the run.",
            "material_delta": True,
            "open_gaps": ["One named follow-up gap."],
            "evidence_refs": ["ST-0101 deterministic fixture"],
            "recommendations": ["Reconcile with canonical sources."],
            "authority": "UNAPPROVED_ADVICE",
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def write_scenario(path: Path, *, disconnect_after_tool: int | None = None) -> Path:
    scenario: dict[str, Any] = {
        "schema": orchestrator.FAKE_SCHEMA,
        "response": advice(),
        "transcript": transcript(),
        "expected_tools": EXPECTED_TOOLS,
    }
    if disconnect_after_tool is not None:
        scenario["disconnect_after_tool"] = disconnect_after_tool
    path.write_text(json.dumps(scenario), encoding="utf-8")
    return path


def write_doctor_scenario(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": orchestrator.FAKE_SCHEMA,
                "doctor": {
                    "status": "READY",
                    "url": "https://chatgpt.com/c/fake-doctor",
                    "authenticated": True,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_auto_prefers_edge_without_probing_chrome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / ".secrets"
    probes: list[str] = []

    def probe(browser: str) -> str:
        probes.append(browser)
        return "available"

    monkeypatch.setattr(orchestrator, "_browser_probe", probe)

    result = orchestrator.setup(
        private_root=root,
        open_login=False,
        browser="auto",
    )

    assert probes == ["edge"]
    assert result["browser"] == "edge"
    assert result["browser_executable"] == "/opt/microsoft/msedge/msedge"
    assert result["profile"] == str(root / "chatgpt-pro-edge-profile")
    state = json.loads((root / "chatgpt-pro-setup.v1.json").read_text(encoding="utf-8"))
    assert state["browser"] == "edge"
    assert state["profile"] == "chatgpt-pro-edge-profile"


def test_auto_falls_back_to_chrome_only_when_edge_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / ".secrets"
    probes: list[str] = []

    def probe(browser: str) -> str:
        probes.append(browser)
        return "unavailable" if browser == "edge" else "available"

    monkeypatch.setattr(orchestrator, "_browser_probe", probe)

    result = orchestrator.setup(
        private_root=root,
        open_login=False,
        browser="auto",
    )

    assert probes == ["edge", "chrome"]
    assert result["browser"] == "chrome"
    assert result["browser_executable"] == "/opt/google/chrome/chrome"
    assert result["profile"] == str(root / "chatgpt-pro-profile")


@pytest.mark.parametrize("browser", ["edge", "chrome"])
def test_explicit_missing_browser_fails_without_fallback_or_setup_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    browser: str,
) -> None:
    root = tmp_path / ".secrets"
    probes: list[str] = []

    def probe(candidate: str) -> str:
        probes.append(candidate)
        return "unavailable"

    monkeypatch.setattr(orchestrator, "_browser_probe", probe)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.setup(
            private_root=root,
            open_login=False,
            browser=browser,
        )

    assert captured.value.code == f"{browser.upper()}_UNAVAILABLE"
    assert probes == [browser]
    assert not (root / "chatgpt-pro-setup.v1.json").exists()


def test_auto_does_not_treat_invalid_edge_as_a_fallback_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probes: list[str] = []

    def probe(browser: str) -> str:
        probes.append(browser)
        return "invalid" if browser == "edge" else "available"

    monkeypatch.setattr(orchestrator, "_browser_probe", probe)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.setup(
            private_root=tmp_path / ".secrets",
            open_login=False,
            browser="auto",
        )

    assert captured.value.code == "EDGE_INVALID"
    assert probes == ["edge"]


def test_symlinked_fixed_edge_path_is_invalid_and_never_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "msedge-target"
    target.write_text("not an approved system browser", encoding="utf-8")
    target.chmod(0o755)
    linked_edge = tmp_path / "msedge"
    linked_edge.symlink_to(target)
    monkeypatch.setattr(orchestrator, "DEFAULT_EDGE", linked_edge)

    assert orchestrator._browser_probe("edge") == "invalid"
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._select_browser("auto")
    assert captured.value.code == "EDGE_INVALID"


def test_login_launch_failure_stays_on_selected_edge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / ".secrets"
    probes: list[str] = []
    launched: list[list[str]] = []

    def probe(browser: str) -> str:
        probes.append(browser)
        return "available"

    def failed_launch(command: list[str], **_kwargs: Any) -> Any:
        launched.append(command)
        return type("LaunchResult", (), {"returncode": 1})()

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "_browser_probe", probe)
    monkeypatch.setattr(orchestrator.subprocess, "run", failed_launch)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.setup(private_root=root, open_login=True, browser="auto")

    assert captured.value.code == "LOGIN_BROWSER_FAILED"
    assert probes == ["edge", "edge"]
    assert len(launched) == 1
    assert launched[0][0] == "/opt/microsoft/msedge/msedge"
    assert not any("chrome" in argument for argument in launched[0])


def test_legacy_chrome_input_is_closed_and_normalized_to_package_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy_chrome = orchestrator.LEGACY_CHROME_LAUNCHER
    real_lstat = Path.lstat
    real_resolve = Path.resolve
    real_access = os.access

    def simulated_lstat(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == legacy_chrome:
            return type(
                "RootOwnedExecutable",
                (),
                {"st_mode": stat.S_IFREG | 0o755, "st_uid": 0},
            )()
        return real_lstat(path, *args, **kwargs)

    def simulated_resolve(path: Path, *args: Any, **kwargs: Any) -> Path:
        if path == legacy_chrome:
            return legacy_chrome
        return real_resolve(path, *args, **kwargs)

    def simulated_access(path: Any, mode: int, *args: Any, **kwargs: Any) -> bool:
        if Path(path) == legacy_chrome and mode == os.X_OK:
            return True
        return real_access(path, mode, *args, **kwargs)

    with monkeypatch.context() as positive:
        positive.setattr(Path, "lstat", simulated_lstat)
        positive.setattr(Path, "resolve", simulated_resolve)
        positive.setattr(os, "access", simulated_access)
        assert orchestrator._normalize_setup_browser("auto", legacy_chrome) == "chrome"

    arbitrary = tmp_path / "browser"
    arbitrary.write_text("not approved", encoding="utf-8")
    arbitrary.chmod(0o700)
    with pytest.raises(orchestrator.OrchestrationRefusal) as outside:
        orchestrator._normalize_setup_browser("auto", arbitrary)
    assert outside.value.code == "BROWSER_EXECUTABLE_NOT_ALLOWED"

    symlink_target = tmp_path / "target"
    symlink_target.write_text("not approved", encoding="utf-8")
    symlink_target.chmod(0o700)
    symlink = tmp_path / "legacy-chrome"
    symlink.symlink_to(symlink_target)
    monkeypatch.setattr(orchestrator, "LEGACY_CHROME_LAUNCHER", symlink)
    with pytest.raises(orchestrator.OrchestrationRefusal) as linked:
        orchestrator._normalize_setup_browser("auto", symlink)
    assert linked.value.code == "CHROME_COMPATIBILITY_INPUT_INVALID"


def test_profiles_are_separate_owner_private_and_repository_scoped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / ".secrets"
    monkeypatch.setattr(orchestrator, "_browser_probe", lambda _browser: "available")

    orchestrator.setup(private_root=root, open_login=False, browser="edge")
    layout = orchestrator._ensure_layout(root)
    edge_profile = layout["edge_profile"]
    chrome_profile = layout["chrome_profile"]

    assert edge_profile != chrome_profile
    assert edge_profile.parent == chrome_profile.parent == root
    assert edge_profile.name == "chatgpt-pro-edge-profile"
    assert chrome_profile.name == "chatgpt-pro-profile"
    for profile in (edge_profile, chrome_profile):
        assert stat.S_IMODE(profile.stat().st_mode) == 0o700
        assert profile.stat().st_uid == os.getuid()
        assert "/mnt/c/" not in str(profile)
    assert ".config/microsoft-edge" not in str(edge_profile)
    assert ".config/google-chrome" not in str(chrome_profile)


def test_setup_browser_is_used_by_doctor_and_hash_bound_ask_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / ".secrets"
    monkeypatch.setattr(orchestrator, "_browser_probe", lambda _browser: "available")
    setup_result = orchestrator.setup(
        private_root=root,
        open_login=False,
        browser="chrome",
    )
    doctor_result = orchestrator.doctor(
        private_root=root,
        fake_scenario=write_doctor_scenario(tmp_path / "doctor.json"),
        wrapper=tmp_path / "unused-wrapper",
    )

    request = private_request(root)
    exit_code, ask_result = orchestrator.ask(
        private_root=root,
        request_file=request,
        importance="ordinary",
        fake_scenario=write_scenario(tmp_path / "ask.json"),
        parent_run_id=None,
        gap_file=None,
    )

    assert setup_result["browser"] == "chrome"
    assert doctor_result["browser"] == "chrome"
    assert doctor_result["profile"] == str(root / "chatgpt-pro-profile")
    assert exit_code == 0
    assert ask_result["browser"] == "chrome"
    run_dir = root / "chatgpt-pro-runs" / ask_result["run_id"]
    state = json.loads(
        (run_dir / "orchestration-state.v1.json").read_text(encoding="utf-8")
    )
    assert state["browser"] == "chrome"
    lines = (run_dir / "run-record.v1.jsonl").read_text(encoding="utf-8").splitlines()
    _, final_hash = workflow._verify_events(lines, ask_result["run_id"])
    assert final_hash == json.loads(lines[-1])["event_sha256"]
    assert json.loads(lines[-1])["payload"]["state_sha256"] == (
        orchestrator.hashlib.sha256(orchestrator._canonical_json(state)).hexdigest()
    )


def test_valid_browser_tamper_breaks_the_run_state_hash_binding(tmp_path: Path) -> None:
    root = private_root(tmp_path)
    write_setup_state(root, "edge")
    exit_code, result = orchestrator.ask(
        private_root=root,
        request_file=private_request(root),
        importance="ordinary",
        fake_scenario=write_scenario(tmp_path / "success.json"),
        parent_run_id=None,
        gap_file=None,
    )
    assert exit_code == 0
    run_dir = root / "chatgpt-pro-runs" / result["run_id"]
    state_path = run_dir / "orchestration-state.v1.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["browser"] = "chrome"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    state_path.chmod(0o600)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.status(private_root=root, run_id=result["run_id"])
    assert captured.value.code == "STATE_RECORD_MISMATCH"


def test_resume_uses_run_browser_even_if_setup_selection_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = private_root(tmp_path)
    write_setup_state(root, "edge")
    exit_code, pending = orchestrator.ask(
        private_root=root,
        request_file=private_request(root),
        importance="ordinary",
        fake_scenario=write_scenario(
            tmp_path / "pending.json", disconnect_after_tool=5
        ),
        parent_run_id=None,
        gap_file=None,
    )
    assert exit_code == 0
    assert pending["status"] == "SUBMISSION_AMBIGUOUS"
    run_root = root / "chatgpt-pro-runs"
    run_dir, state = orchestrator._load_state(run_root, pending["run_id"])
    state["conversation_url"] = "https://chatgpt.com/c/fake-edge-selection"
    orchestrator._persist_state(
        run_dir,
        run_dir / "run-record.v1.jsonl",
        state,
        event_type="RESUME_SCOPE_BOUND",
        event_payload={"browser": state["browser"]},
    )
    write_setup_state(root, "chrome")
    captured_browsers: list[str] = []
    transports: list[SnapshotTransport] = []

    def fake_transport(
        _wrapper: Path, secret_file: Path, browser: str
    ) -> SnapshotTransport:
        captured_browsers.append(browser)
        transport = SnapshotTransport("", secret_file)
        transports.append(transport)
        return transport

    def fake_resume_live_capture(**arguments: Any) -> None:
        captured_browsers.append(arguments["browser"])
        raise orchestrator.TransportUnavailable("MCP_DISCONNECTED_WAITING")

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", fake_transport)
    monkeypatch.setattr(orchestrator, "_resume_live_capture", fake_resume_live_capture)

    resume_code, resumed = orchestrator.resume(
        private_root=root,
        run_id=pending["run_id"],
        fake_scenario=None,
    )

    assert resume_code == 0
    assert resumed["status"] == "WAITING"
    assert resumed["browser"] == "edge"
    assert captured_browsers == ["edge", "edge"]
    assert len(transports) == 1
    assert transports[0].closed is True
    assert not transports[0].secret_file.exists()
    _, final_state = orchestrator._load_state(run_root, pending["run_id"])
    assert final_state["browser"] == "edge"


class SnapshotTransport:
    mode = "LIVE"

    def __init__(self, snapshot: str, secret_file: Path) -> None:
        self.snapshot = snapshot
        self.secret_file = secret_file
        self.calls: list[str] = []
        self.closed = False

    def call(self, tool: str, _arguments: dict[str, Any]) -> str:
        self.calls.append(tool)
        return self.snapshot if tool == "browser_snapshot" else ""

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("snapshot", "expected_code", "returns_result", "settles"),
    [
        pytest.param(
            '- Page URL: https://chatgpt.com/\n- button "Log in" [ref=e90]',
            "STOP_LOGIN",
            True,
            False,
            id="login",
        ),
        pytest.param(
            '- Page URL: https://chatgpt.com/\n- alert "CAPTCHA" [ref=e90]',
            "STOP_CAPTCHA",
            True,
            False,
            id="captcha",
        ),
        pytest.param(
            '- Page URL: https://chatgpt.com/\n- alert "Too many requests" [ref=e90]',
            "STOP_RATE_LIMIT",
            True,
            False,
            id="rate-limit",
        ),
        pytest.param(
            '- Page URL: https://chatgpt.com/\n- button "Choose an account" [ref=e90]',
            "STOP_ACCOUNT_AMBIGUITY",
            True,
            False,
            id="account-ambiguity",
        ),
        pytest.param(
            '- Page URL: https://chatgpt.com/\n- dialog "Session expired" [ref=e90]',
            "STOP_REAUTHENTICATION",
            True,
            False,
            id="reauthentication",
        ),
        pytest.param(
            "- Page URL: https://chatgpt.com.evil.example/",
            "ORIGIN_MISMATCH",
            False,
            False,
            id="origin",
        ),
        pytest.param(
            "- Page URL: https://chatgpt.com/",
            "UNKNOWN_UI",
            False,
            True,
            id="unknown-ui",
        ),
        pytest.param(
            "\n".join(
                (
                    "- Page URL: https://chatgpt.com/",
                    '- textbox "Ask anything" [ref=e1]',
                    '- textbox "Ask anything" [ref=e2]',
                )
            ),
            "UNKNOWN_UI",
            False,
            True,
            id="selector-ambiguity",
        ),
    ],
)
def test_stop_states_never_trigger_cross_browser_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    snapshot: str,
    expected_code: str,
    returns_result: bool,
    settles: bool,
) -> None:
    root = private_root(tmp_path)
    write_setup_state(root, "edge")
    transports: list[SnapshotTransport] = []
    browsers: list[str] = []

    def factory(_wrapper: Path, secret_file: Path, browser: str) -> SnapshotTransport:
        browsers.append(browser)
        transport = SnapshotTransport(snapshot, secret_file)
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(
        orchestrator, "_verify_private_runtime", lambda _root: {"status": "ready"}
    )
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", factory)

    if returns_result:
        result = orchestrator.doctor(
            private_root=root,
            fake_scenario=None,
            wrapper=orchestrator.DEFAULT_WRAPPER,
        )
        assert result["reason_code"] == expected_code
    else:
        with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
            orchestrator.doctor(
                private_root=root,
                fake_scenario=None,
                wrapper=orchestrator.DEFAULT_WRAPPER,
            )
        assert captured.value.code == expected_code

    assert browsers == ["edge"]
    assert len(transports) == 1
    expected_calls = ["browser_navigate", "browser_snapshot"]
    if settles:
        expected_calls.extend(["browser_wait_for", "browser_snapshot"])
    assert transports[0].calls == expected_calls
    assert transports[0].closed is True
    assert not transports[0].secret_file.exists()


@requires_pathname_unix_socket
@pytest.mark.parametrize("browser", ["edge", "chrome"])
def test_stdio_child_receives_only_the_selected_closed_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    browser: str,
) -> None:
    captured: dict[str, Any] = {}
    display_socket_path = tmp_path / "X0"

    def refuse_popen(command: list[str], **kwargs: Any) -> None:
        captured["command"] = command
        captured.update(kwargs)
        raise OSError("synthetic no-launch refusal")

    monkeypatch.setenv("DISPLAY", ":0")
    for name in (
        "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR",
        "DBUS_SESSION_BUS_ADDRESS",
        "PULSE_SERVER",
    ):
        monkeypatch.setenv(name, f"untrusted-{name.lower()}")
    monkeypatch.setattr(orchestrator, "FIXED_WSLG_X11_SOCKET", display_socket_path)
    monkeypatch.setattr(
        orchestrator,
        "_verify_private_runtime",
        lambda _private_root: {"status": "PRO_RUNTIME_READY"},
    )
    monkeypatch.setattr(orchestrator.subprocess, "Popen", refuse_popen)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as display_socket:
        display_socket.bind(str(display_socket_path))
        with pytest.raises(orchestrator.TransportUnavailable) as unavailable:
            orchestrator.StdioMcpTransport(
                orchestrator.DEFAULT_WRAPPER,
                tmp_path / "unused-secret.env",
                browser,
            )

    assert unavailable.value.code == "MCP_START_FAILED"
    assert captured["command"] == [
        "/bin/bash",
        str(orchestrator.DEFAULT_WRAPPER),
    ]
    environment = captured["env"]
    assert environment["DISPLAY"] == ":0"
    assert environment["RAOS_CHATGPT_BROWSER"] == browser
    assert "PROFILE" not in " ".join(environment)
    assert "EXECUTABLE" not in " ".join(environment)
    assert set(environment) == {
        "DISPLAY",
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "PLAYWRIGHT_MCP_SECRETS_FILE",
        "RAOS_CHATGPT_BROWSER",
        "TZ",
    }


@pytest.mark.parametrize("browser", ["", "auto", "firefox", "Edge", "/bin/sh"])
def test_wrapper_refuses_every_non_selected_browser_value(browser: str) -> None:
    process = subprocess.run(
        ["/bin/bash", str(WRAPPER_PATH)],
        cwd=REPOSITORY_ROOT,
        env={
            "DISPLAY": ":0",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "RAOS_CHATGPT_BROWSER": browser,
        },
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert process.returncode == 64
    assert process.stdout == ""
    assert process.stderr == (
        "chatgpt-pro-mcp: fail-closed launch refusal (invalid-browser)\n"
    )


@pytest.mark.parametrize("browser", ["edge", "chrome"])
def test_wrapper_accepts_closed_value_before_requiring_private_secret(
    browser: str,
) -> None:
    process = subprocess.run(
        ["/bin/bash", str(WRAPPER_PATH)],
        cwd=REPOSITORY_ROOT,
        env={
            "DISPLAY": ":0",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "RAOS_CHATGPT_BROWSER": browser,
        },
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert process.returncode == 64
    assert process.stdout == ""
    assert process.stderr == (
        "chatgpt-pro-mcp: fail-closed launch refusal (missing-secret-file)\n"
    )


def test_wrapper_and_makefile_keep_only_fixed_browser_mappings() -> None:
    wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
    for required in (
        "readonly EDGE_EXECUTABLE=/opt/microsoft/msedge/msedge",
        "readonly CHROME_EXECUTABLE=/opt/google/chrome/chrome",
        'readonly EDGE_PROFILE_DIR="${PRIVATE_ROOT}/chatgpt-pro-edge-profile"',
        'readonly CHROME_PROFILE_DIR="${PRIVATE_ROOT}/chatgpt-pro-profile"',
        "readonly MCP_BROWSER=msedge",
        "readonly MCP_BROWSER=chrome",
        "browser=${RAOS_CHATGPT_BROWSER:-}",
        'check_fixed_executable "$BROWSER_EXECUTABLE"',
        '--browser "$MCP_BROWSER"',
        '--executable-path "$BROWSER_EXECUTABLE"',
        '--user-data-dir "$PROFILE_DIR"',
    ):
        assert required in wrapper
    exact_browser_launch = "\n".join(
        (
            '  --browser "$MCP_BROWSER" \\',
            '  --executable-path "$BROWSER_EXECUTABLE" \\',
            '  --user-data-dir "$PROFILE_DIR" \\',
        )
    )
    assert exact_browser_launch in wrapper
    assert wrapper.count('--executable-path "$BROWSER_EXECUTABLE"') == 1
    for prohibited in (
        "/mnt/c/",
        ".config/microsoft-edge",
        ".config/google-chrome",
        "--profile-directory",
        "PLAYWRIGHT_MCP_EXECUTABLE_PATH",
    ):
        assert prohibited not in wrapper

    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "PRO_BROWSER" not in makefile
    assert "pro-ask:" not in makefile


def test_documentation_records_edge_first_scope_and_profile_prohibition() -> None:
    readme = (REPOSITORY_ROOT / "changes/st-0101/README.md").read_text(encoding="utf-8")
    assert "Edge" in readme
    assert "Chrome" in readme
    assert "unavailable before launch" in readme
    assert "never" in readme
    assert "Windows" in readme
    assert "personal" in readme
    assert "switch browsers" in readme
    assert "PRO_BROWSER=auto" in readme
    assert "PRO_BROWSER=edge" in readme
    assert "PRO_BROWSER=chrome" in readme


@pytest.mark.raos_owner_private
def test_owner_private_skill_records_edge_first_scope_and_profile_prohibition() -> None:
    skill = Path("/home/minami/.codex/skills/raos-ask-pro/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "Edge" in skill
    assert "Chrome" in skill
    assert "unavailable before launch" in skill
    assert "never" in skill
    assert "Windows" in skill
    assert "personal" in skill
    assert "switch browsers" in skill
