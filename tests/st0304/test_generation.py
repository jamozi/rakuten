"""Deterministic generation and fail-closed installation tests for ST-0304."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from typing import Any

import pytest
import yaml

from .support import REPOSITORY_ROOT
from scripts import build_st0304_domain_schemas as generator


def _candidate_outputs() -> dict[Path, bytes]:
    return {
        path: f"candidate:{index}:{path.as_posix()}\n".encode()
        for index, path in enumerate(generator.GENERATED_PATHS)
    }


def _seed_outputs(root: Path, prefix: str = "previous") -> dict[Path, bytes]:
    seeded: dict[Path, bytes] = {}
    for index, path in enumerate(generator.GENERATED_PATHS):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        content = f"{prefix}:{index}:{path.as_posix()}\n".encode()
        target.write_bytes(content)
        target.chmod(0o644)
        seeded[path] = content
    return seeded


def _stage_residue(root: Path) -> list[Path]:
    return [path for path in root.rglob(".*.st0304-*")]


def _copy_current_source_artifacts(root: Path) -> None:
    for relative in generator.CURRENT_SOURCE_ARTIFACT_PATHS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)


def _write_repinned_upstream_catalog(root: Path, document: dict[str, Any]) -> bytes:
    content = yaml.safe_dump(
        document,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    ).encode("utf-8")
    target = root / generator.UPSTREAM_CATALOG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return content


def test_revision_is_deterministic_bounded_valid_python_and_exact_identity() -> None:
    first = generator.render_revision()
    second = generator.render_revision()
    text = first.decode("utf-8")

    assert first == second
    assert len(first) < 256 * 1024
    ast.parse(text)
    compile(text, generator.REVISION_PATH.as_posix(), "exec")
    assert 'revision: str = "202608030004"' in text
    assert 'down_revision: str | None = "202608030003"' in text
    assert "- runner version: 1.3.0" in text
    assert "- server version: 180004" in text
    assert "one PostgreSQL transaction" in text
    assert "_PAYLOAD_SHA256" in text


def test_revision_uses_no_parameter_driver_execution_without_rewriting_sql() -> None:
    source = generator.render_revision().decode("utf-8")
    namespace: dict[str, Any] = {}
    exec(compile(source, generator.REVISION_PATH.as_posix(), "exec"), namespace)
    statements = ("SELECT ':0.98', '%';", "SELECT 'exact';")
    observed: list[str] = []
    execution_options: list[dict[str, bool]] = []

    class FakeConnection:
        def execution_options(self, **options: bool) -> FakeConnection:
            execution_options.append(options)
            return self

        def exec_driver_sql(self, statement: str) -> None:
            observed.append(statement)

    class FakeOp:
        def get_bind(self) -> FakeConnection:
            return FakeConnection()

    namespace["op"] = FakeOp()
    namespace["UPGRADE_STATEMENTS"] = statements
    namespace["upgrade"]()

    assert execution_options == [{"no_parameters": True}]
    assert observed == list(statements)


def test_upgrade_and_downgrade_have_exact_transaction_guards() -> None:
    upgrade = generator.render_upgrade_statements()
    downgrade = generator.render_downgrade_statements()
    upgrade_text = "\n".join(upgrade)
    downgrade_text = "\n".join(downgrade)

    assert upgrade[:3] == (
        "SET LOCAL search_path = pg_catalog;",
        "SET LOCAL TIME ZONE 'UTC';",
        "SET LOCAL check_function_bodies = false;",
    )
    assert sum(" NOT VALID;" in item for item in upgrade) == 265
    assert sum("VALIDATE CONSTRAINT" in item for item in upgrade) == 265
    assert upgrade_text.count(" FORCE ROW LEVEL SECURITY") == 11
    assert upgrade_text.count(" ENABLE ROW LEVEL SECURITY") == 11
    assert "CREATE POLICY" not in upgrade_text
    assert "fk_iam_break_glass_record_incident_id" not in upgrade_text

    lock_index = next(
        index for index, item in enumerate(downgrade) if item.startswith("LOCK TABLE ")
    )
    preflight_index = next(
        index
        for index, item in enumerate(downgrade)
        if "ST0304_DOWNGRADE_NONEMPTY" in item
    )
    first_drop_index = next(
        index for index, item in enumerate(downgrade) if "DROP " in item
    )
    assert lock_index < preflight_index < first_drop_index
    assert downgrade_text.count("NO FORCE ROW LEVEL SECURITY") == 11
    assert downgrade_text.count("EXISTS (SELECT 1 FROM ") == 86
    assert downgrade_text.count("DROP TABLE ") == 86
    assert downgrade_text.count("DROP FUNCTION ") == 48
    assert " CASCADE" not in downgrade_text


def test_outputs_are_deterministic_and_preserve_frozen_manifest_snapshot() -> None:
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
    manifest = REPOSITORY_ROOT / generator.MANIFEST_PATH
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o644


def test_catalog_and_manifest_bind_every_source_and_generated_hash() -> None:
    outputs = generator.render_outputs()
    catalog = json.loads(outputs[generator.CATALOG_PATH])
    manifest = yaml.safe_load(outputs[generator.MANIFEST_PATH])

    assert (
        catalog["revision"]["sha256"]
        == hashlib.sha256(outputs[generator.REVISION_PATH]).hexdigest()
    )
    assert (
        catalog["validation"]["sha256"]
        == hashlib.sha256(outputs[generator.VALIDATION_PATH]).hexdigest()
    )
    assert catalog["object_inventory"]["count"] == 1842
    assert catalog["inventory"]["tables"] == 86
    assert catalog["rls_boundary"]["enabled_and_forced_tables"] == list(
        generator.RLS_TABLES
    )
    assert catalog["rls_boundary"]["policy_count"] == 0
    assert catalog["foreign_key_boundary"]["connected_from_st0303"] == (
        "fk_ops_job_site_id"
    )
    assert catalog["foreign_key_boundary"]["retained_deferred"] == (
        "fk_iam_break_glass_record_incident_id"
    )

    sources = manifest["source_artifacts"]
    assert manifest["source_artifact_count"] == len(sources) == 49
    assert len(generator.CURRENT_SOURCE_ARTIFACT_PATHS) == 49
    assert [row["uri"] for row in sources] == [
        f"repo://{path.as_posix()}" for path in generator.CURRENT_SOURCE_ARTIFACT_PATHS
    ]
    assert len({row["uri"] for row in sources}) == len(sources)
    for row in sources:
        path = REPOSITORY_ROOT / row["uri"].removeprefix("repo://")
        content = path.read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == hashlib.sha256(content).hexdigest()
    generated = manifest["generated_artifacts"]
    assert manifest["generated_artifact_count"] == 3 == len(generated)
    for row in generated:
        path = Path(row["uri"].removeprefix("repo://"))
        assert row["bytes"] == len(outputs[path])
        assert row["sha256"] == hashlib.sha256(outputs[path]).hexdigest()
    assert manifest["manifest_self_integrity"] == {
        "included_in_source_artifacts": False,
        "verification": "deterministic byte-for-byte regeneration via --check",
    }


def test_catalog_deep_preserves_the_selected_upstream_baseline_metadata() -> None:
    outputs = generator.render_outputs()
    catalog = json.loads(outputs[generator.CATALOG_PATH])
    upstream = yaml.safe_load(
        (REPOSITORY_ROOT / generator.UPSTREAM_CATALOG_PATH).read_bytes()
    )
    expected_schemas = [
        next(schema for schema in upstream["schemas"] if schema["id"] == schema_id)
        for schema_id in generator.SCHEMAS
    ]
    baseline = catalog["baseline_metadata"]

    assert baseline == {
        "provenance": {
            "translation_rule": "PRESERVE_ALL_BASELINE_TABLE_METADATA",
            "machine_source": {
                "path": f"repo://{generator.UPSTREAM_CATALOG_PATH.as_posix()}",
                "sha256": generator.EXPECTED_UPSTREAM_CATALOG_SHA256,
                "role": "BASELINE_MACHINE_TABLE_INVENTORY",
            },
            "design_source": {
                "path": f"repo://{generator.UPSTREAM_DESIGN_PATH.as_posix()}",
                "sha256": generator.EXPECTED_UPSTREAM_DESIGN_SHA256,
                "role": "DOMAIN_AND_IMMUTABILITY_DESIGN",
            },
        },
        "schema_count": 6,
        "table_count": 66,
        "column_count": 821,
        "schemas": expected_schemas,
    }
    assert [schema["id"] for schema in baseline["schemas"]] == list(generator.SCHEMAS)
    assert all(
        set(schema) == generator.BASELINE_SCHEMA_KEYS for schema in baseline["schemas"]
    )
    assert all(
        set(table) == generator.BASELINE_TABLE_KEYS
        for schema in baseline["schemas"]
        for table in schema["tables"]
    )
    assert all(
        set(column) == generator.BASELINE_COLUMN_KEYS
        for schema in baseline["schemas"]
        for table in schema["tables"]
        for column in table["columns"]
    )


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    (
        ("missing_schema", "upstream schema policy differs"),
        ("duplicate_fqn", "baseline table FQN is duplicated"),
        ("duplicate_column", "baseline column name is duplicated"),
        (
            "missing_physical_table",
            "baseline table is missing from physical inventory",
        ),
        (
            "missing_physical_column",
            "baseline column is missing from physical inventory",
        ),
    ),
)
def test_baseline_metadata_mutations_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_error: str,
) -> None:
    upstream = yaml.safe_load(
        (REPOSITORY_ROOT / generator.UPSTREAM_CATALOG_PATH).read_bytes()
    )
    selected = {
        schema["id"]: schema
        for schema in upstream["schemas"]
        if schema["id"] in generator.SCHEMAS
    }
    if mutation == "missing_schema":
        upstream["schemas"].remove(selected["policy"])
    elif mutation == "duplicate_fqn":
        tables = selected["portfolio"]["tables"]
        tables[1]["fully_qualified_name"] = tables[0]["fully_qualified_name"]
    elif mutation == "duplicate_column":
        columns = selected["portfolio"]["tables"][0]["columns"]
        columns[1]["name"] = columns[0]["name"]
    elif mutation == "missing_physical_table":
        table = selected["portfolio"]["tables"][0]
        table["name"] = "not_in_physical_inventory"
        table["fully_qualified_name"] = "portfolio.not_in_physical_inventory"
    elif mutation == "missing_physical_column":
        selected["portfolio"]["tables"][0]["columns"][0]["name"] = (
            "not_in_physical_inventory"
        )
    else:
        raise AssertionError(f"unhandled mutation: {mutation}")

    content = _write_repinned_upstream_catalog(tmp_path, upstream)
    monkeypatch.setattr(
        generator,
        "EXPECTED_UPSTREAM_CATALOG_SHA256",
        hashlib.sha256(content).hexdigest(),
    )

    with pytest.raises(RuntimeError, match=expected_error):
        generator._load_baseline_metadata(tmp_path, generator._load_objects())


def test_source_validation_rejects_a_missing_finalized_overlay_checkpoint(
    tmp_path: Path,
) -> None:
    _copy_current_source_artifacts(tmp_path)
    checkpoint = tmp_path / (
        "changes/st-0003/database/202607300007_ai_governance_expand.sql"
    )
    checkpoint.unlink()

    with pytest.raises(FileNotFoundError):
        generator.validate_source_inputs(tmp_path)


def test_source_validation_accepts_a_semantic_noop_checkpoint_comment(
    tmp_path: Path,
) -> None:
    _copy_current_source_artifacts(tmp_path)
    checkpoint = tmp_path / (
        "changes/st-0004/database/202607300017_content_contract.sql"
    )
    checkpoint.write_bytes(checkpoint.read_bytes() + b"\n-- semantic no-op\n")
    generator.validate_source_inputs(tmp_path)


def test_main_check_mode_never_calls_install(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(generator, "check_generated", lambda: calls.append("check"))
    monkeypatch.setattr(
        generator,
        "install_generated",
        lambda root=generator.REPO_ROOT: calls.append("install"),
    )

    assert generator.main(["--check"]) == 0
    assert calls == ["check"]


def test_install_creates_the_exact_bundle_with_safe_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = _candidate_outputs()
    monkeypatch.setattr(generator, "render_outputs", lambda root=tmp_path: outputs)

    generator.install_generated(tmp_path)

    for path, content in outputs.items():
        target = tmp_path / path
        assert target.read_bytes() == content
        assert stat.S_IMODE(target.stat().st_mode) == 0o644
    assert _stage_residue(tmp_path) == []


def test_stage_failure_preserves_the_complete_original_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = _seed_outputs(tmp_path)
    outputs = _candidate_outputs()
    monkeypatch.setattr(generator, "render_outputs", lambda root=tmp_path: outputs)
    real_stage = generator._stage_output

    def fail_third_stage(root: Path, path: Path, content: bytes, ordinal: int):
        if ordinal == 2:
            raise OSError("injected stage failure")
        return real_stage(root, path, content, ordinal)

    monkeypatch.setattr(generator, "_stage_output", fail_third_stage)
    with pytest.raises(OSError, match="injected stage failure"):
        generator.install_generated(tmp_path)

    assert {path: (tmp_path / path).read_bytes() for path in previous} == previous
    assert _stage_residue(tmp_path) == []


def test_mid_commit_failure_rolls_back_without_a_partial_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = _seed_outputs(tmp_path)
    outputs = _candidate_outputs()
    monkeypatch.setattr(generator, "render_outputs", lambda root=tmp_path: outputs)
    real_replace = generator.os.replace
    calls = 0

    def fail_second_replace(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected commit failure")
        real_replace(*args, **kwargs)

    monkeypatch.setattr(generator.os, "replace", fail_second_replace)
    with pytest.raises(OSError, match="injected commit failure"):
        generator.install_generated(tmp_path)

    assert {path: (tmp_path / path).read_bytes() for path in previous} == previous
    assert _stage_residue(tmp_path) == []


def test_install_rejects_a_symlink_target_without_touching_its_referent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = _candidate_outputs()
    monkeypatch.setattr(generator, "render_outputs", lambda root=tmp_path: outputs)
    target = tmp_path / generator.REVISION_PATH
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside.py"
    outside.write_bytes(b"outside\n")
    target.symlink_to(outside)

    with pytest.raises(RuntimeError, match="regular non-symlink"):
        generator.install_generated(tmp_path)
    assert outside.read_bytes() == b"outside\n"


def test_install_rejects_a_symlink_ancestor_without_writing_outside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = _candidate_outputs()
    monkeypatch.setattr(generator, "render_outputs", lambda root=tmp_path: outputs)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "migrations").symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError):
        generator.install_generated(tmp_path)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("kind", ("directory", "fifo"))
def test_install_rejects_special_targets_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    outputs = _candidate_outputs()
    monkeypatch.setattr(generator, "render_outputs", lambda root=tmp_path: outputs)
    target = tmp_path / generator.REVISION_PATH
    target.parent.mkdir(parents=True)
    if kind == "directory":
        target.mkdir()
    else:
        os.mkfifo(target)

    with pytest.raises(RuntimeError, match="regular non-symlink"):
        generator.install_generated(tmp_path)


@pytest.mark.parametrize("flag_name", ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"))
def test_source_validation_requires_every_secure_open_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flag_name: str,
) -> None:
    monkeypatch.delattr(generator.os, flag_name)

    with pytest.raises(RuntimeError, match=rf"secure open flag {flag_name} "):
        generator.validate_source_inputs(tmp_path)


@pytest.mark.parametrize("flag_name", ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"))
@pytest.mark.parametrize("operation", ("install", "check"))
def test_generated_bundle_operations_require_every_secure_open_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flag_name: str,
    operation: str,
) -> None:
    outputs = _candidate_outputs()
    _seed_outputs(tmp_path)
    monkeypatch.setattr(generator, "render_outputs", lambda root=tmp_path: outputs)
    monkeypatch.delattr(generator.os, flag_name)

    action = (
        generator.install_generated
        if operation == "install"
        else generator.check_generated
    )
    with pytest.raises(RuntimeError, match=rf"secure open flag {flag_name} "):
        action(tmp_path)
    assert _stage_residue(tmp_path) == []


@pytest.mark.parametrize("kind", ("symlink", "fifo"))
def test_secure_read_rejects_nonregular_sources_without_blocking(
    tmp_path: Path, kind: str
) -> None:
    source = tmp_path / "source.txt"
    if kind == "symlink":
        referent = tmp_path / "referent.txt"
        referent.write_bytes(b"source\n")
        source.symlink_to(referent)
    else:
        os.mkfifo(source)

    with pytest.raises(RuntimeError, match="regular file"):
        generator._secure_read(tmp_path, Path("source.txt"), "test source", 1024)


def test_secure_read_rejects_a_preopen_inode_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.txt"
    pinned = tmp_path / "pinned.txt"
    source.write_bytes(b"approved\n")
    real_open = generator.os.open
    injected = False

    def replace_then_open(
        path: Any, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        nonlocal injected
        if not injected and path == source.name and dir_fd is not None:
            source.rename(pinned)
            source.write_bytes(b"replacement\n")
            injected = True
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(generator.os, "open", replace_then_open)
    with pytest.raises(RuntimeError, match="changed while it was being verified"):
        generator._secure_read(tmp_path, Path("source.txt"), "test source", 1024)


def test_secure_read_rejects_mutation_during_descriptor_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"approved\n")
    real_read = generator.os.read
    injected = False

    def mutate_then_read(descriptor: int, count: int) -> bytes:
        nonlocal injected
        if not injected:
            source.write_bytes(b"changed-content\n")
            injected = True
        return real_read(descriptor, count)

    monkeypatch.setattr(generator.os, "read", mutate_then_read)
    with pytest.raises(RuntimeError, match="changed while it was being verified"):
        generator._secure_read(tmp_path, Path("source.txt"), "test source", 1024)
