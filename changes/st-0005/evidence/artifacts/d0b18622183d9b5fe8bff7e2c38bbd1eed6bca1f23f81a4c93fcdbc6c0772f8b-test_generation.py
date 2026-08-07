"""Fail-closed ST-0303 contract validation and revision rendering tests."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import stat
from typing import Any

import pytest

from conftest import REPOSITORY_ROOT
from scripts import build_st0303_iam_ops as generator
from scripts import build_st0304_domain_schemas as successor
from scripts import build_st0306_database_roles as active_successor


def test_generator_strictly_accepts_the_source_bound_contract() -> None:
    contract = generator._load_contract()

    assert contract["document"] == {
        "id": "RAOS-IAM-OPS-SCHEMA-001",
        "version": "1.0.0",
        "story_id": "ST-0303",
        "status": "LOCAL_AND_CI_CANDIDATE",
        "formal_verification": "NOT_EXECUTED",
    }
    assert generator._inventory(contract) == generator.EXPECTED_INVENTORY
    assert (
        tuple(table["fully_qualified_name"] for table in contract["tables"])
        == generator.SELECTED_TABLES
    )


def test_source_predecessor_and_scalar_drift_fail_before_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_hash = generator.shared.sha256_file

    def predecessor_drift(path: Path) -> str:
        if path == REPOSITORY_ROOT / generator.PREDECESSOR_PATH:
            return "0" * 64
        return real_hash(path)

    monkeypatch.setattr(generator.shared, "sha256_file", predecessor_drift)
    with pytest.raises(RuntimeError, match="predecessor manifest digest"):
        generator._verify_inputs(REPOSITORY_ROOT)

    monkeypatch.setattr(generator.shared, "sha256_file", real_hash)
    baseline = generator._load_contract()
    mutated = copy.deepcopy(baseline)
    mutated["database"]["transactional_ddl"] = 1
    real_load = generator.shared.load_yaml

    def load(path: Path) -> Any:
        if path == REPOSITORY_ROOT / generator.CONTRACT_PATH:
            return mutated
        return real_load(path)

    monkeypatch.setattr(generator.shared, "load_yaml", load)
    with pytest.raises(RuntimeError, match="database contract differs"):
        generator._load_contract()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda value: value["tables"].append(copy.deepcopy(value["tables"][0])),
            "structured inventory differs",
        ),
        (
            lambda value: value["tables"][0]["columns"].__setitem__(
                1, copy.deepcopy(value["tables"][0]["columns"][0])
            ),
            "contract tables differ",
        ),
        (
            lambda value: value["tables"][0]["indexes"].__setitem__(
                1, copy.deepcopy(value["tables"][0]["indexes"][0])
            ),
            "contract tables differ",
        ),
        (
            lambda value: value["tables"][1]["deferred_foreign_keys"][0].update(
                {"deferred_until_story": "ST-0303"}
            ),
            "contract tables differ",
        ),
    ),
)
def test_duplicate_or_inferred_contract_semantics_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    mutation: Any,
    message: str,
) -> None:
    baseline = generator._load_contract()
    mutated = copy.deepcopy(baseline)
    mutation(mutated)
    real_load = generator.shared.load_yaml

    def load(path: Path) -> Any:
        if path == REPOSITORY_ROOT / generator.CONTRACT_PATH:
            return mutated
        return real_load(path)

    monkeypatch.setattr(generator.shared, "load_yaml", load)
    with pytest.raises(RuntimeError, match=message):
        generator._load_contract()


def test_revision_is_deterministic_parseable_and_has_exact_identity() -> None:
    contract = generator._load_contract()
    first = generator.render_revision(contract)
    second = generator.render_revision(contract)
    text = first.decode("utf-8")

    assert first == second
    ast.parse(text)
    assert 'revision: str = "202608030003"' in text
    assert 'down_revision: str | None = "202608030002"' in text
    assert "- runner version: 1.2.0" in text
    assert "- server version: 180004" in text
    assert "branch_labels: str | Sequence[str] | None = None" in text
    assert "depends_on: str | Sequence[str] | None = None" in text


def test_upgrade_statements_install_only_the_exact_contract_inventory() -> None:
    contract = generator._load_contract()
    statements = generator.render_upgrade_statements(contract)
    joined = "\n".join(statements)

    assert statements[:2] == (
        "SET LOCAL search_path = pg_catalog",
        "SET LOCAL TIME ZONE 'UTC'",
    )
    assert sum(statement.startswith("CREATE TABLE ") for statement in statements) == 17
    assert sum(" ADD CONSTRAINT " in statement for statement in statements) == 20
    assert (
        sum(
            statement.startswith(("CREATE INDEX ", "CREATE UNIQUE INDEX "))
            for statement in statements
        )
        == 48
    )
    assert (
        sum(statement.startswith("CREATE FUNCTION ") for statement in statements) == 2
    )
    assert sum(statement.startswith("CREATE TRIGGER ") for statement in statements) == 4
    assert sum(" NULLS NOT DISTINCT" in statement for statement in statements) == 3
    assert "CONSTRAINT uq_ops_setting_version UNIQUE " in joined
    assert "CONSTRAINT uq_ops_setting_version UNIQUE NULLS NOT DISTINCT" not in joined
    assert "REFERENCES portfolio.site" not in joined
    assert "REFERENCES ops.incident" not in joined
    assert "ix_ops_job_site_id" in joined
    assert "ix_iam_break_glass_record_incident_id" in joined
    assert "approved_by_principal_id <> principal_id" not in joined
    assert "principal_id <> approved_by_principal_id" not in joined

    forbidden = (
        "IF NOT EXISTS",
        "IF EXISTS",
        " CASCADE",
        "CREATE EXTENSION",
        "CREATE TYPE",
        "CREATE ROLE",
        "CREATE USER",
        "GRANT ",
        "ALTER DEFAULT PRIVILEGES",
        "CREATE SCHEMA",
        "portfolio.",
    )
    assert not any(token in joined for token in forbidden)


def test_job_final_contract_is_created_directly_without_proposal_phases() -> None:
    contract = generator._load_contract()
    statements = generator.render_upgrade_statements(contract)
    job = next(
        statement
        for statement in statements
        if statement.startswith("CREATE TABLE ops.job ")
    )
    indexes = [
        statement
        for statement in statements
        if statement.startswith(("CREATE INDEX ", "CREATE UNIQUE INDEX "))
        and " ON ops.job " in statement
    ]

    assert "status pg_catalog.text DEFAULT 'REQUESTED' NOT NULL" in job
    assert all(state in job for state in contract["job_contract"]["states"])
    assert job.count("CONSTRAINT ck_ops_job_") == 11
    assert "job_version pg_catalog.int2 DEFAULT 1 NOT NULL" in job
    assert "deadline_at pg_catalog.timestamptz" in job
    assert "cancel_requested_at pg_catalog.timestamptz" in job
    assert len(indexes) == 9
    assert any("ix_ops_job_ready" in index for index in indexes)
    assert any("ix_ops_job_deadline_active" in index for index in indexes)
    assert "ALTER TYPE" not in "\n".join(statements)


def test_functions_are_invoker_only_and_require_both_maintenance_factors() -> None:
    statements = generator.render_upgrade_statements(generator._load_contract())
    joined = "\n".join(statements)

    assert joined.count("SECURITY INVOKER") == 2
    assert "SECURITY DEFINER" not in joined
    assert joined.count("SET search_path = pg_catalog") == 2
    assert "current_setting('raos.allow_immutable_maintenance', true) = 'on'" in joined
    assert "pg_catalog.pg_has_role(current_user, 'raos_migrator', 'MEMBER')" in joined
    assert "ERRCODE = '55000'" in joined
    assert "REVOKE ALL ON FUNCTION ops.touch_mutable_row() FROM PUBLIC" in statements
    assert (
        "REVOKE ALL ON FUNCTION ops.reject_immutable_mutation() FROM PUBLIC"
        in statements
    )


def test_downgrade_locks_every_owned_table_before_one_preflight_and_any_drop() -> None:
    statements = generator.render_downgrade_statements()
    lock = statements[2]
    preflight = statements[3]

    assert lock == (
        "LOCK TABLE "
        + ", ".join(generator.TABLE_CREATION_ORDER)
        + " IN ACCESS EXCLUSIVE MODE"
    )
    assert all(
        preflight.index(f"SELECT 1 FROM {table} LIMIT 1")
        < preflight.index("ST0303_DOWNGRADE_NONEMPTY")
        for table in generator.TABLE_CREATION_ORDER
    )
    assert statements[4:21] == tuple(
        f"DROP TABLE {table} RESTRICT"
        for table in reversed(generator.TABLE_CREATION_ORDER)
    )
    assert all("DROP " not in statement for statement in statements[:4])
    assert "CASCADE" not in "\n".join(statements)


def test_frozen_generated_payloads_match_rendering_and_successor_pin() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()

    assert first == second
    assert tuple(first) == generator.GENERATED_PATHS
    for path in (
        generator.REVISION_PATH,
        generator.CATALOG_PATH,
        generator.VALIDATION_PATH,
    ):
        target = REPOSITORY_ROOT / path
        assert target.read_bytes() == first[path]
        assert stat.S_IMODE(target.stat().st_mode) == 0o644
    manifest = (REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes()
    assert hashlib.sha256(manifest).hexdigest() == (
        successor.EXPECTED_PREDECESSOR_MANIFEST_SHA256
    )
    assert stat.S_IMODE((REPOSITORY_ROOT / generator.MANIFEST_PATH).stat().st_mode) == (
        0o644
    )


def test_generated_catalog_binds_every_artifact_and_exact_contract_shape() -> None:
    catalog = json.loads((REPOSITORY_ROOT / generator.CATALOG_PATH).read_bytes())
    contract = generator._load_contract()
    revision = (REPOSITORY_ROOT / generator.REVISION_PATH).read_bytes()
    validation = (REPOSITORY_ROOT / generator.VALIDATION_PATH).read_bytes()

    assert catalog["document"] == {
        "formal_verification": "NOT_EXECUTED",
        "id": "RAOS-IAM-OPS-CATALOG-001",
        "story_id": "ST-0303",
        "version": "1.0.0",
    }
    assert catalog["contract"] == {
        "path": generator.CONTRACT_PATH.as_posix(),
        "sha256": hashlib.sha256(
            (REPOSITORY_ROOT / generator.CONTRACT_PATH).read_bytes()
        ).hexdigest(),
    }
    assert catalog["revision"] == {
        "down_revision": "202608030002",
        "path": generator.REVISION_PATH.as_posix(),
        "revision": "202608030003",
        "runner_version": "1.2.0",
        "server_version_num": 180004,
        "sha256": hashlib.sha256(revision).hexdigest(),
        "story_id": "ST-0303",
        "transaction": "ALEMBIC_PER_REVISION",
    }
    assert catalog["validation"]["sha256"] == hashlib.sha256(validation).hexdigest()
    assert catalog["validation"]["success_row"] == {
        "status": "PASS",
        "table_count": 17,
        "column_count": 219,
        "immediate_foreign_key_count": 20,
        "deferred_foreign_key_count": 2,
    }
    assert catalog["inventory"] == generator.EXPECTED_INVENTORY
    assert catalog["creation_order"] == list(generator.TABLE_CREATION_ORDER)
    assert catalog["tables"] == contract["tables"]
    assert catalog["functions"] == contract["functions"]
    assert catalog["triggers"] == contract["triggers"]
    assert catalog["boundary"]["effective_canonical_status"] == "UNCHANGED"
    assert catalog["boundary"]["formal_tst_008"] == "NOT_EXECUTED"
    assert catalog["boundary"]["formal_tst_011"] == "NOT_EXECUTED"
    assert catalog["boundary"]["formal_tst_013"] == "NOT_EXECUTED"


def test_validation_sql_is_exact_no_write_attestation_with_stable_markers() -> None:
    text = (REPOSITORY_ROOT / generator.VALIDATION_PATH).read_text(encoding="utf-8")

    for marker in (
        "ST0303_SERVER_VERSION_MISMATCH",
        "ST0303_TIMEZONE_MISMATCH",
        "ST0303_SEARCH_PATH_MISMATCH",
        "ST0303_SCHEMA_OWNER_OR_ACL_MISMATCH",
        "ST0303_DEFAULT_ACL_PRESENT",
        "ST0303_TABLE_CATALOG_MISMATCH",
        "ST0303_COLUMN_CATALOG_MISMATCH",
        "ST0303_CONSTRAINT_CATALOG_MISMATCH",
        "ST0303_INDEX_CATALOG_MISMATCH",
        "ST0303_FUNCTION_CATALOG_MISMATCH",
        "ST0303_TRIGGER_CATALOG_MISMATCH",
        "ST0303_DEFERRED_FOREIGN_KEY_BOUNDARY_MISMATCH",
        "ST0303_JOB_CONTRACT_MISMATCH",
        "ST0303_CANONICAL_LIMITATION_DRIFT",
        "ST0303_MIGRATION_VERSION_MISMATCH",
        "ST0303_MIGRATION_HISTORY_MISMATCH",
    ):
        assert marker in text
    assert "17::pg_catalog.int4 AS table_count" in text
    assert "219::pg_catalog.int4 AS column_count" in text
    assert "20::pg_catalog.int4 AS immediate_foreign_key_count" in text
    assert "2::pg_catalog.int4 AS deferred_foreign_key_count" in text
    assert "defaults.defaclnamespace = 0" in text
    assert "constraint_record.contype" in text
    assert "index_record.indnullsnotdistinct" in text
    assert "constraint_record.conname = 'uq_ops_setting_version'" in text
    assert "index_record.indexrelid::pg_catalog.regclass::pg_catalog.text" not in text
    assert (
        re.search(
            r"(?mi)^\s*(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|GRANT|REVOKE|TRUNCATE)\b",
            text,
        )
        is None
    )


def test_frozen_manifest_inventory_is_exact_unique_and_content_addressed() -> None:
    manifest_content = (REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes()
    manifest = generator.shared.load_yaml(REPOSITORY_ROOT / generator.MANIFEST_PATH)
    sources = manifest["source_artifacts"]
    generated = manifest["generated_artifacts"]

    assert hashlib.sha256(manifest_content).hexdigest() == (
        successor.EXPECTED_PREDECESSOR_MANIFEST_SHA256
    )

    assert (
        manifest["source_artifact_count"]
        == len(sources)
        == len(generator.SOURCE_ARTIFACT_PATHS)
    )
    assert [item["uri"] for item in sources] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_ARTIFACT_PATHS
    ]
    assert len({item["uri"] for item in sources}) == len(sources)
    assert manifest["generated_artifact_count"] == len(generated) == 3
    assert [item["uri"] for item in generated] == [
        f"repo://{path.as_posix()}"
        for path in generator.GENERATED_PATHS
        if path != generator.MANIFEST_PATH
    ]
    for item in sources:
        assert set(item) == {"uri", "bytes", "sha256"}
        assert type(item["bytes"]) is int and item["bytes"] > 0
        assert re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
        relative = Path(item["uri"].removeprefix("repo://"))
        assert not relative.is_absolute()
        assert all(part not in {"", ".", ".."} for part in relative.parts)
    for item in generated:
        relative = Path(item["uri"].removeprefix("repo://"))
        content = (REPOSITORY_ROOT / relative).read_bytes()
        assert item["bytes"] == len(content)
        assert item["sha256"] == hashlib.sha256(content).hexdigest()
    assert manifest["provenance"]["predecessor_manifest"] == {
        "story_id": "ST-0302",
        "uri": "repo://changes/st-0302/manifest.yaml",
        "sha256": generator.EXPECTED_PREDECESSOR_SHA256,
    }
    assert {
        item["uri"].removeprefix("repo://"): item["sha256"]
        for item in manifest["provenance"]["canonical_and_upstream_inputs"]
    } == generator.PINNED_INPUTS
    assert manifest["manifest_self_integrity"] == {
        "included_in_source_artifacts": False,
        "verification": "deterministic byte-for-byte regeneration via --check",
    }


def _candidate_outputs() -> dict[Path, bytes]:
    return {
        path: f"candidate:{index}:{path.as_posix()}\n".encode()
        for index, path in enumerate(generator.GENERATED_PATHS)
    }


def test_install_rejects_symlink_target_without_touching_external_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = _candidate_outputs()
    monkeypatch.setattr(generator, "render_outputs", lambda root=tmp_path: outputs)
    target = tmp_path / generator.REVISION_PATH
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_bytes(b"unchanged")
    target.symlink_to(outside)

    with pytest.raises(RuntimeError, match="regular non-symlink"):
        generator.install_generated(tmp_path)
    assert outside.read_bytes() == b"unchanged"
    assert not (tmp_path / generator.CATALOG_PATH).exists()


def test_install_rolls_back_a_mid_commit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = _candidate_outputs()
    previous: dict[Path, bytes] = {}
    for index, path in enumerate(generator.GENERATED_PATHS):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        content = f"previous:{index}\n".encode()
        target.write_bytes(content)
        target.chmod(0o644)
        previous[path] = content
    monkeypatch.setattr(generator, "render_outputs", lambda root=tmp_path: outputs)
    real_replace = generator.os.replace
    calls = 0

    def fail_second_commit(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second commit failure")
        real_replace(*args, **kwargs)

    monkeypatch.setattr(generator.os, "replace", fail_second_commit)
    with pytest.raises(OSError, match="injected second commit failure"):
        generator.install_generated(tmp_path)

    assert calls >= 3
    for path, content in previous.items():
        assert (tmp_path / path).read_bytes() == content
    assert not list(tmp_path.rglob("*.st0303-*"))


def test_check_mode_never_calls_install(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        active_successor, "check_generated", lambda: calls.append("check")
    )
    monkeypatch.setattr(
        active_successor,
        "install_generated",
        lambda root=active_successor.REPO_ROOT: calls.append("install"),
    )

    assert generator.main(["--check"]) == 0
    assert calls == ["check"]
