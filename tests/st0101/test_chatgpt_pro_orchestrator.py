"""Fake-only evidence for the ST-0101 ChatGPT Pro orchestrator."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
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
EXPECTED_TOOLS = [
    "browser_navigate",
    "browser_click",
    "browser_click",
    "browser_type",
    "browser_click",
    "browser_wait_for",
]


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


def invoke_orchestrator_main(arguments: list[str]) -> int:
    """Run the CLI entry point without leaking its restrictive process umask."""

    previous_umask = os.umask(0o077)
    try:
        return orchestrator.main(arguments)
    finally:
        os.umask(previous_umask)


def test_setup_without_login_is_noninteractive_and_owner_private(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".secrets"
    missing_chrome = tmp_path / "must-not-be-opened"
    process = subprocess.run(
        [
            sys.executable,
            str(ORCHESTRATOR_PATH),
            "setup",
            "--private-root",
            str(root),
            "--no-open-login",
            "--chrome",
            str(missing_chrome),
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
    result = json.loads(process.stdout)
    assert result == {
        "login_opened": False,
        "next_action": "pro-doctor",
        "profile": str(root / "chatgpt-pro-profile"),
        "status": "SETUP_READY",
        "story_id": "ST-0101",
    }
    setup_state = json.loads(
        (root / "chatgpt-pro-setup.v1.json").read_text(encoding="utf-8")
    )
    assert setup_state["status"] == "LOGIN_NOT_VERIFIED"
    assert_private_tree(root)


def test_setup_opens_and_waits_for_the_dedicated_login_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / ".secrets"
    chrome = tmp_path / "google-chrome"
    chrome.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    chrome.chmod(0o700)
    calls: list[dict[str, Any]] = []

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append({"command": command, **kwargs})
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "DEFAULT_CHROME", chrome)
    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)

    result = orchestrator.setup(private_root=root, open_login=True, chrome=chrome)

    assert result["login_opened"] is True
    assert result["next_action"] == "pro-doctor"
    assert len(calls) == 1
    assert calls[0]["command"] == [
        str(chrome),
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
    orchestrator.setup(
        private_root=root,
        open_login=False,
        chrome=tmp_path / "unused-chrome",
    )
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
    orchestrator.setup(
        private_root=root,
        open_login=False,
        chrome=tmp_path / "unused-chrome",
    )
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
    assert REQUEST_TEXT not in record_text
    assert REQUEST_TEXT not in proposal
    assert "UNAPPROVED_PROPOSAL" in proposal
    assert "cannot authorize" in proposal
    assert "UNAPPROVED_ADVICE" in proposal


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
        "SELECTOR_AMBIGUITY",
        "MODEL_OPTIONS_AMBIGUOUS",
        "ORIGIN_MISMATCH",
        "UNKNOWN_UI",
    }
    source = orchestrator.OrchestrationRefusal(reason_code)

    classified = orchestrator._classify_pre_submission_ui_refusal(source)

    assert type(classified) is orchestrator.LiveUiUnavailable
    assert classified.code == reason_code


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
    request = private_request(root, f"live-no-model-picker-{importance}.txt")
    raw_snapshot = "\n".join(
        (
            "- Page URL: https://chatgpt.com/",
            '- textbox "Ask anything" [ref=e1]',
            '- button "Send" [ref=e2]',
        )
    )
    transports: list[ScriptedLiveTransport] = []

    def scripted_transport(_wrapper: Path, secrets_file: Path) -> ScriptedLiveTransport:
        assert secrets_file.is_file()
        transport = ScriptedLiveTransport([raw_snapshot], secrets_file)
        transports.append(transport)
        return transport

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
    assert result["submission_attempted"] is False
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
    ]
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
    assert final_event["payload"]["submission_attempted"] is False
    assert REQUEST_TEXT not in record_text
    verified = orchestrator.status(private_root=root, run_id=run_id)
    assert verified["record_verified"] is True
    assert verified["submission_attempted"] is False


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
    request = private_request(root, f"hard-refusal-{reason_code}.txt")
    transports: list[ScriptedLiveTransport] = []

    def scripted_transport(_wrapper: Path, secrets_file: Path) -> ScriptedLiveTransport:
        transport = ScriptedLiveTransport([], secrets_file)
        transports.append(transport)
        return transport

    def refuse_live_capture(**_arguments: Any) -> None:
        raise orchestrator.OrchestrationRefusal(reason_code)

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", scripted_transport)
    monkeypatch.setattr(orchestrator, "_live_capture", refuse_live_capture)

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

    def scripted_transport(_wrapper: Path, secrets_file: Path) -> ScriptedLiveTransport:
        transport = ScriptedLiveTransport([], secrets_file)
        transports.append(transport)
        return transport

    monkeypatch.setattr(workflow, "_load_contract", load_contract)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", scripted_transport)

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
    for target in ("pro-setup:", "pro-doctor:", "pro-ask:", "pro-resume:"):
        assert target in makefile
    assert "scripts/chatgpt_pro_python.sh" in makefile
    assert '"$(PRO_PYTHON_LAUNCHER)" setup' in makefile
    assert '"$(PRO_PYTHON_LAUNCHER)" doctor' in makefile
    assert '"$(PRO_PYTHON_LAUNCHER)" ask' in makefile
    assert '"$(PRO_PYTHON_LAUNCHER)" resume' in makefile
    pro_targets = makefile[
        makefile.index("PRO_REQUEST_FILE ?=") : makefile.index("python-install:")
    ]
    assert "UV_READONLY_RUN" not in pro_targets
    assert '--private-root "$(PRO_PRIVATE_ROOT)"' in pro_targets
    assert "PRO_REQUEST_FILE ?=\n" in makefile
    assert (
        '$(if $(strip $(PRO_REQUEST_FILE)),--request-file "$(PRO_REQUEST_FILE)",)'
        in makefile
    )
    assert '--importance "$(PRO_IMPORTANCE)"' in makefile
    assert '--run-id "$(PRO_RUN_ID)"' in makefile

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
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
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
    assert "Then run `make pro-setup` yourself" in skill
    assert "Do not ask the user to run a command" in skill
    assert "run `make pro-doctor` again and resume the same" in skill
    assert "Skill always uses this private-file" in skill
    assert "make pro-ask" in skill
    assert "make pro-resume" in skill
    assert "allow_implicit_invocation: true" in skill_metadata
    assert "Use $raos-ask-pro" in skill_metadata


def test_make_pro_setup_ignores_wrong_ambient_uv(tmp_path: Path) -> None:
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
            "pro-setup",
            f"PRO_PRIVATE_ROOT={private}",
            "PRO_NO_OPEN_LOGIN=1",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert process.returncode == 0, process.stderr
    assert '"status":"SETUP_READY"' in process.stdout
    assert not marker.exists()
    assert_private_tree(private)
