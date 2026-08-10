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
    expanded_snapshot: str | None = None,
    final_snapshot: str | None = None,
) -> list[str]:
    return [
        landing(button_ref="e1", composer_ref="e2"),
        compact_menu() if menu_snapshot is None else menu_snapshot,
        expanded_menu() if expanded_snapshot is None else expanded_snapshot,
        landing(button_ref="e40", composer_ref="e41")
        if final_snapshot is None
        else final_snapshot,
    ]


def settle_exhaustion(snapshot_value: str) -> list[str]:
    return [
        snapshot_value
        for _ in range(orchestrator.PRE_SUBMISSION_SETTLE_ADDITIONAL_OBSERVATIONS + 1)
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
            ),
            observation(
                "effort_menu",
                model_label="GPT-5.6 Sol",
                option_labels=EFFORT_LABELS,
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


def test_predecessor_advanced_evidence_refs_remain_read_compatible() -> None:
    contract = workflow._load_contract(CONTRACT_PATH)
    transcript = advanced_transcript()
    transcript["observations"][1]["refs"] = {"target_model": ["e90"]}
    transcript["observations"][2]["refs"] = {"target_effort": ["e91"]}

    actions = workflow.validate_transcript(transcript, contract)

    click_targets = {
        action["arguments"].get("target")
        for action in actions
        if action["tool"] == "browser_click"
    }
    assert click_targets.isdisjoint({"e90", "e91"})


@pytest.mark.parametrize(
    ("observation_index", "refs"),
    [
        (1, {"target_model": []}),
        (1, {"target_model": ["e90", "e91"]}),
        (1, {"unexpected": ["e90"]}),
        (2, {"target_effort": ["invalid"]}),
        (2, {"target_effort": ["e91"], "unexpected": ["e92"]}),
    ],
)
def test_advanced_evidence_ref_compatibility_shape_is_closed(
    observation_index: int,
    refs: dict[str, list[str]],
) -> None:
    contract = workflow._load_contract(CONTRACT_PATH)
    transcript = advanced_transcript()
    transcript["observations"][observation_index]["refs"] = refs

    with pytest.raises(workflow.WorkflowRefusal, match="SELECTOR_AMBIGUITY"):
        workflow.validate_transcript(transcript, contract)


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
        ("browser_click", {"element": "Pro menu", "target": "e6"}),
        ("browser_snapshot", {}),
    ]
    click_targets = {
        arguments["target"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    }
    assert click_targets.isdisjoint({"e9", "e10"})
    assert not any(tool == "browser_wait_for" for tool, _arguments in transport.calls)
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


def test_already_expanded_advanced_menu_skips_expansion_and_child_menus() -> None:
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            expanded_menu(offset=3),
            landing(button_ref="e20", composer_ref="e21"),
        ]
    )

    _contract, observations, profile_id, _profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert [item["state"] for item in observations] == [
        "landing",
        "model_menu",
        "effort_menu",
        "ready",
    ]
    assert ready["refs"] == {"composer": ["e21"]}
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "Pro menu"]


def test_delayed_advanced_menu_is_not_misclassified_as_legacy() -> None:
    transitional = snapshot(
        '- button "Pro" [ref=e3]',
        '- menu "Pro" [ref=e4]',
        '- menuitem "Pro" [ref=e5]',
    )
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            transitional,
            compact_menu(),
            expanded_menu(),
            landing(button_ref="e40", composer_ref="e41"),
        ]
    )

    _contract, observations, profile_id, _profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert [item["state"] for item in observations] == [
        "landing",
        "model_menu",
        "effort_menu",
        "ready",
    ]
    assert ready["refs"] == {"composer": ["e41"]}
    assert sum(tool == "browser_wait_for" for tool, _arguments in transport.calls) == 1
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "show advanced options", "Pro menu"]


def test_proven_advanced_landing_never_reclassifies_stable_legacy_menu() -> None:
    legacy_menu = snapshot('- menuitem "Pro" [ref=e3]')
    transport = ScriptedTransport(
        [
            snapshot(
                '- button "Pro" [ref=e1]',
                '- textbox "Ask anything" [ref=e2]',
            ),
            *settle_exhaustion(legacy_menu),
            snapshot(
                '- menuitem "Pro" [ref=e4]',
                '- button "Effort" [ref=e5]',
            ),
            snapshot(
                '- menuitem "Standard" [ref=e6]',
                '- menuitem "Extended" [ref=e7]',
            ),
            snapshot(
                '- button "Pro" [ref=e8]',
                '- textbox "Ask anything" [ref=e9]',
                '- button "Send" [ref=e10]',
            ),
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == "ADVANCED_PRO_BUTTON_INVALID"
    assert captured.value.phase == "pro_menu"
    assert sum(tool == "browser_wait_for" for tool, _arguments in transport.calls) == 12
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker"]
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


def test_proven_advanced_landing_classifies_stable_unknown_shell_as_advanced() -> None:
    ambiguous_shell = snapshot(
        '- button "Pro" [ref=e3]',
        '- menu "Pro" [ref=e4]',
        '- menuitem "Pro" [ref=e5]',
    )
    transport = ScriptedTransport(
        [
            snapshot(
                '- button "Pro" [ref=e1]',
                '- textbox "Ask anything" [ref=e2]',
            ),
            *settle_exhaustion(ambiguous_shell),
            snapshot(
                '- menuitem "Pro" [ref=e6]',
                '- button "Effort" [ref=e7]',
            ),
            snapshot(
                '- menuitem "Standard" [ref=e8]',
                '- menuitem "Extended" [ref=e9]',
            ),
            snapshot(
                '- button "Pro" [ref=e10]',
                '- textbox "Ask anything" [ref=e11]',
                '- button "Send" [ref=e12]',
            ),
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == "ADVANCED_MENU_UNRECOGNIZED"
    assert captured.value.phase == "pro_menu"
    assert sum(tool == "browser_wait_for" for tool, _arguments in transport.calls) == 12
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker"]
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


def test_delayed_advanced_menuitem_pro_frame_never_triggers_legacy_click() -> None:
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            snapshot('- menuitem "Pro" [ref=e3]'),
            compact_menu(),
            expanded_menu(),
            landing(button_ref="e40", composer_ref="e41"),
        ]
    )

    _contract, observations, profile_id, _profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert observations[-1]["state"] == "ready"
    assert ready["refs"] == {"composer": ["e41"]}
    assert sum(tool == "browser_wait_for" for tool, _arguments in transport.calls) == 1
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "show advanced options", "Pro menu"]


def test_unrelated_landing_menu_cannot_disable_advanced_transition_guard() -> None:
    advanced_landing_with_sidebar = snapshot(
        '- button "Pro" [ref=e1]',
        '- textbox "Chat with ChatGPT" [ref=e2]',
        '- navigation "Sidebar" [ref=e80]:',
        '  - menuitem "History" [ref=e81]',
    )
    transport = ScriptedTransport(
        [
            advanced_landing_with_sidebar,
            snapshot('- menuitem "Pro" [ref=e3]'),
            compact_menu(),
            expanded_menu(),
            landing(button_ref="e40", composer_ref="e41"),
        ]
    )

    _contract, observations, profile_id, _profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert observations[-1]["state"] == "ready"
    assert ready["refs"] == {"composer": ["e41"]}
    assert sum(tool == "browser_wait_for" for tool, _arguments in transport.calls) == 1
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "show advanced options", "Pro menu"]


CLICKED_MENU_CONTROLS = {
    "button": ("button", "Pro", "e6", "expanded"),
    "expand": ("menuitem", "Show advanced options", "e5", "compact"),
}

ADVANCED_LANDING_INERT_COPY_KINDS = (
    "text",
    "statictext",
    "generic",
    "heading",
    "description",
    "wrong-role",
    "wrong-case",
    "padded-label",
)
ADVANCED_LANDING_DEFECTS = (
    "missing",
    "wrong-role-only",
    "wrong-role-case-only",
    "wrong-case-only",
    "padded-label-only",
    "disabled",
    "ref-free-only",
    "malformed-ref-only",
    "multiple-ref",
    "multiple-ref-malformed-after",
    "multiple-ref-malformed-before",
    "duplicate-actionable",
    "duplicate-ref-free",
    "duplicate-malformed",
    "ref-collision",
)


def clicked_control_surface(control: str) -> str:
    return (
        compact_menu()
        if CLICKED_MENU_CONTROLS[control][3] == "compact"
        else expanded_menu()
    )


def invalid_clicked_control(control: str, mutation: str) -> str:
    lines = clicked_control_surface(control).splitlines()[1:]
    role, label, ref, _surface = CLICKED_MENU_CONTROLS[control]
    exact = f'- {role} "{label}" [ref={ref}]'
    index = lines.index(exact)
    if mutation == "missing":
        lines.pop(index)
    elif mutation == "duplicate-actionable":
        lines.append(f'- {role} "{label}" [ref=e90]')
    elif mutation == "duplicate-ref-free":
        lines.append(f'- {role} "{label}"')
    elif mutation == "duplicate-malformed":
        lines.append(f'- {role} "{label}" [ref=invalid]')
    elif mutation == "wrong-case-only":
        lines[index] = f'- {role} "{label.swapcase()}" [ref={ref}]'
    elif mutation == "wrong-role-only":
        lines[index] = f'- link "{label}" [ref={ref}]'
    elif mutation == "padded-label-only":
        lines[index] = f'- {role} " {label} " [ref={ref}]'
    elif mutation == "near-label-only":
        lines[index] = f'- {role} "{label} option" [ref={ref}]'
    elif mutation == "ref-free-only":
        lines[index] = f'- {role} "{label}"'
    elif mutation == "malformed-ref-only":
        lines[index] = f'- {role} "{label}" [ref=invalid]'
    elif mutation == "disabled":
        lines[index] = f'- {role} "{label}" [disabled] [ref={ref}]'
    elif mutation == "ref-collision":
        if control != "expand":
            raise AssertionError(mutation)
        lines[index] = f'- {role} "{label}" [ref=e3]'
    elif mutation == "multiple-ref":
        lines[index] = f'- {role} "{label}" [ref={ref}] [ref=e90]'
    elif mutation == "multiple-ref-malformed-after":
        lines[index] = f'- {role} "{label}" [ref={ref}] [ref=invalid]'
    elif mutation == "multiple-ref-malformed-before":
        lines[index] = f'- {role} "{label}" [ref=invalid] [ref={ref}]'
    elif mutation == "multiple-ref-unclosed-after":
        lines[index] = f'- {role} "{label}" [ref={ref}] [ref=invalid'
    else:
        raise AssertionError(mutation)
    return snapshot(*lines)


def clicked_control_surface_with_inert_copy(control: str, copy_kind: str) -> str:
    lines = clicked_control_surface(control).splitlines()[1:]
    role, label, _ref, _surface = CLICKED_MENU_CONTROLS[control]
    if copy_kind in {"text", "statictext", "generic", "heading", "description"}:
        copy_role = copy_kind
        copy_label = label
    elif copy_kind == "wrong-role":
        copy_role = "link"
        copy_label = label
    elif copy_kind == "wrong-case":
        copy_role = role
        copy_label = label.swapcase()
    elif copy_kind == "padded-label":
        copy_role = role
        copy_label = f" {label} "
    else:
        raise AssertionError(copy_kind)
    lines.append(f'- {copy_role} "{copy_label}" [ref=e90]')
    return snapshot(*lines)


def semantic_expanded_menu(
    *,
    model_lines: tuple[str, ...] = ('- text: "Model GPT-5.6 Sol"',),
    effort_lines: tuple[str, ...] = ('- statictext: "Effort Pro"',),
    container_lines: tuple[str, ...] = ('- menu "Pro" [ref=e7]',),
    extra_lines: tuple[str, ...] = (),
) -> str:
    return snapshot(
        '- button "Pro" [ref=e6]',
        *container_lines,
        *model_lines,
        *effort_lines,
        *extra_lines,
    )


HYBRID_EXPAND_SHAPES = [
    pytest.param((), id="absent"),
    pytest.param(
        ('- menuitem "Show advanced options" [ref=e5]',),
        id="valid",
    ),
    pytest.param(
        ('- menuitem "Show advanced options" [disabled] [ref=e5]',),
        id="disabled",
    ),
    pytest.param(
        ('- menuitem "Show advanced options"',),
        id="ref-free",
    ),
    pytest.param(
        ('- menuitem "Show advanced options" [ref=invalid]',),
        id="malformed-ref",
    ),
    pytest.param(
        ('- menuitem "Show advanced options" [ref=e5] [ref=e90]',),
        id="multiple-valid-refs",
    ),
    pytest.param(
        ('- menuitem "Show advanced options" [ref=e5] [ref=invalid]',),
        id="multiple-malformed-ref-after",
    ),
    pytest.param(
        ('- menuitem "Show advanced options" [ref=invalid] [ref=e5]',),
        id="multiple-malformed-ref-before",
    ),
    pytest.param(
        ('- menuitem "Show advanced options" [ref=e5] [ref=invalid',),
        id="unclosed-malformed-ref",
    ),
    pytest.param(
        (
            '- menuitem "Show advanced options" [ref=e5]',
            '- menuitem "Show advanced options" [ref=e90]',
        ),
        id="duplicate-actionable",
    ),
    pytest.param(
        (
            '- menuitem "Show advanced options" [ref=e5]',
            '- menuitem "Show advanced options"',
        ),
        id="duplicate-ref-free",
    ),
    pytest.param(
        (
            '- menuitem "Show advanced options" [ref=e5]',
            '- menuitem "Show advanced options" [ref=invalid]',
        ),
        id="duplicate-malformed",
    ),
    pytest.param(
        ('- link "Show advanced options" [ref=e6]',),
        id="wrong-role",
    ),
    pytest.param(
        ('- MenuItem "Show advanced options" [ref=e6]',),
        id="wrong-role-case",
    ),
    pytest.param(
        ('- menuitem "SHOW ADVANCED OPTIONS" [ref=e6]',),
        id="wrong-label-case",
    ),
    pytest.param(
        ('- menuitem " Show advanced options " [ref=e6]',),
        id="padded-label",
    ),
    pytest.param(
        ('- menuitem "Show advanced options option" [ref=e6]',),
        id="near-label",
    ),
    pytest.param(
        ('- text "Show advanced options" [ref=e6]',),
        id="presentational",
    ),
    pytest.param(
        (
            '- menuitem "Show advanced options" [ref=e5]',
            '- text "Show advanced options" [ref=e6]',
        ),
        id="valid-with-presentational-copy",
    ),
    pytest.param(
        (
            '- navigation "Sidebar" [ref=e80]:',
            '  - menuitem "Show advanced options" [ref=e6]',
        ),
        id="untrusted-colliding-copy",
    ),
]


HYBRID_PRO_COLLISION_EXPAND_SHAPES = [
    pytest.param(
        ('- menuitem "Show advanced options" [ref=e6]',),
        id="valid",
    ),
    pytest.param(
        ('- menuitem "Show advanced options" [disabled] [ref=e6]',),
        id="disabled",
    ),
    pytest.param(
        ('- menuitem "Show advanced options" [ref=e6] [ref=invalid]',),
        id="malformed-after",
    ),
    pytest.param(
        ('- menuitem "Show advanced options" [ref=invalid] [ref=e6]',),
        id="malformed-before",
    ),
    pytest.param(
        ('- menuitem "Show advanced options" [ref=e5] [ref=e6]',),
        id="multiple-valid",
    ),
    pytest.param(
        (
            '- menuitem "Show advanced options" [ref=e5]',
            '- menuitem "Show advanced options" [ref=e6]',
        ),
        id="duplicate",
    ),
]


def advanced_landing_surface_with_inert_copy(
    copy_kind: str,
    *,
    button_ref: str,
    composer_ref: str,
) -> str:
    lines = [
        f'- button "Pro" [ref={button_ref}]',
        f'- textbox "Chat with ChatGPT" [ref={composer_ref}]',
    ]
    if copy_kind in {"text", "statictext", "generic", "heading", "description"}:
        copy_role = copy_kind
        copy_label = "Pro"
    elif copy_kind == "wrong-role":
        copy_role = "link"
        copy_label = "Pro"
    elif copy_kind == "wrong-case":
        copy_role = "button"
        copy_label = "pRO"
    elif copy_kind == "padded-label":
        copy_role = "button"
        copy_label = " Pro "
    else:
        raise AssertionError(copy_kind)
    lines.append(f'- {copy_role} "{copy_label}" [ref={button_ref}]')
    return snapshot(*lines)


def invalid_advanced_landing_surface(
    mutation: str,
    *,
    button_ref: str,
    composer_ref: str,
) -> str:
    button = f'- button "Pro" [ref={button_ref}]'
    composer = f'- textbox "Chat with ChatGPT" [ref={composer_ref}]'
    lines = [button, composer]
    if mutation == "missing":
        lines.remove(button)
    elif mutation == "wrong-role-only":
        lines[0] = f'- combobox "Pro" [ref={button_ref}]'
    elif mutation == "wrong-role-case-only":
        lines[0] = f'- Button "Pro" [ref={button_ref}]'
    elif mutation == "wrong-case-only":
        lines[0] = f'- button "pRO" [ref={button_ref}]'
    elif mutation == "padded-label-only":
        lines[0] = f'- button " Pro " [ref={button_ref}]'
    elif mutation == "disabled":
        lines[0] = f'- button "Pro" [disabled] [ref={button_ref}]'
    elif mutation == "ref-free-only":
        lines[0] = '- button "Pro"'
    elif mutation == "malformed-ref-only":
        lines[0] = '- button "Pro" [ref=invalid]'
    elif mutation == "multiple-ref":
        lines[0] = f'- button "Pro" [ref={button_ref}] [ref=e90]'
    elif mutation == "multiple-ref-malformed-after":
        lines[0] = f'- button "Pro" [ref={button_ref}] [ref=invalid]'
    elif mutation == "multiple-ref-malformed-before":
        lines[0] = f'- button "Pro" [ref=invalid] [ref={button_ref}]'
    elif mutation == "duplicate-actionable":
        lines.append('- button "Pro" [ref=e90]')
    elif mutation == "duplicate-ref-free":
        lines.append('- button "Pro"')
    elif mutation == "duplicate-malformed":
        lines.append('- button "Pro" [ref=invalid]')
    elif mutation == "ref-collision":
        lines[0] = f'- button "Pro" [ref={composer_ref}]'
    else:
        raise AssertionError(mutation)
    return snapshot(*lines)


@pytest.mark.parametrize("control", sorted(CLICKED_MENU_CONTROLS))
@pytest.mark.parametrize(
    "copy_kind",
    [
        "text",
        "statictext",
        "generic",
        "heading",
        "description",
        "wrong-role",
        "wrong-case",
        "padded-label",
    ],
)
def test_inert_clicked_control_copies_do_not_create_ambiguity(
    control: str,
    copy_kind: str,
) -> None:
    surface = clicked_control_surface_with_inert_copy(control, copy_kind)
    is_compact = CLICKED_MENU_CONTROLS[control][3] == "compact"
    transport = ScriptedTransport(
        advanced_pre_type_snapshots(
            menu_snapshot=surface if is_compact else None,
            expanded_snapshot=None if is_compact else surface,
        )
    )

    _contract, observations, profile_id, _profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert observations[1]["refs"] == {}
    assert observations[2]["refs"] == {}
    assert ready["refs"] == {"composer": ["e41"]}
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "show advanced options", "Pro menu"]
    assert not any(tool == "browser_wait_for" for tool, _arguments in transport.calls)


@pytest.mark.parametrize(
    "inert_expand_copy",
    [
        '- text "Show advanced options"',
        '- link "Show advanced options" [ref=e90]',
        '- generic "Show advanced options" [ref=e90]',
        '- MenuItem "Show advanced options" [ref=e90]',
        '- menuitem "SHOW ADVANCED OPTIONS" [ref=e90]',
        '- menuitem " Show advanced options " [ref=e90]',
        '- menuitem "Show advanced options option" [ref=e90]',
    ],
)
def test_inert_expand_copies_do_not_veto_valid_expanded_semantic_state(
    inert_expand_copy: str,
) -> None:
    surface = semantic_expanded_menu(extra_lines=(inert_expand_copy,))
    transport = ScriptedTransport(
        advanced_pre_type_snapshots(expanded_snapshot=surface)
    )

    assert orchestrator._advanced_menu_state(surface)["view"] == "expanded"
    _contract, observations, profile_id, _profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert observations[1]["refs"] == {}
    assert observations[2]["refs"] == {}
    assert ready["refs"] == {"composer": ["e41"]}
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "show advanced options", "Pro menu"]
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


@pytest.mark.parametrize("expand_lines", HYBRID_EXPAND_SHAPES)
def test_exact_semantic_pair_ignores_every_expand_shape_before_resolution(
    expand_lines: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    surface = semantic_expanded_menu(
        container_lines=(),
        extra_lines=expand_lines,
    )
    resolved_labels: list[str] = []
    original_strict_control_ref = orchestrator._strict_control_ref

    def record_strict_control_resolution(
        snapshot_value: str,
        *,
        label: str,
        role: str,
    ) -> str:
        resolved_labels.append(label)
        return original_strict_control_ref(
            snapshot_value,
            label=label,
            role=role,
        )

    monkeypatch.setattr(
        orchestrator,
        "_strict_control_ref",
        record_strict_control_resolution,
    )

    state = orchestrator._advanced_menu_state(surface)
    assert state["view"] == "expanded"
    assert state["expand_ref"] is None

    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            surface,
            landing(button_ref="e40", composer_ref="e41"),
        ]
    )
    _contract, observations, profile_id, _profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert observations[1]["refs"] == {}
    assert observations[2]["refs"] == {}
    assert ready["refs"] == {"composer": ["e41"]}
    assert orchestrator.ADVANCED_EXPAND_LABEL not in resolved_labels
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "Pro menu"]
    assert [
        arguments["target"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["e1", "e6"]
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)
    assert not any(tool == "browser_wait_for" for tool, _arguments in transport.calls)


@pytest.mark.parametrize("expand_lines", HYBRID_PRO_COLLISION_EXPAND_SHAPES)
def test_exact_semantic_pair_rejects_expand_ref_collision_as_used_pro_defect(
    expand_lines: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    surface = semantic_expanded_menu(
        container_lines=(),
        extra_lines=expand_lines,
    )
    resolved_labels: list[str] = []
    original_strict_control_ref = orchestrator._strict_control_ref

    def record_strict_control_resolution(
        snapshot_value: str,
        *,
        label: str,
        role: str,
    ) -> str:
        resolved_labels.append(label)
        return original_strict_control_ref(
            snapshot_value,
            label=label,
            role=role,
        )

    def reject_submission_event(*_arguments: Any, **_keywords: Any) -> str:
        raise AssertionError("a colliding Pro target must refuse before intent")

    monkeypatch.setattr(
        orchestrator,
        "_strict_control_ref",
        record_strict_control_resolution,
    )
    monkeypatch.setattr(workflow, "_append_event", reject_submission_event)
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            *settle_exhaustion(surface),
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._live_capture(
            prepared={
                "record_path": "/unused/colliding-pro-record.jsonl",
                "run_id": "20260810T000000Z-bbbbbbbbbbbb",
                "prompt_sha256": "c" * 64,
            },
            transport=transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == "ADVANCED_PRO_BUTTON_INVALID"
    assert captured.value.phase == "pro_menu"
    assert orchestrator.ADVANCED_EXPAND_LABEL not in resolved_labels
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker"]
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)
    assert not any(
        tool == "browser_click" and arguments.get("element") == "send prompt"
        for tool, arguments in transport.calls
    )


CLICKED_CONTROL_DEFECT_CASES = [
    (control, mutation)
    for control in sorted(CLICKED_MENU_CONTROLS)
    for mutation in (
        "missing",
        "wrong-role-only",
        "wrong-case-only",
        "padded-label-only",
        "near-label-only",
        "disabled",
        "ref-free-only",
        "malformed-ref-only",
        "multiple-ref",
        "multiple-ref-malformed-after",
        "multiple-ref-malformed-before",
        "multiple-ref-unclosed-after",
        "duplicate-actionable",
        "duplicate-ref-free",
        "duplicate-malformed",
    )
] + [("expand", "ref-collision")]


@pytest.mark.parametrize(("control", "mutation"), CLICKED_CONTROL_DEFECT_CASES)
def test_each_clicked_control_defect_fails_closed_before_input(
    control: str,
    mutation: str,
) -> None:
    bad_surface = invalid_clicked_control(control, mutation)
    is_compact = CLICKED_MENU_CONTROLS[control][3] == "compact"
    transport = ScriptedTransport(
        (
            [
                landing(button_ref="e1", composer_ref="e2"),
                *settle_exhaustion(bad_surface),
            ]
            if is_compact
            else [
                landing(button_ref="e1", composer_ref="e2"),
                compact_menu(),
                *settle_exhaustion(bad_surface),
            ]
        )
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    expected_code = (
        "ADVANCED_PRO_BUTTON_INVALID"
        if control == "button"
        else (
            "ADVANCED_MENU_UNRECOGNIZED"
            if mutation
            in {
                "missing",
                "wrong-role-only",
                "wrong-case-only",
                "padded-label-only",
                "near-label-only",
            }
            else "ADVANCED_EXPAND_CONTROL_INVALID"
        )
    )
    assert captured.value.code == expected_code
    assert captured.value.phase == ("pro_menu" if is_compact else "advanced_summary")
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == (["model picker"] if is_compact else ["model picker", "show advanced options"])
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == 12


SEMANTIC_SUMMARY_ROLES = (
    "menuitem",
    "button",
    "link",
    "text",
    "statictext",
    "heading",
    "description",
)


@pytest.mark.parametrize("model_role", SEMANTIC_SUMMARY_ROLES)
@pytest.mark.parametrize("effort_role", SEMANTIC_SUMMARY_ROLES)
def test_semantic_summary_roles_are_evidence_only(
    model_role: str,
    effort_role: str,
) -> None:
    semantic_surface = semantic_expanded_menu(
        model_lines=(f'- {model_role} "Model GPT-5.6 Sol" [ref=e90]',),
        effort_lines=(f'- {effort_role} "Effort Pro" [ref=e91]',),
    )
    transport = ScriptedTransport(
        advanced_pre_type_snapshots(expanded_snapshot=semantic_surface)
    )

    _contract, observations, profile_id, _profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert observations[1]["refs"] == {}
    assert observations[2]["refs"] == {}
    assert ready["refs"] == {"composer": ["e41"]}
    click_targets = {
        arguments["target"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    }
    assert click_targets.isdisjoint({"e90", "e91"})
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "show advanced options", "Pro menu"]


@pytest.mark.parametrize(
    "container_lines",
    [
        ('- menu "Pro" [ref=e7]',),
        ("- menu [ref=e7]",),
        ('- menu "Current mode" [ref=e7]',),
        ('- generic "Picker surface" [ref=e7]',),
        ('- menu "Pro"',),
        (),
    ],
)
def test_semantic_summary_ignores_container_identity(
    container_lines: tuple[str, ...],
) -> None:
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            semantic_expanded_menu(container_lines=container_lines),
            landing(button_ref="e40", composer_ref="e41"),
        ]
    )

    _contract, observations, profile_id, _profile, _ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert observations[1]["refs"] == {}
    assert observations[2]["refs"] == {}
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "Pro menu"]


@pytest.mark.parametrize(
    ("container_lines", "model_lines", "effort_lines"),
    [
        pytest.param(
            ('- menu "Model GPT-5.6 Sol" [ref=e7]',),
            (),
            ('- text: "Effort Pro"',),
            id="target-model-container-is-not-evidence",
        ),
        pytest.param(
            ('- menu "Effort Pro" [ref=e7]',),
            ('- text: "Model GPT-5.6 Sol"',),
            (),
            id="target-effort-container-is-not-evidence",
        ),
        pytest.param(
            ('- generic "Model GPT-5.6 Sol" [ref=e7]',),
            (),
            ('- text: "Effort Pro"',),
            id="target-model-generic-is-not-evidence",
        ),
        pytest.param(
            ('- listbox "Effort Pro" [ref=e7]',),
            ('- text: "Model GPT-5.6 Sol"',),
            (),
            id="target-effort-listbox-is-not-evidence",
        ),
        pytest.param(
            ('- dialog "Model GPT-5.6 Sol" [ref=e7]',),
            (),
            ('- text: "Effort Pro"',),
            id="target-model-dialog-is-not-evidence",
        ),
        pytest.param(
            ('- menuitemradio "Effort Pro" [ref=e7]',),
            ('- text: "Model GPT-5.6 Sol"',),
            (),
            id="target-effort-child-option-is-not-evidence",
        ),
    ],
)
def test_semantic_summary_container_label_cannot_supply_target_evidence(
    container_lines: tuple[str, ...],
    model_lines: tuple[str, ...],
    effort_lines: tuple[str, ...],
) -> None:
    bad_summary = semantic_expanded_menu(
        container_lines=container_lines,
        model_lines=model_lines,
        effort_lines=effort_lines,
    )
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            compact_menu(),
            *settle_exhaustion(bad_summary),
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.phase == "advanced_summary"
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


@pytest.mark.parametrize(
    "container_lines",
    [
        ('- menu "Model GPT-5.5" [ref=e7]',),
        ('- menu "Effort High"',),
        ('- generic "Model settings" [ref=e7]',),
        ('- listbox "Model GPT-5.5" [ref=e7]',),
        ('- dialog "Effort High" [ref=e7]',),
        ('- menuitemradio "Model GPT-5.5" [ref=e7]',),
        ('- option "Effort High" [ref=e7]',),
        ('- radio "Model GPT-5.5" [ref=e7]',),
    ],
)
def test_semantic_summary_container_label_cannot_compete_with_target_evidence(
    container_lines: tuple[str, ...],
) -> None:
    transport = ScriptedTransport(
        advanced_pre_type_snapshots(
            expanded_snapshot=semantic_expanded_menu(
                container_lines=container_lines,
            )
        )
    )

    _contract, observations, profile_id, _profile, _ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert observations[1]["refs"] == {}
    assert observations[2]["refs"] == {}


@pytest.mark.parametrize(
    ("model_lines", "effort_lines"),
    [
        pytest.param(
            ('- text "Model GPT-5.6 Sol"',),
            ('- statictext "Effort Pro"',),
            id="ref-free",
        ),
        pytest.param(
            ('- text: "Model   GPT-5.6\\tSol"',),
            ('- statictext: "Effort\\t Pro"',),
            id="canonical-presentational-payload",
        ),
        pytest.param(
            ('- button "Model GPT-5.6 Sol" [disabled] [ref=e6] [ref=e90]',),
            ('- menuitem "Effort Pro" [ref=invalid]',),
            id="attributes-and-malformed-refs",
        ),
        pytest.param(
            (
                '- menuitem "Model GPT-5.6 Sol" [ref=e90]',
                '- text "Model   GPT-5.6\tSol"',
            ),
            (
                '- menuitem "Effort Pro" [ref=e91]',
                '- description "Effort\t Pro"',
            ),
            id="same-value-duplicates",
        ),
    ],
)
def test_semantic_summary_refs_attributes_and_same_value_duplicates_are_inert(
    model_lines: tuple[str, ...],
    effort_lines: tuple[str, ...],
) -> None:
    transport = ScriptedTransport(
        advanced_pre_type_snapshots(
            expanded_snapshot=semantic_expanded_menu(
                model_lines=model_lines,
                effort_lines=effort_lines,
            )
        )
    )

    _contract, observations, profile_id, _profile, _ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert observations[1]["refs"] == {}
    assert observations[2]["refs"] == {}
    assert not any(
        arguments.get("element") in {"advanced model", "advanced effort"}
        for tool, arguments in transport.calls
        if tool == "browser_click"
    )


SEMANTIC_SUMMARY_DEFECT_CASES = [
    pytest.param(
        (),
        ('- text "Effort Pro"',),
        "ADVANCED_MODEL_EVIDENCE_MISSING",
        id="missing-model",
    ),
    pytest.param(
        ('- text "Model GPT-5.6 Sol"',),
        (),
        "ADVANCED_EFFORT_EVIDENCE_MISSING",
        id="missing-effort",
    ),
    pytest.param(
        ('- text "model GPT-5.6 Sol"',),
        ('- text "Effort Pro"',),
        "ADVANCED_MODEL_EVIDENCE_CONFLICT",
        id="wrong-model-case",
    ),
    pytest.param(
        ('- text "Model GPT-5.6 Sol"',),
        ('- text "effort Pro"',),
        "ADVANCED_EFFORT_EVIDENCE_CONFLICT",
        id="wrong-effort-case",
    ),
    pytest.param(
        ('- text " Model GPT-5.6 Sol"',),
        ('- text "Effort Pro"',),
        "ADVANCED_MODEL_EVIDENCE_CONFLICT",
        id="leading-model-padding",
    ),
    pytest.param(
        ('- text "Model GPT-5.6 Sol"',),
        ('- text "Effort Pro "',),
        "ADVANCED_EFFORT_EVIDENCE_CONFLICT",
        id="trailing-effort-padding",
    ),
    pytest.param(
        ('- text "Selected model GPT-5.6 Sol"',),
        ('- text "Effort Pro"',),
        "ADVANCED_MODEL_EVIDENCE_MISSING",
        id="renamed-model",
    ),
    pytest.param(
        ('- text "Model GPT-5.6 Sol"',),
        ('- text "Selected effort Pro"',),
        "ADVANCED_EFFORT_EVIDENCE_MISSING",
        id="renamed-effort",
    ),
    pytest.param(
        ('- text "Model GPT-5.6"',),
        ('- text "Effort Pro"',),
        "ADVANCED_MODEL_EVIDENCE_CONFLICT",
        id="near-model",
    ),
    pytest.param(
        ('- text "Model GPT-5.6 Sol"',),
        ('- text "Effort Standard"',),
        "ADVANCED_EFFORT_EVIDENCE_CONFLICT",
        id="near-effort",
    ),
    pytest.param(
        ('- text "Model GPT-5.6 Sol"', '- text "Model GPT-5.5"'),
        ('- text "Effort Pro"',),
        "ADVANCED_MODEL_EVIDENCE_CONFLICT",
        id="competing-model",
    ),
    pytest.param(
        ('- text "Model GPT-5.6 Sol"',),
        ('- text "Effort Pro"', '- text "Effort High"'),
        "ADVANCED_EFFORT_EVIDENCE_CONFLICT",
        id="competing-effort",
    ),
    pytest.param(
        ("- text: Model GPT-5.6 Sol",),
        ('- text: "Effort Pro"',),
        "ADVANCED_MODEL_EVIDENCE_MISSING",
        id="unquoted-model-payload",
    ),
    pytest.param(
        ('- text: "Model GPT-5.6 Sol',),
        ('- text: "Effort Pro"',),
        "ADVANCED_MODEL_EVIDENCE_MISSING",
        id="unterminated-model-payload",
    ),
    pytest.param(
        ("- text: 42",),
        ('- text: "Effort Pro"',),
        "ADVANCED_MODEL_EVIDENCE_MISSING",
        id="non-string-model-payload",
    ),
    pytest.param(
        ('- generic: "Model GPT-5.6 Sol"',),
        ('- text: "Effort Pro"',),
        "ADVANCED_MODEL_EVIDENCE_MISSING",
        id="unapproved-payload-role",
    ),
]


@pytest.mark.parametrize(
    ("model_lines", "effort_lines", "expected_code"),
    SEMANTIC_SUMMARY_DEFECT_CASES,
)
def test_semantic_summary_defects_refuse_before_type(
    model_lines: tuple[str, ...],
    effort_lines: tuple[str, ...],
    expected_code: str,
) -> None:
    bad_summary = semantic_expanded_menu(
        model_lines=model_lines,
        effort_lines=effort_lines,
    )
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            compact_menu(),
            *settle_exhaustion(bad_summary),
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == expected_code
    assert captured.value.phase == "advanced_summary"
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "show advanced options"]
    assert not any(tool == "browser_type" for tool, _ in transport.calls)
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == 12


@pytest.mark.parametrize("expand_lines", HYBRID_EXPAND_SHAPES)
@pytest.mark.parametrize(
    ("model_lines", "effort_lines", "expected_code"),
    SEMANTIC_SUMMARY_DEFECT_CASES,
)
def test_partial_or_conflicting_semantics_prevent_every_expand_and_submission_action(
    model_lines: tuple[str, ...],
    effort_lines: tuple[str, ...],
    expected_code: str,
    expand_lines: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad_summary = semantic_expanded_menu(
        container_lines=(),
        model_lines=model_lines,
        effort_lines=effort_lines,
        extra_lines=expand_lines,
    )
    resolved_labels: list[str] = []
    original_strict_control_ref = orchestrator._strict_control_ref

    def record_strict_control_resolution(
        snapshot_value: str,
        *,
        label: str,
        role: str,
    ) -> str:
        resolved_labels.append(label)
        return original_strict_control_ref(
            snapshot_value,
            label=label,
            role=role,
        )

    def reject_submission_event(*_arguments: Any, **_keywords: Any) -> str:
        raise AssertionError("semantic defects must refuse before submission intent")

    monkeypatch.setattr(
        orchestrator,
        "_strict_control_ref",
        record_strict_control_resolution,
    )
    monkeypatch.setattr(workflow, "_append_event", reject_submission_event)
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            *settle_exhaustion(bad_summary),
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._live_capture(
            prepared={
                "record_path": "/unused/semantic-defect-record.jsonl",
                "run_id": "20260810T000000Z-aaaaaaaaaaaa",
                "prompt_sha256": "b" * 64,
            },
            transport=transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == expected_code
    assert captured.value.phase == "pro_menu"
    assert orchestrator.ADVANCED_EXPAND_LABEL not in resolved_labels
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker"]
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)
    assert not any(
        tool == "browser_click" and arguments.get("element") == "send prompt"
        for tool, arguments in transport.calls
    )
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == 12


@pytest.mark.parametrize("boundary", ["initial", "closed"])
@pytest.mark.parametrize("copy_kind", ADVANCED_LANDING_INERT_COPY_KINDS)
def test_advanced_landing_inert_copies_do_not_duplicate_the_exact_button(
    boundary: str,
    copy_kind: str,
) -> None:
    surface = advanced_landing_surface_with_inert_copy(
        copy_kind,
        button_ref="e1" if boundary == "initial" else "e40",
        composer_ref="e2" if boundary == "initial" else "e41",
    )
    transport = ScriptedTransport(
        [
            surface,
            compact_menu(),
            expanded_menu(),
            landing(button_ref="e40", composer_ref="e41"),
        ]
        if boundary == "initial"
        else advanced_pre_type_snapshots(final_snapshot=surface)
    )

    _contract, _observations, profile_id, _profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert ready["refs"] == {"composer": ["e41"]}
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "show advanced options", "Pro menu"]
    assert not any(tool == "browser_wait_for" for tool, _ in transport.calls)
    assert not any(tool == "browser_type" for tool, _ in transport.calls)


@pytest.mark.parametrize("boundary", ["initial", "closed"])
@pytest.mark.parametrize("mutation", ADVANCED_LANDING_DEFECTS)
def test_advanced_landing_button_defects_fail_closed_before_input(
    boundary: str,
    mutation: str,
) -> None:
    bad_surface = invalid_advanced_landing_surface(
        mutation,
        button_ref="e1" if boundary == "initial" else "e40",
        composer_ref="e2" if boundary == "initial" else "e41",
    )
    transport = ScriptedTransport(
        [bad_surface, bad_surface]
        if boundary == "initial"
        else [
            landing(button_ref="e1", composer_ref="e2"),
            compact_menu(),
            expanded_menu(),
            *settle_exhaustion(bad_surface),
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.phase == (
        "landing" if boundary == "initial" else "closed_landing"
    )
    assert not any(tool == "browser_type" for tool, _ in transport.calls)
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == (
        []
        if boundary == "initial"
        else ["model picker", "show advanced options", "Pro menu"]
    )
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == (
        1 if boundary == "initial" else 12
    )


def test_wrong_role_picker_is_not_clicked_as_an_advanced_landing() -> None:
    unverified_landing = snapshot(
        '- combobox "Pro" [ref=e1]',
        '- textbox "Chat with ChatGPT" [ref=e2]',
    )
    transport = ScriptedTransport([unverified_landing, unverified_landing])

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == "SELECTOR_AMBIGUITY"
    assert captured.value.phase == "landing"
    assert not any(tool == "browser_click" for tool, _ in transport.calls)
    assert not any(tool == "browser_type" for tool, _ in transport.calls)
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == 1


@pytest.mark.parametrize("picker_role", ["button", "combobox"])
def test_untrusted_sidebar_picker_is_never_clicked(picker_role: str) -> None:
    untrusted_landing = snapshot(
        '- textbox "Chat with ChatGPT" [ref=e2]',
        '- navigation "Sidebar" [ref=e80]:',
        f'  - {picker_role} "Pro" [ref=e1]',
    )
    transport = ScriptedTransport([untrusted_landing, untrusted_landing])

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == "SELECTOR_AMBIGUITY"
    assert captured.value.phase == "landing"
    assert not any(tool == "browser_click" for tool, _ in transport.calls)
    assert not any(tool == "browser_type" for tool, _ in transport.calls)
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == 1


def test_independently_distinguishable_legacy_combined_profile_remains_supported() -> (
    None
):
    transport = ScriptedTransport(
        [
            snapshot(
                '- button "Models" [ref=e1]',
                '- textbox "Ask anything" [ref=e10]',
                '- navigation "Sidebar" [ref=e80]:',
                '  - button "Pro" [ref=e81]',
            ),
            snapshot(
                '- menuitem "Pro Standard" [ref=e2]',
                '- menuitem "Pro Extended" [ref=e3]',
            ),
            snapshot(
                '- button "Pro Extended" [ref=e4]',
                '- textbox "Ask anything" [ref=e5]',
                '- button "Send" [ref=e6]',
            ),
        ]
    )

    _contract, observations, profile_id, profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == "pro-extended-combined-v1"
    assert profile["effort_mode"] == "combined"
    assert [item["state"] for item in observations] == [
        "landing",
        "model_menu",
        "ready",
    ]
    assert ready["refs"] == {"composer": ["e5"], "send": ["e6"]}
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "Pro model option"]


def test_independently_distinguishable_legacy_split_profile_remains_supported() -> None:
    transport = ScriptedTransport(
        [
            snapshot('- button "Models" [ref=e1]'),
            snapshot('- menuitem "Pro" [ref=e2]'),
            snapshot(
                '- menuitem "Pro" [ref=e3]',
                '- button "Effort" [ref=e4]',
            ),
            snapshot(
                '- menuitem "Standard" [ref=e5]',
                '- menuitem "Extended" [ref=e6]',
            ),
            snapshot(
                '- button "Pro" [ref=e7]',
                '- textbox "Ask anything" [ref=e8]',
                '- button "Send" [ref=e9]',
            ),
        ]
    )

    _contract, observations, profile_id, profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == "pro-extended-split-v1"
    assert profile["effort_mode"] == "split"
    assert [item["state"] for item in observations] == [
        "landing",
        "model_menu",
        "model_selected",
        "effort_menu",
        "ready",
    ]
    assert ready["refs"] == {"composer": ["e8"], "send": ["e9"]}
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == [
        "model picker",
        "Pro model option",
        "Pro effort picker",
        "maximum Pro effort",
    ]


def test_closed_landing_ignores_untrusted_sidebar_controls_and_ref_collisions() -> None:
    closed_with_sidebar = snapshot(
        '- button "Pro" [ref=e40]',
        '- textbox "Chat with ChatGPT" [ref=e41]',
        '- navigation "Sidebar" [ref=e80]:',
        '  - button "Pro" [ref=e40]',
        '  - menuitem "Model GPT-5.6 Sol" [ref=e81]',
    )
    transport = ScriptedTransport(
        advanced_pre_type_snapshots(final_snapshot=closed_with_sidebar)
    )

    _contract, _observations, profile_id, _profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert ready["refs"] == {"composer": ["e41"]}
    assert not any(tool == "browser_wait_for" for tool, _ in transport.calls)
    assert not any(tool == "browser_type" for tool, _ in transport.calls)


def test_summary_controls_may_reorder_without_child_option_inspection() -> None:
    lines = expanded_menu().splitlines()[1:]
    reordered = snapshot(lines[1], lines[4], lines[3], lines[0], lines[2], lines[5])
    transport = ScriptedTransport(
        advanced_pre_type_snapshots(expanded_snapshot=reordered)
    )

    _contract, observations, profile_id, _profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert observations[1]["refs"] == {}
    assert observations[2]["refs"] == {}
    assert ready["model_label"] == "GPT-5.6 Sol"
    assert ready["effort_label"] == "Pro"


@pytest.mark.parametrize(
    "child_lines",
    [
        (),
        ('- menuitemradio "Unknown Ultra" [checked] [ref=e80]',),
        (
            '- menuitemradio "GPT-5.5" [ref=e82]',
            '- menuitemradio "GPT-5.6 Sol" [checked] [ref=e81]',
            '- menuitemradio "New model" [ref=e83]',
        ),
        (
            '- menuitemradio "Pro"',
            '- menuitemradio "Experimental" [disabled] [ref=e84]',
        ),
    ],
)
def test_unobserved_child_inventory_drift_cannot_refuse_summary_path(
    child_lines: tuple[str, ...],
) -> None:
    drifted = "\n".join((expanded_menu(), *child_lines))
    transport = ScriptedTransport(
        advanced_pre_type_snapshots(expanded_snapshot=drifted)
    )

    _contract, _observations, profile_id, _profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert ready["model_label"] == "GPT-5.6 Sol"
    assert ready["effort_label"] == "Pro"
    assert not any(
        arguments.get("element") in {"advanced model", "advanced effort"}
        for tool, arguments in transport.calls
        if tool == "browser_click"
    )


@pytest.mark.parametrize(
    ("phase", "snapshots", "preceding_action"),
    [
        pytest.param(
            "pro_menu",
            [
                landing(button_ref="e1", composer_ref="e2"),
                snapshot('- status "Loading menu" [ref=e80]'),
                compact_menu(),
                expanded_menu(),
                landing(button_ref="e40", composer_ref="e41"),
            ],
            "model picker",
            id="open",
        ),
        pytest.param(
            "advanced_summary",
            [
                landing(button_ref="e1", composer_ref="e2"),
                compact_menu(),
                snapshot('- status "Loading summaries" [ref=e80]'),
                expanded_menu(),
                landing(button_ref="e40", composer_ref="e41"),
            ],
            "show advanced options",
            id="expand",
        ),
        pytest.param(
            "closed_landing",
            [
                landing(button_ref="e1", composer_ref="e2"),
                compact_menu(),
                expanded_menu(),
                snapshot('- status "Closing menu" [ref=e80]'),
                landing(button_ref="e40", composer_ref="e41"),
            ],
            "Pro menu",
            id="close",
        ),
    ],
)
def test_each_advanced_transition_may_settle_without_repeating_action(
    phase: str,
    snapshots: list[str],
    preceding_action: str,
) -> None:
    transport = ScriptedTransport(snapshots)

    _contract, _observations, profile_id, _profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert ready["refs"] == {"composer": ["e41"]}
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == 1
    assert (
        sum(
            tool == "browser_click" and arguments.get("element") == preceding_action
            for tool, arguments in transport.calls
        )
        == 1
    )
    assert not any(
        arguments.get("element") in {"advanced model", "advanced effort"}
        for tool, arguments in transport.calls
        if tool == "browser_click"
    )
    assert phase in orchestrator.PRE_SUBMISSION_PHASES


def test_twelfth_additional_summary_observation_is_accepted() -> None:
    transient = snapshot('- status "Loading summaries" [ref=e80]')
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            compact_menu(),
            *[transient for _ in range(12)],
            expanded_menu(),
            landing(button_ref="e40", composer_ref="e41"),
        ]
    )

    _contract, _observations, profile_id, _profile, _ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == 12
    assert (
        sum(
            tool == "browser_click"
            and arguments.get("element") == "show advanced options"
            for tool, arguments in transport.calls
        )
        == 1
    )


@pytest.mark.parametrize(
    ("menu_snapshot", "expected_code"),
    [
        pytest.param(
            invalid_clicked_control("button", "missing"),
            "ADVANCED_PRO_BUTTON_INVALID",
            id="pro-control",
        ),
        pytest.param(
            invalid_clicked_control("expand", "disabled"),
            "ADVANCED_EXPAND_CONTROL_INVALID",
            id="expand-control",
        ),
        pytest.param(
            snapshot(
                '- button "Pro" [ref=e3]',
                '- menuitem "Show advanced options" [ref=e5]',
                '- text "Model GPT-5.5"',
            ),
            "ADVANCED_MODEL_EVIDENCE_CONFLICT",
            id="semantic-conflict-before-expand",
        ),
        pytest.param(
            semantic_expanded_menu(model_lines=()),
            "ADVANCED_MODEL_EVIDENCE_MISSING",
            id="model-missing",
        ),
        pytest.param(
            semantic_expanded_menu(
                model_lines=(
                    '- text "Model GPT-5.6 Sol"',
                    '- text "Model GPT-5.5"',
                )
            ),
            "ADVANCED_MODEL_EVIDENCE_CONFLICT",
            id="model-conflict",
        ),
        pytest.param(
            semantic_expanded_menu(effort_lines=()),
            "ADVANCED_EFFORT_EVIDENCE_MISSING",
            id="effort-missing",
        ),
        pytest.param(
            semantic_expanded_menu(
                effort_lines=(
                    '- text "Effort Pro"',
                    '- text "Effort High"',
                )
            ),
            "ADVANCED_EFFORT_EVIDENCE_CONFLICT",
            id="effort-conflict",
        ),
        pytest.param(
            snapshot('- button "Pro" [ref=e3]', '- menu "Pro" [ref=e4]'),
            "ADVANCED_MENU_UNRECOGNIZED",
            id="unrecognized",
        ),
    ],
)
def test_advanced_diagnostic_codes_are_immediate_and_closed(
    menu_snapshot: str,
    expected_code: str,
) -> None:
    assert orchestrator.ADVANCED_PRE_SUBMISSION_DIAGNOSTIC_CODES == {
        "ADVANCED_PRO_BUTTON_INVALID",
        "ADVANCED_EXPAND_CONTROL_INVALID",
        "ADVANCED_MENU_STATE_MIXED",
        "ADVANCED_MODEL_EVIDENCE_MISSING",
        "ADVANCED_MODEL_EVIDENCE_CONFLICT",
        "ADVANCED_EFFORT_EVIDENCE_MISSING",
        "ADVANCED_EFFORT_EVIDENCE_CONFLICT",
        "ADVANCED_MENU_UNRECOGNIZED",
    }

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._advanced_menu_state(menu_snapshot)

    assert captured.value.code == expected_code
    assert captured.value.code in orchestrator.ADVANCED_PRE_SUBMISSION_DIAGNOSTIC_CODES


@pytest.mark.parametrize(
    ("surface", "expected_code"),
    [
        pytest.param(
            snapshot(
                '- button "PRO" [ref=e3]',
                '- menuitem "Show advanced options" [disabled] [ref=e3]',
                '- text "Model GPT-5.5"',
                '- text "Effort High"',
            ),
            "ADVANCED_PRO_BUTTON_INVALID",
            id="pro-before-everything",
        ),
        pytest.param(
            snapshot(
                '- button "Pro" [ref=e3]',
                '- menuitem "Show advanced options" [disabled] [ref=e5]',
                '- text "Model GPT-5.5"',
                '- text "Effort High"',
            ),
            "ADVANCED_MODEL_EVIDENCE_CONFLICT",
            id="semantic-before-invalid-expand",
        ),
        pytest.param(
            snapshot(
                '- button "Pro" [ref=e3]',
                '- menuitem "Show advanced options" [ref=e5]',
                '- text "Model GPT-5.5"',
                '- text "Effort High"',
            ),
            "ADVANCED_MODEL_EVIDENCE_CONFLICT",
            id="semantic-before-valid-expand",
        ),
        pytest.param(
            semantic_expanded_menu(
                model_lines=(), effort_lines=('- text "Effort High"',)
            ),
            "ADVANCED_MODEL_EVIDENCE_MISSING",
            id="model-missing-before-effort-conflict",
        ),
        pytest.param(
            semantic_expanded_menu(
                model_lines=('- text "Model GPT-5.5"',), effort_lines=()
            ),
            "ADVANCED_MODEL_EVIDENCE_CONFLICT",
            id="model-conflict-before-effort-missing",
        ),
    ],
)
def test_advanced_diagnostic_compound_priority_is_deterministic(
    surface: str,
    expected_code: str,
) -> None:
    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._advanced_menu_state(surface)

    assert captured.value.code == expected_code


def test_delayed_valid_advanced_surfaces_emit_no_diagnostic_or_repeated_action() -> (
    None
):
    unrecognized = snapshot('- button "Pro" [ref=e3]', '- menu "Pro" [ref=e4]')
    missing_model = semantic_expanded_menu(model_lines=())
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            unrecognized,
            compact_menu(),
            missing_model,
            expanded_menu(),
            landing(button_ref="e40", composer_ref="e41"),
        ]
    )

    _contract, _observations, profile_id, _profile, _ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == 2
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "show advanced options", "Pro menu"]
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


def test_final_settle_observation_preserves_its_closed_diagnostic() -> None:
    unrecognized = snapshot('- button "Pro" [ref=e3]', '- menu "Pro" [ref=e4]')
    missing_model = semantic_expanded_menu(model_lines=())
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            *[unrecognized for _ in range(12)],
            missing_model,
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == "ADVANCED_MODEL_EVIDENCE_MISSING"
    assert captured.value.phase == "pro_menu"
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == 12
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker"]
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


@pytest.mark.parametrize(
    ("snapshots", "phase", "clicked"),
    [
        pytest.param(
            [
                landing(button_ref="e1", composer_ref="e2"),
                orchestrator.TransportUnavailable("MCP_DISCONNECTED"),
            ],
            "pro_menu",
            ["model picker"],
            id="open",
        ),
        pytest.param(
            [
                landing(button_ref="e1", composer_ref="e2"),
                compact_menu(),
                orchestrator.TransportUnavailable("MCP_DISCONNECTED"),
            ],
            "advanced_summary",
            ["model picker", "show advanced options"],
            id="expand",
        ),
    ],
)
def test_advanced_transport_failure_preempts_diagnostics_without_retry(
    snapshots: list[str | Exception],
    phase: str,
    clicked: list[str],
) -> None:
    transport = ScriptedTransport(snapshots)

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == "MCP_DISCONNECTED"
    assert captured.value.phase == phase
    assert not any(tool == "browser_wait_for" for tool, _ in transport.calls)
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == clicked
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


def test_valid_compact_exhaustion_after_expand_remains_generic() -> None:
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            compact_menu(),
            *settle_exhaustion(compact_menu()),
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == "SELECTOR_AMBIGUITY"
    assert captured.value.phase == "advanced_summary"
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == 12
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "show advanced options"]
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


def test_valid_expanded_exhaustion_after_close_remains_generic() -> None:
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            expanded_menu(),
            *settle_exhaustion(expanded_menu()),
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == "SELECTOR_AMBIGUITY"
    assert captured.value.phase == "closed_landing"
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == 12
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "Pro menu"]
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


@pytest.mark.parametrize(
    ("phase", "prefix", "preceding_action"),
    [
        pytest.param(
            "pro_menu",
            [landing(button_ref="e1", composer_ref="e2")],
            "model picker",
            id="open",
        ),
        pytest.param(
            "advanced_summary",
            [
                landing(button_ref="e1", composer_ref="e2"),
                compact_menu(),
            ],
            "show advanced options",
            id="expand",
        ),
        pytest.param(
            "closed_landing",
            [
                landing(button_ref="e1", composer_ref="e2"),
                compact_menu(),
                expanded_menu(),
            ],
            "Pro menu",
            id="close",
        ),
    ],
)
@pytest.mark.parametrize(
    ("failure", "reason_code"),
    [
        pytest.param(
            snapshot('- alert "Too many requests" [ref=e90]'),
            "STOP_RATE_LIMIT",
            id="structural-stop",
        ),
        pytest.param(
            snapshot(
                '- status "Still loading" [ref=e90]',
                url="https://chatgpt.com.evil.example/",
            ),
            "ORIGIN_MISMATCH",
            id="origin",
        ),
    ],
)
def test_settle_observation_stops_before_any_further_advanced_action(
    phase: str,
    prefix: list[str],
    preceding_action: str,
    failure: str,
    reason_code: str,
) -> None:
    transient = snapshot('- status "Transitioning" [ref=e80]')
    transport = ScriptedTransport([*prefix, transient, failure])

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == reason_code
    assert captured.value.phase == phase
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == 1
    assert (
        sum(
            tool == "browser_click" and arguments.get("element") == preceding_action
            for tool, arguments in transport.calls
        )
        == 1
    )
    assert transport.calls[-1] == ("browser_snapshot", {})
    assert not any(tool == "browser_type" for tool, _ in transport.calls)


UNTRUSTED_SUMMARY_REGIONS = [
    pytest.param(
        (
            '- navigation "Sidebar" [ref=e80]:',
            '  - text: "Model GPT-5.5"',
            '  - statictext: "Effort High"',
        ),
        id="navigation",
    ),
    pytest.param(
        (
            '- complementary "Sidebar" [ref=e80]:',
            '  - generic "Nested" [ref=e81]:',
            '    - text "Model GPT-5.5" [ref=e82]',
            '    - text "Effort High" [ref=e83]',
        ),
        id="nested-sidebar",
    ),
    pytest.param(
        (
            '- citation-preview "Source" [ref=e80]:',
            '  - text "Model GPT-5.5" [ref=e81]',
            '  - text "Effort High" [ref=e82]',
        ),
        id="citation",
    ),
    pytest.param(
        (
            '- heading "You said:" [ref=e80]',
            "- generic [ref=e81]:",
            '  - text "Model GPT-5.5" [ref=e82]',
            '  - text "Effort High" [ref=e83]',
        ),
        id="user-message",
    ),
    pytest.param(
        (
            '- heading "ChatGPT said:" [ref=e80]',
            "- generic [ref=e81]:",
            '  - text "Model GPT-5.5" [ref=e82]',
            '  - text "Effort High" [ref=e83]',
        ),
        id="assistant-response",
    ),
]


@pytest.mark.parametrize("untrusted_lines", UNTRUSTED_SUMMARY_REGIONS)
def test_untrusted_competing_summaries_do_not_duplicate_trusted_evidence(
    untrusted_lines: tuple[str, ...],
) -> None:
    with_untrusted_copies = semantic_expanded_menu(extra_lines=untrusted_lines)
    transport = ScriptedTransport(
        advanced_pre_type_snapshots(expanded_snapshot=with_untrusted_copies)
    )

    _contract, observations, profile_id, _profile, _ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert observations[1]["refs"] == {}
    assert observations[2]["refs"] == {}


@pytest.mark.parametrize("untrusted_lines", UNTRUSTED_SUMMARY_REGIONS)
def test_untrusted_target_summaries_cannot_supply_missing_evidence(
    untrusted_lines: tuple[str, ...],
) -> None:
    target_only_untrusted = tuple(
        line.replace("Model GPT-5.5", "Model GPT-5.6 Sol").replace(
            "Effort High", "Effort Pro"
        )
        for line in untrusted_lines
    )
    bad_summary = semantic_expanded_menu(
        model_lines=(),
        effort_lines=(),
        extra_lines=target_only_untrusted,
    )
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            compact_menu(),
            *settle_exhaustion(bad_summary),
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.phase == "advanced_summary"
    assert not any(tool == "browser_type" for tool, _ in transport.calls)


@pytest.mark.parametrize(
    ("menu_snapshot", "expected_code"),
    [
        pytest.param(
            snapshot(
                '- button "Pro" [ref=e3]',
                '- menu "Pro" [ref=e4]',
            ),
            "ADVANCED_MENU_UNRECOGNIZED",
            id="missing-state-toggle",
        ),
        pytest.param(
            snapshot(
                '- button "Pro" [ref=e3]',
                '- menu "Pro" [ref=e4]',
                '- menuitem "Show advanced options" [ref=e5]',
                '- menuitem "Show advanced options" [ref=e6]',
            ),
            "ADVANCED_EXPAND_CONTROL_INVALID",
            id="duplicate-expand",
        ),
    ],
)
def test_advanced_expansion_state_must_be_unique(
    menu_snapshot: str,
    expected_code: str,
) -> None:
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            *settle_exhaustion(menu_snapshot),
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == expected_code
    assert captured.value.phase == "pro_menu"
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


def test_show_compact_chrome_is_inert_while_exact_expand_remains_clickable() -> None:
    compact_with_chrome = snapshot(
        '- button "Pro" [ref=e3]',
        '- generic "Any container" [ref=e4]',
        '- menuitem "Show advanced options" [ref=e5]',
        '- menuitem "Show compact options" [ref=e6]',
    )
    transport = ScriptedTransport(
        advanced_pre_type_snapshots(menu_snapshot=compact_with_chrome)
    )

    _contract, _observations, profile_id, _profile, _ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert [
        arguments["target"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["e1", "e5", "e6"]


def test_exact_semantic_targets_make_simultaneous_expand_control_irrelevant() -> None:
    compact_with_targets = snapshot(
        '- button "Pro" [ref=e3]',
        '- menuitem "Show advanced options" [ref=e5]',
        '- text "Model GPT-5.6 Sol"',
        '- text "Effort Pro"',
    )
    transport = ScriptedTransport(
        [
            landing(button_ref="e1", composer_ref="e2"),
            compact_with_targets,
            landing(button_ref="e40", composer_ref="e41"),
        ]
    )

    _contract, observations, profile_id, _profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )
    )

    assert profile_id == ADVANCED_PROFILE_ID
    assert observations[1]["refs"] == {}
    assert observations[2]["refs"] == {}
    assert ready["refs"] == {"composer": ["e41"]}
    assert [
        arguments["element"]
        for tool, arguments in transport.calls
        if tool == "browser_click"
    ] == ["model picker", "Pro menu"]
    assert not any(tool == "browser_type" for tool, _ in transport.calls)
    assert not any(tool == "browser_wait_for" for tool, _ in transport.calls)


def test_unrelated_power_menuitem_is_allowed_but_not_required() -> None:
    assert orchestrator._advanced_menu_state(compact_menu())["view"] == "compact"
    assert orchestrator._advanced_menu_state(expanded_menu())["view"] == "expanded"
    without_power = snapshot(*expanded_menu().splitlines()[1:-1])
    assert orchestrator._advanced_menu_state(without_power)["view"] == "expanded"


def test_legacy_menu_container_is_not_an_advanced_profile_marker() -> None:
    legacy_snapshot = snapshot(
        '- button "Pro" [ref=e1]',
        '- menu "Pro" [ref=e2]',
        '- menuitem "Pro" [ref=e3]',
    )
    elements = orchestrator._elements(legacy_snapshot)
    contract = workflow._load_contract(CONTRACT_PATH)

    assert orchestrator._advanced_snapshot_present(legacy_snapshot) is False
    profile_id, profile, target_ref = orchestrator._known_profile(elements, contract)

    assert profile_id == "pro-extended-split-v1"
    assert profile["effort_mode"] == "split"
    assert target_ref == "e3"


def test_legacy_model_click_transport_failure_has_pro_menu_phase() -> None:
    class ModelClickFailureTransport(ScriptedTransport):
        def call(self, tool: str, arguments: dict[str, Any]) -> str:
            if tool == "browser_click" and arguments.get("element") == (
                "Pro model option"
            ):
                copied = dict(arguments)
                self.calls.append((tool, copied))
                self.trace.append(("tool", tool, copied))
                raise orchestrator.TransportUnavailable("MCP_DISCONNECTED")
            return super().call(tool, arguments)

    transport = ModelClickFailureTransport(
        [
            snapshot('- button "Models" [ref=e1]'),
            snapshot(
                '- menuitem "Pro Standard" [ref=e2]',
                '- menuitem "Pro Extended" [ref=e3]',
            ),
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._live_capture(
            prepared={
                "record_path": "/tmp/inert-record.jsonl",
                "run_id": "20260810T000000Z-aaaaaaaaaaaa",
                "prompt_sha256": "a" * 64,
            },
            transport=transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == "MCP_DISCONNECTED"
    assert captured.value.phase == "pro_menu"
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


def test_legacy_post_selection_auth_timeout_has_pro_menu_phase() -> None:
    login = snapshot('- button "Log in" [ref=e90]')
    transport = ScriptedTransport(
        [
            snapshot('- button "Models" [ref=e1]'),
            snapshot(
                '- menuitem "Pro Standard" [ref=e2]',
                '- menuitem "Pro Extended" [ref=e3]',
            ),
            login,
            login,
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._live_capture(
            prepared={
                "record_path": "/tmp/inert-record.jsonl",
                "run_id": "20260810T000000Z-bbbbbbbbbbbb",
                "prompt_sha256": "b" * 64,
            },
            transport=transport,
            interactive_auth_wait_seconds=5,
        )

    assert captured.value.code == "INTERACTIVE_AUTH_TIMEOUT"
    assert captured.value.phase == "pro_menu"
    assert sum(tool == "browser_wait_for" for tool, _arguments in transport.calls) == 1
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


@pytest.mark.parametrize(
    ("post_selection_snapshot", "expected_code"),
    [
        pytest.param(
            snapshot('- alert "Too many requests" [ref=e90]'),
            "STOP_RATE_LIMIT",
            id="structural-stop",
        ),
        pytest.param(
            snapshot(
                '- button "Pro Extended" [ref=e4]',
                '- textbox "Ask anything" [ref=e5]',
                '- button "Send" [ref=e6]',
                url="https://chatgpt.com.evil.example/",
            ),
            "ORIGIN_MISMATCH",
            id="origin",
        ),
        pytest.param(
            snapshot('- button "Unknown" [ref=e4]'),
            "SELECTOR_AMBIGUITY",
            id="selector",
        ),
    ],
)
def test_legacy_post_selection_refusals_have_pro_menu_phase(
    post_selection_snapshot: str,
    expected_code: str,
) -> None:
    transport = ScriptedTransport(
        [
            snapshot('- button "Models" [ref=e1]'),
            snapshot(
                '- menuitem "Pro Standard" [ref=e2]',
                '- menuitem "Pro Extended" [ref=e3]',
            ),
            post_selection_snapshot,
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._live_capture(
            prepared={
                "record_path": "/tmp/inert-record.jsonl",
                "run_id": "20260810T000000Z-cccccccccccc",
                "prompt_sha256": "c" * 64,
            },
            transport=transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == expected_code
    assert captured.value.phase == "pro_menu"
    assert not any(tool == "browser_type" for tool, _arguments in transport.calls)


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
            snapshot('- alert "Too many requests" [ref=e90]'),
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
        [
            *advanced_pre_type_snapshots()[:-1],
            *settle_exhaustion(final_snapshot),
        ]
    )

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == expected_code
    assert captured.value.phase == "closed_landing"
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
    assert click_targets.isdisjoint({"e9", "e10"})
    assert transport.snapshots == []


def test_typed_composer_transition_settles_without_repeating_type() -> None:
    profile = workflow._load_contract(CONTRACT_PATH)["profiles"][ADVANCED_PROFILE_ID]
    transient = snapshot('- status "Preparing Send" [ref=e80]')
    transport = ScriptedTransport(
        [transient, snapshot('- button "Send prompt" [ref=e50]')]
    )
    type_arguments = {
        "element": "ChatGPT composer",
        "target": "e41",
        "text": "RAOS_CHATGPT_PROMPT",
        "submit": False,
    }

    transport.call("browser_type", type_arguments)
    send_ready, send = orchestrator._post_type_send_prompt(
        transport,
        profile,
        composer_ref="e41",
    )

    assert send == "e50"
    assert send_ready["refs"] == {"send": ["e50"]}
    assert transport.calls == [
        ("browser_type", type_arguments),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
    ]


@pytest.mark.parametrize(
    "inert_line",
    [
        '- text "Send prompt" [ref=e50]',
        '- menuitem "Send prompt" [ref=e50]',
        '- button "SEND PROMPT" [ref=e50]',
        '- button " Send prompt " [ref=e50]',
    ],
)
def test_send_prompt_strict_control_ignores_inert_near_copies(
    inert_line: str,
) -> None:
    profile = workflow._load_contract(CONTRACT_PATH)["profiles"][ADVANCED_PROFILE_ID]
    transport = ScriptedTransport(
        [snapshot('- button "Send prompt" [ref=e50]', inert_line)]
    )

    send_ready, send = orchestrator._post_type_send_prompt(
        transport,
        profile,
        composer_ref="e41",
    )

    assert send == "e50"
    assert send_ready["refs"] == {"send": ["e50"]}
    assert transport.calls == [("browser_snapshot", {})]


@pytest.mark.parametrize(
    ("failure", "reason_code"),
    [
        pytest.param(
            snapshot('- alert "Too many requests" [ref=e90]'),
            "STOP_RATE_LIMIT",
            id="structural-stop",
        ),
        pytest.param(
            snapshot(
                '- status "Preparing Send" [ref=e90]',
                url="https://chatgpt.com.evil.example/",
            ),
            "ORIGIN_MISMATCH",
            id="origin",
        ),
    ],
)
def test_typed_composer_settle_stops_without_retrying_type_or_send(
    failure: str,
    reason_code: str,
) -> None:
    profile = workflow._load_contract(CONTRACT_PATH)["profiles"][ADVANCED_PROFILE_ID]
    transient = snapshot('- status "Preparing Send" [ref=e80]')
    transport = ScriptedTransport([transient, failure])
    type_arguments = {
        "element": "ChatGPT composer",
        "target": "e41",
        "text": "RAOS_CHATGPT_PROMPT",
        "submit": False,
    }
    transport.call("browser_type", type_arguments)

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._post_type_send_prompt(
            transport,
            profile,
            composer_ref="e41",
        )

    assert captured.value.code == reason_code
    assert captured.value.phase == "send_control"
    assert sum(tool == "browser_type" for tool, _ in transport.calls) == 1
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == 1
    assert not any(tool == "browser_click" for tool, _ in transport.calls)
    assert transport.calls[-1] == ("browser_snapshot", {})


def test_type_transport_failure_is_typed_composer_phase_without_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class TypeFailureTransport(ScriptedTransport):
        def call(self, tool: str, arguments: dict[str, Any]) -> str:
            if tool == "browser_type":
                copied = dict(arguments)
                self.calls.append((tool, copied))
                self.trace.append(("tool", tool, copied))
                raise orchestrator.TransportUnavailable("MCP_DISCONNECTED")
            return super().call(tool, arguments)

    transport = TypeFailureTransport([])
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
                "record_path": "/tmp/inert-record.jsonl",
                "run_id": "20260805T000000Z-aaaaaaaaaaaa",
                "prompt_sha256": "e" * 64,
            },
            transport=transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == "MCP_DISCONNECTED"
    assert captured.value.phase == "typed_composer"
    assert events == []
    assert [tool for tool, _arguments in transport.calls] == ["browser_type"]


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
            snapshot('- Button "Send prompt" [ref=e50]'),
            "SELECTOR_AMBIGUITY",
            id="wrong-role-case",
        ),
        pytest.param(
            snapshot('- button " Send prompt " [ref=e50]'),
            "SELECTOR_AMBIGUITY",
            id="padded-label",
        ),
        pytest.param(
            snapshot('- button "Send prompt" [disabled] [ref=e50]'),
            "SELECTOR_AMBIGUITY",
            id="disabled",
        ),
        pytest.param(
            snapshot('- button "Send prompt" [ref=e50] [ref=e51]'),
            "SELECTOR_AMBIGUITY",
            id="multiple-ref",
        ),
        pytest.param(
            snapshot('- button "Send prompt" [ref=e50] [ref=invalid]'),
            "SELECTOR_AMBIGUITY",
            id="valid-plus-malformed-ref",
        ),
        pytest.param(
            snapshot(
                '- button "Send prompt" [ref=e50]',
                '- button "Send prompt"',
            ),
            "SELECTOR_AMBIGUITY",
            id="ref-free-duplicate",
        ),
        pytest.param(
            snapshot(
                '- button "Send prompt" [ref=e50]',
                '- button "Send prompt" [ref=invalid]',
            ),
            "SELECTOR_AMBIGUITY",
            id="malformed-ref-duplicate",
        ),
        pytest.param(
            snapshot(
                '- textbox "Chat with ChatGPT" [ref=e41]',
                '- button "Send prompt" [ref=e41]',
            ),
            "SELECTOR_AMBIGUITY",
            id="composer-ref-collision",
        ),
        pytest.param(
            snapshot('- alert "Too many requests" [ref=e90]'),
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
    scripted_results = (
        settle_exhaustion(post_type_result)
        if isinstance(post_type_result, str) and expected_code == "SELECTOR_AMBIGUITY"
        else [post_type_result]
    )
    transport = ScriptedTransport(scripted_results)
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
    assert captured.value.phase == "send_control"
    assert transport.calls[0] == (
        "browser_type",
        {
            "element": "ChatGPT composer",
            "target": "e41",
            "text": "RAOS_CHATGPT_PROMPT",
            "submit": False,
        },
    )
    assert transport.calls[1] == ("browser_snapshot", {})
    assert sum(tool == "browser_type" for tool, _arguments in transport.calls) == 1
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
        transport = ScriptedTransport(settle_exhaustion(snapshot("- Initial tree")))
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
    assert result["phase"] == "send_control"
    assert result["submission_attempted"] is False
    assert len(transports) == 1
    assert not any(tool == "browser_click" for tool, _arguments in transports[0].calls)
    run_dir = root / "chatgpt-pro-runs" / result["run_id"]
    state = json.loads(
        (run_dir / "orchestration-state.v1.json").read_text(encoding="utf-8")
    )
    assert state["submission_attempted"] is False
    assert state["phase"] == "send_control"
    events = [
        json.loads(line)
        for line in (run_dir / "run-record.v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert not any(
        event["event_type"] == "SUBMISSION_INTENT_RECORDED" for event in events
    )
