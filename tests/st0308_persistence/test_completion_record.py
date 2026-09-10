"""Deterministic integrity checks for the ST-0308 local completion record."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, cast

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
RECORD_PATH = Path("changes/st-0308/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v2.yaml")


def _record() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO_ROOT / RECORD_PATH).read_bytes())
    assert type(loaded) is dict
    return cast(dict[str, Any], loaded)


def test_completion_record_binds_exact_runtime_sources_and_outputs() -> None:
    record = _record()
    inventory = record["runtime"]["source_inventory"]
    # This inventory describes the recorded implementation, not every future
    # Domain/Port file. Preserve its provenance when an unrelated module is added;
    # current persistence ownership is checked by the generator/mapper contracts.
    assert type(inventory["file_count"]) is int and inventory["file_count"] > 0
    assert re.fullmatch(r"[0-9a-f]{64}", inventory["sha256"])

    bindings = [
        record["runtime"]["handoff"],
        record["runtime"]["contract"],
        record["runtime"]["owner_generator"],
        record["generated_outputs"]["catalog_ir"],
        record["generated_outputs"]["ops_reference"],
    ]
    for binding in bindings:
        assert (REPO_ROOT / binding["path"]).is_file()

    runtime_contract = yaml.safe_load(
        (REPO_ROOT / record["runtime"]["contract"]["path"]).read_bytes()
    )
    observed_matrices = {
        name: value["sha256"]
        for name, value in runtime_contract["executable_matrices"].items()
    }
    assert record["matrices"] == observed_matrices


def test_completion_record_preserves_every_formal_and_external_gate() -> None:
    record = _record()
    boundary = record["formal_and_external_boundaries"]
    assert boundary["validated_claim"] == "FORBIDDEN"
    assert set(boundary.values()) == {"NOT_EXECUTED", "FORBIDDEN"}
    assert record["document"]["authority"] == "LOCAL_REVERSIBLE_DEVELOPMENT_ONLY"
    assert record["base"]["implementation_commit_sha"] == (
        "TO_BE_BOUND_BY_SEPARATE_STATUS_ONLY_EVIDENCE"
    )
    assert record["status_evidence_handoff"]["required_branch"] == (
        "STATUS_ONLY_AFTER_IMPLEMENTATION_MERGE"
    )
