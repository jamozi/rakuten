"""Typed loading behavior for the ST-0204 runtime configuration boundary."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any, cast

from pydantic import TypeAdapter, ValidationError
import pytest

from conftest import CANONICAL_ENVIRONMENTS, logical_reference
from raos.config import (
    LogLevel,
    RuntimeConfig,
    RuntimeEnvironment,
    SecretReference,
    load_runtime_config,
    load_runtime_config_from_environment,
)


def _typed_runtime_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "environment": RuntimeEnvironment("ENV-DEV"),
        "service_name": "catalog-worker",
        "log_level": LogLevel("INFO"),
        "secret_references": {
            "database_primary": SecretReference(
                logical_reference("fixture/database-primary")
            )
        },
    }


def _coercible_runtime_payload(case: str) -> dict[str, object]:
    payload = _typed_runtime_payload()
    if case == "schema_version_bool":
        payload["schema_version"] = True
    elif case == "environment_string":
        payload["environment"] = "ENV-DEV"
    elif case == "log_level_string":
        payload["log_level"] = "INFO"
    elif case == "reference_bytes":
        payload["secret_references"] = {
            "database_primary": logical_reference("fixture/database-primary").encode()
        }
    else:
        raise AssertionError(f"unknown coercion case: {case}")
    return payload


@pytest.mark.parametrize("environment", CANONICAL_ENVIRONMENTS)
def test_loads_each_canonical_environment_as_a_typed_value(
    minimal_source: dict[str, object], environment: str
) -> None:
    minimal_source["RAOS_ENVIRONMENT"] = environment

    config = load_runtime_config(minimal_source)

    assert isinstance(config, RuntimeConfig)
    assert isinstance(config.environment, RuntimeEnvironment)
    assert config.environment.value == environment
    assert config.schema_version == 1


def test_optional_values_have_closed_deterministic_defaults(
    minimal_source: dict[str, object],
) -> None:
    config = load_runtime_config(minimal_source)

    assert config.service_name == "catalog-worker"
    assert config.log_level is LogLevel.INFO
    assert isinstance(config.secret_references, Mapping)
    assert dict(config.secret_references) == {}


@pytest.mark.parametrize(
    "level",
    ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
)
def test_loads_each_supported_log_level_without_coercing_case(
    minimal_source: dict[str, object], level: str
) -> None:
    minimal_source["RAOS_LOG_LEVEL"] = level

    config = load_runtime_config(minimal_source)

    assert isinstance(config.log_level, LogLevel)
    assert config.log_level.value == level


def test_loads_provider_neutral_references_and_caller_required_aliases(
    minimal_source: dict[str, object],
) -> None:
    minimal_source["RAOS_SECRET_REFERENCES"] = json.dumps(
        {
            "database_primary": logical_reference("local/database-primary"),
            "object_storage": logical_reference("local/object-storage"),
        }
    )

    config = load_runtime_config(
        minimal_source,
        required_secret_aliases=("database_primary", "object_storage"),
    )

    assert set(config.secret_references) == {"database_primary", "object_storage"}
    assert all(
        isinstance(reference, SecretReference)
        for reference in config.secret_references.values()
    )


def test_explicit_mapping_does_not_consult_the_process_environment(
    minimal_source: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RAOS_UNRECOGNIZED_AMBIENT_SETTING", "must-be-ignored")
    monkeypatch.setenv("RAOS_ENVIRONMENT", "ENV-PRODUCTION")
    monkeypatch.setenv("RAOS_SERVICE_NAME", "ambient-service")

    config = load_runtime_config(minimal_source)

    assert config.environment is RuntimeEnvironment("ENV-DEV")
    assert config.service_name == "catalog-worker"


def test_process_environment_is_read_only_by_the_explicit_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in tuple(__import__("os").environ):
        if name.startswith("RAOS_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RAOS_ENVIRONMENT", "ENV-CI")
    monkeypatch.setenv("RAOS_SERVICE_NAME", "ci-worker")
    monkeypatch.setenv("RAOS_LOG_LEVEL", "WARNING")

    config = load_runtime_config_from_environment()

    assert config.environment is RuntimeEnvironment("ENV-CI")
    assert config.service_name == "ci-worker"
    assert config.log_level is LogLevel.WARNING


def test_runtime_model_and_nested_reference_map_are_immutable(
    minimal_source: dict[str, object],
) -> None:
    minimal_source["RAOS_SECRET_REFERENCES"] = json.dumps(
        {"database_primary": logical_reference("local/database-primary")}
    )
    config = load_runtime_config(minimal_source)

    with pytest.raises((TypeError, ValidationError)):
        config.service_name = "changed"  # type: ignore[misc]

    mutable_view = cast(Any, config.secret_references)
    with pytest.raises(TypeError):
        mutable_view["other"] = next(iter(config.secret_references.values()))

    reference = next(iter(config.secret_references.values()))
    with pytest.raises(AttributeError):
        reference.logical_reference = logical_reference(  # type: ignore[attr-defined]
            "local/changed"
        )


def test_direct_runtime_model_validation_is_strict_and_forbids_extra_fields() -> None:
    valid = _typed_runtime_payload()
    config = RuntimeConfig.model_validate(valid)
    assert config.environment is RuntimeEnvironment("ENV-DEV")

    with pytest.raises(ValidationError):
        RuntimeConfig.model_validate({**valid, "unexpected": "value"})
    with pytest.raises(ValidationError):
        RuntimeConfig.model_validate({**valid, "schema_version": True})
    with pytest.raises(ValidationError):
        RuntimeConfig.model_validate({**valid, "environment": "ENV-DEV"})


@pytest.mark.parametrize(
    "case",
    (
        "schema_version_bool",
        "environment_string",
        "log_level_string",
        "reference_bytes",
    ),
)
def test_model_validate_strict_false_cannot_enable_coercion(case: str) -> None:
    with pytest.raises((TypeError, ValidationError)):
        RuntimeConfig.model_validate(_coercible_runtime_payload(case), strict=False)


@pytest.mark.parametrize("extra_policy", ("ignore", "allow"))
def test_model_validate_caller_cannot_weaken_extra_forbid(
    extra_policy: str, reference_canary: str
) -> None:
    payload = {
        **_typed_runtime_payload(),
        "audit_unknown_field": reference_canary,
    }

    with pytest.raises(TypeError) as captured:
        RuntimeConfig.model_validate(payload, extra=extra_policy)  # type: ignore[arg-type]

    assert reference_canary not in f"{captured.value!s} {captured.value!r}"


def test_model_validate_strings_is_an_explicitly_closed_coercion_path(
    reference_canary: str,
) -> None:
    payload = {
        "schema_version": "1",
        "environment": "ENV-DEV",
        "service_name": "catalog-worker",
        "log_level": "INFO",
        "secret_references": {
            "database_primary": logical_reference(f"fixture/{reference_canary}")
        },
    }

    with pytest.raises(TypeError) as captured:
        RuntimeConfig.model_validate_strings(payload)

    rendered = f"{captured.value!s} {captured.value!r}"
    assert reference_canary not in rendered
    assert logical_reference(f"fixture/{reference_canary}") not in rendered


def test_model_construct_is_an_explicitly_closed_unvalidated_path(
    reference_canary: str,
) -> None:
    with pytest.raises(TypeError) as captured:
        RuntimeConfig.model_construct(
            schema_version=True,
            environment="ENV-DEV",
            service_name=1,
            log_level="INFO",
            secret_references={
                "database_primary": logical_reference(f"fixture/{reference_canary}")
            },
            audit_unknown_field=reference_canary,
        )

    rendered = f"{captured.value!s} {captured.value!r}"
    assert reference_canary not in rendered
    assert logical_reference(f"fixture/{reference_canary}") not in rendered


@pytest.mark.parametrize(
    "case",
    (
        "schema_version_bool",
        "environment_string",
        "log_level_string",
        "reference_bytes",
    ),
)
def test_type_adapter_strict_false_cannot_enable_coercion(case: str) -> None:
    adapter = TypeAdapter(RuntimeConfig)

    with pytest.raises(ValidationError):
        adapter.validate_python(_coercible_runtime_payload(case), strict=False)
