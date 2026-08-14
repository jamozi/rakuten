"""Deterministic evidence for the approved ST-0101 initial UI settle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts import chatgpt_pro_orchestrator as orchestrator
from scripts import chatgpt_pro_workflow as workflow


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE_PATH = REPOSITORY_ROOT / "Makefile"
WRAPPER_PATH = REPOSITORY_ROOT / "scripts/chatgpt_pro_mcp.sh"
README_PATH = REPOSITORY_ROOT / "changes/st-0101/README.md"
SKILL_PATH = Path("/home/minami/.codex/skills/raos-ask-pro/SKILL.md")


class ScriptedTransport:
    """One inert transport serving sanitized snapshots in a fixed order."""

    mode = "LIVE"

    def __init__(self, snapshots: list[str], secret_file: Path | None = None) -> None:
        self.snapshots = list(snapshots)
        self.secret_file = secret_file
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


def snapshot(*lines: str, url: str = "https://chatgpt.com/") -> str:
    return "\n".join((f"- Page URL: {url}", *lines))


def unknown_snapshot() -> str:
    return snapshot("- Initial accessible tree is not ready")


def ambiguous_landing_snapshot() -> str:
    return snapshot(
        '- button "Models" [ref=e1]',
        '- button "Models" [ref=e2]',
    )


def landing_snapshot() -> str:
    return snapshot('- button "Models" [ref=e1]')


def doctor_ready_snapshot() -> str:
    return snapshot(
        '- button "Pro" [ref=e1]',
        '- textbox "Ask ChatGPT" [ref=e2]',
    )


def combined_model_menu_snapshot() -> str:
    return snapshot(
        '- menuitem "Pro Standard" [ref=e2]',
        '- menuitem "Pro Extended" [ref=e3]',
    )


def combined_ready_snapshot() -> str:
    return snapshot(
        '- button "Pro Extended" [ref=e4]',
        '- textbox "Ask ChatGPT" [ref=e5]',
        '- button "Send" [ref=e6]',
        url="https://chatgpt.com/c/initial-settle",
    )


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
            "browser_executable": str(orchestrator._browser_executable("edge")),
            "profile": layout["edge_profile"].name,
            "updated_at": "2026-08-05T00:00:00Z",
        },
    )


def install_doctor_transport(
    root: Path,
    snapshots: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> list[ScriptedTransport]:
    write_setup_state(root)
    transports: list[ScriptedTransport] = []

    def factory(
        _wrapper: Path,
        secret_file: Path,
        browser: str,
    ) -> ScriptedTransport:
        assert browser == "edge"
        assert secret_file.is_file()
        transport = ScriptedTransport(snapshots, secret_file)
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "DEFAULT_PRIVATE_ROOT", root)
    monkeypatch.setattr(
        orchestrator, "_verify_private_runtime", lambda _root: {"status": "ready"}
    )
    monkeypatch.setattr(orchestrator, "StdioMcpTransport", factory)
    return transports


def test_doctor_settles_unknown_once_then_recognizes_known_ui(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = private_root(tmp_path)
    transports = install_doctor_transport(
        root,
        [unknown_snapshot(), doctor_ready_snapshot()],
        monkeypatch,
    )

    result = orchestrator.doctor(
        private_root=root,
        fake_scenario=None,
        wrapper=orchestrator.DEFAULT_WRAPPER,
    )

    assert result["status"] == "READY"
    assert len(transports) == 1
    assert transports[0].calls == [
        ("browser_navigate", {"url": "https://chatgpt.com/"}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
    ]
    assert transports[0].closed is True
    assert transports[0].secret_file is not None
    assert not transports[0].secret_file.exists()


@pytest.mark.parametrize(
    ("initial_snapshot", "expected_code", "returns_result"),
    [
        pytest.param(
            snapshot('- button "Log in" [ref=e90]'), "STOP_LOGIN", True, id="login"
        ),
        pytest.param(
            snapshot('- alert "CAPTCHA" [ref=e90]'),
            "STOP_CAPTCHA",
            True,
            id="captcha",
        ),
        pytest.param(
            snapshot('- alert "Too many requests" [ref=e90]'),
            "STOP_RATE_LIMIT",
            True,
            id="rate-limit",
        ),
        pytest.param(
            snapshot(url="https://chatgpt.com.evil.example/"),
            "ORIGIN_MISMATCH",
            False,
            id="origin",
        ),
    ],
)
def test_doctor_initial_stops_never_enter_settle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    initial_snapshot: str,
    expected_code: str,
    returns_result: bool,
) -> None:
    root = private_root(tmp_path)
    transports = install_doctor_transport(root, [initial_snapshot], monkeypatch)

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

    assert transports[0].calls == [
        ("browser_navigate", {"url": "https://chatgpt.com/"}),
        ("browser_snapshot", {}),
    ]


@pytest.mark.parametrize(
    ("second_snapshot", "expected_code", "returns_result"),
    [
        pytest.param(
            snapshot('- button "Log in" [ref=e90]'), "STOP_LOGIN", True, id="login"
        ),
        pytest.param(
            snapshot('- alert "CAPTCHA" [ref=e90]'),
            "STOP_CAPTCHA",
            True,
            id="captcha",
        ),
        pytest.param(
            snapshot('- alert "Too many requests" [ref=e90]'),
            "STOP_RATE_LIMIT",
            True,
            id="rate-limit",
        ),
        pytest.param(
            snapshot(url="https://chatgpt.com.evil.example/"),
            "ORIGIN_MISMATCH",
            False,
            id="origin",
        ),
    ],
)
def test_doctor_retry_snapshot_revalidates_origin_and_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    second_snapshot: str,
    expected_code: str,
    returns_result: bool,
) -> None:
    root = private_root(tmp_path)
    transports = install_doctor_transport(
        root,
        [unknown_snapshot(), second_snapshot],
        monkeypatch,
    )

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

    assert transports[0].calls == [
        ("browser_navigate", {"url": "https://chatgpt.com/"}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
    ]


@pytest.mark.parametrize(
    "unavailable_snapshot",
    [
        pytest.param(unknown_snapshot(), id="unknown"),
        pytest.param(
            snapshot(
                '- textbox "Ask ChatGPT" [ref=e1]',
                '- textbox "ASK CHATGPT" [ref=e2]',
            ),
            id="ambiguous",
        ),
    ],
)
def test_doctor_persistent_unknown_or_ambiguity_stops_after_one_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unavailable_snapshot: str,
) -> None:
    root = private_root(tmp_path)
    transports = install_doctor_transport(
        root,
        [unavailable_snapshot, unavailable_snapshot],
        monkeypatch,
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.doctor(
            private_root=root,
            fake_scenario=None,
            wrapper=orchestrator.DEFAULT_WRAPPER,
        )

    assert captured.value.code == "UNKNOWN_UI"
    assert transports[0].calls == [
        ("browser_navigate", {"url": "https://chatgpt.com/"}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
    ]
    assert not any(
        tool in {"browser_click", "browser_type"}
        for tool, _arguments in transports[0].calls
    )


@pytest.mark.parametrize(
    "initial_snapshot",
    [
        pytest.param(unknown_snapshot(), id="unknown"),
        pytest.param(ambiguous_landing_snapshot(), id="ambiguous"),
    ],
)
def test_pro_ask_initial_landing_settles_once_on_same_transport(
    initial_snapshot: str,
) -> None:
    transport = ScriptedTransport(
        [
            initial_snapshot,
            landing_snapshot(),
            combined_model_menu_snapshot(),
            combined_ready_snapshot(),
        ]
    )

    _contract, observations, _profile_id, _profile, ready = (
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=900,
        )
    )

    assert [item["state"] for item in observations] == [
        "landing",
        "model_menu",
        "ready",
    ]
    assert ready["refs"] == {"composer": ["e5"], "send": ["e6"]}
    assert transport.calls[:4] == [
        ("browser_navigate", {"url": "https://chatgpt.com/"}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
    ]
    assert not any(
        tool in {"browser_click", "browser_type"}
        for tool, _arguments in transport.calls[:4]
    )
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == 1


@pytest.mark.parametrize(
    "unavailable_snapshot",
    [
        pytest.param(unknown_snapshot(), id="unknown"),
        pytest.param(ambiguous_landing_snapshot(), id="ambiguous"),
    ],
)
def test_pro_ask_persistent_initial_failure_stops_once_without_input(
    unavailable_snapshot: str,
) -> None:
    transport = ScriptedTransport([unavailable_snapshot, unavailable_snapshot])

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=900,
        )

    assert captured.value.code == "SELECTOR_AMBIGUITY"
    assert transport.calls == [
        ("browser_navigate", {"url": "https://chatgpt.com/"}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
    ]
    assert not any(
        tool in {"browser_click", "browser_type"}
        for tool, _arguments in transport.calls
    )


@pytest.mark.parametrize(
    ("second_snapshot", "auth_wait_seconds", "expected_code"),
    [
        pytest.param(
            snapshot('- alert "Too many requests" [ref=e90]'),
            900,
            "STOP_RATE_LIMIT",
            id="rate-limit",
        ),
        pytest.param(
            snapshot('- alert "CAPTCHA" [ref=e90]'),
            0,
            "STOP_CAPTCHA",
            id="captcha",
        ),
        pytest.param(
            snapshot(url="https://chatgpt.com.evil.example/"),
            900,
            "ORIGIN_MISMATCH",
            id="origin",
        ),
    ],
)
def test_pro_ask_retry_snapshot_revalidates_origin_and_stops_without_input(
    second_snapshot: str,
    auth_wait_seconds: int,
    expected_code: str,
) -> None:
    transport = ScriptedTransport([unknown_snapshot(), second_snapshot])

    with pytest.raises(
        (orchestrator.OrchestrationRefusal, workflow.WorkflowRefusal)
    ) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=auth_wait_seconds,
        )

    assert captured.value.code == expected_code
    assert transport.calls == [
        ("browser_navigate", {"url": "https://chatgpt.com/"}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
    ]
    assert not any(
        tool in {"browser_click", "browser_type"}
        for tool, _arguments in transport.calls
    )


@pytest.mark.parametrize(
    ("snapshots", "expected_code", "expected_waits"),
    [
        pytest.param(
            [
                landing_snapshot(),
                *[
                    snapshot(
                        '- menuitem "Pro Standard" [ref=e2]',
                        '- menuitem "Pro Extended" [ref=e3]',
                        '- menuitem "Pro" [ref=e4]',
                    )
                    for _ in range(
                        orchestrator.PRE_SUBMISSION_SETTLE_ADDITIONAL_OBSERVATIONS + 1
                    )
                ],
            ],
            "MODEL_OPTIONS_AMBIGUOUS",
            12,
            id="after-model-picker-click",
        ),
        pytest.param(
            [
                landing_snapshot(),
                snapshot('- menuitem "Pro" [ref=e2]'),
                snapshot(
                    '- button "Pro" [ref=e3]',
                    '- button "Effort" [ref=e4]',
                    '- button "Reasoning effort" [ref=e5]',
                ),
            ],
            "SELECTOR_AMBIGUITY",
            0,
            id="after-model-click",
        ),
        pytest.param(
            [
                landing_snapshot(),
                snapshot('- menuitem "Pro" [ref=e2]'),
                snapshot(
                    '- button "Pro" [ref=e3]',
                    '- button "Effort" [ref=e4]',
                ),
                snapshot(
                    '- option "Standard" [ref=e5]',
                    '- option "Extended" [ref=e6]',
                    '- option "Extended" [ref=e7]',
                ),
            ],
            "SELECTOR_AMBIGUITY",
            0,
            id="after-effort-picker-click",
        ),
    ],
)
def test_only_approved_post_click_transition_receives_bounded_settle(
    snapshots: list[str],
    expected_code: str,
    expected_waits: int,
) -> None:
    transport = ScriptedTransport(snapshots)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=900,
        )

    assert captured.value.code == expected_code
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == (
        expected_waits
    )
    assert not any(tool == "browser_type" for tool, _ in transport.calls)
    assert any(tool == "browser_click" for tool, _ in transport.calls)


def test_initial_settle_is_fixed_and_has_no_runtime_configuration() -> None:
    assert orchestrator.INITIAL_UI_SETTLE_SECONDS == 5
    source = (REPOSITORY_ROOT / "scripts/chatgpt_pro_orchestrator.py").read_text(
        encoding="utf-8"
    )
    helper = source[
        source.index("def _settle_initial_ui_once(") : source.index(
            "\ndef _doctor_snapshot(", source.index("def _settle_initial_ui_once(")
        )
    ]
    assert helper.count("browser_wait_for") == 1
    assert helper.count("browser_snapshot") == 1
    assert "for " not in helper
    assert "while " not in helper

    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    pro_region = makefile[
        makefile.index("PRO_REQUEST_FILE ?=") : makefile.index("python-install:")
    ]
    wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
    parser_source = source[source.index("def _parser(") : source.index("\ndef main(")]
    transport_source = source[
        source.index("class StdioMcpTransport:") : source.index("\ndef _extract_url(")
    ]
    for text in (pro_region, wrapper, parser_source, transport_source):
        assert "initial-ui-settle" not in text.casefold()
        assert "initial_ui_settle" not in text.casefold()


def test_initial_settle_guidance_preserves_narrow_boundary() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    lowered = readme.casefold()
    assert "five-second" in lowered
    assert "exactly one" in lowered
    assert "initial" in lowered
    assert "no click" in lowered
    assert "not an authentication wait" in lowered


@pytest.mark.raos_owner_private
def test_owner_private_skill_preserves_initial_settle_boundary() -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    lowered = skill.casefold()
    assert "five-second" in lowered
    assert "exactly one" in lowered
    assert "initial" in lowered
    assert "no click" in lowered
    assert "not an authentication wait" in lowered
