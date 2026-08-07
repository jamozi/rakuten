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
    extra_lines: tuple[str, ...] = (),
    url: str = "https://chatgpt.com/c/current-response",
) -> str:
    actual_response = advice_text() if response is None else response
    return snapshot(
        f'- heading "ChatGPT said:" [ref={ref}]',
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
        '- paragraph "assistant sidebar label" [ref=e68]:',
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
    "bad_snapshot",
    [
        pytest.param(
            advanced_action_group_snapshot(
                include_content_before=False,
                after_group=(
                    "    - paragraph [ref=e63]:",
                    "      - text: " + json.dumps(advice_text()),
                ),
            ),
            id="group-before-first-fragment",
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
        pytest.param(
            advanced_action_group_snapshot(
                group_line='      - group "Response actions":'
            ),
            id="group-inside-response-paragraph",
        ),
        pytest.param(
            advanced_action_group_snapshot(group_line='  - group "Response actions":'),
            id="group-with-only-body-root-ancestor",
        ),
        pytest.param(
            advanced_action_group_snapshot(group_line='- group "Response actions":'),
            id="group-outside-body-boundary",
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
            id="group-inside-link",
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
                '      - status "unexpected node" [ref=e64]:',
                "      - text: " + json.dumps(advice_text()),
            ),
            id="unexpected-structural-role",
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
            advanced_paragraph_snapshot('      - text: ""'),
            id="empty-only-fragment",
        ),
        pytest.param(
            advanced_paragraph_snapshot(
                "      - text: " + json.dumps("prefix" + advice_text())
            ),
            id="prose-prefix",
        ),
        pytest.param(
            advanced_paragraph_snapshot(
                "      - text: " + json.dumps(advice_text() + "suffix")
            ),
            id="prose-suffix",
        ),
        pytest.param(
            advanced_paragraph_snapshot(
                "      - text: " + json.dumps(advice_text() + "{}")
            ),
            id="second-object-suffix",
        ),
        pytest.param(
            advanced_paragraph_snapshot(
                "      - text: " + json.dumps(advice_text()[:17]),
                extra_lines=(
                    '- paragraph "outside body" [ref=e64]:',
                    "  - text: " + json.dumps(advice_text()[17:]),
                ),
            ),
            id="boundary-escape",
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
                "- Too many requests",
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
