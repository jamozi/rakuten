"""Deterministic evidence for ST-0101 bound response-only recovery."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

import pytest

from scripts import chatgpt_pro_orchestrator as orchestrator
from scripts import chatgpt_pro_workflow as workflow


RUN_ID = "20260810T120000Z-aaaaaaaaaaaa"
CONVERSATION_URL = "https://chatgpt.com/c/bound-response-recovery"


def advice_text(summary: str = "Recover only the bound displayed response.") -> str:
    return json.dumps(
        {
            "schema": "PRO_ADVICE_V1",
            "summary": summary,
            "material_delta": True,
            "open_gaps": ["One named gap remains."],
            "evidence_refs": ["ST-0101 bound recovery fixture"],
            "recommendations": ["Reconcile with canonical evidence."],
            "authority": "UNAPPROVED_ADVICE",
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def response_snapshot(
    response: str,
    *,
    url: str = CONVERSATION_URL,
    heading_line: str = '- heading "ChatGPT said:" [ref=e60]',
    extra_lines: tuple[str, ...] = (),
) -> str:
    return "\n".join(
        (
            f"- Page URL: {url}",
            heading_line,
            "- generic [ref=e61]:",
            "  - generic [ref=e62]:",
            f"    - text: {json.dumps(response)}",
            *extra_lines,
        )
    )


def pre_content_response_snapshot(
    response: str,
    *,
    action_descendants: tuple[str, ...] = (),
) -> str:
    return "\n".join(
        (
            f"- Page URL: {CONVERSATION_URL}",
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            *action_descendants,
            "  - generic [ref=e62]:",
            f"    - text: {json.dumps(response)}",
        )
    )


def embedded_pre_content_response_snapshot(
    response: str,
    *,
    wrapper_ref: str | None = None,
    extra_descendants: tuple[str, ...] = (),
    before_group: tuple[str, ...] = (),
    after_group: tuple[str, ...] = (),
) -> str:
    optional_ref = "" if wrapper_ref is None else f" [ref={wrapper_ref}]"
    return "\n".join(
        (
            f"- Page URL: {CONVERSATION_URL}",
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            "  - generic [ref=e62]:",
            *before_group,
            '    - group "Response actions":',
            "      - paragraph:",
            f"        - text: {json.dumps(response)}",
            f"      - quote{optional_ref}:",
            '        - statictext: ""',
            *extra_descendants,
            *after_group,
        )
    )


class RecoveryTransport:
    mode = "LIVE"

    def __init__(
        self,
        snapshots: list[str | BaseException],
        *,
        wait_failure: BaseException | None = None,
    ) -> None:
        self.snapshots = list(snapshots)
        self.wait_failure = wait_failure
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    def call(self, tool: str, arguments: dict[str, Any]) -> str:
        self.calls.append((tool, dict(arguments)))
        if tool == "browser_wait_for" and self.wait_failure is not None:
            raise self.wait_failure
        if tool == "browser_snapshot":
            if not self.snapshots:
                raise AssertionError("unexpected browser snapshot")
            value = self.snapshots.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value
        return ""

    def close(self) -> None:
        self.calls.append(("browser_close", {}))
        self.closed = True


def private_root(tmp_path: Path) -> Path:
    root = tmp_path / ".secrets"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    orchestrator._ensure_layout(root)
    return root


def create_terminal_run(
    root: Path,
    *,
    reason_code: str = "RESPONSE_NOT_IDENTIFIABLE",
    importance: str = "ordinary",
    mode: str = "LIVE",
    browser: str = "edge",
    submission_intents: int = 1,
    pending_transcript: bytes | None = None,
) -> tuple[Path, dict[str, Any]]:
    run_dir = root / "chatgpt-pro-runs" / RUN_ID
    run_dir.mkdir(mode=0o700)
    run_dir.chmod(0o700)
    prepared = {
        "run_id": RUN_ID,
        "run_dir": str(run_dir),
        "record_path": str(run_dir / "run-record.v1.jsonl"),
        "prompt_sha256": "a" * 64,
    }
    state = orchestrator._new_state(
        prepared,
        mode=mode,
        browser=browser,
        importance=importance,
        parent_run_id=None,
        gap_hashes=[],
        response_fingerprints=[],
    )
    workflow._append_event(
        run_dir / "run-record.v1.jsonl",
        RUN_ID,
        "RUN_PREPARED",
        {
            "status": "PREPARED",
            "origin": workflow.EXACT_ORIGIN,
            "prompt_sha256": state["prompt_sha256"],
            "contract_sha256": "b" * 64,
            "prompt_secret_name": "RAOS_CHATGPT_PROMPT",
        },
    )
    orchestrator._persist_state(
        run_dir,
        run_dir / "run-record.v1.jsonl",
        state,
        event_type="ORCHESTRATION_PREPARED",
        event_payload={
            "status": "PREPARED",
            "mode": mode,
            "browser": browser,
            "importance": importance,
        },
    )
    for _index in range(submission_intents):
        workflow._append_event(
            run_dir / "run-record.v1.jsonl",
            RUN_ID,
            "SUBMISSION_INTENT_RECORDED",
            {
                "status": "PRE_SEND",
                "origin": workflow.EXACT_ORIGIN,
                "model_label": "GPT-5.6 Sol",
                "effort_label": "Pro",
                "prompt_sha256": state["prompt_sha256"],
            },
        )
    state["submission_attempted"] = True
    state["conversation_url"] = CONVERSATION_URL
    if pending_transcript is not None:
        state["transcript_sha256"] = hashlib.sha256(pending_transcript).hexdigest()
        pending_path = run_dir / "pending-transcript.v1.json"
        pending_path.write_bytes(pending_transcript)
        pending_path.chmod(0o600)
    orchestrator._record_unavailable(
        prepared=prepared,
        state=state,
        reason_code=reason_code,
    )
    return run_dir, state


def install_transport(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    transport: RecoveryTransport,
) -> None:
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(
        orchestrator,
        "StdioMcpTransport",
        lambda _wrapper, _secret_file, browser: (
            transport if browser == "edge" else pytest.fail("unexpected browser")
        ),
    )


def event_list(run_dir: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (run_dir / "run-record.v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]


def rewrite_record(
    run_dir: Path,
    mutate: Callable[[list[dict[str, Any]]], None],
) -> None:
    events = event_list(run_dir)
    mutate(events)
    record_path = run_dir / "run-record.v1.jsonl"
    record_path.unlink()
    for event in events:
        workflow._append_event(
            record_path,
            RUN_ID,
            event["event_type"],
            event["payload"],
        )


def assert_recovery_tools_only(transport: RecoveryTransport) -> None:
    assert all(
        tool
        in {
            "browser_navigate",
            "browser_snapshot",
            "browser_wait_for",
            "browser_close",
        }
        for tool, _arguments in transport.calls
    )


def invoke_orchestrator_main(arguments: list[str]) -> int:
    """Run the CLI without leaking its restrictive process umask."""

    previous_umask = os.umask(0o077)
    try:
        return orchestrator.main(arguments)
    finally:
        os.umask(previous_umask)


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(advice_text(), id="structured-advice"),
        pytest.param("A stable plain Markdown review.", id="plain-review"),
    ],
)
def test_exact_terminal_recovery_commits_event_last_without_mutating_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response: str,
) -> None:
    root = private_root(tmp_path)
    pending = b'{"unrelated":"pending transcript remains inert"}\n'
    run_dir, _state = create_terminal_run(root, pending_transcript=pending)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    pending_before = (run_dir / "pending-transcript.v1.json").read_bytes()
    stable = response_snapshot(response)
    transport = RecoveryTransport([stable, stable, stable])
    install_transport(monkeypatch, root, transport)
    monkeypatch.setattr(
        orchestrator,
        "_load_pending_transcript",
        lambda *_args, **_kwargs: pytest.fail(
            "terminal recovery must not read a pending transcript"
        ),
    )

    exit_code, result = orchestrator.resume(
        private_root=root,
        run_id=RUN_ID,
        fake_scenario=None,
    )

    assert exit_code == 0
    assert result["status"] in {"ADVICE_CAPTURED", "REVIEW_CAPTURED"}
    assert result["provenance"] == "AUTOMATED_BOUND_CONVERSATION_RECOVERY"
    assert result["resubmitted"] is False
    assert result["record_verified"] is True
    assert "diagnostic_context_code" not in result
    assert "diagnostic_context_detail_code" not in result
    assert "diagnostic_context_shape_code" not in result
    assert "diagnostic_fallback_code" not in result
    assert "diagnostic_fallback_entry_code" not in result
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "pending-transcript.v1.json").read_bytes() == pending_before
    events = event_list(run_dir)
    assert events[-1]["event_type"] == "BOUND_RESPONSE_RECOVERED"
    assert events[-1]["payload"]["resubmitted"] is False
    assert events[-1]["payload"]["provenance"] == (
        "AUTOMATED_BOUND_CONVERSATION_RECOVERY"
    )
    assert "diagnostic_context_code" not in json.dumps(events[-1], sort_keys=True)
    assert "diagnostic_context_detail_code" not in json.dumps(
        events[-1], sort_keys=True
    )
    assert "diagnostic_context_shape_code" not in json.dumps(events[-1], sort_keys=True)
    assert "diagnostic_fallback_code" not in json.dumps(events[-1], sort_keys=True)
    assert "diagnostic_fallback_entry_code" not in json.dumps(
        events[-1], sort_keys=True
    )
    assert events[-1]["payload"]["source_terminal_event_sha256"] == next(
        event["event_sha256"]
        for event in events
        if event["event_type"] == "PRO_UNAVAILABLE"
    )
    assert (
        sum(event["event_type"] == "SUBMISSION_INTENT_RECORDED" for event in events)
        == 1
    )
    assert transport.calls[0] == (
        "browser_navigate",
        {"url": CONVERSATION_URL},
    )
    assert transport.calls[-1] == ("browser_close", {})
    assert_recovery_tools_only(transport)

    status = orchestrator.status(private_root=root, run_id=RUN_ID)
    assert status["status"] == result["status"]
    assert status["advice_type"] == result["advice_type"]
    assert status["authority"] == result["authority"]
    assert status["next_action"] == result["next_action"]
    assert status["provenance"] == result["provenance"]
    assert status["resubmitted"] is False
    assert "diagnostic_context_code" not in status
    assert "diagnostic_context_code" not in (
        run_dir / "unapproved-proposal.md"
    ).read_text(encoding="utf-8")
    assert "diagnostic_context_detail_code" not in status
    assert "diagnostic_context_detail_code" not in (
        run_dir / "unapproved-proposal.md"
    ).read_text(encoding="utf-8")
    assert "diagnostic_context_shape_code" not in status
    assert "diagnostic_context_shape_code" not in (
        run_dir / "unapproved-proposal.md"
    ).read_text(encoding="utf-8")
    assert "diagnostic_fallback_code" not in status
    assert "diagnostic_fallback_code" not in (
        run_dir / "unapproved-proposal.md"
    ).read_text(encoding="utf-8")
    assert "diagnostic_fallback_entry_code" not in status
    assert "diagnostic_fallback_entry_code" not in (
        run_dir / "unapproved-proposal.md"
    ).read_text(encoding="utf-8")

    before_repeat = (run_dir / "run-record.v1.jsonl").read_bytes()
    repeat_code, repeat = orchestrator.resume(
        private_root=root,
        run_id=RUN_ID,
        fake_scenario=None,
    )
    assert repeat_code == 0
    assert repeat == result
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == before_repeat
    assert transport.calls.count(("browser_close", {})) == 1


def test_terminal_recovery_accepts_inert_heading_attributes_without_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    response = advice_text("Complete heading attributes are structural only.")
    stable = response_snapshot(
        response,
        heading_line=(
            '- heading "ChatGPT said:" [disabled] [level=2] [ref=e60] '
            '[busy=true] [aria-label="ready"]'
        ),
    )
    transport = RecoveryTransport([stable, stable, stable])
    install_transport(monkeypatch, root, transport)

    exit_code, result = orchestrator.resume(
        private_root=root,
        run_id=RUN_ID,
        fake_scenario=None,
    )

    assert exit_code == 0
    assert result["status"] == "ADVICE_CAPTURED"
    assert result["provenance"] == "AUTOMATED_BOUND_CONVERSATION_RECOVERY"
    assert result["resubmitted"] is False
    assert "diagnostic_code" not in result
    assert "diagnostic_detail_code" not in result
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes().startswith(record_before)
    events = event_list(run_dir)
    assert events[-1]["event_type"] == "BOUND_RESPONSE_RECOVERED"
    assert (
        sum(event["event_type"] == "SUBMISSION_INTENT_RECORDED" for event in events)
        == 1
    )
    proposal = (run_dir / "unapproved-proposal.md").read_text(encoding="utf-8")
    assert response in proposal
    assert "aria-label" not in proposal
    assert "busy=true" not in proposal
    assert transport.calls == [
        ("browser_navigate", {"url": CONVERSATION_URL}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_close", {}),
    ]
    assert_recovery_tools_only(transport)


def test_terminal_recovery_accepts_opaque_pre_content_actions_without_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    response = advice_text("Opaque pre-content actions do not alter the answer.")
    snapshots = [
        pre_content_response_snapshot(
            response,
            action_descendants=(
                '    - heading "ChatGPT said:" [ref=e60]',
                "    - generic [ref=e61]:",
                '      - text: "injected response"',
                '    - button "Answer now" [ref=e70]',
                '    - button "Answer now" [ref=e71]',
                '    - group "Response actions":',
                '      - statictext: "nested injected response"',
            ),
        ),
        pre_content_response_snapshot(
            response,
            action_descendants=(
                '    - heading "ChatGPT said:" [ref=e60]',
                "    - generic [ref=e61]:",
                '      - text: "changed injected response"',
                '    - button "Answer now" [ref=e170]',
                '    - button "Answer now" [ref=e171]',
                '    - group "Response actions":',
                '      - statictext: "changed nested injection"',
            ),
        ),
        pre_content_response_snapshot(
            response,
            action_descendants=(
                '    - alert "Too many requests" [ref=e60]',
                '    - link "Duplicate" [ref=e61]',
                '    - button "Copy" [ref=e80]',
                '    - link "Same ref" [ref=e80]',
                '    - text: "final injected response"',
            ),
        ),
    ]
    transport = RecoveryTransport(snapshots)
    install_transport(monkeypatch, root, transport)

    exit_code, result = orchestrator.resume(
        private_root=root,
        run_id=RUN_ID,
        fake_scenario=None,
    )

    assert exit_code == 0
    assert result["status"] == "ADVICE_CAPTURED"
    assert result["provenance"] == "AUTOMATED_BOUND_CONVERSATION_RECOVERY"
    assert result["resubmitted"] is False
    assert "diagnostic_code" not in result
    assert "diagnostic_detail_code" not in result
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes().startswith(record_before)
    events = event_list(run_dir)
    assert events[-1]["event_type"] == "BOUND_RESPONSE_RECOVERED"
    assert events[-1]["payload"]["resubmitted"] is False
    assert (
        sum(event["event_type"] == "SUBMISSION_INTENT_RECORDED" for event in events)
        == 1
    )
    proposal = (run_dir / "unapproved-proposal.md").read_text(encoding="utf-8")
    assert response in proposal
    for injected in (
        "injected response",
        "Answer now",
        "Too many requests",
        "nested injected response",
    ):
        assert injected not in proposal
    assert transport.calls == [
        ("browser_navigate", {"url": CONVERSATION_URL}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_close", {}),
    ]
    assert_recovery_tools_only(transport)
    assert not {"browser_click", "browser_type"} & {
        tool for tool, _arguments in transport.calls
    }


@pytest.mark.parametrize(
    ("continuation", "reason_code", "diagnostic_code", "detail_code"),
    [
        pytest.param(
            ('- text: "OUTSIDE"',),
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_CONTENT_AFTER",
            id="direct-text",
        ),
        pytest.param(
            ("- paragraph [ref=e90]:", '  - text: "OUTSIDE"'),
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_CONTENT_AFTER",
            id="semantic-paragraph",
        ),
        pytest.param(
            ("- generic [ref=e90]:", '  - text: "OUTSIDE"'),
            "RESPONSE_SELECTOR_AMBIGUITY",
            "ADVANCED_RESPONSE_BOUNDARY_CONFLICT",
            None,
            id="duplicate-generic-root",
        ),
        pytest.param(
            ('- widget "outside response":', '  - text: "OUTSIDE"'),
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_BOUNDARY_CONFLICT",
            None,
            id="unknown-container-with-response-content",
        ),
    ],
)
def test_terminal_recovery_refuses_post_boundary_response_continuation_without_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    continuation: tuple[str, ...],
    reason_code: str,
    diagnostic_code: str,
    detail_code: str | None,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    response = advice_text("Post-boundary content must never be truncated.")
    malformed = response_snapshot(
        response,
        extra_lines=(
            '- group "Response actions":',
            '  - button "Copy" [ref=e70]',
            *continuation,
        ),
    )
    transport = RecoveryTransport([malformed, malformed, malformed])
    install_transport(monkeypatch, root, transport)

    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert captured.value.code == reason_code
    assert captured.value.diagnostic_code == diagnostic_code
    if detail_code is None:
        assert not hasattr(captured.value, "diagnostic_detail_code")
    else:
        assert captured.value.diagnostic_detail_code == detail_code
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert (
        sum(
            event["event_type"] == "SUBMISSION_INTENT_RECORDED"
            for event in event_list(run_dir)
        )
        == 1
    )
    assert_recovery_tools_only(transport)
    assert not {"browser_click", "browser_type"} & {
        tool for tool, _arguments in transport.calls
    }


def test_delayed_recovery_progress_keeps_terminal_state_and_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    loading = f'- Page URL: {CONVERSATION_URL}\n- status "loading" [ref=e90]'
    stable = response_snapshot(advice_text("Delayed response recovered once."))
    transport = RecoveryTransport([*[loading] * 13, stable, stable, stable])
    install_transport(monkeypatch, root, transport)

    exit_code, result = orchestrator.resume(
        private_root=root,
        run_id=RUN_ID,
        fake_scenario=None,
    )

    assert exit_code == 0
    assert result["status"] == "ADVICE_CAPTURED"
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    events = event_list(run_dir)
    progress = [
        event for event in events if event["event_type"] == "RESPONSE_WAIT_PROGRESS"
    ]
    assert [
        (
            event["payload"]["elapsed_seconds"],
            event["payload"]["poll_count"],
            event["payload"]["phase"],
        )
        for event in progress
    ] == [(60, 12, "response_absent")]
    terminal_hash = next(
        event["payload"]["state_sha256"]
        for event in events
        if event["event_type"] == "PRO_UNAVAILABLE"
    )
    assert {event["payload"]["state_sha256"] for event in progress} == {terminal_hash}
    assert events[-1]["event_type"] == "BOUND_RESPONSE_RECOVERED"
    assert_recovery_tools_only(transport)


def test_recovered_response_fingerprint_is_inherited_by_named_gap_follow_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    response = advice_text("Recovered response must participate in convergence.")
    stable = response_snapshot(response)
    transport = RecoveryTransport([stable, stable, stable])
    install_transport(monkeypatch, root, transport)

    exit_code, recovered = orchestrator.resume(
        private_root=root,
        run_id=RUN_ID,
        fake_scenario=None,
    )

    assert exit_code == 0
    assert recovered["status"] == "ADVICE_CAPTURED"
    recovered_fingerprint = event_list(run_dir)[-1]["payload"]["response_fingerprint"]
    request_root = root / "chatgpt-pro-requests"
    request_file = request_root / "recovered-follow-up.txt"
    gap_file = request_root / "recovered-gap.txt"
    request_file.write_text("Resolve the one named recovered gap.", encoding="utf-8")
    gap_file.write_text("One named gap remains.", encoding="utf-8")
    request_file.chmod(0o600)
    gap_file.chmod(0o600)

    _prepared, child_state = orchestrator._prepare_orchestration_run(
        private_root=root,
        request_file=request_file,
        importance="ordinary",
        parent_run_id=RUN_ID,
        gap_file=gap_file,
        mode="LOCAL_FIXTURE",
        browser="edge",
    )

    assert child_state["response_fingerprints"] == [recovered_fingerprint]
    advice = orchestrator._validate_advice(response)
    event_type = orchestrator._apply_capture_outcome(
        state=child_state,
        advice=advice,
        response_fingerprint=recovered_fingerprint,
        transcript_hash="c" * 64,
    )
    assert event_type == "ORCHESTRATION_COMPLETED"
    assert child_state["status"] == "CONVERGED_DUPLICATE_RESPONSE"
    assert child_state["next_action"] == "STOP"


@pytest.mark.parametrize(
    ("failure", "expected_exception"),
    [
        pytest.param(
            orchestrator.TransportUnavailable("MCP_DISCONNECTED"),
            orchestrator.TransportUnavailable,
            id="transport-loss",
        ),
        pytest.param(KeyboardInterrupt(), KeyboardInterrupt, id="interrupt"),
    ],
)
def test_failed_recovery_retains_terminal_state_and_proposal_absence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
    expected_exception: type[BaseException],
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    transport = RecoveryTransport([failure])
    install_transport(monkeypatch, root, transport)

    with pytest.raises(expected_exception):
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert_recovery_tools_only(transport)


def test_failure_after_progress_keeps_verified_tail_eligible_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    loading = f'- Page URL: {CONVERSATION_URL}\n- status "loading" [ref=e90]'
    first = RecoveryTransport(
        [*[loading] * 13, orchestrator.TransportUnavailable("MCP_DISCONNECTED")]
    )
    install_transport(monkeypatch, root, first)

    with pytest.raises(orchestrator.TransportUnavailable):
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    events_after_failure = event_list(run_dir)
    assert events_after_failure[-1]["event_type"] == "RESPONSE_WAIT_PROGRESS"
    assert events_after_failure[-1]["payload"]["state_sha256"] == next(
        event["payload"]["state_sha256"]
        for event in events_after_failure
        if event["event_type"] == "PRO_UNAVAILABLE"
    )
    assert not (run_dir / "unapproved-proposal.md").exists()

    stable = response_snapshot("Retry recovers without another submission.")
    second = RecoveryTransport([stable, stable, stable])
    install_transport(monkeypatch, root, second)
    exit_code, result = orchestrator.resume(
        private_root=root,
        run_id=RUN_ID,
        fake_scenario=None,
    )

    assert exit_code == 0
    assert result["status"] == "REVIEW_CAPTURED"
    assert event_list(run_dir)[-1]["event_type"] == "BOUND_RESPONSE_RECOVERED"
    assert_recovery_tools_only(first)
    assert_recovery_tools_only(second)


def test_parser_failure_after_stable_snapshot_creates_no_proposal_or_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    malformed = response_snapshot("Visible", extra_lines=("    - text: unquoted",))
    transport = RecoveryTransport([malformed])
    install_transport(monkeypatch, root, transport)
    monkeypatch.setattr(
        orchestrator,
        "_wait_for_stable_response_snapshot",
        lambda _transport, current, **_kwargs: (current, CONVERSATION_URL),
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert_recovery_tools_only(transport)


def test_orphan_proposal_is_status_invisible_then_committed_without_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    stable = response_snapshot(advice_text("Commit the exact orphan on retry."))
    transport = RecoveryTransport([stable, stable, stable])
    install_transport(monkeypatch, root, transport)
    original_append = workflow._append_event

    def fail_bound_event(
        record_path: Path,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> str:
        if event_type == "BOUND_RESPONSE_RECOVERED":
            raise workflow.WorkflowRefusal("RUN_RECORD_WRITE_FAILED")
        return original_append(record_path, run_id, event_type, payload)

    monkeypatch.setattr(workflow, "_append_event", fail_bound_event)
    with pytest.raises(workflow.WorkflowRefusal):
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )
    proposal_before = (run_dir / "unapproved-proposal.md").read_bytes()
    status = orchestrator.status(private_root=root, run_id=RUN_ID)
    assert status["status"] == "PRO_UNAVAILABLE_FALLBACK"
    assert status["advice_type"] is None
    assert "provenance" not in status

    monkeypatch.setattr(workflow, "_append_event", original_append)

    def no_second_transport(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("validated orphan retry must not launch a browser")

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", no_second_transport)
    exit_code, recovered = orchestrator.resume(
        private_root=root,
        run_id=RUN_ID,
        fake_scenario=None,
    )

    assert exit_code == 0
    assert recovered["status"] == "ADVICE_CAPTURED"
    assert (run_dir / "unapproved-proposal.md").read_bytes() == proposal_before
    assert event_list(run_dir)[-1]["event_type"] == "BOUND_RESPONSE_RECOVERED"


def test_mismatching_orphan_refuses_before_browser_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    proposal = run_dir / "unapproved-proposal.md"
    proposal.write_text("not the exact automatic proposal\n", encoding="utf-8")
    proposal.chmod(0o600)

    def unexpected_transport(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid orphan must fail before browser launch")

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", unexpected_transport)
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )
    assert captured.value.code == "RUN_NOT_RESUMABLE"


def test_wrong_url_and_mismatched_progress_hash_refuse_before_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, state = create_terminal_run(root)
    orchestrator._append_terminal_response_wait_progress(
        run_dir=run_dir,
        state=state,
        conversation_url=CONVERSATION_URL,
        elapsed_seconds=60,
        poll_count=12,
        phase="response_absent",
    )
    state_path = run_dir / "orchestration-state.v1.json"
    changed = json.loads(state_path.read_text(encoding="utf-8"))
    changed["conversation_url"] = "https://chatgpt.com/c/substituted-conversation"
    state_path.write_bytes(orchestrator._canonical_json(changed) + b"\n")
    final = event_list(run_dir)[-1]
    final["payload"]["state_sha256"] = hashlib.sha256(
        orchestrator._canonical_json(changed)
    ).hexdigest()
    without_hash = dict(final)
    without_hash.pop("event_sha256")
    final["event_sha256"] = hashlib.sha256(
        orchestrator._canonical_json(without_hash)
    ).hexdigest()
    lines = event_list(run_dir)
    lines[-1] = final
    (run_dir / "run-record.v1.jsonl").write_text(
        "".join(
            json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n"
            for item in lines
        ),
        encoding="utf-8",
    )

    def unexpected_transport(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("binding mismatch must fail before browser launch")

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", unexpected_transport)
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )
    assert captured.value.code == "RUN_NOT_RESUMABLE"


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda state: state.update(mode="LOCAL_FIXTURE"), id="non-live"),
        pytest.param(lambda state: state.update(browser="chrome"), id="wrong-browser"),
        pytest.param(
            lambda state: state.update(submission_attempted=False),
            id="submission-not-attempted",
        ),
    ],
)
def test_wrong_bound_state_refuses_before_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_path = run_dir / "orchestration-state.v1.json"
    changed = json.loads(state_path.read_text(encoding="utf-8"))
    mutate(changed)
    state_path.write_bytes(orchestrator._canonical_json(changed) + b"\n")

    def unexpected_transport(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid state must fail before browser launch")

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", unexpected_transport)
    with pytest.raises(orchestrator.OrchestrationRefusal):
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )


def test_duplicate_submission_intent_refuses_before_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    _run_dir, _state = create_terminal_run(root, submission_intents=2)

    def unexpected_transport(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("duplicate intent must fail before browser launch")

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", unexpected_transport)
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )
    assert captured.value.code == "RUN_NOT_RESUMABLE"


def test_missing_submission_intent_refuses_before_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    _run_dir, _state = create_terminal_run(root, submission_intents=0)

    def unexpected_transport(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("missing intent must fail before browser launch")

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", unexpected_transport)
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )
    assert captured.value.code == "RUN_NOT_RESUMABLE"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("status", "SUBMITTED", id="wrong-status"),
        pytest.param("origin", "https://example.invalid", id="wrong-origin"),
        pytest.param("model_label", "Instant", id="wrong-model"),
        pytest.param("effort_label", "Standard", id="wrong-effort"),
        pytest.param("prompt_sha256", "f" * 64, id="wrong-prompt-hash"),
    ],
)
def test_malformed_submission_intent_refuses_before_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)

    def mutate(events: list[dict[str, Any]]) -> None:
        intent = next(
            event
            for event in events
            if event["event_type"] == "SUBMISSION_INTENT_RECORDED"
        )
        intent["payload"][field] = value

    rewrite_record(run_dir, mutate)

    def unexpected_transport(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid intent must fail before browser launch")

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", unexpected_transport)
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )
    assert captured.value.code == "RUN_NOT_RESUMABLE"


def test_wrong_terminal_reason_refuses_before_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    _run_dir, _state = create_terminal_run(root, reason_code="STOP_CAPTCHA")

    def unexpected_transport(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("wrong reason must fail before browser launch")

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", unexpected_transport)
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )
    assert captured.value.code == "RUN_NOT_RESUMABLE"


@pytest.mark.parametrize(
    ("bad_snapshot", "expected_code"),
    [
        pytest.param(
            response_snapshot(advice_text(), url="https://chatgpt.com/c/other"),
            "LIVE_RESUME_SCOPE",
            id="different-bound-conversation",
        ),
        pytest.param(
            response_snapshot(advice_text(), url="https://example.invalid/c/other"),
            "ORIGIN_MISMATCH",
            id="wrong-origin",
        ),
        pytest.param(
            "\n".join(
                (
                    f"- Page URL: {CONVERSATION_URL}",
                    '- alert "Too many requests" [ref=e90]',
                )
            ),
            "STOP_RATE_LIMIT",
            id="structural-stop",
        ),
    ],
)
def test_recovery_observation_scope_refuses_without_proposal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_snapshot: str,
    expected_code: str,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    before = (run_dir / "run-record.v1.jsonl").read_bytes()
    transport = RecoveryTransport([bad_snapshot])
    install_transport(monkeypatch, root, transport)

    with pytest.raises(
        (orchestrator.OrchestrationRefusal, workflow.WorkflowRefusal)
    ) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert captured.value.code == expected_code
    assert not isinstance(captured.value, orchestrator._BoundResponseRecoveryRefusal)
    assert not hasattr(captured.value, "diagnostic_code")
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert_recovery_tools_only(transport)


@pytest.mark.parametrize(
    "response",
    [
        pytest.param("Review with trailing spaces.   ", id="trailing-spaces"),
        pytest.param("Review with trailing newlines.\n\n", id="trailing-newlines"),
        pytest.param(
            "Review body.\n\n## Captured response\n\nNested heading is content.",
            id="proposal-marker-in-review-body",
        ),
    ],
)
def test_bound_proposal_round_trips_its_exact_canonical_body(response: str) -> None:
    prepared = {
        "run_id": RUN_ID,
        "prompt_sha256": "a" * 64,
    }
    proposal, advice, fingerprint, response_hash = (
        orchestrator._bound_response_proposal(prepared=prepared, response=response)
    )

    validated = orchestrator._validated_bound_response_proposal(
        prepared=prepared,
        proposal=proposal,
    )

    assert validated == (advice, fingerprint, response_hash)
    stored_body = proposal.split(b"\n## Captured response\n\n", 1)[1][:-1]
    assert response_hash == hashlib.sha256(stored_body).hexdigest()


def test_orphan_self_declared_response_hash_is_never_trusted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    proposal, _advice, _fingerprint, response_hash = (
        orchestrator._bound_response_proposal(
            prepared={"run_id": RUN_ID, "prompt_sha256": "a" * 64},
            response="Exact orphan review.",
        )
    )
    forged = proposal.replace(response_hash.encode(), b"f" * 64, 1)
    proposal_path = run_dir / "unapproved-proposal.md"
    proposal_path.write_bytes(forged)
    proposal_path.chmod(0o600)

    def unexpected_transport(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("forged orphan must fail before browser launch")

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", unexpected_transport)
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )
    assert captured.value.code == "RUN_NOT_RESUMABLE"


def test_manual_import_remains_available_after_verified_recovery_progress_tail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, state = create_terminal_run(root)
    orchestrator._append_terminal_response_wait_progress(
        run_dir=run_dir,
        state=state,
        conversation_url=CONVERSATION_URL,
        elapsed_seconds=60,
        poll_count=12,
        phase="response_absent",
    )
    response_path = root / "chatgpt-pro-responses" / "response.txt"
    response_path.write_text("Human-copied fallback review.", encoding="utf-8")
    response_path.chmod(0o600)

    def unexpected_transport(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("manual import must never launch a browser")

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", unexpected_transport)
    exit_code, result = orchestrator.import_response(
        private_root=root,
        run_id=RUN_ID,
        response_file=response_path,
    )

    assert exit_code == 0
    assert result["provenance"] == "HUMAN_COPIED_DISPLAYED_RESPONSE"
    assert result["resubmitted"] is False
    events = event_list(run_dir)
    assert events[-2]["event_type"] == "RESPONSE_WAIT_PROGRESS"
    assert events[-1]["event_type"] == "MANUAL_RESPONSE_IMPORTED"


@pytest.mark.parametrize("tamper", ["proposal-bytes", "proposal-mode"])
def test_status_rejects_committed_recovery_proposal_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    stable = response_snapshot("Committed recovery proposal.")
    transport = RecoveryTransport([stable, stable, stable])
    install_transport(monkeypatch, root, transport)
    orchestrator.resume(private_root=root, run_id=RUN_ID, fake_scenario=None)
    proposal_path = run_dir / "unapproved-proposal.md"
    if tamper == "proposal-bytes":
        proposal_path.write_bytes(proposal_path.read_bytes() + b"tamper\n")
    else:
        proposal_path.chmod(0o644)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.status(private_root=root, run_id=RUN_ID)

    assert captured.value.code == "STATE_INVALID"


def test_event_after_committed_recovery_is_not_a_valid_progress_tail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, state = create_terminal_run(root)
    stable = response_snapshot("Committed recovery has no later progress.")
    transport = RecoveryTransport([stable, stable, stable])
    install_transport(monkeypatch, root, transport)
    orchestrator.resume(private_root=root, run_id=RUN_ID, fake_scenario=None)
    orchestrator._append_terminal_response_wait_progress(
        run_dir=run_dir,
        state=state,
        conversation_url=CONVERSATION_URL,
        elapsed_seconds=60,
        poll_count=12,
        phase="response_absent",
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.status(private_root=root, run_id=RUN_ID)

    assert captured.value.code == "STATE_INVALID"


def diagnostic_snapshot(*lines: str) -> str:
    return "\n".join((f"- Page URL: {CONVERSATION_URL}", *lines))


EXPECTED_BOUND_RESPONSE_RECOVERY_DIAGNOSTIC_CODES = frozenset(
    {
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_BODY_ROOT_ABSENT",
        "ADVANCED_RESPONSE_BODY_ROOT_INVALID",
        "ADVANCED_RESPONSE_BOUNDARY_CONFLICT",
        "ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID",
        "ADVANCED_RESPONSE_GENERATING_MARKER_DUPLICATION",
        "ADVANCED_RESPONSE_HEADING_INVALID",
        "ADVANCED_RESPONSE_MARKER_CONFLICT",
        "ADVANCED_RESPONSE_STRUCTURAL_REF_COLLISION",
    }
)

EXPECTED_BOUND_RESPONSE_HEADING_DETAIL_CODES = frozenset(
    {
        "ADVANCED_RESPONSE_HEADING_ROLE_INVALID",
        "ADVANCED_RESPONSE_HEADING_LABEL_CASE_INVALID",
        "ADVANCED_RESPONSE_HEADING_LABEL_PUNCTUATION_INVALID",
        "ADVANCED_RESPONSE_HEADING_LABEL_EDGE_WHITESPACE_INVALID",
        "ADVANCED_RESPONSE_HEADING_LABEL_OTHER_INVALID",
        "ADVANCED_RESPONSE_HEADING_REF_MISSING",
        "ADVANCED_RESPONSE_HEADING_REF_INVALID",
        "ADVANCED_RESPONSE_HEADING_EXTRA_ATTRIBUTES",
        "ADVANCED_RESPONSE_HEADING_LINE_SHAPE_INVALID",
    }
)

EXPECTED_BOUND_RESPONSE_ACTION_DETAIL_CODES = frozenset(
    {
        "ADVANCED_RESPONSE_ACTION_ROLE_INVALID",
        "ADVANCED_RESPONSE_ACTION_LABEL_INVALID",
        "ADVANCED_RESPONSE_ACTION_REF_PRESENT",
        "ADVANCED_RESPONSE_ACTION_EXTRA_ATTRIBUTES",
        "ADVANCED_RESPONSE_ACTION_LINE_SHAPE_INVALID",
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "ADVANCED_RESPONSE_ACTION_DUPLICATE",
        "ADVANCED_RESPONSE_ACTION_CONTENT_AFTER",
        "ADVANCED_RESPONSE_ACTION_PLACEMENT_INVALID",
    }
)

EXPECTED_BOUND_RESPONSE_PRECONTENT_CONTEXT_CODES = frozenset(
    {
        "ADVANCED_RESPONSE_PRECONTENT_SAME_INDENT_BOUNDARY",
        "ADVANCED_RESPONSE_PRECONTENT_SHALLOW_BOUNDARY",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_ONLY_OPAQUE",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY",
    }
)

EXPECTED_BOUND_RESPONSE_PRECONTENT_CONTEXT_DETAIL_CODES = frozenset(
    {
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_VALUE_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_CONTEXT_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_UNSATISFIED_WITH_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_UNSATISFIED_EMPTY",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_MATERIAL_UNSUPPORTED",
    }
)

EXPECTED_BOUND_RESPONSE_PRECONTENT_CONTEXT_SHAPE_CODES = frozenset(
    {
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_LINE_SHAPE_INVALID",
    }
)

EXPECTED_BOUND_RESPONSE_REF_FREE_FALLBACK_CODES = frozenset(
    {
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_SCALAR_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_MATERIAL_UNSUPPORTED",
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_REF_COLLISION",
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_UNSATISFIED_WITH_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_UNSATISFIED_EMPTY",
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_CONTENT_EMPTY",
    }
)

EXPECTED_BOUND_RESPONSE_REF_FREE_FALLBACK_ENTRY_CODES = frozenset(
    {
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR",
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_PRESENTATION_WRAPPER",
    }
)


def ref_free_fallback_snapshot(*descendants: str) -> str:
    return diagnostic_snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - generic [ref=e62]:",
        '    - group "Response actions":',
        *descendants,
    )


ADVANCED_RESPONSE_REF_FREE_FALLBACK_CASES = (
    pytest.param(
        ref_free_fallback_snapshot(
            "      - paragraph:",
            '        - text: "Visible"',
            "      - Generic: residual",
        ),
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID",
        id="wrapper-invalid",
    ),
    pytest.param(
        ref_free_fallback_snapshot(
            "      - paragraph:",
            '        - text: "Visible"',
            "      - text: unquoted",
        ),
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_SCALAR_INVALID",
        id="scalar-invalid",
    ),
    pytest.param(
        ref_free_fallback_snapshot(
            "      - paragraph:",
            '        - text: "Visible"',
            '      - widget: "unsupported"',
        ),
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_MATERIAL_UNSUPPORTED",
        id="material-unsupported",
    ),
    pytest.param(
        ref_free_fallback_snapshot(
            "      - generic:",
            '        - text: "Entry"',
            "      - paragraph [ref=e70]:",
            '        - text: "A"',
            "      - quote [ref=e70]:",
            '        - text: "B"',
        ),
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_REF_COLLISION",
        id="ref-collision",
    ),
    pytest.param(
        ref_free_fallback_snapshot(
            "      - paragraph:",
            "      - quote:",
            '        - text: "Visible"',
        ),
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_UNSATISFIED_WITH_CONTENT",
        id="unsatisfied-with-content",
    ),
    pytest.param(
        ref_free_fallback_snapshot("      - paragraph:"),
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_UNSATISFIED_EMPTY",
        id="unsatisfied-empty",
    ),
    pytest.param(
        ref_free_fallback_snapshot(
            "      - paragraph:",
            '        - text: "   "',
        ),
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_CONTENT_EMPTY",
        id="content-empty",
    ),
)

ADVANCED_RESPONSE_REF_FREE_FALLBACK_ENTRY_CASES = (
    pytest.param(
        embedded_pre_content_response_snapshot(
            advice_text("Entry suppression by an outside whitespace scalar."),
            before_group=('    - statictext: "   "',),
        ),
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR",
        id="outside-whitespace-scalar",
    ),
    pytest.param(
        embedded_pre_content_response_snapshot(
            advice_text("Entry suppression by an outside presentation wrapper."),
            before_group=("    - paragraph [ref=e80] [REF=e81]:",),
        ),
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_PRESENTATION_WRAPPER",
        id="outside-presentation-wrapper",
    ),
)

ADVANCED_RESPONSE_PRECONTENT_CONTAINER_SHAPE_CASES = (
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            '    - paragraph "ref-free label" [disabled] [level=2]:',
        ),
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
        id="ref-missing",
    ),
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            "    - generic [ref=bad]:",
        ),
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID",
        id="ref-invalid",
    ),
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            "    - generic: trailing",
        ),
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_LINE_SHAPE_INVALID",
        id="line-shape-invalid",
    ),
)

ADVANCED_RESPONSE_PRECONTENT_CONTEXT_CASES = (
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '- group "Response actions":',
        ),
        "ADVANCED_RESPONSE_PRECONTENT_SAME_INDENT_BOUNDARY",
        id="same-indent-boundary",
    ),
    pytest.param(
        diagnostic_snapshot(
            '- region "response" [ref=e50]:',
            '  - heading "ChatGPT said:" [ref=e60]',
            "  - generic [ref=e61]:",
            '- group "Response actions":',
        ),
        "ADVANCED_RESPONSE_PRECONTENT_SHALLOW_BOUNDARY",
        id="shallow-boundary",
    ),
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            "    - generic [ref=e70]:",
            '      - text: "hidden response material"',
        ),
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_CONTENT",
        id="nested-descendant-content",
    ),
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            "    - generic [ref=e70]:",
        ),
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
        id="nested-descendant-invalid",
    ),
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            '    - button "Copy" [ref=e70]:',
            '      - text: "opaque injection"',
        ),
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_ONLY_OPAQUE",
        id="nested-only-opaque",
    ),
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            "    - text:",
        ),
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_ONLY_OPAQUE",
        id="bare-text-container-preserves-opaque-context",
    ),
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            "    - statictext:\t",
        ),
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_ONLY_OPAQUE",
        id="bare-statictext-container-with-whitespace-preserves-opaque-context",
    ),
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
        ),
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY",
        id="nested-empty",
    ),
)

ADVANCED_RESPONSE_PRECONTENT_INVALID_DETAIL_CASES = (
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            '    - Text: "wrong role"',
        ),
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID",
        id="scalar-shape-invalid",
    ),
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            "    - text: 123",
        ),
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_VALUE_INVALID",
        id="scalar-value-invalid",
    ),
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            "    - generic:",
        ),
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
        id="container-shape-invalid",
    ),
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            "    - generic [ref=e70]:",
            '    - text: "valid sibling content"',
        ),
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_UNSATISFIED_WITH_CONTENT",
        id="unsatisfied-container-with-content",
    ),
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            "    - generic [ref=e70]:",
        ),
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_UNSATISFIED_EMPTY",
        id="unsatisfied-container-empty",
    ),
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            '    - widget: "unsupported scalar"',
        ),
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_MATERIAL_UNSUPPORTED",
        id="unsupported-material",
    ),
)

ADVANCED_RESPONSE_HEADING_DETAIL_CASES = (
    pytest.param(
        '- article "ChatGPT said:" [ref=e60]',
        "ADVANCED_RESPONSE_HEADING_ROLE_INVALID",
        id="role-invalid",
    ),
    pytest.param(
        '- heading "chatgpt said:" [ref=e60]',
        "ADVANCED_RESPONSE_HEADING_LABEL_CASE_INVALID",
        id="label-case-invalid",
    ),
    pytest.param(
        '- heading "ChatGPT said" [ref=e60]',
        "ADVANCED_RESPONSE_HEADING_LABEL_PUNCTUATION_INVALID",
        id="label-punctuation-invalid",
    ),
    pytest.param(
        '- heading " ChatGPT said: " [ref=e60]',
        "ADVANCED_RESPONSE_HEADING_LABEL_EDGE_WHITESPACE_INVALID",
        id="label-edge-whitespace-invalid",
    ),
    pytest.param(
        '- heading "Assistant response" [ref=e60]',
        "ADVANCED_RESPONSE_HEADING_LABEL_OTHER_INVALID",
        id="label-other-invalid",
    ),
    pytest.param(
        '- heading "ChatGPT said:"',
        "ADVANCED_RESPONSE_HEADING_REF_MISSING",
        id="ref-missing",
    ),
    pytest.param(
        '- heading "ChatGPT said:" [ref=invalid]',
        "ADVANCED_RESPONSE_HEADING_REF_INVALID",
        id="ref-invalid",
    ),
    pytest.param(
        '- heading "ChatGPT said:" [ref=e60]:',
        "ADVANCED_RESPONSE_HEADING_LINE_SHAPE_INVALID",
        id="line-shape-invalid",
    ),
)

HEADING_DETAIL_BODY = (
    "- generic [ref=e61]:",
    "  - paragraph [ref=e62]:",
    '    - text: "Visible"',
)

ACTION_DETAIL_PREFIX = (
    '- heading "ChatGPT said:" [ref=e60]',
    "- generic [ref=e61]:",
    "  - paragraph [ref=e62]:",
    '    - text: "Visible"',
)

ADVANCED_RESPONSE_ACTION_DETAIL_CASES = (
    pytest.param(
        diagnostic_snapshot(*ACTION_DETAIL_PREFIX, '- Group "Response actions":'),
        "ADVANCED_RESPONSE_ACTION_ROLE_INVALID",
        id="role-invalid",
    ),
    pytest.param(
        diagnostic_snapshot(
            *ACTION_DETAIL_PREFIX,
            '- group "response actions":',
        ),
        "ADVANCED_RESPONSE_ACTION_LABEL_INVALID",
        id="label-invalid",
    ),
    pytest.param(
        diagnostic_snapshot(
            *ACTION_DETAIL_PREFIX,
            '- group "Response actions" [ref=e70]:',
        ),
        "ADVANCED_RESPONSE_ACTION_REF_PRESENT",
        id="ref-present",
    ),
    pytest.param(
        diagnostic_snapshot(
            *ACTION_DETAIL_PREFIX,
            '- group "Response actions" [disabled] [busy=true]:',
        ),
        "ADVANCED_RESPONSE_ACTION_EXTRA_ATTRIBUTES",
        id="extra-attributes",
    ),
    pytest.param(
        diagnostic_snapshot(
            *ACTION_DETAIL_PREFIX,
            '- group "Response actions": unexpected',
        ),
        "ADVANCED_RESPONSE_ACTION_LINE_SHAPE_INVALID",
        id="line-shape-invalid",
    ),
    pytest.param(
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
        ),
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        id="pre-content-without-later-content",
    ),
    pytest.param(
        diagnostic_snapshot(
            *ACTION_DETAIL_PREFIX,
            '  - group "Response actions":',
            '  - group "Response actions":',
        ),
        "ADVANCED_RESPONSE_ACTION_DUPLICATE",
        id="duplicate",
    ),
    pytest.param(
        diagnostic_snapshot(
            *ACTION_DETAIL_PREFIX,
            '  - group "Response actions":',
            "  - paragraph [ref=e70]:",
            '    - text: "After"',
        ),
        "ADVANCED_RESPONSE_ACTION_CONTENT_AFTER",
        id="content-after",
    ),
)


ADVANCED_RESPONSE_DIAGNOSTIC_CASES = (
    pytest.param(
        "candidate",
        diagnostic_snapshot(
            '- button "Answer now" [ref=e50]',
            '- button "Answer now" [ref=e51]',
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_GENERATING_MARKER_DUPLICATION",
        id="generating-marker-duplication",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            '- heading "ChatGPT said:" [ref=e70]',
            "- generic [ref=e61]:",
            "  - paragraph [ref=e62]:",
            '    - text: "Visible"',
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_MARKER_CONFLICT",
        id="response-marker-conflict",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e60]:",
            "  - paragraph [ref=e62]:",
            '    - text: "Visible"',
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_STRUCTURAL_REF_COLLISION",
        id="structural-ref-collision",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "chatgpt said:" [ref=e60]',
            "- generic [ref=e61]:",
            "  - paragraph [ref=e62]:",
            '    - text: "Visible"',
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_HEADING_INVALID",
        id="exact-heading-invalidity",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot('- heading "ChatGPT said:" [ref=e60]'),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_BODY_ROOT_ABSENT",
        id="body-root-absence",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic:",
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_BODY_ROOT_INVALID",
        id="ref-free-body-root-invalidity",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=bad]:",
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_BODY_ROOT_INVALID",
        id="malformed-ref-body-root-invalidity",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "body root missing",
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_BODY_ROOT_INVALID",
        id="unparsed-scalar-body-root-invalidity",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            '- generic "raw-dynamic-label" [ref=e61]:',
            "  - paragraph [ref=e62]:",
            '    - text: "Visible"',
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_BODY_ROOT_INVALID",
        id="body-root-invalidity",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            "  - paragraph [ref=e62]:",
            '    - text: "Visible"',
            "- paragraph [ref=e70]:",
            '  - text: "OUTSIDE"',
        ),
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_BOUNDARY_CONFLICT",
        id="boundary-conflict",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - group "Response actions":',
            '    - button "Copy" [ref=e70]',
        ),
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        id="action-boundary-invalidity",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            "  - paragraph [ref=e62]:",
            "    - text: unquoted",
        ),
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID",
        id="bounded-content-invalidity",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- article "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - text: "Visible"',
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_HEADING_INVALID",
        id="wrong-role-heading-invalidity",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said" [ref=e60]',
            "- generic [ref=e61]:",
            '  - text: "Visible"',
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_HEADING_INVALID",
        id="wrong-punctuation-heading-invalidity",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - text: "Visible"',
            '- article "Assistant response" [ref=e70]',
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_MARKER_CONFLICT",
        id="competing-legacy-response-marker",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - text: "Visible"',
            '- article "Assistant answer" [ref=e70]',
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_MARKER_CONFLICT",
        id="competing-legacy-substring-anchor",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            "  - paragraph [ref=e62]:",
            '    - text: "Visible"',
            '  - button "Copy" [ref=e60]',
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_STRUCTURAL_REF_COLLISION",
        id="opaque-heading-ref-collision",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60] [ref=e70]',
            "- generic [ref=e61]:",
            '  - text: "Visible"',
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_HEADING_INVALID",
        id="multiple-heading-ref-heading-invalidity",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            '- article "body" [ref=e61]:',
            '  - text: "Visible"',
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_BODY_ROOT_INVALID",
        id="wrong-role-body-root-invalidity",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- intervening scalar material",
            "- generic [ref=e61]:",
            '  - text: "Visible"',
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_BODY_ROOT_INVALID",
        id="intervening-body-root-invalidity",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - text: "Visible"',
            "- generic [ref=e70]:",
        ),
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_BOUNDARY_CONFLICT",
        id="duplicate-body-boundary-conflict",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - text: "Visible"',
            '- Group "Response actions":',
        ),
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        id="malformed-boundary-action-group",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            "  - paragraph [ref=e62]:",
            '    - text: "Before"',
            '  - group "Response actions":',
            '    - button "Copy" [ref=e70]',
            "  - paragraph [ref=e71]:",
            '    - text: "After"',
        ),
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        id="content-after-action-boundary",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            "  - paragraph [ref=e62]:",
            '    - text: "unterminated',
        ),
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID",
        id="malformed-json-bounded-content",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            "  - paragraph [ref=e62]:",
            '    - widget: "arbitrary scalar"',
            '    - text: "Visible"',
        ),
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID",
        id="unknown-scalar-bounded-content",
    ),
    pytest.param(
        "completed",
        diagnostic_snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            '  - text: ""',
        ),
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID",
        id="empty-bounded-content",
    ),
)


def test_bound_response_recovery_diagnostic_allowlist_is_exact_and_covered() -> None:
    assert (
        orchestrator.BOUND_RESPONSE_RECOVERY_DIAGNOSTIC_CODES
        == EXPECTED_BOUND_RESPONSE_RECOVERY_DIAGNOSTIC_CODES
    )
    assert {
        case.values[3] for case in ADVANCED_RESPONSE_DIAGNOSTIC_CASES
    } == EXPECTED_BOUND_RESPONSE_RECOVERY_DIAGNOSTIC_CODES


def test_bound_response_heading_detail_allowlist_is_exact_and_reachable() -> None:
    assert (
        orchestrator.BOUND_RESPONSE_HEADING_DETAIL_CODES
        == EXPECTED_BOUND_RESPONSE_HEADING_DETAIL_CODES
    )
    assert {
        case.values[1] for case in ADVANCED_RESPONSE_HEADING_DETAIL_CASES
    } == EXPECTED_BOUND_RESPONSE_HEADING_DETAIL_CODES - {
        "ADVANCED_RESPONSE_HEADING_EXTRA_ATTRIBUTES"
    }
    assert (
        orchestrator._validated_bound_response_heading_detail_code(
            "ADVANCED_RESPONSE_HEADING_EXTRA_ATTRIBUTES"
        )
        == "ADVANCED_RESPONSE_HEADING_EXTRA_ATTRIBUTES"
    )


def test_bound_response_action_detail_allowlist_is_exact_with_reserved_placement() -> (
    None
):
    assert (
        orchestrator.BOUND_RESPONSE_ACTION_DETAIL_CODES
        == EXPECTED_BOUND_RESPONSE_ACTION_DETAIL_CODES
    )
    assert {
        case.values[1] for case in ADVANCED_RESPONSE_ACTION_DETAIL_CASES
    } == EXPECTED_BOUND_RESPONSE_ACTION_DETAIL_CODES - {
        "ADVANCED_RESPONSE_ACTION_PLACEMENT_INVALID"
    }
    assert (
        orchestrator._validated_bound_response_action_detail_code(
            "ADVANCED_RESPONSE_ACTION_PLACEMENT_INVALID"
        )
        == "ADVANCED_RESPONSE_ACTION_PLACEMENT_INVALID"
    )


def test_bound_response_precontent_context_allowlist_is_exact_and_covered() -> None:
    assert (
        orchestrator.BOUND_RESPONSE_PRECONTENT_CONTEXT_CODES
        == EXPECTED_BOUND_RESPONSE_PRECONTENT_CONTEXT_CODES
    )
    assert {
        case.values[1] for case in ADVANCED_RESPONSE_PRECONTENT_CONTEXT_CASES
    } == EXPECTED_BOUND_RESPONSE_PRECONTENT_CONTEXT_CODES


def test_bound_response_precontent_context_detail_allowlist_is_exact_with_reserved_context() -> (
    None
):
    assert (
        orchestrator.BOUND_RESPONSE_PRECONTENT_CONTEXT_DETAIL_CODES
        == EXPECTED_BOUND_RESPONSE_PRECONTENT_CONTEXT_DETAIL_CODES
    )
    assert {
        case.values[1] for case in ADVANCED_RESPONSE_PRECONTENT_INVALID_DETAIL_CASES
    } == EXPECTED_BOUND_RESPONSE_PRECONTENT_CONTEXT_DETAIL_CODES - {
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_CONTEXT_INVALID"
    }
    assert (
        orchestrator._validated_bound_response_precontent_context_detail_code(
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_CONTEXT_INVALID"
        )
        == "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_CONTEXT_INVALID"
    )


@pytest.mark.parametrize(
    ("raw_snapshot", "diagnostic_context_code"),
    ADVANCED_RESPONSE_PRECONTENT_CONTEXT_CASES,
)
def test_precontent_refusals_have_exact_closed_context_without_acceptance_change(
    raw_snapshot: str,
    diagnostic_context_code: str,
) -> None:
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
    )
    assert captured.value.diagnostic_context_code == diagnostic_context_code
    if (
        diagnostic_context_code
        == "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
    ):
        assert captured.value.diagnostic_context_detail_code == (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_UNSATISFIED_EMPTY"
        )
    else:
        assert not hasattr(captured.value, "diagnostic_context_detail_code")


@pytest.mark.parametrize(
    ("raw_snapshot", "diagnostic_context_code"),
    ADVANCED_RESPONSE_PRECONTENT_CONTEXT_CASES,
)
def test_terminal_recovery_reports_each_closed_precontent_context_without_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_snapshot: str,
    diagnostic_context_code: str,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    transport = RecoveryTransport([raw_snapshot, raw_snapshot, raw_snapshot])
    install_transport(monkeypatch, root, transport)

    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
    )
    assert captured.value.diagnostic_context_code == diagnostic_context_code
    if (
        diagnostic_context_code
        == "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
    ):
        assert captured.value.diagnostic_context_detail_code == (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_UNSATISFIED_EMPTY"
        )
    else:
        assert not hasattr(captured.value, "diagnostic_context_detail_code")
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    serialized_status = json.dumps(
        orchestrator.status(private_root=root, run_id=RUN_ID),
        sort_keys=True,
    )
    assert "diagnostic_code" not in serialized_status
    assert "diagnostic_detail_code" not in serialized_status
    assert "diagnostic_context_code" not in serialized_status
    assert "diagnostic_context_detail_code" not in serialized_status
    assert (
        sum(
            event["event_type"] == "SUBMISSION_INTENT_RECORDED"
            for event in event_list(run_dir)
        )
        == 1
    )
    assert transport.calls == [
        ("browser_navigate", {"url": CONVERSATION_URL}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_close", {}),
    ]
    assert_recovery_tools_only(transport)
    assert not {"browser_click", "browser_type"} & {
        tool for tool, _arguments in transport.calls
    }


@pytest.mark.parametrize(
    ("raw_snapshot", "diagnostic_context_detail_code"),
    ADVANCED_RESPONSE_PRECONTENT_INVALID_DETAIL_CASES,
)
def test_nested_invalid_precontent_refusals_have_exact_closed_context_detail(
    raw_snapshot: str,
    diagnostic_context_detail_code: str,
) -> None:
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
    )
    assert captured.value.diagnostic_context_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
    )
    assert (
        captured.value.diagnostic_context_detail_code == diagnostic_context_detail_code
    )


@pytest.mark.parametrize(
    ("raw_snapshot", "diagnostic_context_detail_code"),
    ADVANCED_RESPONSE_PRECONTENT_INVALID_DETAIL_CASES,
)
def test_terminal_recovery_reports_each_reachable_precontent_context_detail_without_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_snapshot: str,
    diagnostic_context_detail_code: str,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    transport = RecoveryTransport([raw_snapshot, raw_snapshot, raw_snapshot])
    install_transport(monkeypatch, root, transport)

    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
    )
    assert captured.value.diagnostic_context_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
    )
    assert (
        captured.value.diagnostic_context_detail_code == diagnostic_context_detail_code
    )
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    serialized_status = json.dumps(
        orchestrator.status(private_root=root, run_id=RUN_ID),
        sort_keys=True,
    )
    assert "diagnostic_code" not in serialized_status
    assert "diagnostic_detail_code" not in serialized_status
    assert "diagnostic_context_code" not in serialized_status
    assert "diagnostic_context_detail_code" not in serialized_status
    assert (
        sum(
            event["event_type"] == "SUBMISSION_INTENT_RECORDED"
            for event in event_list(run_dir)
        )
        == 1
    )
    assert transport.calls == [
        ("browser_navigate", {"url": CONVERSATION_URL}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_close", {}),
    ]
    assert_recovery_tools_only(transport)
    assert not {"browser_click", "browser_type"} & {
        tool for tool, _arguments in transport.calls
    }


@pytest.mark.parametrize(
    ("raw_snapshot", "diagnostic_detail_code"),
    ADVANCED_RESPONSE_ACTION_DETAIL_CASES,
)
def test_action_boundary_refusals_have_exact_reachable_details(
    raw_snapshot: str,
    diagnostic_detail_code: str,
) -> None:
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == diagnostic_detail_code


@pytest.mark.parametrize(
    ("action_line", "diagnostic_detail_code"),
    [
        pytest.param(
            '- Group "wrong" [ref=e70]:',
            "ADVANCED_RESPONSE_ACTION_ROLE_INVALID",
            id="role-precedes-label-and-ref",
        ),
        pytest.param(
            '- group "response actions" [ref=e70]:',
            "ADVANCED_RESPONSE_ACTION_LABEL_INVALID",
            id="label-precedes-ref",
        ),
        pytest.param(
            '- group "Response actions" [ref]:',
            "ADVANCED_RESPONSE_ACTION_REF_PRESENT",
            id="ref-missing-value",
        ),
        pytest.param(
            '- group "Response actions" [REF=e70]:',
            "ADVANCED_RESPONSE_ACTION_REF_PRESENT",
            id="wrong-case-ref",
        ),
        pytest.param(
            '- group "Response actions" [ref =e70]:',
            "ADVANCED_RESPONSE_ACTION_REF_PRESENT",
            id="spaced-ref",
        ),
        pytest.param(
            '- group "Response actions" [data=ref=e70]:',
            "ADVANCED_RESPONSE_ACTION_REF_PRESENT",
            id="ref-in-attribute-value",
        ),
        pytest.param(
            '- group "Response actions" [name=[ref=e70]:',
            "ADVANCED_RESPONSE_ACTION_REF_PRESENT",
            id="nested-ref-attempt",
        ),
        pytest.param(
            '- group "Response actions" [ref=e70] [ref=e71]:',
            "ADVANCED_RESPONSE_ACTION_REF_PRESENT",
            id="multiple-refs",
        ),
        pytest.param(
            '- group "Response actions" [reference=e70] [data-ref=e71]:',
            "ADVANCED_RESPONSE_ACTION_EXTRA_ATTRIBUTES",
            id="nonreserved-ref-like-attribute-names",
        ),
        pytest.param(
            '- group "Response actions": [disabled]',
            "ADVANCED_RESPONSE_ACTION_LINE_SHAPE_INVALID",
            id="attribute-after-colon",
        ),
        pytest.param(
            '- group "Response actions" [disabled',
            "ADVANCED_RESPONSE_ACTION_LINE_SHAPE_INVALID",
            id="unclosed-attribute",
        ),
        pytest.param(
            '-  group "Response actions":',
            "ADVANCED_RESPONSE_ACTION_LINE_SHAPE_INVALID",
            id="residual-prefix-spacing",
        ),
    ],
)
def test_action_detail_syntax_precedence_is_raw_and_closed(
    action_line: str,
    diagnostic_detail_code: str,
) -> None:
    assert (
        orchestrator._advanced_response_action_detail_for_line(action_line)
        == diagnostic_detail_code
    )


@pytest.mark.parametrize(
    ("earlier_lines", "diagnostic_detail_code"),
    [
        pytest.param(
            ('  - group "Response actions":',),
            "ADVANCED_RESPONSE_ACTION_LABEL_INVALID",
            id="pre-content-is-provisional-before-later-malformed-boundary",
        ),
        pytest.param(
            (
                "  - paragraph [ref=e62]:",
                '    - text: "Before"',
                '  - group "Response actions":',
                "  - paragraph [ref=e63]:",
                '    - text: "After"',
            ),
            "ADVANCED_RESPONSE_ACTION_CONTENT_AFTER",
            id="content-after-before-later-boundary",
        ),
        pytest.param(
            (
                "  - paragraph [ref=e62]:",
                '    - text: "Before"',
                '  - group "Response actions":',
                '  - group "Response actions":',
            ),
            "ADVANCED_RESPONSE_ACTION_DUPLICATE",
            id="duplicate-before-later-boundary",
        ),
    ],
)
def test_action_detail_does_not_look_past_first_lifecycle_failure(
    earlier_lines: tuple[str, ...],
    diagnostic_detail_code: str,
) -> None:
    raw_snapshot = diagnostic_snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        *earlier_lines,
        '- group "response actions":',
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_detail_code == diagnostic_detail_code


@pytest.mark.parametrize(
    ("earlier_lines", "later_boundary", "diagnostic_detail_code"),
    [
        pytest.param(
            (
                "  - paragraph [ref=e62]:",
                '    - text: "Before"',
                '  - group "Response actions":',
                "  - paragraph [ref=e63]:",
                '    - text: "After"',
            ),
            "- paragraph [ref=e90]:",
            "ADVANCED_RESPONSE_ACTION_CONTENT_AFTER",
            id="content-after-before-later-paragraph-boundary",
        ),
        pytest.param(
            (
                "  - paragraph [ref=e62]:",
                '    - text: "Before"',
                '  - group "Response actions":',
                '  - group "Response actions":',
            ),
            "- generic [ref=e90]:",
            "ADVANCED_RESPONSE_ACTION_DUPLICATE",
            id="duplicate-before-later-generic-boundary",
        ),
    ],
)
def test_action_detail_precedes_later_non_action_boundary(
    earlier_lines: tuple[str, ...],
    later_boundary: str,
    diagnostic_detail_code: str,
) -> None:
    raw_snapshot = diagnostic_snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        *earlier_lines,
        later_boundary,
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == diagnostic_detail_code


def test_pre_content_action_is_provisional_before_later_boundary_conflict() -> None:
    raw_snapshot = diagnostic_snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - group "Response actions":',
        "- paragraph [ref=e90]:",
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == "ADVANCED_RESPONSE_BOUNDARY_CONFLICT"
    assert not hasattr(captured.value, "diagnostic_detail_code")


def test_outer_marker_conflict_keeps_priority_over_action_detail() -> None:
    raw_snapshot = diagnostic_snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        '- heading "ChatGPT said:" [ref=e70]',
        "- generic [ref=e61]:",
        '  - text: "Visible"',
        '- Group "Response actions":',
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_code == "ADVANCED_RESPONSE_MARKER_CONFLICT"
    assert not hasattr(captured.value, "diagnostic_detail_code")


def test_complete_heading_attributes_no_longer_emit_the_reserved_detail() -> None:
    heading_line = (
        '- heading "ChatGPT said:" [disabled] [ref=e60] [level=2] [aria-label="ready"]'
    )
    raw_snapshot = diagnostic_snapshot(heading_line, *HEADING_DETAIL_BODY)

    assert orchestrator._advanced_response_heading_detail_for_line(heading_line) is None
    assert orchestrator._completed_response(
        raw_snapshot,
        profile_id=workflow.ADVANCED_PROFILE_ID,
    ) == (CONVERSATION_URL, "e60", "Visible")


@pytest.mark.parametrize(
    ("heading_line", "diagnostic_detail_code"),
    ADVANCED_RESPONSE_HEADING_DETAIL_CASES,
)
def test_every_closed_heading_detail_is_exact_without_changing_refusal(
    heading_line: str,
    diagnostic_detail_code: str,
) -> None:
    raw_snapshot = diagnostic_snapshot(heading_line, *HEADING_DETAIL_BODY)

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_SELECTOR_AMBIGUITY"
    assert captured.value.diagnostic_code == "ADVANCED_RESPONSE_HEADING_INVALID"
    assert captured.value.diagnostic_detail_code == diagnostic_detail_code


@pytest.mark.parametrize(
    ("heading_line", "diagnostic_detail_code"),
    [
        pytest.param(
            '- ARTICLE " chatgpt said " [REF=invalid]',
            "ADVANCED_RESPONSE_HEADING_ROLE_INVALID",
            id="role-before-label-and-ref",
        ),
        pytest.param(
            '-  ARTICLE "ChatGPT said:" [ref=e60]',
            "ADVANCED_RESPONSE_HEADING_ROLE_INVALID",
            id="role-before-prefix-spacing",
        ),
        pytest.param(
            '-\tarticle  "ChatGPT said:" [ref=e60]',
            "ADVANCED_RESPONSE_HEADING_ROLE_INVALID",
            id="role-before-tab-and-label-spacing",
        ),
        pytest.param(
            '- heading " chatgpt said " [ref=invalid]',
            "ADVANCED_RESPONSE_HEADING_LABEL_EDGE_WHITESPACE_INVALID",
            id="edge-whitespace-before-case-punctuation-and-ref",
        ),
        pytest.param(
            '- heading "chatgpt said:" [ref=invalid]',
            "ADVANCED_RESPONSE_HEADING_LABEL_CASE_INVALID",
            id="case-before-ref",
        ),
        pytest.param(
            '- heading "chatgpt said" [ref=invalid]',
            "ADVANCED_RESPONSE_HEADING_LABEL_PUNCTUATION_INVALID",
            id="punctuation-before-ref",
        ),
        pytest.param(
            '- heading "ChatGPT said::" [ref=e60]',
            "ADVANCED_RESPONSE_HEADING_LABEL_PUNCTUATION_INVALID",
            id="repeated-punctuation",
        ),
        pytest.param(
            '- heading "ChatGPT said?!" [ref=e60]',
            "ADVANCED_RESPONSE_HEADING_LABEL_PUNCTUATION_INVALID",
            id="changed-punctuation-run",
        ),
        pytest.param(
            '- heading "ChatGPT\u00a0said:" [ref=e60]',
            "ADVANCED_RESPONSE_HEADING_LABEL_OTHER_INVALID",
            id="unicode-whitespace-is-other",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [reference=e60]',
            "ADVANCED_RESPONSE_HEADING_REF_MISSING",
            id="non-reserved-reference-attribute",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [REF=e60]',
            "ADVANCED_RESPONSE_HEADING_REF_INVALID",
            id="wrong-case-reserved-ref",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [ref = e60]',
            "ADVANCED_RESPONSE_HEADING_REF_INVALID",
            id="spaced-reserved-ref",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [ref=e60',
            "ADVANCED_RESPONSE_HEADING_REF_INVALID",
            id="unclosed-reserved-ref",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [ref=e60] [ref=invalid]',
            "ADVANCED_RESPONSE_HEADING_REF_INVALID",
            id="valid-plus-malformed-ref",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [ref=e60] [ref=e70]',
            "ADVANCED_RESPONSE_HEADING_REF_INVALID",
            id="multiple-valid-refs",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [data=[ref=e70] [ref=e60]',
            "ADVANCED_RESPONSE_HEADING_REF_INVALID",
            id="nested-valid-ref-attempt-before-ref",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [ref=e60] [data=[ref=e70]',
            "ADVANCED_RESPONSE_HEADING_REF_INVALID",
            id="nested-valid-ref-attempt-after-ref",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [data=[REF=e70] [ref=e60]',
            "ADVANCED_RESPONSE_HEADING_REF_INVALID",
            id="nested-wrong-case-ref-attempt",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [data=[ref] [ref=e60]',
            "ADVANCED_RESPONSE_HEADING_REF_INVALID",
            id="nested-valueless-ref-attempt",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [data=[ref =e70] [ref=e60]',
            "ADVANCED_RESPONSE_HEADING_REF_INVALID",
            id="nested-spaced-ref-attempt",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [data=ref=e70] [ref=e60]',
            "ADVANCED_RESPONSE_HEADING_LINE_SHAPE_INVALID",
            id="unbracketed-ref-attempt-inside-value",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [ref=e60] [disabled] unexpected',
            "ADVANCED_RESPONSE_HEADING_LINE_SHAPE_INVALID",
            id="valid-extra-attribute-plus-residual",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [ref=e60] [disabled',
            "ADVANCED_RESPONSE_HEADING_LINE_SHAPE_INVALID",
            id="unclosed-extra-attribute",
        ),
        pytest.param(
            '- heading "ChatGPT said:" ref=e60',
            "ADVANCED_RESPONSE_HEADING_LINE_SHAPE_INVALID",
            id="unbracketed-ref-assignment",
        ),
    ],
)
def test_heading_detail_compound_precedence_is_closed(
    heading_line: str,
    diagnostic_detail_code: str,
) -> None:
    assert (
        orchestrator._advanced_response_heading_detail_for_line(heading_line)
        == diagnostic_detail_code
    )


@pytest.mark.parametrize(
    ("heading_line", "diagnostic_detail_code"),
    [
        pytest.param(
            '-  ARTICLE "ChatGPT said:" [ref=e60]',
            "ADVANCED_RESPONSE_HEADING_ROLE_INVALID",
            id="role",
        ),
        pytest.param(
            '-  heading " ChatGPT said: " [ref=e60]',
            "ADVANCED_RESPONSE_HEADING_LABEL_EDGE_WHITESPACE_INVALID",
            id="edge-whitespace",
        ),
        pytest.param(
            '-  heading "chatgpt said:" [ref=e60]',
            "ADVANCED_RESPONSE_HEADING_LABEL_CASE_INVALID",
            id="case",
        ),
        pytest.param(
            '-  heading "ChatGPT said" [ref=e60]',
            "ADVANCED_RESPONSE_HEADING_LABEL_PUNCTUATION_INVALID",
            id="punctuation",
        ),
        pytest.param(
            '-  heading "Assistant response" [ref=e60]',
            "ADVANCED_RESPONSE_HEADING_LABEL_OTHER_INVALID",
            id="other-label",
        ),
        pytest.param(
            '-  heading "ChatGPT said:"',
            "ADVANCED_RESPONSE_HEADING_REF_MISSING",
            id="ref-missing",
        ),
        pytest.param(
            '-  heading "ChatGPT said:" [ref=invalid]',
            "ADVANCED_RESPONSE_HEADING_REF_INVALID",
            id="ref-invalid",
        ),
    ],
)
def test_runtime_candidate_spacing_drift_preserves_earlier_detail_precedence(
    heading_line: str,
    diagnostic_detail_code: str,
) -> None:
    raw_snapshot = diagnostic_snapshot(heading_line, *HEADING_DETAIL_BODY)

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_code == "ADVANCED_RESPONSE_HEADING_INVALID"
    assert captured.value.diagnostic_detail_code == diagnostic_detail_code


@pytest.mark.parametrize(
    "shared_ref", [False, True], ids=["distinct-ref", "shared-ref"]
)
def test_true_marker_competition_wins_and_has_no_heading_detail(
    shared_ref: bool,
) -> None:
    legacy_ref = "e60" if shared_ref else "e70"
    raw_snapshot = diagnostic_snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        *HEADING_DETAIL_BODY,
        f'- article "Assistant answer" [ref={legacy_ref}]',
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_SELECTOR_AMBIGUITY"
    assert captured.value.diagnostic_code == "ADVANCED_RESPONSE_MARKER_CONFLICT"
    assert not hasattr(captured.value, "diagnostic_detail_code")


@pytest.mark.parametrize(
    "legacy_line",
    [
        pytest.param('- article "Assistant answer"', id="ref-free"),
        pytest.param('- article "Assistant answer" [ref=invalid]', id="bad-ref"),
        pytest.param(
            '- article "Assistant answer" [ref=e70] [ref=e71]',
            id="multiple-valid-refs",
        ),
        pytest.param(
            '- article "Assistant answer" [ref=e70] [ref=invalid]',
            id="valid-plus-malformed-ref",
        ),
    ],
)
def test_invalid_legacy_looking_copy_does_not_suppress_heading_detail(
    legacy_line: str,
) -> None:
    raw_snapshot = diagnostic_snapshot(
        '- heading "chatgpt said:" [ref=e60]',
        *HEADING_DETAIL_BODY,
        legacy_line,
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_code == "ADVANCED_RESPONSE_HEADING_INVALID"
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_HEADING_LABEL_CASE_INVALID"
    )


@pytest.mark.parametrize(
    ("quoted_token", "outside_ref"),
    [
        pytest.param("[ref=e99]", "e70", id="quoted-valid-distinct"),
        pytest.param("[ref=invalid]", "e70", id="quoted-invalid-distinct"),
        pytest.param("[REF=e99]", "e60", id="quoted-wrong-case-shared"),
        pytest.param("[ref]", "e60", id="quoted-missing-value-shared"),
    ],
)
def test_quoted_ref_text_does_not_change_valid_legacy_competition(
    quoted_token: str,
    outside_ref: str,
) -> None:
    raw_snapshot = diagnostic_snapshot(
        '- heading "chatgpt said:" [ref=e60]',
        *HEADING_DETAIL_BODY,
        f'- article "Assistant answer {quoted_token}" [ref={outside_ref}]',
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_code == "ADVANCED_RESPONSE_MARKER_CONFLICT"
    assert not hasattr(captured.value, "diagnostic_detail_code")


@pytest.mark.parametrize(
    ("legacy_line", "diagnostic_code"),
    [
        pytest.param(
            '- article "Assistant answer" [ref=e70] [ref=invalid]',
            "ADVANCED_RESPONSE_MARKER_CONFLICT",
            id="distinct-valid-plus-malformed-preserves-predecessor",
        ),
        pytest.param(
            '- article "Assistant answer" [ref=e60] [ref=invalid]',
            "ADVANCED_RESPONSE_STRUCTURAL_REF_COLLISION",
            id="shared-valid-plus-malformed-preserves-predecessor",
        ),
    ],
)
def test_invalid_legacy_looking_copy_does_not_change_predecessor_exact_path(
    legacy_line: str,
    diagnostic_code: str,
) -> None:
    raw_snapshot = diagnostic_snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        *HEADING_DETAIL_BODY,
        legacy_line,
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_code == diagnostic_code
    assert not hasattr(captured.value, "diagnostic_detail_code")


@pytest.mark.parametrize(
    "heading_line",
    [
        pytest.param(
            '- heading "chatgpt said:" [ref=e60]',
            id="case",
        ),
        pytest.param(
            '- heading " ChatGPT said: " [ref=e60]',
            id="edge-whitespace",
        ),
        pytest.param('- heading "ChatGPT said:"', id="ref-missing"),
        pytest.param(
            '- heading "ChatGPT said:" [ref=invalid]',
            id="ref-invalid",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [ref=e60] [level=2]',
            id="extra-attributes",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [ref=e60]:',
            id="line-shape",
        ),
    ],
)
@pytest.mark.parametrize("answer_now_count", [1, 2], ids=["one", "duplicate"])
def test_late_heading_details_preserve_predecessor_generating_priority(
    heading_line: str,
    answer_now_count: int,
) -> None:
    raw_snapshot = diagnostic_snapshot(
        *(
            f'- button "Answer now" [ref=e{50 + index}]'
            for index in range(answer_now_count)
        ),
        heading_line,
        *HEADING_DETAIL_BODY,
    )

    if answer_now_count == 1:
        assert (
            orchestrator._completed_response(
                raw_snapshot,
                profile_id=workflow.ADVANCED_PROFILE_ID,
            )
            is None
        )
        return

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_GENERATING_MARKER_DUPLICATION"
    )
    assert not hasattr(captured.value, "diagnostic_detail_code")


@pytest.mark.parametrize("answer_now_count", [1, 2], ids=["one", "duplicate"])
def test_exact_heading_legacy_competition_preserves_generating_priority(
    answer_now_count: int,
) -> None:
    raw_snapshot = diagnostic_snapshot(
        *(
            f'- button "Answer now" [ref=e{50 + index}]'
            for index in range(answer_now_count)
        ),
        '- heading "ChatGPT said:" [ref=e60]',
        *HEADING_DETAIL_BODY,
        '- article "Assistant answer" [ref=e70]',
    )

    if answer_now_count == 1:
        assert (
            orchestrator._completed_response(
                raw_snapshot,
                profile_id=workflow.ADVANCED_PROFILE_ID,
            )
            is None
        )
        return

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_GENERATING_MARKER_DUPLICATION"
    )
    assert not hasattr(captured.value, "diagnostic_detail_code")


def test_one_wrong_role_marker_is_not_double_counted_as_competition() -> None:
    raw_snapshot = diagnostic_snapshot(
        '- article "ChatGPT said:" [ref=e60]',
        *HEADING_DETAIL_BODY,
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_code == "ADVANCED_RESPONSE_HEADING_INVALID"
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_HEADING_ROLE_INVALID"
    )


def test_untrusted_marker_copy_does_not_compete_with_trusted_heading_candidate() -> (
    None
):
    raw_snapshot = diagnostic_snapshot(
        '- heading "chatgpt said:" [ref=e60]',
        *HEADING_DETAIL_BODY,
        '- heading "You said:" [ref=e80]',
        "- generic [ref=e81]:",
        "  - paragraph [ref=e82]:",
        '    - article "ChatGPT said:" [ref=e83]',
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_code == "ADVANCED_RESPONSE_HEADING_INVALID"
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_HEADING_LABEL_CASE_INVALID"
    )


@pytest.mark.parametrize(
    ("evaluator", "raw_snapshot", "reason_code", "diagnostic_code"),
    ADVANCED_RESPONSE_DIAGNOSTIC_CASES,
)
def test_every_closed_advanced_response_diagnostic_category_is_exact(
    evaluator: str,
    raw_snapshot: str,
    reason_code: str,
    diagnostic_code: str,
) -> None:
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        if evaluator == "candidate":
            orchestrator._response_candidate_digest(
                raw_snapshot,
                profile_id=workflow.ADVANCED_PROFILE_ID,
            )
        else:
            orchestrator._completed_response(
                raw_snapshot,
                profile_id=workflow.ADVANCED_PROFILE_ID,
            )

    assert captured.value.code == reason_code
    assert captured.value.diagnostic_code == diagnostic_code


def test_recovery_cli_emits_only_closed_diagnostic_and_changes_no_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    malformed = diagnostic_snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        '- generic "raw-dynamic-label" [ref=e987654]:',
        "  - paragraph [ref=e62]:",
        '    - text: "raw response material"',
    )
    transport = RecoveryTransport([malformed, malformed, malformed])
    install_transport(monkeypatch, root, transport)
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(root),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    output = json.loads(capsys.readouterr().err)
    assert output == {
        "diagnostic_code": "ADVANCED_RESPONSE_BODY_ROOT_INVALID",
        "reason_code": "RESPONSE_SELECTOR_AMBIGUITY",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }
    serialized = json.dumps(output, sort_keys=True)
    for forbidden in (
        "raw-dynamic-label",
        "raw response material",
        "e987654",
        CONVERSATION_URL,
    ):
        assert forbidden not in serialized
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert "diagnostic_code" not in orchestrator.status(
        private_root=root,
        run_id=RUN_ID,
    )
    assert_recovery_tools_only(transport)
    assert (
        sum(
            event["event_type"] == "SUBMISSION_INTENT_RECORDED"
            for event in event_list(run_dir)
        )
        == 1
    )


def test_recovery_cli_emits_closed_heading_detail_without_persisting_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    malformed = diagnostic_snapshot(
        '- heading " chatgpt said " [ref=e987654]',
        *HEADING_DETAIL_BODY,
    )
    transport = RecoveryTransport([malformed, malformed, malformed])
    install_transport(monkeypatch, root, transport)
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(root),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    output = json.loads(capsys.readouterr().err)
    assert output == {
        "diagnostic_code": "ADVANCED_RESPONSE_HEADING_INVALID",
        "diagnostic_detail_code": (
            "ADVANCED_RESPONSE_HEADING_LABEL_EDGE_WHITESPACE_INVALID"
        ),
        "reason_code": "RESPONSE_SELECTOR_AMBIGUITY",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }
    serialized = json.dumps(output, sort_keys=True)
    for forbidden in (
        " chatgpt said ",
        "e987654",
        CONVERSATION_URL,
    ):
        assert forbidden not in serialized
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert "diagnostic_detail_code" not in orchestrator.status(
        private_root=root,
        run_id=RUN_ID,
    )
    assert_recovery_tools_only(transport)
    assert not {
        "browser_click",
        "browser_type",
    } & {tool for tool, _arguments in transport.calls}


def test_recovery_cli_emits_closed_action_detail_without_persisting_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    malformed = diagnostic_snapshot(
        *ACTION_DETAIL_PREFIX,
        '- Group "Response actions" [ref=e987654]:',
    )
    transport = RecoveryTransport([malformed, malformed, malformed])
    install_transport(monkeypatch, root, transport)
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(root),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    output = json.loads(capsys.readouterr().err)
    assert output == {
        "diagnostic_code": "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "diagnostic_detail_code": "ADVANCED_RESPONSE_ACTION_ROLE_INVALID",
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }
    serialized = json.dumps(output, sort_keys=True)
    for forbidden in (
        "Group",
        "Response actions",
        "e987654",
        CONVERSATION_URL,
    ):
        assert forbidden not in serialized
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert "diagnostic_detail_code" not in orchestrator.status(
        private_root=root,
        run_id=RUN_ID,
    )
    assert_recovery_tools_only(transport)
    assert not {
        "browser_click",
        "browser_type",
    } & {tool for tool, _arguments in transport.calls}
    assert (
        sum(
            event["event_type"] == "SUBMISSION_INTENT_RECORDED"
            for event in event_list(run_dir)
        )
        == 1
    )


@pytest.mark.parametrize(
    "diagnostic_context_code",
    sorted(EXPECTED_BOUND_RESPONSE_PRECONTENT_CONTEXT_CODES),
)
def test_recovery_cli_emits_only_each_closed_precontent_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    diagnostic_context_code: str,
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        diagnostic_context_code,
    )
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    output = json.loads(capsys.readouterr().err)
    assert output == {
        "diagnostic_code": "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "diagnostic_context_code": diagnostic_context_code,
        "diagnostic_detail_code": "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }
    serialized = json.dumps(output, sort_keys=True)
    for forbidden in (
        "Response actions",
        "hidden response material",
        "e987654",
        CONVERSATION_URL,
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "diagnostic_context_detail_code",
    sorted(EXPECTED_BOUND_RESPONSE_PRECONTENT_CONTEXT_DETAIL_CODES),
)
def test_recovery_cli_emits_only_each_closed_precontent_context_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    diagnostic_context_detail_code: str,
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
        diagnostic_context_detail_code,
    )
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    output = json.loads(capsys.readouterr().err)
    assert output == {
        "diagnostic_code": "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "diagnostic_context_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
        ),
        "diagnostic_context_detail_code": diagnostic_context_detail_code,
        "diagnostic_detail_code": "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }
    serialized = json.dumps(output, sort_keys=True)
    for forbidden in (
        "Response actions",
        "hidden response material",
        "e987654",
        CONVERSATION_URL,
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "invalid",
    [
        pytest.param(
            "ADVANCED_RESPONSE_BODY_ROOT_INVALID_COUNT_2", id="dynamic-suffix"
        ),
        pytest.param(" ADVANCED_RESPONSE_BODY_ROOT_INVALID", id="left-padded"),
        pytest.param("ADVANCED_RESPONSE_BODY_ROOT_INVALID ", id="right-padded"),
        pytest.param("advanced_response_body_root_invalid", id="wrong-case"),
        pytest.param("ADVANCED_RESPONSE_UNKNOWN", id="unknown"),
        pytest.param("e987654", id="raw-ref"),
    ],
)
def test_unknown_or_dynamic_recovery_diagnostic_is_rejected(invalid: str) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._BoundResponseRecoveryRefusal(
            "RESPONSE_SELECTOR_AMBIGUITY",
            invalid,
        )

    assert captured.value.code == "BOUND_RESPONSE_DIAGNOSTIC_INVALID"


@pytest.mark.parametrize(
    "invalid",
    [
        pytest.param(
            "ADVANCED_RESPONSE_HEADING_ROLE_INVALID_COUNT_2",
            id="dynamic-suffix",
        ),
        pytest.param(" ADVANCED_RESPONSE_HEADING_ROLE_INVALID", id="left-padded"),
        pytest.param("ADVANCED_RESPONSE_HEADING_ROLE_INVALID ", id="right-padded"),
        pytest.param("advanced_response_heading_role_invalid", id="wrong-case"),
        pytest.param("ADVANCED_RESPONSE_HEADING_UNKNOWN", id="unknown"),
        pytest.param("e987654", id="raw-ref"),
    ],
)
def test_unknown_or_dynamic_heading_detail_is_rejected(invalid: str) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._BoundResponseRecoveryRefusal(
            "RESPONSE_SELECTOR_AMBIGUITY",
            "ADVANCED_RESPONSE_HEADING_INVALID",
            invalid,
        )

    assert captured.value.code == "BOUND_RESPONSE_DIAGNOSTIC_INVALID"


@pytest.mark.parametrize(
    "invalid",
    [
        pytest.param(
            "ADVANCED_RESPONSE_ACTION_ROLE_INVALID_COUNT_2",
            id="dynamic-suffix",
        ),
        pytest.param(" ADVANCED_RESPONSE_ACTION_ROLE_INVALID", id="left-padded"),
        pytest.param("ADVANCED_RESPONSE_ACTION_ROLE_INVALID ", id="right-padded"),
        pytest.param("advanced_response_action_role_invalid", id="wrong-case"),
        pytest.param("ADVANCED_RESPONSE_ACTION_UNKNOWN", id="unknown"),
        pytest.param("e987654", id="raw-ref"),
    ],
)
def test_unknown_or_dynamic_action_detail_is_rejected(invalid: str) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._BoundResponseRecoveryRefusal(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            invalid,
        )

    assert captured.value.code == "BOUND_RESPONSE_DIAGNOSTIC_INVALID"


@pytest.mark.parametrize(
    "invalid",
    [
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY_COUNT_2",
            id="dynamic-suffix",
        ),
        pytest.param(
            " ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY",
            id="left-padded",
        ),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY ",
            id="right-padded",
        ),
        pytest.param(
            "advanced_response_precontent_nested_empty",
            id="wrong-case",
        ),
        pytest.param("ADVANCED_RESPONSE_PRECONTENT_UNKNOWN", id="unknown"),
        pytest.param("e987654", id="raw-ref"),
    ],
)
def test_unknown_or_dynamic_precontent_context_is_rejected(invalid: str) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._BoundResponseRecoveryRefusal(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            invalid,
        )

    assert captured.value.code == "BOUND_RESPONSE_DIAGNOSTIC_INVALID"


@pytest.mark.parametrize(
    "invalid",
    [
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID_COUNT_2",
            id="dynamic-suffix",
        ),
        pytest.param(
            " ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID",
            id="left-padded",
        ),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID ",
            id="right-padded",
        ),
        pytest.param(
            "advanced_response_precontent_nested_scalar_shape_invalid",
            id="wrong-case",
        ),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_UNKNOWN",
            id="unknown",
        ),
        pytest.param("e987654", id="raw-ref"),
    ],
)
def test_unknown_or_dynamic_precontent_context_detail_is_rejected(
    invalid: str,
) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._BoundResponseRecoveryRefusal(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            invalid,
        )

    assert captured.value.code == "BOUND_RESPONSE_DIAGNOSTIC_INVALID"


@pytest.mark.parametrize(
    ("reason_code", "diagnostic_code", "detail_code"),
    [
        pytest.param(
            "RESPONSE_SELECTOR_AMBIGUITY",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            id="wrong-generic-reason",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID",
            None,
            id="wrong-parent-diagnostic",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_ROLE_INVALID",
            id="wrong-action-detail",
        ),
    ],
)
def test_precontent_context_requires_exact_four_field_conjunction(
    reason_code: str,
    diagnostic_code: str,
    detail_code: str | None,
) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._validated_bound_response_context_code(
            reason_code,
            diagnostic_code,
            detail_code,
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY",
        )

    assert captured.value.code == "BOUND_RESPONSE_DIAGNOSTIC_INVALID"


@pytest.mark.parametrize(
    ("reason_code", "diagnostic_code", "detail_code", "context_code"),
    [
        pytest.param(
            "RESPONSE_SELECTOR_AMBIGUITY",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            id="wrong-generic-reason",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID",
            None,
            None,
            id="wrong-parent-diagnostic",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_ROLE_INVALID",
            None,
            id="wrong-action-detail",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY",
            id="wrong-precontent-context",
        ),
    ],
)
def test_precontent_context_detail_requires_exact_five_field_conjunction(
    reason_code: str,
    diagnostic_code: str,
    detail_code: str | None,
    context_code: str | None,
) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._validated_bound_response_context_detail_code(
            reason_code,
            diagnostic_code,
            detail_code,
            context_code,
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID",
        )

    assert captured.value.code == "BOUND_RESPONSE_DIAGNOSTIC_INVALID"


@pytest.mark.parametrize(
    ("reason_code", "diagnostic_code"),
    [
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_HEADING_INVALID",
            id="wrong-generic-reason",
        ),
        pytest.param(
            "RESPONSE_SELECTOR_AMBIGUITY",
            "ADVANCED_RESPONSE_BODY_ROOT_INVALID",
            id="wrong-parent-diagnostic",
        ),
    ],
)
def test_heading_detail_requires_exact_generic_reason_and_parent(
    reason_code: str,
    diagnostic_code: str,
) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._BoundResponseRecoveryRefusal(
            reason_code,
            diagnostic_code,
            "ADVANCED_RESPONSE_HEADING_ROLE_INVALID",
        )

    assert captured.value.code == "BOUND_RESPONSE_DIAGNOSTIC_INVALID"


@pytest.mark.parametrize(
    ("reason_code", "diagnostic_code"),
    [
        pytest.param(
            "RESPONSE_SELECTOR_AMBIGUITY",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            id="wrong-generic-reason",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID",
            id="wrong-parent-diagnostic",
        ),
    ],
)
def test_action_detail_requires_exact_generic_reason_and_parent(
    reason_code: str,
    diagnostic_code: str,
) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._BoundResponseRecoveryRefusal(
            reason_code,
            diagnostic_code,
            "ADVANCED_RESPONSE_ACTION_ROLE_INVALID",
        )

    assert captured.value.code == "BOUND_RESPONSE_DIAGNOSTIC_INVALID"


@pytest.mark.parametrize(
    "invalid",
    [
        pytest.param(
            "ADVANCED_RESPONSE_BODY_ROOT_INVALID_COUNT_2", id="dynamic-suffix"
        ),
        pytest.param(" ADVANCED_RESPONSE_BODY_ROOT_INVALID", id="padded"),
        pytest.param("advanced_response_body_root_invalid", id="wrong-case"),
        pytest.param("ADVANCED_RESPONSE_UNKNOWN", id="unknown"),
    ],
)
def test_main_revalidates_recovery_diagnostic_before_json_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    invalid: str,
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_BODY_ROOT_INVALID",
    )
    refusal.diagnostic_code = invalid
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "reason_code": "RESPONSE_SELECTOR_AMBIGUITY",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


@pytest.mark.parametrize(
    "invalid",
    [
        pytest.param(
            "ADVANCED_RESPONSE_HEADING_ROLE_INVALID_COUNT_2",
            id="dynamic-suffix",
        ),
        pytest.param(" ADVANCED_RESPONSE_HEADING_ROLE_INVALID", id="left-padded"),
        pytest.param("ADVANCED_RESPONSE_HEADING_ROLE_INVALID ", id="right-padded"),
        pytest.param("advanced_response_heading_role_invalid", id="wrong-case"),
        pytest.param("ADVANCED_RESPONSE_HEADING_UNKNOWN", id="unknown"),
    ],
)
def test_main_omits_invalid_heading_detail_and_preserves_parent_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    invalid: str,
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_HEADING_INVALID",
        "ADVANCED_RESPONSE_HEADING_ROLE_INVALID",
    )
    refusal.diagnostic_detail_code = invalid
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "diagnostic_code": "ADVANCED_RESPONSE_HEADING_INVALID",
        "reason_code": "RESPONSE_SELECTOR_AMBIGUITY",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


def test_main_omits_missing_heading_detail_and_preserves_parent_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_HEADING_INVALID",
        "ADVANCED_RESPONSE_HEADING_ROLE_INVALID",
    )
    del refusal.diagnostic_detail_code
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "diagnostic_code": "ADVANCED_RESPONSE_HEADING_INVALID",
        "reason_code": "RESPONSE_SELECTOR_AMBIGUITY",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


@pytest.mark.parametrize(
    ("detail_code", "expected_detail"),
    [
        pytest.param(
            "ADVANCED_RESPONSE_ACTION_PLACEMENT_INVALID",
            "ADVANCED_RESPONSE_ACTION_PLACEMENT_INVALID",
            id="reserved-valid",
        ),
        pytest.param(None, None, id="missing"),
        pytest.param(
            "ADVANCED_RESPONSE_ACTION_ROLE_INVALID_COUNT_2",
            None,
            id="dynamic-suffix",
        ),
        pytest.param(
            " ADVANCED_RESPONSE_ACTION_ROLE_INVALID",
            None,
            id="left-padded",
        ),
        pytest.param(
            "ADVANCED_RESPONSE_ACTION_ROLE_INVALID ",
            None,
            id="right-padded",
        ),
        pytest.param(
            "advanced_response_action_role_invalid",
            None,
            id="wrong-case",
        ),
        pytest.param("ADVANCED_RESPONSE_ACTION_UNKNOWN", None, id="unknown"),
    ],
)
def test_main_revalidates_action_detail_and_preserves_parent_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    detail_code: str | None,
    expected_detail: str | None,
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_ACTION_ROLE_INVALID",
    )
    if detail_code is None:
        del refusal.diagnostic_detail_code
    else:
        refusal.diagnostic_detail_code = detail_code
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    expected = {
        "diagnostic_code": "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }
    if expected_detail is not None:
        expected["diagnostic_detail_code"] = expected_detail
    assert json.loads(capsys.readouterr().err) == expected


@pytest.mark.parametrize(
    "context_code",
    [
        pytest.param(None, id="missing"),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY_COUNT_2",
            id="dynamic-suffix",
        ),
        pytest.param(
            " ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY",
            id="left-padded",
        ),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY ",
            id="right-padded",
        ),
        pytest.param(
            "advanced_response_precontent_nested_empty",
            id="wrong-case",
        ),
        pytest.param("ADVANCED_RESPONSE_PRECONTENT_UNKNOWN", id="unknown"),
    ],
)
def test_main_omits_invalid_precontent_context_and_preserves_existing_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    context_code: str | None,
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY",
    )
    if context_code is None:
        del refusal.diagnostic_context_code
    else:
        refusal.diagnostic_context_code = context_code
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "diagnostic_code": "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "diagnostic_detail_code": "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


@pytest.mark.parametrize(
    "context_detail_code",
    [
        pytest.param(None, id="missing"),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID_COUNT_2",
            id="dynamic-suffix",
        ),
        pytest.param(
            " ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID",
            id="left-padded",
        ),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID ",
            id="right-padded",
        ),
        pytest.param(
            "advanced_response_precontent_nested_scalar_shape_invalid",
            id="wrong-case",
        ),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_UNKNOWN",
            id="unknown",
        ),
    ],
)
def test_main_omits_invalid_precontent_context_detail_and_preserves_existing_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    context_detail_code: str | None,
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID",
    )
    if context_detail_code is None:
        del refusal.diagnostic_context_detail_code
    else:
        refusal.diagnostic_context_detail_code = context_detail_code
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "diagnostic_code": "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "diagnostic_context_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
        ),
        "diagnostic_detail_code": "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


def test_main_omits_precontent_context_detail_outside_exact_context_conjunction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID",
    )
    refusal.diagnostic_context_code = "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY"
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "diagnostic_code": "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "diagnostic_context_code": "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY",
        "diagnostic_detail_code": "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


def test_main_omits_precontent_context_outside_exact_detail_conjunction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY",
    )
    refusal.diagnostic_detail_code = "ADVANCED_RESPONSE_ACTION_ROLE_INVALID"
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "diagnostic_code": "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "diagnostic_detail_code": "ADVANCED_RESPONSE_ACTION_ROLE_INVALID",
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


@pytest.mark.parametrize(
    ("reason_code", "diagnostic_code"),
    [
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_HEADING_INVALID",
            id="wrong-generic-reason",
        ),
        pytest.param(
            "RESPONSE_SELECTOR_AMBIGUITY",
            "ADVANCED_RESPONSE_BODY_ROOT_INVALID",
            id="wrong-parent-diagnostic",
        ),
    ],
)
def test_main_omits_heading_detail_outside_exact_parent_conjunction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reason_code: str,
    diagnostic_code: str,
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        reason_code,
        diagnostic_code,
    )
    refusal.diagnostic_detail_code = "ADVANCED_RESPONSE_HEADING_ROLE_INVALID"
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "diagnostic_code": diagnostic_code,
        "reason_code": reason_code,
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


@pytest.mark.parametrize(
    ("reason_code", "diagnostic_code"),
    [
        pytest.param(
            "RESPONSE_SELECTOR_AMBIGUITY",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            id="wrong-generic-reason",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID",
            id="wrong-parent-diagnostic",
        ),
    ],
)
def test_main_omits_action_detail_outside_exact_parent_conjunction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reason_code: str,
    diagnostic_code: str,
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        reason_code,
        diagnostic_code,
    )
    refusal.diagnostic_detail_code = "ADVANCED_RESPONSE_ACTION_ROLE_INVALID"
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "diagnostic_code": diagnostic_code,
        "reason_code": reason_code,
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


def test_main_omits_missing_recovery_diagnostic_and_preserves_generic_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID",
    )
    del refusal.diagnostic_code
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


def test_internal_parser_diagnostic_is_not_public_without_recovery_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    refusal = orchestrator._AdvancedResponseParserRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID",
    )
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "status",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )

    exit_code = invoke_orchestrator_main(
        [
            "status",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


def test_internal_heading_detail_is_not_public_without_recovery_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    refusal = orchestrator._AdvancedResponseParserRefusal(
        "RESPONSE_SELECTOR_AMBIGUITY",
        "ADVANCED_RESPONSE_HEADING_INVALID",
        "ADVANCED_RESPONSE_HEADING_ROLE_INVALID",
    )
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "status",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )

    exit_code = invoke_orchestrator_main(
        [
            "status",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "reason_code": "RESPONSE_SELECTOR_AMBIGUITY",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


def test_internal_action_detail_is_not_public_without_recovery_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    refusal = orchestrator._AdvancedResponseParserRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID",
    )
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "status",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )

    exit_code = invoke_orchestrator_main(
        [
            "status",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


def test_diagnostic_recovery_progress_tail_remains_eligible_and_nonpersistent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    loading = f'- Page URL: {CONVERSATION_URL}\n- status "loading" [ref=e90]'
    malformed = diagnostic_snapshot(
        '- heading "chatgpt said:" [ref=e60]',
        *HEADING_DETAIL_BODY,
    )
    first = RecoveryTransport([*[loading] * 13, *[malformed] * 3])
    install_transport(monkeypatch, root, first)

    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert captured.value.code == "RESPONSE_SELECTOR_AMBIGUITY"
    assert captured.value.diagnostic_code == "ADVANCED_RESPONSE_HEADING_INVALID"
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_HEADING_LABEL_CASE_INVALID"
    )
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    progress_events = [
        event
        for event in event_list(run_dir)
        if event["event_type"] == "RESPONSE_WAIT_PROGRESS"
    ]
    assert len(progress_events) == 1
    progress_json = json.dumps(progress_events[0], sort_keys=True)
    assert "diagnostic_code" not in progress_json
    assert "diagnostic_detail_code" not in progress_json
    record_after_first = (run_dir / "run-record.v1.jsonl").read_bytes()

    second = RecoveryTransport([malformed, malformed, malformed])
    install_transport(monkeypatch, root, second)
    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as retry:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert retry.value.diagnostic_code == captured.value.diagnostic_code
    assert retry.value.diagnostic_detail_code == (captured.value.diagnostic_detail_code)
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_after_first
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert_recovery_tools_only(first)
    assert_recovery_tools_only(second)


def test_action_diagnostic_progress_tail_retry_remains_nonpersistent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    loading = f'- Page URL: {CONVERSATION_URL}\n- status "loading" [ref=e90]'
    malformed = diagnostic_snapshot(
        *ACTION_DETAIL_PREFIX,
        '- group "response actions":',
    )
    first = RecoveryTransport([*[loading] * 13, *[malformed] * 3])
    install_transport(monkeypatch, root, first)

    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_ACTION_LABEL_INVALID"
    )
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    progress_events = [
        event
        for event in event_list(run_dir)
        if event["event_type"] == "RESPONSE_WAIT_PROGRESS"
    ]
    assert len(progress_events) == 1
    progress_json = json.dumps(progress_events[0], sort_keys=True)
    assert "diagnostic_code" not in progress_json
    assert "diagnostic_detail_code" not in progress_json
    record_after_first = (run_dir / "run-record.v1.jsonl").read_bytes()

    second = RecoveryTransport([malformed, malformed, malformed])
    install_transport(monkeypatch, root, second)
    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as retry:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert retry.value.diagnostic_code == captured.value.diagnostic_code
    assert retry.value.diagnostic_detail_code == captured.value.diagnostic_detail_code
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_after_first
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert_recovery_tools_only(first)
    assert_recovery_tools_only(second)


def test_precontent_context_progress_tail_retry_remains_nonpersistent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    loading = f'- Page URL: {CONVERSATION_URL}\n- status "loading" [ref=e90]'
    precontent = diagnostic_snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - group "Response actions":',
        "    - generic [ref=e70]:",
    )
    first = RecoveryTransport([*[loading] * 13, *[precontent] * 3])
    install_transport(monkeypatch, root, first)

    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
    )
    assert captured.value.diagnostic_context_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
    )
    assert captured.value.diagnostic_context_detail_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_UNSATISFIED_EMPTY"
    )
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    progress_events = [
        event
        for event in event_list(run_dir)
        if event["event_type"] == "RESPONSE_WAIT_PROGRESS"
    ]
    assert len(progress_events) == 1
    progress_json = json.dumps(progress_events[0], sort_keys=True)
    assert "diagnostic_code" not in progress_json
    assert "diagnostic_detail_code" not in progress_json
    assert "diagnostic_context_code" not in progress_json
    assert "diagnostic_context_detail_code" not in progress_json
    record_after_first = (run_dir / "run-record.v1.jsonl").read_bytes()

    second = RecoveryTransport([precontent, precontent, precontent])
    install_transport(monkeypatch, root, second)
    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as retry:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert retry.value.diagnostic_code == captured.value.diagnostic_code
    assert retry.value.diagnostic_detail_code == captured.value.diagnostic_detail_code
    assert retry.value.diagnostic_context_code == (
        captured.value.diagnostic_context_code
    )
    assert retry.value.diagnostic_context_detail_code == (
        captured.value.diagnostic_context_detail_code
    )
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_after_first
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert_recovery_tools_only(first)
    assert_recovery_tools_only(second)


def test_bound_response_precontent_context_shape_allowlist_is_exact() -> None:
    assert (
        orchestrator.BOUND_RESPONSE_PRECONTENT_CONTEXT_SHAPE_CODES
        == EXPECTED_BOUND_RESPONSE_PRECONTENT_CONTEXT_SHAPE_CODES
    )
    assert {
        case.values[1] for case in ADVANCED_RESPONSE_PRECONTENT_CONTAINER_SHAPE_CASES
    } == EXPECTED_BOUND_RESPONSE_PRECONTENT_CONTEXT_SHAPE_CODES
    for shape_code in EXPECTED_BOUND_RESPONSE_PRECONTENT_CONTEXT_SHAPE_CODES:
        assert (
            orchestrator._validated_bound_response_precontent_context_shape_code(
                shape_code
            )
            == shape_code
        )


@pytest.mark.parametrize(
    ("raw_snapshot", "diagnostic_context_shape_code"),
    ADVANCED_RESPONSE_PRECONTENT_CONTAINER_SHAPE_CASES,
)
def test_container_shape_refusals_have_exact_closed_six_field_conjunction(
    raw_snapshot: str,
    diagnostic_context_shape_code: str,
) -> None:
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
    )
    assert captured.value.diagnostic_context_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
    )
    assert captured.value.diagnostic_context_detail_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID"
    )
    assert captured.value.diagnostic_context_shape_code == diagnostic_context_shape_code


@pytest.mark.parametrize(
    ("raw_snapshot", "diagnostic_context_shape_code"),
    ADVANCED_RESPONSE_PRECONTENT_CONTAINER_SHAPE_CASES,
)
def test_terminal_recovery_reports_each_container_shape_without_actions_or_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_snapshot: str,
    diagnostic_context_shape_code: str,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    transport = RecoveryTransport([raw_snapshot, raw_snapshot, raw_snapshot])
    install_transport(monkeypatch, root, transport)

    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
    )
    assert captured.value.diagnostic_context_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
    )
    assert captured.value.diagnostic_context_detail_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID"
    )
    assert captured.value.diagnostic_context_shape_code == diagnostic_context_shape_code
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    serialized_status = json.dumps(
        orchestrator.status(private_root=root, run_id=RUN_ID),
        sort_keys=True,
    )
    for diagnostic_field in (
        "diagnostic_code",
        "diagnostic_detail_code",
        "diagnostic_context_code",
        "diagnostic_context_detail_code",
        "diagnostic_context_shape_code",
    ):
        assert diagnostic_field not in serialized_status
    assert transport.calls == [
        ("browser_navigate", {"url": CONVERSATION_URL}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_close", {}),
    ]
    assert_recovery_tools_only(transport)
    assert not {"browser_click", "browser_type"} & {
        tool for tool, _arguments in transport.calls
    }


@pytest.mark.parametrize(
    "diagnostic_context_shape_code",
    sorted(EXPECTED_BOUND_RESPONSE_PRECONTENT_CONTEXT_SHAPE_CODES),
)
def test_recovery_cli_emits_only_each_closed_container_shape_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    diagnostic_context_shape_code: str,
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
        diagnostic_context_shape_code,
    )
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    output = json.loads(capsys.readouterr().err)
    assert output == {
        "diagnostic_code": "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "diagnostic_context_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
        ),
        "diagnostic_context_detail_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID"
        ),
        "diagnostic_context_shape_code": diagnostic_context_shape_code,
        "diagnostic_detail_code": "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }
    serialized = json.dumps(output, sort_keys=True)
    for forbidden in (
        "Response actions",
        "ref-free label",
        "e987654",
        CONVERSATION_URL,
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "shape_code",
    [
        pytest.param(None, id="missing"),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING_COUNT_2",
            id="dynamic-suffix",
        ),
        pytest.param(
            " ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            id="left-padded",
        ),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING ",
            id="right-padded",
        ),
        pytest.param(
            "advanced_response_precontent_nested_container_ref_missing",
            id="wrong-case",
        ),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_UNKNOWN",
            id="unknown",
        ),
    ],
)
def test_main_omits_invalid_container_shape_and_preserves_existing_five_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    shape_code: str | None,
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
    )
    refusal.diagnostic_fallback_code = (
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID"
    )
    if shape_code is None:
        del refusal.diagnostic_context_shape_code
    else:
        refusal.diagnostic_context_shape_code = shape_code
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "diagnostic_code": "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "diagnostic_context_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
        ),
        "diagnostic_context_detail_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID"
        ),
        "diagnostic_detail_code": "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


@pytest.mark.parametrize(
    (
        "reason_code",
        "diagnostic_code",
        "detail_code",
        "context_code",
        "context_detail_code",
    ),
    [
        pytest.param(
            "RESPONSE_SELECTOR_AMBIGUITY",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            id="wrong-reason",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_HEADING_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            id="wrong-parent",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_DUPLICATE",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            id="wrong-detail",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            id="wrong-context",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID",
            id="wrong-context-detail",
        ),
    ],
)
def test_container_shape_requires_exact_six_field_conjunction(
    reason_code: str,
    diagnostic_code: str,
    detail_code: str,
    context_code: str,
    context_detail_code: str,
) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._validated_bound_response_context_shape_code(
            reason_code,
            diagnostic_code,
            detail_code,
            context_code,
            context_detail_code,
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
        )

    assert captured.value.code == "BOUND_RESPONSE_DIAGNOSTIC_INVALID"


def test_main_omits_container_shape_outside_exact_context_detail_conjunction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
    )
    refusal.diagnostic_context_detail_code = (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID"
    )
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "diagnostic_code": "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "diagnostic_context_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
        ),
        "diagnostic_context_detail_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID"
        ),
        "diagnostic_detail_code": "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


def test_container_shape_progress_tail_retry_remains_nonpersistent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    loading = f'- Page URL: {CONVERSATION_URL}\n- status "loading" [ref=e90]'
    raw_snapshot = ADVANCED_RESPONSE_PRECONTENT_CONTAINER_SHAPE_CASES[0].values[0]
    first = RecoveryTransport([*[loading] * 13, *[raw_snapshot] * 3])
    install_transport(monkeypatch, root, first)

    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert captured.value.diagnostic_context_shape_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING"
    )
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    progress_events = [
        event
        for event in event_list(run_dir)
        if event["event_type"] == "RESPONSE_WAIT_PROGRESS"
    ]
    assert len(progress_events) == 1
    progress_json = json.dumps(progress_events[0], sort_keys=True)
    assert "diagnostic_context_shape_code" not in progress_json
    record_after_first = (run_dir / "run-record.v1.jsonl").read_bytes()

    second = RecoveryTransport([raw_snapshot, raw_snapshot, raw_snapshot])
    install_transport(monkeypatch, root, second)
    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as retry:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert retry.value.diagnostic_context_shape_code == (
        captured.value.diagnostic_context_shape_code
    )
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_after_first
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert_recovery_tools_only(first)
    assert_recovery_tools_only(second)


def test_terminal_recovery_captures_stable_ref_free_embedded_response_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    response = advice_text("Recover the strict ref-free embedded response.")
    snapshots = [
        embedded_pre_content_response_snapshot(response, wrapper_ref=raw_ref)
        for raw_ref in ("e70", "e170", "e270")
    ]
    transport = RecoveryTransport(snapshots)
    install_transport(monkeypatch, root, transport)

    exit_code, result = orchestrator.resume(
        private_root=root,
        run_id=RUN_ID,
        fake_scenario=None,
    )

    assert exit_code == 0
    assert result["status"] == "ADVICE_CAPTURED"
    assert result["provenance"] == "AUTOMATED_BOUND_CONVERSATION_RECOVERY"
    assert result["resubmitted"] is False
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    record_after = (run_dir / "run-record.v1.jsonl").read_bytes()
    assert record_after.startswith(record_before)
    assert response.encode("utf-8") not in record_after
    events = event_list(run_dir)
    assert events[-1]["event_type"] == "BOUND_RESPONSE_RECOVERED"
    assert events[-1]["payload"]["resubmitted"] is False
    assert (
        sum(event["event_type"] == "SUBMISSION_INTENT_RECORDED" for event in events)
        == 1
    )
    proposal = (run_dir / "unapproved-proposal.md").read_text(encoding="utf-8")
    assert response in proposal
    assert not any(
        field in result
        for field in (
            "diagnostic_code",
            "diagnostic_detail_code",
            "diagnostic_context_code",
            "diagnostic_context_detail_code",
            "diagnostic_context_shape_code",
            "diagnostic_fallback_code",
            "diagnostic_fallback_entry_code",
        )
    )
    assert transport.calls == [
        ("browser_navigate", {"url": CONVERSATION_URL}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_close", {}),
    ]
    assert_recovery_tools_only(transport)
    assert not {"browser_click", "browser_type"} & {
        tool for tool, _arguments in transport.calls
    }

    record_before_repeat = record_after
    repeat_code, repeat = orchestrator.resume(
        private_root=root,
        run_id=RUN_ID,
        fake_scenario=None,
    )
    assert repeat_code == 0
    assert repeat == result
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before_repeat
    assert transport.calls.count(("browser_close", {})) == 1


def test_terminal_ref_free_recovery_ignores_complete_outside_opaque_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    _run_dir, state = create_terminal_run(root)
    response = advice_text("Ignore a complete outside opaque collision source.")
    raw_snapshot = embedded_pre_content_response_snapshot(
        response,
        wrapper_ref="e70",
        before_group=(
            '    - button "Opaque" [ref=e70]:',
            '      - text: "ignored chrome"',
        ),
    )
    transport = RecoveryTransport([raw_snapshot, raw_snapshot, raw_snapshot])
    install_transport(monkeypatch, root, transport)

    exit_code, result = orchestrator.resume(
        private_root=root,
        run_id=state["run_id"],
        fake_scenario=None,
    )

    assert exit_code == 0
    assert result["status"] == "ADVICE_CAPTURED"
    assert result["resubmitted"] is False
    assert "diagnostic_fallback_code" not in result
    assert "diagnostic_fallback_entry_code" not in result
    assert_recovery_tools_only(transport)


def test_terminal_recovery_accepts_stable_silent_wrapper_churn_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    response = advice_text("Recover only the embedded response.")
    snapshots = [
        embedded_pre_content_response_snapshot(
            response,
            before_group=(
                f'    - paragraph "silent-{index}" [disabled] [ref={raw_ref}]:',
                f'      - quote "nested-{index}" [ref=e{index + 80}]:',
            ),
        )
        for index, raw_ref in enumerate(("e70", "e170", "e270"), start=1)
    ]
    transport = RecoveryTransport(snapshots)
    install_transport(monkeypatch, root, transport)

    exit_code, result = orchestrator.resume(
        private_root=root,
        run_id=RUN_ID,
        fake_scenario=None,
    )

    assert exit_code == 0
    assert result["status"] == "ADVICE_CAPTURED"
    assert result["provenance"] == "AUTOMATED_BOUND_CONVERSATION_RECOVERY"
    assert result["resubmitted"] is False
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    record_after = (run_dir / "run-record.v1.jsonl").read_bytes()
    assert record_after.startswith(record_before)
    assert response.encode("utf-8") not in record_after
    proposal = (run_dir / "unapproved-proposal.md").read_text(encoding="utf-8")
    assert response in proposal
    assert "silent-" not in proposal
    events = event_list(run_dir)
    assert events[-1]["event_type"] == "BOUND_RESPONSE_RECOVERED"
    assert events[-1]["payload"]["resubmitted"] is False
    assert (
        sum(event["event_type"] == "SUBMISSION_INTENT_RECORDED" for event in events)
        == 1
    )
    assert transport.calls.count(("browser_wait_for", {"time": 5})) == 2
    assert not {"browser_click", "browser_type"} & {
        tool for tool, _arguments in transport.calls
    }
    assert_recovery_tools_only(transport)

    record_before_repeat = record_after
    repeat_code, repeat = orchestrator.resume(
        private_root=root,
        run_id=RUN_ID,
        fake_scenario=None,
    )
    assert repeat_code == 0
    assert repeat == result
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before_repeat
    assert transport.calls.count(("browser_close", {})) == 1


def test_silent_wrapper_becoming_non_silent_resets_terminal_stability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    response = advice_text("Capture only after silent wrapper restabilization.")
    silent = embedded_pre_content_response_snapshot(
        response,
        before_group=('    - paragraph "silent" [ref=e70]:',),
    )
    non_silent = silent.replace(
        '    - paragraph "silent" [ref=e70]:',
        '    - paragraph "silent" [ref=e70]:\n      - statictext: "   "',
    )
    transport = RecoveryTransport([silent, silent, non_silent, silent, silent, silent])
    install_transport(monkeypatch, root, transport)

    exit_code, result = orchestrator.resume(
        private_root=root,
        run_id=RUN_ID,
        fake_scenario=None,
    )

    assert exit_code == 0
    assert result["status"] == "ADVICE_CAPTURED"
    assert result["resubmitted"] is False
    assert transport.calls.count(("browser_wait_for", {"time": 5})) == 5
    proposal = (run_dir / "unapproved-proposal.md").read_text(encoding="utf-8")
    assert response in proposal
    assert_recovery_tools_only(transport)


def test_embedded_response_change_resets_terminal_recovery_stability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    first_response = advice_text("First embedded candidate.")
    final_response = advice_text("Final embedded candidate.")
    first = embedded_pre_content_response_snapshot(first_response)
    final = embedded_pre_content_response_snapshot(final_response)
    transport = RecoveryTransport([first, first, final, final, final])
    install_transport(monkeypatch, root, transport)

    exit_code, result = orchestrator.resume(
        private_root=root,
        run_id=RUN_ID,
        fake_scenario=None,
    )

    assert exit_code == 0
    assert result["status"] == "ADVICE_CAPTURED"
    proposal = (run_dir / "unapproved-proposal.md").read_text(encoding="utf-8")
    assert final_response in proposal
    assert first_response not in proposal
    assert transport.calls.count(("browser_wait_for", {"time": 5})) == 4
    assert transport.calls.count(("browser_snapshot", {})) == 5
    assert_recovery_tools_only(transport)


@pytest.mark.parametrize(
    "invalid_descendant",
    [
        pytest.param("      - generic [ref=bad]:", id="malformed-ref"),
        pytest.param("      - text: unquoted", id="malformed-scalar"),
        pytest.param('      - widget: "unsupported"', id="unsupported-material"),
    ],
)
def test_invalid_embedded_fallback_keeps_terminal_state_and_proposal_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_descendant: str,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    invalid = embedded_pre_content_response_snapshot(
        advice_text(),
        extra_descendants=(invalid_descendant,),
    )
    transport = RecoveryTransport([invalid, invalid, invalid])
    install_transport(monkeypatch, root, transport)

    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_context_shape_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING"
    )
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert_recovery_tools_only(transport)


@pytest.mark.parametrize(
    ("before_group", "after_group"),
    [
        pytest.param(('    - text: ""',), (), id="empty-scalar-before"),
        pytest.param((), ('    - statictext: "   "',), id="whitespace-after"),
    ],
)
def test_outside_embedded_material_never_creates_recovery_proposal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    before_group: tuple[str, ...],
    after_group: tuple[str, ...],
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    invalid = embedded_pre_content_response_snapshot(
        advice_text(),
        before_group=before_group,
        after_group=after_group,
    )
    transport = RecoveryTransport([invalid, invalid, invalid])
    install_transport(monkeypatch, root, transport)

    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert captured.value.diagnostic_context_shape_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING"
    )
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert_recovery_tools_only(transport)


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(
            "session_token=abcdefghijklmnop",
            id="sensitive",
        ),
        pytest.param(
            "A" * (workflow.MAX_TEXT_BYTES + 1),
            id="over-size-limit",
        ),
    ],
)
def test_embedded_recovery_applies_policy_after_stability_without_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response: str,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    raw_snapshot = embedded_pre_content_response_snapshot(
        response,
        before_group=('    - paragraph "silent policy wrapper" [ref=e70]:',),
    )
    transport = RecoveryTransport([raw_snapshot, raw_snapshot, raw_snapshot])
    install_transport(monkeypatch, root, transport)

    with pytest.raises((orchestrator.OrchestrationRefusal, workflow.WorkflowRefusal)):
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert transport.calls.count(("browser_wait_for", {"time": 5})) == 2
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert_recovery_tools_only(transport)


def _assert_exact_ref_free_fallback_refusal(
    refusal: orchestrator._AdvancedResponseParserRefusal
    | orchestrator._BoundResponseRecoveryRefusal,
    fallback_code: str,
) -> None:
    assert refusal.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert refusal.diagnostic_code == "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    assert refusal.diagnostic_detail_code == "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
    assert refusal.diagnostic_context_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
    )
    assert refusal.diagnostic_context_detail_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID"
    )
    assert refusal.diagnostic_context_shape_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING"
    )
    assert refusal.diagnostic_fallback_code == fallback_code
    assert not hasattr(refusal, "diagnostic_fallback_entry_code")


def _assert_exact_ref_free_fallback_entry_refusal(
    refusal: orchestrator._AdvancedResponseParserRefusal
    | orchestrator._BoundResponseRecoveryRefusal,
    fallback_entry_code: str,
) -> None:
    assert refusal.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert refusal.diagnostic_code == "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    assert refusal.diagnostic_detail_code == "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
    assert refusal.diagnostic_context_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
    )
    assert refusal.diagnostic_context_detail_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID"
    )
    assert refusal.diagnostic_context_shape_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING"
    )
    assert refusal.diagnostic_fallback_entry_code == fallback_entry_code
    assert not hasattr(refusal, "diagnostic_fallback_code")


def test_ref_free_fallback_recovery_allowlist_is_exact() -> None:
    assert (
        orchestrator.BOUND_RESPONSE_REF_FREE_FALLBACK_CODES
        == EXPECTED_BOUND_RESPONSE_REF_FREE_FALLBACK_CODES
    )
    assert {
        case.values[1] for case in ADVANCED_RESPONSE_REF_FREE_FALLBACK_CASES
    } == EXPECTED_BOUND_RESPONSE_REF_FREE_FALLBACK_CODES
    for fallback_code in EXPECTED_BOUND_RESPONSE_REF_FREE_FALLBACK_CODES:
        assert (
            orchestrator._validated_bound_response_ref_free_fallback_code(fallback_code)
            == fallback_code
        )


def test_ref_free_fallback_entry_recovery_allowlist_is_exact() -> None:
    assert (
        orchestrator.BOUND_RESPONSE_REF_FREE_FALLBACK_ENTRY_CODES
        == EXPECTED_BOUND_RESPONSE_REF_FREE_FALLBACK_ENTRY_CODES
    )
    assert {
        case.values[1] for case in ADVANCED_RESPONSE_REF_FREE_FALLBACK_ENTRY_CASES
    } == EXPECTED_BOUND_RESPONSE_REF_FREE_FALLBACK_ENTRY_CODES
    for fallback_entry_code in EXPECTED_BOUND_RESPONSE_REF_FREE_FALLBACK_ENTRY_CODES:
        assert (
            orchestrator._validated_bound_response_ref_free_fallback_entry_code(
                fallback_entry_code
            )
            == fallback_entry_code
        )
        assert (
            orchestrator._validated_bound_response_fallback_entry_code(
                "RESPONSE_NOT_IDENTIFIABLE",
                "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
                "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
                "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
                "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
                "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
                None,
                fallback_entry_code,
            )
            == fallback_entry_code
        )


@pytest.mark.parametrize(
    ("raw_snapshot", "fallback_entry_code"),
    ADVANCED_RESPONSE_REF_FREE_FALLBACK_ENTRY_CASES,
)
def test_ref_free_fallback_entry_refusals_have_exact_seven_field_conjunction(
    raw_snapshot: str,
    fallback_entry_code: str,
) -> None:
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
            allow_bound_precontent_fallback=True,
        )

    _assert_exact_ref_free_fallback_entry_refusal(
        captured.value,
        fallback_entry_code,
    )


@pytest.mark.parametrize(
    ("raw_snapshot", "fallback_entry_code"),
    ADVANCED_RESPONSE_REF_FREE_FALLBACK_ENTRY_CASES,
)
def test_terminal_recovery_reports_each_ref_free_fallback_entry_without_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_snapshot: str,
    fallback_entry_code: str,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    transport = RecoveryTransport([raw_snapshot, raw_snapshot, raw_snapshot])
    install_transport(monkeypatch, root, transport)

    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    _assert_exact_ref_free_fallback_entry_refusal(
        captured.value,
        fallback_entry_code,
    )
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    serialized_status = json.dumps(
        orchestrator.status(private_root=root, run_id=RUN_ID),
        sort_keys=True,
    )
    for diagnostic_field in (
        "diagnostic_code",
        "diagnostic_detail_code",
        "diagnostic_context_code",
        "diagnostic_context_detail_code",
        "diagnostic_context_shape_code",
        "diagnostic_fallback_code",
        "diagnostic_fallback_entry_code",
    ):
        assert diagnostic_field not in serialized_status
    assert transport.calls == [
        ("browser_navigate", {"url": CONVERSATION_URL}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_close", {}),
    ]
    assert_recovery_tools_only(transport)
    assert not {"browser_click", "browser_type"} & {
        tool for tool, _arguments in transport.calls
    }


@pytest.mark.parametrize(
    ("raw_snapshot", "fallback_code"),
    ADVANCED_RESPONSE_REF_FREE_FALLBACK_CASES,
)
def test_ref_free_fallback_failures_have_exact_seven_field_conjunction(
    raw_snapshot: str,
    fallback_code: str,
) -> None:
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=workflow.ADVANCED_PROFILE_ID,
            allow_bound_precontent_fallback=True,
        )

    _assert_exact_ref_free_fallback_refusal(captured.value, fallback_code)


@pytest.mark.parametrize(
    ("raw_snapshot", "fallback_code"),
    ADVANCED_RESPONSE_REF_FREE_FALLBACK_CASES,
)
def test_terminal_recovery_reports_each_ref_free_fallback_failure_without_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_snapshot: str,
    fallback_code: str,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    record_before = (run_dir / "run-record.v1.jsonl").read_bytes()
    transport = RecoveryTransport([raw_snapshot, raw_snapshot, raw_snapshot])
    install_transport(monkeypatch, root, transport)

    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    _assert_exact_ref_free_fallback_refusal(captured.value, fallback_code)
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    serialized_status = json.dumps(
        orchestrator.status(private_root=root, run_id=RUN_ID),
        sort_keys=True,
    )
    for diagnostic_field in (
        "diagnostic_code",
        "diagnostic_detail_code",
        "diagnostic_context_code",
        "diagnostic_context_detail_code",
        "diagnostic_context_shape_code",
        "diagnostic_fallback_code",
        "diagnostic_fallback_entry_code",
    ):
        assert diagnostic_field not in serialized_status
    assert transport.calls == [
        ("browser_navigate", {"url": CONVERSATION_URL}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_close", {}),
    ]
    assert_recovery_tools_only(transport)
    assert not {"browser_click", "browser_type"} & {
        tool for tool, _arguments in transport.calls
    }


@pytest.mark.parametrize(
    "fallback_code",
    sorted(EXPECTED_BOUND_RESPONSE_REF_FREE_FALLBACK_CODES),
)
def test_recovery_cli_emits_only_each_closed_ref_free_fallback_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fallback_code: str,
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
        fallback_code,
    )
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    output = json.loads(capsys.readouterr().err)
    assert output == {
        "diagnostic_code": "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "diagnostic_context_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
        ),
        "diagnostic_context_detail_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID"
        ),
        "diagnostic_context_shape_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING"
        ),
        "diagnostic_detail_code": "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "diagnostic_fallback_code": fallback_code,
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }
    serialized = json.dumps(output, sort_keys=True)
    for forbidden in (
        "Response actions",
        "Visible",
        "unsupported",
        "e70",
        CONVERSATION_URL,
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "fallback_code",
    [
        pytest.param(None, id="missing"),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID_COUNT_2",
            id="dynamic-suffix",
        ),
        pytest.param(
            " ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID",
            id="left-padded",
        ),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID ",
            id="right-padded",
        ),
        pytest.param(
            "advanced_response_precontent_ref_free_wrapper_invalid",
            id="wrong-case",
        ),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_UNKNOWN",
            id="unknown",
        ),
        pytest.param(
            ["ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID"],
            id="list",
        ),
        pytest.param(
            {"code": "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID"},
            id="mapping",
        ),
    ],
)
def test_main_omits_invalid_fallback_code_and_preserves_existing_six_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fallback_code: object,
) -> None:
    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID",
    )
    if fallback_code is None:
        del refusal.diagnostic_fallback_code
    else:
        refusal.diagnostic_fallback_code = fallback_code
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "diagnostic_code": "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "diagnostic_context_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
        ),
        "diagnostic_context_detail_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID"
        ),
        "diagnostic_context_shape_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING"
        ),
        "diagnostic_detail_code": "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


@pytest.mark.parametrize(
    (
        "reason_code",
        "diagnostic_code",
        "detail_code",
        "context_code",
        "context_detail_code",
        "context_shape_code",
    ),
    [
        pytest.param(
            "RESPONSE_SELECTOR_AMBIGUITY",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            id="wrong-reason",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_HEADING_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            id="wrong-parent",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_DUPLICATE",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            id="wrong-detail",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            id="wrong-context",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            id="wrong-context-detail",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID",
            id="wrong-context-shape",
        ),
    ],
)
def test_ref_free_fallback_code_requires_exact_existing_six_field_conjunction(
    reason_code: str,
    diagnostic_code: str,
    detail_code: str,
    context_code: str,
    context_detail_code: str,
    context_shape_code: str,
) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._validated_bound_response_fallback_code(
            reason_code,
            diagnostic_code,
            detail_code,
            context_code,
            context_detail_code,
            context_shape_code,
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID",
        )

    assert captured.value.code == "BOUND_RESPONSE_DIAGNOSTIC_INVALID"


def test_ref_free_fallback_progress_tail_retry_remains_nonpersistent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    loading = f'- Page URL: {CONVERSATION_URL}\n- status "loading" [ref=e90]'
    raw_snapshot = ADVANCED_RESPONSE_REF_FREE_FALLBACK_CASES[0].values[0]
    first = RecoveryTransport([*[loading] * 13, *[raw_snapshot] * 3])
    install_transport(monkeypatch, root, first)

    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    _assert_exact_ref_free_fallback_refusal(
        captured.value,
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID",
    )
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    progress_events = [
        event
        for event in event_list(run_dir)
        if event["event_type"] == "RESPONSE_WAIT_PROGRESS"
    ]
    assert len(progress_events) == 1
    progress_json = json.dumps(progress_events[0], sort_keys=True)
    assert "diagnostic_fallback_code" not in progress_json
    assert "diagnostic_fallback_entry_code" not in progress_json
    record_after_first = (run_dir / "run-record.v1.jsonl").read_bytes()

    second = RecoveryTransport([raw_snapshot, raw_snapshot, raw_snapshot])
    install_transport(monkeypatch, root, second)
    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as retry:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert retry.value.diagnostic_fallback_code == (
        captured.value.diagnostic_fallback_code
    )
    assert not hasattr(retry.value, "diagnostic_fallback_entry_code")
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_after_first
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert_recovery_tools_only(first)
    assert_recovery_tools_only(second)


def bound_response_fallback_entry_refusal(
    fallback_entry_code: str,
) -> orchestrator._BoundResponseRecoveryRefusal:
    return orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
        None,
        fallback_entry_code,
    )


@pytest.mark.parametrize(
    "fallback_entry_code",
    sorted(EXPECTED_BOUND_RESPONSE_REF_FREE_FALLBACK_ENTRY_CODES),
)
def test_recovery_cli_emits_only_each_closed_ref_free_fallback_entry_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fallback_entry_code: str,
) -> None:
    refusal = bound_response_fallback_entry_refusal(fallback_entry_code)
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    output = json.loads(capsys.readouterr().err)
    assert output == {
        "diagnostic_code": "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "diagnostic_context_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
        ),
        "diagnostic_context_detail_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID"
        ),
        "diagnostic_context_shape_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING"
        ),
        "diagnostic_detail_code": "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "diagnostic_fallback_entry_code": fallback_entry_code,
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }
    serialized = json.dumps(output, sort_keys=True)
    assert "diagnostic_fallback_code" not in output
    for forbidden in (
        "Response actions",
        "Visible",
        "paragraph",
        "e80",
        CONVERSATION_URL,
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "fallback_entry_code",
    [
        pytest.param(None, id="missing"),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR_COUNT_2",
            id="dynamic-suffix",
        ),
        pytest.param(
            " ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR",
            id="left-padded",
        ),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR ",
            id="right-padded",
        ),
        pytest.param(
            "advanced_response_precontent_ref_free_entry_outside_whitespace_scalar",
            id="wrong-case",
        ),
        pytest.param(
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_UNKNOWN",
            id="unknown",
        ),
        pytest.param(
            ["ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR"],
            id="list",
        ),
        pytest.param(
            {
                "code": "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR"
            },
            id="mapping",
        ),
    ],
)
def test_main_omits_invalid_fallback_entry_and_preserves_existing_six_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fallback_entry_code: object,
) -> None:
    refusal = bound_response_fallback_entry_refusal(
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR"
    )
    if fallback_entry_code is None:
        del refusal.diagnostic_fallback_entry_code
    else:
        refusal.diagnostic_fallback_entry_code = fallback_entry_code
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    exit_code = invoke_orchestrator_main(
        [
            "resume",
            "--private-root",
            str(tmp_path),
            "--run-id",
            RUN_ID,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "diagnostic_code": "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "diagnostic_context_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
        ),
        "diagnostic_context_detail_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID"
        ),
        "diagnostic_context_shape_code": (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING"
        ),
        "diagnostic_detail_code": "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "reason_code": "RESPONSE_NOT_IDENTIFIABLE",
        "status": "REFUSED",
        "story_id": "ST-0101",
    }


@pytest.mark.parametrize(
    (
        "reason_code",
        "diagnostic_code",
        "detail_code",
        "context_code",
        "context_detail_code",
        "context_shape_code",
        "fallback_code",
    ),
    [
        pytest.param(
            "RESPONSE_SELECTOR_AMBIGUITY",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            None,
            id="wrong-reason",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_HEADING_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            None,
            id="wrong-parent",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_DUPLICATE",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            None,
            id="wrong-detail",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            None,
            id="wrong-context",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            None,
            id="wrong-context-detail",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID",
            None,
            id="wrong-context-shape",
        ),
        pytest.param(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID",
            id="attempted-fallback-mutual-exclusion",
        ),
    ],
)
def test_ref_free_fallback_entry_requires_exact_unattempted_six_field_conjunction(
    reason_code: str,
    diagnostic_code: str,
    detail_code: str,
    context_code: str,
    context_detail_code: str,
    context_shape_code: str,
    fallback_code: str | None,
) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._validated_bound_response_fallback_entry_code(
            reason_code,
            diagnostic_code,
            detail_code,
            context_code,
            context_detail_code,
            context_shape_code,
            fallback_code,
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR",
        )

    assert captured.value.code == "BOUND_RESPONSE_DIAGNOSTIC_INVALID"


def test_ref_free_fallback_and_entry_diagnostics_are_mutually_exclusive_in_constructor_and_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._BoundResponseRecoveryRefusal(
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID",
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR",
        )
    assert captured.value.code == "BOUND_RESPONSE_DIAGNOSTIC_INVALID"

    refusal = orchestrator._BoundResponseRecoveryRefusal(
        "RESPONSE_NOT_IDENTIFIABLE",
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID",
    )
    refusal.diagnostic_fallback_entry_code = (
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR"
    )
    monkeypatch.setattr(orchestrator, "_physical_repository_guard", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "resume",
        lambda **_kwargs: (_ for _ in ()).throw(refusal),
    )
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", tmp_path)

    assert (
        invoke_orchestrator_main(
            [
                "resume",
                "--private-root",
                str(tmp_path),
                "--run-id",
                RUN_ID,
            ]
        )
        == 2
    )
    output = json.loads(capsys.readouterr().err)
    assert output["diagnostic_fallback_code"] == (
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID"
    )
    assert "diagnostic_fallback_entry_code" not in output


def test_ref_free_fallback_entry_progress_tail_retry_remains_nonpersistent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    run_dir, _state = create_terminal_run(root)
    state_before = (run_dir / "orchestration-state.v1.json").read_bytes()
    loading = f'- Page URL: {CONVERSATION_URL}\n- status "loading" [ref=e90]'
    raw_snapshot = ADVANCED_RESPONSE_REF_FREE_FALLBACK_ENTRY_CASES[0].values[0]
    first = RecoveryTransport([*[loading] * 13, *[raw_snapshot] * 3])
    install_transport(monkeypatch, root, first)

    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    _assert_exact_ref_free_fallback_entry_refusal(
        captured.value,
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR",
    )
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    progress_events = [
        event
        for event in event_list(run_dir)
        if event["event_type"] == "RESPONSE_WAIT_PROGRESS"
    ]
    assert len(progress_events) == 1
    progress_json = json.dumps(progress_events[0], sort_keys=True)
    assert "diagnostic_fallback_entry_code" not in progress_json
    record_after_first = (run_dir / "run-record.v1.jsonl").read_bytes()

    second = RecoveryTransport([raw_snapshot, raw_snapshot, raw_snapshot])
    install_transport(monkeypatch, root, second)
    with pytest.raises(orchestrator._BoundResponseRecoveryRefusal) as retry:
        orchestrator.resume(
            private_root=root,
            run_id=RUN_ID,
            fake_scenario=None,
        )

    assert retry.value.diagnostic_fallback_entry_code == (
        captured.value.diagnostic_fallback_entry_code
    )
    assert not hasattr(retry.value, "diagnostic_fallback_code")
    assert (run_dir / "run-record.v1.jsonl").read_bytes() == record_after_first
    assert (run_dir / "orchestration-state.v1.json").read_bytes() == state_before
    assert not (run_dir / "unapproved-proposal.md").exists()
    assert_recovery_tools_only(first)
    assert_recovery_tools_only(second)
