"""Deterministic evidence for the approved ST-0101 current response body."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import chatgpt_pro_orchestrator as orchestrator
from scripts import chatgpt_pro_workflow as workflow


ADVANCED_PROFILE_ID = workflow.ADVANCED_PROFILE_ID
LEGACY_PROFILE_ID = "pro-extended-combined-v1"
REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR = (
    "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR"
)
REF_FREE_ENTRY_OUTSIDE_PRESENTATION_WRAPPER = (
    "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_PRESENTATION_WRAPPER"
)
EXPECTED_BOUND_RESPONSE_REF_FREE_FALLBACK_ENTRY_CODES = frozenset(
    {
        REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR,
        REF_FREE_ENTRY_OUTSIDE_PRESENTATION_WRAPPER,
    }
)


def snapshot(*lines: str, url: str = "https://chatgpt.com/c/current-response") -> str:
    return "\n".join((f"- Page URL: {url}", *lines))


def advice_text(*, summary: str = "Use the exact current response anchor.") -> str:
    return json.dumps(
        {
            "schema": "PRO_ADVICE_V1",
            "summary": summary,
            "material_delta": True,
            "open_gaps": ["One named gap remains."],
            "evidence_refs": ["ST-0101 current response fixture"],
            "recommendations": ["Reconcile with canonical evidence."],
            "authority": "UNAPPROVED_ADVICE",
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def advanced_response_snapshot(
    response: str | None = None,
    *,
    ref: str = "e60",
    body_ref: str = "e61",
    wrapper_ref: str = "e62",
    paragraph_ref: str = "e63",
    heading_line: str | None = None,
    extra_lines: tuple[str, ...] = (),
    url: str = "https://chatgpt.com/c/current-response",
) -> str:
    actual_response = advice_text() if response is None else response
    actual_heading = (
        f'- heading "ChatGPT said:" [ref={ref}]'
        if heading_line is None
        else heading_line
    )
    return snapshot(
        actual_heading,
        f"- generic [ref={body_ref}]:",
        f"  - generic [ref={wrapper_ref}]:",
        f"    - paragraph [ref={paragraph_ref}]:",
        f"      - text: {json.dumps(actual_response)}",
        *extra_lines,
        url=url,
    )


def advanced_paragraph_snapshot(
    *paragraph_lines: str,
    extra_lines: tuple[str, ...] = (),
) -> str:
    return snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - generic [ref=e62]:",
        "    - paragraph [ref=e63]:",
        *paragraph_lines,
        *extra_lines,
    )


def advanced_action_group_snapshot(
    *,
    response: str | None = None,
    include_content_before: bool = True,
    group_line: str = '    - group "Response actions":',
    group_descendants: tuple[str, ...] = (),
    after_group: tuple[str, ...] = (),
) -> str:
    actual_response = advice_text() if response is None else response
    split_at = max(1, len(actual_response) // 2)
    content_lines = (
        (
            "    - paragraph [ref=e63]:",
            "      - text: " + json.dumps(actual_response[:split_at]),
            "      - statictext: " + json.dumps(actual_response[split_at:]),
        )
        if include_content_before
        else ()
    )
    return snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - generic [ref=e62]:",
        *content_lines,
        group_line,
        *group_descendants,
        *after_group,
    )


def embedded_pre_content_snapshot(
    *group_descendants: str,
    before_group: tuple[str, ...] = (),
    after_group: tuple[str, ...] = (),
) -> str:
    return snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - generic [ref=e62]:",
        *before_group,
        '    - group "Response actions":',
        *group_descendants,
        *after_group,
    )


def fifteen_fragments(response: str) -> tuple[str, ...]:
    return (
        response[:2],
        *(response[index : index + 1] for index in range(2, 15)),
        response[15:],
    )


def observation(
    state: str,
    *,
    model_label: str | None = None,
    effort_label: str | None = None,
    option_labels: list[str] | None = None,
    refs: dict[str, list[str]] | None = None,
    generating: bool | None = None,
) -> dict[str, Any]:
    return {
        "state": state,
        "url": "https://chatgpt.com/c/current-response",
        "authenticated": True,
        "stop_state": None,
        "model_label": model_label,
        "effort_label": effort_label,
        "option_labels": [] if option_labels is None else option_labels,
        "refs": {} if refs is None else refs,
        "generating": generating,
        "response_complete": False,
    }


def advanced_pending_transcript() -> dict[str, Any]:
    return {
        "schema_version": workflow.SCHEMA_VERSION,
        "profile_id": ADVANCED_PROFILE_ID,
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
        ],
    }


def legacy_pending_transcript() -> dict[str, Any]:
    return {
        "schema_version": workflow.SCHEMA_VERSION,
        "profile_id": LEGACY_PROFILE_ID,
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
        ],
    }


class ResumeTransport:
    """Inert resume transport that records every permitted operation."""

    mode = "LIVE"

    def __init__(self, snapshots: list[str]) -> None:
        self.snapshots = list(snapshots)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, tool: str, arguments: dict[str, Any]) -> str:
        self.calls.append((tool, dict(arguments)))
        if tool == "browser_snapshot":
            if not self.snapshots:
                raise AssertionError("unexpected browser snapshot")
            return self.snapshots.pop(0)
        return ""

    def close(self) -> None:
        self.calls.append(("browser_close", {}))


def configure_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    snapshots: list[str],
) -> tuple[Path, ResumeTransport, dict[str, Any]]:
    private_root = tmp_path / "private"
    secret_root = private_root / "chatgpt-pro"
    secret_root.mkdir(mode=0o700, parents=True)
    private_root.chmod(0o700)
    secret_root.chmod(0o700)
    expanded_snapshots: list[str] = []
    for raw_snapshot in snapshots:
        expanded_snapshots.append(raw_snapshot)
        if orchestrator._has_assistant_marker(
            raw_snapshot
        ) and not orchestrator._has_generating_marker(raw_snapshot):
            expanded_snapshots.extend(
                [raw_snapshot] * (orchestrator.RESPONSE_STABILITY_OBSERVATIONS - 1)
            )
    transport = ResumeTransport(expanded_snapshots)
    finalized: dict[str, Any] = {}

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", private_root)
    monkeypatch.setattr(
        orchestrator,
        "StdioMcpTransport",
        lambda _wrapper, _secret_file, browser: (
            transport if browser == "edge" else pytest.fail("unexpected browser")
        ),
    )

    def finalize_transcript(**arguments: Any) -> tuple[Any, ...]:
        finalized.update(arguments)
        return (
            {"response_sha256": "a" * 64},
            {"authority": "UNAPPROVED_ADVICE"},
            "b" * 64,
            "c" * 64,
        )

    monkeypatch.setattr(orchestrator, "_finalize_transcript", finalize_transcript)
    return private_root, transport, finalized


def resume_capture(
    private_root: Path,
    transcript: dict[str, Any],
) -> tuple[dict[str, str], dict[str, Any], str, str] | None:
    return orchestrator._resume_live_capture(
        prepared={
            "run_id": "20260805T000000Z-aaaaaaaaaaaa",
            "run_dir": str(private_root / "run"),
            "record_path": str(private_root / "run" / "run-record.v1.jsonl"),
            "prompt_sha256": "d" * 64,
        },
        transcript=transcript,
        conversation_url="https://chatgpt.com/c/current-response",
        private_root=private_root,
        browser="edge",
    )


def assert_no_resume_submission(transport: ResumeTransport) -> None:
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


def test_advanced_fragmented_body_reconstructs_only_paragraph_text_in_order() -> None:
    response = advice_text(
        summary="Decode ordered response text without inventing a separator."
    )
    fragments = fifteen_fragments(response)
    body_lines: list[str] = []
    for index, fragment in enumerate(fragments):
        role = "text" if index % 2 == 0 else "statictext"
        body_lines.append(f"      - {role}: {json.dumps(fragment)}")
        if index == 1:
            body_lines.extend(
                (
                    '      - link "source-label-not-response" [ref=e64]:',
                    "        - /url: https://example.invalid/source",
                    '        - generic "citation preview" [ref=e65]:',
                    "          - paragraph [ref=e69]:",
                    "            - text: " + json.dumps('{"schema":"WRONG"}'),
                )
            )
        if index == 4:
            body_lines.extend(
                (
                    '      - citation-preview "preview-not-response" [ref=e66]:',
                    "        - statictext: " + json.dumps('{"authority":"WRONG"}'),
                    '      - button "copy-not-response" [ref=e67]:',
                    "        - text: " + json.dumps('{"summary":"WRONG"}'),
                )
            )
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - generic "content wrapper not response bytes" [ref=e62]:',
        '    - paragraph "paragraph label not response bytes" [ref=e63]:',
        *body_lines,
        '- navigation "assistant sidebar label" [ref=e68]:',
        "  - text: " + json.dumps('{"schema":"OUTSIDE"}'),
    )

    completed = orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
    )

    assert completed == (
        "https://chatgpt.com/c/current-response",
        "e60",
        response,
    )
    assert orchestrator._validate_advice(completed[2])["advice_type"] == (
        "PRO_ADVICE_V1"
    )
    assert len(fragments) == 15
    with pytest.raises(json.JSONDecodeError):
        json.loads("\n".join(fragments))


def test_exact_post_fragment_action_group_is_opaque_and_resume_inspect_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = advice_text(summary="Ignore only the exact post-response action group.")
    ignored_response = advice_text(summary="Action chrome is never response data.")
    raw_snapshot = advanced_action_group_snapshot(
        response=response,
        group_descendants=(
            '      - button "{\\"schema\\":\\"WRONG\\"}" [ref=e64]:',
            "        - text: " + json.dumps(ignored_response),
            '      - group "Response actions":',
            "        - statictext: " + json.dumps(ignored_response),
            '      - link "{\\"authority\\":\\"WRONG\\"}" [ref=e65]:',
            "        - /url: https://example.invalid/{response-like-json}",
            '        - generic "preview action" [ref=e66]:',
            "          - paragraph [ref=e67]:",
            "            - statictext: " + json.dumps(ignored_response),
        ),
    )

    completed = orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
    )
    assert completed == (
        "https://chatgpt.com/c/current-response",
        "e60",
        response,
    )
    assert orchestrator._validate_advice(completed[2])["advice_type"] == (
        "PRO_ADVICE_V1"
    )

    private_root, transport, finalized = configure_resume(
        tmp_path,
        monkeypatch,
        [raw_snapshot],
    )
    result = resume_capture(private_root, advanced_pending_transcript())

    assert result is not None
    assert finalized["response"] == response
    assert transport.calls == [
        (
            "browser_navigate",
            {"url": "https://chatgpt.com/c/current-response"},
        ),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_close", {}),
    ]
    assert_no_resume_submission(transport)


def test_advanced_action_group_is_optional() -> None:
    response = advice_text(summary="Action chrome may be absent.")

    completed = orchestrator._completed_response(
        advanced_response_snapshot(response),
        profile_id=ADVANCED_PROFILE_ID,
    )

    assert completed == (
        "https://chatgpt.com/c/current-response",
        "e60",
        response,
    )


@pytest.mark.parametrize(
    ("with_action_lines", "without_action_lines", "expected_response"),
    [
        pytest.param(
            (
                '  - group "Response actions":',
                '    - button "Copy":',
                '      - text: "ignored"',
                '  - text: "Direct content"',
            ),
            ('  - text: "Direct content"',),
            "Direct content",
            id="direct-content",
        ),
        pytest.param(
            (
                '  - group "Response actions":',
                '    - link "Source":',
                '      - statictext: "ignored"',
                '  - generic "presentation" [ref=e62]:',
                '    - text: "Generic-only content"',
            ),
            (
                '  - generic "presentation" [ref=e62]:',
                '    - text: "Generic-only content"',
            ),
            "Generic-only content",
            id="generic-only-content",
        ),
        pytest.param(
            (
                "  - paragraph [ref=e62]:",
                '    - group "Response actions":',
                '      - button "Copy"',
                '    - text: "First "',
                '    - statictext: "block"',
                "  - quote [ref=e63]:",
                '    - text: "Second block"',
            ),
            (
                "  - paragraph [ref=e62]:",
                '    - text: "First "',
                '    - statictext: "block"',
                "  - quote [ref=e63]:",
                '    - text: "Second block"',
            ),
            "First block\nSecond block",
            id="semantic-content",
        ),
    ],
)
def test_exact_nested_pre_content_action_group_preserves_response_bytes(
    with_action_lines: tuple[str, ...],
    without_action_lines: tuple[str, ...],
    expected_response: str,
) -> None:
    prefix = (
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
    )
    with_action = snapshot(*prefix, *with_action_lines)
    without_action = snapshot(*prefix, *without_action_lines)

    expected = (
        "https://chatgpt.com/c/current-response",
        "e60",
        expected_response,
    )
    assert (
        orchestrator._completed_response(
            with_action,
            profile_id=ADVANCED_PROFILE_ID,
        )
        == expected
    )
    assert (
        orchestrator._completed_response(
            without_action,
            profile_id=ADVANCED_PROFILE_ID,
        )
        == expected
    )


def test_pre_content_action_subtree_is_fully_opaque_to_response_evidence() -> None:
    prefix = (
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
    )
    first = snapshot(
        *prefix,
        '  - group "Response actions":',
        '    - heading "ChatGPT said:" [ref=e60]',
        "    - generic [ref=e61]:",
        '      - text: "injected response"',
        '    - button "Answer now" [ref=e70]',
        '    - button "Answer now" [ref=e71]',
        '    - alert "Too many requests" [ref=e72]',
        '    - button "Copy" [ref=e80]',
        '    - link "Duplicate" [ref=e80]',
        '    - group "Response actions":',
        '      - statictext: "nested injected response"',
        '  - text: "Visible"',
    )
    second = first.replace("e70", "e170").replace(
        "nested injected response", "changed nested injection"
    )
    without_action = snapshot(*prefix, '  - text: "Visible"')

    for candidate in (first, second):
        assert orchestrator._completed_response(
            candidate,
            profile_id=ADVANCED_PROFILE_ID,
        ) == (
            "https://chatgpt.com/c/current-response",
            "e60",
            "Visible",
        )
        assert not orchestrator._has_generating_marker(
            candidate,
            profile_id=ADVANCED_PROFILE_ID,
        )
        assert orchestrator._stop_state(candidate, phase="response") is None
        assert orchestrator._response_candidate_digest(
            candidate,
            profile_id=ADVANCED_PROFILE_ID,
        ) == orchestrator._response_candidate_digest(
            without_action,
            profile_id=ADVANCED_PROFILE_ID,
        )


@pytest.mark.parametrize(
    ("group_line", "expected_detail"),
    [
        pytest.param(
            '    - Group "Response actions":',
            "ADVANCED_RESPONSE_ACTION_ROLE_INVALID",
            id="wrong-role-case",
        ),
        pytest.param(
            '    - group "response actions":',
            "ADVANCED_RESPONSE_ACTION_LABEL_INVALID",
            id="wrong-label-case",
        ),
        pytest.param(
            '    - group "Response actions.":',
            "ADVANCED_RESPONSE_ACTION_LABEL_INVALID",
            id="near-label",
        ),
        pytest.param(
            '    - group "Response actions" [ref=e70]:',
            "ADVANCED_RESPONSE_ACTION_REF_PRESENT",
            id="ref-bearing",
        ),
        pytest.param(
            '    - group "Response actions" [disabled]:',
            "ADVANCED_RESPONSE_ACTION_EXTRA_ATTRIBUTES",
            id="attribute-bearing",
        ),
        pytest.param(
            '    - group "Response actions": unexpected',
            "ADVANCED_RESPONSE_ACTION_LINE_SHAPE_INVALID",
            id="residual-shape",
        ),
    ],
)
def test_malformed_pre_content_action_candidate_remains_refused(
    group_line: str,
    expected_detail: str,
) -> None:
    raw_snapshot = advanced_action_group_snapshot(
        include_content_before=False,
        group_line=group_line,
        after_group=(
            "    - paragraph [ref=e63]:",
            '      - text: "Visible"',
        ),
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == expected_detail


@pytest.mark.parametrize(
    ("raw_snapshot", "expected_context"),
    [
        pytest.param(
            snapshot(
                '- heading "ChatGPT said:" [ref=e60]',
                "- generic [ref=e61]:",
                '- group "Response actions":',
                '  - alert "Too many requests" [ref=e60]',
            ),
            "ADVANCED_RESPONSE_PRECONTENT_SAME_INDENT_BOUNDARY",
            id="same-indent",
        ),
        pytest.param(
            snapshot(
                '- region "response" [ref=e50]:',
                '  - heading "ChatGPT said:" [ref=e60]',
                "  - generic [ref=e61]:",
                '- group "Response actions":',
                '  - dialog "Please log in" [ref=e61]',
            ),
            "ADVANCED_RESPONSE_PRECONTENT_SHALLOW_BOUNDARY",
            id="shallower-indent",
        ),
    ],
)
def test_same_or_shallower_pre_content_action_boundary_remains_refused(
    raw_snapshot: str,
    expected_context: str,
) -> None:
    assert orchestrator._stop_state(raw_snapshot, phase="response") is None
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
    )
    assert captured.value.diagnostic_context_code == expected_context


@pytest.mark.parametrize(
    ("after_group", "expected_context"),
    [
        pytest.param(
            (),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY",
            id="clean-end",
        ),
        pytest.param(
            ('    - text: "   "',),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY",
            id="whitespace-only-payload",
        ),
        pytest.param(
            (
                '    - button "Copy":',
                '      - text: "opaque injection"',
            ),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_ONLY_OPAQUE",
            id="approved-opaque-sibling",
        ),
    ],
)
def test_pre_content_action_requires_later_non_whitespace_content(
    after_group: tuple[str, ...],
    expected_context: str,
) -> None:
    raw_snapshot = advanced_action_group_snapshot(
        include_content_before=False,
        after_group=after_group,
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
    )
    assert captured.value.diagnostic_context_code == expected_context


@pytest.mark.parametrize(
    ("group_descendants", "expected_context"),
    [
        pytest.param(
            (
                "      - generic [ref=e70]:",
                '        - text: "hidden response material"',
            ),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_CONTENT",
            id="valid-content",
        ),
        pytest.param(
            (
                "      - generic [ref=e70]:",
                '        - text: "hidden response material"',
                '      - statictext: "unterminated',
            ),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            id="invalid-wins-over-valid",
        ),
        pytest.param(
            ("      - generic [ref=e70]:",),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            id="bare-generic",
        ),
        pytest.param(
            (
                "      - paragraph [ref=e70]:",
                '        - button "Copy":',
            ),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            id="semantic-with-only-opaque-descendant",
        ),
        pytest.param(
            (
                "      - generic [ref=e70]:",
                '        - text: ""',
            ),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY",
            id="valid-empty-payload",
        ),
        pytest.param(
            (
                "      - generic [ref=e70]:",
                '        - statictext: "   "',
                '      - button "Copy":',
            ),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_ONLY_OPAQUE",
            id="whitespace-with-opaque-chrome",
        ),
        pytest.param(
            (
                "      - generic [ref=e70]:",
                '        - text: "visible"',
                '      - button "Copy":',
            ),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_CONTENT",
            id="valid-content-with-opaque-chrome",
        ),
        pytest.param(
            (
                "      - generic [ref=e70]:",
                '        - text: "\\ud83d\\ude00"',
            ),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_CONTENT",
            id="valid-surrogate-pair",
        ),
        pytest.param(
            (
                "      - generic [ref=e70]:",
                '        - text: "\\ud800"',
            ),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
            id="lone-surrogate",
        ),
    ],
)
def test_pre_content_context_uses_closed_nested_precedence_without_acceptance_change(
    group_descendants: tuple[str, ...],
    expected_context: str,
) -> None:
    raw_snapshot = advanced_action_group_snapshot(
        include_content_before=False,
        group_descendants=group_descendants,
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
    )
    assert captured.value.diagnostic_context_code == expected_context


@pytest.mark.parametrize(
    "bare_scalar_container",
    [
        pytest.param("      - text:", id="text"),
        pytest.param("      - text:   ", id="text-trailing-whitespace"),
        pytest.param("      - statictext:", id="statictext"),
        pytest.param("      - statictext:\t", id="statictext-trailing-whitespace"),
    ],
)
def test_complete_bare_scalar_containers_preserve_predecessor_opaque_context(
    bare_scalar_container: str,
) -> None:
    raw_snapshot = advanced_action_group_snapshot(
        include_content_before=False,
        group_descendants=(bare_scalar_container,),
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
    )
    assert captured.value.diagnostic_context_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_ONLY_OPAQUE"
    )
    assert not hasattr(captured.value, "diagnostic_context_detail_code")


@pytest.mark.parametrize(
    ("group_descendants", "expected_context_detail"),
    [
        pytest.param(
            ('      - Text: "wrong role"',),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID",
            id="scalar-shape-invalid",
        ),
        pytest.param(
            ("      - text: 123",),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_VALUE_INVALID",
            id="scalar-non-string-json",
        ),
        pytest.param(
            ('      - text: "unterminated',),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_VALUE_INVALID",
            id="scalar-malformed-json",
        ),
        pytest.param(
            ('      - text: "\ud800"',),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_VALUE_INVALID",
            id="scalar-invalid-unicode",
        ),
        pytest.param(
            ('      - statictext: "\udc00"',),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_VALUE_INVALID",
            id="scalar-invalid-low-surrogate",
        ),
        pytest.param(
            ("      - generic:",),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            id="container-shape-invalid",
        ),
        pytest.param(
            (
                "      - generic [ref=e70]:",
                '      - text: "valid sibling content"',
            ),
            ("ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_UNSATISFIED_WITH_CONTENT"),
            id="unsatisfied-container-with-content",
        ),
        pytest.param(
            ("      - generic [ref=e70]:",),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_UNSATISFIED_EMPTY",
            id="unsatisfied-container-empty",
        ),
        pytest.param(
            ('      - widget: "unsupported scalar"',),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_MATERIAL_UNSUPPORTED",
            id="unsupported-material",
        ),
        pytest.param(
            (
                '      - Text: "first explicit defect"',
                "      - text: 123",
            ),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID",
            id="first-physical-explicit-defect-wins",
        ),
        pytest.param(
            (
                "      - text: 123",
                '      - Text: "later shape defect"',
            ),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_VALUE_INVALID",
            id="reverse-explicit-order",
        ),
        pytest.param(
            (
                "      - generic [ref=e70]:",
                "      - text: 123",
            ),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_VALUE_INVALID",
            id="later-explicit-defect-beats-deferred-unsatisfied-container",
        ),
        pytest.param(
            (
                "      - generic [ref=e70]:",
                "      - generic:",
            ),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
            id="later-container-shape-beats-deferred-unsatisfied-container",
        ),
        pytest.param(
            (
                "      - generic [ref=e70]:",
                '      - widget: "unsupported scalar"',
            ),
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_MATERIAL_UNSUPPORTED",
            id="later-unsupported-beats-deferred-unsatisfied-container",
        ),
    ],
)
def test_pre_content_nested_invalid_detail_uses_closed_physical_precedence(
    group_descendants: tuple[str, ...],
    expected_context_detail: str,
) -> None:
    raw_snapshot = advanced_action_group_snapshot(
        include_content_before=False,
        group_descendants=group_descendants,
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
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
    assert captured.value.diagnostic_context_detail_code == expected_context_detail


@pytest.mark.parametrize(
    ("container_line", "expected_shape_code"),
    [
        pytest.param(
            "      - generic:",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            id="ref-missing-generic",
        ),
        pytest.param(
            '      - paragraph "label":',
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            id="ref-missing-json-label",
        ),
        pytest.param(
            '      - list "label [ref=bad]" [disabled] [level=2]:\t',
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            id="label-ref-like-is-inert",
        ),
        pytest.param(
            "      - quote [disabled] [level=2]:",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            id="ref-missing-complete-attributes",
        ),
        pytest.param(
            '      - code "escaped \\"label\\"" [disabled]:',
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            id="ref-missing-escaped-json-label",
        ),
        pytest.param(
            "      - generic [reference=e70]:",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            id="non-reserved-reference-attribute",
        ),
        pytest.param(
            "      - generic [ref]:",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID",
            id="ref-invalid-valueless",
        ),
        pytest.param(
            "      - generic [ ref=e70]:",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID",
            id="ref-invalid-space-after-bracket",
        ),
        pytest.param(
            "      - generic [ref=bad]:",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID",
            id="ref-invalid-value",
        ),
        pytest.param(
            "      - generic [REF=e70]:",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID",
            id="ref-invalid-case",
        ),
        pytest.param(
            "      - generic [ref =e70]:",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID",
            id="ref-invalid-space-before-equals",
        ),
        pytest.param(
            "      - generic [ref= e70]:",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID",
            id="ref-invalid-space-after-equals",
        ),
        pytest.param(
            "      - generic [ref=e0]:",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID",
            id="ref-invalid-zero",
        ),
        pytest.param(
            "      - generic [ref=e70",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID",
            id="ref-invalid-unclosed",
        ),
        pytest.param(
            "      - generic ref=e70:",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID",
            id="ref-invalid-unbracketed",
        ),
        pytest.param(
            "      - generic [name=ref=e70]:",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID",
            id="ref-invalid-in-attribute-value",
        ),
        pytest.param(
            "      - generic",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_LINE_SHAPE_INVALID",
            id="line-shape-missing-colon",
        ),
        pytest.param(
            "      - paragraph: trailing",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_LINE_SHAPE_INVALID",
            id="line-shape-residual-text",
        ),
        pytest.param(
            "      - quote [disabled:",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_LINE_SHAPE_INVALID",
            id="line-shape-unclosed-attribute",
        ),
        pytest.param(
            "      - list: [disabled]",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_LINE_SHAPE_INVALID",
            id="line-shape-attribute-after-colon",
        ),
        pytest.param(
            '      - code "unterminated:',
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_LINE_SHAPE_INVALID",
            id="line-shape-malformed-label",
        ),
    ],
)
def test_pre_content_container_shape_diagnostic_is_closed_and_source_derived(
    container_line: str,
    expected_shape_code: str,
) -> None:
    raw_snapshot = advanced_action_group_snapshot(
        include_content_before=False,
        group_descendants=(container_line,),
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
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
    assert captured.value.diagnostic_context_shape_code == expected_shape_code


@pytest.mark.parametrize(
    "container_line",
    [
        pytest.param(
            '      - paragraph "label [ref=e70]":',
            id="valid-ref-only-inside-label",
        ),
        pytest.param(
            "      - generic [ref=e70] [REF=e71]:",
            id="predecessor-valid-ref-plus-malformed-extra",
        ),
        pytest.param(
            "      - generic [ref=e70] [ref=e71]:",
            id="predecessor-valid-ref-plus-duplicate-extra",
        ),
    ],
)
def test_pre_content_container_shape_preserves_predecessor_selected_controls(
    container_line: str,
) -> None:
    raw_snapshot = advanced_action_group_snapshot(
        include_content_before=False,
        group_descendants=(container_line,),
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_context_detail_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_UNSATISFIED_EMPTY"
    )
    assert not hasattr(captured.value, "diagnostic_context_shape_code")


@pytest.mark.parametrize(
    ("first_line", "second_line", "expected_shape_code"),
    [
        pytest.param(
            "      - generic:",
            "      - generic [ref=bad]:",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
            id="first-missing-before-invalid",
        ),
        pytest.param(
            "      - generic [ref=bad]:",
            "      - generic",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID",
            id="first-invalid-before-residual",
        ),
        pytest.param(
            "      - generic",
            "      - generic:",
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_LINE_SHAPE_INVALID",
            id="first-residual-before-missing",
        ),
    ],
)
def test_pre_content_container_shape_uses_first_selected_physical_defect(
    first_line: str,
    second_line: str,
    expected_shape_code: str,
) -> None:
    raw_snapshot = advanced_action_group_snapshot(
        include_content_before=False,
        group_descendants=(first_line, second_line),
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_context_shape_code == expected_shape_code


def test_pre_content_container_shape_never_reads_beyond_owned_boundary() -> None:
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - group "Response actions":',
        '- navigation "page navigation" [ref=e90]:',
        "  - generic [ref=bad]:",
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_context_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY"
    )
    assert not hasattr(captured.value, "diagnostic_context_detail_code")
    assert not hasattr(captured.value, "diagnostic_context_shape_code")


@pytest.mark.parametrize(
    "opaque_descendants",
    [
        pytest.param(
            (
                '      - button "Copy":',
                "        - text: 123",
            ),
            id="known-opaque",
        ),
        pytest.param(
            (
                '      - heading "You said:" [ref=e80]:',
                "        - text: 123",
            ),
            id="untrusted-region",
        ),
        pytest.param(
            (
                '      - widget "opaque chrome":',
                "        - text: 123",
            ),
            id="unknown-opaque",
        ),
    ],
)
def test_pre_content_nested_invalid_detail_ignores_opaque_and_untrusted_defects(
    opaque_descendants: tuple[str, ...],
) -> None:
    raw_snapshot = advanced_action_group_snapshot(
        include_content_before=False,
        group_descendants=(
            *opaque_descendants,
            "      - generic [ref=e70]:",
        ),
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_context_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
    )
    assert captured.value.diagnostic_context_detail_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_UNSATISFIED_EMPTY"
    )


def test_pre_content_context_reads_no_action_descendant_as_parser_evidence() -> None:
    first = advanced_action_group_snapshot(
        include_content_before=False,
        group_descendants=(
            '      - heading "ChatGPT said:" [ref=e60]',
            "      - generic [ref=e61]:",
            '        - text: "hidden response material"',
            '      - button "Answer now" [ref=e70]',
            '      - button "Answer now" [ref=e71]',
            '      - button "Stop generating" [ref=e72]',
            '      - alert "Too many requests" [ref=e73]',
            '      - link "Duplicate" [ref=e80]',
            '      - button "Same ref" [ref=e80]',
        ),
    )
    changed = first.replace("hidden response material", "changed injection").replace(
        "e70", "e170"
    )

    assert orchestrator._stop_state(first, phase="response") is None
    assert not orchestrator._has_generating_marker(
        first,
        profile_id=ADVANCED_PROFILE_ID,
    )
    assert orchestrator._response_candidate_digest(
        first,
        profile_id=ADVANCED_PROFILE_ID,
    ) == orchestrator._response_candidate_digest(
        changed,
        profile_id=ADVANCED_PROFILE_ID,
    )
    for raw_snapshot in (first, changed):
        with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
            orchestrator._completed_response(
                raw_snapshot,
                profile_id=ADVANCED_PROFILE_ID,
            )
        assert captured.value.diagnostic_detail_code == (
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
        )
        assert captured.value.diagnostic_context_code == (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID"
        )
        assert captured.value.diagnostic_context_detail_code == (
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_MATERIAL_UNSUPPORTED"
        )


def test_pre_content_context_stops_at_existing_owned_body_boundary() -> None:
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - group "Response actions":',
        '- navigation "page navigation" [ref=e90]:',
        "  - paragraph [ref=e91]:",
        '    - text: "OUTSIDE"',
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
    )
    assert captured.value.diagnostic_context_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY"
    )
    assert not hasattr(captured.value, "diagnostic_context_detail_code")


def test_pre_content_action_does_not_expand_the_owned_body_boundary() -> None:
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - group "Response actions":',
        '    - text: "opaque"',
        '  - text: "Visible"',
        "- paragraph [ref=e90]:",
        '  - text: "OUTSIDE"',
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == "ADVANCED_RESPONSE_BOUNDARY_CONFLICT"
    assert not hasattr(captured.value, "diagnostic_detail_code")


@pytest.mark.parametrize(
    ("boundary", "expected_diagnostic"),
    [
        pytest.param(
            ('- widget "empty page chrome":',),
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            id="empty-unknown-chrome",
        ),
        pytest.param(
            (
                '- widget "opaque page chrome":',
                '  - button "Page control":',
                '    - text: "opaque"',
            ),
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            id="fully-opaque-unknown-chrome",
        ),
        pytest.param(
            (
                '- widget "opaque page chrome":',
                '  - group "Response actions":',
                '    - text: "opaque action payload"',
            ),
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            id="action-like-group-inside-unknown-chrome",
        ),
        pytest.param(
            ('- widget "outside response":', '  - text: "OUTSIDE"'),
            "ADVANCED_RESPONSE_BOUNDARY_CONFLICT",
            id="unknown-with-text",
        ),
        pytest.param(
            ('- widget "outside response":', "  - generic [ref=e90]:"),
            "ADVANCED_RESPONSE_BOUNDARY_CONFLICT",
            id="unknown-with-generic-root",
        ),
    ],
)
def test_pre_content_action_distinguishes_unknown_page_chrome_from_boundary_escape(
    boundary: tuple[str, ...],
    expected_diagnostic: str,
) -> None:
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - group "Response actions":',
        *boundary,
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == expected_diagnostic
    if expected_diagnostic == "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID":
        assert captured.value.diagnostic_detail_code == (
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT"
        )
    else:
        assert not hasattr(captured.value, "diagnostic_detail_code")


@pytest.mark.parametrize(
    "raw_snapshot",
    [
        pytest.param(
            advanced_action_group_snapshot(
                group_line='      - group "Response actions":'
            ),
            id="inside-semantic-paragraph",
        ),
        pytest.param(
            advanced_action_group_snapshot(group_line='  - group "Response actions":'),
            id="inside-body-root",
        ),
        pytest.param(
            advanced_action_group_snapshot(group_line='- group "Response actions":'),
            id="same-indent-boundary",
        ),
        pytest.param(
            snapshot(
                '- heading "ChatGPT said:" [ref=e60]',
                "- generic [ref=e61]:",
                "  - generic [ref=e62]:",
                "    - paragraph [ref=e63]:",
                "      - text: " + json.dumps(advice_text()),
                '    - link "actions" [ref=e64]:',
                '      - group "Response actions":',
            ),
            id="inside-opaque-link",
        ),
    ],
)
def test_exact_action_group_placements_are_opaque(raw_snapshot: str) -> None:
    assert orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
    ) == (
        "https://chatgpt.com/c/current-response",
        "e60",
        advice_text(),
    )


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
            ('- statictext: "OUTSIDE"',),
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_CONTENT_AFTER",
            id="direct-statictext",
        ),
        pytest.param(
            ("- paragraph [ref=e90]:", '  - text: "OUTSIDE"'),
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_CONTENT_AFTER",
            id="semantic-paragraph",
        ),
        pytest.param(
            ("- list [ref=e90]:", "  - listitem [ref=e91]:", '    - text: "OUTSIDE"'),
            "RESPONSE_NOT_IDENTIFIABLE",
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
            "ADVANCED_RESPONSE_ACTION_CONTENT_AFTER",
            id="semantic-list",
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
def test_post_boundary_action_never_truncates_later_response_content(
    continuation: tuple[str, ...],
    reason_code: str,
    diagnostic_code: str,
    detail_code: str | None,
) -> None:
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - text: "Before"',
        '- group "Response actions":',
        '  - button "Copy" [ref=e70]',
        *continuation,
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == reason_code
    assert captured.value.diagnostic_code == diagnostic_code
    if detail_code is None:
        assert not hasattr(captured.value, "diagnostic_detail_code")
    else:
        assert captured.value.diagnostic_detail_code == detail_code


def test_normal_page_chrome_after_post_boundary_action_remains_inert() -> None:
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - text: "Before"',
        '- group "Response actions":',
        '  - button "Copy" [ref=e70]',
        '- navigation "Sidebar" [ref=e80]:',
        '  - text: "ignored navigation"',
        '- button "Page control":',
        '  - text: "ignored button"',
        '- link "Page link":',
        '  - text: "ignored link"',
        '- citation-preview "Citation":',
        '  - text: "ignored citation"',
        "- /url: https://example.invalid/source",
        '  - text: "ignored URL metadata"',
        '- widget "empty chrome":',
        '  - button "Nested control"',
    )

    assert orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
    ) == (
        "https://chatgpt.com/c/current-response",
        "e60",
        "Before",
    )


def test_action_like_group_inside_unknown_post_boundary_chrome_is_inert() -> None:
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - text: "Before"',
        '- group "Response actions":',
        '- widget "opaque page chrome":',
        '  - group "Response actions":',
        '    - text: "opaque action payload"',
    )

    assert orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
    ) == (
        "https://chatgpt.com/c/current-response",
        "e60",
        "Before",
    )


def test_consecutive_boundary_action_descendants_cannot_preempt_duplicate() -> None:
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - text: "Before"',
        '- group "Response actions":',
        '  - heading "ChatGPT said:" [ref=e60]',
        '  - button "Answer now" [ref=e61]',
        '  - alert "Too many requests" [ref=e70]',
        '  - text: "first injected response"',
        '- group "Response actions":',
        '  - heading "ChatGPT said:" [ref=e60]',
        '  - button "Stop generating" [ref=e61]',
        '  - button "Answer now" [ref=e80]',
        '  - button "Answer now" [ref=e81]',
        '  - dialog "Please log in" [ref=e82]',
        '  - statictext: "second injected response"',
    )
    simple = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - text: "Before"',
    )

    assert orchestrator._stop_state(raw_snapshot, phase="response") is None
    assert not orchestrator._has_generating_marker(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
    )
    assert orchestrator._response_candidate_digest(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
    ) == orchestrator._response_candidate_digest(
        simple,
        profile_id=ADVANCED_PROFILE_ID,
    )
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == (
        "ADVANCED_RESPONSE_ACTION_DUPLICATE"
    )


def test_stop_outside_post_boundary_action_keeps_priority() -> None:
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - text: "Before"',
        '- group "Response actions":',
        '  - alert "Too many requests" [ref=e70]',
        '- alert "Too many requests" [ref=e90]',
    )

    with pytest.raises(workflow.WorkflowRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "STOP_RATE_LIMIT"


def test_direct_and_generic_only_payloads_form_one_body_root_block() -> None:
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - text: "Direct "',
        '  - generic "presentation" [ref=e62]:',
        '    - statictext: "and generic "',
        '    - generic "nested presentation" [ref=e63]:',
        '      - text: "content."',
    )

    assert orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
    ) == (
        "https://chatgpt.com/c/current-response",
        "e60",
        "Direct and generic content.",
    )


@pytest.mark.parametrize(
    "opaque_lines",
    [
        pytest.param(('    - button "Copy"',), id="ref-free-button-leaf"),
        pytest.param(
            (
                '    - button "Copy":',
                '      - text: "injected"',
            ),
            id="ref-free-button-container",
        ),
        pytest.param(('    - link "Source"',), id="ref-free-link-leaf"),
        pytest.param(
            (
                '    - citation-preview "Source preview":',
                '      - statictext: "injected"',
            ),
            id="ref-free-citation-container",
        ),
        pytest.param(
            (
                "    - /url: https://example.invalid/source",
                '      - text: "injected"',
            ),
            id="direct-url-metadata-subtree",
        ),
        pytest.param(
            (
                '    - status "unknown chrome":',
                '      - text: "injected"',
            ),
            id="unknown-structural-container",
        ),
        pytest.param(
            (
                '    - button "ChatGPT said:":',
                '      - button "Stop generating"',
                '      - text: "injected"',
            ),
            id="response-and-generating-labels-inside-opaque-chrome",
        ),
        pytest.param(
            (
                '    - button "Copy":',
                '      - heading "ChatGPT said:" [ref=e70]',
                "      - generic [ref=e71]:",
                '        - text: "injected"',
            ),
            id="exact-response-anchor-inside-known-opaque-container",
        ),
        pytest.param(
            (
                '    - status "unknown chrome":',
                '      - heading "ChatGPT said:" [ref=e70]',
                "      - generic [ref=e71]:",
                '        - text: "injected"',
            ),
            id="exact-response-anchor-inside-unknown-opaque-container",
        ),
        pytest.param(
            ('    - button "Copy [ref=e60]"',),
            id="ref-literal-inside-opaque-label",
        ),
        pytest.param(
            (
                '    - button "{\\"schema\\":\\"WRONG\\"}" [ref=e70]:',
                '      - text: "injected"',
            ),
            id="escaped-label-button",
        ),
        pytest.param(
            (
                '    - link "{\\"schema\\":\\"WRONG\\"}" [ref=e70]:',
                '      - text: "injected"',
            ),
            id="escaped-label-link",
        ),
        pytest.param(
            (
                '    - citation-preview "{\\"schema\\":\\"WRONG\\"}" [ref=e70]:',
                '      - text: "injected"',
            ),
            id="escaped-label-citation",
        ),
        pytest.param(
            (
                '    - url "{\\"schema\\":\\"WRONG\\"}" [ref=e70]:',
                '      - text: "injected"',
            ),
            id="escaped-label-url",
        ),
        pytest.param(
            (
                '    - widget "{\\"state\\":\\"ready\\"}":',
                '      - text: "injected"',
            ),
            id="escaped-label-unknown-container",
        ),
        pytest.param(
            (
                '    - button "Copy" [disabled] [ref=e70]:',
                '      - text: "injected"',
            ),
            id="disabled-state-before-ref",
        ),
        pytest.param(
            (
                '    - button "Vote" [pressed=false] [ref=e70]:',
                '      - text: "injected"',
            ),
            id="pressed-state-before-ref",
        ),
        pytest.param(
            (
                '    - link "Source" [ref=e70] [current=page]:',
                '      - text: "injected"',
            ),
            id="current-state-after-ref",
        ),
    ],
)
def test_ref_free_and_unknown_opaque_subtrees_cannot_inject_or_veto(
    opaque_lines: tuple[str, ...],
) -> None:
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - paragraph [ref=e62]:",
        '    - text: "Visible"',
        *opaque_lines,
    )

    assert orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
    ) == (
        "https://chatgpt.com/c/current-response",
        "e60",
        "Visible",
    )


def test_opaque_chrome_changes_do_not_change_response_stability_digest() -> None:
    first = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - paragraph [ref=e62]:",
        '    - text: "Visible"',
        '    - button "Copy first":',
        '      - text: "first injected value"',
    )
    second = first.replace("Copy first", "Copy second").replace(
        "first injected value", "second injected value"
    )

    assert orchestrator._response_candidate_digest(
        first, profile_id=ADVANCED_PROFILE_ID
    ) == orchestrator._response_candidate_digest(second, profile_id=ADVANCED_PROFILE_ID)


def test_ref_literal_in_response_text_remains_part_of_stability_identity() -> None:
    first = advanced_paragraph_snapshot('      - text: "Visible [ref=e70]"')
    second = advanced_paragraph_snapshot('      - text: "Visible [ref=e71]"')

    assert orchestrator._response_candidate_digest(
        first, profile_id=ADVANCED_PROFILE_ID
    ) != orchestrator._response_candidate_digest(second, profile_id=ADVANCED_PROFILE_ID)


@pytest.mark.parametrize(
    ("group_line", "expected_detail"),
    [
        pytest.param(
            '- Group "Response actions":',
            "ADVANCED_RESPONSE_ACTION_ROLE_INVALID",
            id="role-invalid",
        ),
        pytest.param(
            '- group "response actions":',
            "ADVANCED_RESPONSE_ACTION_LABEL_INVALID",
            id="label-invalid",
        ),
        pytest.param(
            '- group "Response actions" [ref=e64]:',
            "ADVANCED_RESPONSE_ACTION_REF_PRESENT",
            id="ref-present",
        ),
        pytest.param(
            '- group "Response actions" [disabled] [busy=true]:',
            "ADVANCED_RESPONSE_ACTION_EXTRA_ATTRIBUTES",
            id="complete-extra-attributes",
        ),
        pytest.param(
            '- group "Response actions": [disabled]',
            "ADVANCED_RESPONSE_ACTION_LINE_SHAPE_INVALID",
            id="after-colon-attribute-is-residual-shape",
        ),
    ],
)
def test_action_group_syntax_details_are_local_and_closed(
    group_line: str,
    expected_detail: str,
) -> None:
    raw_snapshot = advanced_action_group_snapshot(group_line="    " + group_line)

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == expected_detail


@pytest.mark.parametrize(
    ("bad_snapshot", "expected_detail"),
    [
        pytest.param(
            advanced_action_group_snapshot(
                include_content_before=False,
            ),
            "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
            id="pre-content-without-later-content",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                after_group=('    - group "Response actions":',)
            ),
            "ADVANCED_RESPONSE_ACTION_DUPLICATE",
            id="duplicate",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                after_group=(
                    "    - paragraph [ref=e64]:",
                    '      - text: "later response fragment"',
                )
            ),
            "ADVANCED_RESPONSE_ACTION_CONTENT_AFTER",
            id="content-after",
        ),
    ],
)
def test_action_group_lifecycle_details_follow_current_first_failure(
    bad_snapshot: str,
    expected_detail: str,
) -> None:
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            bad_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == expected_detail


def test_action_group_syntax_precedes_current_lifecycle_state() -> None:
    wrong_role_before_content = advanced_action_group_snapshot(
        include_content_before=False,
        group_line='    - Group "Response actions":',
        after_group=(
            "    - paragraph [ref=e63]:",
            "      - text: " + json.dumps(advice_text()),
        ),
    )
    malformed_duplicate = advanced_action_group_snapshot(
        after_group=('    - group "response actions":',)
    )
    content_then_unobserved_duplicate = advanced_action_group_snapshot(
        after_group=(
            "    - paragraph [ref=e64]:",
            '      - text: "first decisive content"',
            '    - group "Response actions":',
        )
    )

    expected = (
        (
            wrong_role_before_content,
            "ADVANCED_RESPONSE_ACTION_ROLE_INVALID",
        ),
        (malformed_duplicate, "ADVANCED_RESPONSE_ACTION_LABEL_INVALID"),
        (
            content_then_unobserved_duplicate,
            "ADVANCED_RESPONSE_ACTION_CONTENT_AFTER",
        ),
    )
    for raw_snapshot, detail_code in expected:
        with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
            orchestrator._completed_response(
                raw_snapshot,
                profile_id=ADVANCED_PROFILE_ID,
            )
        assert captured.value.diagnostic_detail_code == detail_code


@pytest.mark.parametrize(
    ("raw_snapshot", "expected_detail"),
    [
        pytest.param(
            advanced_action_group_snapshot(
                include_content_before=False,
                after_group=('    - group "Response actions":',),
            ),
            "ADVANCED_RESPONSE_ACTION_DUPLICATE",
            id="pre-plus-pre",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                include_content_before=False,
                after_group=(
                    "    - paragraph [ref=e63]:",
                    '      - text: "Visible"',
                    '    - group "Response actions":',
                ),
            ),
            "ADVANCED_RESPONSE_ACTION_DUPLICATE",
            id="pre-plus-post",
        ),
    ],
)
def test_only_one_independently_visible_action_group_is_allowed(
    raw_snapshot: str,
    expected_detail: str,
) -> None:
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.diagnostic_detail_code == expected_detail


@pytest.mark.parametrize(
    ("bad_snapshot", "expected_detail"),
    [
        pytest.param(
            advanced_action_group_snapshot(
                include_content_before=False,
                after_group=("- paragraph [ref=e90]:",),
            ),
            None,
            id="pre-content-before-later-paragraph-boundary",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                after_group=(
                    "    - paragraph [ref=e64]:",
                    '      - text: "first decisive content"',
                    "- paragraph [ref=e90]:",
                )
            ),
            "ADVANCED_RESPONSE_ACTION_CONTENT_AFTER",
            id="content-after-before-later-paragraph-boundary",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                after_group=(
                    '    - group "Response actions":',
                    "- generic [ref=e90]:",
                )
            ),
            "ADVANCED_RESPONSE_ACTION_DUPLICATE",
            id="duplicate-before-later-generic-boundary",
        ),
    ],
)
def test_action_lifecycle_failure_precedes_later_non_action_boundary(
    bad_snapshot: str,
    expected_detail: str | None,
) -> None:
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            bad_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    if expected_detail is None:
        assert captured.value.diagnostic_code == "ADVANCED_RESPONSE_BOUNDARY_CONFLICT"
        assert not hasattr(captured.value, "diagnostic_detail_code")
    else:
        assert captured.value.diagnostic_code == (
            "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
        )
        assert captured.value.diagnostic_detail_code == expected_detail


def test_malformed_action_like_line_in_opaque_subtree_remains_inert() -> None:
    response = advice_text(summary="Opaque action-like descendants remain inert.")
    raw_snapshot = advanced_response_snapshot(
        response,
        extra_lines=(
            '    - link "chrome" [ref=e70]:',
            '      - Group "Response actions" [ref=e71]:',
            '        - text: "ignored"',
        ),
    )

    assert orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
    ) == (
        "https://chatgpt.com/c/current-response",
        "e60",
        response,
    )


def test_untrusted_action_like_parent_refusal_omits_detail() -> None:
    raw_snapshot = advanced_response_snapshot(
        "Visible",
        extra_lines=(
            '    - heading "You said:" [ref=e70]:',
            '      - Group "Response actions":',
        ),
    )

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert not hasattr(captured.value, "diagnostic_detail_code")


@pytest.mark.parametrize(
    "bad_snapshot",
    [
        pytest.param(
            advanced_action_group_snapshot(response=" "),
            id="whitespace-only-before-group",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                after_group=(
                    "    - paragraph [ref=e64]:",
                    "      - text: " + json.dumps("later response fragment"),
                )
            ),
            id="text-fragment-after-group",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                after_group=(
                    "    - paragraph [ref=e64]:",
                    "      - statictext: " + json.dumps("later response fragment"),
                )
            ),
            id="statictext-fragment-after-group",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                after_group=('    - group "Response actions":',)
            ),
            id="duplicate-action-group",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                after_group=('    - group "Your response actions":',)
            ),
            id="near-match-after-action-group",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                group_line='    - group "Your message actions":'
            ),
            id="user-message-region-label",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                group_line='    - group "response actions":'
            ),
            id="wrong-label-case",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                group_line='    - Group "Response actions":'
            ),
            id="wrong-role-case",
        ),
        pytest.param(
            advanced_action_group_snapshot(group_line='    - group "Response actions"'),
            id="missing-container-colon",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                group_line='    - group "Response actions.":'
            ),
            id="wrong-punctuation",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                group_line='    -  group "Response actions":'
            ),
            id="extra-role-whitespace",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                group_line='    - group " Response actions ":'
            ),
            id="label-whitespace",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                group_line='    - group "Response actions": '
            ),
            id="trailing-whitespace",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                group_line='    - group "Response actions" [disabled]:'
            ),
            id="attribute-bearing-group",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                group_line='    - group "Response actions": unexpected'
            ),
            id="scalar-bearing-group",
        ),
        pytest.param(
            advanced_action_group_snapshot(
                group_line='    - group "Response actions" [ref=e64]:'
            ),
            id="ref-bearing-group",
        ),
    ],
)
def test_action_group_drift_refuses_without_finalization_or_resubmission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_snapshot: str,
) -> None:
    private_root, transport, finalized = configure_resume(
        tmp_path,
        monkeypatch,
        [bad_snapshot],
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        resume_capture(private_root, advanced_pending_transcript())

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert finalized == {}
    assert not any(path.is_file() for path in private_root.rglob("*"))
    assert_no_resume_submission(transport)


@pytest.mark.parametrize(
    "bad_snapshot",
    [
        pytest.param(
            snapshot('- heading "ChatGPT said:" [ref=e60]'),
            id="missing-body",
        ),
        pytest.param(
            snapshot(
                '- heading "ChatGPT said:" [ref=e60]',
                "- generic [ref=e61]:",
                "  - generic [ref=e62]:",
                "    - paragraph [ref=e63]:",
                f"      - text: {json.dumps(advice_text())}",
                "- generic [ref=e64]:",
            ),
            id="duplicate-body-candidate",
        ),
        pytest.param(
            snapshot(
                '- heading "ChatGPT said:" [ref=e60]',
                "- paragraph [ref=e61]:",
                f"  - text: {json.dumps(advice_text())}",
            ),
            id="wrong-body-role",
        ),
        pytest.param(
            snapshot(
                '- heading "ChatGPT said:" [ref=e60]',
                '- generic "labelled body" [ref=e61]:',
                "  - paragraph [ref=e62]:",
                f"    - text: {json.dumps(advice_text())}",
            ),
            id="labelled-body-root",
        ),
        pytest.param(
            snapshot(
                '- heading "ChatGPT said:" [ref=e60]',
                "- generic [ref=e61]",
                "  - paragraph [ref=e62]:",
                f"    - text: {json.dumps(advice_text())}",
            ),
            id="body-root-without-container-colon",
        ),
        pytest.param(
            snapshot(
                '- heading "ChatGPT said:" [ref=e60]',
                "- response metadata without an element ref",
                "- generic [ref=e61]:",
                "  - paragraph [ref=e62]:",
                f"    - text: {json.dumps(advice_text())}",
            ),
            id="intervening-nonempty-line",
        ),
        pytest.param(
            snapshot(
                '- heading "ChatGPT said:" [ref=e60]',
                "  - generic [ref=e61]:",
                "    - paragraph [ref=e62]:",
                f"      - text: {json.dumps(advice_text())}",
            ),
            id="wrong-body-indent",
        ),
        pytest.param(
            snapshot(
                '- heading "ChatGPT said:" [ref=e60]',
                '- button "copy" [ref=e61]',
                "- generic [ref=e62]:",
                "  - paragraph [ref=e63]:",
                f"    - text: {json.dumps(advice_text())}",
            ),
            id="body-not-immediately-following-element",
        ),
        pytest.param(
            snapshot(
                '- heading "ChatGPT said:" [ref=e60]',
                "- generic [ref=e60]:",
                "  - paragraph [ref=e61]:",
                f"    - text: {json.dumps(advice_text())}",
            ),
            id="heading-body-ref-collision",
        ),
        pytest.param(
            advanced_response_snapshot(extra_lines=('    - button "Copy" [ref=e60]',)),
            id="opaque-descendant-heading-ref-collision",
        ),
        pytest.param(
            advanced_response_snapshot(extra_lines=('    - link "Source" [ref=e61]',)),
            id="opaque-descendant-body-ref-collision",
        ),
    ],
)
def test_advanced_body_root_ambiguity_refuses_before_resume_finalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_snapshot: str,
) -> None:
    private_root, transport, finalized = configure_resume(
        tmp_path,
        monkeypatch,
        [bad_snapshot],
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        resume_capture(private_root, advanced_pending_transcript())

    assert captured.value.code == "RESPONSE_SELECTOR_AMBIGUITY"
    assert finalized == {}
    assert_no_resume_submission(transport)


@pytest.mark.parametrize(
    "bad_snapshot",
    [
        pytest.param(
            advanced_paragraph_snapshot("      - text: unquoted"),
            id="unquoted-fragment",
        ),
        pytest.param(
            advanced_paragraph_snapshot('      - text: "unterminated'),
            id="malformed-json-string-fragment",
        ),
        pytest.param(
            advanced_paragraph_snapshot(r'      - text: "bad\qescape"'),
            id="bad-json-string-escape",
        ),
        pytest.param(
            advanced_paragraph_snapshot("      - statictext: 42"),
            id="non-string-json-fragment",
        ),
        pytest.param(
            advanced_paragraph_snapshot('      - text: "first" "second"'),
            id="two-json-string-literals",
        ),
        pytest.param(
            advanced_paragraph_snapshot("      - text " + json.dumps(advice_text())),
            id="missing-payload-colon",
        ),
        pytest.param(
            advanced_paragraph_snapshot("      - Text: " + json.dumps(advice_text())),
            id="wrong-case-payload-role",
        ),
        pytest.param(
            advanced_paragraph_snapshot(
                '      - StaticText: "ignored"',
                "      - text: " + json.dumps(advice_text()),
            ),
            id="wrong-case-payload-role-with-valid-sibling",
        ),
        pytest.param(
            advanced_paragraph_snapshot(
                '      - button "Copy" [ref=invalid]:',
                "      - text: " + json.dumps(advice_text()),
            ),
            id="malformed-opaque-ref",
        ),
        pytest.param(
            advanced_paragraph_snapshot(
                '      - button "Copy" [ref=e70] [ref=e71]:',
                "      - text: " + json.dumps(advice_text()),
            ),
            id="multiple-opaque-refs",
        ),
        pytest.param(
            advanced_paragraph_snapshot(
                r'      - button "bad\qescape":',
                "      - text: " + json.dumps(advice_text()),
            ),
            id="malformed-opaque-label-escape",
        ),
        pytest.param(
            advanced_paragraph_snapshot(
                '      - widget: "arbitrary scalar"',
                "      - text: " + json.dumps(advice_text()),
            ),
            id="unknown-scalar-role",
        ),
        pytest.param(
            advanced_paragraph_snapshot(
                '      - textual: "arbitrary scalar"',
                "      - text: " + json.dumps(advice_text()),
            ),
            id="near-text-scalar-role",
        ),
        pytest.param(
            advanced_paragraph_snapshot(
                "      - /url:",
                "      - text: " + json.dumps(advice_text()),
            ),
            id="empty-url-metadata",
        ),
        pytest.param(
            advanced_paragraph_snapshot(
                '      - link "source" [ref=e64]:',
                "        - /url: https://example.invalid/source",
                '        - generic "citation preview" [ref=e65]:',
                "          - text: " + json.dumps(advice_text()),
            ),
            id="zero-paragraph-text-fragments",
        ),
        pytest.param(
            advanced_paragraph_snapshot(
                '      - button "Copy":',
                '        - text: "injected only"',
            ),
            id="ref-free-opaque-only-content",
        ),
        pytest.param(
            advanced_paragraph_snapshot('      - text: ""'),
            id="empty-only-fragment",
        ),
    ],
)
def test_advanced_body_content_refuses_before_resume_finalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_snapshot: str,
) -> None:
    private_root, transport, finalized = configure_resume(
        tmp_path,
        monkeypatch,
        [bad_snapshot],
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        resume_capture(private_root, advanced_pending_transcript())

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert finalized == {}
    assert_no_resume_submission(transport)


def test_plain_review_boundary_escape_refuses_instead_of_truncating() -> None:
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - paragraph [ref=e62]:",
        '    - text: "Visible"',
        "- paragraph [ref=e63]:",
        '  - text: "OUTSIDE"',
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"


def test_sensitive_fragment_refuses_before_resume_finalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sensitive_response = advice_text(
        summary="session_token=abcdefghijklmnop remains prohibited"
    )
    split_at = sensitive_response.index("abcdefghijklmnop") + 8
    private_root, transport, finalized = configure_resume(
        tmp_path,
        monkeypatch,
        [
            advanced_paragraph_snapshot(
                "      - text: " + json.dumps(sensitive_response[:split_at]),
                "      - statictext: " + json.dumps(sensitive_response[split_at:]),
            )
        ],
    )

    with pytest.raises(workflow.WorkflowRefusal) as captured:
        resume_capture(private_root, advanced_pending_transcript())

    assert captured.value.code == "RESPONSE_SENSITIVE_OR_INVALID"
    assert finalized == {}
    assert_no_resume_submission(transport)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(r'      - text: "\ud800"', id="unpaired-high-surrogate"),
        pytest.param(r'      - statictext: "\udc00"', id="unpaired-low-surrogate"),
    ],
)
def test_unpaired_surrogate_payload_refuses_as_invalid(payload: str) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._completed_response(
            advanced_paragraph_snapshot(payload),
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_SENSITIVE_OR_INVALID"


def test_valid_surrogate_pair_payload_remains_utf8_text() -> None:
    assert orchestrator._completed_response(
        advanced_paragraph_snapshot(r'      - text: "\ud83d\ude00"'),
        profile_id=ADVANCED_PROFILE_ID,
    ) == ("https://chatgpt.com/c/current-response", "e60", "😀")


def test_literal_unpaired_surrogate_refuses_during_candidate_digest() -> None:
    raw_snapshot = advanced_paragraph_snapshot('      - text: "' + "\ud800" + '"')

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._response_candidate_digest(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_SENSITIVE_OR_INVALID"


@pytest.mark.parametrize(
    "heading_line",
    [
        pytest.param(
            '- heading "ChatGPT said:" [ref=e60]',
            id="predecessor-no-attribute",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [level=2] [ref=e60]',
            id="value-attribute-before-ref",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [ref=e60] [disabled]',
            id="valueless-attribute-after-ref",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [disabled] [level=2] [ref=e60] '
            "[busy=true] [current=page]",
            id="multiple-attributes-before-and-after-ref",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [busy=true] [ref=e60] [disabled]',
            id="attribute-order-is-inert",
        ),
        pytest.param(
            '- heading "ChatGPT said:"  [busy=true] [ref=e60]\t[disabled]',
            id="existing-grammar-attribute-whitespace",
        ),
        pytest.param(
            '- heading "ChatGPT said:" '
            "[data-url=https://example.invalid/path] [ref=e60]",
            id="colon-valued-attribute-before-ref",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [ref=e60] [aria-label="ready"]',
            id="quoted-non-whitespace-attribute-value",
        ),
        pytest.param(
            '- heading "ChatGPT said:" [reference=e61] [data-ref=e61] [ref=e60]',
            id="non-reserved-ref-like-attribute-names-and-values",
        ),
    ],
)
def test_complete_non_ref_heading_attributes_preserve_response_bytes(
    heading_line: str,
) -> None:
    raw_snapshot = advanced_response_snapshot(
        "Visible",
        heading_line=heading_line,
    )

    assert orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
    ) == ("https://chatgpt.com/c/current-response", "e60", "Visible")
    assert orchestrator._advanced_response_heading_detail_for_line(heading_line) is None
    assert orchestrator._structural_accessibility_refs(heading_line) == ["e60"]


def test_complete_heading_attributes_are_inert_for_candidate_stability() -> None:
    snapshots = [
        advanced_response_snapshot(
            "Visible",
            heading_line='- heading "ChatGPT said:" [level=2] [ref=e60]',
        ),
        advanced_response_snapshot(
            "Visible",
            heading_line=(
                '- heading "ChatGPT said:" [ref=e60] '
                "[data-url=https://example.invalid/path]"
            ),
        ),
        advanced_response_snapshot(
            "Visible",
            heading_line=('- heading "ChatGPT said:" [disabled] [ref=e60] [busy=true]'),
        ),
    ]

    normalized = [
        orchestrator._normalized_response_candidate(
            item,
            profile_id=ADVANCED_PROFILE_ID,
        )
        for item in snapshots
    ]
    assert len(set(normalized)) == 1
    assert "disabled" not in normalized[0]
    assert "example.invalid" not in normalized[0]
    stability = orchestrator._ResponseStability(ADVANCED_PROFILE_ID)
    assert [stability.observe(item) for item in snapshots] == [False, False, True]


def test_attributed_heading_owns_body_while_opaque_chrome_stays_inert() -> None:
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [level=2] [ref=e60] [busy=false]',
        "- generic [ref=e61]:",
        "  - paragraph [ref=e62]:",
        '    - text: "Visible"',
        '  - button "Copy" [ref=e63]:',
        '    - heading "ChatGPT said:" [ref=e70]',
        "    - generic [ref=e71]:",
        '      - text: "Injected"',
    )

    assert orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
    ) == ("https://chatgpt.com/c/current-response", "e60", "Visible")


def test_invalid_heading_attributes_are_not_normalized_out_of_stability() -> None:
    malformed = [
        advanced_response_snapshot(
            "Visible",
            heading_line='- heading "ChatGPT said:" [ref=e60] [disabled',
        ),
        advanced_response_snapshot(
            "Visible",
            heading_line='- heading "ChatGPT said:" [ref=e60] [busy',
        ),
    ]

    digests = [
        orchestrator._response_candidate_digest(
            item,
            profile_id=ADVANCED_PROFILE_ID,
        )
        for item in malformed
    ]
    assert len(set(digests)) == 2
    for item in malformed:
        with pytest.raises(orchestrator._AdvancedResponseParserRefusal):
            orchestrator._completed_response(
                item,
                profile_id=ADVANCED_PROFILE_ID,
            )


@pytest.mark.parametrize(
    "bad_snapshot",
    [
        pytest.param(
            snapshot('- paragraph "Assistant response" [ref=e60]'),
            id="missing-heading",
        ),
        pytest.param(
            snapshot(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [ref=e61]',
            ),
            id="duplicate-heading",
        ),
        pytest.param(
            snapshot('- article "ChatGPT said:" [ref=e60]'),
            id="wrong-role",
        ),
        pytest.param(
            snapshot('- HEADING "ChatGPT said:" [ref=e60]'),
            id="wrong-case-role",
        ),
        pytest.param(
            snapshot('- heading "chatgpt said:" [ref=e60]'),
            id="wrong-case",
        ),
        pytest.param(
            snapshot('- heading "ChatGPT said" [ref=e60]'),
            id="wrong-punctuation",
        ),
        pytest.param(
            snapshot('- heading " ChatGPT said: " [ref=e60]'),
            id="surrounding-whitespace",
        ),
        pytest.param(
            advanced_response_snapshot().replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:"',
            ),
            id="ref-free-exact-heading",
        ),
        pytest.param(
            advanced_response_snapshot().replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [ref=e60] [ref=e70]',
            ),
            id="multiple-heading-refs",
        ),
        pytest.param(
            advanced_response_snapshot().replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [ref=invalid] [ref=e60]',
            ),
            id="malformed-ref-before-valid-heading-ref",
        ),
        pytest.param(
            advanced_response_snapshot().replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [ref=e60] [ref=invalid]',
            ),
            id="malformed-ref-after-valid-heading-ref",
        ),
        pytest.param(
            advanced_response_snapshot().replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [disabled]',
            ),
            id="ref-free-heading-with-attribute",
        ),
        pytest.param(
            advanced_response_snapshot().replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [ref=e60] [disabled',
            ),
            id="unclosed-heading-attribute",
        ),
        pytest.param(
            advanced_response_snapshot().replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [ref=e60] [data value]',
            ),
            id="malformed-heading-attribute",
        ),
        pytest.param(
            advanced_response_snapshot().replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:"  [ref=e60]',
            ),
            id="non-exact-ref-separator",
        ),
        pytest.param(
            advanced_response_snapshot().replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [disabled]  [ref=e60]',
            ),
            id="non-exact-ref-separator-after-attribute",
        ),
        pytest.param(
            advanced_response_snapshot().replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [ref=e60] [REF=metadata]',
            ),
            id="reserved-wrong-case-ref-attribute",
        ),
        pytest.param(
            advanced_response_snapshot().replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [data=[ref=e70] [ref=e60]',
            ),
            id="nested-ref-attempt-before-valid-ref",
        ),
        pytest.param(
            advanced_response_snapshot().replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [ref=e60] [data=[ref=e70]',
            ),
            id="nested-ref-attempt-after-valid-ref",
        ),
        pytest.param(
            advanced_response_snapshot().replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [disabled] [ref=e61]',
            ),
            id="attributed-heading-body-ref-collision",
        ),
        pytest.param(
            advanced_response_snapshot(
                extra_lines=('  - button "Copy" [ref=e60]',)
            ).replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [disabled] [ref=e60]',
            ),
            id="attributed-heading-global-ref-collision",
        ),
        pytest.param(
            snapshot(
                '- heading "ChatGPT said:" [disabled] [ref=e60]',
                '- heading "ChatGPT said:" [ref=e70] [level=2]',
                "- generic [ref=e61]:",
                '  - text: "Visible"',
            ),
            id="duplicate-attributed-heading",
        ),
        pytest.param(
            advanced_response_snapshot(
                extra_lines=('- article "Assistant response" [ref=e70]',)
            ).replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [disabled] [ref=e60]',
            ),
            id="attributed-heading-competing-legacy-marker",
        ),
        pytest.param(
            advanced_response_snapshot().replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [ref=e60]:',
            ),
            id="container-shaped-heading",
        ),
        pytest.param(
            advanced_response_snapshot().replace(
                '- heading "ChatGPT said:" [ref=e60]',
                '- heading "ChatGPT said:" [ref=e60] unexpected',
            ),
            id="scalar-bearing-heading",
        ),
        pytest.param(
            snapshot(
                '- heading "ChatGPT said:" [ref=e60]',
                '- button "Copy" [ref=e60]',
            ),
            id="ref-collision",
        ),
        pytest.param(
            snapshot(
                '- heading "ChatGPT said:" [ref=e60]',
                '- article "ChatGPT said" [ref=e61]',
            ),
            id="competing-legacy-anchor",
        ),
    ],
)
def test_advanced_response_anchor_drift_refuses_and_resume_never_resubmits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_snapshot: str,
) -> None:
    private_root, transport, finalized = configure_resume(
        tmp_path,
        monkeypatch,
        [bad_snapshot],
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        resume_capture(private_root, advanced_pending_transcript())

    assert captured.value.code == "RESPONSE_SELECTOR_AMBIGUITY"
    assert transport.calls == [
        (
            "browser_navigate",
            {"url": "https://chatgpt.com/c/current-response"},
        ),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_close", {}),
    ]
    assert finalized == {}
    assert_no_resume_submission(transport)


@pytest.mark.parametrize(
    ("bad_snapshot", "expected_code"),
    [
        pytest.param(
            advanced_response_snapshot(url="https://chatgpt.com.evil.example/"),
            "ORIGIN_MISMATCH",
            id="origin-drift",
        ),
        pytest.param(
            snapshot(
                '- alert "Too many requests" [ref=e90]',
                '- heading "ChatGPT said:" [ref=e60]',
            ),
            "STOP_RATE_LIMIT",
            id="stop-state",
        ),
    ],
)
def test_resume_validates_origin_and_stops_before_response_anchor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_snapshot: str,
    expected_code: str,
) -> None:
    private_root, transport, finalized = configure_resume(
        tmp_path,
        monkeypatch,
        [bad_snapshot],
    )

    with pytest.raises(
        (orchestrator.OrchestrationRefusal, workflow.WorkflowRefusal)
    ) as captured:
        resume_capture(private_root, advanced_pending_transcript())

    assert captured.value.code == expected_code
    assert finalized == {}
    assert_no_resume_submission(transport)


def test_generating_marker_prevents_advanced_completion() -> None:
    raw_snapshot = advanced_response_snapshot(
        extra_lines=('- button "Stop generating" [ref=e64]',)
    )

    assert (
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )
        is None
    )


def test_advanced_resume_waits_for_empty_loading_tree_then_captures_without_resubmit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = advice_text(summary="Wait for the existing response anchor.")
    loading = snapshot("- Initial response tree is loading")
    private_root, transport, finalized = configure_resume(
        tmp_path,
        monkeypatch,
        [loading, advanced_response_snapshot(response)],
    )

    result = resume_capture(private_root, advanced_pending_transcript())

    assert result is not None
    assert finalized["response"] == response
    assert finalized["transcript"]["observations"][-1]["refs"] == {
        "assistant_response": ["e60"]
    }
    assert transport.calls == [
        (
            "browser_navigate",
            {"url": "https://chatgpt.com/c/current-response"},
        ),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_close", {}),
    ]
    assert_no_resume_submission(transport)


def test_advanced_pending_resume_waits_then_completes_without_resubmission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = advice_text(summary="Resume the existing conversation only.")
    generating = advanced_response_snapshot(
        response,
        ref="e40",
        extra_lines=('- button "Stop generating" [ref=e41]',),
    )
    still_generating = advanced_response_snapshot(
        response,
        ref="e50",
        extra_lines=('- button "Stop generating" [ref=e51]',),
    )
    private_root, transport, finalized = configure_resume(
        tmp_path,
        monkeypatch,
        [generating, still_generating, advanced_response_snapshot(response)],
    )

    result = resume_capture(private_root, advanced_pending_transcript())

    assert result is not None
    assert finalized["response"] == response
    assert finalized["transcript"]["observations"][-1]["refs"] == {
        "assistant_response": ["e60"]
    }
    assert transport.calls == [
        (
            "browser_navigate",
            {"url": "https://chatgpt.com/c/current-response"},
        ),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_close", {}),
    ]
    assert_no_resume_submission(transport)


def test_legacy_article_completion_behavior_is_unchanged() -> None:
    response = advice_text(summary="Retain the predecessor article selector.")
    legacy_snapshot = snapshot(
        '- article "ChatGPT said" [ref=e70]',
        f"  - text {json.dumps(response)}",
    )

    completed = orchestrator._completed_response(
        legacy_snapshot,
        profile_id=LEGACY_PROFILE_ID,
    )
    pending = orchestrator._complete_pending_transcript(
        legacy_pending_transcript(),
        legacy_snapshot,
    )

    assert completed == (
        "https://chatgpt.com/c/current-response",
        "e70",
        response,
    )
    assert pending is not None
    assert pending[0]["observations"][-1]["refs"] == {"assistant_response": ["e70"]}
    assert pending[1] == response


@pytest.mark.parametrize(
    "response",
    [
        "{}",
        json.dumps(
            {
                "schema": "PRO_ADVICE_V1",
                "summary": "Authority remains invalid.",
                "material_delta": True,
                "open_gaps": [],
                "evidence_refs": [],
                "recommendations": [],
                "authority": "APPROVED_ADVICE",
            },
            separators=(",", ":"),
        ),
    ],
)
def test_invalid_advanced_advice_is_rejected_before_fixture_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response: str,
) -> None:
    raw_snapshot = advanced_response_snapshot(response)
    completed = orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
    )
    assert completed is not None
    execute_called = False

    def execute_fixture(**_arguments: Any) -> dict[str, str]:
        nonlocal execute_called
        execute_called = True
        return {}

    monkeypatch.setattr(workflow, "execute_fixture", execute_fixture)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._finalize_transcript(
            prepared={
                "run_dir": str(run_dir),
                "record_path": str(run_dir / "run-record.v1.jsonl"),
                "run_id": "20260805T000000Z-aaaaaaaaaaaa",
            },
            transcript=advanced_pending_transcript(),
            response=completed[2],
        )

    assert captured.value.code == "ADVICE_INVALID"
    assert execute_called is False
    assert list(run_dir.iterdir()) == []


@pytest.mark.parametrize(
    ("descendants", "expected"),
    [
        pytest.param(
            ("      - generic:", '        - text: "A"'),
            "A",
            id="generic",
        ),
        pytest.param(
            ("      - paragraph:", '        - text: "A"'),
            "A",
            id="paragraph",
        ),
        pytest.param(
            ("      - blockquote:", '        - text: "A"'),
            "A",
            id="blockquote",
        ),
        pytest.param(
            ("      - quote:", '        - text: "A"'),
            "A",
            id="quote",
        ),
        pytest.param(
            ("      - heading:", '        - text: "A"'),
            "A",
            id="heading",
        ),
        pytest.param(
            ("      - code:", '        - text: "A"'),
            "A",
            id="code",
        ),
        pytest.param(
            ("      - codeblock:", '        - text: "A"'),
            "A",
            id="codeblock",
        ),
        pytest.param(
            ("      - listitem:", '        - text: "A"'),
            "A",
            id="standalone-listitem",
        ),
        pytest.param(
            (
                "      - list:",
                "        - listitem:",
                '          - text: "- one"',
                "        - listitem:",
                '          - statictext: "- two"',
            ),
            "- one- two",
            id="list-preserves-predecessor-bytes",
        ),
        pytest.param(
            (
                "      - paragraph:",
                '        - text: "A"',
                '        - statictext: "B"',
                "      - quote:",
                '        - text: "C"',
            ),
            "AB\nC",
            id="multiple-fragments-and-blocks",
        ),
        pytest.param(
            (
                '      - text: "direct"',
                "      - paragraph:",
                '        - text: "wrapped"',
            ),
            "direct\nwrapped",
            id="direct-scalar-with-independent-ref-missing-entry",
        ),
    ],
)
def test_bound_recovery_fallback_reconstructs_exact_embedded_semantics(
    descendants: tuple[str, ...],
    expected: str,
) -> None:
    raw_snapshot = embedded_pre_content_snapshot(*descendants)

    completed = orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )

    assert completed == (
        "https://chatgpt.com/c/current-response",
        "e60",
        expected,
    )


def test_embedded_fallback_is_recovery_only_and_requires_ref_missing_entry() -> None:
    eligible = embedded_pre_content_snapshot(
        "      - paragraph:",
        '        - text: "Visible"',
    )
    direct_only = embedded_pre_content_snapshot('      - text: "Visible"')

    for raw_snapshot, expected_context in (
        (
            eligible,
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
        ),
        (
            direct_only,
            "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_CONTENT",
        ),
    ):
        with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
            orchestrator._completed_response(
                raw_snapshot,
                profile_id=ADVANCED_PROFILE_ID,
            )
        assert captured.value.diagnostic_context_code == expected_context
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            direct_only,
            profile_id=ADVANCED_PROFILE_ID,
            allow_bound_precontent_fallback=True,
        )
    assert captured.value.diagnostic_context_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_CONTENT"
    )


def test_embedded_fallback_accepts_complete_labels_attributes_and_safe_refs() -> None:
    raw_snapshot = embedded_pre_content_snapshot(
        '      - generic "outer [ref=not-structural]" [disabled] [level=2]:\t',
        '        - paragraph "escaped \\"label\\"" [name=a:b] [ref=e70] [busy=true]:',
        '          - text: "Visible"',
    )

    completed = orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )

    assert completed is not None
    assert completed[2] == "Visible"


def _assert_predecessor_ref_missing_refusal(
    raw_snapshot: str,
) -> orchestrator._AdvancedResponseParserRefusal:
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
            allow_bound_precontent_fallback=True,
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
    assert captured.value.diagnostic_context_shape_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING"
    )
    return captured.value


def _assert_ref_free_fallback_code(
    raw_snapshot: str,
    expected_code: str,
) -> None:
    refusal = _assert_predecessor_ref_missing_refusal(raw_snapshot)
    assert refusal.diagnostic_fallback_code == expected_code
    assert not hasattr(refusal, "diagnostic_fallback_entry_code")


def _assert_ref_free_fallback_entry_code(
    raw_snapshot: str,
    expected_code: str,
) -> None:
    refusal = _assert_predecessor_ref_missing_refusal(raw_snapshot)
    assert refusal.diagnostic_fallback_entry_code == expected_code
    assert not hasattr(refusal, "diagnostic_fallback_code")


def test_ref_free_fallback_diagnostic_allowlist_is_exact_and_closed() -> None:
    expected = frozenset(
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

    assert orchestrator.BOUND_RESPONSE_REF_FREE_FALLBACK_CODES == expected
    for code in expected:
        assert (
            orchestrator._validated_bound_response_ref_free_fallback_code(code) == code
        )
        assert (
            orchestrator._validated_bound_response_fallback_code(
                "RESPONSE_NOT_IDENTIFIABLE",
                "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID",
                "ADVANCED_RESPONSE_ACTION_PRE_CONTENT",
                "ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID",
                "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID",
                "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING",
                code,
            )
            == code
        )

    for invalid in (
        None,
        "",
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID ",
        "advanced_response_precontent_ref_free_wrapper_invalid",
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID_SUFFIX",
        "RAW UI",
    ):
        with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
            orchestrator._validated_bound_response_ref_free_fallback_code(invalid)
        assert captured.value.code == "BOUND_RESPONSE_DIAGNOSTIC_INVALID"


def test_ref_free_fallback_entry_diagnostic_allowlist_is_exact_and_closed() -> None:
    assert (
        orchestrator.BOUND_RESPONSE_REF_FREE_FALLBACK_ENTRY_CODES
        == EXPECTED_BOUND_RESPONSE_REF_FREE_FALLBACK_ENTRY_CODES
    )
    for code in EXPECTED_BOUND_RESPONSE_REF_FREE_FALLBACK_ENTRY_CODES:
        assert (
            orchestrator._validated_bound_response_ref_free_fallback_entry_code(code)
            == code
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
                code,
            )
            == code
        )

    for invalid in (
        None,
        "",
        f" {REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR}",
        f"{REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR} ",
        REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR.casefold(),
        f"{REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR}_COUNT_2",
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_UNKNOWN",
        [REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR],
        {"code": REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR},
    ):
        with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
            orchestrator._validated_bound_response_ref_free_fallback_entry_code(invalid)
        assert captured.value.code == "BOUND_RESPONSE_DIAGNOSTIC_INVALID"


@pytest.mark.parametrize(
    ("descendants", "expected_code"),
    [
        pytest.param(
            (
                "      - paragraph:",
                '        - text: "Visible"',
                "      - Generic: residual",
            ),
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID",
            id="wrapper-invalid",
        ),
        pytest.param(
            (
                "      - paragraph:",
                '        - text: "Visible"',
                "      - text: unquoted",
            ),
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_SCALAR_INVALID",
            id="scalar-invalid",
        ),
        pytest.param(
            (
                "      - paragraph:",
                '        - text: "Visible"',
                '      - widget: "unsupported"',
            ),
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_MATERIAL_UNSUPPORTED",
            id="material-unsupported",
        ),
        pytest.param(
            (
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
            (
                "      - paragraph:",
                "      - quote:",
                '        - text: "Visible"',
            ),
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_UNSATISFIED_WITH_CONTENT",
            id="unsatisfied-with-content",
        ),
        pytest.param(
            ("      - paragraph:",),
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_UNSATISFIED_EMPTY",
            id="unsatisfied-empty",
        ),
        pytest.param(
            ("      - paragraph:", '        - text: "   "'),
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_CONTENT_EMPTY",
            id="content-empty",
        ),
    ],
)
def test_ref_free_fallback_diagnostic_direct_matrix(
    descendants: tuple[str, ...],
    expected_code: str,
) -> None:
    _assert_ref_free_fallback_code(
        embedded_pre_content_snapshot(*descendants),
        expected_code,
    )


@pytest.mark.parametrize(
    ("descendants", "expected_code"),
    [
        pytest.param(
            (
                "      - paragraph:",
                '        - text: "Visible"',
                "      - Generic: residual",
                "      - text: unquoted",
            ),
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID",
            id="first-wrapper-before-scalar",
        ),
        pytest.param(
            (
                "      - paragraph:",
                '        - text: "Visible"',
                "      - text: unquoted",
                "      - Generic: residual",
            ),
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_SCALAR_INVALID",
            id="first-scalar-before-wrapper",
        ),
        pytest.param(
            (
                "      - paragraph:",
                '        - text: "Visible"',
                '      - widget: "unsupported"',
                "      - text: unquoted",
            ),
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_MATERIAL_UNSUPPORTED",
            id="first-unsupported-before-scalar",
        ),
        pytest.param(
            (
                "      - generic:",
                '        - text: "Entry"',
                "      - paragraph [ref=e70]:",
                '        - text: "Visible"',
                "      - quote [ref=e70]:",
                "      - text: unquoted",
            ),
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_SCALAR_INVALID",
            id="explicit-defect-before-postscan-ref-collision",
        ),
        pytest.param(
            (
                "      - generic:",
                '        - text: "Entry"',
                "      - paragraph [ref=e70]:",
                '        - text: "Visible"',
                "      - quote [ref=e70]:",
            ),
            "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_REF_COLLISION",
            id="ref-collision-before-unsatisfied-fallback",
        ),
    ],
)
def test_ref_free_fallback_diagnostic_precedence(
    descendants: tuple[str, ...],
    expected_code: str,
) -> None:
    _assert_ref_free_fallback_code(
        embedded_pre_content_snapshot(*descendants),
        expected_code,
    )


@pytest.mark.parametrize(
    "invalid_scalar",
    [
        pytest.param('      - Text: "wrong case"', id="wrong-case-payload"),
        pytest.param('      - text: {"not":"a string"}', id="non-string-json"),
        pytest.param('      - statictext: "\\ud800"', id="lone-surrogate"),
        pytest.param('      - text: "valid" trailing', id="residual-tail"),
    ],
)
def test_ref_free_fallback_scalar_invalid_variants_are_closed(
    invalid_scalar: str,
) -> None:
    _assert_ref_free_fallback_code(
        embedded_pre_content_snapshot(
            "      - paragraph:",
            '        - text: "Visible"',
            invalid_scalar,
        ),
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_SCALAR_INVALID",
    )


@pytest.mark.parametrize(
    "invalid_wrapper",
    [
        pytest.param("      - generic [ref]:", id="valueless-ref"),
        pytest.param("      - paragraph [REF=e70]:", id="wrong-case-ref"),
        pytest.param("      - quote [ref =e70]:", id="spaced-ref"),
        pytest.param("      - generic: trailing", id="residual-tail"),
    ],
)
def test_ref_free_fallback_wrapper_invalid_variants_are_closed(
    invalid_wrapper: str,
) -> None:
    _assert_ref_free_fallback_code(
        embedded_pre_content_snapshot(
            "      - paragraph:",
            '        - text: "Visible"',
            invalid_wrapper,
        ),
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID",
    )


@pytest.mark.parametrize("opaque_role", ["Text", "StaticText"])
def test_ref_free_fallback_preserves_bare_wrong_case_scalar_container_opacity(
    opaque_role: str,
) -> None:
    raw_snapshot = embedded_pre_content_snapshot(
        "      - paragraph:",
        '        - text: "Visible"',
        f"      - {opaque_role}:",
        '        - text: "OPAQUE INJECTION"',
    )

    completed = orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )

    assert completed is not None
    assert completed[2] == "Visible"


@pytest.mark.parametrize(
    "before_group",
    [
        pytest.param(
            ('    - button "Opaque" [ref=e70]:', '      - text: "ignored"'),
            id="button",
        ),
        pytest.param(
            ('    - link "Opaque" [ref=e70]:', '      - text: "ignored"'),
            id="link",
        ),
        pytest.param(
            (
                '    - citation-preview "Opaque" [ref=e70]:',
                '      - text: "ignored"',
            ),
            id="citation",
        ),
        pytest.param(
            ("    - /url: https://example.invalid/[ref=e70]",),
            id="url-metadata",
        ),
        pytest.param(
            ('    - status "Opaque" [ref=e70]:', '      - text: "ignored"'),
            id="unknown-chrome",
        ),
        pytest.param(
            (
                '    - navigation "Opaque" [ref=e70]:',
                '      - text: "ignored"',
            ),
            id="untrusted-region",
        ),
    ],
)
def test_ref_free_fallback_outside_opaque_refs_are_inert(
    before_group: tuple[str, ...],
) -> None:
    raw_snapshot = embedded_pre_content_snapshot(
        "      - generic:",
        '        - text: "A"',
        "      - quote [ref=e70]:",
        '        - text: "B"',
        before_group=before_group,
    )

    completed = orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )

    assert completed is not None
    assert completed[2] == "A\nB"


@pytest.mark.parametrize(
    ("before_group", "after_group"),
    [
        pytest.param(('    - text: ""',), (), id="direct-empty-before"),
        pytest.param(('    - statictext: "   "',), (), id="direct-whitespace-before"),
        pytest.param((), ('    - text: ""',), id="direct-empty-after"),
        pytest.param((), ('    - statictext: "   "',), id="direct-whitespace-after"),
        pytest.param(
            ("    - paragraph [ref=e70]:", '      - text: ""'),
            (),
            id="semantic-empty-before",
        ),
        pytest.param(
            ("    - quote [ref=e70]:", '      - statictext: "   "'),
            (),
            id="semantic-whitespace-before",
        ),
        pytest.param(
            (),
            ("    - paragraph [ref=e70]:", '      - text: ""'),
            id="semantic-empty-after",
        ),
        pytest.param(
            (),
            ("    - quote [ref=e70]:", '      - statictext: "   "'),
            id="semantic-whitespace-after",
        ),
    ],
)
def test_ref_free_fallback_entry_reports_outside_whitespace_scalar_matrix(
    before_group: tuple[str, ...],
    after_group: tuple[str, ...],
) -> None:
    _assert_ref_free_fallback_entry_code(
        embedded_pre_content_snapshot(
            "      - paragraph:",
            '        - text: "Visible"',
            before_group=before_group,
            after_group=after_group,
        ),
        REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR,
    )


@pytest.mark.parametrize(
    ("before_group", "after_group"),
    [
        pytest.param(("    - generic [ref=e70]:",), (), id="generic-before"),
        pytest.param((), ("    - generic [ref=e70]:",), id="generic-after"),
        pytest.param(("    - paragraph [ref=e70]:",), (), id="semantic-before"),
        pytest.param((), ("    - quote [ref=e70]:",), id="semantic-after"),
    ],
)
def test_ref_free_fallback_accepts_silent_outside_presentation_wrapper_matrix(
    before_group: tuple[str, ...],
    after_group: tuple[str, ...],
) -> None:
    completed = orchestrator._completed_response(
        embedded_pre_content_snapshot(
            "      - paragraph:",
            '        - text: "Visible"',
            before_group=before_group,
            after_group=after_group,
        ),
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )

    assert completed == (
        "https://chatgpt.com/c/current-response",
        "e60",
        "Visible",
    )


@pytest.mark.parametrize(
    "outside_wrapper",
    [
        pytest.param(
            "    - paragraph [ref=e70] [ref=e71]:",
            id="additional-valid-ref",
        ),
        pytest.param(
            "    - paragraph [ref=e70] [ref=e70]:",
            id="duplicate-ref",
        ),
        pytest.param(
            "    - paragraph [ref=e70] [REF=e71]:",
            id="wrong-case-ref",
        ),
        pytest.param(
            "    - paragraph [ref=e70] [ref =e71]:",
            id="malformed-ref",
        ),
        pytest.param(
            "    - paragraph [ref=e70]: residual",
            id="residual-line-shape",
        ),
        pytest.param(
            '    - paragraph "[ref=e70]":',
            id="quoted-label-ref-backtracking",
        ),
        pytest.param(
            '    - paragraph "escaped \\"label [ref=e70]\\"" [disabled]:',
            id="escaped-quoted-label-ref-backtracking",
        ),
    ],
)
def test_ref_free_fallback_keeps_non_silent_wrapper_entry_refusal(
    outside_wrapper: str,
) -> None:
    _assert_ref_free_fallback_entry_code(
        embedded_pre_content_snapshot(
            "      - paragraph:",
            '        - text: "Visible"',
            before_group=(outside_wrapper,),
        ),
        REF_FREE_ENTRY_OUTSIDE_PRESENTATION_WRAPPER,
    )


@pytest.mark.parametrize(
    "role",
    ["generic", *sorted(orchestrator.ADVANCED_RESPONSE_SEMANTIC_ROLES)],
)
@pytest.mark.parametrize("placement", ["before", "after"])
def test_ref_free_fallback_accepts_each_exact_silent_wrapper_role(
    role: str,
    placement: str,
) -> None:
    wrapper = f'    - {role} "silent [ref=e999]" [disabled] [ref=e70] [level=2]:'
    completed = orchestrator._completed_response(
        embedded_pre_content_snapshot(
            "      - paragraph:",
            '        - text: "Visible"',
            before_group=(wrapper,) if placement == "before" else (),
            after_group=(wrapper,) if placement == "after" else (),
        ),
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )

    assert completed == (
        "https://chatgpt.com/c/current-response",
        "e60",
        "Visible",
    )


def test_ref_free_fallback_accepts_nested_multiple_silent_trees_and_inert_chrome() -> (
    None
):
    raw_snapshot = embedded_pre_content_snapshot(
        "      - paragraph:",
        '        - text: "Visible"',
        before_group=(
            '    - paragraph "silent outer" [ref=e70]:',
            '      - quote "silent nested" [ref=e71]:',
            '        - button "Opaque chrome" [ref=e90]:',
            '          - heading "ChatGPT said:" [ref=e91]',
            '          - alert "Too many requests" [ref=e92]',
            '          - group "Response actions":',
            '            - text: "OPAQUE ACTION INJECTION"',
            "        - /url: https://example.invalid/ignored",
            '        - status "Unknown chrome" [ref=e93]:',
            '          - group "response actions":',
            '            - text: "OPAQUE NEAR-ACTION INJECTION"',
            '          - group "Response actions" [disabled]:',
            '            - text: "OPAQUE MALFORMED-ACTION INJECTION"',
            '          - text: "OPAQUE UNKNOWN INJECTION"',
            '      - navigation "Untrusted" [ref=e94]:',
            '        - group "Response actions":',
            '          - text: "UNTRUSTED INJECTION"',
        ),
        after_group=(
            '    - list "silent second tree" [ref=e72]:',
            '      - listitem "silent child" [ref=e73]:',
        ),
    )

    completed = orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )

    assert completed == (
        "https://chatgpt.com/c/current-response",
        "e60",
        "Visible",
    )


@pytest.mark.parametrize(
    ("action_line", "expected_detail"),
    [
        pytest.param(
            '      - group "Response actions":',
            "ADVANCED_RESPONSE_ACTION_DUPLICATE",
            id="exact",
        ),
        pytest.param(
            '      - group "response actions":',
            "ADVANCED_RESPONSE_ACTION_LABEL_INVALID",
            id="near-label",
        ),
        pytest.param(
            '      - Group "Response actions":',
            "ADVANCED_RESPONSE_ACTION_ROLE_INVALID",
            id="near-role",
        ),
        pytest.param(
            '      - group "Response actions" [disabled]:',
            "ADVANCED_RESPONSE_ACTION_EXTRA_ATTRIBUTES",
            id="malformed-attributes",
        ),
    ],
)
@pytest.mark.parametrize("placement", ["before", "after"])
def test_ref_free_fallback_never_silences_independently_visible_action_group(
    action_line: str,
    expected_detail: str,
    placement: str,
) -> None:
    wrapper_tree = ("    - paragraph [ref=e70]:", action_line)
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            embedded_pre_content_snapshot(
                "      - paragraph:",
                '        - text: "Visible"',
                before_group=wrapper_tree if placement == "before" else (),
                after_group=wrapper_tree if placement == "after" else (),
            ),
            profile_id=ADVANCED_PROFILE_ID,
            allow_bound_precontent_fallback=True,
        )

    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID"
    )
    assert captured.value.diagnostic_detail_code == expected_detail
    assert not hasattr(captured.value, "diagnostic_fallback_code")
    assert not hasattr(captured.value, "diagnostic_fallback_entry_code")


@pytest.mark.parametrize(
    "wrapper_tree",
    [
        pytest.param(("    - paragraph:",), id="outer-ref-free"),
        pytest.param(
            ("    - paragraph [ref=e70]:", "      - quote:"),
            id="nested-ref-free",
        ),
        pytest.param(
            ("    - paragraph [ref=bad]:",),
            id="outer-no-valid-first-ref",
        ),
    ],
)
def test_ref_free_fallback_preserves_predecessor_bounded_wrapper_refusals(
    wrapper_tree: tuple[str, ...],
) -> None:
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            embedded_pre_content_snapshot(
                "      - paragraph:",
                '        - text: "Visible"',
                before_group=wrapper_tree,
            ),
            profile_id=ADVANCED_PROFILE_ID,
            allow_bound_precontent_fallback=True,
        )

    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID"
    )
    assert not hasattr(captured.value, "diagnostic_context_shape_code")
    assert not hasattr(captured.value, "diagnostic_fallback_code")
    assert not hasattr(captured.value, "diagnostic_fallback_entry_code")


def test_ref_free_fallback_keeps_nested_quoted_label_ref_backtracking_entry() -> None:
    _assert_ref_free_fallback_entry_code(
        embedded_pre_content_snapshot(
            "      - paragraph:",
            '        - text: "Visible"',
            before_group=(
                "    - paragraph [ref=e71]:",
                '      - quote "nested [ref=e70]" [disabled]:',
            ),
        ),
        REF_FREE_ENTRY_OUTSIDE_PRESENTATION_WRAPPER,
    )


def test_ref_free_fallback_silent_wrapper_predicate_controls_extractor_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = orchestrator._advanced_response_embedded_precontent_response
    calls = 0

    def counted(*args: Any, **kwargs: Any) -> tuple[Any, Any]:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        orchestrator,
        "_advanced_response_embedded_precontent_response",
        counted,
    )
    silent = embedded_pre_content_snapshot(
        "      - paragraph:",
        '        - text: "Visible"',
        before_group=("    - paragraph [ref=e70]:",),
    )
    assert (
        orchestrator._completed_response(
            silent,
            profile_id=ADVANCED_PROFILE_ID,
            allow_bound_precontent_fallback=True,
        )
        is not None
    )
    assert calls == 1

    _assert_ref_free_fallback_entry_code(
        silent.replace("[ref=e70]:", "[ref=e70] [REF=e71]:"),
        REF_FREE_ENTRY_OUTSIDE_PRESENTATION_WRAPPER,
    )
    _assert_ref_free_fallback_entry_code(
        silent.replace(
            "    - paragraph [ref=e70]:",
            '    - paragraph [ref=e70]:\n      - text: ""',
        ),
        REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR,
    )
    assert calls == 1


def test_ref_free_fallback_silent_wrappers_never_enter_bytes_or_candidate_indexes() -> (
    None
):
    raw_snapshot = embedded_pre_content_snapshot(
        "      - paragraph:",
        '        - text: "Visible"',
        before_group=(
            '    - paragraph "SILENT OUTER" '
            "[data-url=https://example.invalid/x] [ref=e70]:",
            '      - quote "SILENT INNER" [ref=e71]:',
        ),
    )
    lines = raw_snapshot.splitlines()
    completed = orchestrator._completed_response_with_metadata(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
        enforce_response_safety=False,
    )

    assert completed is not None
    assert completed[2] == "Visible"
    assert completed[3] == frozenset(
        {
            lines.index("      - paragraph:"),
            lines.index('        - text: "Visible"'),
        }
    )
    assert completed[4] == frozenset(
        {
            lines.index(
                '    - paragraph "SILENT OUTER" '
                "[data-url=https://example.invalid/x] [ref=e70]:"
            ),
            lines.index('      - quote "SILENT INNER" [ref=e71]:'),
        }
    )
    assert completed[3].isdisjoint(completed[4])
    normalized = orchestrator._normalized_response_candidate(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )
    assert "Visible" in normalized
    assert "SILENT OUTER" not in normalized
    assert "SILENT INNER" not in normalized


@pytest.mark.parametrize("colliding_ref", ["e60", "e61", "e62"])
def test_ref_free_fallback_silent_wrapper_refs_keep_outer_collision_priority(
    colliding_ref: str,
) -> None:
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            embedded_pre_content_snapshot(
                "      - paragraph:",
                '        - text: "Visible"',
                before_group=(f"    - quote [ref={colliding_ref}]:",),
            ),
            profile_id=ADVANCED_PROFILE_ID,
            allow_bound_precontent_fallback=True,
        )

    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_STRUCTURAL_REF_COLLISION"
    )
    assert not hasattr(captured.value, "diagnostic_fallback_code")
    assert not hasattr(captured.value, "diagnostic_fallback_entry_code")


def test_ref_free_fallback_rejects_duplicate_refs_across_independent_silent_trees() -> (
    None
):
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            embedded_pre_content_snapshot(
                "      - paragraph:",
                '        - text: "Visible"',
                before_group=(
                    "    - paragraph [ref=e70]:",
                    "    - quote [ref=e70]:",
                ),
            ),
            profile_id=ADVANCED_PROFILE_ID,
            allow_bound_precontent_fallback=True,
        )

    assert captured.value.diagnostic_code == (
        "ADVANCED_RESPONSE_STRUCTURAL_REF_COLLISION"
    )
    assert not hasattr(captured.value, "diagnostic_fallback_code")
    assert not hasattr(captured.value, "diagnostic_fallback_entry_code")


def test_ref_free_fallback_silent_wrapper_colon_attribute_ref_collides_with_embedded_ref() -> (
    None
):
    raw_snapshot = embedded_pre_content_snapshot(
        "      - paragraph:",
        '        - text: "A"',
        "      - quote [ref=e70]:",
        '        - text: "B"',
        before_group=(
            "    - paragraph [data-url=https://example.invalid/x] [ref=e70]:",
        ),
    )

    _assert_ref_free_fallback_code(
        raw_snapshot,
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_REF_COLLISION",
    )


def test_ref_free_fallback_silent_wrapper_churn_is_inert_but_defects_reset_stability() -> (
    None
):
    first = embedded_pre_content_snapshot(
        "      - paragraph:",
        '        - text: "Visible"',
        before_group=('    - paragraph "First" [ref=e70]:',),
    )
    churned = first.replace('"First" [ref=e70]', '"Second" [ref=e170]')
    non_silent = churned.replace(
        '    - paragraph "Second" [ref=e170]:',
        '    - paragraph "Second" [ref=e170]:\n      - text: ""',
    )
    ref_collision = churned.replace(
        '        - text: "Visible"',
        '        - text: "Visible"\n'
        "      - quote [ref=e170]:\n"
        '        - text: "Collision"',
    )

    assert orchestrator._response_candidate_digest(
        first,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    ) == orchestrator._response_candidate_digest(
        churned,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )
    assert orchestrator._response_candidate_digest(
        churned,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    ) != orchestrator._response_candidate_digest(
        non_silent,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as collision:
        orchestrator._completed_response(
            ref_collision,
            profile_id=ADVANCED_PROFILE_ID,
            allow_bound_precontent_fallback=True,
        )
    assert collision.value.diagnostic_fallback_code == (
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_REF_COLLISION"
    )

    stability = orchestrator._ResponseStability(
        ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )
    assert stability.observe(first) is False
    assert stability.observe(churned) is False
    assert stability.observe(non_silent) is False
    assert stability.observe(churned) is False
    assert stability.observe(first) is False
    assert stability.observe(churned) is True

    collision_stability = orchestrator._ResponseStability(
        ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )
    assert collision_stability.observe(first) is False
    assert collision_stability.observe(churned) is False
    assert collision_stability.observe(ref_collision) is False
    assert collision_stability.observe(churned) is False
    assert collision_stability.observe(first) is False
    assert collision_stability.observe(churned) is True


def test_ref_free_fallback_preserves_enclosing_chain_stability_and_excludes_only_independent_silent_roots() -> (
    None
):
    first = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - paragraph "Enclosing" [ref=e70]:',
        '    - group "Response actions":',
        "      - paragraph:",
        '        - text: "Visible"',
        '  - quote "Independent silent" [ref=e71]:',
    )
    enclosing_churned = first.replace(
        'paragraph "Enclosing" [ref=e70]',
        'paragraph "Changed enclosing" [ref=e170]',
    )
    silent_churned = first.replace(
        'quote "Independent silent" [ref=e71]',
        'quote "Changed silent" [ref=e171]',
    )
    lines = first.splitlines()

    completed = orchestrator._completed_response_with_metadata(
        first,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
        enforce_response_safety=False,
    )

    assert completed is not None
    assert completed[2] == "Visible"
    assert completed[4] == frozenset(
        {lines.index('  - quote "Independent silent" [ref=e71]:')}
    )
    assert lines.index('  - paragraph "Enclosing" [ref=e70]:') not in completed[4]
    first_digest = orchestrator._response_candidate_digest(
        first,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )
    assert first_digest != orchestrator._response_candidate_digest(
        enclosing_churned,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )
    assert first_digest == orchestrator._response_candidate_digest(
        silent_churned,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )


def test_ref_free_fallback_entry_scalar_suppressor_precedes_wrapper() -> None:
    _assert_ref_free_fallback_entry_code(
        embedded_pre_content_snapshot(
            "      - paragraph:",
            '        - text: "Visible"',
            before_group=(
                "    - paragraph [ref=e70]:",
                '      - statictext: "   "',
            ),
            after_group=("    - generic [ref=e71]:",),
        ),
        REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR,
    )


def test_ref_free_fallback_entry_excludes_enclosing_wrapper_record_but_not_sibling_scalar() -> (
    None
):
    enclosing_only = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - paragraph [ref=e70]:",
        '    - group "Response actions":',
        "      - paragraph:",
        '        - text: "Visible"',
    )
    completed = orchestrator._completed_response(
        enclosing_only,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )
    assert completed == (
        "https://chatgpt.com/c/current-response",
        "e60",
        "Visible",
    )

    sibling_scalar = enclosing_only.replace(
        '    - group "Response actions":',
        '    - text: "   "\n    - group "Response actions":',
    )
    _assert_ref_free_fallback_entry_code(
        sibling_scalar,
        REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR,
    )


@pytest.mark.parametrize(
    "before_group",
    [
        pytest.param(
            ('    - button "Opaque" [ref=e70]:', '      - text: "ignored"'),
            id="opaque",
        ),
        pytest.param(
            (
                '    - navigation "Untrusted" [ref=e70]:',
                '      - paragraph "ignored" [ref=e71]:',
                '        - text: "ignored"',
            ),
            id="untrusted",
        ),
    ],
)
def test_ref_free_fallback_entry_excludes_opaque_and_untrusted_subtrees(
    monkeypatch: pytest.MonkeyPatch,
    before_group: tuple[str, ...],
) -> None:
    original = orchestrator._advanced_response_embedded_precontent_response
    calls = 0

    def counted(*args: Any, **kwargs: Any) -> tuple[Any, Any]:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        orchestrator,
        "_advanced_response_embedded_precontent_response",
        counted,
    )
    completed = orchestrator._completed_response(
        embedded_pre_content_snapshot(
            "      - paragraph:",
            '        - text: "Visible"',
            '      - group "Response actions":',
            '        - button "Copy" [ref=e80]',
            before_group=before_group,
        ),
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )

    assert completed is not None
    assert completed[2] == "Visible"
    assert calls == 1


@pytest.mark.parametrize(
    ("before_group", "expected_code"),
    [
        pytest.param(
            ('    - text: ""',),
            REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR,
            id="scalar",
        ),
        pytest.param(
            ("    - paragraph [ref=e70] [REF=e71]:",),
            REF_FREE_ENTRY_OUTSIDE_PRESENTATION_WRAPPER,
            id="non-silent-wrapper",
        ),
    ],
)
def test_ref_free_fallback_entry_suppression_never_invokes_extractor(
    monkeypatch: pytest.MonkeyPatch,
    before_group: tuple[str, ...],
    expected_code: str,
) -> None:
    monkeypatch.setattr(
        orchestrator,
        "_advanced_response_embedded_precontent_response",
        lambda *_args, **_kwargs: pytest.fail(
            "entry suppression must precede the pure fallback extractor"
        ),
    )
    _assert_ref_free_fallback_entry_code(
        embedded_pre_content_snapshot(
            "      - paragraph:",
            '        - text: "Visible"',
            before_group=before_group,
        ),
        expected_code,
    )


def test_ref_free_fallback_entry_requires_capability_and_exact_six_field_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orchestrator,
        "_advanced_response_embedded_precontent_response",
        lambda *_args, **_kwargs: pytest.fail(
            "disabled or wrong-chain fallback must not invoke the extractor"
        ),
    )
    disabled = embedded_pre_content_snapshot(
        "      - paragraph:",
        '        - text: "Visible"',
        before_group=('    - text: ""',),
    )
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            disabled,
            profile_id=ADVANCED_PROFILE_ID,
            allow_bound_precontent_fallback=False,
        )
    assert captured.value.diagnostic_context_shape_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING"
    )
    assert not hasattr(captured.value, "diagnostic_fallback_code")
    assert not hasattr(captured.value, "diagnostic_fallback_entry_code")

    wrong_chain = embedded_pre_content_snapshot("      - generic [ref=bad]:")
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as wrong:
        orchestrator._completed_response(
            wrong_chain,
            profile_id=ADVANCED_PROFILE_ID,
            allow_bound_precontent_fallback=True,
        )
    assert wrong.value.diagnostic_context_shape_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID"
    )
    assert not hasattr(wrong.value, "diagnostic_fallback_code")
    assert not hasattr(wrong.value, "diagnostic_fallback_entry_code")


def test_ref_free_fallback_success_and_attempted_failure_emit_no_entry_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = orchestrator._advanced_response_embedded_precontent_response
    calls = 0

    def counted(*args: Any, **kwargs: Any) -> tuple[Any, Any]:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        orchestrator,
        "_advanced_response_embedded_precontent_response",
        counted,
    )
    successful = embedded_pre_content_snapshot(
        "      - paragraph:",
        '        - text: "Visible"',
    )
    completed = orchestrator._completed_response(
        successful,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )
    assert completed is not None
    assert completed[2] == "Visible"

    failed = embedded_pre_content_snapshot(
        "      - paragraph:",
        '        - text: "Visible"',
        "      - Generic: residual",
    )
    refusal = _assert_predecessor_ref_missing_refusal(failed)
    assert refusal.diagnostic_fallback_code == (
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID"
    )
    assert not hasattr(refusal, "diagnostic_fallback_entry_code")
    assert calls == 2


def test_ref_free_fallback_entry_nonwhitespace_and_owned_body_boundary_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nonwhitespace = embedded_pre_content_snapshot(
        "      - paragraph:",
        '        - text: "Embedded"',
        before_group=('    - text: "Outside"',),
    )
    assert orchestrator._completed_response(
        nonwhitespace,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    ) == ("https://chatgpt.com/c/current-response", "e60", "Outside")

    monkeypatch.setattr(
        orchestrator,
        "_advanced_response_embedded_precontent_response",
        lambda *_args, **_kwargs: pytest.fail(
            "a wrapper beyond the owned body must not reach the extractor"
        ),
    )
    outside_body = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - paragraph [ref=e70]:",
        '    - group "Response actions":',
        "      - paragraph:",
        '        - text: "Visible"',
        "  - quote [ref=e71]:",
        "- generic [ref=e90]:",
    )
    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._completed_response(
            outside_body,
            profile_id=ADVANCED_PROFILE_ID,
            allow_bound_precontent_fallback=True,
        )
    assert captured.value.diagnostic_code == "ADVANCED_RESPONSE_BOUNDARY_CONFLICT"
    assert not hasattr(captured.value, "diagnostic_fallback_code")
    assert not hasattr(captured.value, "diagnostic_fallback_entry_code")


def test_ref_free_fallback_nested_action_refs_are_inert() -> None:
    raw_snapshot = embedded_pre_content_snapshot(
        "      - generic:",
        '        - text: "A"',
        "      - quote [ref=e70]:",
        '        - text: "B"',
        '      - group "Response actions":',
        '        - button "Copy" [ref=e70]',
    )

    completed = orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )

    assert completed is not None
    assert completed[2] == "A\nB"


def test_ref_free_fallback_diagnostic_never_reads_beyond_owned_group() -> None:
    lines = [
        "- generic [ref=e61]:",
        '  - group "Response actions":',
        "    - paragraph:",
        '      - text: "Visible"',
        '    - widget: "outside-owned-group"',
    ]

    embedded, diagnostic = orchestrator._advanced_response_embedded_precontent_response(
        lines,
        body_line=0,
        body_indent=0,
        group_line=1,
        group_indent=2,
        owned_end=4,
        outside_refs=("e61",),
    )

    assert embedded == ("Visible", frozenset({2, 3}))
    assert diagnostic is None


@pytest.mark.parametrize(
    "invalid_line",
    [
        pytest.param("      - generic [ref]:", id="valueless-ref"),
        pytest.param("      - generic [REF=e70]:", id="wrong-case-ref"),
        pytest.param("      - generic [ref =e70]:", id="padded-ref"),
        pytest.param("      - generic ref=e70:", id="unbracketed-ref"),
        pytest.param("      - generic [name=[ref=e70]:", id="nested-ref"),
        pytest.param("      - generic", id="residual-line-shape"),
        pytest.param("      - Generic:", id="wrong-case-role"),
        pytest.param('      - text: {"not":"a string"}', id="non-string"),
        pytest.param("      - text: unquoted", id="malformed-json"),
        pytest.param('      - widget: "unsupported"', id="unsupported-scalar"),
    ],
)
def test_embedded_fallback_invalid_material_retains_predecessor_refusal(
    invalid_line: str,
) -> None:
    raw_snapshot = embedded_pre_content_snapshot(
        "      - paragraph:",
        '        - text: "Visible"',
        invalid_line,
    )

    _assert_predecessor_ref_missing_refusal(raw_snapshot)


@pytest.mark.parametrize("collision_ref", ["e60", "e61", "e62"])
def test_embedded_fallback_used_ref_cannot_collide_outside_action_subtree(
    collision_ref: str,
) -> None:
    raw_snapshot = embedded_pre_content_snapshot(
        "      - generic:",
        '        - text: "Entry"',
        f"      - paragraph [ref={collision_ref}]:",
        '        - text: "Collision"',
    )

    _assert_ref_free_fallback_code(
        raw_snapshot,
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_REF_COLLISION",
    )


def test_embedded_fallback_used_refs_must_be_unique() -> None:
    raw_snapshot = embedded_pre_content_snapshot(
        "      - generic:",
        '        - text: "Entry"',
        "      - paragraph [ref=e70]:",
        '        - text: "A"',
        "      - quote [ref=e70]:",
        '        - text: "B"',
    )

    _assert_ref_free_fallback_code(
        raw_snapshot,
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_REF_COLLISION",
    )


def test_embedded_fallback_finds_outer_refs_after_colon_valued_attributes() -> None:
    def raw_snapshot(embedded_ref: str) -> str:
        return snapshot(
            '- heading "ChatGPT said:" [ref=e60]',
            "- generic [ref=e61]:",
            "  - paragraph [data-url=https://example.invalid/x] [ref=e70]:",
            '    - group "Response actions":',
            "      - paragraph:",
            '        - text: "A"',
            f"      - quote [ref={embedded_ref}]:",
            '        - text: "B"',
        )

    _assert_ref_free_fallback_code(
        raw_snapshot("e70"),
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_REF_COLLISION",
    )
    completed = orchestrator._completed_response(
        raw_snapshot("e71"),
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )
    assert completed is not None
    assert completed[2] == "AB"


@pytest.mark.parametrize(
    "trusted_outer_line",
    [
        pytest.param(
            "- paragraph [data-url=https://example.invalid/x] JUNK [ref=e70]:",
            id="residual-before-ref",
        ),
        pytest.param(
            '- button "Outside" [ref=e70] JUNK:',
            id="residual-after-ref",
        ),
        pytest.param(
            "- mystery [data-url=https://example.invalid/x] [ref=e70] JUNK:",
            id="malformed-unknown-record",
        ),
        pytest.param(
            '- paragraph "unterminated [ref=e70]:',
            id="unterminated-label",
        ),
        pytest.param(
            '- paragraph "escaped\\"unterminated [ref=e70]:',
            id="escaped-unterminated-label",
        ),
        pytest.param(
            '- text [ref=e70]: "outside"',
            id="text-pre-colon-structural-ref",
        ),
        pytest.param(
            '- statictext [ref=e70]: "outside"',
            id="statictext-pre-colon-structural-ref",
        ),
        pytest.param(
            '- Text [ref=e70]: "outside"',
            id="wrong-case-text-structural-ref",
        ),
        pytest.param(
            '- text: "outside" [ref=e70]',
            id="text-post-payload-structural-ref",
        ),
        pytest.param(
            "- statictext: unquoted [ref=e70]",
            id="statictext-unquoted-structural-ref",
        ),
        pytest.param(
            '- text: {"value":1} [ref=e70]',
            id="text-non-string-structural-ref",
        ),
    ],
)
def test_embedded_fallback_collision_scan_covers_residual_trusted_records(
    trusted_outer_line: str,
) -> None:
    raw_snapshot = snapshot(
        trusted_outer_line,
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - generic [ref=e62]:",
        '    - group "Response actions":',
        "      - paragraph:",
        '        - text: "A"',
        "      - quote [ref=e70]:",
        '        - text: "B"',
    )

    _assert_ref_free_fallback_code(
        raw_snapshot,
        "ADVANCED_RESPONSE_PRECONTENT_REF_FREE_REF_COLLISION",
    )


def test_embedded_fallback_never_treats_quoted_label_ref_text_as_structural() -> None:
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - paragraph "label [ref=e70] with colon:" [ref=e71]:',
        '    - group "Response actions":',
        "      - paragraph:",
        '        - text: "A"',
        "      - quote [ref=e70]:",
        '        - text: "B"',
    )

    completed = orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )

    assert completed is not None
    assert completed[2] == "AB"

    scalar_data_snapshot = snapshot(
        '- text: "scalar data [ref=e70]"',
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - generic [ref=e62]:",
        '    - group "Response actions":',
        "      - paragraph:",
        '        - text: "A"',
        "      - quote [ref=e70]:",
        '        - text: "B"',
    )
    scalar_completed = orchestrator._completed_response(
        scalar_data_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )
    assert scalar_completed is not None
    assert scalar_completed[2] == "A\nB"


@pytest.mark.parametrize(
    ("before_group", "after_group"),
    [
        pytest.param(('    - text: ""',), (), id="empty-scalar-before"),
        pytest.param(('    - statictext: "   "',), (), id="whitespace-before"),
        pytest.param((), ('    - text: ""',), id="empty-scalar-after"),
        pytest.param((), ('    - statictext: "   "',), id="whitespace-after"),
    ],
)
def test_embedded_fallback_rejects_response_material_outside_selected_group(
    before_group: tuple[str, ...],
    after_group: tuple[str, ...],
) -> None:
    raw_snapshot = embedded_pre_content_snapshot(
        "      - paragraph:",
        '        - text: "Visible"',
        before_group=before_group,
        after_group=after_group,
    )

    _assert_predecessor_ref_missing_refusal(raw_snapshot)


def test_embedded_fallback_keeps_enclosing_wrapper_and_sibling_chrome_inert() -> None:
    raw_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        '  - button "Before chrome" [ref=e70]:',
        '    - text: "ignored before"',
        "  - paragraph [ref=e71]:",
        '    - group "Response actions":',
        "      - paragraph:",
        '        - text: "Visible"',
        '  - link "After chrome" [ref=e72]:',
        '    - text: "ignored after"',
    )

    completed = orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )

    assert completed is not None
    assert completed[2] == "Visible"


@pytest.mark.parametrize(
    "invalid_descendants",
    [
        pytest.param(
            ("      - paragraph:",),
            id="unsatisfied-wrapper",
        ),
        pytest.param(
            ("      - paragraph:", '        - text: ""'),
            id="empty-response",
        ),
        pytest.param(
            ("      - paragraph:", '        - statictext: "   "'),
            id="whitespace-response",
        ),
        pytest.param(
            ("      - paragraph:", '        - text: "\\ud800"'),
            id="lone-surrogate",
        ),
        pytest.param(
            (
                "      - paragraph:",
                '        - text: "Visible"',
                "      - quote:",
                '        - button "Copy":',
            ),
            id="wrapper-with-only-opaque-child",
        ),
    ],
)
def test_embedded_fallback_requires_satisfied_nonempty_utf8_content(
    invalid_descendants: tuple[str, ...],
) -> None:
    _assert_predecessor_ref_missing_refusal(
        embedded_pre_content_snapshot(*invalid_descendants)
    )


def test_embedded_fallback_keeps_action_chrome_and_untrusted_subtrees_opaque() -> None:
    raw_snapshot = embedded_pre_content_snapshot(
        "      - paragraph:",
        '        - text: "Visible"',
        '      - button "Answer now [ref=e60]":',
        '        - alert "Too many requests" [ref=e61]',
        '        - text: "BUTTON INJECTION"',
        '      - link "Source" [ref=e60]:',
        '        - heading "ChatGPT said:" [ref=e61]',
        '      - citation-preview "Citation":',
        '        - statictext: "CITATION INJECTION"',
        "      - /url: https://example.invalid",
        '        - text: "URL INJECTION"',
        '      - status "unknown chrome" [ref=e60]:',
        '        - text: "UNKNOWN INJECTION"',
        '      - navigation "page navigation" [ref=e61]:',
        '        - text: "UNTRUSTED INJECTION"',
        '      - group "Response actions":',
        '        - button "Stop generating" [ref=e60]',
        '        - text: "NESTED ACTION INJECTION"',
    )

    completed = orchestrator._completed_response(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )
    normalized = orchestrator._normalized_response_candidate(
        raw_snapshot,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )

    assert completed is not None
    assert completed[2] == "Visible"
    assert (
        orchestrator._has_generating_marker(
            raw_snapshot,
            profile_id=ADVANCED_PROFILE_ID,
        )
        is False
    )
    assert orchestrator._stop_state(raw_snapshot, phase="response") is None
    for injected in (
        "BUTTON INJECTION",
        "CITATION INJECTION",
        "URL INJECTION",
        "UNKNOWN INJECTION",
        "UNTRUSTED INJECTION",
        "NESTED ACTION INJECTION",
        "Too many requests",
        "Stop generating",
    ):
        assert injected not in normalized


def test_embedded_fallback_stability_tracks_content_and_canonicalizes_used_refs() -> (
    None
):
    first = embedded_pre_content_snapshot(
        "      - generic:",
        '        - text: "Entry"',
        "      - paragraph [name=a:b] [ref=e70]:",
        '        - text: "A"',
    )
    aliased = first.replace("[ref=e70]", "[ref=e170]")
    changed = aliased.replace('text: "A"', 'text: "B"')
    stability = orchestrator._ResponseStability(
        ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )

    assert orchestrator._response_candidate_digest(
        first,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    ) == orchestrator._response_candidate_digest(
        aliased,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )
    assert stability.observe(first) is False
    assert stability.observe(aliased) is False
    assert stability.observe(changed) is False
    assert stability.observe(changed) is False
    assert stability.observe(changed) is True


@pytest.mark.parametrize(
    "outside_lines",
    [
        pytest.param(
            ('- article "Assistant response" [ref=e90]',),
            id="legacy-marker-competition",
        ),
        pytest.param(
            (
                '- button "Outside A" [ref=e90]',
                '- link "Outside B" [ref=e90]',
            ),
            id="outside-global-ref-collision",
        ),
    ],
)
def test_noneligible_marker_or_ref_conflict_keeps_embedded_lines_out_of_stability(
    outside_lines: tuple[str, ...],
) -> None:
    first = embedded_pre_content_snapshot(
        "      - paragraph:",
        '        - text: "A"',
        after_group=outside_lines,
    )
    changed = first.replace('text: "A"', 'text: "B"')

    assert (
        orchestrator._advanced_response_embedded_candidate_line_indexes(
            first,
            allow_bound_precontent_fallback=True,
        )
        == set()
    )
    assert orchestrator._response_candidate_digest(
        first,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    ) == orchestrator._response_candidate_digest(
        changed,
        profile_id=ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )


@pytest.mark.parametrize(
    "first_response,second_response",
    [
        (
            "session_token=abcdefghijklmnop",
            "session_token=qrstuvwxyzabcdef",
        ),
        ("A" * (workflow.MAX_TEXT_BYTES + 1), "B" * (workflow.MAX_TEXT_BYTES + 1)),
    ],
    ids=["sensitive-values", "oversized-responses"],
)
def test_embedded_fallback_stability_precedes_size_and_sensitivity_policy(
    first_response: str,
    second_response: str,
) -> None:
    first = embedded_pre_content_snapshot(
        "      - paragraph:",
        f"        - text: {json.dumps(first_response)}",
    )
    second = embedded_pre_content_snapshot(
        "      - paragraph:",
        f"        - text: {json.dumps(second_response)}",
    )
    stability = orchestrator._ResponseStability(
        ADVANCED_PROFILE_ID,
        allow_bound_precontent_fallback=True,
    )

    assert stability.observe(first) is False
    assert stability.observe(first) is False
    assert stability.observe(second) is False
    assert stability.observe(second) is False
    assert stability.observe(second) is True
    with pytest.raises(
        (orchestrator.OrchestrationRefusal, workflow.WorkflowRefusal)
    ) as captured:
        orchestrator._completed_response(
            second,
            profile_id=ADVANCED_PROFILE_ID,
            allow_bound_precontent_fallback=True,
        )
    assert not hasattr(captured.value, "diagnostic_fallback_code")
