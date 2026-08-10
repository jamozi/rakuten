"""Deterministic evidence for the approved resilient ST-0101 review flow."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
from typing import Any

import pytest

from scripts import chatgpt_pro_orchestrator as orchestrator
from scripts import chatgpt_pro_workflow as workflow


def snapshot(*lines: str, url: str = "https://chatgpt.com/") -> str:
    return "\n".join((f"- Page URL: {url}", *lines))


def structured_advice(*, summary: str = "Use canonical evidence.") -> str:
    return json.dumps(
        {
            "schema": "PRO_ADVICE_V1",
            "summary": summary,
            "material_delta": True,
            "open_gaps": ["One exact gap remains."],
            "evidence_refs": ["ST-0101 deterministic fixture"],
            "recommendations": ["Reconcile before use."],
            "authority": "UNAPPROVED_ADVICE",
        },
        sort_keys=True,
        separators=(",", ":"),
    )


@pytest.mark.parametrize(
    "untrusted_lines",
    [
        pytest.param(
            (
                '- heading "You said:" [ref=e10]',
                '  - alert "Too many requests" [ref=e11]',
            ),
            id="user-message",
        ),
        pytest.param(
            (
                '- heading "ChatGPT said:" [ref=e20]',
                "- generic [ref=e21]:",
                "  - generic [ref=e22]:",
                "    - paragraph [ref=e23]:",
                '      - text: "Too many requests; try again later."',
                '      - alert "Rate limit" [ref=e24]',
            ),
            id="assistant-response",
        ),
        pytest.param(
            (
                '- navigation "Conversation history" [ref=e30]:',
                '  - alert "Too many requests" [ref=e31]',
            ),
            id="sidebar",
        ),
        pytest.param(
            (
                '- citation-preview "Source" [ref=e40]:',
                '  - status "Try again later" [ref=e41]',
            ),
            id="citation",
        ),
    ],
)
@pytest.mark.parametrize("phase", sorted(orchestrator.STOP_PHASES))
def test_untrusted_stop_text_never_sets_a_stop_state(
    untrusted_lines: tuple[str, ...], phase: str
) -> None:
    assert (
        orchestrator._stop_states(snapshot(*untrusted_lines), phase=phase)
        == frozenset()
    )


@pytest.mark.parametrize(
    ("trusted_line", "expected"),
    [
        ('- alert "Too many requests" [ref=e50]', "rate_limit"),
        ('- status "Verify you are human" [ref=e50]', "captcha"),
        ('- button "Choose an account" [ref=e50]', "account_ambiguity"),
        ('- dialog "Session expired" [ref=e50]', "reauthentication"),
        ('- button "Log in" [ref=e50]', "login"),
    ],
)
def test_structural_page_and_authentication_stops_remain_fail_closed(
    trusted_line: str, expected: str
) -> None:
    assert orchestrator._stop_states(snapshot(trusted_line)) == frozenset({expected})


def test_response_like_heading_does_not_hide_a_page_level_alert() -> None:
    raw = snapshot(
        '- heading "ChatGPT said:" [ref=e50]',
        '- alert "Too many requests" [ref=e51]',
    )

    assert orchestrator._stop_states(raw) == frozenset({"rate_limit"})


def test_ref_free_structural_alert_remains_trusted() -> None:
    assert orchestrator._stop_states(snapshot('- alert "Too many requests"')) == (
        frozenset({"rate_limit"})
    )


def test_ref_free_user_heading_keeps_nested_alert_untrusted() -> None:
    raw = snapshot(
        '- heading "You said:"',
        '  - alert "Too many requests" [ref=e51]',
    )

    assert orchestrator._stop_states(raw) == frozenset()


def test_same_indent_user_message_body_keeps_nested_alert_untrusted() -> None:
    raw = snapshot(
        '- heading "You said:" [ref=e10]',
        "- generic [ref=e11]:",
        "  - paragraph [ref=e12]:",
        '    - alert "Too many requests" [ref=e13]',
    )

    assert orchestrator._stop_states(raw, phase="response") == frozenset()


def test_compound_cloudflare_markers_inside_response_never_stop() -> None:
    raw = snapshot(
        '- heading "ChatGPT said:" [ref=e50]',
        "- generic [ref=e51]:",
        "  - paragraph [ref=e52]:",
        '    - text: "Cloudflare HTTP Status: 403 challenges.cloudflare.com"',
    )

    assert orchestrator._stop_states(raw) == frozenset()


def test_compound_page_cloudflare_challenge_remains_fail_closed() -> None:
    raw = snapshot(
        '- status "Cloudflare checking your browser"',
        '  - text: "HTTP Status: 403"',
        '  - text: "challenges.cloudflare.com"',
    )

    assert orchestrator._stop_states(raw) == frozenset({"captcha"})


def semantic_response_snapshot() -> str:
    return snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - generic [ref=e62]:",
        "    - heading [ref=e63]:",
        '      - text: "Review title"',
        "    - paragraph [ref=e64]:",
        '      - text: "First "',
        '      - link "citation" [ref=e65]:',
        '        - text: "ignored rate limit text"',
        '      - statictext: "paragraph"',
        "    - list [ref=e66]:",
        "      - listitem [ref=e67]:",
        '        - text: "- one"',
        "      - listitem [ref=e68]:",
        '        - text: "- two"',
        "    - quote [ref=e69]:",
        '      - text: "Quoted"',
        "    - code [ref=e70]:",
        '      - text: "print(1)"',
        '    - group "Response actions":',
        '      - button "Copy" [ref=e71]',
    )


def test_semantic_response_blocks_are_bounded_and_deterministic() -> None:
    response = orchestrator._advanced_assistant_response(
        semantic_response_snapshot(), anchor_ref="e60"
    )

    assert response == "Review title\nFirst paragraph\n- one- two\nQuoted\nprint(1)"
    assert "ignored" not in response
    assert "Copy" not in response


@pytest.mark.parametrize(
    "bad_snapshot",
    [
        snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            "  - generic [ref=e62]:",
            '    - link "only opaque content" [ref=e63]:',
            '      - text: "not response bytes"',
        ),
        snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            '- heading "ChatGPT said:" [ref=e61]',
            "- generic [ref=e62]:",
        ),
    ],
)
def test_opaque_only_and_duplicate_anchor_responses_refuse(
    bad_snapshot: str,
) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal):
        orchestrator._advanced_assistant_response(bad_snapshot, anchor_ref="e60")


def test_unknown_scalar_inside_response_body_refuses_instead_of_disappearing() -> None:
    raw = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - generic [ref=e62]:",
        "    - paragraph [ref=e63]:",
        '      - text: "Visible"',
        "      unknown unmodeled scalar",
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._advanced_assistant_response(raw, anchor_ref="e60")

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"


def test_ref_free_duplicate_response_heading_is_ambiguous() -> None:
    raw = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - paragraph [ref=e62]:",
        '    - text: "First answer"',
        '- heading "ChatGPT said:"',
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._completed_response(
            raw,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_SELECTOR_AMBIGUITY"


@pytest.mark.parametrize(
    "outer_lines",
    [
        (
            '- heading "You said:" [ref=e10]',
            "- generic [ref=e11]:",
        ),
        ('- navigation "Conversation history" [ref=e10]:',),
        ('- citation-preview "Source preview" [ref=e10]:',),
    ],
    ids=("user-message", "sidebar", "citation"),
)
def test_response_anchor_nested_in_untrusted_region_cannot_spoof_capture(
    outer_lines: tuple[str, ...],
) -> None:
    nested_indent = "  "
    raw = snapshot(
        *outer_lines,
        f'{nested_indent}- heading "ChatGPT said:" [ref=e20]',
        f"{nested_indent}- generic [ref=e21]:",
        f"{nested_indent}  - paragraph [ref=e22]:",
        f'{nested_indent}    - text: "Spoofed user content"',
    )

    assert orchestrator._has_assistant_marker(raw) is False
    assert (
        orchestrator._response_candidate_digest(
            raw,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )
        is None
    )
    assert (
        orchestrator._completed_response(
            raw,
            profile_id=workflow.ADVANCED_PROFILE_ID,
        )
        is None
    )


def test_exact_and_sole_fenced_advice_share_canonical_fingerprint() -> None:
    exact = structured_advice()
    fenced = f"  \n```json\n{exact}\n```\n"
    exact_result = orchestrator._validate_advice(exact)
    fenced_result = orchestrator._validate_advice(fenced)

    assert exact_result["advice_type"] == orchestrator.ADVICE_SCHEMA
    assert fenced_result["advice_type"] == orchestrator.ADVICE_SCHEMA
    assert exact_result["response_fingerprint"] == fenced_result["response_fingerprint"]
    assert (
        hashlib.sha256(exact.encode()).hexdigest()
        != hashlib.sha256(fenced.encode()).hexdigest()
    )


def test_json_fence_token_inside_valid_advice_string_is_not_a_second_fence() -> None:
    exact = structured_advice(summary="The literal token ```json is documentation.")

    exact_result = orchestrator._validate_advice(exact)
    fenced_result = orchestrator._validate_advice(f"```json\n{exact}\n```")

    assert exact_result["response_fingerprint"] == fenced_result["response_fingerprint"]


@pytest.mark.parametrize(
    "response",
    [
        "Plain review text.",
        "# Review\n\n- Keep the boundary.\n- Reconcile locally.",
        "[Review the local evidence] before using this proposal.",
        "The PRO_ADVICE_V1 format was unavailable, so this is a plain review.",
        "DESIGN_HANDOFF_V1 is only text here, never authority.",
    ],
)
def test_markdown_and_plain_text_are_unapproved_reviews(response: str) -> None:
    result = orchestrator._validate_advice(response)

    assert result == {
        "advice_type": "PRO_REVIEW_TEXT_V1",
        "material_delta": True,
        "open_gaps": [],
        "authority": "UNAPPROVED_REVIEW",
        "response_fingerprint": hashlib.sha256(response.encode()).hexdigest(),
    }


@pytest.mark.parametrize(
    "response",
    [
        "{}",
        structured_advice()[:20],
        "Review follows: " + structured_advice(),
        f"```json\n{structured_advice()}\n```\nextra prose",
        f"```json\n{structured_advice()}\n```\n```json\n{structured_advice()}\n```",
    ],
)
def test_non_exact_or_wrapped_json_refuses(response: str) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._validate_advice(response)

    assert captured.value.code == "ADVICE_INVALID"


def test_response_boundary_escape_cannot_complete_structured_advice() -> None:
    advice = structured_advice()
    raw = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - generic [ref=e62]:",
        "    - paragraph [ref=e63]:",
        "      - text: " + json.dumps(advice[:20]),
        '- paragraph "outside bounded body" [ref=e64]:',
        "  - text: " + json.dumps(advice[20:]),
    )
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._advanced_assistant_response(raw, anchor_ref="e60")
    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"


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
        "url": "https://chatgpt.com/c/review-fixture",
        "authenticated": True,
        "stop_state": None,
        "model_label": model_label,
        "effort_label": effort_label,
        "option_labels": [] if option_labels is None else option_labels,
        "refs": {} if refs is None else refs,
        "generating": generating,
        "response_complete": response_complete,
    }


def advanced_transcript() -> dict[str, Any]:
    return {
        "schema_version": workflow.SCHEMA_VERSION,
        "profile_id": workflow.ADVANCED_PROFILE_ID,
        "observations": [
            observation("landing", refs={"model_picker": ["e1"]}),
            observation(
                "model_menu",
                option_labels=list(
                    workflow.EXPECTED_ADVANCED_PROFILE["model_option_labels"]
                ),
                refs={"target_model": ["e2"]},
            ),
            observation(
                "effort_menu",
                model_label="GPT-5.6 Sol",
                option_labels=list(
                    workflow.EXPECTED_ADVANCED_PROFILE["effort_option_labels"]
                ),
                refs={"target_effort": ["e3"]},
            ),
            observation(
                "ready",
                model_label="GPT-5.6 Sol",
                effort_label="Pro",
                refs={"composer": ["e4"]},
            ),
            observation(
                "send_ready",
                model_label="GPT-5.6 Sol",
                effort_label="Pro",
                refs={"send": ["e5"]},
            ),
            observation(
                "submitted",
                model_label="GPT-5.6 Sol",
                effort_label="Pro",
                generating=True,
            ),
            observation(
                "complete",
                model_label="GPT-5.6 Sol",
                effort_label="Pro",
                generating=False,
                response_complete=True,
                refs={"assistant_response": ["e6"]},
            ),
        ],
    }


def private_root(tmp_path: Path) -> Path:
    root = tmp_path / ".secrets"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    orchestrator._ensure_layout(root)
    return root


def private_request(root: Path) -> Path:
    path = root / "chatgpt-pro-requests" / "request.txt"
    path.write_text("Review this reversible local implementation.", encoding="utf-8")
    path.chmod(0o600)
    return path


@pytest.mark.parametrize(
    ("importance", "next_action"),
    [
        ("ordinary", "RECONCILE_CANONICAL_LOCAL"),
        ("gated", "HUMAN_APPROVAL_REQUIRED"),
    ],
)
def test_review_capture_state_authority_and_next_action(
    tmp_path: Path, importance: str, next_action: str
) -> None:
    root = private_root(tmp_path)
    scenario = tmp_path / "scenario.json"
    response = "# Review\n\nUse this only after reconciliation."
    scenario.write_text(
        json.dumps(
            {
                "schema": orchestrator.FAKE_SCHEMA,
                "response": response,
                "transcript": advanced_transcript(),
                "expected_tools": [
                    "browser_navigate",
                    "browser_click",
                    "browser_type",
                    "browser_click",
                    "browser_wait_for",
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code, result = orchestrator.ask(
        private_root=root,
        request_file=private_request(root),
        importance=importance,
        fake_scenario=scenario,
        parent_run_id=None,
        gap_file=None,
    )

    assert exit_code == 0
    assert result["status"] == "REVIEW_CAPTURED"
    assert result["advice_type"] == "PRO_REVIEW_TEXT_V1"
    assert result["authority"] == "UNAPPROVED_REVIEW"
    assert result["next_action"] == next_action
    run_dir, state = orchestrator._load_state(
        root / "chatgpt-pro-runs", result["run_id"]
    )
    assert state["status"] == "REVIEW_CAPTURED"
    assert state["next_action"] == next_action
    event = orchestrator._last_record_event(run_dir)
    assert event["event_type"] == "REVIEW_CAPTURED"
    assert event["payload"]["authority"] == "UNAPPROVED_REVIEW"
    assert event["payload"]["next_action"] == next_action
    proposal = run_dir / "unapproved-proposal.md"
    assert response in proposal.read_text(encoding="utf-8")
    assert stat.S_IMODE(proposal.stat().st_mode) == 0o600


@pytest.mark.parametrize("fenced", [False, True])
def test_structured_and_fenced_advice_keep_convergence_and_raw_hashes(
    tmp_path: Path, fenced: bool
) -> None:
    root = private_root(tmp_path)
    exact = structured_advice()
    response = f"```json\n{exact}\n```" if fenced else exact
    scenario = tmp_path / "structured.json"
    scenario.write_text(
        json.dumps(
            {
                "schema": orchestrator.FAKE_SCHEMA,
                "response": response,
                "transcript": advanced_transcript(),
                "expected_tools": [
                    "browser_navigate",
                    "browser_click",
                    "browser_type",
                    "browser_click",
                    "browser_wait_for",
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code, result = orchestrator.ask(
        private_root=root,
        request_file=private_request(root),
        importance="ordinary",
        fake_scenario=scenario,
        parent_run_id=None,
        gap_file=None,
    )

    assert exit_code == 0
    assert result["status"] == "ADVICE_CAPTURED"
    assert result["advice_type"] == "PRO_ADVICE_V1"
    assert result["next_action"] == "FOLLOW_UP_NAMED_GAP"
    run_dir, state = orchestrator._load_state(
        root / "chatgpt-pro-runs", result["run_id"]
    )
    expected_fingerprint = orchestrator._validate_advice(exact)["response_fingerprint"]
    assert state["response_fingerprints"] == [expected_fingerprint]
    proposal_path = run_dir / "unapproved-proposal.md"
    proposal = proposal_path.read_text(encoding="utf-8")
    assert response in proposal
    final = orchestrator._last_record_event(run_dir)
    assert (
        final["payload"]["response_sha256"]
        == hashlib.sha256(response.encode()).hexdigest()
    )
    assert (
        final["payload"]["proposal_sha256"]
        == hashlib.sha256(proposal_path.read_bytes()).hexdigest()
    )


def create_importable_run(
    root: Path,
    *,
    status: str = "WAITING",
    importance: str = "ordinary",
    submission_attempted: bool = True,
    conversation_url: str | None = "https://chatgpt.com/c/manual-import",
    reason_code: str = "RESPONSE_NOT_IDENTIFIABLE",
    submission_intents: int = 1,
    intent_prompt_sha256: str = "a" * 64,
    intent_model_label: str = "GPT-5.6 Sol",
    intent_effort_label: str = "Pro",
    structural_stop: bool = False,
) -> tuple[str, Path]:
    run_id = "20260810T000000Z-aaaaaaaaaaaa"
    run_dir = root / "chatgpt-pro-runs" / run_id
    run_dir.mkdir(mode=0o700)
    run_dir.chmod(0o700)
    prepared = {
        "run_id": run_id,
        "prompt_sha256": "a" * 64,
    }
    state = orchestrator._new_state(
        prepared,
        mode="LIVE",
        browser="edge",
        importance=importance,
        parent_run_id=None,
        gap_hashes=[],
        response_fingerprints=[],
    )
    state["status"] = status
    state["submission_attempted"] = submission_attempted
    state["conversation_url"] = conversation_url
    for _index in range(submission_intents):
        workflow._append_event(
            run_dir / "run-record.v1.jsonl",
            run_id,
            "SUBMISSION_INTENT_RECORDED",
            {
                "status": "PRE_SEND",
                "origin": workflow.EXACT_ORIGIN,
                "model_label": intent_model_label,
                "effort_label": intent_effort_label,
                "prompt_sha256": intent_prompt_sha256,
            },
        )
    if status in orchestrator.RESUMABLE_STATUSES:
        state["transcript_sha256"] = orchestrator._save_pending_transcript(
            run_dir, {"profile_id": workflow.ADVANCED_PROFILE_ID}
        )
        event_type = "WAIT_INTERRUPTED"
    elif status in {"PRO_UNAVAILABLE_FALLBACK", "BLOCKED_PRO_REQUIRED"}:
        event_type = "PRO_UNAVAILABLE"
    else:
        event_type = "ORCHESTRATION_PREPARED"
    event_payload = {"status": status, "reason_code": reason_code}
    if structural_stop:
        event_payload["stop_classifier"] = orchestrator.STRUCTURAL_STOP_CLASSIFIER
    orchestrator._persist_state(
        run_dir,
        run_dir / "run-record.v1.jsonl",
        state,
        event_type=event_type,
        event_payload=event_payload,
    )
    return run_id, run_dir


def private_response(root: Path, text: str = "Displayed plain-text review.") -> Path:
    path = root / "chatgpt-pro-responses" / "response.txt"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


@pytest.mark.parametrize(
    ("status", "importance", "reason_code"),
    [
        ("WAITING", "ordinary", "OPERATOR_INTERRUPTED"),
        ("PRO_UNAVAILABLE_FALLBACK", "ordinary", "STOP_RATE_LIMIT"),
        ("BLOCKED_PRO_REQUIRED", "gated", "ADVICE_INVALID"),
    ],
)
def test_manual_import_is_hash_bound_and_never_calls_a_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    importance: str,
    reason_code: str,
) -> None:
    root = private_root(tmp_path)
    run_id, run_dir = create_importable_run(
        root,
        status=status,
        importance=importance,
        reason_code=reason_code,
    )
    response = "Displayed plain-text review."

    def unexpected_transport(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("manual import must not construct a transport")

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", unexpected_transport)
    exit_code, result = orchestrator.import_response(
        private_root=root,
        run_id=run_id,
        response_file=private_response(root, response),
    )

    assert exit_code == 0
    assert result["status"] == "REVIEW_CAPTURED"
    assert result["provenance"] == "HUMAN_COPIED_DISPLAYED_RESPONSE"
    assert result["resubmitted"] is False
    assert result["browser_calls"] == 0
    assert "diagnostic_code" not in result
    assert "diagnostic_detail_code" not in result
    assert "diagnostic_context_code" not in result
    assert "diagnostic_context_detail_code" not in result
    assert "diagnostic_context_shape_code" not in result
    assert "diagnostic_fallback_code" not in result
    assert "diagnostic_fallback_entry_code" not in result
    assert result["next_action"] == (
        "HUMAN_APPROVAL_REQUIRED"
        if importance == "gated"
        else "RECONCILE_CANONICAL_LOCAL"
    )
    assert not (run_dir / "pending-transcript.v1.json").exists()
    proposal = (run_dir / "unapproved-proposal.md").read_text(encoding="utf-8")
    assert response in proposal
    assert "HUMAN_COPIED_DISPLAYED_RESPONSE" in proposal
    assert "diagnostic_code" not in proposal
    assert "diagnostic_detail_code" not in proposal
    assert "diagnostic_context_code" not in proposal
    assert "diagnostic_context_detail_code" not in proposal
    assert "diagnostic_context_shape_code" not in proposal
    assert "diagnostic_fallback_code" not in proposal
    assert "diagnostic_fallback_entry_code" not in proposal
    event = orchestrator._last_record_event(run_dir)
    assert event["event_type"] == "MANUAL_RESPONSE_IMPORTED"
    assert (
        event["payload"]["response_sha256"]
        == hashlib.sha256(response.encode()).hexdigest()
    )
    assert event["payload"]["browser_calls"] == 0
    assert event["payload"]["resubmitted"] is False
    state_text = (run_dir / "orchestration-state.v1.json").read_text(encoding="utf-8")
    record_text = (run_dir / "run-record.v1.jsonl").read_text(encoding="utf-8")
    status_result = orchestrator.status(private_root=root, run_id=run_id)
    assert status_result["record_verified"] is True
    assert "diagnostic_code" not in status_result
    assert "diagnostic_code" not in state_text
    assert "diagnostic_code" not in record_text
    assert "diagnostic_detail_code" not in status_result
    assert "diagnostic_detail_code" not in state_text
    assert "diagnostic_detail_code" not in record_text
    assert "diagnostic_context_code" not in status_result
    assert "diagnostic_context_code" not in state_text
    assert "diagnostic_context_code" not in record_text
    assert "diagnostic_context_detail_code" not in status_result
    assert "diagnostic_context_detail_code" not in state_text
    assert "diagnostic_context_detail_code" not in record_text
    assert "diagnostic_context_shape_code" not in status_result
    assert "diagnostic_context_shape_code" not in state_text
    assert "diagnostic_context_shape_code" not in record_text
    assert "diagnostic_fallback_code" not in status_result
    assert "diagnostic_fallback_code" not in state_text
    assert "diagnostic_fallback_code" not in record_text
    assert "diagnostic_fallback_entry_code" not in status_result
    assert "diagnostic_fallback_entry_code" not in state_text
    assert "diagnostic_fallback_entry_code" not in record_text
    with pytest.raises(orchestrator.OrchestrationRefusal) as repeated:
        orchestrator.import_response(
            private_root=root,
            run_id=run_id,
            response_file=root / "chatgpt-pro-responses" / "response.txt",
        )
    assert repeated.value.code == "MANUAL_RESPONSE_ALREADY_IMPORTED"


@pytest.mark.parametrize(
    ("state_overrides", "expected_code"),
    [
        (
            {"status": "SUBMISSION_AMBIGUOUS"},
            "MANUAL_IMPORT_SUBMISSION_AMBIGUOUS",
        ),
        ({"submission_attempted": False}, "MANUAL_IMPORT_PRE_SUBMISSION"),
        ({"conversation_url": None}, "MANUAL_IMPORT_UNBOUND"),
        (
            {
                "status": "PRO_UNAVAILABLE_FALLBACK",
                "reason_code": "STOP_CAPTCHA",
            },
            "MANUAL_IMPORT_REASON_NOT_ALLOWED",
        ),
        (
            {
                "status": "PRO_UNAVAILABLE_FALLBACK",
                "reason_code": "STOP_LOGIN",
            },
            "MANUAL_IMPORT_REASON_NOT_ALLOWED",
        ),
        (
            {
                "status": "PRO_UNAVAILABLE_FALLBACK",
                "reason_code": "STOP_REAUTHENTICATION",
            },
            "MANUAL_IMPORT_REASON_NOT_ALLOWED",
        ),
        (
            {
                "status": "PRO_UNAVAILABLE_FALLBACK",
                "reason_code": "STOP_ACCOUNT_AMBIGUITY",
            },
            "MANUAL_IMPORT_REASON_NOT_ALLOWED",
        ),
    ],
)
def test_manual_import_rejects_unsafe_run_states_without_a_proposal(
    tmp_path: Path,
    state_overrides: dict[str, Any],
    expected_code: str,
) -> None:
    root = private_root(tmp_path)
    run_id, run_dir = create_importable_run(root, **state_overrides)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.import_response(
            private_root=root,
            run_id=run_id,
            response_file=private_response(root),
        )

    assert captured.value.code == expected_code
    assert not (run_dir / "unapproved-proposal.md").exists()


def test_manual_import_rejects_existing_proposal(tmp_path: Path) -> None:
    root = private_root(tmp_path)
    run_id, run_dir = create_importable_run(root)
    proposal = run_dir / "unapproved-proposal.md"
    proposal.write_text("existing", encoding="utf-8")
    proposal.chmod(0o600)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.import_response(
            private_root=root,
            run_id=run_id,
            response_file=private_response(root),
        )

    assert captured.value.code == "MANUAL_IMPORT_PROPOSAL_EXISTS"


@pytest.mark.parametrize(
    (
        "submission_intents",
        "intent_prompt_sha256",
        "intent_model_label",
        "intent_effort_label",
    ),
    [
        (0, "a" * 64, "GPT-5.6 Sol", "Pro"),
        (2, "a" * 64, "GPT-5.6 Sol", "Pro"),
        (1, "b" * 64, "GPT-5.6 Sol", "Pro"),
        (1, "a" * 64, "Instant", "Pro"),
        (1, "a" * 64, "GPT-5.6 Sol", "Standard"),
    ],
)
def test_manual_import_requires_one_matching_submission_intent(
    tmp_path: Path,
    submission_intents: int,
    intent_prompt_sha256: str,
    intent_model_label: str,
    intent_effort_label: str,
) -> None:
    root = private_root(tmp_path)
    run_id, run_dir = create_importable_run(
        root,
        submission_intents=submission_intents,
        intent_prompt_sha256=intent_prompt_sha256,
        intent_model_label=intent_model_label,
        intent_effort_label=intent_effort_label,
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.import_response(
            private_root=root,
            run_id=run_id,
            response_file=private_response(root),
        )

    assert captured.value.code == "MANUAL_IMPORT_SUBMISSION_EVIDENCE_INVALID"
    assert not (run_dir / "unapproved-proposal.md").exists()


def test_manual_import_rejects_current_structural_rate_limit_stop(
    tmp_path: Path,
) -> None:
    root = private_root(tmp_path)
    run_id, run_dir = create_importable_run(
        root,
        status="PRO_UNAVAILABLE_FALLBACK",
        reason_code="STOP_RATE_LIMIT",
        structural_stop=True,
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.import_response(
            private_root=root,
            run_id=run_id,
            response_file=private_response(root),
        )

    assert captured.value.code == "MANUAL_IMPORT_REASON_NOT_ALLOWED"
    assert not (run_dir / "unapproved-proposal.md").exists()


@pytest.mark.parametrize(
    "reason_code",
    [
        "STOP_CAPTCHA",
        "STOP_LOGIN",
        "STOP_REAUTHENTICATION",
        "STOP_ACCOUNT_AMBIGUITY",
        "STOP_RATE_LIMIT",
        "SUBMISSION_AMBIGUOUS",
    ],
)
def test_manual_import_waiting_state_rejects_stop_or_ambiguity_reason(
    tmp_path: Path,
    reason_code: str,
) -> None:
    root = private_root(tmp_path)
    run_id, run_dir = create_importable_run(
        root,
        status="WAITING",
        reason_code=reason_code,
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.import_response(
            private_root=root,
            run_id=run_id,
            response_file=private_response(root),
        )

    assert captured.value.code == "MANUAL_IMPORT_REASON_NOT_ALLOWED"
    assert not (run_dir / "unapproved-proposal.md").exists()


def test_manual_response_symlink_is_rejected(tmp_path: Path) -> None:
    root = private_root(tmp_path)
    target = tmp_path / "outside.txt"
    target.write_text("safe response", encoding="utf-8")
    target.chmod(0o600)
    link = root / "chatgpt-pro-responses" / "response.txt"
    link.symlink_to(target)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._private_response(link, root / "chatgpt-pro-responses")

    assert captured.value.code == "RESPONSE_FILE_SCOPE"


@pytest.mark.parametrize(
    ("location", "mode", "text", "expected_code"),
    [
        ("outside", 0o600, "safe response", "RESPONSE_FILE_SCOPE"),
        ("inside", 0o644, "safe response", "RESPONSE_FILE_MODE"),
        (
            "inside",
            0o600,
            "session_token=abcdefghijklmnop",
            "RESPONSE_SENSITIVE_OR_INVALID",
        ),
        (
            "inside",
            0o600,
            "x" * (workflow.MAX_TEXT_BYTES + 1),
            "RESPONSE_SENSITIVE_OR_INVALID",
        ),
    ],
)
def test_manual_response_file_scope_mode_and_content_are_fail_closed(
    tmp_path: Path,
    location: str,
    mode: int,
    text: str,
    expected_code: str,
) -> None:
    root = private_root(tmp_path)
    path = (
        tmp_path / "outside.txt"
        if location == "outside"
        else root / "chatgpt-pro-responses" / "response.txt"
    )
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._private_response(path, root / "chatgpt-pro-responses")

    assert captured.value.code == expected_code
