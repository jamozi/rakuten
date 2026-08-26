from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml

from .support import GENERATED, MANIFEST, run_builder
from scripts import build_st0605_claim_evidence_coverage_reference_plan as generator
from .test_contract import EXPECTED_CASE_IDS, EXPECTED_RESULT_COUNTS


def _snapshot(paths: list[Path]) -> dict[Path, tuple[bytes, int, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in paths
    }


def test_committed_generated_plan_is_current() -> None:
    completed = run_builder("--check")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert completed.stdout.strip().endswith("reference plan checked")


def test_generated_plan_has_exact_projection_sections(
    generated: dict[str, Any],
) -> None:
    assert tuple(generated) == generator.PLAN_KEYS
    assert generated["document"]["decision"] == "NOT_READY"
    assert generated["document"]["executable"] is False
    assert generated["document"]["publication_permitted"] is False
    assert generated["vocabulary_context"]["inferred_mappings"] == []


def test_generated_matrix_preserves_exact_canonical_rows_and_order(
    generated: dict[str, Any],
) -> None:
    matrix = generated["matrix_projection"]
    rows = matrix["rows"]
    assert matrix["row_count"] == 162
    assert matrix["first_test_id"] == "CT-0389"
    assert matrix["last_test_id"] == "CT-0550"
    assert matrix["mapping_authority"] == "UNAVAILABLE"
    assert matrix["executable"] is False
    assert [row["test_id"] for row in rows] == EXPECTED_CASE_IDS
    assert len({row["test_id"] for row in rows}) == 162
    assert tuple(rows[0]) == tuple(generator.MATRIX_COLUMNS)


def test_generated_matrix_preserves_exact_outcome_distribution(
    generated: dict[str, Any],
) -> None:
    rows = generated["matrix_projection"]["rows"]
    actual = {
        outcome: sum(row["expected_result"] == outcome for row in rows)
        for outcome in EXPECTED_RESULT_COUNTS
    }
    assert actual == EXPECTED_RESULT_COUNTS
    assert generated["matrix_projection"]["expected_outcome_counts"] == actual


def test_matrix_projection_does_not_invent_claim_evidence_mappings(
    generated: dict[str, Any],
) -> None:
    forbidden = {
        "claim_type",
        "evidence_requirement",
        "coverage_mapping",
        "claim_id",
        "fact_id",
        "link_id",
    }
    for row in generated["matrix_projection"]["rows"]:
        assert forbidden.isdisjoint(row)


def test_generated_boundaries_preserve_empty_inputs_and_unknown_results(
    generated: dict[str, Any],
) -> None:
    assert generated["collection_boundary"] == generator.EXPECTED_COLLECTIONS
    assert generated["coverage_boundary"] == generator.EXPECTED_COVERAGE_DEFAULTS
    assert generated["selection_boundary"] == generator.EXPECTED_SELECTIONS
    assert generated["coverage_boundary"]["major_claim_evidence_coverage_ratio"] is None
    assert generated["coverage_boundary"]["major_claim_requirement_satisfied"] is None


def test_owner_generation_is_deterministic_and_atomic(
    isolated_repository: Path,
) -> None:
    generator.build(isolated_repository)
    paths = [isolated_repository / path for path in generator.GENERATED_PATHS]
    first = {path: path.read_bytes() for path in paths}
    generator.build(isolated_repository)
    assert {path: path.read_bytes() for path in paths} == first
    assert all(path.stat().st_mode & 0o777 == 0o644 for path in paths)


def test_check_mode_does_not_write_content_mtime_or_mode(
    isolated_repository: Path,
) -> None:
    generator.build(isolated_repository)
    paths = [isolated_repository / path for path in generator.GENERATED_PATHS]
    for index, path in enumerate(paths):
        os.chmod(path, 0o640)
        os.utime(path, ns=(1_700_000_000_000_000_000 + index,) * 2)
    before = _snapshot(paths)
    generator.build(isolated_repository, check=True)
    assert _snapshot(paths) == before


def test_manifest_binds_exact_sources_and_generated_plan() -> None:
    manifest = yaml.safe_load(MANIFEST.read_bytes())
    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_PATHS
    ]
    reference = GENERATED.read_bytes()
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.REFERENCE_PLAN_PATH.as_posix()}",
            "bytes": len(reference),
            "sha256": hashlib.sha256(reference).hexdigest(),
        }
    ]


def test_generated_json_is_deterministic_owner_projection_not_contract_copy(
    generated: dict[str, Any], contract: dict[str, Any]
) -> None:
    assert json.loads(GENERATED.read_bytes()) == generated
    assert generated != contract
    assert "matrix_projection" in generated
    assert "matrix_projection" not in contract


def test_cli_rejects_unsupported_paths_without_echoing_value() -> None:
    canary = "canary-sensitive-output-path"
    completed = run_builder("--output", canary)
    assert completed.returncode == 2
    combined = completed.stdout + completed.stderr
    assert canary not in combined
    assert not combined
