"""Deterministic integrity checks for the ST-0308 local completion record."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
RECORD_PATH = Path("changes/st-0308/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v2.yaml")
RUNTIME_ROOTS = (
    Path("changes/st-0308/DESIGN_HANDOFF_V1_ST0308_LOCAL_PERSISTENCE_RUNTIME_V2.yaml"),
    Path("changes/st-0308/contracts/persistence-runtime.v2.yaml"),
    Path("changes/st-0308/contracts/persistence"),
    Path("changes/st-0308/generated/persistence-catalog-ir.v1.json"),
    Path("changes/st-0308/generated/persistence-runtime.ops-reference.v1.json"),
    Path("python/raos/adapters/persistence"),
    *(
        Path("python/raos/domain") / name
        for name in (
            "ai",
            "catalog",
            "editorial",
            "evidence",
            "iam",
            "ops",
            "policy",
            "portfolio",
            "shared",
        )
    ),
    *(
        Path("python/raos/ports") / name
        for name in (
            "ai",
            "catalog",
            "editorial",
            "evidence",
            "iam",
            "ops",
            "persistence",
            "policy",
            "portfolio",
        )
    ),
    Path("scripts/build_st0308_persistence.py"),
    Path("tests/st0308_persistence"),
)


def _record() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO_ROOT / RECORD_PATH).read_bytes())
    assert type(loaded) is dict
    return cast(dict[str, Any], loaded)


def _runtime_files() -> tuple[Path, ...]:
    files: set[Path] = set()
    for relative in RUNTIME_ROOTS:
        absolute = REPO_ROOT / relative
        if absolute.is_file():
            files.add(relative)
            continue
        files.update(
            path.relative_to(REPO_ROOT)
            for path in absolute.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
    return tuple(sorted(files, key=lambda path: path.as_posix().encode()))


def test_completion_record_binds_exact_runtime_sources_and_outputs() -> None:
    record = _record()
    files = _runtime_files()
    inventory = record["runtime"]["source_inventory"]
    assert inventory["file_count"] == len(files)

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
