from __future__ import annotations

import inspect
from typing import Any

import pytest

from scripts import build_st0205_synthetic_data as generator


@pytest.mark.parametrize(("domain", "scenario"), generator.FIXTURE_SCENARIOS)
def test_factory_builds_each_reviewed_domain_scenario(
    domain: str, scenario: str
) -> None:
    fixture = generator.build_fixture(domain, scenario)
    assert fixture["schema_domain"] == domain
    assert fixture["scenario"] == scenario
    assert set(fixture["payload"]) == set(generator.PAYLOAD_ALLOWLISTS[domain])
    assert fixture["origin"] == generator.ORIGIN
    assert fixture["license"] == generator.LICENSE


def test_factory_is_byte_deterministic_for_same_seed() -> None:
    assert generator.render_fixture_bundle() == generator.render_fixture_bundle()
    assert generator.build_seed_bundle("repeatable-seed") == (
        generator.build_seed_bundle("repeatable-seed")
    )


def test_different_safe_seed_changes_identifiers_without_disclosing_seed() -> None:
    first = generator.build_fixture("ops", "baseline", seed="safe-seed-one")
    second = generator.build_fixture("ops", "baseline", seed="safe-seed-two")
    assert first["fixture_id"] != second["fixture_id"]
    serialized = generator._json_bytes(second).decode()
    assert "safe-seed-two" not in serialized


def test_missing_classification_defaults_to_confidential(
    mutable_catalog_fixture: dict[str, Any],
) -> None:
    mutable_catalog_fixture.pop("classification")
    normalized = generator.validate_fixture(mutable_catalog_fixture)
    assert normalized["classification"] == "CONFIDENTIAL"


def test_factory_has_no_arbitrary_payload_parameter() -> None:
    assert tuple(inspect.signature(generator.build_fixture).parameters) == (
        "domain",
        "scenario",
        "seed",
        "classification",
    )


def test_factory_rejects_unknown_domain_and_scenario() -> None:
    with pytest.raises(generator.FixtureValidationError, match="unknown"):
        generator.build_fixture("unknown", "baseline")
    with pytest.raises(generator.FixtureValidationError, match="unknown"):
        generator.build_fixture("ops", "unknown")


def test_generated_classification_never_weakens_domain_boundary(
    bundle: dict[str, Any],
) -> None:
    for fixture in bundle["fixtures"]:
        assert (
            fixture["classification"]
            == (generator.CLASSIFICATION_BY_DOMAIN[fixture["schema_domain"]])
        )
        assert fixture["classification"] != "RESTRICTED"
