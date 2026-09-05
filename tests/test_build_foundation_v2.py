"""Acceptance checks for the shared RAOS build and status foundations."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import yaml
import pytest

from scripts.raos_build_core import (
    ACTIVE_MANIFEST_PATH,
    EXPLICIT_OWNER_DEPENDENCIES,
    OWNER_PRIVATE_OWNER_IDS,
    VALIDATION_ONLY_OWNER_IDS,
    REPOSITORY_ROOT,
    InputKind,
    BuildRegistryError,
    active_manifest_document,
    affected_owners,
    changed_paths,
    discover_registry,
    generation_relevant_paths,
    run_commands,
)


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


def test_all_generators_have_one_owner_and_an_acyclic_graph() -> None:
    registry = discover_registry()
    # The migration started with 134 owners; new generators must join the same
    # registry instead of requiring another Story-specific workflow.
    assert len(registry) >= 134
    outputs = [path for spec in registry.values() for path in spec.outputs]
    assert len(outputs) == len(set(outputs))
    for owner, dependencies in EXPLICIT_OWNER_DEPENDENCIES.items():
        assert set(dependencies) <= set(registry[owner].owner_dependencies)


def test_validation_only_owners_cannot_hide_missing_generated_outputs() -> None:
    registry = discover_registry()
    assert VALIDATION_ONLY_OWNER_IDS == {
        "build_st1704_portfolio_source_packets",
        "build_st1704_reader_claim_coverage",
    }
    for owner_id in VALIDATION_ONLY_OWNER_IDS:
        owner = registry[owner_id]
        assert owner.output_scope == "validation_only"
        assert owner.as_json()["output_scope"] == "validation_only"
        assert owner.outputs == ()
        with pytest.raises(BuildRegistryError, match="declares outputs"):
            replace(owner, outputs=(Path("unexpected.json"),)).as_json()
        with pytest.raises(BuildRegistryError, match="tracked owner has no outputs"):
            replace(owner, owner_id="unregistered_empty_generator").as_json()
    generated_owner = registry["build_st0105_generated_contracts"]
    assert generated_owner.output_scope == "tracked"
    with pytest.raises(BuildRegistryError, match="tracked owner has no outputs"):
        replace(generated_owner, outputs=()).as_json()


def test_build_infrastructure_change_selects_the_complete_graph() -> None:
    registry = discover_registry()
    selected = affected_owners(registry, {Path("scripts/raos_build_core.py")})
    assert set(selected) == set(registry)


def test_only_historical_editorial_builds_opt_into_development_replay() -> None:
    registry = discover_registry()
    historical = {
        "build_st1704_reader_claim_coverage",
        "build_st1704_self_hosted_editorial_manifest",
    }
    for owner_id, spec in registry.items():
        assert ("--development" in spec.command()) == (owner_id in historical)
        assert "--for-source-refresh" not in spec.command()
        if spec.supports_check:
            assert ("--development" in spec.command(check=True)) == (
                owner_id in historical
            )


def test_direct_offline_editorial_make_targets_replay_historical_evidence() -> None:
    makefile = (
        REPOSITORY_ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/Makefile"
    ).read_text(encoding="utf-8")
    commands = [
        line.strip()
        for line in makefile.splitlines()
        if line.lstrip().startswith(
            (
                "scripts/build_st1704_reader_claim_coverage.py",
                "scripts/build_st1704_self_hosted_editorial_manifest.py",
            )
        )
        and "--skeleton" not in line
    ]
    assert len(commands) == 3
    assert all("--development" in command for command in commands)
    assert all("--for-source-refresh" not in command for command in commands)


def test_changed_paths_falls_back_to_origin_main_without_origin_head(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "RAOS Test")
    _git(tmp_path, "config", "user.email", "raos-test@example.invalid")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("baseline\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-qm", "baseline")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    tracked.write_text("branch\n", encoding="utf-8")
    _git(tmp_path, "commit", "-qam", "branch")

    assert changed_paths(root=tmp_path) == (Path("tracked.txt"),)


def test_editorial_measurement_theme_and_manifest_inputs_are_discoverable() -> None:
    registry = discover_registry()
    measurement = registry["build_editorial_measurement_v1"]
    theme = registry["build_st1704_self_hosted_theme"]
    manifest = registry["build_st1704_self_hosted_editorial_manifest"]

    assert set(measurement.owner_dependencies) >= {
        "build_editorial_portfolio_v3",
    }
    assert set(measurement.outputs) == {
        Path(
            "changes/editorial-measurement-v1/wordpress-plugin/"
            "raos-editorial-measurement/config/measurement-allowlist.v1.json"
        ),
        Path("changes/editorial-measurement-v1/runtime-manifest.v1.json"),
    }
    assert set(theme.owner_dependencies) >= {
        "build_editorial_measurement_v1",
        "build_editorial_v3_theme_navigation",
        "build_st1704_theme_assets",
    }
    assert set(manifest.owner_dependencies) >= {
        "build_editorial_measurement_v1",
        "build_editorial_portfolio_v3",
        "build_editorial_v3_theme_navigation",
        "build_st0105_generated_contracts",
        "build_st1704_self_hosted_theme",
        "build_st1704_theme_assets",
    }

    measurement_inputs = {item.uri for item in measurement.inputs}
    theme_inputs = {item.uri for item in theme.inputs}
    manifest_inputs = {item.uri for item in manifest.inputs}
    theme_root = (
        "repo://changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
        "kurashinoshirube-child/"
    )
    assert {
        "repo://changes/editorial-portfolio-v3/editorial-portfolio.v3.json",
        f"{theme_root}assets/measurement.js",
        f"{theme_root}functions.php",
    } <= measurement_inputs
    assert {
        f"{theme_root}assets/editorial-navigation.v3.json",
        f"{theme_root}assets/images/article-countertop-dishwasher-guide.webp",
        f"{theme_root}assets/images/article-portable-power-guide.webp",
        f"{theme_root}assets/images/article-robot-vacuum-guide.webp",
        f"{theme_root}assets/measurement.js",
        f"{theme_root}functions.php",
        f"{theme_root}theme-contract.v1.json",
    } <= theme_inputs
    assert {
        "repo://changes/editorial-portfolio-v3/editorial-portfolio.v3.json",
        "repo://changes/editorial-portfolio-v3/generated/navigation.v3.json",
        f"{theme_root}assets/editorial-navigation.v3.json",
        f"{theme_root}assets/images/article-countertop-dishwasher-guide.webp",
        f"{theme_root}assets/images/article-portable-power-guide.webp",
        f"{theme_root}assets/images/article-robot-vacuum-guide.webp",
        f"{theme_root}assets/measurement.js",
        f"{theme_root}functions.php",
        f"{theme_root}theme-contract.v1.json",
    } <= manifest_inputs
    assert measurement.test_paths == (Path("tests/editorial_measurement_v1"),)


def test_wordpress_mcp_consumes_the_generated_audit_inventory() -> None:
    registry = discover_registry()
    wordpress_mcp = registry["build_wordpress_mcp_v1"]

    assert "build_editorial_v3_theme_navigation" in wordpress_mcp.owner_dependencies
    assert "build_editorial_measurement_v1" in wordpress_mcp.owner_dependencies
    assert (
        Path("changes/wordpress-mcp-v1/contracts/repo-plugin-artifacts.v1.json")
        in wordpress_mcp.outputs
    )
    assert (
        "repo://changes/editorial-portfolio-v3/generated/"
        "wordpress-audit-inventory.v3.json"
    ) in {item.uri for item in wordpress_mcp.inputs}
    selected = affected_owners(
        registry,
        {
            Path(
                "changes/editorial-portfolio-v3/generated/"
                "wordpress-audit-inventory.v3.json"
            )
        },
    )
    assert selected.index("build_editorial_v3_theme_navigation") < selected.index(
        "build_wordpress_mcp_v1"
    )
    assert set(wordpress_mcp.test_paths) >= {
        Path("tests/test_build_foundation_v2.py"),
        Path("tests/wordpress_local_preview"),
        Path("tests/wordpress_mcp_v1"),
        Path("tests/wordpress_seo_audit_v1"),
    }


def test_editorial_runtime_changes_propagate_in_owner_order() -> None:
    registry = discover_registry()

    def assert_order(path: str, owners: tuple[str, ...]) -> None:
        selected = affected_owners(registry, {Path(path)})
        assert set(owners) <= set(selected)
        positions = [selected.index(owner) for owner in owners]
        assert positions == sorted(positions)

    assert_order(
        "changes/editorial-portfolio-v3/editorial-portfolio.v3.json",
        (
            "build_editorial_portfolio_v3",
            "build_editorial_measurement_v1",
            "build_st1704_self_hosted_theme",
            "build_st1704_self_hosted_editorial_manifest",
        ),
    )
    assert_order(
        "changes/editorial-portfolio-v3/editorial-portfolio.v3.json",
        (
            "build_editorial_portfolio_v3",
            "build_editorial_v3_theme_navigation",
            "build_st1704_self_hosted_theme",
            "build_st1704_self_hosted_editorial_manifest",
        ),
    )
    for asset_name in (
        "article-countertop-dishwasher-guide.png",
        "article-portable-power-guide.png",
        "article-robot-vacuum-guide.png",
    ):
        assert_order(
            "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
            + asset_name,
            (
                "build_st1704_theme_assets",
                "build_st1704_self_hosted_theme",
                "build_st1704_self_hosted_editorial_manifest",
            ),
        )
    for relative in ("assets/measurement.js", "functions.php"):
        assert_order(
            "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
            f"kurashinoshirube-child/{relative}",
            (
                "build_editorial_measurement_v1",
                "build_st1704_self_hosted_theme",
                "build_st1704_self_hosted_editorial_manifest",
            ),
        )


def test_migration_catalog_changes_propagate_through_upgrade_fixtures() -> None:
    registry = discover_registry()
    fixture_owner = registry["build_st0307_migration_fixtures"]

    assert set(fixture_owner.owner_dependencies) >= {
        "build_st0301_migration_framework",
        "build_st0306_database_roles",
    }
    assert any(
        item.uri == "repo://changes/st-0301/generated/migration-catalog.v1.json"
        for item in fixture_owner.inputs
    )
    selected = affected_owners(registry, {Path("python/raos/migrations/catalog.py")})
    ordered = (
        "build_st0301_migration_framework",
        "build_st0307_migration_fixtures",
        "build_st0308_persistence",
    )
    assert set(ordered) <= set(selected)
    positions = [selected.index(owner) for owner in ordered]
    assert positions == sorted(positions)

    migration_only = affected_owners(
        registry,
        {Path("migrations/versions/202608300001_google_analytics_live_persistence.py")},
    )
    assert set(ordered) <= set(migration_only)
    migration_positions = [migration_only.index(owner) for owner in ordered]
    assert migration_positions == sorted(migration_positions)


def test_st0005_git_attributes_source_selects_its_generator() -> None:
    registry = discover_registry()
    owner = registry["build_st0005_status"]

    assert any(item.uri == "repo://.gitattributes" for item in owner.inputs)
    assert "build_st0005_status" in affected_owners(registry, {Path(".gitattributes")})


def test_ci_workflow_source_selects_owners_that_hash_it() -> None:
    registry = discover_registry()
    changed = {Path(".github/workflows/ci.yml")}

    assert generation_relevant_paths(changed) == tuple(changed)
    selected = affected_owners(registry, generation_relevant_paths(changed))
    assert "build_st0801_content_ast" in selected


def test_v2_validation_jobs_fetch_the_immutable_baseline_history() -> None:
    workflow = yaml.safe_load(
        (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    for job in ("static", "tests"):
        checkout = workflow["jobs"][job]["steps"][0]
        assert checkout["with"]["fetch-depth"] == 0
        assert checkout["with"]["persist-credentials"] is False


def test_v2_generated_evidence_is_independent_of_ignored_raw_receipts() -> None:
    validation = json.loads(
        (
            REPOSITORY_ROOT
            / "changes/raos-v2/phase-2/generated/phase-2-validation.v2.json"
        ).read_bytes()
    )

    assert (
        validation["local_test_contracts"]["receipt"]["raw_verification"]
        == "RECORDED_NOT_REVERIFIED"
    )
    assert validation["browser_evidence"]["raw_verification"] == (
        "RECORDED_NOT_REVERIFIED"
    )
    assert (
        validation["visual_review_evidence"]["verification"]["raw_verification"]
        == "RECORDED_NOT_REVERIFIED"
    )


def test_owner_commands_do_not_write_python_bytecode(tmp_path: Path) -> None:
    (tmp_path / "owner_module.py").write_text("VALUE = 1\n", encoding="utf-8")

    run_commands(((sys.executable, "-c", "import owner_module"),), root=tmp_path)

    assert not (tmp_path / "__pycache__").exists()


def test_physical_runtime_generator_is_owner_private() -> None:
    assert "build_st1703_self_hosted_runtime_manifest" in OWNER_PRIVATE_OWNER_IDS


def test_active_manifest_uses_hashes_only_for_integrity_inputs_and_outputs() -> None:
    registry = discover_registry()
    committed = json.loads((REPOSITORY_ROOT / ACTIVE_MANIFEST_PATH).read_bytes())
    assert committed == active_manifest_document(registry)
    assert committed["document"]["mutable_source_hash_authority"] is False
    for owner in committed["owners"]:
        for item in owner["semantic_inputs"]:
            if item["kind"] in {InputKind.IMMUTABLE, InputKind.DEPENDENCY}:
                assert set(item) >= {"uri", "kind", "sha256"}
            else:
                assert "sha256" not in item
                assert set(item) >= {"uri", "kind", "semantic_id", "version"}
        for output in owner["outputs"]:
            assert set(output) == {"uri", "bytes", "sha256"}


def test_status_v2_is_compact_and_contains_no_evidence_bodies() -> None:
    status = yaml.safe_load(
        (REPOSITORY_ROOT / "changes/status/status.v2.yaml").read_text(encoding="utf-8")
    )
    assert status["document"] == {
        "id": "RAOS-STATUS-002",
        "version": "2.0.0",
        "history": "GIT_AND_CI",
        "legacy_v1": "ARCHIVE_ONLY",
    }
    assert len(status["stories"]) > 100
    assert all(
        set(story)
        == {
            "story_id",
            "implementation",
            "verification",
            "external_not_run",
        }
        for story in status["stories"]
    )
    assert "evidence" not in json.dumps(status).lower()


def test_root_development_policy_preserves_external_and_irreversible_boundaries() -> None:
    policy = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "## 唯一の停止条件" in policy
    assert "1. GitHub 開発操作を除く live 外部作用" in policy
    assert "2. 回復不能な操作" in policy
    for obsolete in (
        "exact SHA",
        "head confirmation",
        "1 Story/PR",
        "gpt-5.6-sol",
        'reasoning_effort = "ultra"',
    ):
        assert obsolete not in policy
