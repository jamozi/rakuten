"""Focused source and deterministic-generation checks for ST-0306."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from scripts import build_st0306_database_roles as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_active_cumulative_head_check_mode_never_calls_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(generator, "check_generated", lambda: calls.append("check"))
    monkeypatch.setattr(
        generator,
        "install_generated",
        lambda root=generator.REPO_ROOT: calls.append("install"),
    )

    assert generator.main(["--check"]) == 0
    assert calls == ["check"]


def test_source_contract_pins_exact_authority_and_inventory() -> None:
    assert generator.validate_source_inputs() == {
        "roles": 8,
        "schemas": 13,
        "rls_policies": 22,
    }
    assert generator.ROLES == (
        "raos_migrator",
        "raos_api_rw",
        "raos_worker_rw",
        "raos_dispatcher_rw",
        "raos_projection_rw",
        "raos_public_ro",
        "raos_reporting_ro",
        "raos_auditor_ro",
    )
    catalog = json.loads(generator.render_outputs()[generator.CATALOG_PATH])
    assert catalog["role_membership_boundary"] == {
        "existing_role_path": "OUTBOUND_ONLY_PRESERVE_EXTERNAL_INBOUND",
        "fresh_non_superuser_creation": {
            "admin_option": True,
            "exact_edge_count": 8,
            "inherit_option": False,
            "pg_auth_members_member": "CURRENT_MIGRATION_SESSION_ROLE",
            "pg_auth_members_roleid": "EACH_ST0306_ROLE",
            "set_option": False,
        },
        "standalone_validation": "OUTBOUND_ONLY_PRESERVE_EXTERNAL_INBOUND",
        "workload_role_outbound_memberships": "FORBIDDEN",
    }


def test_revision_is_deterministic_bounded_and_has_no_credentials() -> None:
    first = generator.render_revision()
    second = generator.render_revision()
    source = first.decode("utf-8")

    assert first == second
    assert len(first) < 256 * 1024
    ast.parse(source)
    assert 'revision: str = "202608030006"' in source
    assert 'down_revision: str | None = "202608030005"' in source
    upgrade_statements = generator.render_upgrade_statements()
    downgrade_statements = generator.render_downgrade_statements()
    assert upgrade_statements[0] == "SET LOCAL search_path = pg_catalog;"
    assert "PASSWORD" not in "\n".join(upgrade_statements)
    assert (
        upgrade_statements.count(
            "ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;"
        )
        == 1
    )
    assert not any(
        "IN SCHEMA" in statement and "FUNCTIONS FROM PUBLIC" in statement
        for statement in upgrade_statements
    )
    assert not any("DROP ROLE" in statement for statement in downgrade_statements)
    assert not any(
        "GRANT EXECUTE ON FUNCTIONS TO PUBLIC" in statement
        for statement in downgrade_statements
    )


def test_exact_policy_and_safe_translation_surface() -> None:
    upgrade = "\n".join(generator.render_upgrade_statements())
    assert upgrade.count("CREATE POLICY ") == 22
    assert "GRANT USAGE ON SCHEMA readmodel TO raos_public_ro" in upgrade
    assert "GRANT SELECT ON ALL TABLES IN SCHEMA readmodel TO raos_public_ro" in upgrade
    assert not any(
        identity in upgrade for identity in generator.ABSENT_UPSTREAM_RELATIONS
    )


def test_committed_generated_outputs_match_fresh_render() -> None:
    outputs = generator.render_outputs()
    catalog = json.loads(outputs[generator.CATALOG_PATH])

    assert catalog["roles"] == list(generator.ROLES)
    assert catalog["rls"]["policy_count"] == 22
    assert tuple(outputs) == generator.GENERATED_PATHS
    for path, content in outputs.items():
        assert (REPOSITORY_ROOT / path).read_bytes() == content


def test_manifest_source_inventory_closes_direct_integration_surfaces() -> None:
    required_paths = {
        Path("README.md"),
        Path("Makefile"),
        Path("tests/st0106/test_workflow_contract.py"),
        Path("tests/st0301/test_catalog.py"),
        Path("tests/st0301/test_cli.py"),
        Path("tests/st0301/test_contract.py"),
        Path("tests/st0301/test_generation.py"),
        Path("tests/st0301/test_postgresql.py"),
        Path("tests/st0301/test_runner.py"),
        Path("tests/st0302/test_contract.py"),
        Path("tests/st0302/test_revision.py"),
        Path("tests/st0302/test_postgresql.py"),
        Path("tests/st0303/test_generation.py"),
        Path("tests/st0303/test_postgresql.py"),
        Path("tests/st0304/test_generation.py"),
        Path("tests/st0304/test_postgresql.py"),
        Path("tests/st0305/conftest.py"),
        Path("tests/st0305/test_postgresql.py"),
        Path("tests/st0305/test_st0305_publication_analytics_finance.py"),
    }

    assert required_paths <= set(generator.CURRENT_SOURCE_ARTIFACT_PATHS)
    assert len(generator.CURRENT_SOURCE_ARTIFACT_PATHS) == len(
        set(generator.CURRENT_SOURCE_ARTIFACT_PATHS)
    )
