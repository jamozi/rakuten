"""Fail-closed and resource-bound cases for the ST-0204 loader."""

from __future__ import annotations

import json
from typing import Any

import pytest

from conftest import logical_reference
from raos.config import ConfigurationError, load_runtime_config


@pytest.mark.parametrize("missing", ("RAOS_ENVIRONMENT", "RAOS_SERVICE_NAME"))
def test_missing_required_setting_fails_closed(
    minimal_source: dict[str, object], missing: str
) -> None:
    del minimal_source[missing]

    with pytest.raises(ConfigurationError):
        load_runtime_config(minimal_source)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("RAOS_ENVIRONMENT", ""),
        ("RAOS_ENVIRONMENT", "env-dev"),
        ("RAOS_ENVIRONMENT", "ENV-UNKNOWN"),
        ("RAOS_ENVIRONMENT", "ENV-DEV\x00"),
        ("RAOS_SERVICE_NAME", ""),
        ("RAOS_SERVICE_NAME", "CatalogWorker"),
        ("RAOS_SERVICE_NAME", "catalog_worker"),
        ("RAOS_SERVICE_NAME", "catalog worker"),
        ("RAOS_SERVICE_NAME", "-catalog-worker"),
        ("RAOS_SERVICE_NAME", "catalog-worker-"),
        ("RAOS_SERVICE_NAME", "catalog-worker\n"),
        ("RAOS_SERVICE_NAME", "a" * 64),
        ("RAOS_LOG_LEVEL", "info"),
        ("RAOS_LOG_LEVEL", "TRACE"),
        ("RAOS_LOG_LEVEL", "INFO\t"),
    ],
)
def test_invalid_scalar_setting_is_rejected_without_normalization(
    minimal_source: dict[str, object], key: str, value: str
) -> None:
    minimal_source[key] = value

    with pytest.raises(ConfigurationError):
        load_runtime_config(minimal_source)


@pytest.mark.parametrize("value", (True, 1, 1.0, [], {}, None))
@pytest.mark.parametrize(
    "key", ("RAOS_ENVIRONMENT", "RAOS_SERVICE_NAME", "RAOS_LOG_LEVEL")
)
def test_non_string_scalar_values_are_never_coerced(
    minimal_source: dict[str, object], key: str, value: object
) -> None:
    minimal_source[key] = value

    with pytest.raises(ConfigurationError):
        load_runtime_config(minimal_source)


def test_unrecognized_namespaced_setting_is_rejected(
    minimal_source: dict[str, object], reference_canary: str
) -> None:
    minimal_source["RAOS_UNRECOGNIZED_SETTING"] = reference_canary

    with pytest.raises(ConfigurationError) as captured:
        load_runtime_config(minimal_source)

    rendered = f"{captured.value!s} {captured.value!r}"
    assert "RAOS_UNRECOGNIZED_SETTING" not in rendered
    assert reference_canary not in rendered


def test_wrongly_cased_namespace_cannot_bypass_unknown_key_rejection(
    minimal_source: dict[str, object],
) -> None:
    minimal_source["raos_environment"] = "ENV-DEV"

    with pytest.raises(ConfigurationError):
        load_runtime_config(minimal_source)


def test_non_namespaced_ambient_settings_are_ignored(
    minimal_source: dict[str, object],
) -> None:
    minimal_source["PATH"] = "/synthetic/bin"
    minimal_source["LANG"] = "C.UTF-8"

    config = load_runtime_config(minimal_source)

    assert config.service_name == "catalog-worker"


@pytest.mark.parametrize(
    "encoded",
    (
        "",
        "not-json",
        "null",
        "true",
        "1",
        '"text"',
        "[]",
        '{"database_primary": null}',
        '{"database_primary": true}',
        '{"database_primary": 1}',
        '{"database_primary": {}}',
        '{"database_primary": []}',
        '{"database_primary": NaN}',
        '{"database_primary": Infinity}',
        '{"database_primary": -Infinity}',
    ),
)
def test_secret_reference_input_requires_a_strict_json_object_of_strings(
    minimal_source: dict[str, object], encoded: str
) -> None:
    minimal_source["RAOS_SECRET_REFERENCES"] = encoded

    with pytest.raises(ConfigurationError):
        load_runtime_config(minimal_source)


@pytest.mark.parametrize("value", (True, 1, 1.0, [], {}, None))
def test_secret_reference_container_is_not_coerced(
    minimal_source: dict[str, object], value: object
) -> None:
    minimal_source["RAOS_SECRET_REFERENCES"] = value

    with pytest.raises(ConfigurationError):
        load_runtime_config(minimal_source)


def test_duplicate_json_object_keys_are_rejected_without_echoing_input(
    minimal_source: dict[str, object], reference_canary: str
) -> None:
    scheme = logical_reference("")
    encoded = (
        '{"database_primary":"'
        + scheme
        + "local/first-"
        + reference_canary
        + '","database_primary":"'
        + scheme
        + 'local/second"}'
    )
    minimal_source["RAOS_SECRET_REFERENCES"] = encoded

    with pytest.raises(ConfigurationError) as captured:
        load_runtime_config(minimal_source)

    assert reference_canary not in f"{captured.value!s} {captured.value!r}"


@pytest.mark.parametrize(
    "alias",
    (
        "",
        "UPPER_CASE",
        "hyphen-name",
        "_leading_underscore",
        "0_starts_with_digit",
        "trailing_",
        "double__underscore",
        "has space",
        "has\ncontrol",
        "unicode_参照",
        "a" * 65,
    ),
)
def test_secret_aliases_use_bounded_lower_snake_case(
    minimal_source: dict[str, object], alias: str
) -> None:
    minimal_source["RAOS_SECRET_REFERENCES"] = json.dumps(
        {alias: logical_reference("local/reference")}
    )

    with pytest.raises(ConfigurationError):
        load_runtime_config(minimal_source)


@pytest.mark.parametrize(
    "reference",
    (
        "",
        "local/reference",
        "https://local/reference",
        "".join(("SECRET", "://", "local/reference")),
        logical_reference(""),
        logical_reference("user@local/reference"),
        logical_reference("local/reference?version=1"),
        logical_reference("local/reference#fragment"),
        logical_reference("local/has space"),
        logical_reference("local/has\ttab"),
        logical_reference("local/has\nnewline"),
        logical_reference("local/has\x00nul"),
        logical_reference("local/double//slash"),
        logical_reference("local/../traversal"),
        logical_reference("local/./dot-segment"),
        logical_reference("local/percent%2Fencoding"),
        logical_reference("local/" + "a" * 498),
    ),
)
def test_malformed_or_oversized_secret_references_are_rejected(
    minimal_source: dict[str, object], reference: str
) -> None:
    minimal_source["RAOS_SECRET_REFERENCES"] = json.dumps(
        {"database_primary": reference}
    )

    with pytest.raises(ConfigurationError):
        load_runtime_config(minimal_source)


def test_reference_count_is_bounded_to_sixty_four(
    minimal_source: dict[str, object],
) -> None:
    minimal_source["RAOS_SECRET_REFERENCES"] = json.dumps(
        {
            f"item_{index}": logical_reference(f"local/item-{index}")
            for index in range(65)
        }
    )

    with pytest.raises(ConfigurationError):
        load_runtime_config(minimal_source)


def test_encoded_reference_input_is_bounded_to_sixteen_kibibytes(
    minimal_source: dict[str, object],
) -> None:
    minimal_source["RAOS_SECRET_REFERENCES"] = (
        json.dumps({"database_primary": logical_reference("local/reference")})
        + " " * 16384
    )

    with pytest.raises(ConfigurationError):
        load_runtime_config(minimal_source)


def test_missing_caller_required_alias_fails_closed(
    minimal_source: dict[str, object],
) -> None:
    minimal_source["RAOS_SECRET_REFERENCES"] = json.dumps(
        {"database_primary": logical_reference("local/database-primary")}
    )

    with pytest.raises(ConfigurationError):
        load_runtime_config(
            minimal_source,
            required_secret_aliases=("database_primary", "object_storage"),
        )


@pytest.mark.parametrize(
    "required_alias",
    ("", "UPPER_CASE", "hyphen-name", "has space", "a" * 65),
)
def test_caller_required_aliases_follow_the_same_alias_contract(
    minimal_source: dict[str, object], required_alias: str
) -> None:
    with pytest.raises(ConfigurationError):
        load_runtime_config(
            minimal_source,
            required_secret_aliases=(required_alias,),
        )


def test_caller_required_aliases_reject_duplicates_and_excessive_counts(
    minimal_source: dict[str, object],
) -> None:
    with pytest.raises(ConfigurationError):
        load_runtime_config(
            minimal_source,
            required_secret_aliases=("same_alias", "same_alias"),
        )
    with pytest.raises(ConfigurationError):
        load_runtime_config(
            minimal_source,
            required_secret_aliases=tuple(f"alias_{index}" for index in range(65)),
        )


def test_formal_status_promotion_contract_drift_is_rejected(
    mutable_config_contract: dict[str, Any], reject_config_contract
) -> None:
    mutable_config_contract["document"]["formal_verification"] = "PASS"
    reject_config_contract(mutable_config_contract, "differs from the reviewed value")


def test_secret_value_resolution_scope_creep_is_rejected(
    mutable_config_contract: dict[str, Any], reject_config_contract
) -> None:
    mutable_config_contract["secret_references"]["value_resolution"] = "IMPLEMENTED"
    reject_config_contract(mutable_config_contract, "differs from the reviewed value")


def test_dotenv_scope_creep_is_rejected(
    mutable_config_contract: dict[str, Any], reject_config_contract
) -> None:
    mutable_config_contract["boundary"]["dotenv_loading"] = "ALLOWED"
    reject_config_contract(mutable_config_contract, "differs from the reviewed value")


def test_resource_bound_expansion_contract_drift_is_rejected(
    mutable_config_contract: dict[str, Any], reject_config_contract
) -> None:
    mutable_config_contract["secret_references"]["maximum_input_bytes"] = 65536
    reject_config_contract(mutable_config_contract, "differs from the reviewed value")


def test_boolean_cannot_alias_integer_contract_value(
    mutable_config_contract: dict[str, Any], reject_config_contract
) -> None:
    mutable_config_contract["secret_references"]["maximum_reference_count"] = True
    reject_config_contract(mutable_config_contract, "type differs")
