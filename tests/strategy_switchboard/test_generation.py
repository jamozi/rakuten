from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from scripts import build_all_story_strategy_catalog as generator


def _copy_canonical_inputs(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    for relative in (generator.BACKLOG_PATH, generator.OPEN_DECISIONS_PATH):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(generator.REPOSITORY_ROOT / relative, target)
    return root


def test_render_is_deterministic_and_covers_all_boundaries() -> None:
    first = generator.render(generator.REPOSITORY_ROOT)
    second = generator.render(generator.REPOSITORY_ROOT)

    assert first == second
    assert first.endswith(b"\n")
    document = json.loads(first)
    story_count = len(generator.canonical_story_ids(generator.REPOSITORY_ROOT))
    decision_count = len(
        generator.canonical_open_decision_ids(generator.REPOSITORY_ROOT)
    )
    assert document["coverage"] == {
        "candidate_count": 3 * (story_count + decision_count),
        "open_decision_boundary_count": decision_count,
        "story_boundary_count": story_count,
        "total_boundary_count": story_count + decision_count,
    }
    assert document["authority_boundary"] == {
        "external_values_invented": False,
        "human_approval_invented": False,
        "open_decisions_resolved": False,
        "production_activation": False,
        "selection_requires_explicit_gate_context": True,
    }


def test_write_and_check_round_trip(tmp_path: Path) -> None:
    root = _copy_canonical_inputs(tmp_path)

    written_sha = generator.write(root)
    checked_sha = generator.check(root)

    assert checked_sha == written_sha
    output = root / generator.OUTPUT_PATH
    assert output.is_file()
    assert output.read_bytes() == generator.render(root)


def test_check_rejects_generated_drift(tmp_path: Path) -> None:
    root = _copy_canonical_inputs(tmp_path)
    generator.write(root)
    output = root / generator.OUTPUT_PATH
    output.write_bytes(output.read_bytes() + b" ")

    with pytest.raises(RuntimeError, match="catalog is stale"):
        generator.check(root)


def test_missing_or_added_open_decision_fails_closed(tmp_path: Path) -> None:
    root = _copy_canonical_inputs(tmp_path)
    path = root / generator.OPEN_DECISIONS_PATH
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace("OD-015", "OD-099"), encoding="utf-8")

    with pytest.raises(RuntimeError, match="differs from OD-001 through OD-015"):
        generator.canonical_open_decision_ids(root)


def test_repository_generated_catalog_is_current() -> None:
    digest = generator.check(generator.REPOSITORY_ROOT)

    assert len(digest) == 64
    assert all(character in "0123456789abcdef" for character in digest)
