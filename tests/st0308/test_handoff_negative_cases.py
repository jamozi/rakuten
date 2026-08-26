"""Archive-bound checks for the retired ST-0308 approval preflight."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from .support import clone_candidate, report, run_validator


def _write_candidate(tmp_path: Path, candidate: dict[str, object]) -> Path:
    path = tmp_path / "candidate.yaml"
    path.write_text(
        yaml.safe_dump(candidate, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("section", "claim"),
    [
        ("authority", {"status": "APPROVED"}),
        ("approval", {"implementation_authority": "GRANTED"}),
        ("approval", {"approved_by": "owner@example.invalid"}),
    ],
)
def test_archived_candidate_cannot_grant_current_implementation_authority(
    tmp_path: Path,
    pass_candidate: dict[str, object],
    section: str,
    claim: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    payload = candidate["DESIGN_HANDOFF_V1"]
    assert isinstance(payload, dict)
    boundary = payload[section]
    assert isinstance(boundary, dict)
    boundary.update(claim)

    process = run_validator(_write_candidate(tmp_path, candidate))
    result = report(process)
    assert process.returncode != 0
    assert result["implementation_authority"] == "NOT_GRANTED"
    assert result["automated_pass_authorizes_implementation"] is False


@pytest.mark.parametrize(
    "raw",
    [
        "DESIGN_HANDOFF_V1:\n  authority: {}\n  authority: {}\n",
        "DESIGN_HANDOFF_V1: &handoff {}\n",
        "DESIGN_HANDOFF_V1: {}\n---\nDESIGN_HANDOFF_V1: {}\n",
    ],
)
def test_archived_validator_rejects_unsafe_yaml_without_granting_authority(
    tmp_path: Path,
    raw: str,
) -> None:
    path = tmp_path / "unsafe.yaml"
    path.write_text(raw, encoding="utf-8")
    process = run_validator(path)
    result = report(process)
    assert process.returncode != 0
    assert result["implementation_authority"] == "NOT_GRANTED"
