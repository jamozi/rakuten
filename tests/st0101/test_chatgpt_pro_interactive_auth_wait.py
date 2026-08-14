"""Deterministic evidence for the approved ST-0101 same-window auth wait."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import chatgpt_pro_orchestrator as orchestrator
from scripts import chatgpt_pro_workflow as workflow


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE_PATH = REPOSITORY_ROOT / "Makefile"
README_PATH = REPOSITORY_ROOT / "changes/st-0101/README.md"
SKILL_PATH = Path("/home/minami/.codex/skills/raos-ask-pro/SKILL.md")


class ScriptedTransport:
    """One inert transport serving sanitized snapshots in a fixed order."""

    mode = "LIVE"

    def __init__(self, snapshots: list[str]) -> None:
        self.snapshots = list(snapshots)
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


def landing_snapshot() -> str:
    return snapshot('- button "Models" [ref=e1]')


def combined_model_menu_snapshot() -> str:
    return snapshot(
        '- menuitem "Pro Standard" [ref=e2]',
        '- menuitem "Pro Extended" [ref=e3]',
    )


def combined_ready_snapshot() -> str:
    return snapshot(
        '- button "Pro Extended" [ref=e4]',
        '- textbox "Ask anything" [ref=e5]',
        '- button "Send" [ref=e6]',
        url="https://chatgpt.com/c/same-window",
    )


def advice_text() -> str:
    return json.dumps(
        {
            "schema": "PRO_ADVICE_V1",
            "summary": "Keep the same selected browser transport.",
            "material_delta": True,
            "open_gaps": ["One remaining named gap."],
            "evidence_refs": ["ST-0101 scripted transport"],
            "recommendations": ["Reconcile against canonical evidence."],
            "authority": "UNAPPROVED_ADVICE",
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def completed_response_snapshot(response: str) -> str:
    return snapshot(
        '- article "ChatGPT said" [ref=e7]',
        f"  - text {json.dumps(response)}",
        url="https://chatgpt.com/c/same-window",
    )


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


def private_request(root: Path) -> Path:
    request_root = root / "chatgpt-pro-requests"
    request_root.mkdir(mode=0o700, exist_ok=True)
    request_root.chmod(0o700)
    request = request_root / "interactive-auth-request.txt"
    request.write_text("Review the approved ST-0101 boundary.", encoding="utf-8")
    request.chmod(0o600)
    return request


@pytest.mark.parametrize(
    "blocked_snapshot",
    [
        pytest.param(snapshot('- button "Log in" [ref=e90]'), id="login"),
        pytest.param(snapshot('- alert "CAPTCHA" [ref=e90]'), id="captcha"),
        pytest.param(
            snapshot('- dialog "Session expired" [ref=e90]'),
            id="reauthentication",
        ),
        pytest.param(
            snapshot('- button "Choose an account" [ref=e90]'),
            id="account-selection",
        ),
    ],
)
def test_each_approved_auth_state_uses_only_bounded_wait_and_snapshot(
    blocked_snapshot: str,
) -> None:
    transport = ScriptedTransport([landing_snapshot()])

    cleared, remaining = orchestrator._await_interactive_authentication(
        transport,
        blocked_snapshot,
        total_seconds=5,
        remaining_seconds=5,
    )

    assert cleared == landing_snapshot()
    assert remaining == 0
    assert transport.calls == [
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
    ]
    assert not any(
        tool in {"browser_click", "browser_type"} for tool, _ in transport.calls
    )


def test_one_transport_spans_manual_auth_clear_and_secret_name_only_submission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = advice_text()
    transport = ScriptedTransport(
        [
            snapshot('- button "Log in" [ref=e90]'),
            landing_snapshot(),
            combined_model_menu_snapshot(),
            combined_ready_snapshot(),
            completed_response_snapshot(response),
            completed_response_snapshot(response),
            completed_response_snapshot(response),
        ]
    )
    captured: dict[str, Any] = {}

    def append_event(*_arguments: Any, **_keywords: Any) -> None:
        captured["submission_intent"] = True

    def finalize_transcript(**arguments: Any) -> tuple[Any, ...]:
        captured.update(arguments)
        return (
            {"response_sha256": "a" * 64},
            json.loads(response),
            "b" * 64,
            "c" * 64,
        )

    monkeypatch.setattr(workflow, "_append_event", append_event)
    monkeypatch.setattr(orchestrator, "_finalize_transcript", finalize_transcript)

    result = orchestrator._live_capture(
        prepared={
            "record_path": str(tmp_path / "record.jsonl"),
            "run_id": "20260804T000000Z-aaaaaaaaaaaaaaaa",
            "prompt_sha256": "d" * 64,
        },
        transport=transport,
        interactive_auth_wait_seconds=5,
    )

    assert result[1]["authority"] == "UNAPPROVED_ADVICE"
    assert transport.snapshots == []
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
    type_calls = [
        arguments for tool, arguments in transport.calls if tool == "browser_type"
    ]
    assert type_calls == [
        {
            "element": "ChatGPT composer",
            "target": "e5",
            "text": "RAOS_CHATGPT_PROMPT",
            "submit": False,
        }
    ]
    assert "Keep the same selected browser transport." not in json.dumps(
        transport.calls
    )
    assert captured["submission_intent"] is True
    assert captured["response"] == response
    observations = captured["transcript"]["observations"]
    assert [item["state"] for item in observations] == [
        "landing",
        "model_menu",
        "ready",
        "submitted",
        "complete",
    ]
    assert observations[2]["model_label"] == "Pro Extended"
    assert observations[2]["effort_label"] == "Pro Extended"


def test_auth_timeout_is_bounded_and_remains_pre_submission() -> None:
    blocked = snapshot('- alert "CAPTCHA" [ref=e90]')
    transport = ScriptedTransport([blocked, blocked, blocked])

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=6,
        )

    assert captured.value.code == "INTERACTIVE_AUTH_TIMEOUT"
    assert transport.calls == [
        ("browser_navigate", {"url": "https://chatgpt.com/"}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 1}),
        ("browser_snapshot", {}),
    ]
    assert not any(
        tool in {"browser_click", "browser_type"} for tool, _ in transport.calls
    )


def test_live_ask_propagates_timeout_without_second_transport_or_submission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / ".secrets"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    write_setup_state(root)
    blocked = snapshot('- alert "CAPTCHA" [ref=e90]')
    transports: list[ScriptedTransport] = []

    def transport_factory(
        _wrapper: Path,
        secrets_file: Path,
        browser: str,
    ) -> ScriptedTransport:
        assert secrets_file.is_file()
        assert browser == "edge"
        transport = ScriptedTransport([blocked, blocked])
        transports.append(transport)
        return transport

    monkeypatch.setattr(orchestrator, "StdioMcpTransport", transport_factory)

    exit_code, result = orchestrator.ask(
        private_root=root,
        request_file=private_request(root),
        importance="ordinary",
        fake_scenario=None,
        parent_run_id=None,
        gap_file=None,
        interactive_auth_wait_seconds=1,
    )

    assert exit_code == 0
    assert result["status"] == "PRO_UNAVAILABLE_FALLBACK"
    assert result["reason_code"] == "INTERACTIVE_AUTH_TIMEOUT"
    assert result["phase"] == "landing"
    assert result["submission_attempted"] is False
    assert len(transports) == 1
    assert transports[0].closed is True
    assert not any(
        tool in {"browser_click", "browser_type"}
        for tool, _arguments in transports[0].calls
    )
    state = json.loads(
        (
            root / "chatgpt-pro-runs" / result["run_id"] / "orchestration-state.v1.json"
        ).read_text(encoding="utf-8")
    )
    assert state["phase"] == "landing"
    assert state["submission_attempted"] is False
    assert not list((root / "chatgpt-pro").glob("*.env"))


def test_zero_wait_preserves_immediate_fail_closed_behavior() -> None:
    transport = ScriptedTransport([snapshot('- button "Log in" [ref=e90]')])

    with pytest.raises(orchestrator.LiveUiUnavailable) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=0,
        )

    assert captured.value.code == "STOP_LOGIN"
    assert captured.value.phase == "landing"
    assert transport.calls == [
        ("browser_navigate", {"url": "https://chatgpt.com/"}),
        ("browser_snapshot", {}),
    ]


def test_origin_drift_during_auth_wait_stops_before_input() -> None:
    transport = ScriptedTransport(
        [
            snapshot('- button "Log in" [ref=e90]'),
            snapshot(
                '- button "Log in" [ref=e90]',
                url="https://chatgpt.com.evil.example/",
            ),
        ]
    )

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=5,
        )

    assert captured.value.code == "ORIGIN_MISMATCH"
    assert transport.calls == [
        ("browser_navigate", {"url": "https://chatgpt.com/"}),
        ("browser_snapshot", {}),
        ("browser_wait_for", {"time": 5}),
        ("browser_snapshot", {}),
    ]
    assert not any(
        tool in {"browser_click", "browser_type"} for tool, _ in transport.calls
    )


@pytest.mark.parametrize(
    ("snapshots", "expected_code", "expected_waits"),
    [
        pytest.param(
            [snapshot('- alert "Too many requests" [ref=e90]')],
            "STOP_RATE_LIMIT",
            0,
            id="rate",
        ),
        pytest.param(
            [
                snapshot(
                    '- alert "CAPTCHA" [ref=e90]',
                    '- alert "Too many requests" [ref=e91]',
                )
            ],
            "STOP_RATE_LIMIT",
            0,
            id="rate-overrides-waitable-auth",
        ),
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
            id="model-ambiguity",
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
            id="effort-selector-drift",
        ),
    ],
)
def test_non_authentication_failures_stop_immediately_without_wait_or_input(
    snapshots: list[str],
    expected_code: str,
    expected_waits: int,
) -> None:
    transport = ScriptedTransport(snapshots)

    with pytest.raises(
        (orchestrator.OrchestrationRefusal, workflow.WorkflowRefusal)
    ) as captured:
        orchestrator._inspect_live_pre_submission_ui(
            transport,
            interactive_auth_wait_seconds=900,
        )

    assert captured.value.code == expected_code
    assert sum(tool == "browser_wait_for" for tool, _ in transport.calls) == (
        expected_waits
    )
    assert not any(tool == "browser_type" for tool, _ in transport.calls)
    assert not any(
        tool == "browser_click" and arguments.get("element") == "send"
        for tool, arguments in transport.calls
    )


@pytest.mark.parametrize("value", [0, 900])
def test_cli_accepts_closed_interactive_auth_wait_bounds(value: int) -> None:
    arguments = orchestrator._parser().parse_args(
        ["ask", "--interactive-auth-wait-seconds", str(value)]
    )

    assert arguments.interactive_auth_wait_seconds == value


@pytest.mark.parametrize("value", ["-1", "901", "1.5", "unbounded"])
def test_cli_rejects_invalid_auth_wait_before_any_browser_launch(
    value: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as captured:
        orchestrator._parser().parse_args(
            ["ask", "--interactive-auth-wait-seconds", value]
        )

    assert captured.value.code == 2
    assert "must be an integer from 0 through 900" in capsys.readouterr().err


def test_direct_ask_rejects_invalid_wait_before_layout_or_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_layout(_path: Path) -> dict[str, Path]:
        raise AssertionError("layout reached before wait validation")

    monkeypatch.setattr(orchestrator, "_ensure_layout", unexpected_layout)

    with pytest.raises(orchestrator.OrchestrationRefusal) as captured:
        orchestrator.ask(
            private_root=tmp_path / ".secrets",
            request_file=tmp_path / "request.txt",
            importance="ordinary",
            fake_scenario=None,
            parent_run_id=None,
            gap_file=None,
            interactive_auth_wait_seconds=901,
        )

    assert captured.value.code == "INTERACTIVE_AUTH_WAIT_INVALID"


def test_make_and_guidance_keep_wait_scoped_to_pro_ask() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    pro_region = makefile[
        makefile.index("PRO_REQUEST_FILE ?=") : makefile.index("python-install:")
    ]
    assert "PRO_INTERACTIVE_AUTH_WAIT_SECONDS ?= 900" in pro_region
    assert (
        '--interactive-auth-wait-seconds "$(PRO_INTERACTIVE_AUTH_WAIT_SECONDS)"'
        in pro_region
    )
    assert pro_region.count("--interactive-auth-wait-seconds") == 1
    doctor_region = pro_region[
        pro_region.index("pro-doctor:") : pro_region.index("pro-ask:")
    ]
    resume_region = pro_region[pro_region.index("pro-resume:") :]
    assert "interactive-auth-wait" not in doctor_region
    assert "interactive-auth-wait" not in resume_region

    readme = README_PATH.read_text(encoding="utf-8")
    assert "900" in readme
    assert "same" in readme.casefold()
    assert "do not close" in readme.casefold()
    assert "snapshot" in readme.casefold()
    assert "CDP" in readme
    assert "cookie" in readme.casefold()


@pytest.mark.raos_owner_private
def test_owner_private_skill_keeps_wait_scoped_to_pro_ask() -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    assert "900" in skill
    assert "same" in skill.casefold()
    assert "do not close" in skill.casefold()
    assert "snapshot" in skill.casefold()
    assert "CDP" in skill
    assert "cookie" in skill.casefold()
