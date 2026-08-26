"""Deterministic, provenance-complete, fail-closed ST-0302 generator tests."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from .support import REPOSITORY_ROOT
from scripts import build_st0302_foundation as generator


FROZEN_MANIFEST_PATH = Path(
    "changes/st-0005/evidence/artifacts/"
    "d9db1f849ec8ff29a10736e03e98dad34a9a978147c26ed46c8dfa65911b2aa0-"
    "manifest.yaml"
)


def test_historical_renderer_is_deterministic_and_frozen_outputs_remain_pinned() -> (
    None
):
    first = generator.render_outputs()
    second = generator.render_outputs()

    assert first == second
    assert tuple(first) == (
        generator.REVISION_PATH,
        generator.VALIDATION_PATH,
        generator.CATALOG_PATH,
        generator.MANIFEST_PATH,
    )
    for path, content in first.items():
        if path == generator.MANIFEST_PATH:
            continue
        assert (REPOSITORY_ROOT / path).read_bytes() == content
    assert (REPOSITORY_ROOT / FROZEN_MANIFEST_PATH).is_file()


def test_generated_catalog_binds_revision_validation_and_exact_boundary() -> None:
    value = json.loads((REPOSITORY_ROOT / generator.CATALOG_PATH).read_bytes())
    revision = (REPOSITORY_ROOT / generator.REVISION_PATH).read_bytes()
    validation = (REPOSITORY_ROOT / generator.VALIDATION_PATH).read_bytes()

    assert value["revision"]["revision"] == "202608030002"
    assert value["revision"]["down_revision"] == "202608030001"
    assert value["revision"]["sha256"] == hashlib.sha256(revision).hexdigest()
    assert value["validation"]["sha256"] == hashlib.sha256(validation).hexdigest()
    assert value["extensions"]["created"] == []
    assert value["types"]["custom_types_created"] == []
    assert value["types"]["native_enums_created"] == []
    assert value["boundary"]["formal_tst_008"] == "NOT_EXECUTED"
    assert value["boundary"]["effective_canonical_status"] == "UNCHANGED"


def test_contract_verification_uses_the_clean_repository_migration_gate() -> None:
    contract = generator._load_contract()
    command = contract["verification"]["local_command"]
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")

    assert command == "make final"
    assert "final:" in makefile
    assert "$(MAKE) contracts database storage" in makefile
    assert "/home/" not in command


def test_entrypoint_checks_its_own_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []
    monkeypatch.setattr(generator, "check_generated", lambda: observed.append("check"))

    assert generator.main(["--check"]) == 0
    assert observed == ["check"]


def test_manifest_inventory_is_exact_unique_and_attests_runtime_fixture() -> None:
    manifest = yaml.safe_load(
        (REPOSITORY_ROOT / generator.MANIFEST_PATH).read_text(encoding="utf-8")
    )
    sources = [item["uri"] for item in manifest["source_artifacts"]]
    generated = [item["uri"] for item in manifest["generated_artifacts"]]

    assert len(sources) == len(set(sources)) == len(generator.SOURCE_ARTIFACT_PATHS)
    assert manifest["source_artifact_count"] == len(sources)
    assert manifest["generated_artifact_count"] == len(generated) == 3
    assert "repo://tests/postgresql18.py" in sources
    assert "repo://changes/st-0301/manifest.yaml" in sources
    assert not any(uri.startswith("repo://zip/") for uri in sources)
    assert not any(uri.startswith("repo://docs/canonical/") for uri in sources)
    assert not any(uri.startswith("repo://docs/upstream/") for uri in sources)
    assert generated == [
        f"repo://{generator.REVISION_PATH.as_posix()}",
        f"repo://{generator.VALIDATION_PATH.as_posix()}",
        f"repo://{generator.CATALOG_PATH.as_posix()}",
    ]


def test_manifest_pins_immutable_predecessor_and_all_canonical_inputs() -> None:
    manifest = yaml.safe_load(
        (REPOSITORY_ROOT / generator.MANIFEST_PATH).read_text(encoding="utf-8")
    )
    assert manifest["provenance"]["predecessor_manifest"] == {
        "story_id": "ST-0301",
        "uri": "repo://changes/st-0301/manifest.yaml",
        "sha256": generator.EXPECTED_PREDECESSOR_SHA256,
    }
    assert {
        item["uri"].removeprefix("repo://"): item["sha256"]
        for item in manifest["provenance"]["canonical_and_upstream_inputs"]
    } == generator.PINNED_INPUTS


def test_validation_is_story_sliced_and_binds_the_rendered_revision() -> None:
    revision = generator.render_revision(generator._load_contract())
    digest = hashlib.sha256(revision).hexdigest()
    text = generator.render_validation_sql(digest).decode("utf-8")

    assert f"source_sha256 = '{digest}'" in text
    assert "server_version_num')::integer <> 180004" in text
    assert "pg_catalog.uuidv7()" in text
    assert "pg_catalog.pg_collation" in text
    assert "pg_catalog.pg_operator" in text
    assert "pg_catalog.pg_ts_config" in text
    assert "pg_catalog.pg_statistic_ext" in text
    assert "pg_catalog.pg_default_acl" in text
    assert "LEFT JOIN pg_catalog.pg_namespace AS n" in text
    assert "defaults.defaclnamespace = 0" in text
    assert "defaclobjtype" not in text
    assert "current_setting('TimeZone') <> 'UTC'" in text
    assert "ST0302_TIMEZONE_MISMATCH" in text
    assert "(SELECT count(*) FROM public.raos_migration_version) <> 1" in text
    assert "(SELECT count(*) FROM public.raos_migration_history) <> 3" in text
    assert "succeeded.transaction_id = version.xmin::text" in text
    assert "ST0302_LATER_SCHEMA_PRESENT" in text
    assert "130" not in text
    assert "357" not in text
    assert "CREATE " not in text.upper()


def test_predecessor_digest_is_not_an_implementation_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_hash = generator.shared.sha256_file

    def drift(path: Path) -> str:
        if path == REPOSITORY_ROOT / generator.PREDECESSOR_PATH:
            return "0" * 64
        return real_hash(path)

    monkeypatch.setattr(generator.shared, "sha256_file", drift)
    assert generator.render_outputs()


def test_contract_semantic_or_scalar_type_drift_fails_before_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = generator._load_contract()
    real_load = generator.shared.load_yaml

    for path, value, expected_error in (
        (("schemas", 0, "comment"), "injected'", "foundation schemas differ"),
        (
            ("security", "non_owner_schema_privileges"),
            "ALLOWED",
            "security contract differs",
        ),
        (("verification", "unexpected"), True, "verification contract differs"),
        (
            ("verification", "local_command"),
            "curl https://untrusted.invalid",
            "verification contract differs",
        ),
        (("database", "transactional_ddl"), 1, "database contract differs"),
        (("revision", "server_version_num"), 180004.0, "revision contract differs"),
    ):
        contract = copy.deepcopy(baseline)
        target: Any = contract
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value

        def load(path: Path, mutated: dict[str, object] = contract):
            if path == REPOSITORY_ROOT / generator.CONTRACT_PATH:
                return mutated
            return real_load(path)

        monkeypatch.setattr(generator.shared, "load_yaml", load)
        with pytest.raises(RuntimeError, match=expected_error):
            generator._load_contract()


def test_check_mode_never_installs(monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[Path] = []
    monkeypatch.setattr(generator, "check_generated", lambda: None)
    monkeypatch.setattr(
        generator,
        "install_generated",
        lambda root=generator.REPO_ROOT: writes.append(root),
    )

    assert generator.main(["--check"]) == 0
    assert writes == []


def test_install_rejects_symlink_target_and_ancestor(tmp_path: Path) -> None:
    target = tmp_path / generator.CATALOG_PATH
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_bytes(b"unchanged")
    target.symlink_to(outside)

    with pytest.raises(RuntimeError, match="regular non-symlink"):
        generator._install(generator.CATALOG_PATH, b"candidate", tmp_path)
    assert outside.read_bytes() == b"unchanged"

    root = tmp_path / "second"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (root / "changes").symlink_to(external, target_is_directory=True)
    with pytest.raises(OSError):
        generator._install(generator.CATALOG_PATH, b"candidate", root)
    assert list(external.iterdir()) == []
