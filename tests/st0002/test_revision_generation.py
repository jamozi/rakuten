"""Deterministic generation and provenance tests for ST-0002."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest
import yaml

from scripts import build_st0002_revision as revision


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_ROOT = REPOSITORY_ROOT / "changes" / "st-0002"


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_committed_revision_has_no_generated_drift() -> None:
    revision.check_generated()


def test_clean_revision_build_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    revision.build(first)
    revision.build(second)

    assert revision.generated_file_map(first) == revision.generated_file_map(second)
    assert revision.generated_file_map(first) == revision.generated_file_map(
        BUNDLE_ROOT
    )


def test_generation_failure_preserves_the_previous_complete_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "owned"
    revision.build(target)
    before = revision.generated_file_map(target)

    def fail_generation(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected generation failure")

    monkeypatch.setattr(revision, "generate_contracts", fail_generation)
    with pytest.raises(RuntimeError, match="injected generation failure"):
        revision.build(target)

    assert revision.generated_file_map(target) == before


def test_install_failure_restores_the_previous_complete_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "owned"
    revision.build(target)
    before = revision.generated_file_map(target)
    real_replace = revision.os.replace
    injected = False

    def fail_staged_manifest_once(source: object, destination: object) -> None:
        nonlocal injected
        source_path = Path(source)  # type: ignore[arg-type]
        if (
            not injected
            and source_path.parent.name == "generated"
            and source_path.name == "manifest.yaml"
        ):
            injected = True
            raise OSError("injected install failure")
        real_replace(source, destination)  # type: ignore[arg-type]

    monkeypatch.setattr(revision.os, "replace", fail_staged_manifest_once)
    with pytest.raises(OSError, match="injected install failure"):
        revision.build(target)

    assert injected
    assert revision.generated_file_map(target) == before


def test_cli_refuses_custom_or_unowned_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    custom = tmp_path / "foreign"

    assert revision.main(["--output", str(custom)]) == 1
    assert not custom.exists()
    assert "must be the owned canonical" in capsys.readouterr().err

    unowned = tmp_path / "unowned"
    (unowned / "contracts").mkdir(parents=True)
    (unowned / "manifest.yaml").write_text("document:\n  id: FOREIGN\n")
    with pytest.raises(RuntimeError, match="not owned"):
        revision.build(unowned)


def test_manifest_covers_exact_generated_and_source_artifacts() -> None:
    manifest = yaml.safe_load((BUNDLE_ROOT / "manifest.yaml").read_text())
    generated_entries = {
        entry["path"]: entry for entry in manifest["generated_artifacts"]
    }
    actual_generated = {
        path.relative_to(REPOSITORY_ROOT).as_posix(): path
        for path in (BUNDLE_ROOT / "contracts").rglob("*")
        if path.is_file()
    }

    assert manifest["generated_artifact_count"] == 133
    assert set(generated_entries) == set(actual_generated)
    for relative_path, path in actual_generated.items():
        assert generated_entries[relative_path]["bytes"] == path.stat().st_size
        assert generated_entries[relative_path]["sha256"] == file_hash(path)

    source_entries = {entry["path"]: entry for entry in manifest["source_artifacts"]}
    expected_sources = {
        "scripts/build_st0002_revision.py",
        "changes/st-0002/README.md",
        "changes/st-0002/job-state.v1.yaml",
        *{
            f"changes/st-0002/database/{filename}"
            for filename in revision.MIGRATION_FILES
        },
    }
    assert set(source_entries) == expected_sources
    for relative_path, entry in source_entries.items():
        path = REPOSITORY_ROOT / relative_path
        assert entry["bytes"] == path.stat().st_size
        assert entry["sha256"] == file_hash(path)


def test_builder_rejects_immutable_input_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corrupted = dict(revision.EXPECTED_INPUT_HASHES)
    target = next(iter(corrupted))
    corrupted[target] = "0" * 64
    monkeypatch.setattr(revision, "EXPECTED_INPUT_HASHES", corrupted)

    with pytest.raises(RuntimeError, match="immutable input hash mismatch"):
        revision.assert_immutable_inputs()


def test_formal_migration_is_not_the_proposal_sql() -> None:
    proposal = revision.PROPOSAL_PATCH.read_bytes()
    proposal_hash = sha256(proposal).hexdigest()
    migration_paths = [
        revision.DATABASE_ROOT / filename
        for filename in revision.MIGRATION_FILES
        if filename.endswith(".sql")
    ]

    assert (
        proposal_hash
        == revision.EXPECTED_INPUT_HASHES[
            "docs/upstream/patches/RAOS_04_001_contract_alignment_patch_v0.1.sql"
        ]
    )
    assert all(path.read_bytes() != proposal for path in migration_paths)
    assert all(file_hash(path) != proposal_hash for path in migration_paths)

    (
        expand,
        expand_validate,
        migrate_batch,
        contract_prepare,
        contract,
        downgrade,
    ) = migration_paths
    assert "ck_ops_job_status_expand" in expand.read_text()
    assert "VALIDATE CONSTRAINT" not in expand.read_text()
    assert "VALIDATE CONSTRAINT" in expand_validate.read_text()
    assert "CREATE INDEX CONCURRENTLY" in expand_validate.read_text()
    assert "LIMIT 1000" in migrate_batch.read_text()
    assert "repeat this entire payload" in migrate_batch.read_text()
    assert "ADD CONSTRAINT ck_ops_job_status" in contract_prepare.read_text()
    assert "VALIDATE CONSTRAINT" not in contract_prepare.read_text()
    assert "ALTER COLUMN status SET DEFAULT 'REQUESTED'" in contract.read_text()
    assert "VALIDATE CONSTRAINT" in contract.read_text()
    assert "downgrade refused" in downgrade.read_text()


def test_resource_contract_revision_normalizes_v01_pointer_defects() -> None:
    document = yaml.safe_load(
        (
            BUNDLE_ROOT / "contracts" / "catalogs" / "resource-contracts.v0.2.yaml"
        ).read_text()
    )
    rendered = yaml.safe_dump(document)

    assert "#/components/schemas/PublicOffer" not in rendered
    assert "#/components/schemas/PublicProductCard" not in rendered
    assert "#/components/schemas/PublicArticleBlock" not in rendered
    assert rendered.count("#/public_resources/PublicOffer") == 1
    assert rendered.count("#/public_resources/PublicProductCard") == 1
    assert rendered.count("#/public_resources/PublicArticleBlock") == 1
