"""Deterministic evidence for the approved ST-0101 response-wait lifecycle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from scripts import chatgpt_pro_orchestrator as orchestrator
from scripts import chatgpt_pro_workflow as workflow


ADVANCED_PROFILE_ID = workflow.ADVANCED_PROFILE_ID
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
README_PATH = REPOSITORY_ROOT / "changes/st-0101/README.md"
SKILL_PATH = Path("/home/minami/.codex/skills/raos-ask-pro/SKILL.md")
CONVERSATION_URL = "https://chatgpt.com/c/continuous-response-wait"
RAW_REQUEST_MARKER = "RAW_REQUEST_RESPONSE_WAIT_MARKER_7c04e45f"
RAW_SNAPSHOT_MARKER = "RAW_SNAPSHOT_SIDEBAR_MARKER_91a85c73"
RAW_OUTSIDE_URL = "https://example.invalid/raw-response-wait-url"


def snapshot(*lines: str, url: str = CONVERSATION_URL) -> str:
    return "\n".join((f"- Page URL: {url}", *lines))


def advice_text(summary: str = "Keep waiting in the same approved window.") -> str:
    return json.dumps(
        {
            "schema": "PRO_ADVICE_V1",
            "summary": summary,
            "material_delta": True,
            "open_gaps": ["Reconcile the remaining named gap."],
            "evidence_refs": ["ST-0101 deterministic response-wait evidence"],
            "recommendations": ["Retain the approved interface boundary."],
            "authority": "UNAPPROVED_ADVICE",
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def advanced_response_snapshot(
    response: str,
    *,
    ref_base: int,
    outside_marker: str = RAW_SNAPSHOT_MARKER,
) -> str:
    return snapshot(
        f'- heading "ChatGPT said:" [ref=e{ref_base}]',
        f"- generic [ref=e{ref_base + 1}]:",
        f"  - generic [ref=e{ref_base + 2}]:",
        f"    - paragraph [ref=e{ref_base + 3}]:",
        f"      - text: {json.dumps(response)}",
        f'- complementary "{outside_marker}" [ref=e{ref_base + 4}]:',
        f"  - link [ref=e{ref_base + 5}]:",
        f"    - /url: {RAW_OUTSIDE_URL}",
    )


def embedded_pre_content_response_snapshot(response: str) -> str:
    return snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - generic [ref=e62]:",
        '    - paragraph "silent outside wrapper" [ref=e70]:',
        '    - group "Response actions":',
        "      - paragraph:",
        f"        - text: {json.dumps(response)}",
    )


def ambiguous_response_snapshot(response: str, *, ref_base: int) -> str:
    return snapshot(
        f'- heading "ChatGPT said:" [ref=e{ref_base}]',
        f"- generic [ref=e{ref_base + 1}]:",
        f"  - generic [ref=e{ref_base + 2}]:",
        f"    - paragraph [ref=e{ref_base + 3}]:",
        f"      - text: {json.dumps(response)}",
        f'- heading "ChatGPT said:" [ref=e{ref_base + 10}]',
        f"- generic [ref=e{ref_base + 11}]:",
        f"  - generic [ref=e{ref_base + 12}]:",
        f"    - paragraph [ref=e{ref_base + 13}]:",
        f"      - text: {json.dumps(response)}",
        f'- complementary "{RAW_SNAPSHOT_MARKER}" [ref=e{ref_base + 20}]',
    )


def answer_now_snapshot(*, ref_base: int) -> str:
    """Exact current advanced in-progress shape with an empty body root."""

    return snapshot(
        f'- heading "ChatGPT said:" [ref=e{ref_base}]',
        f"- generic [ref=e{ref_base + 1}]:",
        f'- button "Answer now" [ref=e{ref_base + 2}]',
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
    url: str = "https://chatgpt.com/",
) -> dict[str, Any]:
    return {
        "state": state,
        "url": url,
        "authenticated": True,
        "stop_state": None,
        "model_label": model_label,
        "effort_label": effort_label,
        "option_labels": [] if option_labels is None else option_labels,
        "refs": {} if refs is None else refs,
        "generating": generating,
        "response_complete": response_complete,
    }


def pre_submission_observations() -> list[dict[str, Any]]:
    profile = workflow.EXPECTED_ADVANCED_PROFILE
    return [
        observation("landing", refs={"model_picker": ["e1"]}),
        observation(
            "model_menu",
            option_labels=list(profile["model_option_labels"]),
            refs={"target_model": ["e2"]},
        ),
        observation(
            "effort_menu",
            model_label=str(profile["target_model"]),
            option_labels=list(profile["effort_option_labels"]),
            refs={"target_effort": ["e3"]},
        ),
        observation(
            "ready",
            model_label=str(profile["target_model"]),
            effort_label=str(profile["target_effort"]),
            refs={"composer": ["e41"]},
        ),
    ]


def pending_transcript() -> dict[str, Any]:
    profile = workflow.EXPECTED_ADVANCED_PROFILE
    return {
        "schema_version": workflow.SCHEMA_VERSION,
        "profile_id": ADVANCED_PROFILE_ID,
        "observations": [
            *pre_submission_observations(),
            observation(
                "send_ready",
                model_label=str(profile["target_model"]),
                effort_label=str(profile["target_effort"]),
                refs={"send": ["e50"]},
            ),
            observation(
                "submitted",
                model_label=str(profile["target_model"]),
                effort_label=str(profile["target_effort"]),
                generating=True,
                url=CONVERSATION_URL,
            ),
        ],
    }


def inspect_pre_submission(
    _transport: orchestrator.BrowserTransport,
    *,
    interactive_auth_wait_seconds: int,
) -> tuple[
    dict[str, str],
    list[dict[str, Any]],
    str,
    dict[str, Any],
    dict[str, Any],
]:
    assert 0 <= interactive_auth_wait_seconds <= 900
    profile = dict(workflow.EXPECTED_ADVANCED_PROFILE)
    observations = pre_submission_observations()
    return (
        {"prompt_secret_name": "RAOS_CHATGPT_PROMPT"},
        observations,
        ADVANCED_PROFILE_ID,
        profile,
        observations[-1],
    )


class ScriptedTransport:
    """Inert same-window transport with observable cleanup ordering."""

    mode = "LIVE"

    def __init__(
        self,
        snapshots: list[str | BaseException],
        *,
        secret_file: Path | None = None,
        wait_failure: BaseException | None = None,
        send_failure: BaseException | None = None,
        close_probe: Callable[[ScriptedTransport], None] | None = None,
    ) -> None:
        self.snapshots = list(snapshots)
        self.secret_file = secret_file
        self.wait_failure = wait_failure
        self.send_failure = send_failure
        self.close_probe = close_probe
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.wait_calls = 0
        self.closed = False
        self.close_facts: dict[str, Any] = {}

    def call(self, tool: str, arguments: dict[str, Any]) -> str:
        self.calls.append((tool, dict(arguments)))
        if (
            tool == "browser_click"
            and arguments.get("element") == "send prompt"
            and self.send_failure is not None
        ):
            raise self.send_failure
        if tool == "browser_wait_for":
            self.wait_calls += 1
            if self.wait_failure is not None:
                raise self.wait_failure
            return ""
        if tool == "browser_snapshot":
            if not self.snapshots:
                raise AssertionError("unexpected browser snapshot")
            result = self.snapshots.pop(0)
            if isinstance(result, BaseException):
                raise result
            return result
        return ""

    def close(self) -> None:
        self.calls.append(("browser_close", {}))
        self.closed = True
        if self.close_probe is not None:
            self.close_probe(self)


def private_root(tmp_path: Path) -> Path:
    root = tmp_path / ".secrets"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    return root


def write_setup_state(root: Path) -> None:
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
            "updated_at": "2026-08-05T00:00:00Z",
        },
    )


def private_request(root: Path, name: str) -> Path:
    request_root = root / "chatgpt-pro-requests"
    request_root.mkdir(mode=0o700, exist_ok=True)
    request_root.chmod(0o700)
    path = request_root / name
    path.write_text(RAW_REQUEST_MARKER, encoding="utf-8")
    path.chmod(0o600)
    return path


def run_dir(root: Path, run_id: str) -> Path:
    return root / "chatgpt-pro-runs" / run_id


def close_probe(root: Path) -> Callable[[ScriptedTransport], None]:
    def observe(transport: ScriptedTransport) -> None:
        run_directories = sorted(
            path for path in (root / "chatgpt-pro-runs").iterdir() if path.is_dir()
        )
        assert len(run_directories) == 1
        active_run = run_directories[0]
        state = json.loads(
            (active_run / "orchestration-state.v1.json").read_text(encoding="utf-8")
        )
        events = (
            (active_run / "run-record.v1.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        final_event = json.loads(events[-1])
        transport.close_facts = {
            "status": state["status"],
            "conversation_url": state["conversation_url"],
            "event_type": final_event["event_type"],
            "record_hash_valid": final_event["payload"]["state_sha256"]
            == hashlib.sha256(orchestrator._canonical_json(state)).hexdigest(),
            "pending_exists": (active_run / "pending-transcript.v1.json").exists(),
            "proposal_exists": (active_run / "unapproved-proposal.md").exists(),
            "secret_exists": transport.secret_file is not None
            and transport.secret_file.exists(),
        }

    return observe


def install_live_stubs(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(
        orchestrator,
        "_inspect_live_pre_submission_ui",
        inspect_pre_submission,
    )
    write_setup_state(root)


def stable_candidates(response: str, *, ref_base: int = 600) -> list[str]:
    return [
        advanced_response_snapshot(
            response,
            ref_base=ref_base + index * 10,
            outside_marker=f"{RAW_SNAPSHOT_MARKER}-{index}",
        )
        for index in range(orchestrator.RESPONSE_STABILITY_OBSERVATIONS)
    ]


def prepare_interrupted_ask(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    importance: str = "ordinary",
) -> tuple[dict[str, Any], ScriptedTransport]:
    install_live_stubs(root, monkeypatch)
    transports: list[ScriptedTransport] = []

    def transport_factory(
        _wrapper: Path,
        secret_file: Path,
        browser: str,
    ) -> ScriptedTransport:
        assert browser == "edge"
        transport = ScriptedTransport(
            [
                snapshot(
                    '- button "Send prompt" [ref=e50]', url="https://chatgpt.com/"
                ),
                snapshot(f'- status "{RAW_SNAPSHOT_MARKER}" [ref=e701]'),
            ],
            secret_file=secret_file,
            wait_failure=KeyboardInterrupt(),
            close_probe=close_probe(root),
        )
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", transport_factory)
    exit_code, result = orchestrator.ask(
        private_root=root,
        request_file=private_request(root, "response-wait-request.txt"),
        importance=importance,
        fake_scenario=None,
        parent_run_id=None,
        gap_file=None,
    )

    assert exit_code == 0
    assert len(transports) == 1
    return result, transports[0]


def test_semantic_stability_normalizes_refs_excludes_outside_and_resets() -> None:
    response_a = advice_text("First semantic candidate.")
    response_b = advice_text("Second semantic candidate.")
    candidates_a = stable_candidates(response_a, ref_base=100)
    candidates_b = stable_candidates(response_b, ref_base=300)

    normalized = [
        orchestrator._normalized_response_candidate(
            item,
            profile_id=ADVANCED_PROFILE_ID,
        )
        for item in candidates_a
    ]

    assert normalized[0] == normalized[1] == normalized[2]
    assert "[ref=r1]" in normalized[0]
    assert "[ref=e100]" not in normalized[0]
    assert RAW_SNAPSHOT_MARKER not in normalized[0]
    assert RAW_OUTSIDE_URL not in normalized[0]

    stability = orchestrator._ResponseStability(ADVANCED_PROFILE_ID)
    assert [stability.observe(item) for item in candidates_a] == [False, False, True]

    resetting = orchestrator._ResponseStability(ADVANCED_PROFILE_ID)
    sequence = [
        candidates_a[0],
        candidates_a[1],
        candidates_b[0],
        candidates_b[1],
        candidates_b[2],
    ]
    assert [resetting.observe(item) for item in sequence] == [
        False,
        False,
        False,
        False,
        True,
    ]
    assert orchestrator.RESPONSE_POLL_SECONDS == 5
    assert orchestrator.RESPONSE_STABILITY_OBSERVATIONS == 3


def test_response_text_and_unrelated_sidebar_labels_are_not_ui_markers() -> None:
    response = advice_text("Keep thinking content inside the response body.")
    candidates = stable_candidates(response, ref_base=450)
    stability = orchestrator._ResponseStability(ADVANCED_PROFILE_ID)

    assert all(not orchestrator._has_generating_marker(item) for item in candidates)
    assert [stability.observe(item) for item in candidates] == [False, False, True]

    unrelated_sidebar = snapshot(
        '- complementary "Assistant shortcuts" [ref=e490]',
        '  - link "Assistant settings" [ref=e491]',
    )
    assert orchestrator._has_assistant_marker(unrelated_sidebar) is False
    assert (
        orchestrator._response_candidate_digest(
            unrelated_sidebar,
            profile_id=ADVANCED_PROFILE_ID,
        )
        is None
    )
    assert orchestrator._has_generating_marker(
        snapshot('- button "Stop thinking" [ref=e492]')
    )


def test_exact_answer_now_is_advanced_only_generating_marker_and_pending() -> None:
    pending = answer_now_snapshot(ref_base=500)

    assert orchestrator._has_generating_marker(
        pending,
        profile_id=ADVANCED_PROFILE_ID,
    )
    assert not orchestrator._has_generating_marker(pending)
    assert not orchestrator._has_generating_marker(
        pending,
        profile_id="pro-extended-combined-v1",
    )
    assert (
        orchestrator._response_candidate_digest(
            pending,
            profile_id=ADVANCED_PROFILE_ID,
        )
        is None
    )
    assert (
        orchestrator._completed_response(
            pending,
            profile_id=ADVANCED_PROFILE_ID,
        )
        is None
    )


@pytest.mark.parametrize(
    "near_match",
    [
        pytest.param('- link "Answer now" [ref=e510]', id="wrong-role"),
        pytest.param('- button "answer now" [ref=e511]', id="wrong-case"),
        pytest.param('- button "Answer now!" [ref=e512]', id="punctuation"),
        pytest.param('- button " Answer now" [ref=e513]', id="leading-space"),
        pytest.param('- button "Answer now " [ref=e514]', id="trailing-space"),
        pytest.param('- button "Please Answer now" [ref=e515]', id="prefix"),
        pytest.param('- button "Answer now please" [ref=e516]', id="suffix"),
        pytest.param(
            '- button "Answer now" [disabled] [ref=e517]',
            id="attribute-drift",
        ),
        pytest.param(
            '- button "Answer now Answer now" [ref=e518]',
            id="duplicate-token",
        ),
        pytest.param('- text: "Answer now"', id="text-payload"),
        pytest.param('- statictext: "Answer now"', id="statictext-payload"),
        pytest.param('- status "Answer now" [ref=e519]', id="status-role"),
    ],
)
def test_answer_now_near_matches_never_become_generating_marker(
    near_match: str,
) -> None:
    assert not orchestrator._has_generating_marker(
        snapshot(
            '- heading "ChatGPT said:" [ref=e520]',
            "- generic [ref=e521]:",
            near_match,
        ),
        profile_id=ADVANCED_PROFILE_ID,
    )


def test_duplicate_exact_answer_now_controls_fail_closed_as_ambiguity() -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._has_generating_marker(
            snapshot(
                '- heading "ChatGPT said:" [ref=e530]',
                "- generic [ref=e531]:",
                '- button "Answer now" [ref=e532]',
                '- button "Answer now" [ref=e533]',
            ),
            profile_id=ADVANCED_PROFILE_ID,
        )

    assert captured.value.code == "RESPONSE_SELECTOR_AMBIGUITY"


def test_answer_now_resets_existing_advanced_stability_sequence() -> None:
    response = advice_text("Reset stability while Answer now is visible.")
    candidates = stable_candidates(response, ref_base=540)
    stability = orchestrator._ResponseStability(ADVANCED_PROFILE_ID)

    assert stability.observe(candidates[0]) is False
    assert stability.observe(candidates[1]) is False
    assert stability.observe(answer_now_snapshot(ref_base=580)) is False
    assert [stability.observe(candidate) for candidate in candidates] == [
        False,
        False,
        True,
    ]


def test_answer_now_guidance_is_advanced_exact_and_observation_only() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    assert 'button "Answer now"' in readme
    assert "strict `gpt-5.6-sol-pro-advanced-v1` profile only" in readme
    assert "never click" in readme
    assert "text/statictext" in readme
    assert "legacy profile" in readme


@pytest.mark.raos_owner_private
def test_owner_private_skill_keeps_answer_now_observation_only() -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    assert 'button "Answer now"' in skill
    assert "strict `gpt-5.6-sol-pro-advanced-v1` profile only" in skill
    assert "never click" in skill
    assert "text/statictext" in skill
    assert "legacy profile" in skill


def test_advanced_answer_now_waits_past_twenty_polls_without_click_or_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = advice_text("Finalize only after Answer now disappears.")
    answer_now_snapshots = [
        answer_now_snapshot(ref_base=700 + index * 10) for index in range(23)
    ]
    response_snapshots = [
        *answer_now_snapshots,
        *stable_candidates(response, ref_base=1000),
    ]
    transport = ScriptedTransport(
        [
            snapshot('- button "Send prompt" [ref=e50]', url="https://chatgpt.com/"),
            *response_snapshots,
        ]
    )
    parser_calls: list[str] = []
    finalized: dict[str, Any] = {}
    progress: list[tuple[int, int, str, str | None]] = []
    real_completed_response = orchestrator._completed_response

    def count_parser(
        snapshot_text: str,
        *,
        profile_id: str,
    ) -> tuple[str, str, str] | None:
        parser_calls.append(snapshot_text)
        return real_completed_response(snapshot_text, profile_id=profile_id)

    def finalize(**arguments: Any) -> tuple[dict[str, str], dict[str, Any], str, str]:
        finalized.update(arguments)
        return (
            {"response_sha256": "a" * 64},
            {"authority": "UNAPPROVED_ADVICE"},
            "b" * 64,
            "c" * 64,
        )

    monkeypatch.setattr(
        orchestrator,
        "_inspect_live_pre_submission_ui",
        inspect_pre_submission,
    )
    monkeypatch.setattr(orchestrator, "_completed_response", count_parser)
    monkeypatch.setattr(orchestrator, "_finalize_transcript", finalize)
    monkeypatch.setattr(workflow, "_append_event", lambda *_args, **_kwargs: "d" * 64)

    result = orchestrator._live_capture(
        prepared={
            "run_id": "20260806T000000Z-aaaaaaaaaaaa",
            "run_dir": str(tmp_path / "run"),
            "record_path": str(tmp_path / "run-record.v1.jsonl"),
            "prompt_sha256": "e" * 64,
        },
        transport=transport,
        interactive_auth_wait_seconds=0,
        on_wait_progress=lambda elapsed, polls, phase, url: progress.append(
            (elapsed, polls, phase, url)
        ),
    )

    assert result[1]["authority"] == "UNAPPROVED_ADVICE"
    assert finalized["response"] == response
    assert parser_calls == [response_snapshots[-1]]
    assert transport.wait_calls == len(response_snapshots) - 1
    assert transport.wait_calls > 20
    assert progress == [
        (60, 12, "response_generating", CONVERSATION_URL),
        (120, 24, "candidate_stabilizing", CONVERSATION_URL),
    ]
    assert (
        sum(
            tool == "browser_click" and arguments.get("element") == "send prompt"
            for tool, arguments in transport.calls
        )
        == 1
    )


def test_normal_live_ask_does_not_enable_bound_ref_free_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = advice_text("Normal ask must retain predecessor refusal.")
    embedded = embedded_pre_content_response_snapshot(response)
    transport = ScriptedTransport(
        [
            snapshot('- button "Send prompt" [ref=e50]', url="https://chatgpt.com/"),
            embedded,
            embedded,
            embedded,
        ]
    )
    monkeypatch.setattr(
        orchestrator,
        "_inspect_live_pre_submission_ui",
        inspect_pre_submission,
    )
    monkeypatch.setattr(workflow, "_append_event", lambda *_args, **_kwargs: "d" * 64)

    with pytest.raises(orchestrator.LiveResponseUnavailable) as captured:
        orchestrator._live_capture(
            prepared={
                "run_id": "20260810T000000Z-aaaaaaaaaaaa",
                "run_dir": str(tmp_path / "run"),
                "record_path": str(tmp_path / "run-record.v1.jsonl"),
                "prompt_sha256": "e" * 64,
            },
            transport=transport,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert transport.wait_calls == 2
    assert sum(tool == "browser_type" for tool, _arguments in transport.calls) == 1
    assert (
        sum(
            tool == "browser_click" and arguments.get("element") == "send prompt"
            for tool, arguments in transport.calls
        )
        == 1
    )


def test_ordinary_waiting_resume_does_not_enable_bound_ref_free_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    response = advice_text("Ordinary WAITING must retain predecessor refusal.")
    embedded = embedded_pre_content_response_snapshot(response)
    transport = ScriptedTransport([embedded, embedded, embedded])

    with pytest.raises(orchestrator._AdvancedResponseParserRefusal) as captured:
        orchestrator._resume_live_capture(
            prepared={
                "run_id": "20260810T000000Z-bbbbbbbbbbbb",
                "run_dir": str(tmp_path / "run"),
                "record_path": str(tmp_path / "run-record.v1.jsonl"),
                "prompt_sha256": "e" * 64,
            },
            transcript=pending_transcript(),
            conversation_url=CONVERSATION_URL,
            private_root=root,
            browser="edge",
            transport=transport,
        )

    assert captured.value.code == "RESPONSE_NOT_IDENTIFIABLE"
    assert captured.value.diagnostic_context_shape_code == (
        "ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING"
    )
    assert not hasattr(captured.value, "diagnostic_fallback_code")
    assert not hasattr(captured.value, "diagnostic_fallback_entry_code")
    assert transport.calls == [
        ("browser_navigate", {"url": CONVERSATION_URL}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
    ]
    assert not any(
        tool == "browser_click"
        and (
            arguments.get("element") == "Answer now"
            or arguments.get("target")
            in {f"e{700 + index * 10 + 2}" for index in range(23)}
        )
        for tool, arguments in transport.calls
    )
    assert all(tool != "browser_close" for tool, _arguments in transport.calls)


def test_live_ask_waits_past_twenty_polls_and_parses_only_stable_complete_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = advice_text("Capture only after the response body stops changing.")
    empty_loading = [
        snapshot(f'- status "loading-{index}" [ref=e{1000 + index}]')
        for index in range(21)
    ]
    generating = [
        snapshot(
            f'- heading "ChatGPT said:" [ref=e{1200 + index * 2}]',
            f'- button "Stop generating" [ref=e{1201 + index * 2}]',
        )
        for index in range(2)
    ]
    partial_heading = [
        snapshot(f'- heading "ChatGPT said:" [ref=e{1300 + index}]')
        for index in range(2)
    ]
    partial_body = [
        advanced_response_snapshot(response[:47], ref_base=1400 + index * 10)
        for index in range(2)
    ]
    response_snapshots = [
        *empty_loading,
        *generating,
        *partial_heading,
        *partial_body,
        *stable_candidates(response, ref_base=1500),
    ]
    transport = ScriptedTransport(
        [
            snapshot('- button "Send prompt" [ref=e50]', url="https://chatgpt.com/"),
            *response_snapshots,
        ]
    )
    finalized: dict[str, Any] = {}
    parser_calls: list[str] = []
    progress: list[tuple[int, int, str, str]] = []
    real_completed_response = orchestrator._completed_response

    def count_parser(
        snapshot_text: str, *, profile_id: str
    ) -> tuple[str, str, str] | None:
        parser_calls.append(snapshot_text)
        return real_completed_response(snapshot_text, profile_id=profile_id)

    def finalize(**arguments: Any) -> tuple[dict[str, str], dict[str, Any], str, str]:
        finalized.update(arguments)
        return (
            {"response_sha256": "a" * 64},
            {"authority": "UNAPPROVED_ADVICE"},
            "b" * 64,
            "c" * 64,
        )

    monkeypatch.setattr(
        orchestrator,
        "_inspect_live_pre_submission_ui",
        inspect_pre_submission,
    )
    monkeypatch.setattr(orchestrator, "_completed_response", count_parser)
    monkeypatch.setattr(orchestrator, "_finalize_transcript", finalize)
    monkeypatch.setattr(workflow, "_append_event", lambda *_args, **_kwargs: "d" * 64)

    result = orchestrator._live_capture(
        prepared={
            "run_id": "20260805T000000Z-aaaaaaaaaaaa",
            "run_dir": str(tmp_path / "run"),
            "record_path": str(tmp_path / "run-record.v1.jsonl"),
            "prompt_sha256": "e" * 64,
        },
        transport=transport,
        interactive_auth_wait_seconds=0,
        on_wait_progress=lambda elapsed, polls, phase, url: progress.append(
            (elapsed, polls, phase, url)
        ),
    )

    assert result[1]["authority"] == "UNAPPROVED_ADVICE"
    assert finalized["response"] == response
    assert len(parser_calls) == 1
    assert parser_calls[0] == response_snapshots[-1]
    assert transport.wait_calls == len(response_snapshots) - 1
    assert transport.wait_calls > 20
    assert progress == [
        (60, 12, "response_absent", CONVERSATION_URL),
        (120, 24, "candidate_stabilizing", CONVERSATION_URL),
    ]
    assert all(
        arguments == {"time": 5}
        for tool, arguments in transport.calls
        if tool == "browser_wait_for"
    )
    assert sum(tool == "browser_type" for tool, _ in transport.calls) == 1
    assert (
        sum(
            tool == "browser_click" and arguments.get("element") == "send prompt"
            for tool, arguments in transport.calls
        )
        == 1
    )
    assert all(tool != "browser_close" for tool, _ in transport.calls)
    assert transport.closed is False


def test_normal_ask_discards_internal_response_diagnostic_from_all_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    install_live_stubs(root, monkeypatch)
    malformed = [
        snapshot(
            f'- heading "ChatGPT said:" [ref=e{1600 + index * 10}]',
            f"- generic [ref=e{1601 + index * 10}]:",
            '  - group "Response actions":',
            "    - generic:",
        )
        for index in range(orchestrator.RESPONSE_STABILITY_OBSERVATIONS)
    ]
    transports: list[ScriptedTransport] = []

    def transport_factory(
        _wrapper: Path,
        secret_file: Path,
        browser: str,
    ) -> ScriptedTransport:
        assert browser == "edge"
        transport = ScriptedTransport(
            [
                snapshot(
                    '- button "Send prompt" [ref=e50]',
                    url="https://chatgpt.com/",
                ),
                *malformed,
            ],
            secret_file=secret_file,
            close_probe=close_probe(root),
        )
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", transport_factory)
    exit_code, result = orchestrator.ask(
        private_root=root,
        request_file=private_request(root, "normal-ask-parser-refusal.txt"),
        importance="ordinary",
        fake_scenario=None,
        parent_run_id=None,
        gap_file=None,
    )

    assert exit_code == 0
    assert result["status"] == "PRO_UNAVAILABLE_FALLBACK"
    assert result["reason_code"] == "RESPONSE_NOT_IDENTIFIABLE"
    assert "diagnostic_code" not in result
    assert "diagnostic_detail_code" not in result
    assert "diagnostic_context_code" not in result
    assert "diagnostic_context_detail_code" not in result
    assert "diagnostic_context_shape_code" not in result
    assert "diagnostic_fallback_code" not in result
    assert "diagnostic_fallback_entry_code" not in result
    assert len(transports) == 1
    run = run_dir(root, result["run_id"])
    state_text = (run / "orchestration-state.v1.json").read_text(encoding="utf-8")
    record_text = (run / "run-record.v1.jsonl").read_text(encoding="utf-8")
    status_result = orchestrator.status(private_root=root, run_id=result["run_id"])
    assert "diagnostic_code" not in state_text
    assert "diagnostic_code" not in record_text
    assert "diagnostic_code" not in status_result
    assert "diagnostic_detail_code" not in state_text
    assert "diagnostic_detail_code" not in record_text
    assert "diagnostic_detail_code" not in status_result
    assert "diagnostic_context_code" not in state_text
    assert "diagnostic_context_code" not in record_text
    assert "diagnostic_context_code" not in status_result
    assert "diagnostic_context_detail_code" not in state_text
    assert "diagnostic_context_detail_code" not in record_text
    assert "diagnostic_context_detail_code" not in status_result
    assert "diagnostic_context_shape_code" not in state_text
    assert "diagnostic_context_shape_code" not in record_text
    assert "diagnostic_context_shape_code" not in status_result
    assert "diagnostic_fallback_code" not in state_text
    assert "diagnostic_fallback_code" not in record_text
    assert "diagnostic_fallback_code" not in status_result
    assert "diagnostic_fallback_entry_code" not in state_text
    assert "diagnostic_fallback_entry_code" not in record_text
    assert "diagnostic_fallback_entry_code" not in status_result
    assert not (run / "unapproved-proposal.md").exists()


def test_interrupt_during_ask_finalization_is_not_misclassified_as_resumable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    install_live_stubs(root, monkeypatch)
    response = advice_text("Interrupt finalization without duplicating completion.")
    transports: list[ScriptedTransport] = []
    finalized: dict[str, Any] = {}

    def transport_factory(
        _wrapper: Path,
        secret_file: Path,
        _browser: str,
    ) -> ScriptedTransport:
        transport = ScriptedTransport(
            [
                snapshot(
                    '- button "Send prompt" [ref=e50]',
                    url="https://chatgpt.com/",
                ),
                *stable_candidates(response, ref_base=1800),
            ],
            secret_file=secret_file,
        )
        transports.append(transport)
        return transport

    def interrupt_finalize(**arguments: Any) -> tuple[Any, ...]:
        finalized.update(arguments)
        raise KeyboardInterrupt

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", transport_factory)
    monkeypatch.setattr(orchestrator, "_finalize_transcript", interrupt_finalize)

    with pytest.raises(KeyboardInterrupt):
        orchestrator.ask(
            private_root=root,
            request_file=private_request(root, "finalization-interrupt.txt"),
            importance="ordinary",
            fake_scenario=None,
            parent_run_id=None,
            gap_file=None,
        )

    assert len(transports) == 1
    assert transports[0].closed is True
    assert finalized["transcript"]["observations"][-1]["state"] == "complete"
    run_directories = list((root / "chatgpt-pro-runs").iterdir())
    assert len(run_directories) == 1
    active_run = run_directories[0]
    state = json.loads(
        (active_run / "orchestration-state.v1.json").read_text(encoding="utf-8")
    )
    events = [
        json.loads(line)
        for line in (active_run / "run-record.v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert state["status"] == "PREPARED"
    assert not (active_run / "pending-transcript.v1.json").exists()
    assert not any(event["event_type"] == "WAIT_INTERRUPTED" for event in events)
    assert (
        sum(
            tool == "browser_click" and arguments.get("element") == "send prompt"
            for tool, arguments in transports[0].calls
        )
        == 1
    )


@pytest.mark.parametrize("failure_phase", ["send", "first-post-send-snapshot"])
def test_prebinding_interrupt_or_disconnect_is_submission_ambiguous_and_unbound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_phase: str,
) -> None:
    root = private_root(tmp_path)
    install_live_stubs(root, monkeypatch)
    transports: list[ScriptedTransport] = []

    def transport_factory(
        _wrapper: Path,
        secret_file: Path,
        _browser: str,
    ) -> ScriptedTransport:
        snapshots: list[str | BaseException] = [
            snapshot('- button "Send prompt" [ref=e50]', url="https://chatgpt.com/")
        ]
        send_failure: BaseException | None = None
        if failure_phase == "send":
            send_failure = KeyboardInterrupt()
        else:
            snapshots.append(orchestrator.TransportUnavailable("MCP_DISCONNECTED"))
        transport = ScriptedTransport(
            snapshots,
            secret_file=secret_file,
            send_failure=send_failure,
            close_probe=close_probe(root),
        )
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", transport_factory)
    exit_code, result = orchestrator.ask(
        private_root=root,
        request_file=private_request(root, f"prebinding-{failure_phase}.txt"),
        importance="ordinary",
        fake_scenario=None,
        parent_run_id=None,
        gap_file=None,
    )

    assert exit_code == 0
    assert result["status"] == "SUBMISSION_AMBIGUOUS"
    assert result["resubmit_allowed"] is False
    assert len(transports) == 1
    assert transports[0].close_facts == {
        "status": "SUBMISSION_AMBIGUOUS",
        "conversation_url": None,
        "event_type": "MCP_RECONNECT_REQUIRED",
        "record_hash_valid": True,
        "pending_exists": True,
        "proposal_exists": False,
        "secret_exists": True,
    }
    active_run = run_dir(root, result["run_id"])
    state_before = (active_run / "orchestration-state.v1.json").read_bytes()
    record_before = (active_run / "run-record.v1.jsonl").read_bytes()

    def unexpected_transport(*_arguments: Any, **_keywords: Any) -> None:
        raise AssertionError("unbound live resume must fail before transport creation")

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", unexpected_transport)
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.resume(
            private_root=root,
            run_id=result["run_id"],
            fake_scenario=None,
        )

    assert captured.value.code == "LIVE_RESUME_SCOPE"
    assert (active_run / "orchestration-state.v1.json").read_bytes() == state_before
    assert (active_run / "run-record.v1.jsonl").read_bytes() == record_before
    assert not list((root / "chatgpt-pro").glob("*.env"))


def test_public_ask_persists_only_sanitized_sixty_second_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    install_live_stubs(root, monkeypatch)
    transports: list[ScriptedTransport] = []
    pending_snapshots: list[str | BaseException] = [
        *[
            snapshot(f'- status "{RAW_SNAPSHOT_MARKER}-{index}" [ref=e{5000 + index}]')
            for index in range(13)
        ],
        KeyboardInterrupt(),
    ]

    def transport_factory(
        _wrapper: Path,
        secret_file: Path,
        _browser: str,
    ) -> ScriptedTransport:
        transport = ScriptedTransport(
            [
                snapshot(
                    '- button "Send prompt" [ref=e50]',
                    url="https://chatgpt.com/",
                ),
                *pending_snapshots,
            ],
            secret_file=secret_file,
            close_probe=close_probe(root),
        )
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", transport_factory)
    exit_code, result = orchestrator.ask(
        private_root=root,
        request_file=private_request(root, "progress-request.txt"),
        importance="ordinary",
        fake_scenario=None,
        parent_run_id=None,
        gap_file=None,
    )

    assert exit_code == 0
    assert result["status"] == "WAITING"
    assert result["resubmit_allowed"] is False
    assert len(transports) == 1
    transport = transports[0]
    assert transport.wait_calls == 13
    assert transport.close_facts["status"] == "WAITING"
    assert transport.close_facts["event_type"] == "WAIT_INTERRUPTED"
    assert transport.close_facts["record_hash_valid"] is True

    active_run = run_dir(root, result["run_id"])
    lines = (
        (active_run / "run-record.v1.jsonl").read_text(encoding="utf-8").splitlines()
    )
    events = [json.loads(line) for line in lines]
    progress_events = [
        event for event in events if event["event_type"] == "RESPONSE_WAIT_PROGRESS"
    ]
    assert len(progress_events) == 1
    assert progress_events[0]["payload"] == {
        "elapsed_seconds": 60,
        "phase": "response_absent",
        "poll_count": 12,
        "state_sha256": progress_events[0]["payload"]["state_sha256"],
    }
    assert isinstance(progress_events[0]["payload"]["state_sha256"], str)
    assert len(progress_events[0]["payload"]["state_sha256"]) == 64
    serialized_progress = json.dumps(progress_events[0], sort_keys=True)
    assert RAW_REQUEST_MARKER not in serialized_progress
    assert RAW_SNAPSHOT_MARKER not in serialized_progress
    assert CONVERSATION_URL not in serialized_progress
    assert "e5012" not in serialized_progress
    event_count, final_event_hash = workflow._verify_events(lines, result["run_id"])
    assert event_count == len(lines)
    assert final_event_hash == events[-1]["event_sha256"]


def test_explicit_ask_interrupt_is_durable_then_resume_waits_without_resubmission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    interrupted, ask_transport = prepare_interrupted_ask(root, monkeypatch)
    interrupted_run = run_dir(root, interrupted["run_id"])

    assert interrupted["status"] == "WAITING"
    assert interrupted["resubmit_allowed"] is False
    assert ask_transport.close_facts == {
        "status": "WAITING",
        "conversation_url": CONVERSATION_URL,
        "event_type": "WAIT_INTERRUPTED",
        "record_hash_valid": True,
        "pending_exists": True,
        "proposal_exists": False,
        "secret_exists": True,
    }
    assert not ask_transport.secret_file.exists()
    assert sum(tool == "browser_type" for tool, _ in ask_transport.calls) == 1
    assert (
        sum(
            tool == "browser_click" and arguments.get("element") == "send prompt"
            for tool, arguments in ask_transport.calls
        )
        == 1
    )
    verified_waiting = orchestrator.status(
        private_root=root,
        run_id=interrupted["run_id"],
    )
    assert verified_waiting["status"] == "WAITING"

    response = advice_text("Resume the existing response without sending again.")
    response_snapshots = [
        *[answer_now_snapshot(ref_base=2000 + index * 10) for index in range(21)],
        *[
            snapshot(
                f'- heading "ChatGPT said:" [ref=e{2300 + index * 2}]',
                f'- button "Stop generating" [ref=e{2301 + index * 2}]',
            )
            for index in range(2)
        ],
        *stable_candidates(response, ref_base=2400),
    ]
    resume_transports: list[ScriptedTransport] = []

    def resume_transport_factory(
        _wrapper: Path,
        secret_file: Path,
        browser: str,
    ) -> ScriptedTransport:
        assert browser == "edge"
        transport = ScriptedTransport(
            response_snapshots,
            secret_file=secret_file,
            close_probe=close_probe(root),
        )
        resume_transports.append(transport)
        return transport

    monkeypatch.setattr(
        orchestrator,
        "StdioMcpTransport",
        resume_transport_factory,
    )
    resume_code, resumed = orchestrator.resume(
        private_root=root,
        run_id=interrupted["run_id"],
        fake_scenario=None,
    )

    assert resume_code == 0
    assert resumed["status"] == "ADVICE_CAPTURED"
    assert resumed["resubmitted"] is False
    assert len(resume_transports) == 1
    resume_transport = resume_transports[0]
    assert resume_transport.wait_calls == len(response_snapshots) - 1
    assert resume_transport.wait_calls > 20
    assert resume_transport.close_facts == {
        "status": "ADVICE_CAPTURED",
        "conversation_url": CONVERSATION_URL,
        "event_type": "MCP_RECONNECTED",
        "record_hash_valid": True,
        "pending_exists": False,
        "proposal_exists": True,
        "secret_exists": True,
    }
    assert not resume_transport.secret_file.exists()
    assert resume_transport.calls[0] == (
        "browser_navigate",
        {"url": CONVERSATION_URL},
    )
    assert resume_transport.calls[-1] == ("browser_close", {})
    assert all(
        tool
        in {
            "browser_navigate",
            "browser_snapshot",
            "browser_wait_for",
            "browser_close",
        }
        for tool, _arguments in resume_transport.calls
    )
    assert all(
        arguments == {"time": 5}
        for tool, arguments in resume_transport.calls
        if tool == "browser_wait_for"
    )
    assert (interrupted_run / "unapproved-proposal.md").is_file()
    assert not (interrupted_run / "pending-transcript.v1.json").exists()
    persisted_run = b"\n".join(
        path.read_bytes() for path in interrupted_run.rglob("*") if path.is_file()
    ).decode("utf-8", errors="replace")
    assert "Answer now" not in persisted_run
    assert "[ref=e2002]" not in persisted_run
    record_lines = (
        (interrupted_run / "run-record.v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    progress_events = [
        json.loads(line)
        for line in record_lines
        if json.loads(line)["event_type"] == "RESPONSE_WAIT_PROGRESS"
    ]
    assert [
        (
            event["payload"]["elapsed_seconds"],
            event["payload"]["poll_count"],
            event["payload"]["phase"],
        )
        for event in progress_events
    ] == [
        (60, 12, "response_generating"),
        (120, 24, "candidate_stabilizing"),
    ]
    assert all(
        set(event["payload"])
        == {"elapsed_seconds", "phase", "poll_count", "state_sha256"}
        for event in progress_events
    )
    event_count, final_event_hash = workflow._verify_events(
        record_lines,
        interrupted["run_id"],
    )
    assert event_count == len(record_lines)
    assert final_event_hash == json.loads(record_lines[-1])["event_sha256"]
    assert (
        orchestrator.status(
            private_root=root,
            run_id=interrupted["run_id"],
        )["status"]
        == "ADVICE_CAPTURED"
    )


def test_resume_interrupt_retains_latest_checked_conversation_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    waiting, _ask_transport = prepare_interrupted_ask(root, monkeypatch)
    redirected_url = "https://chatgpt.com/c/redirected-response-wait"
    transports: list[ScriptedTransport] = []

    def transport_factory(
        _wrapper: Path,
        secret_file: Path,
        _browser: str,
    ) -> ScriptedTransport:
        transport = ScriptedTransport(
            [snapshot('- status "still generating" [ref=e6100]', url=redirected_url)],
            secret_file=secret_file,
            wait_failure=KeyboardInterrupt(),
            close_probe=close_probe(root),
        )
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", transport_factory)
    exit_code, result = orchestrator.resume(
        private_root=root,
        run_id=waiting["run_id"],
        fake_scenario=None,
    )

    assert exit_code == 0
    assert result["status"] == "WAITING"
    assert result["resubmitted"] is False
    assert len(transports) == 1
    assert transports[0].close_facts == {
        "status": "WAITING",
        "conversation_url": redirected_url,
        "event_type": "WAIT_INTERRUPTED",
        "record_hash_valid": True,
        "pending_exists": True,
        "proposal_exists": False,
        "secret_exists": True,
    }
    state = json.loads(
        (run_dir(root, waiting["run_id"]) / "orchestration-state.v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["conversation_url"] == redirected_url
    assert all(
        tool
        in {
            "browser_navigate",
            "browser_snapshot",
            "browser_wait_for",
            "browser_close",
        }
        for tool, _arguments in transports[0].calls
    )


def test_interrupt_during_resume_finalization_is_not_recorded_as_wait_interrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    waiting, _ask_transport = prepare_interrupted_ask(root, monkeypatch)
    active_run = run_dir(root, waiting["run_id"])
    initial_record = (active_run / "run-record.v1.jsonl").read_text(encoding="utf-8")
    initial_interrupt_count = initial_record.count('"event_type":"WAIT_INTERRUPTED"')
    response = advice_text("Do not convert finalization interruption to waiting.")
    transports: list[ScriptedTransport] = []

    def transport_factory(
        _wrapper: Path,
        secret_file: Path,
        _browser: str,
    ) -> ScriptedTransport:
        transport = ScriptedTransport(
            stable_candidates(response, ref_base=6200),
            secret_file=secret_file,
        )
        transports.append(transport)
        return transport

    def interrupt_finalize(**_arguments: Any) -> tuple[Any, ...]:
        raise KeyboardInterrupt

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", transport_factory)
    monkeypatch.setattr(orchestrator, "_finalize_transcript", interrupt_finalize)

    with pytest.raises(KeyboardInterrupt):
        orchestrator.resume(
            private_root=root,
            run_id=waiting["run_id"],
            fake_scenario=None,
        )

    assert len(transports) == 1
    assert transports[0].closed is True
    record_after = (active_run / "run-record.v1.jsonl").read_text(encoding="utf-8")
    assert record_after.count('"event_type":"WAIT_INTERRUPTED"') == (
        initial_interrupt_count
    )
    assert (active_run / "pending-transcript.v1.json").is_file()
    assert (
        orchestrator.status(private_root=root, run_id=waiting["run_id"])["status"]
        == "WAITING"
    )


@pytest.mark.parametrize(
    ("case", "importance", "expected_code", "expected_status"),
    [
        pytest.param(
            "invalid",
            "ordinary",
            "ADVICE_INVALID",
            "PRO_UNAVAILABLE_FALLBACK",
            id="stable-invalid",
        ),
        pytest.param(
            "ambiguous",
            "gated",
            "RESPONSE_SELECTOR_AMBIGUITY",
            "BLOCKED_PRO_REQUIRED",
            id="stable-ambiguous",
        ),
    ],
)
def test_stable_invalid_or_ambiguous_response_fails_closed_before_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    importance: str,
    expected_code: str,
    expected_status: str,
) -> None:
    root = private_root(tmp_path)
    waiting, _ask_transport = prepare_interrupted_ask(
        root,
        monkeypatch,
        importance=importance,
    )
    waiting_run = run_dir(root, waiting["run_id"])
    pending_before = (waiting_run / "pending-transcript.v1.json").read_bytes()
    response = (
        '{"unique_invalid_payload":"RAW_RESPONSE_INVALID_4cb18151"}'
        if case == "invalid"
        else advice_text("RAW_RESPONSE_AMBIGUOUS_a138f983")
    )
    if case == "invalid":
        candidates = [
            advanced_response_snapshot(response, ref_base=3000 + index * 10)
            for index in range(3)
        ]
    else:
        candidates = [
            ambiguous_response_snapshot(response, ref_base=3300 + index * 30)
            for index in range(3)
        ]
    candidate_digest = orchestrator._response_candidate_digest(
        candidates[0],
        profile_id=ADVANCED_PROFILE_ID,
    )
    transports: list[ScriptedTransport] = []

    def transport_factory(
        _wrapper: Path,
        secret_file: Path,
        _browser: str,
    ) -> ScriptedTransport:
        transport = ScriptedTransport(
            candidates,
            secret_file=secret_file,
            close_probe=close_probe(root),
        )
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", transport_factory)
    exit_code, result = orchestrator.resume(
        private_root=root,
        run_id=waiting["run_id"],
        fake_scenario=None,
    )

    assert exit_code == (4 if importance == "gated" else 0)
    assert result["status"] == expected_status
    assert result["reason_code"] == expected_code
    assert result["resubmitted"] is False
    assert len(transports) == 1
    transport = transports[0]
    assert transport.close_facts == {
        "status": expected_status,
        "conversation_url": CONVERSATION_URL,
        "event_type": "PRO_UNAVAILABLE",
        "record_hash_valid": True,
        "pending_exists": True,
        "proposal_exists": False,
        "secret_exists": True,
    }
    assert not transport.secret_file.exists()
    assert (waiting_run / "pending-transcript.v1.json").read_bytes() == pending_before
    assert not (waiting_run / "unapproved-proposal.md").exists()
    assert not (waiting_run / ".fake-response.txt").exists()
    assert not (waiting_run / ".fake-transcript.json").exists()
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

    persisted = b"\n".join(
        path.read_bytes() for path in waiting_run.rglob("*") if path.is_file()
    ).decode("utf-8", errors="replace")
    assert RAW_REQUEST_MARKER not in persisted
    assert response not in persisted
    assert RAW_SNAPSHOT_MARKER not in persisted
    assert RAW_OUTSIDE_URL not in persisted
    assert "e3000" not in persisted
    assert "e3300" not in persisted
    assert candidate_digest is not None
    assert candidate_digest not in persisted
    urls = orchestrator.URL_PATTERN.findall(persisted)
    assert set(urls) <= {CONVERSATION_URL, "https://chatgpt.com/"}


def test_post_submission_transport_loss_persists_waiting_before_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    install_live_stubs(root, monkeypatch)
    transports: list[ScriptedTransport] = []

    def transport_factory(
        _wrapper: Path,
        secret_file: Path,
        _browser: str,
    ) -> ScriptedTransport:
        transport = ScriptedTransport(
            [
                snapshot(
                    '- button "Send prompt" [ref=e50]', url="https://chatgpt.com/"
                ),
                snapshot('- status "still generating" [ref=e4100]'),
            ],
            secret_file=secret_file,
            wait_failure=orchestrator.TransportUnavailable("MCP_DISCONNECTED"),
            close_probe=close_probe(root),
        )
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", transport_factory)
    exit_code, result = orchestrator.ask(
        private_root=root,
        request_file=private_request(root, "transport-loss-request.txt"),
        importance="ordinary",
        fake_scenario=None,
        parent_run_id=None,
        gap_file=None,
    )

    assert exit_code == 0
    assert result["status"] == "WAITING"
    assert result["resubmit_allowed"] is False
    assert len(transports) == 1
    transport = transports[0]
    assert transport.close_facts == {
        "status": "WAITING",
        "conversation_url": CONVERSATION_URL,
        "event_type": "MCP_RECONNECT_REQUIRED",
        "record_hash_valid": True,
        "pending_exists": True,
        "proposal_exists": False,
        "secret_exists": True,
    }
    assert transport.closed is True
    assert not transport.secret_file.exists()
    assert (
        sum(
            tool == "browser_click" and arguments.get("element") == "send prompt"
            for tool, arguments in transport.calls
        )
        == 1
    )


def test_resume_transport_loss_and_start_failure_remain_waiting_without_resubmit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    waiting, _ask_transport = prepare_interrupted_ask(root, monkeypatch)
    waiting_run = run_dir(root, waiting["run_id"])
    pending_before = (waiting_run / "pending-transcript.v1.json").read_bytes()
    transports: list[ScriptedTransport] = []

    def wait_failure_factory(
        _wrapper: Path,
        secret_file: Path,
        _browser: str,
    ) -> ScriptedTransport:
        transport = ScriptedTransport(
            [snapshot('- status "resume still loading" [ref=e4300]')],
            secret_file=secret_file,
            wait_failure=orchestrator.TransportUnavailable("MCP_DISCONNECTED"),
            close_probe=close_probe(root),
        )
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", wait_failure_factory)
    exit_code, result = orchestrator.resume(
        private_root=root,
        run_id=waiting["run_id"],
        fake_scenario=None,
    )

    assert exit_code == 0
    assert result["status"] == "WAITING"
    assert result["resubmitted"] is False
    assert len(transports) == 1
    transport = transports[0]
    assert transport.close_facts == {
        "status": "WAITING",
        "conversation_url": CONVERSATION_URL,
        "event_type": "WAIT_CONTINUES",
        "record_hash_valid": True,
        "pending_exists": True,
        "proposal_exists": False,
        "secret_exists": True,
    }
    assert not transport.secret_file.exists()
    assert (waiting_run / "pending-transcript.v1.json").read_bytes() == pending_before
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

    startup_secrets: list[Path] = []

    def start_failure_factory(
        _wrapper: Path,
        secret_file: Path,
        _browser: str,
    ) -> ScriptedTransport:
        assert secret_file.is_file()
        startup_secrets.append(secret_file)
        raise orchestrator.TransportUnavailable("MCP_START_FAILED")

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", start_failure_factory)
    second_exit, second_result = orchestrator.resume(
        private_root=root,
        run_id=waiting["run_id"],
        fake_scenario=None,
    )

    assert second_exit == 0
    assert second_result["status"] == "WAITING"
    assert second_result["resubmitted"] is False
    assert len(startup_secrets) == 1
    assert not startup_secrets[0].exists()
    assert (waiting_run / "pending-transcript.v1.json").read_bytes() == pending_before
    _, verified = orchestrator._load_state(root / "chatgpt-pro-runs", waiting["run_id"])
    assert verified["status"] == "WAITING"
    final_event = json.loads(
        (waiting_run / "run-record.v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[-1]
    )
    assert final_event["event_type"] == "WAIT_CONTINUES"
    assert final_event["payload"]["reason_code"] == "MCP_START_FAILED"
    assert final_event["payload"]["resubmitted"] is False


@pytest.mark.parametrize(
    ("response_snapshot", "expected_code"),
    [
        pytest.param(
            snapshot('- button "Log in" [ref=e90]'),
            "STOP_LOGIN",
            id="authentication",
        ),
        pytest.param(
            snapshot('- alert "CAPTCHA" [ref=e90]'),
            "STOP_CAPTCHA",
            id="captcha",
        ),
        pytest.param(
            snapshot('- alert "Too many requests" [ref=e90]'),
            "STOP_RATE_LIMIT",
            id="rate-limit",
        ),
        pytest.param(
            snapshot('- button "Choose an account" [ref=e90]'),
            "STOP_ACCOUNT_AMBIGUITY",
            id="account-ambiguity",
        ),
        pytest.param(
            snapshot("- response candidate", url="https://chatgpt.com.evil.example/"),
            "ORIGIN_MISMATCH",
            id="origin-mismatch",
        ),
    ],
)
def test_known_post_submission_stop_is_durable_before_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response_snapshot: str,
    expected_code: str,
) -> None:
    root = private_root(tmp_path)
    install_live_stubs(root, monkeypatch)
    transports: list[ScriptedTransport] = []

    def transport_factory(
        _wrapper: Path,
        secret_file: Path,
        _browser: str,
    ) -> ScriptedTransport:
        transport = ScriptedTransport(
            [
                snapshot(
                    '- button "Send prompt" [ref=e50]', url="https://chatgpt.com/"
                ),
                response_snapshot,
            ],
            secret_file=secret_file,
            close_probe=close_probe(root),
        )
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", transport_factory)
    exit_code, result = orchestrator.ask(
        private_root=root,
        request_file=private_request(root, f"stop-{expected_code}.txt"),
        importance="ordinary",
        fake_scenario=None,
        parent_run_id=None,
        gap_file=None,
    )

    assert exit_code == 0
    assert result["status"] == "PRO_UNAVAILABLE_FALLBACK"
    assert result["reason_code"] == expected_code
    assert result["submission_attempted"] is True
    assert len(transports) == 1
    transport = transports[0]
    assert transport.close_facts["status"] == "PRO_UNAVAILABLE_FALLBACK"
    assert transport.close_facts["event_type"] == "PRO_UNAVAILABLE"
    assert transport.close_facts["record_hash_valid"] is True
    assert transport.close_facts["proposal_exists"] is False
    assert transport.close_facts["secret_exists"] is True
    assert transport.closed is True
    assert not transport.secret_file.exists()
    assert transport.wait_calls == 0
    assert (
        sum(
            tool == "browser_click" and arguments.get("element") == "send prompt"
            for tool, arguments in transport.calls
        )
        == 1
    )
