"""Focused source and deterministic-generation checks for ST-0305."""

from __future__ import annotations

import ast
from collections.abc import Sequence
import json
from pathlib import Path

import pytest

from scripts import build_st0305_publication_analytics_finance as generator
from scripts import build_st0306_database_roles as successor


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_legacy_entrypoint_delegates_to_active_cumulative_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[Sequence[str] | None] = []

    def record_main(argv: Sequence[str] | None = None) -> int:
        observed.append(argv)
        return 0

    monkeypatch.setattr(successor, "main", record_main)

    assert generator.main(["--check"]) == 0
    assert observed == [["--check"]]


def test_explicit_own_story_check_bypasses_successor_without_installing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []
    successor_calls: list[Sequence[str] | None] = []

    monkeypatch.setattr(
        successor,
        "main",
        lambda argv=None: successor_calls.append(argv) or 0,
    )
    monkeypatch.setattr(generator, "check_generated", lambda: observed.append("check"))
    monkeypatch.setattr(
        generator,
        "install_generated",
        lambda root=generator.REPO_ROOT: observed.append("install"),
    )

    assert generator.main(["--own-story", "--check"]) == 0
    assert successor_calls == []
    assert observed == ["check"]


def test_explicit_own_story_install_bypasses_successor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []
    successor_calls: list[Sequence[str] | None] = []

    monkeypatch.setattr(
        successor,
        "main",
        lambda argv=None: successor_calls.append(argv) or 0,
    )
    monkeypatch.setattr(
        generator,
        "install_generated",
        lambda root=generator.REPO_ROOT: observed.append("install"),
    )

    assert generator.main(["--own-story"]) == 0
    assert successor_calls == []
    assert observed == ["install"]


def test_source_contract_has_exact_approved_inventory() -> None:
    counts = generator.validate_source_inputs()

    assert counts == generator.EXPECTED_INVENTORY
    assert generator.SCHEMAS == (
        "publishing",
        "freshness",
        "analytics",
        "finance",
        "readmodel",
    )


def test_revision_render_is_deterministic_and_has_catalog_metadata() -> None:
    first = generator.render_revision()
    second = generator.render_revision()
    source = first.decode("utf-8")

    assert first == second
    assert len(first) < 256 * 1024
    ast.parse(source)
    assert 'revision: str = "202608030005"' in source
    assert 'down_revision: str | None = "202608030004"' in source
    for label in (
        "- story: ST-0305",
        "- requirement IDs: FR-010, FR-013, FR-014, FR-015",
        "- architecture:",
        "- risk class:",
        "- estimated lock:",
        "- backfill job:",
        "- rollback category:",
    ):
        assert label in source


def test_rendered_catalog_and_committed_outputs_have_exact_inventory() -> None:
    outputs = generator.render_outputs()
    catalog = json.loads(outputs[generator.CATALOG_PATH])

    assert {
        key: catalog["expected_inventory"][key] for key in generator.EXPECTED_INVENTORY
    } == generator.EXPECTED_INVENTORY
    assert catalog["revision"]["revision"] == generator.REVISION
    assert tuple(outputs) == generator.GENERATED_PATHS
    for path, content in outputs.items():
        assert (REPOSITORY_ROOT / path).read_bytes() == content
