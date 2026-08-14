"""Fake-only evidence for the ST-0101 ChatGPT Pro orchestrator."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading
import tomllib
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import chatgpt_pro_orchestrator as orchestrator
from scripts import chatgpt_pro_workflow as workflow


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_PATH = REPOSITORY_ROOT / "scripts/chatgpt_pro_orchestrator.py"
PYTHON_LAUNCHER_PATH = REPOSITORY_ROOT / "scripts/chatgpt_pro_python.sh"
MAKEFILE_PATH = REPOSITORY_ROOT / "Makefile"
CONFIG_PATH = REPOSITORY_ROOT / ".codex/config.toml"
AGENTS_PATH = REPOSITORY_ROOT / "AGENTS.md"
SKILL_ROOT = Path("/home/minami/.codex/skills/raos-ask-pro")

REQUEST_TEXT = "Compare the existing boundaries using only cited repository evidence."
MCP_STALE_REF_SENTINEL = "f12e987654"
MCP_STALE_REF_ERROR = (
    f"### Error\nError: Ref {MCP_STALE_REF_SENTINEL} not found in the current "
    "page snapshot. Try capturing new snapshot."
)
MCP_NONEDITABLE_ERROR = (
    "### Error\nError: locator.fill: Error: Element is not an <input>, <textarea> "
    "or [contenteditable] element"
)
MCP_FILL_TIMEOUT_ERROR = (
    "### Error\nTimeoutError: locator.fill: Timeout 5000ms exceeded."
)
MCP_CALL_LOG_SENTINEL = "RAW_CALL_LOG_SENTINEL_TYPED_COMPOSER"
MCP_CALL_LOG_CONTINUATION = (
    "\nCall log:\n"
    f"  - waiting for locator('aria-ref=e778899') {MCP_CALL_LOG_SENTINEL}\n"
)
EXPECTED_TOOLS = [
    "browser_navigate",
    "browser_click",
    "browser_click",
    "browser_type",
    "browser_click",
    "browser_wait_for",
]


def mcp_error_result(text: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "isError": True,
    }


def observation(
    state: str,
    *,
    model_label: str | None = None,
    effort_label: str | None = None,
    option_labels: list[str] | None = None,
    refs: dict[str, list[str]] | None = None,
    generating: bool | None = None,
    response_complete: bool = False,
    authenticated: bool = True,
    stop_state: str | None = None,
    url: str = "https://chatgpt.com/c/fake-orchestration-run",
) -> dict[str, Any]:
    return {
        "state": state,
        "url": url,
        "authenticated": authenticated,
        "stop_state": stop_state,
        "model_label": model_label,
        "effort_label": effort_label,
        "option_labels": [] if option_labels is None else option_labels,
        "refs": {} if refs is None else refs,
        "generating": generating,
        "response_complete": response_complete,
    }


def combined_transcript() -> dict[str, Any]:
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


def advice_text(
    summary: str = "Keep the approved interface boundary.",
    *,
    material_delta: bool = True,
    open_gaps: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "schema": "PRO_ADVICE_V1",
            "summary": summary,
            "material_delta": material_delta,
            "open_gaps": ["Name the remaining failure boundary."]
            if open_gaps is None
            else open_gaps,
            "evidence_refs": ["ST-0101 fixture evidence"],
            "recommendations": ["Reconcile this advice with canonical sources."],
            "authority": "UNAPPROVED_ADVICE",
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def private_root(tmp_path: Path) -> Path:
    root = tmp_path / ".secrets"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    return root


def write_setup_state(root: Path, browser: str = "edge") -> None:
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


def private_request(
    root: Path,
    name: str,
    text: str = REQUEST_TEXT,
    *,
    mode: int = 0o600,
) -> Path:
    request_root = root / "chatgpt-pro-requests"
    request_root.mkdir(mode=0o700, exist_ok=True)
    request_root.chmod(0o700)
    path = request_root / name
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)
    return path


def write_scenario(
    path: Path,
    *,
    response: str | None = None,
    transcript: dict[str, Any] | None = None,
    expected_tools: list[str] | None = None,
    doctor: dict[str, Any] | None = None,
    disconnect_after_tool: int | None = None,
    transport_error: str | None = None,
) -> Path:
    value: dict[str, Any] = {"schema": orchestrator.FAKE_SCHEMA}
    if response is not None:
        value["response"] = response
    if transcript is not None:
        value["transcript"] = transcript
    if expected_tools is not None:
        value["expected_tools"] = expected_tools
    if doctor is not None:
        value["doctor"] = doctor
    if disconnect_after_tool is not None:
        value["disconnect_after_tool"] = disconnect_after_tool
    if transport_error is not None:
        value["transport_error"] = transport_error
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def successful_scenario(
    path: Path,
    *,
    response: str | None = None,
) -> Path:
    return write_scenario(
        path,
        response=advice_text() if response is None else response,
        transcript=combined_transcript(),
        expected_tools=EXPECTED_TOOLS,
    )


def ask_fixture(
    root: Path,
    request_file: Path,
    scenario: Path,
    *,
    importance: str = "ordinary",
    parent_run_id: str | None = None,
    gap_file: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    return orchestrator.ask(
        private_root=root,
        request_file=request_file,
        importance=importance,
        fake_scenario=scenario,
        parent_run_id=parent_run_id,
        gap_file=gap_file,
    )


def assert_private_tree(root: Path) -> None:
    for path in root.rglob("*"):
        mode = stat.S_IMODE(path.stat().st_mode)
        if path.is_dir():
            assert mode == 0o700, path
        elif path.is_file():
            assert mode == 0o600, path


class ScriptedLiveTransport:
    """Raw-snapshot transport that never starts a browser or MCP child."""

    mode = "LIVE"

    def __init__(self, snapshots: list[str], secrets_file: Path) -> None:
        self.snapshots = list(snapshots)
        self.secrets_file = secrets_file
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    def call(self, tool: str, arguments: dict[str, Any]) -> str:
        self.calls.append((tool, dict(arguments)))
        if tool == "browser_snapshot":
            if not self.snapshots:
                raise AssertionError("unexpected browser snapshot")
            return self.snapshots.pop(0)
        return ""

    def close(self) -> None:
        self.closed = True


def accept_snapshot_as_stable(
    _transport: ScriptedLiveTransport,
    snapshot: str,
    *,
    profile_id: str,
    on_progress: Any = None,
    on_checked_url: Any = None,
) -> tuple[str, str]:
    """Bypass the separately tested stability barrier in lifecycle-only tests."""

    assert profile_id
    assert on_progress is None or callable(on_progress)
    assert on_checked_url is None or callable(on_checked_url)
    url = orchestrator._extract_url(snapshot)
    if on_checked_url is not None:
        on_checked_url(url)
    return snapshot, url


def prepare_live_waiting_run(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    importance: str,
    name: str,
) -> dict[str, Any]:
    """Create a public LIVE WAITING run without launching a browser or MCP child."""

    write_setup_state(root)
    request = private_request(root, f"{name}.txt")
    transports: list[ScriptedLiveTransport] = []

    def scripted_transport(
        _wrapper: Path, secrets_file: Path, browser: str
    ) -> ScriptedLiveTransport:
        assert browser == "edge"
        transport = ScriptedLiveTransport([], secrets_file)
        transports.append(transport)
        return transport

    def pending_capture(**_kwargs: Any) -> None:
        raise orchestrator.LivePending(
            combined_transcript(),
            "https://chatgpt.com/c/fake-live-resume-run",
        )

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(
        orchestrator, "_verify_private_runtime", lambda _root: {"status": "ready"}
    )
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", scripted_transport)
    monkeypatch.setattr(orchestrator, "_live_capture", pending_capture)

    exit_code, result = orchestrator.ask(
        private_root=root,
        request_file=request,
        importance=importance,
        fake_scenario=None,
        parent_run_id=None,
        gap_file=None,
    )

    assert exit_code == 0
    assert result["status"] == "WAITING"
    assert result["mode"] == "LIVE"
    assert result["resubmit_allowed"] is False
    assert len(transports) == 1
    assert transports[0].calls == []
    assert transports[0].closed is True
    assert not transports[0].secrets_file.exists()
    return result


def prepare_live_diagnostic_run(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    reason_code: str,
    phase: str,
    importance: str,
) -> tuple[int, dict[str, Any], ScriptedLiveTransport]:
    """Create one inert pre-submission diagnostic run without live I/O."""

    write_setup_state(root)
    request = private_request(
        root,
        f"diagnostic-{reason_code.lower()}-{importance}.txt",
        "RAW_PROMPT_SENTINEL_CLOSED_DIAGNOSTIC",
    )
    transports: list[ScriptedLiveTransport] = []

    def scripted_transport(
        _wrapper: Path, secrets_file: Path, browser: str
    ) -> ScriptedLiveTransport:
        assert browser == "edge"
        transport = ScriptedLiveTransport([], secrets_file)
        transports.append(transport)
        return transport

    def diagnostic_capture(**_arguments: Any) -> None:
        raise orchestrator.LiveUiUnavailable(reason_code, phase)

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", scripted_transport)
    monkeypatch.setattr(orchestrator, "_live_capture", diagnostic_capture)

    exit_code, result = orchestrator.ask(
        private_root=root,
        request_file=request,
        importance=importance,
        fake_scenario=None,
        parent_run_id=None,
        gap_file=None,
    )

    assert len(transports) == 1
    return exit_code, result, transports[0]


def rewrite_hash_bound_terminal(
    run_dir: Path,
    *,
    mutate_state: Any,
    mutate_event: Any,
) -> None:
    """Rebuild one test record so semantic tampering still has valid hashes."""

    state_path = run_dir / "orchestration-state.v1.json"
    record_path = run_dir / "run-record.v1.jsonl"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in record_path.read_text(encoding="utf-8").splitlines()
    ]
    mutate_state(state)
    orchestrator._atomic_private_json(state_path, state)
    final_event = events[-1]
    final_event["payload"]["state_sha256"] = hashlib.sha256(
        orchestrator._canonical_json(state)
    ).hexdigest()
    mutate_event(final_event)
    record_path.unlink()
    for event in events:
        workflow._append_event(
            record_path,
            event["run_id"],
            event["event_type"],
            event["payload"],
        )


def test_raw_snapshot_elements_parse_complete_roles_labels_and_refs() -> None:
    raw_snapshot = "\n".join(
        (
            '- textbox "Ask anything" [ref=e1]',
            '- button "Send" [ref=e2]',
            '- combobox "Message ChatGPT" [ref=e3]',
        )
    )

    assert orchestrator._elements(raw_snapshot) == [
        ("textbox", "Ask anything", "e1"),
        ("button", "Send", "e2"),
        ("combobox", "Message ChatGPT", "e3"),
    ]


def test_doctor_and_ready_parser_recognize_observed_exact_ask_chatgpt() -> None:
    raw_snapshot = "\n".join(
        (
            "- Page URL: https://chatgpt.com/",
            '- button "Pro" [ref=e1]',
            '- textbox "Ask ChatGPT" [ref=e2]',
            '- button "Send" [ref=e3]',
        )
    )

    assert orchestrator.COMPOSER_LABELS == frozenset(
        {
            "ask anything",
            "ask chatgpt",
            "chat with chatgpt",
            "message chatgpt",
            "message",
            "send a message",
        }
    )
    assert orchestrator._doctor_snapshot(raw_snapshot) == {
        "status": "READY",
        "url": "https://chatgpt.com/",
        "authenticated": True,
    }
    ready = orchestrator._ready_observation(
        raw_snapshot,
        {"target_model": "Pro", "target_effort": "Extended"},
    )
    assert ready["state"] == "ready"
    assert ready["refs"] == {"composer": ["e2"], "send": ["e3"]}


@pytest.mark.parametrize(
    "composer_label",
    ["Ask ChatGPT!", "Ask Chat GPT", "AskChatGPT", "Ask ChatGPT now"],
)
def test_doctor_refuses_ask_chatgpt_near_misses(composer_label: str) -> None:
    raw_snapshot = "\n".join(
        (
            "- Page URL: https://chatgpt.com/",
            '- button "Pro" [ref=e1]',
            f'- textbox "{composer_label}" [ref=e2]',
        )
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._doctor_snapshot(raw_snapshot)

    assert captured.value.code == "UNKNOWN_UI"


def test_doctor_refuses_duplicate_ask_chatgpt_composer_refs() -> None:
    raw_snapshot = "\n".join(
        (
            "- Page URL: https://chatgpt.com/",
            '- button "Pro" [ref=e1]',
            '- textbox "Ask ChatGPT" [ref=e2]',
            '- textbox "ASK CHATGPT" [ref=e3]',
        )
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._doctor_snapshot(raw_snapshot)

    assert captured.value.code == "UNKNOWN_UI"


def test_doctor_recognizes_observed_exact_chat_with_chatgpt() -> None:
    sanitized_snapshot = "\n".join(
        (
            "- Page URL: https://chatgpt.com/",
            '- button "Pro" [ref=e1]',
            '- textbox "Chat with ChatGPT" [ref=e2]',
        )
    )

    assert orchestrator._doctor_snapshot(sanitized_snapshot) == {
        "status": "READY",
        "url": "https://chatgpt.com/",
        "authenticated": True,
    }


def test_ready_parser_recognizes_exact_chat_with_chatgpt_when_send_present() -> None:
    sanitized_snapshot = "\n".join(
        (
            "- Page URL: https://chatgpt.com/",
            '- button "Pro" [ref=e1]',
            '- textbox "Chat with ChatGPT" [ref=e2]',
            '- button "Send" [ref=e3]',
        )
    )

    ready = orchestrator._ready_observation(
        sanitized_snapshot,
        {"target_model": "Pro", "target_effort": "Extended"},
    )

    assert ready["state"] == "ready"
    assert ready["refs"] == {"composer": ["e2"], "send": ["e3"]}


@pytest.mark.parametrize(
    "composer_label",
    [
        "Chat with ChatGPT!",
        "Chat with Chat GPT",
        "Chatwith ChatGPT",
        "Chat with ChatGPT now",
    ],
)
def test_doctor_refuses_chat_with_chatgpt_near_misses(composer_label: str) -> None:
    sanitized_snapshot = "\n".join(
        (
            "- Page URL: https://chatgpt.com/",
            '- button "Pro" [ref=e1]',
            f'- textbox "{composer_label}" [ref=e2]',
        )
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._doctor_snapshot(sanitized_snapshot)

    assert captured.value.code == "UNKNOWN_UI"


def test_doctor_refuses_duplicate_chat_with_chatgpt_composer_refs() -> None:
    sanitized_snapshot = "\n".join(
        (
            "- Page URL: https://chatgpt.com/",
            '- button "Pro" [ref=e1]',
            '- textbox "Chat with ChatGPT" [ref=e2]',
            '- textbox "CHAT WITH CHATGPT" [ref=e3]',
        )
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._doctor_snapshot(sanitized_snapshot)

    assert captured.value.code == "UNKNOWN_UI"


def test_raw_snapshot_ready_parser_resolves_composer_and_send() -> None:
    raw_snapshot = "\n".join(
        (
            "- Page URL: https://chatgpt.com/",
            '- button "Pro Extended" [ref=e1]',
            '- textbox "Ask anything" [ref=e2]',
            '- button "Send" [ref=e3]',
        )
    )

    result = orchestrator._ready_observation(
        raw_snapshot,
        {"target_model": "Pro Extended", "target_effort": "Pro Extended"},
    )

    assert result["state"] == "ready"
    assert result["refs"] == {"composer": ["e2"], "send": ["e3"]}


@pytest.mark.parametrize(
    "selector_lines",
    [
        (
            '- textbox "Ask anything" [ref=e2]',
            '- textbox "Ask anything" [ref=e3]',
            '- button "Send" [ref=e4]',
        ),
        (
            '- textbox "Ask anything" [ref=e2]',
            '- button "Send" [ref=e3]',
            '- button "Send" [ref=e4]',
        ),
        (
            '- textbox "Ask anything" [ref=e0]',
            '- button "Send" [ref=e3]',
        ),
        (
            '- textbox "Unknown composer" [ref=e2]',
            '- button "Send" [ref=e3]',
        ),
    ],
)
def test_raw_snapshot_selectors_remain_fail_closed(
    selector_lines: tuple[str, ...],
) -> None:
    raw_snapshot = "\n".join(
        (
            "- Page URL: https://chatgpt.com/",
            '- button "Pro Extended" [ref=e1]',
            *selector_lines,
        )
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._ready_observation(
            raw_snapshot,
            {"target_model": "Pro Extended", "target_effort": "Pro Extended"},
        )

    assert captured.value.code == "SELECTOR_AMBIGUITY"


def invoke_orchestrator_main(arguments: list[str]) -> int:
    """Run the CLI entry point without leaking its restrictive process umask."""

    previous_umask = os.umask(0o077)
    try:
        return orchestrator.main(arguments)
    finally:
        os.umask(previous_umask)


def test_setup_without_login_is_noninteractive_and_owner_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / ".secrets"
    monkeypatch.setattr(
        orchestrator,
        "_browser_probe",
        lambda browser: "available" if browser == "edge" else "unavailable",
    )

    result = orchestrator.setup(
        private_root=root,
        open_login=False,
        browser="auto",
    )

    assert result == {
        "browser": "edge",
        "browser_executable": str(orchestrator.DEFAULT_EDGE),
        "login_opened": False,
        "next_action": "pro-doctor",
        "profile": str(root / "chatgpt-pro-edge-profile"),
        "status": "SETUP_READY",
        "story_id": "ST-0101",
    }
    setup_state = json.loads(
        (root / "chatgpt-pro-setup.v1.json").read_text(encoding="utf-8")
    )
    assert setup_state["status"] == "LOGIN_NOT_VERIFIED"
    assert setup_state["browser"] == "edge"
    assert_private_tree(root)


def test_setup_opens_and_waits_for_the_dedicated_login_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / ".secrets"
    calls: list[dict[str, Any]] = []

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append({"command": command, **kwargs})
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "_browser_probe", lambda _browser: "available")
    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)

    result = orchestrator.setup(
        private_root=root,
        open_login=True,
        browser="chrome",
    )

    assert result["login_opened"] is True
    assert result["next_action"] == "pro-doctor"
    assert len(calls) == 1
    assert calls[0]["command"] == [
        str(orchestrator.DEFAULT_CHROME),
        f"--user-data-dir={root / 'chatgpt-pro-profile'}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://chatgpt.com/",
    ]
    assert calls[0]["check"] is False
    assert_private_tree(root)


@pytest.mark.parametrize(
    ("doctor_result", "expected_status", "expected_authenticated"),
    [
        (
            {
                "status": "READY",
                "url": "https://chatgpt.com/c/fake-ready",
                "authenticated": True,
            },
            "READY",
            True,
        ),
        (
            {
                "status": "LOGIN_REQUIRED",
                "url": "https://chatgpt.com/",
                "authenticated": False,
            },
            "LOGIN_REQUIRED",
            False,
        ),
    ],
)
def test_doctor_reports_ready_or_login_required_from_fake_snapshot(
    tmp_path: Path,
    doctor_result: dict[str, Any],
    expected_status: str,
    expected_authenticated: bool,
) -> None:
    root = private_root(tmp_path)
    write_setup_state(root)
    scenario = write_scenario(tmp_path / "doctor.json", doctor=doctor_result)

    result = orchestrator.doctor(
        private_root=root,
        fake_scenario=scenario,
        wrapper=tmp_path / "unused-wrapper",
    )

    assert result["mode"] == "LOCAL_FIXTURE"
    assert result["status"] == expected_status
    assert result["authenticated"] is expected_authenticated


def test_doctor_refuses_non_exact_origin_in_fake_input(tmp_path: Path) -> None:
    root = private_root(tmp_path)
    write_setup_state(root)
    scenario = write_scenario(
        tmp_path / "doctor-origin-drift.json",
        doctor={
            "status": "READY",
            "url": "https://chatgpt.com.evil.example/",
            "authenticated": True,
        },
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.doctor(
            private_root=root,
            fake_scenario=scenario,
            wrapper=tmp_path / "unused-wrapper",
        )
    assert captured.value.code == "ORIGIN_MISMATCH"


def test_live_doctor_reports_compound_cloudflare_challenge_as_captcha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = private_root(tmp_path)
    write_setup_state(root)
    raw_snapshot = "\n".join(
        (
            "- Page URL: https://chatgpt.com/",
            "- HTTP status: 403",
            "- challenges.cloudflare.com",
            "- Cloudflare",
        )
    )
    transports: list[ScriptedLiveTransport] = []

    def scripted_transport(
        _wrapper: Path, secrets_file: Path, browser: str
    ) -> ScriptedLiveTransport:
        assert browser == "edge"
        transport = ScriptedLiveTransport([raw_snapshot], secrets_file)
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(
        orchestrator, "_verify_private_runtime", lambda _root: {"status": "ready"}
    )
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", scripted_transport)

    exit_code = invoke_orchestrator_main(
        [
            "doctor",
            "--private-root",
            str(root),
            "--wrapper",
            str(tmp_path / "unused-wrapper"),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert raw_snapshot not in captured.out
    assert json.loads(captured.out) == {
        "authenticated": False,
        "browser": "edge",
        "mode": "LIVE",
        "next_action": "STOP",
        "profile": str(root / "chatgpt-pro-edge-profile"),
        "reason_code": "STOP_CAPTCHA",
        "status": "STOPPED",
        "story_id": "ST-0101",
        "url": "https://chatgpt.com/",
    }
    assert len(transports) == 1
    transport = transports[0]
    assert transport.closed is True
    assert [tool for tool, _arguments in transport.calls] == [
        "browser_navigate",
        "browser_snapshot",
    ]
    assert not any(
        tool in {"browser_click", "browser_type"}
        for tool, _arguments in transport.calls
    )
    assert not transport.secrets_file.exists()


@pytest.mark.parametrize(
    "challenge_lines",
    [
        ("- challenges.cloudflare.com", "- Cloudflare"),
        ("- HTTP status: 403", "- Cloudflare"),
        ("- HTTP status: 403", "- challenges.cloudflare.com"),
        ("- Cloudflare",),
    ],
)
def test_cloudflare_challenge_near_misses_remain_unknown_ui(
    challenge_lines: tuple[str, ...],
) -> None:
    raw_snapshot = "\n".join(("- Page URL: https://chatgpt.com/", *challenge_lines))

    assert orchestrator._stop_state(raw_snapshot) is None
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._doctor_snapshot(raw_snapshot)

    assert captured.value.code == "UNKNOWN_UI"


def test_successful_ask_emits_sanitized_result_and_hash_bound_private_artifacts(
    tmp_path: Path,
) -> None:
    root = private_root(tmp_path)
    request = private_request(root, "successful-request.txt")
    response = advice_text(summary="A unique response that must not reach stdout.")
    scenario = successful_scenario(tmp_path / "success.json", response=response)
    process = subprocess.run(
        [
            sys.executable,
            str(ORCHESTRATOR_PATH),
            "ask",
            "--private-root",
            str(root),
            "--request-file",
            str(request),
            "--importance",
            "ordinary",
            "--fake-scenario",
            str(scenario),
        ],
        cwd=REPOSITORY_ROOT,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert process.returncode == 0
    assert process.stderr == ""
    assert process.stdout.count("\n") == 1
    assert REQUEST_TEXT not in process.stdout
    assert response not in process.stdout
    result = json.loads(process.stdout)
    assert result["status"] == "ADVICE_CAPTURED"
    assert result["mode"] == "LOCAL_FIXTURE"
    assert result["advice_type"] == "PRO_ADVICE_V1"
    assert result["authority"] == "UNAPPROVED_ADVICE"
    assert "diagnostic_code" not in result
    assert "diagnostic_detail_code" not in result
    assert "diagnostic_context_code" not in result
    assert "diagnostic_context_detail_code" not in result
    assert "diagnostic_context_shape_code" not in result
    assert "diagnostic_fallback_code" not in result
    assert "diagnostic_fallback_entry_code" not in result

    run_id = result["run_id"]
    run_dir = root / "chatgpt-pro-runs" / run_id
    record_path = run_dir / "run-record.v1.jsonl"
    state_path = run_dir / "orchestration-state.v1.json"
    proposal_path = run_dir / "unapproved-proposal.md"
    assert not (root / "chatgpt-pro" / f"{run_id}.env").exists()
    assert not list(run_dir.glob(".fake-*"))
    assert_private_tree(root)

    record_text = record_path.read_text(encoding="utf-8")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    proposal = proposal_path.read_text(encoding="utf-8")
    count, final_hash = workflow._verify_events(record_text.splitlines(), run_id)
    assert count >= 10
    assert final_hash == json.loads(record_text.splitlines()[-1])["event_sha256"]
    compiled = orchestrator._compiled_prompt(
        REQUEST_TEXT, importance="ordinary", gap=None
    )
    assert state["prompt_sha256"] == hashlib.sha256(compiled.encode()).hexdigest()
    assert state["status"] == "ADVICE_CAPTURED"
    assert state["mode"] == "LOCAL_FIXTURE"
    assert state["submission_attempted"] is True
    assert state["advice_type"] == "PRO_ADVICE_V1"
    assert "diagnostic_code" not in state
    assert "diagnostic_code" not in record_text
    assert "diagnostic_code" not in proposal
    assert "diagnostic_detail_code" not in state
    assert "diagnostic_detail_code" not in record_text
    assert "diagnostic_detail_code" not in proposal
    assert "diagnostic_context_code" not in state
    assert "diagnostic_context_code" not in record_text
    assert "diagnostic_context_code" not in proposal
    assert "diagnostic_context_detail_code" not in state
    assert "diagnostic_context_detail_code" not in record_text
    assert "diagnostic_context_detail_code" not in proposal
    assert "diagnostic_context_shape_code" not in state
    assert "diagnostic_context_shape_code" not in record_text
    assert "diagnostic_context_shape_code" not in proposal
    assert "diagnostic_fallback_code" not in state
    assert "diagnostic_fallback_code" not in record_text
    assert "diagnostic_fallback_code" not in proposal
    assert "diagnostic_fallback_entry_code" not in state
    assert "diagnostic_fallback_entry_code" not in record_text
    assert "diagnostic_fallback_entry_code" not in proposal
    assert REQUEST_TEXT not in record_text
    assert REQUEST_TEXT not in proposal
    assert "UNAPPROVED_PROPOSAL" in proposal
    assert "cannot authorize" in proposal
    assert "UNAPPROVED_ADVICE" in proposal

    status_result = orchestrator.status(private_root=root, run_id=run_id)
    assert "diagnostic_code" not in status_result
    assert "diagnostic_detail_code" not in status_result
    assert "diagnostic_context_code" not in status_result
    assert "diagnostic_context_detail_code" not in status_result
    assert "diagnostic_context_shape_code" not in status_result
    assert "diagnostic_fallback_code" not in status_result
    assert "diagnostic_fallback_entry_code" not in status_result
    resume_code, terminal_result = orchestrator.resume(
        private_root=root,
        run_id=run_id,
        fake_scenario=scenario,
    )
    assert resume_code == 0
    assert terminal_result["status"] == "ADVICE_CAPTURED"
    assert "diagnostic_code" not in terminal_result
    assert "diagnostic_detail_code" not in terminal_result
    assert "diagnostic_context_code" not in terminal_result
    assert "diagnostic_context_detail_code" not in terminal_result
    assert "diagnostic_context_shape_code" not in terminal_result
    assert "diagnostic_fallback_code" not in terminal_result
    assert "diagnostic_fallback_entry_code" not in terminal_result


def test_cli_ask_without_request_file_reads_stdin_into_private_artifact(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".secrets"
    scenario = successful_scenario(
        tmp_path / "stdin-success.json", response=advice_text()
    )
    process = subprocess.run(
        [
            sys.executable,
            str(ORCHESTRATOR_PATH),
            "ask",
            "--private-root",
            str(root),
            "--importance",
            "ordinary",
            "--fake-scenario",
            str(scenario),
        ],
        cwd=REPOSITORY_ROOT,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
        input=REQUEST_TEXT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert process.returncode == 0
    assert process.stderr == ""
    assert REQUEST_TEXT not in process.stdout
    assert json.loads(process.stdout)["status"] == "ADVICE_CAPTURED"
    staged = list((root / "chatgpt-pro-requests").glob("stdin-request.*.txt"))
    assert len(staged) == 1
    assert staged[0].read_text(encoding="utf-8") == REQUEST_TEXT
    assert stat.S_IMODE(staged[0].stat().st_mode) == 0o600
    assert_private_tree(root)


@pytest.mark.parametrize(
    ("importance", "expected_code", "expected_status", "expected_next_action"),
    [
        (
            "ordinary",
            0,
            "PRO_UNAVAILABLE_FALLBACK",
            "CONTINUE_CANONICAL_LOCAL_ONLY",
        ),
        ("gated", 4, "BLOCKED_PRO_REQUIRED", "STOP"),
    ],
)
def test_transport_failure_obeys_importance_boundary(
    tmp_path: Path,
    importance: str,
    expected_code: int,
    expected_status: str,
    expected_next_action: str,
) -> None:
    root = private_root(tmp_path)
    request = private_request(root, f"{importance}.txt")
    scenario = write_scenario(
        tmp_path / f"{importance}-transport-error.json",
        response=advice_text(),
        transcript=combined_transcript(),
        expected_tools=EXPECTED_TOOLS,
        transport_error="MCP_TIMEOUT",
    )

    exit_code, result = ask_fixture(
        root,
        request,
        scenario,
        importance=importance,
    )

    assert exit_code == expected_code
    assert result["status"] == expected_status
    assert result["reason_code"] == "MCP_TIMEOUT"
    assert result["next_action"] == expected_next_action
    state = json.loads(
        (
            root / "chatgpt-pro-runs" / result["run_id"] / "orchestration-state.v1.json"
        ).read_text(encoding="utf-8")
    )
    assert state["status"] == expected_status
    assert state["importance"] == importance
    assert not (root / "chatgpt-pro" / f"{result['run_id']}.env").exists()


@pytest.mark.parametrize(
    "reason_code",
    [
        *sorted(orchestrator.ADVANCED_PRE_SUBMISSION_DIAGNOSTIC_CODES),
        "EFFORT_OPTIONS_AMBIGUOUS",
        "SELECTOR_AMBIGUITY",
        "MODEL_OPTIONS_AMBIGUOUS",
        "ORIGIN_MISMATCH",
        "UNKNOWN_UI",
    ],
)
def test_pre_submission_ui_classifier_maps_every_eligible_code(
    reason_code: str,
) -> None:
    assert orchestrator.PRE_SUBMISSION_UI_UNAVAILABLE_CODES == {
        *orchestrator.ADVANCED_PRE_SUBMISSION_DIAGNOSTIC_CODES,
        "EFFORT_OPTIONS_AMBIGUOUS",
        "SELECTOR_AMBIGUITY",
        "MODEL_OPTIONS_AMBIGUOUS",
        "ORIGIN_MISMATCH",
        "UNKNOWN_UI",
    }
    source = orchestrator.OrchestrationRefusal(reason_code)

    classified = orchestrator._classify_pre_submission_ui_refusal(
        source, phase="advanced_summary"
    )

    assert type(classified) is orchestrator.LiveUiUnavailable
    assert classified.code == reason_code
    assert classified.phase == "advanced_summary"


def test_pre_submission_phase_vocabulary_and_settle_bounds_are_closed() -> None:
    assert orchestrator.PRE_SUBMISSION_PHASES == {
        "landing",
        "pro_menu",
        "advanced_summary",
        "closed_landing",
        "typed_composer",
        "send_control",
    }
    assert orchestrator.PRE_SUBMISSION_SETTLE_SECONDS == 5
    assert orchestrator.PRE_SUBMISSION_SETTLE_ADDITIONAL_OBSERVATIONS == 12


@pytest.mark.parametrize(
    ("reason_code", "phase"),
    [
        pytest.param("ADVANCED_PRO_BUTTON_INVALID", "pro_menu", id="pro-button"),
        pytest.param(
            "ADVANCED_EXPAND_CONTROL_INVALID", "pro_menu", id="expand-control"
        ),
        pytest.param("ADVANCED_MENU_STATE_MIXED", "pro_menu", id="mixed"),
        pytest.param(
            "ADVANCED_MODEL_EVIDENCE_MISSING",
            "advanced_summary",
            id="model-missing",
        ),
        pytest.param(
            "ADVANCED_MODEL_EVIDENCE_CONFLICT",
            "advanced_summary",
            id="model-conflict",
        ),
        pytest.param(
            "ADVANCED_EFFORT_EVIDENCE_MISSING",
            "advanced_summary",
            id="effort-missing",
        ),
        pytest.param(
            "ADVANCED_EFFORT_EVIDENCE_CONFLICT",
            "advanced_summary",
            id="effort-conflict",
        ),
        pytest.param("ADVANCED_MENU_UNRECOGNIZED", "pro_menu", id="unrecognized"),
        pytest.param("MCP_TYPE_REF_STALE", "typed_composer", id="typed-stale-ref"),
        pytest.param(
            "MCP_TYPE_ELEMENT_NOT_EDITABLE",
            "typed_composer",
            id="typed-noneditable",
        ),
        pytest.param(
            "MCP_TYPE_FILL_TIMEOUT", "typed_composer", id="typed-fill-timeout"
        ),
    ],
)
@pytest.mark.parametrize(
    ("importance", "expected_exit", "expected_status", "importance_action"),
    [
        pytest.param(
            "ordinary",
            0,
            "PRO_UNAVAILABLE_FALLBACK",
            "CONTINUE_CANONICAL_LOCAL_ONLY",
            id="ordinary",
        ),
        pytest.param("gated", 4, "BLOCKED_PRO_REQUIRED", "STOP", id="gated"),
    ],
)
def test_closed_diagnostic_is_hash_bound_in_state_event_result_and_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason_code: str,
    phase: str,
    importance: str,
    expected_exit: int,
    expected_status: str,
    importance_action: str,
) -> None:
    root = private_root(tmp_path)
    expected_action = (
        "STOP"
        if reason_code in orchestrator.TYPED_COMPOSER_MCP_DIAGNOSTIC_CODES
        else importance_action
    )
    exit_code, result, transport = prepare_live_diagnostic_run(
        root,
        monkeypatch,
        reason_code=reason_code,
        phase=phase,
        importance=importance,
    )

    assert exit_code == expected_exit
    assert result == {
        "status": expected_status,
        "story_id": "ST-0101",
        "mode": "LIVE",
        "browser": "edge",
        "run_id": result["run_id"],
        "reason_code": reason_code,
        "submission_attempted": False,
        "next_action": expected_action,
        "phase": phase,
    }
    assert transport.calls == []
    assert transport.closed is True
    assert not transport.secrets_file.exists()

    run_dir = root / "chatgpt-pro-runs" / result["run_id"]
    state_path = run_dir / "orchestration-state.v1.json"
    record_path = run_dir / "run-record.v1.jsonl"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    record_text = record_path.read_text(encoding="utf-8")
    events = [json.loads(line) for line in record_text.splitlines()]
    final_event = events[-1]
    assert state["reason_code"] == reason_code
    assert state["phase"] == phase
    assert state["submission_attempted"] is False
    assert state["status"] == expected_status
    assert state["next_action"] == expected_action
    assert final_event["event_type"] == "PRO_UNAVAILABLE"
    assert final_event["payload"] == {
        "status": expected_status,
        "importance": importance,
        "reason_code": reason_code,
        "fallback_scope": expected_action,
        "submission_attempted": False,
        "phase": phase,
        "state_sha256": hashlib.sha256(orchestrator._canonical_json(state)).hexdigest(),
    }
    assert workflow._verify_events(record_text.splitlines(), result["run_id"])[
        0
    ] == len(events)

    before = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.iterdir()
        if path.is_file()
    }
    verified = orchestrator.status(private_root=root, run_id=result["run_id"])
    after = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.iterdir()
        if path.is_file()
    }
    assert verified == {
        "status": expected_status,
        "story_id": "ST-0101",
        "mode": "LIVE",
        "browser": "edge",
        "run_id": result["run_id"],
        "importance": importance,
        "submission_attempted": False,
        "advice_type": None,
        "next_action": expected_action,
        "record_verified": True,
        "phase": phase,
        "reason_code": reason_code,
    }
    assert before == after

    diagnostic_surfaces = json.dumps(
        {
            "result": result,
            "state": state,
            "record": events,
            "status": verified,
        },
        sort_keys=True,
    )
    for forbidden in (
        "RAW_PROMPT_SENTINEL_CLOSED_DIAGNOSTIC",
        "RAW_RESPONSE_SENTINEL_CLOSED_DIAGNOSTIC",
        "SNAPSHOT_LABEL_SENTINEL_CLOSED_DIAGNOSTIC",
        "ROLE_SENTINEL_CLOSED_DIAGNOSTIC",
        "e987654",
        "COUNT_SENTINEL_77",
        "VALUE_SENTINEL_CLOSED_DIAGNOSTIC",
        "SNAPSHOT_HASH_SENTINEL_CLOSED_DIAGNOSTIC",
        "SIDEBAR_SENTINEL_CLOSED_DIAGNOSTIC",
        "ACCOUNT_SENTINEL_CLOSED_DIAGNOSTIC",
        "PROFILE_SENTINEL_CLOSED_DIAGNOSTIC",
        "https://unrelated.invalid/closed-diagnostic",
        MCP_STALE_REF_SENTINEL,
        MCP_CALL_LOG_SENTINEL,
    ):
        assert forbidden not in diagnostic_surfaces
    assert not any(
        event["event_type"] == "SUBMISSION_INTENT_RECORDED" for event in events
    )
    assert not (run_dir / "pending-transcript.v1.json").exists()
    assert not (run_dir / "unapproved-proposal.md").exists()


def test_closed_diagnostics_never_become_manual_import_reasons() -> None:
    assert orchestrator.ADVANCED_PRE_SUBMISSION_DIAGNOSTIC_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_TERMINAL_REASON_CODES
    )
    assert orchestrator.ADVANCED_PRE_SUBMISSION_DIAGNOSTIC_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_WAIT_CONTINUES_REASON_CODES
    )
    assert orchestrator.TYPED_COMPOSER_MCP_DIAGNOSTIC_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_TERMINAL_REASON_CODES
    )
    assert orchestrator.TYPED_COMPOSER_MCP_DIAGNOSTIC_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_WAIT_CONTINUES_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_RECOVERY_DIAGNOSTIC_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_TERMINAL_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_RECOVERY_DIAGNOSTIC_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_WAIT_CONTINUES_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_HEADING_DETAIL_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_TERMINAL_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_HEADING_DETAIL_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_WAIT_CONTINUES_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_ACTION_DETAIL_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_TERMINAL_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_ACTION_DETAIL_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_WAIT_CONTINUES_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_PRECONTENT_CONTEXT_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_TERMINAL_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_PRECONTENT_CONTEXT_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_WAIT_CONTINUES_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_PRECONTENT_CONTEXT_DETAIL_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_TERMINAL_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_PRECONTENT_CONTEXT_DETAIL_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_WAIT_CONTINUES_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_PRECONTENT_CONTEXT_SHAPE_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_TERMINAL_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_PRECONTENT_CONTEXT_SHAPE_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_WAIT_CONTINUES_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_REF_FREE_FALLBACK_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_TERMINAL_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_REF_FREE_FALLBACK_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_WAIT_CONTINUES_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_REF_FREE_FALLBACK_ENTRY_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_TERMINAL_REASON_CODES
    )
    assert orchestrator.BOUND_RESPONSE_REF_FREE_FALLBACK_ENTRY_CODES.isdisjoint(
        orchestrator.MANUAL_IMPORT_WAIT_CONTINUES_REASON_CODES
    )


@pytest.mark.parametrize(
    "reason_code",
    [
        "advanced_model_evidence_missing",
        " ADVANCED_MODEL_EVIDENCE_MISSING ",
        "Advanced_Unknown_Boundary",
    ],
)
def test_reserved_advanced_reason_variants_cannot_be_recorded(
    reason_code: str,
) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._record_unavailable(
            prepared={},
            state={},
            reason_code=reason_code,
            phase="advanced_summary",
        )

    assert captured.value.code == "STATE_INVALID"


def test_real_classifier_persists_no_raw_browser_material_or_submission_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    write_setup_state(root)
    request = private_request(
        root,
        "raw-browser-material-diagnostic.txt",
        "RAW_PROMPT_SENTINEL_CLOSED_DIAGNOSTIC",
    )
    landing_snapshot = "\n".join(
        (
            "- Page URL: https://chatgpt.com/",
            '- button "Pro" [ref=e1]',
            '- textbox "Chat with ChatGPT" [ref=e2]',
        )
    )
    raw_snapshot = "\n".join(
        (
            "- Page URL: https://chatgpt.com/",
            '- button "Pro" [ref=e3]',
            '- menu "Pro" [ref=e4]',
            '- navigation "SIDEBAR_SENTINEL_CLOSED_DIAGNOSTIC" [ref=e80]:',
            '  - text: "SNAPSHOT_LABEL_SENTINEL_CLOSED_DIAGNOSTIC"',
            '  - statictext: "RAW_RESPONSE_SENTINEL_CLOSED_DIAGNOSTIC"',
            '  - link "https://unrelated.invalid/closed-diagnostic" [ref=e987654]',
            '- complementary "ACCOUNT_SENTINEL_CLOSED_DIAGNOSTIC" [ref=e81]:',
            '  - description "PROFILE_SENTINEL_CLOSED_DIAGNOSTIC"',
            '- toolbar "ROLE_SENTINEL_CLOSED_DIAGNOSTIC" [ref=e82]:',
            '  - text "COUNT_SENTINEL_77"',
            '  - text "VALUE_SENTINEL_CLOSED_DIAGNOSTIC"',
            '  - text "SNAPSHOT_HASH_SENTINEL_CLOSED_DIAGNOSTIC"',
        )
    )
    transports: list[ScriptedLiveTransport] = []

    def scripted_transport(
        _wrapper: Path, secrets_file: Path, browser: str
    ) -> ScriptedLiveTransport:
        assert browser == "edge"
        transport = ScriptedLiveTransport(
            [
                landing_snapshot,
                *[
                    raw_snapshot
                    for _ in range(
                        orchestrator.PRE_SUBMISSION_SETTLE_ADDITIONAL_OBSERVATIONS + 1
                    )
                ],
            ],
            secrets_file,
        )
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", scripted_transport)

    exit_code, result = orchestrator.ask(
        private_root=root,
        request_file=request,
        importance="ordinary",
        fake_scenario=None,
        parent_run_id=None,
        gap_file=None,
        interactive_auth_wait_seconds=0,
    )

    assert exit_code == 0
    assert result["reason_code"] == "ADVANCED_MENU_UNRECOGNIZED"
    assert result["phase"] == "pro_menu"
    assert result["submission_attempted"] is False
    assert len(transports) == 1
    transport = transports[0]
    assert transport.closed is True
    assert transport.snapshots == []
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == 12
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker"]
    assert not any(tool == "browser_type" for tool, _ in transport.calls)
    assert not any(
        tool == "browser_click" and arguments.get("element") == "send prompt"
        for tool, arguments in transport.calls
    )

    run_dir = root / "chatgpt-pro-runs" / result["run_id"]
    state = json.loads(
        (run_dir / "orchestration-state.v1.json").read_text(encoding="utf-8")
    )
    record_text = (run_dir / "run-record.v1.jsonl").read_text(encoding="utf-8")
    verified = orchestrator.status(private_root=root, run_id=result["run_id"])
    diagnostic_surfaces = json.dumps(
        {"result": result, "state": state, "record": record_text, "status": verified},
        sort_keys=True,
    )
    for forbidden in (
        "RAW_PROMPT_SENTINEL_CLOSED_DIAGNOSTIC",
        "RAW_RESPONSE_SENTINEL_CLOSED_DIAGNOSTIC",
        "SNAPSHOT_LABEL_SENTINEL_CLOSED_DIAGNOSTIC",
        "ROLE_SENTINEL_CLOSED_DIAGNOSTIC",
        "e987654",
        "COUNT_SENTINEL_77",
        "VALUE_SENTINEL_CLOSED_DIAGNOSTIC",
        "SNAPSHOT_HASH_SENTINEL_CLOSED_DIAGNOSTIC",
        "SIDEBAR_SENTINEL_CLOSED_DIAGNOSTIC",
        "ACCOUNT_SENTINEL_CLOSED_DIAGNOSTIC",
        "PROFILE_SENTINEL_CLOSED_DIAGNOSTIC",
        "https://unrelated.invalid/closed-diagnostic",
    ):
        assert forbidden not in diagnostic_surfaces
    assert "SUBMISSION_INTENT_RECORDED" not in record_text
    assert not (run_dir / "pending-transcript.v1.json").exists()
    assert not (run_dir / "unapproved-proposal.md").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "dynamic-both",
        "unknown-both",
        "event-disagreement",
        "state-reason-missing",
        "wrong-case-event-state-reason-missing",
        "event-reason-missing",
        "event-dynamic-field",
        "phase-mismatch",
        "action-mismatch",
    ],
)
@pytest.mark.parametrize(
    ("reason_code", "phase"),
    [
        pytest.param(
            "ADVANCED_MODEL_EVIDENCE_MISSING",
            "advanced_summary",
            id="current-diagnostic",
        ),
        pytest.param(
            "ADVANCED_MENU_STATE_MIXED",
            "pro_menu",
            id="predecessor-mixed-compatibility",
        ),
        pytest.param(
            "MCP_TYPE_REF_STALE",
            "typed_composer",
            id="typed-composer-diagnostic",
        ),
    ],
)
def test_status_rejects_semantically_invalid_hash_valid_diagnostic_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    reason_code: str,
    phase: str,
) -> None:
    root = private_root(tmp_path)
    _exit_code, result, _transport = prepare_live_diagnostic_run(
        root,
        monkeypatch,
        reason_code=reason_code,
        phase=phase,
        importance="ordinary",
    )
    run_dir = root / "chatgpt-pro-runs" / result["run_id"]
    typed_diagnostic = reason_code in orchestrator.TYPED_COMPOSER_MCP_DIAGNOSTIC_CODES
    dynamic_reason = f"{reason_code}_COUNT_2"
    unknown_reason = (
        "MCP_TYPE_UNKNOWN_BOUNDARY" if typed_diagnostic else "ADVANCED_UNKNOWN_BOUNDARY"
    )
    disagreeing_reason = (
        "MCP_TYPE_FILL_TIMEOUT"
        if typed_diagnostic
        else "ADVANCED_EFFORT_EVIDENCE_MISSING"
    )
    invalid_phase = "advanced_summary" if typed_diagnostic else "typed_composer"

    def mutate_state(state: dict[str, Any]) -> None:
        if mutation == "dynamic-both":
            state["reason_code"] = dynamic_reason
        elif mutation == "unknown-both":
            state["reason_code"] = unknown_reason
        elif mutation in {
            "state-reason-missing",
            "wrong-case-event-state-reason-missing",
        }:
            state.pop("reason_code")
        elif mutation == "phase-mismatch":
            state["phase"] = invalid_phase
        elif mutation == "action-mismatch":
            state["next_action"] = (
                "CONTINUE_CANONICAL_LOCAL_ONLY" if typed_diagnostic else "STOP"
            )

    def mutate_event(event: dict[str, Any]) -> None:
        if mutation == "dynamic-both":
            event["payload"]["reason_code"] = dynamic_reason
        elif mutation == "unknown-both":
            event["payload"]["reason_code"] = unknown_reason
        elif mutation == "event-disagreement":
            event["payload"]["reason_code"] = disagreeing_reason
        elif mutation == "wrong-case-event-state-reason-missing":
            event["payload"]["reason_code"] = reason_code.lower()
        elif mutation == "event-reason-missing":
            event["payload"].pop("reason_code")
        elif mutation == "event-dynamic-field":
            event["payload"]["raw_label"] = "Model secret sentinel"
        elif mutation == "phase-mismatch":
            event["payload"]["phase"] = invalid_phase
        elif mutation == "action-mismatch":
            event["payload"]["fallback_scope"] = (
                "CONTINUE_CANONICAL_LOCAL_ONLY" if typed_diagnostic else "STOP"
            )

    rewrite_hash_bound_terminal(
        run_dir,
        mutate_state=mutate_state,
        mutate_event=mutate_event,
    )
    before = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.iterdir()
        if path.is_file()
    }

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.status(private_root=root, run_id=result["run_id"])

    after = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.iterdir()
        if path.is_file()
    }
    assert captured.value.code == "STATE_INVALID"
    assert before == after


@pytest.mark.parametrize(
    "reason_code",
    [
        "RESPONSE_SELECTOR_AMBIGUITY",
        "MCP_TOOL_NOT_ALLOWED",
        "RAW_PROMPT_TOOL_ARGUMENT",
        "CONTRACT_INVALID",
    ],
)
def test_pre_submission_ui_classifier_rethrows_ineligible_invariants(
    reason_code: str,
) -> None:
    source = orchestrator.OrchestrationRefusal(reason_code)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._classify_pre_submission_ui_refusal(source)

    assert captured.value is source
    assert type(captured.value) is orchestrator.OrchestrationRefusal


@pytest.mark.parametrize(
    ("importance", "expected_code", "expected_status", "expected_next_action"),
    [
        (
            "ordinary",
            0,
            "PRO_UNAVAILABLE_FALLBACK",
            "CONTINUE_CANONICAL_LOCAL_ONLY",
        ),
        ("gated", 4, "BLOCKED_PRO_REQUIRED", "STOP"),
    ],
)
def test_live_no_model_picker_records_pre_submission_unavailability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    importance: str,
    expected_code: int,
    expected_status: str,
    expected_next_action: str,
) -> None:
    root = private_root(tmp_path)
    write_setup_state(root)
    request = private_request(root, f"live-no-model-picker-{importance}.txt")
    raw_snapshot = "\n".join(
        (
            "- Page URL: https://chatgpt.com/",
            '- textbox "Ask anything" [ref=e1]',
            '- button "Send" [ref=e2]',
        )
    )
    transports: list[ScriptedLiveTransport] = []

    def scripted_transport(
        _wrapper: Path, secrets_file: Path, browser: str
    ) -> ScriptedLiveTransport:
        assert browser == "edge"
        assert secrets_file.is_file()
        transport = ScriptedLiveTransport([raw_snapshot, raw_snapshot], secrets_file)
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", scripted_transport)

    exit_code = invoke_orchestrator_main(
        [
            "ask",
            "--private-root",
            str(root),
            "--request-file",
            str(request),
            "--importance",
            importance,
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == expected_code
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert REQUEST_TEXT not in captured.out
    assert raw_snapshot not in captured.out
    result = json.loads(captured.out)
    assert result["status"] == expected_status
    assert result["mode"] == "LIVE"
    assert result["reason_code"] == "SELECTOR_AMBIGUITY"
    assert result["phase"] == "landing"
    assert result["submission_attempted"] is False
    assert "resubmitted" not in result
    assert result["next_action"] == expected_next_action
    run_id = result["run_id"]
    assert workflow.RUN_ID_PATTERN.fullmatch(run_id)

    assert len(transports) == 1
    transport = transports[0]
    assert transport.closed is True
    assert transport.snapshots == []
    assert [tool for tool, _arguments in transport.calls] == [
        "browser_navigate",
        "browser_snapshot",
        "browser_wait_for",
        "browser_snapshot",
    ]
    assert transport.calls[2][1] == {"time": 5}
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)
    assert not any(
        tool == "browser_click" and arguments.get("element") == "send"
        for tool, arguments in transport.calls
    )
    assert not transport.secrets_file.exists()
    assert not list((root / "chatgpt-pro").glob("*.env"))

    run_dir = root / "chatgpt-pro-runs" / run_id
    state = json.loads(
        (run_dir / "orchestration-state.v1.json").read_text(encoding="utf-8")
    )
    assert state["status"] == expected_status
    assert state["phase"] == "landing"
    assert state["submission_attempted"] is False
    assert state["next_action"] == expected_next_action
    record_text = (run_dir / "run-record.v1.jsonl").read_text(encoding="utf-8")
    lines = record_text.splitlines()
    event_count, final_hash = workflow._verify_events(lines, run_id)
    final_event = json.loads(lines[-1])
    assert event_count == len(lines)
    assert final_hash == final_event["event_sha256"]
    assert final_event["event_type"] == "PRO_UNAVAILABLE"
    assert final_event["payload"]["reason_code"] == "SELECTOR_AMBIGUITY"
    assert final_event["payload"]["phase"] == "landing"
    assert final_event["payload"]["submission_attempted"] is False
    assert set(final_event["payload"]) == {
        "fallback_scope",
        "importance",
        "phase",
        "reason_code",
        "state_sha256",
        "status",
        "submission_attempted",
    }
    assert "resubmitted" not in final_event["payload"]
    assert REQUEST_TEXT not in record_text
    verified = orchestrator.status(private_root=root, run_id=run_id)
    assert verified["record_verified"] is True
    assert verified["phase"] == "landing"
    assert verified["submission_attempted"] is False
    assert "reason_code" not in verified
    assert "reason_code" not in state


def test_live_transport_startup_failure_records_landing_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    write_setup_state(root)
    request = private_request(root, "live-transport-startup-failure.txt")

    def unavailable_transport(_wrapper: Path, secrets_file: Path, browser: str) -> None:
        assert browser == "edge"
        assert secrets_file.is_file()
        raise orchestrator.TransportUnavailable("MCP_TIMEOUT")

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", unavailable_transport)

    exit_code, result = orchestrator.ask(
        private_root=root,
        request_file=request,
        importance="ordinary",
        fake_scenario=None,
        parent_run_id=None,
        gap_file=None,
    )

    assert exit_code == 0
    assert result["reason_code"] == "MCP_TIMEOUT"
    assert result["phase"] == "landing"
    assert result["submission_attempted"] is False
    run_id = result["run_id"]
    run_dir = root / "chatgpt-pro-runs" / run_id
    state = json.loads(
        (run_dir / "orchestration-state.v1.json").read_text(encoding="utf-8")
    )
    assert state["phase"] == "landing"
    assert state["submission_attempted"] is False
    final_event = json.loads(
        (run_dir / "run-record.v1.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    )
    assert final_event["event_type"] == "PRO_UNAVAILABLE"
    assert final_event["payload"]["reason_code"] == "MCP_TIMEOUT"
    assert final_event["payload"]["phase"] == "landing"
    assert final_event["payload"]["submission_attempted"] is False
    assert orchestrator.status(private_root=root, run_id=run_id)["phase"] == "landing"
    assert not list((root / "chatgpt-pro").glob("*.env"))


@pytest.mark.parametrize("invalid_phase", [[], {}])
def test_status_sanitizes_unhashable_phase_schema_values(
    tmp_path: Path,
    invalid_phase: object,
) -> None:
    root = private_root(tmp_path)
    request = private_request(root, "invalid-phase-state.txt")
    scenario = successful_scenario(tmp_path / "invalid-phase-state.json")
    _, asked = ask_fixture(root, request, scenario)
    state_path = (
        root / "chatgpt-pro-runs" / asked["run_id"] / "orchestration-state.v1.json"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["phase"] = invalid_phase
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.status(private_root=root, run_id=asked["run_id"])

    assert captured.value.code == "STATE_INVALID"


def test_browser_type_mcp_diagnostic_allowlist_is_closed() -> None:
    assert orchestrator.TYPED_COMPOSER_MCP_DIAGNOSTIC_CODES == {
        "MCP_TYPE_REF_STALE",
        "MCP_TYPE_ELEMENT_NOT_EDITABLE",
        "MCP_TYPE_FILL_TIMEOUT",
    }
    assert orchestrator.CLOSED_PRE_SUBMISSION_DIAGNOSTIC_CODES == {
        *orchestrator.ADVANCED_PRE_SUBMISSION_DIAGNOSTIC_CODES,
        *orchestrator.TYPED_COMPOSER_MCP_DIAGNOSTIC_CODES,
    }


@pytest.mark.parametrize(
    ("text", "reason_code"),
    [
        pytest.param(MCP_STALE_REF_ERROR, "MCP_TYPE_REF_STALE", id="stale-ref"),
        pytest.param(
            MCP_NONEDITABLE_ERROR,
            "MCP_TYPE_ELEMENT_NOT_EDITABLE",
            id="noneditable-end-of-text",
        ),
        pytest.param(
            MCP_NONEDITABLE_ERROR + MCP_CALL_LOG_CONTINUATION,
            "MCP_TYPE_ELEMENT_NOT_EDITABLE",
            id="noneditable-call-log",
        ),
        pytest.param(
            MCP_FILL_TIMEOUT_ERROR,
            "MCP_TYPE_FILL_TIMEOUT",
            id="timeout-end-of-text",
        ),
        pytest.param(
            MCP_FILL_TIMEOUT_ERROR
            + "\nCall log:\n"
            + "  2 × waiting for locator('aria-ref=e778899')\n"
            + "    - locator resolved to hidden element\n",
            "MCP_TYPE_FILL_TIMEOUT",
            id="timeout-compressed-call-log",
        ),
    ],
)
def test_browser_type_mcp_classifier_accepts_only_pinned_signatures(
    text: str,
    reason_code: str,
) -> None:
    result = mcp_error_result(text)

    assert orchestrator._classify_browser_type_mcp_error(result) == reason_code
    assert result == mcp_error_result(text)


@pytest.mark.parametrize(
    "result",
    [
        pytest.param(None, id="not-a-mapping"),
        pytest.param({}, id="empty-mapping"),
        pytest.param(
            {"content": [{"type": "text", "text": MCP_STALE_REF_ERROR}]},
            id="is-error-missing",
        ),
        pytest.param(
            {
                "content": [{"type": "text", "text": MCP_STALE_REF_ERROR}],
                "isError": False,
            },
            id="is-error-false",
        ),
        pytest.param(
            {
                "content": [{"type": "text", "text": MCP_STALE_REF_ERROR}],
                "isError": 1,
            },
            id="is-error-integer",
        ),
        pytest.param(
            {
                "content": [{"type": "text", "text": MCP_STALE_REF_ERROR}],
                "isError": True,
                "structuredContent": {},
            },
            id="extra-result-field",
        ),
        pytest.param({"content": [], "isError": True}, id="zero-blocks"),
        pytest.param(
            {
                "content": ({"type": "text", "text": MCP_STALE_REF_ERROR},),
                "isError": True,
            },
            id="non-list-content",
        ),
        pytest.param(
            {
                "content": [
                    {"type": "text", "text": MCP_STALE_REF_ERROR},
                    {"type": "text", "text": MCP_STALE_REF_ERROR},
                ],
                "isError": True,
            },
            id="multiple-text-blocks",
        ),
        pytest.param(
            {
                "content": [
                    {"type": "text", "text": MCP_STALE_REF_ERROR},
                    {"type": "image", "data": "RAW_IMAGE_SENTINEL"},
                ],
                "isError": True,
            },
            id="text-and-non-text-blocks",
        ),
        pytest.param(
            {
                "content": [{"type": "image", "data": "RAW_IMAGE_SENTINEL"}],
                "isError": True,
            },
            id="non-text-block",
        ),
        pytest.param(
            {"content": [{"text": MCP_STALE_REF_ERROR}], "isError": True},
            id="block-type-missing",
        ),
        pytest.param(
            {
                "content": [{"type": "Text", "text": MCP_STALE_REF_ERROR}],
                "isError": True,
            },
            id="wrong-block-type-case",
        ),
        pytest.param(
            {
                "content": [{"type": "text", "text": MCP_STALE_REF_ERROR, "meta": {}}],
                "isError": True,
            },
            id="extra-block-field",
        ),
        pytest.param(
            {"content": [{"type": "text", "text": 7}], "isError": True},
            id="non-string-text",
        ),
        pytest.param(
            {"content": [{"type": "text", "text": ""}], "isError": True},
            id="empty-text",
        ),
        pytest.param(
            {
                "content": [
                    {"type": "text", "text": MCP_FILL_TIMEOUT_ERROR + "\ud800"}
                ],
                "isError": True,
            },
            id="invalid-utf8-surrogate",
        ),
    ],
)
def test_browser_type_mcp_classifier_rejects_malformed_result_shapes(
    result: object,
) -> None:
    assert orchestrator._classify_browser_type_mcp_error(result) is None


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(MCP_STALE_REF_ERROR.lower(), id="wrong-case"),
        pytest.param(" " + MCP_STALE_REF_ERROR, id="leading-padding"),
        pytest.param(MCP_STALE_REF_ERROR + " ", id="trailing-padding"),
        pytest.param(MCP_STALE_REF_ERROR + "\n", id="trailing-newline"),
        pytest.param(MCP_STALE_REF_ERROR.replace("\n", "\r\n"), id="crlf"),
        pytest.param(
            MCP_STALE_REF_ERROR.replace(MCP_STALE_REF_SENTINEL, "f12"),
            id="stale-ref-frame-only",
        ),
        pytest.param(
            MCP_STALE_REF_ERROR.replace(MCP_STALE_REF_SENTINEL, "e12x"),
            id="stale-ref-suffix",
        ),
        pytest.param(
            MCP_STALE_REF_ERROR.replace(MCP_STALE_REF_SENTINEL, "[e12]"),
            id="stale-ref-brackets",
        ),
        pytest.param(
            MCP_STALE_REF_ERROR.replace(MCP_STALE_REF_SENTINEL, "F12E987654"),
            id="stale-ref-uppercase",
        ),
        pytest.param(
            MCP_STALE_REF_ERROR + MCP_CALL_LOG_CONTINUATION,
            id="stale-ref-call-log-forbidden",
        ),
        pytest.param(MCP_NONEDITABLE_ERROR + ".", id="noneditable-punctuation"),
        pytest.param(MCP_NONEDITABLE_ERROR + " ", id="noneditable-padding"),
        pytest.param(
            MCP_NONEDITABLE_ERROR.replace("Element", "element"),
            id="noneditable-case",
        ),
        pytest.param(
            MCP_FILL_TIMEOUT_ERROR.replace("5000ms", "5001ms"),
            id="timeout-value",
        ),
        pytest.param(
            MCP_FILL_TIMEOUT_ERROR + "\ncall log:\n  - waiting\n",
            id="call-log-case",
        ),
        pytest.param(
            MCP_FILL_TIMEOUT_ERROR + "\nCall log:\n  - waiting",
            id="call-log-final-newline-missing",
        ),
        pytest.param(
            MCP_FILL_TIMEOUT_ERROR + "\nCall log:\n",
            id="call-log-body-missing",
        ),
        pytest.param(
            MCP_FILL_TIMEOUT_ERROR + "\nCall log:\n  - waiting\n\n",
            id="call-log-blank-line",
        ),
        pytest.param(
            MCP_FILL_TIMEOUT_ERROR + "\nCall log:\n - waiting\n",
            id="call-log-indent",
        ),
        pytest.param(
            MCP_FILL_TIMEOUT_ERROR + "\nCall log:\n  - waiting \n",
            id="call-log-trailing-space",
        ),
        pytest.param(
            MCP_FILL_TIMEOUT_ERROR + "\nCall log:\n  1 × waiting\n",
            id="call-log-impossible-one-repeat",
        ),
        pytest.param(
            MCP_FILL_TIMEOUT_ERROR + "\nCall log:\n  02 × waiting\n",
            id="call-log-zero-padded-repeat",
        ),
        pytest.param(
            MCP_FILL_TIMEOUT_ERROR + MCP_STALE_REF_ERROR,
            id="concatenated-timeout-and-stale-signatures",
        ),
        pytest.param(
            MCP_NONEDITABLE_ERROR + "\n" + MCP_FILL_TIMEOUT_ERROR,
            id="concatenated-fill-signatures",
        ),
    ],
)
def test_browser_type_mcp_classifier_rejects_hostile_near_and_multi_signatures(
    text: str,
) -> None:
    assert orchestrator._classify_browser_type_mcp_error(mcp_error_result(text)) is None


def test_browser_type_mcp_classifier_enforces_exact_utf8_size_boundary() -> None:
    line_prefix = MCP_FILL_TIMEOUT_ERROR + "\nCall log:\n  - "
    final_newline = "\n"
    padding_size = (
        workflow.MAX_TEXT_BYTES
        - len(line_prefix.encode("utf-8"))
        - len(final_newline.encode("utf-8"))
    )
    at_limit = line_prefix + ("x" * padding_size) + final_newline
    over_limit = line_prefix + ("x" * (padding_size + 1)) + final_newline

    assert len(at_limit.encode("utf-8")) == workflow.MAX_TEXT_BYTES
    assert len(over_limit.encode("utf-8")) == workflow.MAX_TEXT_BYTES + 1
    assert (
        orchestrator._classify_browser_type_mcp_error(mcp_error_result(at_limit))
        == "MCP_TYPE_FILL_TIMEOUT"
    )
    assert (
        orchestrator._classify_browser_type_mcp_error(mcp_error_result(over_limit))
        is None
    )
    transport = object.__new__(orchestrator.StdioMcpTransport)
    requests: list[tuple[str, dict[str, Any]]] = []

    def request(method: str, params: dict[str, Any]) -> dict[str, Any]:
        requests.append((method, params))
        return mcp_error_result(over_limit)

    transport._request = request
    arguments = {"text": "RAOS_CHATGPT_PROMPT"}
    with pytest.raises(orchestrator.TransportUnavailable) as captured:
        transport.call("browser_type", arguments)

    assert captured.value.code == "MCP_CALL_FAILED"
    assert str(captured.value) == "MCP_CALL_FAILED"
    assert requests == [
        (
            "tools/call",
            {"name": "browser_type", "arguments": arguments},
        )
    ]


def test_browser_type_mcp_classifier_rejects_ambiguous_match_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orchestrator,
        "_matches_pinned_mcp_fill_error",
        lambda _text, _prefix: True,
    )

    assert (
        orchestrator._classify_browser_type_mcp_error(
            mcp_error_result(MCP_STALE_REF_ERROR)
        )
        is None
    )


@pytest.mark.parametrize(
    ("tool", "result", "reason_code"),
    [
        pytest.param(
            "browser_type",
            mcp_error_result(MCP_STALE_REF_ERROR),
            "MCP_TYPE_REF_STALE",
            id="typed-stale-ref",
        ),
        pytest.param(
            "browser_type",
            mcp_error_result(MCP_NONEDITABLE_ERROR + MCP_CALL_LOG_CONTINUATION),
            "MCP_TYPE_ELEMENT_NOT_EDITABLE",
            id="typed-noneditable",
        ),
        pytest.param(
            "browser_type",
            mcp_error_result(MCP_FILL_TIMEOUT_ERROR),
            "MCP_TYPE_FILL_TIMEOUT",
            id="typed-timeout",
        ),
        pytest.param(
            "browser_type",
            {
                "content": [
                    {"type": "text", "text": MCP_STALE_REF_ERROR},
                    {"type": "text", "text": MCP_FILL_TIMEOUT_ERROR},
                ],
                "isError": True,
            },
            "MCP_CALL_FAILED",
            id="typed-multiple-blocks-generic",
        ),
        pytest.param(
            "browser_click",
            mcp_error_result(MCP_STALE_REF_ERROR),
            "MCP_CALL_FAILED",
            id="non-type-tool-generic",
        ),
    ],
)
def test_stdio_transport_sanitizes_browser_type_error_without_another_call(
    tool: str,
    result: dict[str, Any],
    reason_code: str,
) -> None:
    transport = object.__new__(orchestrator.StdioMcpTransport)
    requests: list[tuple[str, dict[str, Any]]] = []

    def request(method: str, params: dict[str, Any]) -> dict[str, Any]:
        requests.append((method, params))
        return result

    transport._request = request
    arguments = {"text": "RAOS_CHATGPT_PROMPT"} if tool == "browser_type" else {}

    with pytest.raises(orchestrator.TransportUnavailable) as captured:
        transport.call(tool, arguments)

    assert captured.value.code == reason_code
    assert str(captured.value) == reason_code
    assert requests == [
        ("tools/call", {"name": tool, "arguments": arguments}),
    ]
    exception_surface = f"{captured.value!s}\n{captured.value!r}"
    for forbidden in (
        MCP_STALE_REF_SENTINEL,
        MCP_CALL_LOG_SENTINEL,
        "locator.fill",
        "Call log:",
    ):
        assert forbidden not in exception_surface


@pytest.mark.parametrize(
    ("reason_code", "tool", "arguments"),
    [
        ("MCP_TOOL_NOT_ALLOWED", "browser_evaluate", {}),
        (
            "RAW_PROMPT_TOOL_ARGUMENT",
            "browser_type",
            {"text": REQUEST_TEXT},
        ),
    ],
)
def test_live_security_invariants_remain_hard_refusals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reason_code: str,
    tool: str,
    arguments: dict[str, Any],
) -> None:
    guard = object.__new__(orchestrator.StdioMcpTransport)
    with pytest.raises(orchestrator.OrchestrationRefusal) as guarded:
        guard.call(tool, arguments)
    assert guarded.value.code == reason_code

    root = private_root(tmp_path)
    write_setup_state(root)
    request = private_request(root, f"hard-refusal-{reason_code}.txt")
    transports: list[ScriptedLiveTransport] = []

    def scripted_transport(
        _wrapper: Path, secrets_file: Path, browser: str
    ) -> ScriptedLiveTransport:
        assert browser == "edge"
        transport = ScriptedLiveTransport([], secrets_file)
        transports.append(transport)
        return transport

    def refuse_live_capture(**_arguments: Any) -> None:
        raise orchestrator.OrchestrationRefusal(reason_code)

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", scripted_transport)
    monkeypatch.setattr(orchestrator, "_live_capture", refuse_live_capture)
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)

    exit_code = invoke_orchestrator_main(
        [
            "ask",
            "--private-root",
            str(root),
            "--request-file",
            str(request),
            "--importance",
            "ordinary",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.count("\n") == 1
    assert REQUEST_TEXT not in captured.err
    assert json.loads(captured.err) == {
        "reason_code": reason_code,
        "status": "REFUSED",
        "story_id": "ST-0101",
    }
    assert len(transports) == 1
    assert transports[0].closed is True
    assert not transports[0].secrets_file.exists()
    assert not list((root / "chatgpt-pro").glob("*.env"))
    run_dirs = list((root / "chatgpt-pro-runs").iterdir())
    assert len(run_dirs) == 1
    prepared_state = json.loads(
        (run_dirs[0] / "orchestration-state.v1.json").read_text(encoding="utf-8")
    )
    assert prepared_state["status"] == "PREPARED"
    assert prepared_state["submission_attempted"] is False
    events = [
        json.loads(line)
        for line in (run_dirs[0] / "run-record.v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert not any(event["event_type"] == "PRO_UNAVAILABLE" for event in events)


def test_live_contract_drift_remains_a_hard_refusal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = private_root(tmp_path)
    write_setup_state(root)
    request = private_request(root, "hard-refusal-contract.txt")
    original_load_contract = workflow._load_contract
    load_count = 0
    transports: list[ScriptedLiveTransport] = []

    def load_contract(path: Path) -> dict[str, Any]:
        nonlocal load_count
        load_count += 1
        if load_count == 1:
            return original_load_contract(path)
        raise workflow.WorkflowRefusal("CONTRACT_INVALID")

    def scripted_transport(
        _wrapper: Path, secrets_file: Path, browser: str
    ) -> ScriptedLiveTransport:
        assert browser == "edge"
        transport = ScriptedLiveTransport([], secrets_file)
        transports.append(transport)
        return transport

    monkeypatch.setattr(workflow, "_load_contract", load_contract)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", scripted_transport)
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)

    exit_code = invoke_orchestrator_main(
        [
            "ask",
            "--private-root",
            str(root),
            "--request-file",
            str(request),
            "--importance",
            "ordinary",
        ]
    )
    captured = capsys.readouterr()

    assert load_count == 2
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.count("\n") == 1
    assert json.loads(captured.err) == {
        "reason_code": "CONTRACT_INVALID",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }
    assert len(transports) == 1
    assert transports[0].calls == []
    assert transports[0].closed is True
    assert not transports[0].secrets_file.exists()
    assert not list((root / "chatgpt-pro").glob("*.env"))


@pytest.mark.parametrize(
    ("disconnect_after_tool", "expected_status"),
    [(5, "SUBMISSION_AMBIGUOUS"), (6, "WAITING")],
)
def test_resume_waits_without_resubmitting_after_ambiguous_or_lost_connection(
    tmp_path: Path,
    disconnect_after_tool: int,
    expected_status: str,
) -> None:
    root = private_root(tmp_path)
    request = private_request(root, f"{expected_status.lower()}.txt")
    initial_scenario = write_scenario(
        tmp_path / "disconnect.json",
        response=advice_text(),
        transcript=combined_transcript(),
        expected_tools=EXPECTED_TOOLS,
        disconnect_after_tool=disconnect_after_tool,
    )

    exit_code, initial = ask_fixture(root, request, initial_scenario)

    assert exit_code == 0
    assert initial["status"] == expected_status
    assert initial["resubmit_allowed"] is False
    run_id = initial["run_id"]
    run_dir = root / "chatgpt-pro-runs" / run_id
    assert (run_dir / "pending-transcript.v1.json").is_file()
    resume_scenario = write_scenario(
        tmp_path / "resume.json",
        response=advice_text(summary=f"Recovered from {expected_status}."),
        expected_tools=["browser_wait_for"],
    )

    resume_code, resumed = orchestrator.resume(
        private_root=root,
        run_id=run_id,
        fake_scenario=resume_scenario,
    )

    assert resume_code == 0
    assert resumed["status"] == "ADVICE_CAPTURED"
    assert resumed["resubmitted"] is False
    assert "diagnostic_code" not in initial
    assert "diagnostic_code" not in resumed
    assert "diagnostic_detail_code" not in initial
    assert "diagnostic_detail_code" not in resumed
    assert "diagnostic_context_code" not in initial
    assert "diagnostic_context_code" not in resumed
    assert "diagnostic_context_detail_code" not in initial
    assert "diagnostic_context_detail_code" not in resumed
    assert "diagnostic_context_shape_code" not in initial
    assert "diagnostic_context_shape_code" not in resumed
    assert "diagnostic_fallback_code" not in initial
    assert "diagnostic_fallback_code" not in resumed
    assert "diagnostic_fallback_entry_code" not in initial
    assert "diagnostic_fallback_entry_code" not in resumed
    assert not (run_dir / "pending-transcript.v1.json").exists()
    events = [
        json.loads(line)
        for line in (run_dir / "run-record.v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    reconnect = [event for event in events if event["event_type"] == "MCP_RECONNECTED"]
    assert len(reconnect) == 1
    assert reconnect[0]["payload"]["resubmitted"] is False
    assert not any(
        event.get("payload", {}).get("arguments", {}).get("text")
        for event in events
        if isinstance(event.get("payload"), dict)
    )
    assert "diagnostic_code" not in json.dumps(events, sort_keys=True)
    assert "diagnostic_detail_code" not in json.dumps(events, sort_keys=True)
    assert "diagnostic_context_code" not in json.dumps(events, sort_keys=True)
    assert "diagnostic_context_detail_code" not in json.dumps(events, sort_keys=True)
    assert "diagnostic_context_shape_code" not in json.dumps(events, sort_keys=True)
    assert "diagnostic_fallback_code" not in json.dumps(events, sort_keys=True)
    assert "diagnostic_fallback_entry_code" not in json.dumps(events, sort_keys=True)
    assert "diagnostic_code" not in (run_dir / "orchestration-state.v1.json").read_text(
        encoding="utf-8"
    )
    assert "diagnostic_detail_code" not in (
        run_dir / "orchestration-state.v1.json"
    ).read_text(encoding="utf-8")
    assert "diagnostic_context_code" not in (
        run_dir / "orchestration-state.v1.json"
    ).read_text(encoding="utf-8")
    assert "diagnostic_context_detail_code" not in (
        run_dir / "orchestration-state.v1.json"
    ).read_text(encoding="utf-8")
    assert "diagnostic_context_shape_code" not in (
        run_dir / "orchestration-state.v1.json"
    ).read_text(encoding="utf-8")
    assert "diagnostic_fallback_code" not in (
        run_dir / "orchestration-state.v1.json"
    ).read_text(encoding="utf-8")
    assert "diagnostic_fallback_entry_code" not in (
        run_dir / "orchestration-state.v1.json"
    ).read_text(encoding="utf-8")
    assert "diagnostic_code" not in (run_dir / "unapproved-proposal.md").read_text(
        encoding="utf-8"
    )
    assert "diagnostic_detail_code" not in (
        run_dir / "unapproved-proposal.md"
    ).read_text(encoding="utf-8")
    assert "diagnostic_context_code" not in (
        run_dir / "unapproved-proposal.md"
    ).read_text(encoding="utf-8")
    assert "diagnostic_context_detail_code" not in (
        run_dir / "unapproved-proposal.md"
    ).read_text(encoding="utf-8")
    assert "diagnostic_context_shape_code" not in (
        run_dir / "unapproved-proposal.md"
    ).read_text(encoding="utf-8")
    assert "diagnostic_fallback_code" not in (
        run_dir / "unapproved-proposal.md"
    ).read_text(encoding="utf-8")
    assert "diagnostic_fallback_entry_code" not in (
        run_dir / "unapproved-proposal.md"
    ).read_text(encoding="utf-8")
    assert "diagnostic_code" not in orchestrator.status(
        private_root=root,
        run_id=run_id,
    )
    assert "diagnostic_detail_code" not in orchestrator.status(
        private_root=root,
        run_id=run_id,
    )
    assert "diagnostic_context_code" not in orchestrator.status(
        private_root=root,
        run_id=run_id,
    )
    assert "diagnostic_context_detail_code" not in orchestrator.status(
        private_root=root,
        run_id=run_id,
    )
    assert "diagnostic_context_shape_code" not in orchestrator.status(
        private_root=root,
        run_id=run_id,
    )
    assert "diagnostic_fallback_code" not in orchestrator.status(
        private_root=root,
        run_id=run_id,
    )
    assert "diagnostic_fallback_entry_code" not in orchestrator.status(
        private_root=root,
        run_id=run_id,
    )


@pytest.mark.parametrize(
    "reason_code",
    ["RESPONSE_NOT_IDENTIFIABLE", "RESPONSE_SELECTOR_AMBIGUITY"],
)
@pytest.mark.parametrize(
    ("importance", "expected_exit", "expected_status", "expected_next_action"),
    [
        (
            "ordinary",
            0,
            "PRO_UNAVAILABLE_FALLBACK",
            "CONTINUE_CANONICAL_LOCAL_ONLY",
        ),
        ("gated", 4, "BLOCKED_PRO_REQUIRED", "STOP"),
    ],
)
def test_live_resume_response_parser_refusal_becomes_terminal_unavailability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason_code: str,
    importance: str,
    expected_exit: int,
    expected_status: str,
    expected_next_action: str,
) -> None:
    assert orchestrator.LIVE_RESUME_RESPONSE_UNAVAILABLE_CODES == {
        "RESPONSE_NOT_IDENTIFIABLE",
        "RESPONSE_SELECTOR_AMBIGUITY",
    }
    root = private_root(tmp_path)
    initial = prepare_live_waiting_run(
        root,
        monkeypatch,
        importance=importance,
        name=f"resume-{reason_code.lower()}-{importance}",
    )
    run_id = initial["run_id"]
    run_dir = root / "chatgpt-pro-runs" / run_id
    pending_path = run_dir / "pending-transcript.v1.json"
    pending_before = pending_path.read_bytes()
    transports: list[ScriptedLiveTransport] = []

    def scripted_transport(
        _wrapper: Path, secrets_file: Path, browser: str
    ) -> ScriptedLiveTransport:
        assert browser == "edge"
        assert secrets_file.is_file()
        transport = ScriptedLiveTransport(
            ["- Page URL: https://chatgpt.com/c/fake-live-resume-run"],
            secrets_file,
        )
        transports.append(transport)
        return transport

    def parser_refusal(
        _transcript: dict[str, Any], _snapshot: str
    ) -> tuple[dict[str, Any], str] | None:
        diagnostic_code = (
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
            if reason_code == "RESPONSE_NOT_IDENTIFIABLE"
            else "ADVANCED_RESPONSE_HEADING_INVALID"
        )
        raise orchestrator._AdvancedResponseParserRefusal(
            reason_code,
            diagnostic_code,
            (
                "ADVANCED_RESPONSE_HEADING_LABEL_CASE_INVALID"
                if reason_code == "RESPONSE_SELECTOR_AMBIGUITY"
                else "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
            ),
            (
                "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
                if reason_code == "RESPONSE_NOT_IDENTIFIABLE"
                else None
            ),
            (
                "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID"
                if reason_code == "RESPONSE_NOT_IDENTIFIABLE"
                else None
            ),
            (
                "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING"
                if reason_code == "RESPONSE_NOT_IDENTIFIABLE"
                else None
            ),
        )

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", scripted_transport)
    monkeypatch.setattr(
        orchestrator,
        "_wait_for_stable_response_snapshot",
        accept_snapshot_as_stable,
    )
    monkeypatch.setattr(orchestrator, "_complete_pending_transcript", parser_refusal)

    exit_code, result = orchestrator.resume(
        private_root=root,
        run_id=run_id,
        fake_scenario=None,
    )

    assert exit_code == expected_exit
    assert result == {
        "status": expected_status,
        "story_id": "ST-0101",
        "mode": "LIVE",
        "browser": "edge",
        "run_id": run_id,
        "reason_code": reason_code,
        "submission_attempted": True,
        "next_action": expected_next_action,
        "resubmitted": False,
    }
    assert "diagnostic_code" not in result
    assert "diagnostic_detail_code" not in result
    assert "diagnostic_context_code" not in result
    assert "diagnostic_context_detail_code" not in result
    assert "diagnostic_context_shape_code" not in result
    assert "diagnostic_fallback_code" not in result
    assert "diagnostic_fallback_entry_code" not in result
    assert len(transports) == 1
    assert transports[0].closed is True
    assert [tool for tool, _arguments in transports[0].calls] == [
        "browser_navigate",
        "browser_snapshot",
    ]
    assert not transports[0].secrets_file.exists()

    state = json.loads(
        (run_dir / "orchestration-state.v1.json").read_text(encoding="utf-8")
    )
    assert state["status"] == expected_status
    assert state["submission_attempted"] is True
    assert state["next_action"] == expected_next_action
    assert "diagnostic_code" not in state
    assert "diagnostic_detail_code" not in state
    assert "diagnostic_context_code" not in state
    assert "diagnostic_context_detail_code" not in state
    assert "diagnostic_context_shape_code" not in state
    assert "diagnostic_fallback_code" not in state
    assert "diagnostic_fallback_entry_code" not in state
    assert pending_path.read_bytes() == pending_before
    assert not (run_dir / "unapproved-proposal.md").exists()

    record_path = run_dir / "run-record.v1.jsonl"
    lines = record_path.read_text(encoding="utf-8").splitlines()
    event_count, final_hash = workflow._verify_events(lines, run_id)
    final_event = json.loads(lines[-1])
    assert event_count == len(lines)
    assert final_hash == final_event["event_sha256"]
    assert final_event["event_type"] == "PRO_UNAVAILABLE"
    assert final_event["payload"]["reason_code"] == reason_code
    assert final_event["payload"]["submission_attempted"] is True
    assert final_event["payload"]["resubmitted"] is False
    assert "diagnostic_code" not in record_path.read_text(encoding="utf-8")
    assert "diagnostic_detail_code" not in record_path.read_text(encoding="utf-8")
    assert "diagnostic_context_code" not in record_path.read_text(encoding="utf-8")
    assert "diagnostic_context_detail_code" not in record_path.read_text(
        encoding="utf-8"
    )
    assert "diagnostic_context_shape_code" not in record_path.read_text(
        encoding="utf-8"
    )
    assert "diagnostic_fallback_code" not in record_path.read_text(encoding="utf-8")
    assert "diagnostic_fallback_entry_code" not in record_path.read_text(
        encoding="utf-8"
    )
    assert not any(
        event["event_type"]
        in {
            "UNAPPROVED_PROPOSAL_CAPTURED",
            "ORCHESTRATION_COMPLETED",
            "MCP_RECONNECTED",
        }
        for event in map(json.loads, lines)
    )

    before_status = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    status_result = orchestrator.status(private_root=root, run_id=run_id)
    after_status = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    assert status_result["status"] == expected_status
    assert status_result["submission_attempted"] is True
    assert status_result["record_verified"] is True
    assert "diagnostic_code" not in status_result
    assert "diagnostic_detail_code" not in status_result
    assert "diagnostic_context_code" not in status_result
    assert "diagnostic_context_detail_code" not in status_result
    assert "diagnostic_context_shape_code" not in status_result
    assert "diagnostic_fallback_code" not in status_result
    assert "diagnostic_fallback_entry_code" not in status_result
    assert before_status == after_status

    with pytest.raises(orchestrator.OrchestrationRefusal) as repeated:
        orchestrator.resume(
            private_root=root,
            run_id=run_id,
            fake_scenario=None,
        )
    after_second_resume = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    assert repeated.value.code == "RUN_NOT_RESUMABLE"
    assert len(transports) == 1
    assert after_second_resume == after_status


def test_legacy_waiting_ambiguity_cli_remains_generic_without_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = private_root(tmp_path)
    initial = prepare_live_waiting_run(
        root,
        monkeypatch,
        importance="ordinary",
        name="legacy-response-ambiguity",
    )
    run_id = initial["run_id"]
    run_dir = root / "chatgpt-pro-runs" / run_id
    ambiguous = "\n".join(
        (
            "- Page URL: https://chatgpt.com/c/fake-live-resume-run",
            '- article "Assistant response" [ref=e10]:',
            '  - text "First" [ref=e11]',
            '- article "Assistant response" [ref=e20]:',
            '  - text "Second" [ref=e21]',
        )
    )
    transports: list[ScriptedLiveTransport] = []

    def scripted_transport(
        _wrapper: Path,
        secrets_file: Path,
        browser: str,
    ) -> ScriptedLiveTransport:
        assert browser == "edge"
        transport = ScriptedLiveTransport([ambiguous], secrets_file)
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", scripted_transport)
    monkeypatch.setattr(
        orchestrator,
        "_wait_for_stable_response_snapshot",
        accept_snapshot_as_stable,
    )

    exit_code = invoke_orchestrator_main(
        ["resume", "--private-root", str(root), "--run-id", run_id]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    result = json.loads(captured.out)
    assert result["status"] == "PRO_UNAVAILABLE_FALLBACK"
    assert result["reason_code"] == "RESPONSE_SELECTOR_AMBIGUITY"
    assert "diagnostic_code" not in result
    assert "diagnostic_detail_code" not in result
    assert "diagnostic_context_code" not in result
    assert "diagnostic_context_detail_code" not in result
    assert "diagnostic_context_shape_code" not in result
    assert "diagnostic_fallback_code" not in result
    assert "diagnostic_fallback_entry_code" not in result
    assert len(transports) == 1
    assert transports[0].closed is True
    assert "diagnostic_code" not in (run_dir / "orchestration-state.v1.json").read_text(
        encoding="utf-8"
    )
    assert "diagnostic_detail_code" not in (
        run_dir / "orchestration-state.v1.json"
    ).read_text(encoding="utf-8")
    assert "diagnostic_context_code" not in (
        run_dir / "orchestration-state.v1.json"
    ).read_text(encoding="utf-8")
    assert "diagnostic_context_detail_code" not in (
        run_dir / "orchestration-state.v1.json"
    ).read_text(encoding="utf-8")
    assert "diagnostic_context_shape_code" not in (
        run_dir / "orchestration-state.v1.json"
    ).read_text(encoding="utf-8")
    assert "diagnostic_fallback_code" not in (
        run_dir / "orchestration-state.v1.json"
    ).read_text(encoding="utf-8")
    assert "diagnostic_fallback_entry_code" not in (
        run_dir / "orchestration-state.v1.json"
    ).read_text(encoding="utf-8")
    assert "diagnostic_code" not in (run_dir / "run-record.v1.jsonl").read_text(
        encoding="utf-8"
    )
    assert "diagnostic_detail_code" not in (run_dir / "run-record.v1.jsonl").read_text(
        encoding="utf-8"
    )
    assert "diagnostic_context_code" not in (run_dir / "run-record.v1.jsonl").read_text(
        encoding="utf-8"
    )
    assert "diagnostic_context_detail_code" not in (
        run_dir / "run-record.v1.jsonl"
    ).read_text(encoding="utf-8")
    assert "diagnostic_context_shape_code" not in (
        run_dir / "run-record.v1.jsonl"
    ).read_text(encoding="utf-8")
    assert "diagnostic_fallback_code" not in (
        run_dir / "run-record.v1.jsonl"
    ).read_text(encoding="utf-8")
    assert "diagnostic_fallback_entry_code" not in (
        run_dir / "run-record.v1.jsonl"
    ).read_text(encoding="utf-8")
    assert "diagnostic_code" not in orchestrator.status(
        private_root=root,
        run_id=run_id,
    )
    assert "diagnostic_detail_code" not in orchestrator.status(
        private_root=root,
        run_id=run_id,
    )
    assert "diagnostic_context_code" not in orchestrator.status(
        private_root=root,
        run_id=run_id,
    )
    assert "diagnostic_context_detail_code" not in orchestrator.status(
        private_root=root,
        run_id=run_id,
    )
    assert "diagnostic_context_shape_code" not in orchestrator.status(
        private_root=root,
        run_id=run_id,
    )
    assert "diagnostic_fallback_code" not in orchestrator.status(
        private_root=root,
        run_id=run_id,
    )
    assert "diagnostic_fallback_entry_code" not in orchestrator.status(
        private_root=root,
        run_id=run_id,
    )
    assert not (run_dir / "unapproved-proposal.md").exists()


def test_concurrent_live_resumes_reload_locked_state_and_preserve_terminality(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    initial = prepare_live_waiting_run(
        root,
        monkeypatch,
        importance="gated",
        name="concurrent-resume-terminality",
    )
    run_id = initial["run_id"]
    run_dir = root / "chatgpt-pro-runs" / run_id
    pending_path = run_dir / "pending-transcript.v1.json"
    pending_before = pending_path.read_bytes()

    real_existing_run_dir = orchestrator._existing_run_dir
    path_resolution_barrier = threading.Barrier(2)

    def synchronized_existing_run_dir(run_root: Path, requested_run_id: str) -> Path:
        run_dir = real_existing_run_dir(run_root, requested_run_id)
        path_resolution_barrier.wait(timeout=5)
        return run_dir

    snapshot = "- Page URL: https://chatgpt.com/c/fake-live-resume-run"
    transports: list[ScriptedLiveTransport] = []
    transport_lock = threading.Lock()

    def scripted_transport(
        _wrapper: Path, secrets_file: Path, browser: str
    ) -> ScriptedLiveTransport:
        assert browser == "edge"
        transport = ScriptedLiveTransport([snapshot, snapshot, snapshot], secrets_file)
        with transport_lock:
            transports.append(transport)
        return transport

    parser_calls = 0
    parser_lock = threading.Lock()

    def first_parser_refuses_then_pending(
        _transcript: dict[str, Any], _snapshot: str
    ) -> tuple[dict[str, Any], str] | None:
        nonlocal parser_calls
        with parser_lock:
            parser_calls += 1
            current_call = parser_calls
        if current_call == 1:
            raise orchestrator.OrchestrationRefusal("RESPONSE_NOT_IDENTIFIABLE")
        return None

    monkeypatch.setattr(
        orchestrator, "_existing_run_dir", synchronized_existing_run_dir
    )
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", scripted_transport)
    monkeypatch.setattr(
        orchestrator,
        "_wait_for_stable_response_snapshot",
        accept_snapshot_as_stable,
    )
    monkeypatch.setattr(
        orchestrator,
        "_complete_pending_transcript",
        first_parser_refuses_then_pending,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                orchestrator.resume,
                private_root=root,
                run_id=run_id,
                fake_scenario=None,
            )
            for _index in range(2)
        ]
        results: list[tuple[int, dict[str, Any]]] = []
        refusals: list[orchestrator.OrchestrationRefusal] = []
        for future in futures:
            try:
                results.append(future.result(timeout=10))
            except orchestrator.OrchestrationRefusal as refusal:
                refusals.append(refusal)

    assert len(results) == 1
    assert len(refusals) == 1
    assert refusals[0].code == "RUN_NOT_RESUMABLE"
    winner_exit, winner = results[0]
    assert winner_exit == 4
    assert winner["status"] == "BLOCKED_PRO_REQUIRED"
    assert winner["next_action"] == "STOP"
    assert winner["resubmitted"] is False

    assert len(transports) == 1
    assert parser_calls == 1
    assert transports[0].closed is True
    assert [tool for tool, _arguments in transports[0].calls] == [
        "browser_navigate",
        "browser_snapshot",
    ]
    assert not transports[0].secrets_file.exists()

    state = json.loads(
        (run_dir / "orchestration-state.v1.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "BLOCKED_PRO_REQUIRED"
    assert state["next_action"] == "STOP"
    assert state["submission_attempted"] is True
    assert pending_path.read_bytes() == pending_before
    assert not (run_dir / "unapproved-proposal.md").exists()

    lines = (run_dir / "run-record.v1.jsonl").read_text(encoding="utf-8").splitlines()
    event_count, final_hash = workflow._verify_events(lines, run_id)
    events = [json.loads(line) for line in lines]
    assert event_count == len(lines)
    assert final_hash == events[-1]["event_sha256"]
    assert [event["event_type"] for event in events].count("PRO_UNAVAILABLE") == 1
    assert not any(event["event_type"] == "WAIT_CONTINUES" for event in events)
    assert events[-1]["event_type"] == "PRO_UNAVAILABLE"


def test_resume_and_status_wait_through_event_state_publication_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    initial = prepare_live_waiting_run(
        root,
        monkeypatch,
        importance="gated",
        name="publication-window",
    )
    run_id = initial["run_id"]
    run_dir = root / "chatgpt-pro-runs" / run_id
    pending_path = run_dir / "pending-transcript.v1.json"
    pending_before = pending_path.read_bytes()

    role = threading.local()
    publication_open = threading.Event()
    release_publication = threading.Event()
    real_atomic_private_json = orchestrator._atomic_private_json

    def paused_atomic_private_json(path: Path, value: dict[str, Any]) -> None:
        if (
            getattr(role, "name", None) == "winner"
            and value.get("status") == "BLOCKED_PRO_REQUIRED"
        ):
            publication_open.set()
            if not release_publication.wait(timeout=5):
                raise AssertionError("publication-window release timed out")
        real_atomic_private_json(path, value)

    lock_attempted = {
        "loser": threading.Event(),
        "status": threading.Event(),
    }
    real_flock = orchestrator.fcntl.flock

    def observed_flock(descriptor: int, operation: int) -> None:
        current_role = getattr(role, "name", None)
        if current_role in lock_attempted and operation in {
            orchestrator.fcntl.LOCK_EX,
            orchestrator.fcntl.LOCK_SH,
        }:
            lock_attempted[current_role].set()
        real_flock(descriptor, operation)

    snapshot = "- Page URL: https://chatgpt.com/c/fake-live-resume-run"
    transports: list[ScriptedLiveTransport] = []

    def scripted_transport(
        _wrapper: Path, secrets_file: Path, browser: str
    ) -> ScriptedLiveTransport:
        transport = ScriptedLiveTransport([snapshot], secrets_file)
        transports.append(transport)
        return transport

    parser_calls = 0

    def parser_refusal(
        _transcript: dict[str, Any], _snapshot: str
    ) -> tuple[dict[str, Any], str] | None:
        nonlocal parser_calls
        parser_calls += 1
        raise orchestrator.OrchestrationRefusal("RESPONSE_NOT_IDENTIFIABLE")

    def run_resume(worker_role: str) -> tuple[int, dict[str, Any]]:
        role.name = worker_role
        return orchestrator.resume(
            private_root=root,
            run_id=run_id,
            fake_scenario=None,
        )

    def run_status() -> dict[str, Any]:
        role.name = "status"
        return orchestrator.status(private_root=root, run_id=run_id)

    monkeypatch.setattr(
        orchestrator, "_atomic_private_json", paused_atomic_private_json
    )
    monkeypatch.setattr(orchestrator.fcntl, "flock", observed_flock)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", scripted_transport)
    monkeypatch.setattr(
        orchestrator,
        "_wait_for_stable_response_snapshot",
        accept_snapshot_as_stable,
    )
    monkeypatch.setattr(orchestrator, "_complete_pending_transcript", parser_refusal)

    with ThreadPoolExecutor(max_workers=3) as executor:
        winner_future = executor.submit(run_resume, "winner")
        assert publication_open.wait(timeout=5)

        loser_future = executor.submit(run_resume, "loser")
        status_future = executor.submit(run_status)
        assert lock_attempted["loser"].wait(timeout=5)
        assert lock_attempted["status"].wait(timeout=5)
        assert not loser_future.done()
        assert not status_future.done()

        release_publication.set()
        winner_exit, winner = winner_future.result(timeout=10)
        with pytest.raises(orchestrator.OrchestrationRefusal) as loser_refusal:
            loser_future.result(timeout=10)
        verified = status_future.result(timeout=10)

    assert winner_exit == 4
    assert loser_refusal.value.code == "RUN_NOT_RESUMABLE"
    assert winner["status"] == "BLOCKED_PRO_REQUIRED"
    assert winner["next_action"] == "STOP"
    assert verified["status"] == "BLOCKED_PRO_REQUIRED"
    assert verified["next_action"] == "STOP"
    assert verified["record_verified"] is True

    assert len(transports) == 1
    assert parser_calls == 1
    assert transports[0].closed is True
    assert [tool for tool, _arguments in transports[0].calls] == [
        "browser_navigate",
        "browser_snapshot",
    ]
    assert not transports[0].secrets_file.exists()

    state = json.loads(
        (run_dir / "orchestration-state.v1.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "BLOCKED_PRO_REQUIRED"
    assert state["next_action"] == "STOP"
    assert pending_path.read_bytes() == pending_before
    assert not (run_dir / "unapproved-proposal.md").exists()

    lines = (run_dir / "run-record.v1.jsonl").read_text(encoding="utf-8").splitlines()
    event_count, final_hash = workflow._verify_events(lines, run_id)
    events = [json.loads(line) for line in lines]
    assert event_count == len(lines)
    assert final_hash == events[-1]["event_sha256"]
    assert [event["event_type"] for event in events].count("PRO_UNAVAILABLE") == 1
    assert not any(event["event_type"] == "WAIT_CONTINUES" for event in events)


@pytest.mark.parametrize("operation", ["resume", "status"])
def test_resume_and_status_do_not_create_a_missing_run_directory(
    tmp_path: Path,
    operation: str,
) -> None:
    root = private_root(tmp_path)
    run_id = "20260805T000000Z-000000000000"
    run_root = root / "chatgpt-pro-runs"
    run_dir = run_root / run_id

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        if operation == "resume":
            orchestrator.resume(
                private_root=root,
                run_id=run_id,
                fake_scenario=None,
            )
        else:
            orchestrator.status(private_root=root, run_id=run_id)

    assert captured.value.code == "RUN_NOT_FOUND"
    assert not run_root.exists()
    assert not run_dir.exists()


@pytest.mark.parametrize("operation", ["resume", "status"])
def test_resume_and_status_reject_a_symlink_run_directory(
    tmp_path: Path,
    operation: str,
) -> None:
    root = private_root(tmp_path)
    run_root = root / "chatgpt-pro-runs"
    run_root.mkdir(mode=0o700)
    run_id = "20260805T000000Z-111111111111"
    target = tmp_path / "outside-run"
    target.mkdir(mode=0o700)
    run_dir = run_root / run_id
    run_dir.symlink_to(target, target_is_directory=True)

    with pytest.raises(workflow.WorkflowRefusal) as captured:
        if operation == "resume":
            orchestrator.resume(
                private_root=root,
                run_id=run_id,
                fake_scenario=None,
            )
        else:
            orchestrator.status(private_root=root, run_id=run_id)

    assert captured.value.code == "PATH_SYMLINK"
    assert run_dir.is_symlink()
    assert list(target.iterdir()) == []


@pytest.mark.parametrize("operation", ["resume", "status"])
def test_resume_and_status_reject_nonprivate_run_directory_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    root = private_root(tmp_path)
    initial = prepare_live_waiting_run(
        root,
        monkeypatch,
        importance="gated",
        name=f"run-mode-{operation}",
    )
    run_dir = root / "chatgpt-pro-runs" / initial["run_id"]
    run_dir.chmod(0o750)

    def unexpected_transport(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("transport must not be created")

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", unexpected_transport)
    try:
        with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
            if operation == "resume":
                orchestrator.resume(
                    private_root=root,
                    run_id=initial["run_id"],
                    fake_scenario=None,
                )
            else:
                orchestrator.status(private_root=root, run_id=initial["run_id"])
        assert captured.value.code == "RUN_DIRECTORY_MODE"
    finally:
        run_dir.chmod(0o700)


def test_resume_hash_mismatch_is_refused_only_after_exclusive_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    initial = prepare_live_waiting_run(
        root,
        monkeypatch,
        importance="gated",
        name="locked-state-tamper",
    )
    run_id = initial["run_id"]
    run_dir = root / "chatgpt-pro-runs" / run_id
    state_path = run_dir / "orchestration-state.v1.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["next_action"] = "TAMPERED"
    state_path.write_text(
        json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    before = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }

    exclusive_lock_acquired = False
    real_flock = orchestrator.fcntl.flock

    def observed_flock(descriptor: int, operation: int) -> None:
        nonlocal exclusive_lock_acquired
        real_flock(descriptor, operation)
        if operation == orchestrator.fcntl.LOCK_EX:
            exclusive_lock_acquired = True

    def unexpected_transport(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("transport must not be created")

    monkeypatch.setattr(orchestrator.fcntl, "flock", observed_flock)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", unexpected_transport)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=run_id,
            fake_scenario=None,
        )

    after = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    assert captured.value.code == "STATE_RECORD_MISMATCH"
    assert exclusive_lock_acquired is True
    assert before == after
    assert (run_dir / "pending-transcript.v1.json").is_file()
    assert not (run_dir / "unapproved-proposal.md").exists()


def test_live_resume_nonallowlisted_refusal_remains_hard_and_state_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = private_root(tmp_path)
    initial = prepare_live_waiting_run(
        root,
        monkeypatch,
        importance="ordinary",
        name="resume-contract-hard-refusal",
    )
    run_id = initial["run_id"]
    run_dir = root / "chatgpt-pro-runs" / run_id
    transports: list[ScriptedLiveTransport] = []

    def scripted_transport(
        _wrapper: Path, secrets_file: Path, browser: str
    ) -> ScriptedLiveTransport:
        transport = ScriptedLiveTransport(
            ["- Page URL: https://chatgpt.com/c/fake-live-resume-run"],
            secrets_file,
        )
        transports.append(transport)
        return transport

    def contract_refusal(
        _transcript: dict[str, Any], _snapshot: str
    ) -> tuple[dict[str, Any], str] | None:
        raise orchestrator.OrchestrationRefusal("CONTRACT_INVALID")

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", scripted_transport)
    monkeypatch.setattr(
        orchestrator,
        "_wait_for_stable_response_snapshot",
        accept_snapshot_as_stable,
    )
    monkeypatch.setattr(orchestrator, "_complete_pending_transcript", contract_refusal)
    before = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }

    exit_code = invoke_orchestrator_main(
        ["resume", "--private-root", str(root), "--run-id", run_id]
    )
    captured = capsys.readouterr()
    after = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }

    assert exit_code == 2
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "reason_code": "CONTRACT_INVALID",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }
    assert before == after
    assert len(transports) == 1
    assert transports[0].closed is True
    assert not transports[0].secrets_file.exists()
    assert (run_dir / "pending-transcript.v1.json").is_file()
    assert not (run_dir / "unapproved-proposal.md").exists()


def test_status_is_content_read_only_and_rejects_tampered_hash_chain(
    tmp_path: Path,
) -> None:
    root = private_root(tmp_path)
    request = private_request(root, "status.txt")
    scenario = successful_scenario(tmp_path / "status-success.json")
    _, asked = ask_fixture(root, request, scenario)
    run_id = asked["run_id"]
    run_dir = root / "chatgpt-pro-runs" / run_id
    before = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.iterdir()
        if path.is_file()
    }

    result = orchestrator.status(private_root=root, run_id=run_id)

    after = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.iterdir()
        if path.is_file()
    }
    assert result["record_verified"] is True
    assert result["status"] == "ADVICE_CAPTURED"
    assert before == after

    record_path = run_dir / "run-record.v1.jsonl"
    record_path.write_text(
        record_path.read_text(encoding="utf-8").replace(
            "ADVICE_CAPTURED", "ADVICE_TAMPERED", 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(workflow.WorkflowRefusal) as captured:
        orchestrator.status(private_root=root, run_id=run_id)
    assert captured.value.code == "RUN_RECORD_INVALID"


def test_follow_ups_have_no_numeric_cap_and_repeated_gap_converges(
    tmp_path: Path,
) -> None:
    root = private_root(tmp_path)
    initial_request = private_request(root, "initial.txt")
    initial_scenario = successful_scenario(
        tmp_path / "initial.json",
        response=advice_text(summary="Initial delta.", open_gaps=["Gap zero"]),
    )
    _, current = ask_fixture(root, initial_request, initial_scenario)
    assert current["status"] == "ADVICE_CAPTURED"

    gap_texts: list[str] = []
    for index in range(1, 13):
        gap_text = f"Unresolved gap {index}"
        gap_texts.append(gap_text)
        request = private_request(root, f"follow-up-request-{index}.txt")
        gap = private_request(root, f"follow-up-gap-{index}.txt", gap_text)
        scenario = successful_scenario(
            tmp_path / f"follow-up-{index}.json",
            response=advice_text(
                summary=f"Material delta {index}.",
                open_gaps=[f"Next gap {index}"],
            ),
        )
        exit_code, current = ask_fixture(
            root,
            request,
            scenario,
            parent_run_id=current["run_id"],
            gap_file=gap,
        )
        assert exit_code == 0
        assert current["status"] == "ADVICE_CAPTURED"

    last_state = json.loads(
        (
            root
            / "chatgpt-pro-runs"
            / current["run_id"]
            / "orchestration-state.v1.json"
        ).read_text(encoding="utf-8")
    )
    assert len(last_state["gap_hashes"]) == 12
    assert "follow_up_count" not in orchestrator.STATE_KEYS

    repeated_request = private_request(root, "repeated-request.txt")
    repeated_gap = private_request(
        root,
        "repeated-gap.txt",
        f"  {gap_texts[4].upper()}   ",
    )
    nonexistent_scenario = tmp_path / "must-not-open-transport.json"
    exit_code, converged = ask_fixture(
        root,
        repeated_request,
        nonexistent_scenario,
        parent_run_id=current["run_id"],
        gap_file=repeated_gap,
    )
    assert exit_code == 0
    assert converged["status"] == "CONVERGED_REPEATED_GAP"
    assert converged["next_action"] == "STOP"


def test_materially_duplicate_follow_up_converges(tmp_path: Path) -> None:
    root = private_root(tmp_path)
    response = advice_text(summary="Stable response", open_gaps=["Still open"])
    initial_request = private_request(root, "duplicate-initial.txt")
    initial_scenario = successful_scenario(
        tmp_path / "duplicate-initial.json", response=response
    )
    _, initial = ask_fixture(root, initial_request, initial_scenario)
    assert initial["status"] == "ADVICE_CAPTURED"

    follow_up_request = private_request(root, "duplicate-follow-up.txt")
    gap = private_request(root, "duplicate-gap.txt", "A new named gap")
    follow_up_scenario = successful_scenario(
        tmp_path / "duplicate-follow-up.json", response=response
    )
    exit_code, converged = ask_fixture(
        root,
        follow_up_request,
        follow_up_scenario,
        parent_run_id=initial["run_id"],
        gap_file=gap,
    )

    assert exit_code == 0
    assert converged["status"] == "CONVERGED_DUPLICATE_RESPONSE"
    assert converged["next_action"] == "STOP"


@pytest.mark.parametrize(
    ("material_delta", "open_gaps", "expected_status"),
    [
        (
            False,
            ["Still described but not materially advanced"],
            "CONVERGED_NO_MATERIAL_DELTA",
        ),
        (True, [], "CONVERGED_NO_OPEN_GAP"),
    ],
)
def test_no_delta_or_no_open_gap_stops_convergence(
    tmp_path: Path,
    material_delta: bool,
    open_gaps: list[str],
    expected_status: str,
) -> None:
    root = private_root(tmp_path)
    request = private_request(root, f"{expected_status.lower()}.txt")
    scenario = successful_scenario(
        tmp_path / f"{expected_status.lower()}.json",
        response=advice_text(
            summary=expected_status,
            material_delta=material_delta,
            open_gaps=open_gaps,
        ),
    )

    exit_code, result = ask_fixture(root, request, scenario)

    assert exit_code == 0
    assert result["status"] == expected_status
    assert result["next_action"] == "STOP"


@pytest.mark.parametrize(
    ("placement", "mode", "text", "expected_code"),
    [
        ("outside", 0o600, REQUEST_TEXT, "REQUEST_FILE_SCOPE"),
        ("inside", 0o644, REQUEST_TEXT, "REQUEST_FILE_MODE"),
        (
            "inside",
            0o600,
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
            "REQUEST_INVALID",
        ),
    ],
)
def test_request_must_be_private_in_scope_and_non_sensitive(
    tmp_path: Path,
    placement: str,
    mode: int,
    text: str,
    expected_code: str,
) -> None:
    root = private_root(tmp_path)
    if placement == "inside":
        request = private_request(root, "request.txt", text, mode=mode)
    else:
        request = tmp_path / "outside-request.txt"
        request.write_text(text, encoding="utf-8")
        request.chmod(mode)
    scenario = successful_scenario(tmp_path / "unused-success.json")

    with pytest.raises(
        (orchestrator.OrchestrationRefusal, workflow.WorkflowRefusal)
    ) as captured:
        ask_fixture(root, request, scenario)
    assert captured.value.code == expected_code


def test_sensitive_response_is_rejected_without_persisting_the_value(
    tmp_path: Path,
) -> None:
    root = private_root(tmp_path)
    request = private_request(root, "sensitive-response.txt")
    synthetic_secret = "s" + "k-proj-" + "A1b2C3d4E5f6G7h8I9j0K1l2"
    scenario = successful_scenario(
        tmp_path / "sensitive.json", response=synthetic_secret
    )

    exit_code, result = ask_fixture(root, request, scenario)

    assert exit_code == 0
    assert result["status"] == "PRO_UNAVAILABLE_FALLBACK"
    assert result["reason_code"] == "RESPONSE_SENSITIVE_OR_INVALID"
    run_dir = root / "chatgpt-pro-runs" / result["run_id"]
    for artifact in run_dir.rglob("*"):
        if artifact.is_file():
            assert synthetic_secret.encode() not in artifact.read_bytes()


def test_make_config_agents_and_skill_retain_approved_policy() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    for target in (
        "pro-runtime-install:",
        "pro-setup:",
        "pro-doctor:",
        "pro-ask:",
        "pro-resume:",
        "pro-import-response:",
    ):
        assert target in makefile
    assert "scripts/chatgpt_pro_python.sh" in makefile
    assert '"$(PRO_PYTHON_LAUNCHER)" setup' in makefile
    assert '"$(PRO_PYTHON_LAUNCHER)" doctor' in makefile
    assert '"$(PRO_PYTHON_LAUNCHER)" ask' in makefile
    assert '"$(PRO_PYTHON_LAUNCHER)" resume' in makefile
    assert '"$(PRO_PYTHON_LAUNCHER)" runtime-install' in makefile
    assert '"$(PRO_PYTHON_LAUNCHER)" import-response' in makefile
    pro_targets = makefile[
        makefile.index("PRO_REQUEST_FILE ?=") : makefile.index("python-install:")
    ]
    assert "UV_READONLY_RUN" not in pro_targets
    assert '--private-root "$(PRO_PRIVATE_ROOT)"' in pro_targets
    assert "PRO_REQUEST_FILE ?=\n" in makefile
    assert "PRO_RESPONSE_FILE ?=\n" in makefile
    assert "PRO_NODE ?=" in pro_targets
    assert "PRO_NPM_CLI ?=" in pro_targets
    assert "PRO_BROWSER ?= auto" in pro_targets
    assert "PRO_INTERACTIVE_AUTH_WAIT_SECONDS ?= 900" in pro_targets
    assert (
        '$(if $(strip $(PRO_REQUEST_FILE)),--request-file "$(PRO_REQUEST_FILE)",)'
        in makefile
    )
    assert '--importance "$(PRO_IMPORTANCE)"' in makefile
    assert '--run-id "$(PRO_RUN_ID)"' in makefile
    assert '--browser "$(PRO_BROWSER)"' in pro_targets
    assert (
        '--interactive-auth-wait-seconds "$(PRO_INTERACTIVE_AUTH_WAIT_SECONDS)"'
        in pro_targets
    )

    config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    playwright = config["mcp_servers"]["playwright"]
    expected_tools = set(orchestrator.ALLOWED_MCP_TOOLS)
    assert playwright["enabled"] is False
    assert playwright["command"] == "/bin/bash"
    assert playwright["args"] == [str(REPOSITORY_ROOT / "scripts/chatgpt_pro_mcp.sh")]
    assert set(playwright["enabled_tools"]) == expected_tools
    assert "env_vars" not in playwright
    assert set(playwright["tools"]) == expected_tools
    assert all(
        tool["approval_mode"] == "approve" for tool in playwright["tools"].values()
    )
    assert {
        "browser_tabs",
        "browser_evaluate",
        "browser_run_code_unsafe",
        "browser_file_upload",
        "browser_storage_state",
        "browser_cookie_list",
        "browser_localstorage_list",
        "browser_sessionstorage_list",
    }.issubset(playwright["disabled_tools"])

    agents = AGENTS_PATH.read_text(encoding="utf-8")
    story_readme = (REPOSITORY_ROOT / "changes/st-0101/README.md").read_text(
        encoding="utf-8"
    )
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    normalized_skill = " ".join(skill.split())
    skill_metadata = (SKILL_ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
    for policy in (agents, skill):
        assert (
            "After local exploration" in policy or "after local exploration" in policy
        )
        assert "cross-module or architecture-boundary" in policy
        assert "locally discoverable" in policy
        assert "no fixed count cap" in policy or "no numerical follow-up cap" in policy
        assert "materially duplicate" in policy
        assert "no material delta" in policy
        assert "DESIGN_HANDOFF_V1" in policy
        assert "human approval" in policy
    assert "physical /home/minami/rakuten" in skill
    assert "make pro-doctor" in skill
    assert "make pro-setup" in skill
    assert "make pro-runtime-install" in skill
    assert "make pro-import-response" in skill
    assert "run a fresh `make pro-doctor` and require `READY`" in normalized_skill
    assert "never proceed from a `STOPPED` outcome" in skill
    assert "never ask the user to run the command" in skill
    assert "do not close" in skill
    assert "one MCP child, one transport" in skill
    assert "up to 900 seconds" in skill
    assert "snapshots, and" in skill
    assert "CDP or remote debugging" in normalized_skill
    assert "selected dedicated ChatGPT-only browser" in normalized_skill
    assert "prefers the approved fixed Linux Edge browser" in normalized_skill
    assert "only when Edge is unavailable before launch" in normalized_skill
    assert "must never switch browsers" in skill
    assert "Skill always uses this private-file" in skill
    assert "make pro-ask" in skill
    assert "make pro-resume" in skill
    assert "allow_implicit_invocation: true" in skill_metadata
    assert "Use $raos-ask-pro" in skill_metadata
    for policy in (agents, story_readme, skill):
        assert "diagnostic_fallback_entry_code" in policy
        assert (
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR"
            in policy
        )
        assert (
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_PRESENTATION_WRAPPER"
            in policy
        )


def test_make_pro_launcher_ignores_wrong_ambient_uv_and_setup_uses_it(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "ambient-uv-was-executed"
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        '#!/bin/sh\nprintf invoked > "$RAOS_TEST_UV_MARKER"\nexit 99\n',
        encoding="utf-8",
    )
    fake_uv.chmod(0o700)
    private = tmp_path / ".secrets"
    environment = {
        "HOME": os.environ.get("HOME", "/home/minami"),
        "LANG": "C.UTF-8",
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "RAOS_TEST_UV_MARKER": str(marker),
    }

    process = subprocess.run(
        [
            "/usr/bin/make",
            "--no-builtin-rules",
            "--no-builtin-variables",
            "--file",
            str(MAKEFILE_PATH),
            "pro-doctor",
            f"PRO_PRIVATE_ROOT={private}",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert process.returncode == 0, process.stderr
    assert '"status":"SETUP_REQUIRED"' in process.stdout
    assert not marker.exists()
    assert_private_tree(private)

    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert (
        "override PRO_PYTHON_LAUNCHER := "
        "$(RAOS_REPOSITORY_ROOT)/scripts/chatgpt_pro_python.sh"
    ) in makefile
    setup_start = makefile.index("pro-setup:")
    setup_recipe = makefile[setup_start : makefile.index("\npro-doctor:", setup_start)]
    assert setup_recipe == (
        "pro-setup:\n"
        '\t"$(PRO_PYTHON_LAUNCHER)" setup \\\n'
        '\t\t--private-root "$(PRO_PRIVATE_ROOT)" \\\n'
        '\t\t--browser "$(PRO_BROWSER)" \\\n'
        "\t\t$(if $(filter 1,$(PRO_NO_OPEN_LOGIN)),"
        "--no-open-login,--open-login)\n"
    )
    assert "uv" not in setup_recipe.casefold()
