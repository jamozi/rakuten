from __future__ import annotations

# pyright: reportPrivateUsage=false

from collections.abc import Callable
import hashlib
from pathlib import Path

import pytest
import yaml

from .support import REPO_ROOT, read
from scripts import build_st0903_publication_snapshot_runtime_v2 as generator
from raos.adapters.recorded_publication_snapshot_fixture_v2 import (
    PUBLICATION_SNAPSHOT_PASS_V2_JSON,
    PUBLICATION_SNAPSHOT_PASS_V2_SHA256,
)


def test_owner_generator_is_no_write_clean() -> None:
    generator.build(REPO_ROOT, check=True)


def test_generated_module_is_exact_fixture_copy() -> None:
    fixture = read(generator.FIXTURE_PATH)
    assert PUBLICATION_SNAPSHOT_PASS_V2_JSON == fixture
    assert PUBLICATION_SNAPSHOT_PASS_V2_SHA256 == hashlib.sha256(fixture).hexdigest()


def test_manifest_binds_every_owner_and_dependency_source() -> None:
    manifest = yaml.safe_load(read(generator.MANIFEST_PATH))
    rows = manifest["source_artifacts"]
    assert manifest["source_artifact_count"] == len(rows)
    assert manifest["generated_artifact_count"] == 2
    observed = {row["uri"]: row for row in rows}
    assert len(observed) == len(rows)
    expected = {
        f"repo://{path.as_posix()}"
        for path in (*generator.SOURCE_PATHS, *generator.DEPENDENCY_PATHS)
    }
    assert set(observed) == expected
    for uri, row in observed.items():
        payload = (REPO_ROOT / Path(uri.removeprefix("repo://"))).read_bytes()
        assert row["bytes"] == len(payload)
        assert row["sha256"] == hashlib.sha256(payload).hexdigest()


def test_manifest_preserves_external_gates() -> None:
    manifest = yaml.safe_load(read(generator.MANIFEST_PATH))
    authority = manifest["authority"]
    assert authority["public_projection_authorized"] is False
    assert authority["publication_authorized"] is False
    assert authority["release_authorized"] is False
    assert authority["production_authorized"] is False
    assert set(authority.values()) <= {
        False,
        "NOT_EXECUTED",
    }


def test_v1_reference_plan_owner_is_no_write_clean() -> None:
    from scripts import build_st0903_publication_snapshot_reference_plan as v1

    v1.build(check=True)


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda value: value.replace(
                "  publication_authorized: false",
                "  publication_authorized: true",
                1,
            ),
            "AUTHORITY_ESCALATION",
        ),
        (
            lambda value: value.replace(
                "schema_version: 2",
                "schema_version: 2\nschema_version: 2",
                1,
            ),
            "CONTRACT_MAPPING_INVALID",
        ),
        (
            lambda value: value.replace(
                "  legacy_schema_reconciliation_required: true",
                "  legacy_schema_reconciliation_required: false",
                1,
            ),
            "SNAPSHOT_BOUNDARY_INVALID",
        ),
    ],
)
def test_contract_mutations_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[str], str],
    code: str,
) -> None:
    original_reader = generator._read_regular
    original = read(generator.CONTRACT_PATH).decode("utf-8")
    mutated = mutate(original).encode("utf-8")
    contract_path = REPO_ROOT / generator.CONTRACT_PATH

    def reader(path: Path) -> bytes:
        return mutated if path == contract_path else original_reader(path)

    monkeypatch.setattr(generator, "_read_regular", reader)
    with pytest.raises(generator.PublicationSnapshotGenerationError) as captured:
        generator.load_contract(REPO_ROOT)
    assert captured.value.code == code
