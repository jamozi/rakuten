from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from scripts import build_st0205_synthetic_data as generator


@pytest.mark.parametrize("story_index", [0, 1])
def test_dependency_manifest_hash_mismatch_fails_before_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    story_index: int,
) -> None:
    _story, relative, _digest = generator.PREDECESSOR_MANIFESTS[story_index]
    tampered = tmp_path / relative.name
    tampered.write_bytes((generator.REPO_ROOT / relative).read_bytes() + b"\n")
    real_regular_file = generator.shared._repository_regular_file

    def repository_regular_file(root: Path, path: Path, label: str) -> Path:
        if path == relative:
            return tampered
        return real_regular_file(root, path, label)

    monkeypatch.setattr(
        generator.shared,
        "_repository_regular_file",
        repository_regular_file,
    )
    with pytest.raises(RuntimeError, match="predecessor manifest digest drift"):
        generator.render_outputs()


def test_unknown_contract_field_fails_closed(
    contract: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mutated = deepcopy(contract)
    mutated["unreviewed"] = True
    monkeypatch.setattr(generator.shared, "load_yaml", lambda _path: mutated)
    with pytest.raises(RuntimeError, match="top-level fields differ"):
        generator.load_and_validate_contract()


def test_unknown_fixture_field_fails_closed(
    mutable_catalog_fixture: dict[str, Any],
) -> None:
    mutable_catalog_fixture["unreviewed"] = "value"
    with pytest.raises(generator.FixtureValidationError, match="fields differ"):
        generator.validate_fixture(mutable_catalog_fixture)


def test_unknown_payload_field_fails_closed(
    mutable_catalog_fixture: dict[str, Any],
) -> None:
    mutable_catalog_fixture["payload"]["unknown_metric"] = 1
    with pytest.raises(generator.FixtureValidationError, match="payload fields differ"):
        generator.validate_fixture(mutable_catalog_fixture)


def test_unknown_classification_and_restricted_are_distinct_refusals(
    mutable_catalog_fixture: dict[str, Any],
) -> None:
    mutable_catalog_fixture["classification"] = "UNREVIEWED"
    with pytest.raises(
        generator.FixtureValidationError, match="unknown classification"
    ):
        generator.validate_fixture(mutable_catalog_fixture)
    mutable_catalog_fixture["classification"] = "RESTRICTED"
    with pytest.raises(generator.FixtureValidationError, match="restricted data"):
        generator.validate_fixture(mutable_catalog_fixture)


@pytest.mark.parametrize("field", ["origin", "license"])
def test_missing_origin_or_license_fails_closed(
    mutable_catalog_fixture: dict[str, Any],
    field: str,
) -> None:
    mutable_catalog_fixture.pop(field)
    with pytest.raises(generator.FixtureValidationError, match="fields differ"):
        generator.validate_fixture(mutable_catalog_fixture)


def test_production_copy_marker_fails_without_echo(
    mutable_catalog_fixture: dict[str, Any],
) -> None:
    canary = "production-copy-marker-91"
    mutable_catalog_fixture["payload"]["label"] = canary
    with pytest.raises(generator.FixtureValidationError) as raised:
        generator.validate_fixture(mutable_catalog_fixture)
    assert "sensitive data" in str(raised.value)
    assert canary not in str(raised.value)


def test_credential_shaped_seed_fails_without_echo(secret_canary: str) -> None:
    with pytest.raises(generator.FixtureValidationError) as raised:
        generator.build_seed_bundle(secret_canary)
    assert "credential material" in str(raised.value)
    assert secret_canary not in str(raised.value)


def test_invalid_dotted_version_is_not_misclassified_as_an_ip(
    mutable_catalog_fixture: dict[str, Any],
) -> None:
    value = "release-999.999.999.999-v1.2.3.4"
    mutable_catalog_fixture["payload"]["label"] = value
    assert (
        generator.validate_fixture(mutable_catalog_fixture)["payload"]["label"] == value
    )


def test_nondeterministic_renderer_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def alternating(_seed: str = generator.DEFAULT_SEED) -> bytes:
        nonlocal calls
        calls += 1
        return b"first" if calls == 1 else b"second"

    monkeypatch.setattr(generator, "_render_fixture_bundle_once", alternating)
    with pytest.raises(generator.FixtureValidationError, match="nondeterministic"):
        generator.render_fixture_bundle()


def test_missing_license_authority_fails_before_fixture_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = tmp_path / "package.json"
    invalid.write_text('{"license":"DIFFERENT"}\n')
    real_regular_file = generator.shared._repository_regular_file

    def repository_regular_file(root: Path, path: Path, label: str) -> Path:
        if path == generator.LICENSE_AUTHORITY_PATH:
            return invalid
        return real_regular_file(root, path, label)

    monkeypatch.setattr(
        generator.shared,
        "_repository_regular_file",
        repository_regular_file,
    )
    with pytest.raises(RuntimeError, match="license authority digest drift"):
        generator.render_outputs()
