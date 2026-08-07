from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest
import yaml

from conftest import apply_fixture, apply_upstream_bootstrap
from raos.migrations import catalog as migration_catalog
from scripts import build_st0307_migration_fixtures as generator


REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _copy_file(source: Path, target_root: Path, relative: Path) -> None:
    destination = target_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / relative, destination, follow_symlinks=False)


def _copy_generator_sources(target_root: Path) -> None:
    paths = set(generator.CURRENT_SOURCE_ARTIFACT_PATHS)
    paths.update(spec.relative_path for spec in migration_catalog.ALEMBIC_RUNTIME_SPECS)
    paths.update(spec.relative_path for spec in migration_catalog.REVISION_SPECS)
    for path in paths:
        _copy_file(REPO_ROOT, target_root, path)


def test_contract_is_the_exact_approved_story_and_boundary() -> None:
    contract = generator._load_contract()
    assert contract["document"]["story_id"] == "ST-0307"
    assert contract["story"] == {
        "epic_id": "EPIC-03",
        "title": "Migration upgrade fixtures",
        "objective": "旧VersionとAlignment dataのupgradeを固定",
        "dependencies": ["ST-0305"],
        "requirement_ids": [],
        "deliverables": ["VERSIONED_DB_FIXTURES"],
        "acceptance": ["UPGRADE_ROLLBACK_STRATEGY_PASS"],
        "required_suites": ["TST-010"],
        "open_decisions": [],
    }
    assert contract["production_graph"] == {
        "anchor_revision": migration_catalog.ANCHOR_REVISION,
        "predecessor_revision": (
            migration_catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION
        ),
        "head_revision": migration_catalog.HEAD_REVISION,
        "revision_count": len(migration_catalog.REVISION_SPECS),
        "mutation": "FORBIDDEN",
        "new_revision": "FORBIDDEN",
        "checkpoint_activation": "FORBIDDEN",
    }
    assert contract["boundary"]["formal_tst_010"] == "NOT_EXECUTED"
    assert contract["boundary"]["production_execution"] == "FORBIDDEN"


def test_source_check_verifies_all_18_checkpoint_sources() -> None:
    summary = generator.validate_source_inputs()
    assert summary["checkpoint_sources"] == 18
    assert summary["fixture_sources"] == 4
    assert summary["production_revisions"] == 6


def test_checkpoint_inventory_is_exactly_the_live_read_only_catalog() -> None:
    contract = generator._load_contract()
    assert (
        generator._contract_checkpoint_rows(contract)
        == generator._live_checkpoint_rows()
    )
    assert len(generator._live_checkpoint_rows()) == 18
    checkpoint_contract = contract["checkpoint_catalog"]
    assert tuple(checkpoint_contract["forward_plan"]) == migration_catalog.FORWARD_PLAN
    assert (
        tuple(checkpoint_contract["guarded_reverse_plan"])
        == migration_catalog.GUARDED_REVERSE_PLAN
    )
    assert (
        checkpoint_contract["authority_catalog_sha256"]
        == (generator.validate_source_inputs()["catalog_sha256"])
    )
    assert all(
        row["path"].startswith("changes/st-000")
        for row in generator._live_checkpoint_rows()
    )
    assert all(
        path not in generator.GENERATED_PATHS
        for path in (
            Path("python/raos/migrations/catalog.py"),
            Path("python/raos/migrations/runner.py"),
            Path("migrations/env.py"),
            *(spec.relative_path for spec in migration_catalog.REVISION_SPECS),
        )
    )


def test_fixture_precursors_and_ordered_checkpoint_subsets_are_exact() -> None:
    contract = generator._load_contract()
    fixtures = {row["id"]: row for row in contract["fixtures"]}
    first_wave = migration_catalog.FORWARD_PLAN[:5]
    second_wave = migration_catalog.FORWARD_PLAN[5:10]
    third_wave = migration_catalog.FORWARD_PLAN[10:]
    job = fixtures["ST0307-V01-JOB-ALIGNMENT"]
    ai = fixtures["ST0307-V02-AI-ALIGNMENT"]
    content = fixtures["ST0307-V03-CONTENT-ALIGNMENT"]
    predecessor = fixtures["ST0307-202608030005-PREDECESSOR"]
    assert job["apply_at"]["completed_forward_checkpoints"] == []
    assert tuple(job["ordered_forward_checkpoints"]) == first_wave
    assert tuple(ai["apply_at"]["completed_forward_checkpoints"]) == first_wave
    assert tuple(ai["ordered_forward_checkpoints"]) == second_wave
    assert tuple(content["apply_at"]["completed_forward_checkpoints"]) == (
        first_wave + second_wave
    )
    assert tuple(content["ordered_forward_checkpoints"]) == third_wave
    assert predecessor["apply_at"]["production_revision"] == (
        migration_catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION
    )
    assert tuple(predecessor["ordered_upgrade_revisions"]) == (
        migration_catalog.HEAD_REVISION,
    )


def test_upstream_bootstrap_is_pinned_and_fixture_authority_is_separate() -> None:
    contract = generator._load_contract()
    baseline = contract["source_precedence"]["upstream_baseline"]
    harness = contract["historical_test_harness"]
    assert (
        tuple(
            (row["purpose"], row["member_suffix"], row["member_sha256"])
            for row in baseline["members"]
        )
        == generator.UPSTREAM_MEMBER_SPECS
    )
    assert tuple(harness["baseline_members_loaded"]) == tuple(
        member_suffix
        for _purpose, member_suffix, _digest in generator.UPSTREAM_MEMBER_SPECS
    )
    assert harness["bootstrap_source"] == "PINNED_UPSTREAM_ONLY"
    assert harness["environment"] == "ISOLATED_EPHEMERAL_TEST_SETUP_ONLY"
    assert harness["acl_or_default_privilege_semantics"] == "NOT_EVALUATED"
    assert harness["tst_011"] == "NOT_EXECUTED"
    assert contract["security"]["generated_fixture_payloads"] == {
        "roles_grants_or_rls": "FORBIDDEN"
    }


def test_rendered_outputs_are_deterministic_and_match_committed_bytes() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()
    assert first == second
    assert tuple(first) == generator.GENERATED_PATHS
    for path, expected in first.items():
        assert (REPO_ROOT / path).read_bytes() == expected


def test_fixture_sql_is_transactional_synthetic_and_has_no_authority_ddl() -> None:
    outputs = generator.render_outputs()
    forbidden = (
        "CREATE ROLE",
        "ALTER ROLE",
        "GRANT ",
        "CREATE POLICY",
        "ENABLE ROW LEVEL SECURITY",
        "FORCE ROW LEVEL SECURITY",
        "PASSWORD",
    )
    for path in generator.FIXTURE_PATHS:
        text = outputs[path].decode("utf-8")
        assert text.count("BEGIN;") == 1
        assert text.count("COMMIT;") == 1
        assert "server_version_num" in text
        assert "180004" in text
        assert "Synthetic test data only" in text
        assert all(token not in text.upper() for token in forbidden)


def test_fixture_catalog_and_manifest_hash_every_generated_payload() -> None:
    catalog = json.loads((REPO_ROOT / generator.CATALOG_PATH).read_text())
    manifest = yaml.safe_load((REPO_ROOT / generator.MANIFEST_PATH).read_text())
    assert catalog["fixture_count"] == 4
    assert catalog["checkpoint_catalog"]["count"] == 18
    catalog_rows = {Path(row["path"]): row for row in catalog["fixtures"]}
    assert set(catalog_rows) == set(generator.FIXTURE_PATHS)
    for path in generator.FIXTURE_PATHS:
        content = (REPO_ROOT / path).read_bytes()
        assert catalog_rows[path]["bytes"] == len(content)
        assert catalog_rows[path]["sha256"] == _sha256(content)
    generated = {
        Path(row["uri"].removeprefix("repo://")): row
        for row in manifest["generated_artifacts"]
    }
    assert set(generated) == set(generator.GENERATED_PATHS) - {generator.MANIFEST_PATH}
    for path, row in generated.items():
        content = (REPO_ROOT / path).read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == _sha256(content)


def test_checkpoint_tamper_is_rejected_before_any_fixture_mutation(
    tmp_path: Path,
) -> None:
    _copy_generator_sources(tmp_path)
    sentinel_path = tmp_path / generator.JOB_FIXTURE_PATH
    sentinel_path.parent.mkdir(parents=True, exist_ok=True)
    sentinel_path.write_bytes(b"sentinel\n")
    checkpoint = migration_catalog.CHECKPOINT_SPECS[0].relative_path
    with (tmp_path / checkpoint).open("ab") as stream:
        stream.write(b"\n-- tampered\n")
    with pytest.raises(migration_catalog.CatalogError) as raised:
        generator.install_generated(tmp_path)
    assert (
        raised.value.code is migration_catalog.CatalogErrorCode.SOURCE_DIGEST_MISMATCH
    )
    assert sentinel_path.read_bytes() == b"sentinel\n"
    assert not (tmp_path / generator.CATALOG_PATH).exists()


def test_fixture_tamper_is_rejected_before_superuser_execution(tmp_path: Path) -> None:
    _copy_generator_sources(tmp_path)
    outputs = generator.render_outputs(tmp_path)
    for path, content in outputs.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    fixture = tmp_path / generator.JOB_FIXTURE_PATH
    fixture.write_bytes(fixture.read_bytes() + b"\n-- tampered\n")
    executions: list[str] = []

    def record_execution(*_arguments: object) -> None:
        executions.append("executed")

    with pytest.raises(AssertionError, match="fixture differs"):
        apply_fixture(
            object(),  # type: ignore[arg-type]
            "disposable",
            generator.JOB_FIXTURE_PATH,
            root=tmp_path,
            executor=record_execution,
        )
    assert executions == []


def test_archive_tamper_is_rejected_before_bootstrap_execution(tmp_path: Path) -> None:
    _copy_generator_sources(tmp_path)
    archive = tmp_path / generator.UPSTREAM_ARCHIVE_PATH
    archive.chmod(0o600)
    archive.write_bytes(archive.read_bytes() + b"\n")
    executions: list[str] = []

    def record_execution(*_arguments: object) -> None:
        executions.append("executed")

    with pytest.raises(RuntimeError, match="baseline archive digest differs"):
        apply_upstream_bootstrap(
            object(),  # type: ignore[arg-type]
            "disposable",
            root=tmp_path,
            executor=record_execution,
        )
    assert executions == []


def test_generated_install_rejects_symlink_ancestor(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    tests = tmp_path / "tests"
    tests.mkdir()
    os.symlink(outside, tests / "fixtures")
    with pytest.raises((OSError, RuntimeError)):
        generator.secure._stage_output(
            tmp_path,
            generator.JOB_FIXTURE_PATH,
            b"unsafe\n",
            0,
        )
    assert list(outside.iterdir()) == []


def test_check_mode_is_read_only_and_detects_no_drift() -> None:
    before = {
        path: (REPO_ROOT / path).stat().st_mtime_ns
        for path in generator.GENERATED_PATHS
    }
    generator.check_generated()
    after = {
        path: (REPO_ROOT / path).stat().st_mtime_ns
        for path in generator.GENERATED_PATHS
    }
    assert after == before


def test_root_make_and_readme_route_only_the_st0307_fixture_surface() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert (
        "migration-fixture-generate migration-fixture-check migration-fixture-test"
        in (makefile)
    )
    assert (
        "migration-fixture-generate: | python-sync\n"
        "\t$(UV_RUN) run --locked --no-sync --no-env-file python \\\n"
        "\t\tscripts/build_st0307_migration_fixtures.py"
    ) in makefile
    assert (
        "migration-fixture-check: | python-sync\n"
        "\tPYTHONDONTWRITEBYTECODE=1 $(UV_READONLY_RUN) python \\\n"
        "\t\tscripts/build_st0307_migration_fixtures.py --check"
    ) in makefile
    assert (
        "migration-fixture-test: | python-sync\n"
        "\tPYTHONDONTWRITEBYTECODE=1 $(UV_READONLY_RUN) pytest \\\n"
        "\t\t-p no:cacheprovider -q tests/st0307"
    ) in makefile
    cumulative_test = makefile.split("migration-test: | python-sync", 1)[1].split(
        "migration-fixture-generate:", 1
    )[0]
    assert "tests/st0307" not in cumulative_test
    repository_policy_dependencies = makefile.split("ci-repository-policy:", 1)[
        1
    ].split("\n\tPYTHONDONTWRITEBYTECODE", 1)[0]
    normalized_policy_dependencies = " ".join(
        repository_policy_dependencies.replace("\\\n", " ").split()
    )
    assert (
        "migration-check migration-fixture-check ai-registry-check content-ast-check"
        in normalized_policy_dependencies
    )
    assert "scripts/build_st0307_migration_fixtures.py" in readme
    assert "make migration-fixture-generate" in readme
    assert "make migration-fixture-check" in readme
    assert "make migration-fixture-test" in readme
