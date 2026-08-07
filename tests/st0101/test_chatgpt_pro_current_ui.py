"""Deterministic evidence for the approved ST-0101 current Pro UI handoff."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from scripts import chatgpt_pro_orchestrator as orchestrator
from scripts import chatgpt_pro_workflow as workflow


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPOSITORY_ROOT / "changes/st-0101/chatgpt-pro-known-ui.v1.json"
ADVANCED_PROFILE_ID = "gpt-5.6-sol-pro-advanced-v1"
MODEL_LABELS = ["GPT-5.6 Sol", "GPT-5.5", "GPT-5.3", "o3"]
EFFORT_LABELS = ["Instant 5.5", "Medium", "High", "Extra High", "Pro"]


class ScriptedTransport:
    """One inert transport serving sanitized snapshots in a fixed order."""

    mode = "LIVE"

    def __init__(
        self,
        snapshots: list[str | Exception],
        *,
        trace: list[tuple[str, Any, Any]] | None = None,
    ) -> None:
        self.snapshots = list(snapshots)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.trace = [] if trace is None else trace
        self.closed = False

    def call(self, tool: str, arguments: dict[str, Any]) -> str:
        copied = dict(arguments)
        self.calls.append((tool, copied))
        self.trace.append(("tool", tool, copied))
        if tool == "browser_snapshot":
            if not self.snapshots:
                raise AssertionError("unexpected browser snapshot")
            result = self.snapshots.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return ""

    def close(self) -> None:
        self.closed = True


def snapshot(*lines: str, url: str = "https://chatgpt.com/") -> str:
    return "\n".join((f"- Page URL: {url}", *lines))


def landing(*, button_ref: str, composer_ref: str) -> str:
    return snapshot(
        f'- button "Pro" [ref={button_ref}]',
        f'- textbox "Chat with ChatGPT" [ref={composer_ref}]',
    )


def compact_menu() -> str:
    return snapshot(
        '- button "Pro" [ref=e3]',
        '- menu "Pro" [ref=e4]',
        '- menuitem "Show advanced options" [ref=e5]',
        '- menuitem "Power" [ref=e6]',
    )


def expanded_menu(*, offset: int = 6) -> str:
    return snapshot(
        f'- button "Pro" [ref=e{offset}]',
        f'- menu "Pro" [ref=e{offset + 1}]',
        f'- menuitem "Show compact options" [ref=e{offset + 2}]',
        f'- menuitem "Model GPT-5.6 Sol" [ref=e{offset + 3}]',
        f'- menuitem "Effort Pro" [ref=e{offset + 4}]',
        f'- menuitem "Power" [ref=e{offset + 5}]',
    )


def radio_menu(
    labels: list[str],
    *,
    top_ref: str,
    first_ref: int,
    checked_index: int | None,
    roles: list[str] | None = None,
) -> str:
    actual_roles = ["menuitemradio"] * len(labels) if roles is None else roles
    lines = [f'- button "Pro" [ref={top_ref}]']
    for index, (label, role) in enumerate(zip(labels, actual_roles, strict=True)):
        checked = " [checked]" if checked_index == index else ""
        lines.append(f'- {role} "{label}"{checked} [ref=e{first_ref + index}]')
    return snapshot(*lines)


def valid_model_menu() -> str:
    return radio_menu(
        MODEL_LABELS,
        top_ref="e11",
        first_ref=12,
        checked_index=0,
    )


def valid_effort_menu() -> str:
    return radio_menu(
        EFFORT_LABELS,
        top_ref="e30",
        first_ref=31,
        checked_index=4,
    )


def advanced_pre_type_snapshots(
    *,
    menu_snapshot: str | None = None,
    model_snapshot: str | None = None,
    effort_snapshot: str | None = None,
    final_snapshot: str | None = None,
) -> list[str]:
    return [
        landing(button_ref="e1", composer_ref="e2"),
        compact_menu() if menu_snapshot is None else menu_snapshot,
        expanded_menu(),
        valid_model_menu() if model_snapshot is None else model_snapshot,
        landing(button_ref="e20", composer_ref="e21"),
        expanded_menu(offset=22),
        valid_effort_menu() if effort_snapshot is None else effort_snapshot,
        landing(button_ref="e40", composer_ref="e41")
        if final_snapshot is None
        else final_snapshot,
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
) -> dict[str, Any]:
    return {
        "state": state,
        "url": "https://chatgpt.com/c/current-ui",
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
        "schema_version": 1,
        "profile_id": ADVANCED_PROFILE_ID,
        "observations": [
            observation("landing", refs={"model_picker": ["e1"]}),
            observation(
                "model_menu",
                option_labels=MODEL_LABELS,
                refs={"target_model": ["e2"]},
            ),
            observation(
                "effort_menu",
                model_label="GPT-5.6 Sol",
                option_labels=EFFORT_LABELS,
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
                refs={"assistant_response": ["e6"]},
                generating=False,
                response_complete=True,
            ),
        ],
    }


def advanced_inspection_result() -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    str,
    dict[str, Any],
    dict[str, Any],
]:
    contract = workflow._load_contract(CONTRACT_PATH)
    profile = contract["profiles"][ADVANCED_PROFILE_ID]
    ready = orchestrator._base_observation(
        "ready",
        "https://chatgpt.com/",
        model_label=profile["target_model"],
        effort_label=profile["target_effort"],
        refs={"composer": ["e41"]},
    )
    return contract, [], ADVANCED_PROFILE_ID, profile, ready


def test_advanced_contract_is_exact_and_checked_targets_are_not_action_targets() -> (
    None
):
    contract = workflow._load_contract(CONTRACT_PATH)

    assert contract["profiles"][ADVANCED_PROFILE_ID] == (
        workflow.EXPECTED_ADVANCED_PROFILE
    )
    actions = workflow.validate_transcript(advanced_transcript(), contract)
    assert [action["tool"] for action in actions] == [
        "browser_click",
        "browser_type",
        "browser_click",
        "browser_wait_for",
        "capture_response",
    ]
    assert actions[1]["arguments"] == {
        "element": "ChatGPT composer",
        "target": "e4",
        "text": "RAOS_CHATGPT_PROMPT",
        "submit": False,
    }
    assert actions[2]["arguments"] == {
        "element": "send prompt",
        "target": "e5",
    }
    click_targets = {
        action["arguments"]["target"]
        for action in actions
        if action["tool"] == "browser_click"
    }
    assert click_targets.isdisjoint({"e2", "e3"})


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "second-advanced",
        "wrong-mode",
        "wrong-states",
        "model-order",
        "model-target",
        "effort-order",
        "extra-field",
    ],
)
def test_advanced_contract_drift_is_refused(
    tmp_path: Path,
    mutation: str,
) -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    profile = contract["profiles"][ADVANCED_PROFILE_ID]
    if mutation == "missing":
        del contract["profiles"][ADVANCED_PROFILE_ID]
    elif mutation == "second-advanced":
        contract["profiles"]["unexpected-advanced-v1"] = copy.deepcopy(profile)
    elif mutation == "wrong-mode":
        profile["effort_mode"] = "split"
    elif mutation == "wrong-states":
        profile["states"].remove("send_ready")
    elif mutation == "model-order":
        profile["model_option_labels"][0:2] = reversed(
            profile["model_option_labels"][0:2]
        )
    elif mutation == "model-target":
        profile["target_model"] = "GPT-5.5"
    elif mutation == "effort-order":
        profile["effort_option_labels"][-2:] = reversed(
            profile["effort_option_labels"][-2:]
        )
    elif mutation == "extra-field":
        profile["checked"] = True
    path = tmp_path / f"{mutation}.json"
    path.write_text(json.dumps(contract), encoding="utf-8")

    with pytest.raises(workflow.WorkflowRefusal) as captured:
        workflow._load_contract(path)

    assert captured.value.code == "CONTRACT_INVALID"


def test_current_advanced_happy_path_is_exact_and_never_clicks_checked_targets() -> (
    None
):
    transport = ScriptedTransport(advanced_pre_type_snapshots())

    _contract, observations, profile_id, profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert profile["target_model"] == "GPT-5.6 Sol"
    assert profile["target_effort"] == "Pro"
    assert [item["state"] for item in observations] == [
        "landing",
        "model_menu",
        "effort_menu",
        "ready",
    ]
    assert ready["refs"] == {"composer": ["e41"]}
    assert transport.calls == [
        ("browser_navigate", {"url": "https://chatgpt.com/"}),
        ("browser_snapshot", {}),
        ("browser_click", {"element": "model picker", "target": "e1"}),
        ("browser_snapshot", {}),
        (
            "browser_click",
            {"element": "show advanced options", "target": "e5"},
        ),
        ("browser_snapshot", {}),
        ("browser_click", {"element": "advanced model", "target": "e9"}),
        ("browser_snapshot", {}),
        ("browser_click", {"element": "Pro menu", "target": "e11"}),
        ("browser_snapshot", {}),
        ("browser_click", {"element": "model picker", "target": "e20"}),
        ("browser_snapshot", {}),
        ("browser_click", {"element": "advanced effort", "target": "e26"}),
        ("browser_snapshot", {}),
        ("browser_click", {"element": "Pro menu", "target": "e30"}),
        ("browser_snapshot", {}),
    ]
    click_targets = {
        arguments["target"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    }
    assert click_targets.isdisjoint({"e12", "e35"})
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "duplicate",
        "reordered",
        "extra",
        "wrong-role",
        "wrong-case",
        "unchecked",
        "wrong-checked",
        "checked-ref-collision",
    ],
)
def test_advanced_model_options_fail_closed_before_input(case: str) -> None:
    labels = list(MODEL_LABELS)
    roles = ["menuitemradio"] * len(labels)
    checked_index: int | None = 0
    top_ref = "e11"
    if case == "missing":
        labels.pop(1)
        roles.pop(1)
    elif case == "duplicate":
        labels[1] = labels[0]
    elif case == "reordered":
        labels[1], labels[2] = labels[2], labels[1]
    elif case == "extra":
        labels.append("GPT-4o")
        roles.append("menuitemradio")
    elif case == "wrong-role":
        roles[1] = "menuitem"
    elif case == "wrong-case":
        labels[1] = "gpt-5.5"
    elif case == "unchecked":
        checked_index = None
    elif case == "wrong-checked":
        checked_index = 1
    elif case == "checked-ref-collision":
        top_ref = "e12"
    model_snapshot = radio_menu(
        labels,
        top_ref=top_ref,
        first_ref=12,
        checked_index=checked_index,
        roles=roles,
    )
    transport = ScriptedTransport(
        advanced_pre_type_snapshots(model_snapshot=model_snapshot)
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == "MODEL_OPTIONS_AMBIGUOUS"
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)
    assert not any(
        tool == "browser_click" and arguments.get("target") == "e12"
        for tool, arguments in transport.calls
    )


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "duplicate",
        "reordered",
        "extra",
        "wrong-role",
        "wrong-case",
        "target-not-last",
        "unchecked",
        "wrong-checked",
        "checked-ref-collision",
    ],
)
def test_advanced_effort_options_fail_closed_before_input(case: str) -> None:
    labels = list(EFFORT_LABELS)
    roles = ["menuitemradio"] * len(labels)
    checked_index: int | None = 4
    top_ref = "e30"
    if case == "missing":
        labels.pop(1)
        roles.pop(1)
        checked_index = 3
    elif case == "duplicate":
        labels[1] = labels[0]
    elif case == "reordered":
        labels[1], labels[2] = labels[2], labels[1]
    elif case == "extra":
        labels.append("Ultra")
        roles.append("menuitemradio")
    elif case == "wrong-role":
        roles[2] = "menuitem"
    elif case == "wrong-case":
        labels[1] = "medium"
    elif case == "target-not-last":
        labels[-2], labels[-1] = labels[-1], labels[-2]
        checked_index = 3
    elif case == "unchecked":
        checked_index = None
    elif case == "wrong-checked":
        checked_index = 2
    elif case == "checked-ref-collision":
        top_ref = "e35"
    effort_snapshot = radio_menu(
        labels,
        top_ref=top_ref,
        first_ref=31,
        checked_index=checked_index,
        roles=roles,
    )
    transport = ScriptedTransport(
        advanced_pre_type_snapshots(effort_snapshot=effort_snapshot)
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == "EFFORT_OPTIONS_AMBIGUOUS"
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)
    click_targets = {
        arguments["target"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    }
    assert click_targets.isdisjoint({"e12", "e35"})


@pytest.mark.parametrize(
    "menu_snapshot",
    [
        pytest.param(
            snapshot(
                '- button "Pro" [ref=e3]',
                '- menu "Pro" [ref=e4]',
            ),
            id="missing-state-toggle",
        ),
        pytest.param(
            snapshot(
                '- button "Pro" [ref=e3]',
                '- menu "Pro" [ref=e4]',
                '- menuitem "Show advanced options" [ref=e5]',
                '- menuitem "Show advanced options" [ref=e6]',
            ),
            id="duplicate-expand",
        ),
        pytest.param(
            snapshot(
                '- button "Pro" [ref=e3]',
                '- menu "Pro" [ref=e4]',
                '- menuitem "Show advanced options" [ref=e5]',
                '- menuitem "Show compact options" [ref=e6]',
            ),
            id="simultaneous-expand-compact",
        ),
    ],
)
def test_advanced_expansion_state_must_be_unique(menu_snapshot: str) -> None:
    transport = ScriptedTransport(
        [landing(button_ref="e1", composer_ref="e2"), menu_snapshot]
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code in {
        "MODEL_OPTIONS_AMBIGUOUS",
        "SELECTOR_AMBIGUITY",
    }
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


def test_unrelated_power_menuitem_is_allowed_but_not_required() -> None:
    compact_elements = orchestrator._elements(compact_menu())
    expanded_elements = orchestrator._elements(expanded_menu())

    compact_view, expand_ref, model_ref, effort_ref = orchestrator._advanced_menu_view(
        compact_elements
    )
    assert (compact_view, expand_ref, model_ref, effort_ref) == (
        "compact",
        "e5",
        None,
        None,
    )
    expanded_view, _expand_ref, model_ref, effort_ref = (
        orchestrator._advanced_menu_view(expanded_elements)
    )
    assert (expanded_view, model_ref, effort_ref) == ("expanded", "e9", "e10")

    without_power = [element for element in expanded_elements if element[1] != "Power"]
    assert orchestrator._advanced_menu_view(without_power)[0] == "expanded"


def test_legacy_menu_container_is_not_an_advanced_profile_marker() -> None:
    elements = orchestrator._elements(
        snapshot(
            '- button "Pro" [ref=e1]',
            '- menu "Pro" [ref=e2]',
            '- menuitem "Pro" [ref=e3]',
        )
    )
    contract = workflow._load_contract(CONTRACT_PATH)

    assert orchestrator._advanced_ui_present(elements) is False
    profile_id, profile, target_ref = orchestrator._known_profile(elements, contract)

    assert profile_id == "pro-extended-split-v1"
    assert profile["effort_mode"] == "split"
    assert target_ref == "e3"


@pytest.mark.parametrize(
    ("final_snapshot", "expected_code"),
    [
        pytest.param(
            landing(
                button_ref="e40",
                composer_ref="e41",
            ).replace("https://chatgpt.com/", "https://chatgpt.com.evil.example/"),
            "ORIGIN_MISMATCH",
            id="origin",
        ),
        pytest.param(
            snapshot("- Too many requests"),
            "STOP_RATE_LIMIT",
            id="stop-state",
        ),
        pytest.param(
            snapshot('- textbox "Chat with ChatGPT" [ref=e41]'),
            "SELECTOR_AMBIGUITY",
            id="missing-pro-button",
        ),
        pytest.param(
            snapshot(
                '- button "Pro" [ref=e40]',
                '- button "Pro" [ref=e42]',
                '- textbox "Chat with ChatGPT" [ref=e41]',
            ),
            "SELECTOR_AMBIGUITY",
            id="duplicate-pro-button",
        ),
        pytest.param(
            snapshot('- button "Pro" [ref=e40]'),
            "SELECTOR_AMBIGUITY",
            id="missing-composer",
        ),
        pytest.param(
            snapshot(
                '- button "Pro" [ref=e40]',
                '- textbox "Chat with ChatGPT" [ref=e41]',
                '- textbox "Chat with ChatGPT" [ref=e42]',
            ),
            "SELECTOR_AMBIGUITY",
            id="duplicate-composer",
        ),
        pytest.param(
            snapshot(
                '- button "Pro" [ref=e40]',
                '- textbox "CHAT WITH CHATGPT" [ref=e41]',
            ),
            "SELECTOR_AMBIGUITY",
            id="wrong-case-composer",
        ),
        pytest.param(
            snapshot(
                '- button "PRO" [ref=e40]',
                '- textbox "Chat with ChatGPT" [ref=e41]',
            ),
            "SELECTOR_AMBIGUITY",
            id="wrong-case-pro-button",
        ),
    ],
)
def test_advanced_final_landing_is_revalidated_before_type(
    final_snapshot: str,
    expected_code: str,
) -> None:
    transport = ScriptedTransport(
        advanced_pre_type_snapshots(final_snapshot=final_snapshot)
    )

    with pytest.raises(
        (orchestrator.OrchestrationRefusal, workflow.WorkflowRefusal)
    ) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == expected_code
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


def test_advanced_post_type_send_prompt_and_intent_order_are_exact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace: list[tuple[str, Any, Any]] = []
    response = json.dumps(
        {
            "schema": "PRO_ADVICE_V1",
            "summary": "Keep the exact current UI boundary.",
            "material_delta": True,
            "open_gaps": ["One named gap."],
            "evidence_refs": ["ST-0101 current UI fixture"],
            "recommendations": ["Reconcile with canonical evidence."],
            "authority": "UNAPPROVED_ADVICE",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    response_snapshot = snapshot(
        '- heading "ChatGPT said:" [ref=e60]',
        "- generic [ref=e61]:",
        "  - generic [ref=e62]:",
        "    - paragraph [ref=e63]:",
        f"      - text: {json.dumps(response)}",
        url="https://chatgpt.com/c/current-ui",
    )
    transport = ScriptedTransport(
        [
            *advanced_pre_type_snapshots(),
            snapshot('- button "Send prompt" [ref=e50]'),
            response_snapshot,
            response_snapshot,
            response_snapshot,
        ],
        trace=trace,
    )
    captured: dict[str, Any] = {}

    def append_event(
        _record_path: Path,
        _run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> str:
        trace.append(("event", event_type, dict(payload)))
        return "a" * 64

    def finalize_transcript(**arguments: Any) -> tuple[Any, ...]:
        captured.update(arguments)
        return (
            {"response_sha256": "b" * 64},
            {"authority": "UNAPPROVED_ADVICE"},
            "c" * 64,
            "d" * 64,
        )

    monkeypatch.setattr(workflow, "_append_event", append_event)
    monkeypatch.setattr(orchestrator, "_finalize_transcript", finalize_transcript)

    result = orchestrator._live_capture(
        prepared={
            "record_path": str(tmp_path / "record.jsonl"),
            "run_id": "20260805T000000Z-aaaaaaaaaaaa",
            "prompt_sha256": "e" * 64,
        },
        transport=transport,
        interactive_auth_wait_seconds=0,
    )

    assert result[1]["authority"] == "UNAPPROVED_ADVICE"
    type_index = next(
        index
        for index, item in enumerate(trace)
        if item[0:2] == ("tool", "browser_type")
    )
    intent_index = next(
        index
        for index, item in enumerate(trace)
        if item[0:2] == ("event", "SUBMISSION_INTENT_RECORDED")
    )
    send_index = next(
        index
        for index, item in enumerate(trace)
        if item[0:2] == ("tool", "browser_click")
        and item[2].get("element") == "send prompt"
    )
    assert trace[type_index][2] == {
        "element": "ChatGPT composer",
        "target": "e41",
        "text": "RAOS_CHATGPT_PROMPT",
        "submit": False,
    }
    assert trace[type_index + 1] == ("tool", "browser_snapshot", {})
    assert intent_index == type_index + 2
    assert send_index == intent_index + 1
    assert trace[send_index][2] == {"element": "send prompt", "target": "e50"}
    assert "DO NOT LEAK RAW REQUEST" not in json.dumps(trace)
    assert [
        item["state"] for item in captured["transcript"]["observations"]
    ] == workflow.EXPECTED_ADVANCED_PROFILE["states"]
    ready, send_ready = captured["transcript"]["observations"][3:5]
    assert ready["refs"] == {"composer": ["e41"]}
    assert send_ready["refs"] == {"send": ["e50"]}
    assert captured["transcript"]["observations"][-1]["refs"] == {
        "assistant_response": ["e60"]
    }
    assert captured["response"] == response
    click_targets = {
        item[2]["target"] for item in trace if item[0:2] == ("tool", "browser_click")
    }
    assert click_targets.isdisjoint({"e12", "e35"})
    assert transport.snapshots == []


@pytest.mark.parametrize(
    ("post_type_result", "expected_code"),
    [
        pytest.param(snapshot("- Initial tree"), "SELECTOR_AMBIGUITY", id="missing"),
        pytest.param(
            snapshot(
                '- button "Send prompt" [ref=e50]',
                '- button "Send prompt" [ref=e51]',
            ),
            "SELECTOR_AMBIGUITY",
            id="duplicate",
        ),
        pytest.param(
            snapshot('- button "SEND PROMPT" [ref=e50]'),
            "SELECTOR_AMBIGUITY",
            id="wrong-case",
        ),
        pytest.param(
            snapshot('- menuitem "Send prompt" [ref=e50]'),
            "SELECTOR_AMBIGUITY",
            id="wrong-role",
        ),
        pytest.param(
            snapshot("- Too many requests"),
            "STOP_RATE_LIMIT",
            id="stop-state",
        ),
        pytest.param(
            snapshot(
                '- button "Send prompt" [ref=e50]',
                url="https://chatgpt.com.evil.example/",
            ),
            "ORIGIN_MISMATCH",
            id="origin-drift",
        ),
        pytest.param(
            orchestrator.TransportUnavailable("MCP_DISCONNECTED"),
            "MCP_DISCONNECTED",
            id="disconnect",
        ),
    ],
)
def test_post_type_send_failures_are_unavailable_without_intent_or_send_click(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    post_type_result: str | Exception,
    expected_code: str,
) -> None:
    transport = ScriptedTransport([post_type_result])
    events: list[str] = []
    monkeypatch.setattr(
        orchestrator,
        "_inspect_live_pre_submission_ui",
        lambda *_args, **_kwargs: advanced_inspection_result(),
    )
    monkeypatch.setattr(
        workflow,
        "_append_event",
        lambda _path, _run_id, event_type, _payload: events.append(event_type),
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._live_capture(
            prepared={
                "record_path": str(tmp_path / "record.jsonl"),
                "run_id": "20260805T000000Z-aaaaaaaaaaaa",
                "prompt_sha256": "e" * 64,
            },
            transport=transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == expected_code
    assert transport.calls == [
        (
            "browser_type",
            {
                "element": "ChatGPT composer",
                "target": "e41",
                "text": "RAOS_CHATGPT_PROMPT",
                "submit": False,
            },
        ),
        ("browser_snapshot", {}),
    ]
    assert events == []
    assert not any(
        tool == "browser_click" and arguments.get("element") == "send prompt"
        for tool, arguments in transport.calls
    )


def test_ask_persists_post_type_send_failure_as_unsubmitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / ".secrets"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
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
    request_root = root / "chatgpt-pro-requests"
    request_root.chmod(0o700)
    request = request_root / "current-ui.txt"
    request.write_text("Review the approved current UI boundary.", encoding="utf-8")
    request.chmod(0o600)
    transports: list[ScriptedTransport] = []

    def transport_factory(
        _wrapper: Path,
        _secret_file: Path,
        browser: str,
    ) -> ScriptedTransport:
        assert browser == "edge"
        transport = ScriptedTransport([snapshot("- Initial tree")])
        transports.append(transport)
        return transport

    monkeypatch.setattr(
        orchestrator,
        "_inspect_live_pre_submission_ui",
        lambda *_args, **_kwargs: advanced_inspection_result(),
    )
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", transport_factory)

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
    assert result["status"] == "PRO_UNAVAILABLE_FALLBACK"
    assert result["reason_code"] == "SELECTOR_AMBIGUITY"
    assert result["submission_attempted"] is False
    assert len(transports) == 1
    assert not any(tool == "browser_click" for tool, _arguments in transports[0].calls)
    run_dir = root / "chatgpt-pro-runs" / result["run_id"]
    state = json.loads(
        (run_dir / "orchestration-state.v1.json").read_text(encoding="utf-8")
    )
    assert state["submission_attempted"] is False
    events = [
        json.loads(line)
        for line in (run_dir / "run-record.v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert not any(
        event["event_type"] == "SUBMISSION_INTENT_RECORDED" for event in events
    )
