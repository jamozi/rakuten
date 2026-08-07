from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from scripts import build_st0205_synthetic_data as generator
from scripts import scan_secrets


def _walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(generator._normalized_key(key))
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def test_generated_bundle_has_no_prohibited_structural_fields(
    bundle: dict[str, Any],
) -> None:
    assert _walk_keys(bundle).isdisjoint(generator.PROHIBITED_STRUCTURAL_KEYS)
    for fixture in bundle["fixtures"]:
        assert set(fixture["payload"]) == set(
            generator.PAYLOAD_ALLOWLISTS[fixture["schema_domain"]]
        )


def test_generated_bundle_has_no_secret_scanner_findings() -> None:
    content = generator.render_fixture_bundle()
    assert scan_secrets.scan_bytes(content, "st0205-fixtures") == set()


def test_only_readmodel_fixture_is_public(bundle: dict[str, Any]) -> None:
    public = [
        fixture
        for fixture in bundle["fixtures"]
        if fixture["classification"] == "PUBLIC"
    ]
    assert [(fixture["schema_domain"], fixture["scenario"]) for fixture in public] == [
        ("readmodel", "unicode-locale")
    ]
    assert all(
        fixture["classification"] != "RESTRICTED" for fixture in bundle["fixtures"]
    )


def test_legitimate_policy_metadata_is_not_a_substring_false_positive(
    mutable_catalog_fixture: dict[str, Any],
) -> None:
    generator._reject_prohibited_structural_keys(
        {
            "review_count": 12,
            "review_average": 4,
            "email_verified": False,
            "policy_metric": "NO_REVIEW_BODY",
        }
    )
    mutable_catalog_fixture["payload"]["label"] = (
        "NO_REVIEW_BODY review_count email_verified 999.999.999.999 v1.2.3.4"
    )
    assert (
        generator.validate_fixture(mutable_catalog_fixture)["payload"]["label"]
        == (mutable_catalog_fixture["payload"]["label"])
    )


@pytest.mark.parametrize("key", ["review_body", "reviewText", "review-author"])
def test_review_content_fields_fail_structurally_without_value_echo(
    mutable_catalog_fixture: dict[str, Any],
    key: str,
) -> None:
    canary = "marker-that-must-not-echo"
    mutable_catalog_fixture["payload"][key] = canary
    with pytest.raises(generator.FixtureValidationError) as raised:
        generator.validate_fixture(mutable_catalog_fixture)
    assert "prohibited data field" in str(raised.value)
    assert canary not in str(raised.value)


@pytest.mark.parametrize("key", ["ｒｅｖｉｅｗ＿ｂｏｄｙ", "ｅｍａｉｌ"])
def test_nfkc_equivalent_prohibited_fields_fail_closed(
    mutable_catalog_fixture: dict[str, Any],
    key: str,
) -> None:
    mutable_catalog_fixture["payload"][key] = "synthetic-canary"
    with pytest.raises(generator.FixtureValidationError, match="prohibited data field"):
        generator.validate_fixture(mutable_catalog_fixture)


@pytest.mark.parametrize(
    "key",
    [
        "customer_id",
        "poster_name",
        "email",
        "raw_ip",
        "raw_user_agent",
        "api_key",
        "raw_prompt",
        "provider_body",
    ],
)
def test_person_provider_and_credential_fields_fail_closed(
    mutable_catalog_fixture: dict[str, Any],
    key: str,
) -> None:
    mutable_catalog_fixture["payload"][key] = "synthetic-canary"
    with pytest.raises(generator.FixtureValidationError, match="prohibited data field"):
        generator.validate_fixture(mutable_catalog_fixture)


def test_email_value_is_rejected_without_echo(
    mutable_catalog_fixture: dict[str, Any],
    email_canary: str,
) -> None:
    mutable_catalog_fixture["payload"]["label"] = email_canary
    with pytest.raises(generator.FixtureValidationError) as raised:
        generator.validate_fixture(mutable_catalog_fixture)
    assert "personal data" in str(raised.value)
    assert email_canary not in str(raised.value)


@pytest.mark.parametrize(
    "address",
    ["192.0.2.1", "https://192.0.2.1/path", "2001:db8::1"],
)
def test_valid_ipv4_and_ipv6_values_are_rejected_without_echo(
    mutable_catalog_fixture: dict[str, Any],
    address: str,
) -> None:
    mutable_catalog_fixture["payload"]["label"] = address
    with pytest.raises(generator.FixtureValidationError) as raised:
        generator.validate_fixture(mutable_catalog_fixture)
    assert "network identity" in str(raised.value)
    assert address not in str(raised.value)


def test_secret_value_is_rejected_by_repository_scanner_without_echo(
    mutable_catalog_fixture: dict[str, Any],
    secret_canary: str,
) -> None:
    mutable_catalog_fixture["payload"]["label"] = secret_canary
    with pytest.raises(generator.FixtureValidationError) as raised:
        generator.validate_fixture(mutable_catalog_fixture)
    assert "credential material" in str(raised.value)
    assert secret_canary not in str(raised.value)


def test_fixture_validation_does_not_mutate_caller_mapping(
    mutable_catalog_fixture: dict[str, Any],
) -> None:
    original = deepcopy(mutable_catalog_fixture)
    generator.validate_fixture(mutable_catalog_fixture)
    assert mutable_catalog_fixture == original
