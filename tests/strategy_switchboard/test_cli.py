from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import select_all_story_strategy as cli


def _write_json(path: Path, value: object) -> Path:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return path


def _safe_profile(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "profile.json",
        {
            "fallback_policy": "safe_only",
            "overrides": {},
            "preferred_tier": "safe",
            "profile_id": "safe-local",
        },
    )


def _local_context(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "context.json",
        {
            "approvals": [],
            "capabilities": [],
            "environment": "local",
            "evidence": [],
        },
    )


def test_cli_selects_safe_candidate_from_explicit_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cli.main(
        [
            "--root",
            str(cli.REPOSITORY_ROOT),
            "--boundary",
            "OD-001",
            "--profile",
            str(_safe_profile(tmp_path)),
            "--context",
            str(_local_context(tmp_path)),
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert captured.err == ""
    document = json.loads(captured.out)
    assert document["status"] == "PASS"
    assert document["mode"] == "selection"
    assert document["decision"]["selected_strategy_id"] == (
        "OD-001:synthetic-fixture"
    )
    assert len(document["catalog_sha256"]) == 64


def test_cli_executes_safe_plan_without_recording_payload_content(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = _write_json(tmp_path / "payload.json", {"secret_value": "not-recorded"})

    result = cli.main(
        [
            "--root",
            str(cli.REPOSITORY_ROOT),
            "--boundary",
            "OD-001",
            "--profile",
            str(_safe_profile(tmp_path)),
            "--context",
            str(_local_context(tmp_path)),
            "--payload",
            str(payload),
            "--execute",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert captured.err == ""
    assert "not-recorded" not in captured.out
    document = json.loads(captured.out)
    assert document["execution"]["status"] == "planned"
    assert document["execution"]["payload_sha256"]


def test_cli_reports_advanced_gate_refusal_as_stable_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile = _write_json(
        tmp_path / "advanced.json",
        {
            "fallback_policy": "fail_closed",
            "overrides": {},
            "preferred_tier": "advanced",
            "profile_id": "advanced-external",
        },
    )

    result = cli.main(
        [
            "--root",
            str(cli.REPOSITORY_ROOT),
            "--boundary",
            "OD-001",
            "--profile",
            str(profile),
            "--context",
            str(_local_context(tmp_path)),
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert captured.out == ""
    document = json.loads(captured.err)
    assert document == {
        "boundary_id": "OD-001",
        "error_code": "STRATEGY_REQUIREMENTS_UNSATISFIED",
        "status": "REFUSED",
        "strategy_id": "OD-001:approved-multi-category",
    }


def test_cli_execute_refuses_missing_advanced_adapter_after_complete_gates(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile = _write_json(
        tmp_path / "advanced.json",
        {
            "fallback_policy": "fail_closed",
            "overrides": {},
            "preferred_tier": "advanced",
            "profile_id": "advanced-external",
        },
    )
    context = _write_json(
        tmp_path / "production.json",
        {
            "approvals": ["OD-001", "production-use"],
            "capabilities": ["external-io"],
            "environment": "production",
            "evidence": ["category-portfolio-evidence"],
        },
    )
    payload = _write_json(tmp_path / "payload.json", {"version": "reviewed-v1"})

    result = cli.main(
        [
            "--root",
            str(cli.REPOSITORY_ROOT),
            "--boundary",
            "OD-001",
            "--profile",
            str(profile),
            "--context",
            str(context),
            "--payload",
            str(payload),
            "--execute",
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert captured.out == ""
    document = json.loads(captured.err)
    assert document["error_code"] == "STRATEGY_ADAPTER_MISSING"
    assert document["strategy_id"] == "OD-001:approved-multi-category"


def test_cli_rejects_symlinked_configuration_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile = _safe_profile(tmp_path)
    linked = tmp_path / "linked-profile.json"
    linked.symlink_to(profile.name)

    result = cli.main(
        [
            "--root",
            str(cli.REPOSITORY_ROOT),
            "--boundary",
            "OD-001",
            "--profile",
            str(linked),
            "--context",
            str(_local_context(tmp_path)),
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert captured.out == ""
    assert json.loads(captured.err)["error_code"] == "STRATEGY_INPUT_FILE_INVALID"


def test_cli_rejects_unknown_boundary_without_internal_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cli.main(
        [
            "--root",
            str(cli.REPOSITORY_ROOT),
            "--boundary",
            "ST-9999",
            "--profile",
            str(_safe_profile(tmp_path)),
            "--context",
            str(_local_context(tmp_path)),
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert json.loads(captured.err)["error_code"] == "STRATEGY_BOUNDARY_UNKNOWN"


def test_cli_rejects_non_object_or_duplicate_key_payload(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = tmp_path / "payload.json"
    payload.write_text('{"key":1,"key":2}', encoding="utf-8")

    result = cli.main(
        [
            "--root",
            str(cli.REPOSITORY_ROOT),
            "--boundary",
            "OD-001",
            "--profile",
            str(_safe_profile(tmp_path)),
            "--context",
            str(_local_context(tmp_path)),
            "--payload",
            str(payload),
            "--execute",
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert json.loads(captured.err)["error_code"] == "STRATEGY_PAYLOAD_INVALID"
