"""Fixture and policy evidence for the ST-0101 ChatGPT Pro workflow."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tomllib
from typing import Any

import pytest

from scripts import chatgpt_pro_workflow as workflow


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPOSITORY_ROOT / "changes/st-0101/chatgpt-pro-known-ui.v1.json"
CONFIG_PATH = REPOSITORY_ROOT / ".codex/config.toml"
WRAPPER_PATH = REPOSITORY_ROOT / "scripts/chatgpt_pro_mcp.sh"
PROMPT_TEXT = "Decide the narrow interface boundary for the approved Story."
RESPONSE_TEXT = "Proposal: retain the interface boundary and add a negative test."


def synthetic_openai_credential() -> str:
    """Build a non-secret scanner fixture without a key-shaped source literal."""
    return "s" + "k-proj-" + "aB3dE5fG7hJ9kL2mN4pQ6rS8"


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
    url: str = "https://chatgpt.com/c/example-run",
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


def split_transcript() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "profile_id": "pro-extended-split-v1",
        "observations": [
            observation("landing", refs={"model_picker": ["e11"]}),
            observation(
                "model_menu",
                option_labels=["Pro"],
                refs={"target_model": ["e12"]},
            ),
            observation(
                "model_selected",
                model_label="Pro",
                refs={"effort_picker": ["e13"]},
            ),
            observation(
                "effort_menu",
                model_label="Pro",
                option_labels=["Standard", "Extended"],
                refs={"target_effort": ["e14"]},
            ),
            observation(
                "ready",
                model_label="Pro",
                effort_label="Extended",
                refs={"composer": ["e15"], "send": ["e16"]},
            ),
            observation(
                "submitted",
                model_label="Pro",
                effort_label="Extended",
                generating=True,
            ),
            observation(
                "complete",
                model_label="Pro",
                effort_label="Extended",
                generating=False,
                response_complete=True,
                refs={"assistant_response": ["e17"]},
            ),
        ],
    }


def write_inputs(
    root: Path,
    transcript: dict[str, Any] | None = None,
    *,
    prompt: str = PROMPT_TEXT,
    response: str = RESPONSE_TEXT,
) -> tuple[Path, Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    prompt_path = root / "prompt.txt"
    response_path = root / "response.txt"
    transcript_path = root / "transcript.json"
    prompt_path.write_text(prompt, encoding="utf-8")
    response_path.write_text(response, encoding="utf-8")
    transcript_path.write_text(
        json.dumps(combined_transcript() if transcript is None else transcript),
        encoding="utf-8",
    )
    return prompt_path, response_path, transcript_path


def private_roots(root: Path) -> tuple[Path, Path]:
    secret_root = root / ".secrets/chatgpt-pro"
    run_root = root / ".secrets/chatgpt-pro-runs"
    secret_root.parent.mkdir(parents=True, mode=0o700)
    secret_root.parent.chmod(0o700)
    return secret_root, run_root


def prepare(root: Path, prompt_path: Path) -> dict[str, str]:
    secret_root, run_root = private_roots(root)
    return workflow.prepare_run(
        prompt_path=prompt_path,
        contract_path=CONTRACT_PATH,
        secret_root=secret_root,
        run_root=run_root,
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://chatgpt.com/",
        "https://chatgpt.com.evil.example/",
        "https://evil.example/?next=https://chatgpt.com",
        "https://user@chatgpt.com/",
        "https://chatgpt.com:443/",
        "file:///home/minami/rakuten/prompt.txt",
        "javascript:alert(1)",
        "//chatgpt.com/",
        "",
    ],
)
def test_exact_origin_rejects_every_non_exact_serialized_origin(url: str) -> None:
    assert workflow.exact_origin(url) is False


@pytest.mark.parametrize(
    "url",
    [
        "https://chatgpt.com/",
        "https://chatgpt.com/c/abc",
        "https://chatgpt.com/?model=pro",
    ],
)
def test_exact_origin_accepts_only_chatgpt_https_paths(url: str) -> None:
    assert workflow.exact_origin(url) is True


@pytest.mark.parametrize(
    "transcript_factory,expected_model,expected_effort",
    [
        (combined_transcript, "Pro Extended", "Pro Extended"),
        (split_transcript, "Pro", "Extended"),
    ],
)
def test_known_profiles_require_visible_pro_and_maximum_effort(
    transcript_factory: Any,
    expected_model: str,
    expected_effort: str,
) -> None:
    contract = workflow._load_contract(CONTRACT_PATH)
    transcript = transcript_factory()
    actions = workflow.validate_transcript(transcript, contract)
    assert any(
        action["tool"] == "browser_type"
        and action["arguments"]["text"] == "RAOS_CHATGPT_PROMPT"
        and action["arguments"]["submit"] is False
        for action in actions
    )
    ready = next(
        item for item in transcript["observations"] if item["state"] == "ready"
    )
    assert ready["model_label"] == expected_model
    assert ready["effort_label"] == expected_effort


def test_lower_effort_is_refused_before_submission() -> None:
    contract = workflow._load_contract(CONTRACT_PATH)
    transcript = split_transcript()
    transcript["observations"][4]["effort_label"] = "Standard"
    with pytest.raises(workflow.WorkflowRefusal, match="PRO_OR_MAX_EFFORT"):
        workflow.validate_transcript(transcript, contract)


def test_unknown_model_option_set_is_refused() -> None:
    contract = workflow._load_contract(CONTRACT_PATH)
    transcript = combined_transcript()
    transcript["observations"][1]["option_labels"].append("Pro Unlimited")
    with pytest.raises(workflow.WorkflowRefusal, match="MODEL_OPTIONS_AMBIGUOUS"):
        workflow.validate_transcript(transcript, contract)


def test_duplicate_or_stale_selector_is_refused() -> None:
    contract = workflow._load_contract(CONTRACT_PATH)
    transcript = combined_transcript()
    transcript["observations"][1]["refs"] = {"target_model": ["e2", "e9"]}
    with pytest.raises(workflow.WorkflowRefusal, match="SELECTOR_AMBIGUITY"):
        workflow.validate_transcript(transcript, contract)


@pytest.mark.parametrize(
    "stop_state",
    [
        "account_ambiguity",
        "captcha",
        "login",
        "rate_limit",
        "reauthentication",
        "selector_drift",
        "unknown_ui",
    ],
)
def test_all_approved_stop_states_fail_closed(stop_state: str) -> None:
    contract = workflow._load_contract(CONTRACT_PATH)
    transcript = combined_transcript()
    transcript["observations"][0]["stop_state"] = stop_state
    with pytest.raises(workflow.WorkflowRefusal) as captured:
        workflow.validate_transcript(transcript, contract)
    assert captured.value.code == f"STOP_{stop_state.upper()}"


def test_unauthenticated_state_fails_closed() -> None:
    contract = workflow._load_contract(CONTRACT_PATH)
    transcript = combined_transcript()
    transcript["observations"][0]["authenticated"] = False
    with pytest.raises(workflow.WorkflowRefusal, match="STOP_LOGIN"):
        workflow.validate_transcript(transcript, contract)


def test_successful_fixture_hash_binds_prompt_response_and_proposal(
    tmp_path: Path,
) -> None:
    prompt_path, response_path, transcript_path = write_inputs(tmp_path / "inputs")
    prepared = prepare(tmp_path, prompt_path)
    evidence = workflow.execute_fixture(
        prepared=prepared,
        transcript_path=transcript_path,
        response_path=response_path,
        contract_path=CONTRACT_PATH,
    )

    secret_file = Path(prepared["secrets_file"])
    assert stat.S_IMODE(secret_file.stat().st_mode) == 0o600
    assert PROMPT_TEXT in secret_file.read_text(encoding="utf-8")

    record_path = Path(evidence["record_path"])
    proposal_path = Path(evidence["proposal_path"])
    assert stat.S_IMODE(record_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(proposal_path.stat().st_mode) == 0o600
    record_text = record_path.read_text(encoding="utf-8")
    proposal_text = proposal_path.read_text(encoding="utf-8")
    assert PROMPT_TEXT not in record_text
    assert PROMPT_TEXT not in proposal_text
    assert evidence["prompt_sha256"] == hashlib.sha256(PROMPT_TEXT.encode()).hexdigest()
    assert (
        evidence["response_sha256"]
        == hashlib.sha256(RESPONSE_TEXT.encode()).hexdigest()
    )
    assert "UNAPPROVED_PROPOSAL" in proposal_text
    assert "cannot authorize" in proposal_text
    assert "DESIGN_HANDOFF_V1" not in proposal_text

    lines = record_text.splitlines()
    count, last_hash = workflow._verify_events(lines, prepared["run_id"])
    assert count == len(lines) >= 9
    assert last_hash == evidence["final_event_sha256"]
    final = json.loads(lines[-1])
    assert final["payload"]["prompt_sha256"] == evidence["prompt_sha256"]
    assert final["payload"]["response_sha256"] == evidence["response_sha256"]
    assert final["payload"]["status"] == "UNAPPROVED_PROPOSAL"


def test_fixture_cli_emits_only_sanitized_one_line_result(tmp_path: Path) -> None:
    prompt_path, response_path, transcript_path = write_inputs(tmp_path / "inputs")
    secret_root, run_root = private_roots(tmp_path)
    process = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts/chatgpt_pro_workflow.py"),
            "fixture",
            "--prompt-file",
            str(prompt_path),
            "--response-file",
            str(response_path),
            "--transcript",
            str(transcript_path),
            "--secret-root",
            str(secret_root),
            "--run-root",
            str(run_root),
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
    assert PROMPT_TEXT not in process.stdout
    assert RESPONSE_TEXT not in process.stdout
    result = json.loads(process.stdout)
    assert result["status"] == "PASS"
    assert result["mode"] == "fixture"


@pytest.mark.parametrize(
    "field_text,expected_code",
    [
        (
            f"Use key {synthetic_openai_credential()} now.",
            "PROMPT_SENSITIVE_OR_INVALID",
        ),
        (
            "Set-Cookie: __Secure-session=abcdefghijklmnopqrstu",
            "RESPONSE_SENSITIVE_OR_INVALID",
        ),
        (
            '{"cookies": [{"name":"x"}], "origins": [{"origin":"x"}]}',
            "RESPONSE_SENSITIVE_OR_INVALID",
        ),
    ],
)
def test_secret_or_browser_session_data_never_enters_artifacts(
    tmp_path: Path,
    field_text: str,
    expected_code: str,
) -> None:
    prompt = field_text if expected_code.startswith("PROMPT") else PROMPT_TEXT
    response = field_text if expected_code.startswith("RESPONSE") else RESPONSE_TEXT
    prompt_path, response_path, transcript_path = write_inputs(
        tmp_path / "inputs", prompt=prompt, response=response
    )
    if expected_code.startswith("PROMPT"):
        with pytest.raises(workflow.WorkflowRefusal) as captured:
            prepare(tmp_path, prompt_path)
    else:
        prepared = prepare(tmp_path, prompt_path)
        with pytest.raises(workflow.WorkflowRefusal) as captured:
            workflow.execute_fixture(
                prepared=prepared,
                transcript_path=transcript_path,
                response_path=response_path,
                contract_path=CONTRACT_PATH,
            )
    assert captured.value.code == expected_code


def test_tampered_append_only_record_is_rejected(tmp_path: Path) -> None:
    prompt_path, _, _ = write_inputs(tmp_path / "inputs")
    prepared = prepare(tmp_path, prompt_path)
    record_path = Path(prepared["record_path"])
    content = record_path.read_text(encoding="utf-8")
    record_path.write_text(content.replace("PREPARED", "ALTERED", 1), encoding="utf-8")
    with pytest.raises(workflow.WorkflowRefusal, match="RUN_RECORD_INVALID"):
        workflow._append_event(
            record_path,
            prepared["run_id"],
            "SHOULD_NOT_APPEND",
            {"status": "REFUSED"},
        )


def test_symlinked_secret_root_is_rejected(tmp_path: Path) -> None:
    prompt_path, _, _ = write_inputs(tmp_path / "inputs")
    outside = tmp_path / "outside"
    outside.mkdir()
    secret_parent = tmp_path / ".secrets"
    secret_parent.mkdir(mode=0o700)
    (secret_parent / "chatgpt-pro").symlink_to(outside, target_is_directory=True)
    run_root = tmp_path / ".secrets/chatgpt-pro-runs"
    with pytest.raises(workflow.WorkflowRefusal, match="PATH_SYMLINK"):
        workflow.prepare_run(
            prompt_path=prompt_path,
            contract_path=CONTRACT_PATH,
            secret_root=secret_parent / "chatgpt-pro",
            run_root=run_root,
        )


def test_secret_parent_must_be_owner_private(tmp_path: Path) -> None:
    prompt_path, _, _ = write_inputs(tmp_path / "inputs")
    secret_parent = tmp_path / ".secrets"
    secret_parent.mkdir(mode=0o755)
    run_root = tmp_path / ".secrets/chatgpt-pro-runs"
    with pytest.raises(workflow.WorkflowRefusal, match="PRIVATE_DIRECTORY_MODE"):
        workflow.prepare_run(
            prompt_path=prompt_path,
            contract_path=CONTRACT_PATH,
            secret_root=secret_parent / "chatgpt-pro",
            run_root=run_root,
        )


def test_project_config_exposes_only_the_approved_playwright_tools() -> None:
    config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    playwright = config["mcp_servers"]["playwright"]
    expected_tools = {
        "browser_navigate",
        "browser_snapshot",
        "browser_click",
        "browser_type",
        "browser_wait_for",
        "browser_close",
    }
    assert playwright["enabled"] is False
    assert playwright["command"] == "/bin/bash"
    assert playwright["args"] == ["/home/minami/rakuten/scripts/chatgpt_pro_mcp.sh"]
    assert "env_vars" not in playwright
    assert set(playwright["enabled_tools"]) == expected_tools
    assert {
        "browser_tabs",
        "browser_evaluate",
        "browser_run_code_unsafe",
        "browser_file_upload",
        "browser_storage_state",
    }.issubset(playwright["disabled_tools"])
    assert set(playwright["tools"]) == expected_tools
    assert all(
        tool["approval_mode"] == "approve" for tool in playwright["tools"].values()
    )


def test_transport_wrapper_is_exact_origin_pinned_and_fail_closed() -> None:
    wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
    for required in (
        "--allowed-origins https://chatgpt.com",
        "--block-service-workers",
        "--snapshot-mode none",
        "--image-responses omit",
        "--codegen none",
        "--secrets",
        "--user-data-dir",
        "env -u DEBUG",
        "/home/minami/.nvm/versions/node/v24.18.1/bin/node",
        "chatgpt-pro-mcp-runtime",
        "scripts/chatgpt_pro_mcp_runtime",
        "verify_runtime.py",
    ):
        assert required in wrapper
    for prohibited in (
        "--extension",
        "--save-session",
        "--allow-unrestricted-file-access",
        "--ignore-https-errors",
        "--no-sandbox",
        "npx_path",
        "/.npm/_npx",
        "--yes",
    ):
        assert prohibited not in wrapper
    process = subprocess.run(
        ["/bin/bash", str(WRAPPER_PATH)],
        cwd=REPOSITORY_ROOT,
        env={"PATH": os.environ.get("PATH", "")},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert process.returncode == 64
    assert process.stdout == ""
    assert process.stderr == (
        "chatgpt-pro-mcp: fail-closed launch refusal (invalid-browser)\n"
    )
    runtime_source = REPOSITORY_ROOT / "scripts/chatgpt_pro_mcp_runtime"
    package = json.loads((runtime_source / "package.json").read_text(encoding="utf-8"))
    lock = json.loads(
        (runtime_source / "package-lock.json").read_text(encoding="utf-8")
    )
    assert package["dependencies"] == {"@playwright/mcp": "0.0.78"}
    assert lock["packages"]["node_modules/@playwright/mcp"]["version"] == "0.0.78"


def test_repository_policy_keeps_proposals_unapproved_and_live_separate() -> None:
    policy = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    normalized_policy = " ".join(policy.split())
    assert "exact `https://chatgpt.com` origin" in policy
    assert "maximum available Pro" in policy
    assert "types only the MCP secret name" in normalized_policy
    assert (
        "no codex restart or per-run exported variable" in normalized_policy.casefold()
    )
    assert "`UNAPPROVED_PROPOSAL`" in policy
    assert "Neither Pro content nor a handoff resolves a Canonical Open Decision" in (
        normalized_policy
    )
    assert "Fixture/dry-run evidence, a live smoke, and formal" in normalized_policy
