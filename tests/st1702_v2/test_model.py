"""Domain and hostile-record coverage for the ST-1702 V2 fixture."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
import pickle
from pathlib import Path

import pytest

from raos.domain.catalog.category_fixtures import (
    CategoryActivation,
    CategoryFixtureFailure,
    CategoryFixtureFailureCode,
    ExpectedIdentityOutcome,
    FreshnessActivation,
    IdentityActivation,
    IdentityScenario,
    build_category_fixture_bundle,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "changes/st-1702/generated/category-fixture-runtime-recorded.v2.json"


def _material() -> tuple[dict[str, object], str]:
    payload = FIXTURE.read_bytes()
    return json.loads(payload), hashlib.sha256(payload).hexdigest()


def _bundle():  # type: ignore[no-untyped-def]
    record, digest = _material()
    return build_category_fixture_bundle(record, source_fixture_sha256=digest)


def test_fixture_builds_exact_maximum_safe_boundary() -> None:
    bundle = _bundle()
    assert bundle.category_id == "synthetic_validator_category"
    assert bundle.candidate_category_id == "suitcase_and_carry_bags"
    assert bundle.category_activation is CategoryActivation.DISABLED_UNRESOLVED_OD_001
    assert tuple(item.key for item in bundle.attribute_schema) == (
        "model_code",
        "size_code",
        "variant_code",
        "set_count",
    )
    assert len(bundle.golden_products) == 4
    assert len(bundle.identity_cases) == 3
    assert bundle.identity_activation is IdentityActivation.DISABLED_UNRESOLVED_OD_006
    assert bundle.freshness_activation is FreshnessActivation.DISABLED_UNRESOLVED_OD_007
    assert all(item.source == "SYNTHETIC_ONLY" for item in bundle.golden_products)
    assert all(not item.provider_evidence_present for item in bundle.golden_products)
    assert all(not item.publication_eligible for item in bundle.golden_products)


def test_identity_cases_are_ordered_human_review_scenarios() -> None:
    bundle = _bundle()
    assert tuple(case.scenario for case in bundle.identity_cases) == (
        IdentityScenario.EXACT_SYNTHETIC_FIELDS,
        IdentityScenario.VARIANT_DIFFERENCE,
        IdentityScenario.SET_COUNT_DIFFERENCE,
    )
    assert all(
        case.expected_outcome is ExpectedIdentityOutcome.HUMAN_REVIEW
        and case.reason_code == "OD006_EVIDENCE_REQUIRED"
        for case in bundle.identity_cases
    )


def test_every_authority_and_effect_surface_is_closed() -> None:
    bundle = _bundle()
    assert bundle.automatic_merge_enabled is False
    assert bundle.automatic_split_enabled is False
    assert bundle.human_review_required is True
    assert bundle.domain_reviewer_approval == "NOT_OBTAINED"
    assert bundle.category_overrides == ()
    assert bundle.provider_overrides == ()
    assert bundle.stale_never_fresh is True
    assert bundle.recommendation_auto_reorder == "FORBIDDEN"
    assert all(
        value is False
        for value in (
            bundle.runtime_enabled,
            bundle.provider_access_enabled,
            bundle.network_enabled,
            bundle.persistence_enabled,
            bundle.external_actions_enabled,
            bundle.publication_authorized,
            bundle.activation_authorized,
            bundle.release_authorized,
            bundle.production_authorized,
            bundle.formal_acceptance_achieved,
        )
    )
    assert bundle.formal_tst_020 == "NOT_EXECUTED"


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("category", "candidateApplied"), True),
        (("category", "categoryId"), "suitcase_and_carry_bags"),
        (("identityPolicy", "automaticMergeEnabled"), True),
        (("identityPolicy", "automaticSplitEnabled"), True),
        (("identityPolicy", "humanReviewRequired"), False),
        (("identityPolicy", "domainReviewerApproval"), "APPROVED"),
        (("freshnessPolicy", "categoryOverrides"), ["unsafe"]),
        (("freshnessPolicy", "staleNeverFresh"), False),
        (("authority", "runtimeEnabled"), True),
        (("authority", "providerAccessEnabled"), True),
        (("authority", "networkEnabled"), True),
        (("authority", "persistenceEnabled"), True),
        (("authority", "publicationAuthorized"), True),
        (("authority", "productionAuthorized"), True),
        (("authority", "formalTst020"), "PASS"),
    ),
)
def test_unsafe_contract_mutations_fail_closed(
    path: tuple[str, str], value: object
) -> None:
    record, digest = _material()
    mutated = deepcopy(record)
    nested = mutated[path[0]]
    assert isinstance(nested, dict)
    nested[path[1]] = value
    with pytest.raises(CategoryFixtureFailure) as captured:
        build_category_fixture_bundle(mutated, source_fixture_sha256=digest)
    assert captured.value.code is CategoryFixtureFailureCode.FIXTURE_INVALID


@pytest.mark.parametrize(
    "mutation",
    (
        "unknown_top_key",
        "duplicate_product_id",
        "invalid_uuid_version",
        "wrong_attribute_order",
        "wrong_variant_semantics",
        "provider_fact_field",
    ),
)
def test_malformed_or_provider_shaped_records_fail_closed(mutation: str) -> None:
    record, digest = _material()
    mutated = deepcopy(record)
    if mutation == "unknown_top_key":
        mutated["unknown"] = True
    elif mutation == "duplicate_product_id":
        mutated["goldenProducts"][1]["productId"] = mutated["goldenProducts"][0][
            "productId"
        ]  # type: ignore[index]
    elif mutation == "invalid_uuid_version":
        mutated["fixtureId"] = "00000000-0000-4000-8000-000000001702"
    elif mutation == "wrong_attribute_order":
        mutated["attributeSchema"][0]["key"] = "size_code"  # type: ignore[index]
    elif mutation == "wrong_variant_semantics":
        mutated["goldenProducts"][2]["attributes"]["size_code"] = "SIZE_LARGE"  # type: ignore[index]
    else:
        mutated["goldenProducts"][0]["price"] = 1  # type: ignore[index]
    with pytest.raises(CategoryFixtureFailure):
        build_category_fixture_bundle(mutated, source_fixture_sha256=digest)


def test_hash_argument_is_strict_and_not_recomputed_from_untrusted_record() -> None:
    record, _digest = _material()
    for value in ("0" * 63, "G" * 64, b"0" * 64, None):
        with pytest.raises(CategoryFixtureFailure):
            build_category_fixture_bundle(record, source_fixture_sha256=value)


def test_dependency_owner_binding_mutation_fails_closed() -> None:
    record, digest = _material()
    bindings = record["bindings"]
    assert isinstance(bindings, dict)
    bindings["st1701_decision_package"]["owner_id"] = "unknown_owner"
    with pytest.raises(CategoryFixtureFailure) as captured:
        build_category_fixture_bundle(record, source_fixture_sha256=digest)
    assert captured.value.code is CategoryFixtureFailureCode.FIXTURE_INVALID


def test_domain_values_are_frozen_redacted_and_non_pickleable() -> None:
    bundle = _bundle()
    values = (
        bundle,
        bundle.attribute_schema[0],
        bundle.golden_products[0],
        bundle.identity_cases[0],
        bundle.source_bindings[0],
    )
    for value in values:
        rendered = repr(value)
        assert "Synthetic Alpha" not in rendered
        assert "suitcase_and_carry_bags" not in rendered
        assert "redacted-category-fixture" in rendered
        with pytest.raises((TypeError, pickle.PicklingError)):
            pickle.dumps(value)
    with pytest.raises(FrozenInstanceError):
        bundle.category_id = "changed"  # type: ignore[misc]


def test_failure_diagnostic_is_closed_and_non_pickleable() -> None:
    record, digest = _material()
    record["storyId"] = "secret-canary"
    with pytest.raises(CategoryFixtureFailure) as captured:
        build_category_fixture_bundle(record, source_fixture_sha256=digest)
    assert str(captured.value) == "FIXTURE_INVALID"
    assert "secret-canary" not in repr(captured.value)
    with pytest.raises(TypeError):
        pickle.dumps(captured.value)
