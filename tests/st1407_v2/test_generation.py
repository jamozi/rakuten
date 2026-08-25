"""Owner generation and provenance tests for ST-1407 V2."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts import build_st1407_external_policy_registry_runtime as generator


def _mutate_notification(payload: bytes) -> bytes:
    return payload.replace(
        b"notification: LOCAL_LOG_ONLY_NOT_DELIVERED_OD_011",
        b"notification: PRODUCTION",
    )


def _mutate_status(payload: bytes) -> bytes:
    return payload.replace(
        b"  status: LOCAL_IMPLEMENTATION_COMPLETE_FOR_UNRESOLVED_BOUNDARY\n",
        b"  status: VALIDATED\n",
    )


def _mutate_authority(payload: bytes) -> bytes:
    return payload.replace(
        b"  authority: NONE\n",
        b"  authority: SYSTEM\n",
    )


def _add_unknown_root_key(payload: bytes) -> bytes:
    return payload.replace(
        b"fixtures:\n",
        b"unknown: true\nfixtures:\n",
    )


def _substitute_authority_path(payload: bytes) -> bytes:
    return payload.replace(
        b"repo://docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
        b"repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
    )


def _substitute_dependency_use(payload: bytes) -> bytes:
    return payload.replace(
        b"use: EXACT_POLICY_ID_VERSION_AND_CATALOG_BINDING",
        b"use: ADDITIVE_RUNTIME_PROVENANCE_ONLY",
    )


def test_expected_artifacts_are_exactly_the_tracked_outputs() -> None:
    artifacts = generator.expected_artifacts()

    assert tuple(path for path, _payload in artifacts) == (
        generator.FIXTURE_PATH,
        generator.MANIFEST_PATH,
    )
    for path, payload in artifacts:
        assert (generator.REPO_ROOT / path).read_bytes() == payload


def test_generated_fixture_has_two_closed_synthetic_cases_and_no_source_body() -> None:
    payload = json.loads((generator.REPO_ROOT / generator.FIXTURE_PATH).read_bytes())

    assert payload["schema_version"] == 2
    assert payload["story_id"] == "ST-1407"
    assert payload["classification"] == "RECORDED_SYNTHETIC_DEV_CI_ONLY"
    assert len(payload["external_rule_policy_links"]) == 13
    assert len(payload["fixtures"]) == 2
    assert payload["fixtures"][0]["report"]["review"]["state"] == "OVERDUE"
    assert (
        payload["fixtures"][0]["report"]["review"]["alert_candidate"]["route"]
        == "LOCAL_LOG_ONLY"
    )
    assert payload["fixtures"][1]["report"]["review"]["state"] == "NOT_DUE"
    assert payload["fixtures"][1]["report"]["impact"]["affected_articles"] == []
    rendered = json.dumps(payload, sort_keys=True).lower()
    for prohibited in (
        "source_body",
        "raw_content",
        "legal_conclusion",
        "notification_destination",
        "review_body",
        "prompt",
        "secret",
        "commission",
        "epc",
        "rpm",
        "profit",
    ):
        assert prohibited not in rendered


def test_every_generated_fixture_hash_is_reproducible() -> None:
    payload = json.loads((generator.REPO_ROOT / generator.FIXTURE_PATH).read_bytes())

    for fixture in payload["fixtures"]:
        expected_fixture_hash = fixture.pop("fixture_sha256")
        observed = hashlib.sha256(
            json.dumps(
                fixture,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest()
        assert observed == expected_fixture_hash


def test_manifest_binds_every_source_and_exact_generated_bytes() -> None:
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    generated = manifest["generated_artifacts"]

    assert manifest["story_id"] == "ST-1407"
    assert manifest["source_artifact_count"] == len(manifest["source_artifacts"])
    assert len({item["uri"] for item in manifest["source_artifacts"]}) == len(
        manifest["source_artifacts"]
    )
    fixture_bytes = (generator.REPO_ROOT / generator.FIXTURE_PATH).read_bytes()
    assert generated == [
        {
            "uri": f"repo://{generator.FIXTURE_PATH.as_posix()}",
            "role": "RECORDED_SYNTHETIC_REGISTRY_FIXTURE",
            "bytes": len(fixture_bytes),
            "sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        }
    ]
    assert manifest["boundary"]["official_source_attested"] is False
    assert manifest["boundary"]["notification_delivered"] is False
    assert manifest["boundary"]["publication_authorized"] is False
    assert manifest["boundary"]["formal_tst_008"] == "NOT_EXECUTED"
    assert manifest["boundary"]["production"] == "NOT_EXECUTED"
    material_paths = {
        f"repo://{path.as_posix()}": expected
        for path, expected in generator.MATERIAL_RUNTIME_DEPENDENCIES
    }
    manifest_sources = {item["uri"]: item for item in manifest["source_artifacts"]}
    for uri, expected in material_paths.items():
        assert manifest_sources[uri]["role"] == "PINNED_RUNTIME_DEPENDENCY"
        assert manifest_sources[uri]["sha256"] == expected


def test_check_mode_passes_without_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("check mode attempted publication")

    monkeypatch.setattr(
        generator.secure_generated_publication, "publish_generated", forbidden
    )

    generator.build(check=True)


@pytest.mark.parametrize(
    "mutator",
    (
        _mutate_notification,
        _mutate_status,
        _mutate_authority,
        _add_unknown_root_key,
        _substitute_authority_path,
        _substitute_dependency_use,
    ),
)
def test_contract_authority_or_shape_drift_fails_closed(
    mutator: Callable[[bytes], bytes],
) -> None:
    original = (generator.REPO_ROOT / generator.CONTRACT_PATH).read_bytes()
    changed = mutator(original)

    with pytest.raises(generator.ExternalPolicyRegistryGenerationError):
        generator.validate_contract_bytes(changed)


def test_contract_duplicate_key_fails_closed() -> None:
    original = (generator.REPO_ROOT / generator.CONTRACT_PATH).read_bytes()
    changed = original.replace(
        b"  story_id: ST-1407\n",
        b"  story_id: ST-1407\n  story_id: ST-1407\n",
    )

    with pytest.raises(generator.ExternalPolicyRegistryGenerationError):
        generator.validate_contract_bytes(changed)


def test_reader_rejects_symlink_and_non_regular_sources(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_bytes(b"safe")
    link = tmp_path / "link.txt"
    link.symlink_to(real)
    directory = tmp_path / "directory"
    directory.mkdir()

    with pytest.raises(generator.ExternalPolicyRegistryGenerationError):
        generator.read_regular_source(tmp_path, Path("link.txt"))
    with pytest.raises(generator.ExternalPolicyRegistryGenerationError):
        generator.read_regular_source(tmp_path, Path("directory"))


def test_reader_rejects_parent_escape_and_absolute_path(tmp_path: Path) -> None:
    with pytest.raises(generator.ExternalPolicyRegistryGenerationError):
        generator.read_regular_source(tmp_path, Path("../escape"))
    with pytest.raises(generator.ExternalPolicyRegistryGenerationError):
        generator.read_regular_source(tmp_path, Path("/absolute"))


def test_material_runtime_dependency_drift_fails_closed() -> None:
    target = generator.MATERIAL_RUNTIME_DEPENDENCIES[0][0]
    original = (generator.REPO_ROOT / target).read_bytes()

    with pytest.raises(
        generator.ExternalPolicyRegistryGenerationError,
        match="SOURCE_HASH_DRIFT",
    ):
        generator.validate_material_runtime_dependency_bytes(target, original + b"\n")


def test_cli_rejects_unknown_argument_without_generation() -> None:
    assert generator.main(["--unknown"]) == 2
