"""TST-031-aligned redaction and diagnostic minimization checks."""

from __future__ import annotations

import json
import logging
import pickle

from pydantic import BaseModel, TypeAdapter, ValidationError
import pytest

from conftest import logical_reference
import raos.config.runtime as runtime_module
from raos.config import (
    ConfigurationError,
    LogLevel,
    RuntimeConfig,
    RuntimeEnvironment,
    SecretReference,
    load_runtime_config,
    redacted_diagnostics,
)


def _render_model_surfaces(config: object) -> tuple[str, ...]:
    model = config
    return (
        str(model),
        repr(model),
        str(model.model_dump()),  # type: ignore[attr-defined]
        str(model.model_dump(mode="json")),  # type: ignore[attr-defined]
        model.model_dump_json(),  # type: ignore[attr-defined]
    )


def test_reference_identifier_is_absent_from_all_model_serialization_surfaces(
    minimal_source: dict[str, object], reference_canary: str
) -> None:
    reference = logical_reference(f"fixture/{reference_canary}")
    minimal_source["RAOS_SECRET_REFERENCES"] = json.dumps(
        {"database_primary": reference}
    )

    config = load_runtime_config(minimal_source)
    item = config.secret_references["database_primary"]
    surfaces = (*_render_model_surfaces(config), str(item), repr(item))

    assert all(reference not in surface for surface in surfaces)
    assert all(reference_canary not in surface for surface in surfaces)


def test_unvalidated_model_copy_update_cannot_reopen_reference_disclosure(
    minimal_source: dict[str, object], reference_canary: str
) -> None:
    config = load_runtime_config(minimal_source)
    reference = logical_reference(f"fixture/{reference_canary}")

    with pytest.raises(TypeError) as rejected:
        config.model_copy(update={"secret_references": {"database_primary": reference}})

    rendered_error = f"{rejected.value!s} {rejected.value!r}"
    assert reference not in rendered_error
    assert reference_canary not in rendered_error

    copied = BaseModel.model_copy(
        config,
        update={"secret_references": {"database_primary": reference}},
    )
    surfaces = (
        *_render_model_surfaces(copied),
        json.dumps(redacted_diagnostics(copied), sort_keys=True),
    )

    assert all(reference not in surface for surface in surfaces)
    assert all(reference_canary not in surface for surface in surfaces)


def test_forced_base_model_construct_bypass_remains_redacted(
    reference_canary: str,
) -> None:
    reference = logical_reference(f"fixture/{reference_canary}")
    field_names = {
        "schema_version",
        "environment",
        "service_name",
        "log_level",
        "secret_references",
    }
    constructed = BaseModel.model_construct.__func__(
        RuntimeConfig,
        _fields_set=field_names,
        schema_version=1,
        environment=RuntimeEnvironment("ENV-DEV"),
        service_name="catalog-worker",
        log_level=LogLevel("INFO"),
        secret_references={"database_primary": reference},
    )

    surfaces = (
        *_render_model_surfaces(constructed),
        json.dumps(redacted_diagnostics(constructed), sort_keys=True),
    )
    assert all(reference not in surface for surface in surfaces)
    assert all(reference_canary not in surface for surface in surfaces)


def test_opaque_reference_and_runtime_config_fail_closed_when_pickled(
    minimal_source: dict[str, object], reference_canary: str
) -> None:
    reference_value = logical_reference(f"fixture/{reference_canary}")
    minimal_source["RAOS_SECRET_REFERENCES"] = json.dumps(
        {"database_primary": reference_value}
    )
    config = load_runtime_config(minimal_source)
    reference = config.secret_references["database_primary"]

    for value, expected_message in (
        (reference, "SecretReference serialization is not supported"),
        (config, "RuntimeConfig serialization is not supported"),
    ):
        with pytest.raises(TypeError) as captured:
            pickle.dumps(value)

        rendered = f"{captured.value!s} {captured.value!r}"
        assert str(captured.value) == expected_message
        assert reference_canary not in rendered
        assert reference_value not in rendered


@pytest.mark.parametrize(
    ("base", "expected_message"),
    (
        (SecretReference, "SecretReference subclassing is not supported"),
        (RuntimeConfig, "RuntimeConfig subclassing is not supported"),
    ),
)
def test_security_boundary_types_cannot_be_subclassed(
    base: type[object],
    expected_message: str,
) -> None:
    with pytest.raises(TypeError) as captured:
        type("LeakyBoundaryType", (base,), {})

    assert str(captured.value) == expected_message


def test_supported_validation_revalidates_and_normalizes_existing_models(
    minimal_source: dict[str, object],
    reference_canary: str,
) -> None:
    config = load_runtime_config(minimal_source)
    logical_canary = logical_reference(f"fixture/{reference_canary}")
    forced = BaseModel.model_copy(
        config,
        update={"secret_references": {"database_primary": logical_canary}},
    )

    validated = RuntimeConfig.model_validate(forced)
    adapted = TypeAdapter(RuntimeConfig).validate_python(forced)

    assert validated is not forced
    assert adapted is not forced
    assert type(validated) is RuntimeConfig
    assert type(adapted) is RuntimeConfig
    assert type(validated.secret_references["database_primary"]) is SecretReference
    assert type(adapted.secret_references["database_primary"]) is SecretReference
    surfaces = (*_render_model_surfaces(validated), *_render_model_surfaces(adapted))
    assert all(logical_canary not in surface for surface in surfaces)
    assert all(reference_canary not in surface for surface in surfaces)


def test_redacted_diagnostics_have_an_exact_minimized_allowlist(
    minimal_source: dict[str, object], reference_canary: str
) -> None:
    minimal_source["RAOS_LOG_LEVEL"] = "ERROR"
    minimal_source["RAOS_SECRET_REFERENCES"] = json.dumps(
        {
            "zeta_reference": logical_reference(f"fixture/{reference_canary}"),
            "alpha_reference": logical_reference("fixture/ordinary"),
        }
    )
    config = load_runtime_config(minimal_source)

    diagnostics = redacted_diagnostics(config)

    assert diagnostics == {
        "schema_version": 1,
        "environment": "ENV-DEV",
        "service_name": "catalog-worker",
        "log_level": "ERROR",
        "secret_aliases": ["alpha_reference", "zeta_reference"],
        "secret_reference_count": 2,
    }
    encoded = json.dumps(diagnostics, sort_keys=True, separators=(",", ":"))
    assert reference_canary not in encoded
    assert logical_reference("") not in encoded


def test_redacted_diagnostics_are_repeatable_and_detached_from_model_state(
    minimal_source: dict[str, object],
) -> None:
    minimal_source["RAOS_SECRET_REFERENCES"] = json.dumps(
        {"database_primary": logical_reference("fixture/ordinary")}
    )
    config = load_runtime_config(minimal_source)

    first = redacted_diagnostics(config)
    second = redacted_diagnostics(config)

    assert first == second
    assert first is not second
    first["secret_aliases"] = []
    assert redacted_diagnostics(config)["secret_aliases"] == ["database_primary"]


def test_success_and_failure_paths_do_not_write_or_log_reference_input(
    minimal_source: dict[str, object],
    reference_canary: str,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    reference = logical_reference(f"fixture/{reference_canary}")
    minimal_source["RAOS_SECRET_REFERENCES"] = json.dumps(
        {"database_primary": reference}
    )
    with caplog.at_level(logging.DEBUG):
        load_runtime_config(minimal_source)

    invalid_source = dict(minimal_source)
    invalid_source["RAOS_SECRET_REFERENCES"] = json.dumps(
        {"database_primary": reference + "?forbidden=1"}
    )
    with caplog.at_level(logging.DEBUG), pytest.raises(ConfigurationError) as captured:
        load_runtime_config(invalid_source)

    streams = capsys.readouterr()
    rendered_records = "\n".join(record.getMessage() for record in caplog.records)
    rendered_error = f"{captured.value!s} {captured.value!r}"
    assert streams.out == ""
    assert streams.err == ""
    assert caplog.records == []
    assert reference_canary not in rendered_records
    assert reference_canary not in rendered_error
    assert reference not in rendered_error
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_parser_error_does_not_echo_malformed_json(
    minimal_source: dict[str, object], reference_canary: str
) -> None:
    minimal_source["RAOS_SECRET_REFERENCES"] = (
        '{"database_primary":"' + reference_canary
    )

    with pytest.raises(ConfigurationError) as captured:
        load_runtime_config(minimal_source)

    rendered = f"{captured.value!s} {captured.value!r}"
    assert reference_canary not in rendered
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_direct_model_and_reference_validation_errors_hide_the_rejected_input(
    reference_canary: str,
) -> None:
    invalid_reference = logical_reference(f"fixture/{reference_canary}?forbidden=1")
    with pytest.raises(ValueError) as reference_error:
        SecretReference(invalid_reference)

    with pytest.raises(ValidationError) as model_error:
        RuntimeConfig.model_validate(
            {
                "schema_version": 1,
                "environment": RuntimeEnvironment("ENV-DEV"),
                "service_name": "catalog-worker",
                "log_level": LogLevel("INFO"),
                "secret_references": {"database_primary": invalid_reference},
            }
        )

    rendered = " ".join(
        (
            str(reference_error.value),
            repr(reference_error.value),
            str(model_error.value),
            repr(model_error.value),
        )
    )
    assert reference_canary not in rendered
    assert invalid_reference not in rendered


@pytest.mark.parametrize(
    "entrypoint",
    ("model_validate", "constructor", "type_adapter_python", "type_adapter_json"),
)
def test_structured_validation_error_surfaces_never_retain_a_reference(
    entrypoint: str,
    reference_canary: str,
) -> None:
    invalid_reference = logical_reference(f"fixture/{reference_canary}?forbidden=1")
    python_payload: dict[str, object] = {
        "schema_version": 1,
        "environment": RuntimeEnvironment("ENV-DEV"),
        "service_name": "catalog-worker",
        "log_level": LogLevel("INFO"),
        "secret_references": {"database_primary": invalid_reference},
    }
    json_payload = json.dumps(
        {
            **python_payload,
            "environment": "ENV-DEV",
            "log_level": "INFO",
        }
    )

    with pytest.raises(ValidationError) as captured:
        if entrypoint == "model_validate":
            RuntimeConfig.model_validate(python_payload)
        elif entrypoint == "constructor":
            RuntimeConfig(**python_payload)  # type: ignore[arg-type]
        elif entrypoint == "type_adapter_python":
            TypeAdapter(RuntimeConfig).validate_python(python_payload)
        else:
            TypeAdapter(RuntimeConfig).validate_json(json_payload)

    surfaces = [
        str(captured.value),
        repr(captured.value),
        repr(captured.value.errors()),
        captured.value.json(),
    ]
    try:
        surfaces.append(repr(pickle.dumps(captured.value)))
    except (TypeError, ValueError) as serialization_error:
        surfaces.extend((str(serialization_error), repr(serialization_error)))

    assert all(invalid_reference not in surface for surface in surfaces)
    assert all(reference_canary not in surface for surface in surfaces)


def test_malformed_model_json_is_converted_to_a_sanitized_domain_error(
    reference_canary: str,
) -> None:
    invalid_json = '{"secret_references":"' + logical_reference(reference_canary)

    with pytest.raises(ConfigurationError) as captured:
        RuntimeConfig.model_validate_json(invalid_json)

    rendered = f"{captured.value!s} {captured.value!r}"
    assert reference_canary not in rendered
    assert logical_reference(reference_canary) not in rendered
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_public_model_json_rejects_duplicate_members_without_disclosure(
    reference_canary: str,
) -> None:
    first_reference = logical_reference(f"fixture/{reference_canary}-first")
    second_reference = logical_reference(f"fixture/{reference_canary}-second")
    prefix = (
        '{"schema_version":1,"environment":"ENV-DEV",'
        '"service_name":"catalog-worker","secret_references":'
    )
    duplicate_documents = (
        (
            '{"schema_version":1,"schema_version":1,'
            '"environment":"ENV-DEV","service_name":"catalog-worker",'
            '"secret_references":{}}'
        ),
        (
            prefix
            + '{"database_primary":"'
            + first_reference
            + '","database_primary":"'
            + second_reference
            + '"}}'
        ),
    )

    for document in duplicate_documents:
        for encoded in (document, document.encode(), bytearray(document.encode())):
            with pytest.raises(ConfigurationError) as captured:
                RuntimeConfig.model_validate_json(encoded)

            rendered = f"{captured.value!s} {captured.value!r}"
            assert reference_canary not in rendered
            assert first_reference not in rendered
            assert second_reference not in rendered
            assert captured.value.__cause__ is None
            assert captured.value.__context__ is None


def test_public_model_json_input_has_a_total_byte_bound(
    reference_canary: str,
) -> None:
    compact_json = json.dumps(
        {
            "schema_version": 1,
            "environment": "ENV-DEV",
            "service_name": "catalog-worker",
            "secret_references": {
                "database_primary": logical_reference(reference_canary)
            },
        },
        separators=(",", ":"),
    )
    exact_limit_json = compact_json + " " * (32768 - len(compact_json.encode()))
    assert len(exact_limit_json.encode()) == 32768

    for accepted in (
        exact_limit_json,
        exact_limit_json.encode(),
        bytearray(exact_limit_json.encode()),
    ):
        config = RuntimeConfig.model_validate_json(accepted)
        assert config.service_name == "catalog-worker"
        assert isinstance(config.secret_references["database_primary"], SecretReference)
        assert reference_canary not in config.model_dump_json()

    for oversized_json in (
        exact_limit_json + " ",
        (exact_limit_json + " ").encode(),
        bytearray((exact_limit_json + " ").encode()),
    ):
        with pytest.raises(ConfigurationError) as captured:
            RuntimeConfig.model_validate_json(oversized_json)

        rendered = f"{captured.value!s} {captured.value!r}"
        assert reference_canary not in rendered
        assert logical_reference(reference_canary) not in rendered
        assert captured.value.__cause__ is None
        assert captured.value.__context__ is None


def test_public_model_json_snapshots_mutable_bytearray_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = json.dumps(
        {
            "schema_version": 1,
            "environment": "ENV-DEV",
            "service_name": "catalog-worker",
            "secret_references": {},
        },
        separators=(",", ":"),
    )
    mutable_document = bytearray(document.encode())
    real_loads = runtime_module.json.loads

    def mutate_after_prescan(value: object, **kwargs: object) -> object:
        assert type(value) is bytes
        parsed = real_loads(value, **kwargs)
        mutable_document[:] = b'{"schema_version":1,"schema_version":2}'
        return parsed

    monkeypatch.setattr(runtime_module.json, "loads", mutate_after_prescan)

    config = RuntimeConfig.model_validate_json(mutable_document)

    assert config.schema_version == 1
    assert config.service_name == "catalog-worker"


def test_forced_base_model_scalar_and_alias_injection_remains_redacted(
    minimal_source: dict[str, object],
    reference_canary: str,
) -> None:
    config = load_runtime_config(minimal_source)
    logical_canary = logical_reference(reference_canary)
    copied = BaseModel.model_copy(
        config,
        update={
            "service_name": logical_canary,
            "secret_references": {logical_canary: logical_canary},
        },
    )
    constructed = BaseModel.model_construct.__func__(
        RuntimeConfig,
        _fields_set={
            "schema_version",
            "environment",
            "service_name",
            "log_level",
            "secret_references",
        },
        schema_version=logical_canary,
        environment=logical_canary,
        service_name=logical_canary,
        log_level=logical_canary,
        secret_references={logical_canary: logical_canary},
    )

    surfaces = (
        *_render_model_surfaces(copied),
        json.dumps(redacted_diagnostics(copied), sort_keys=True),
        *_render_model_surfaces(constructed),
        json.dumps(redacted_diagnostics(constructed), sort_keys=True),
    )
    assert all(logical_canary not in surface for surface in surfaces)
    assert all(reference_canary not in surface for surface in surfaces)


def test_hostile_string_subclasses_are_rejected_without_running_overrides(
    reference_canary: str,
) -> None:
    class HostileString(str):
        def _explode(self, *args: object, **kwargs: object) -> None:
            del args, kwargs
            raise RuntimeError(reference_canary)

        encode = _explode
        startswith = _explode
        removeprefix = _explode
        casefold = _explode
        __iter__ = _explode

    hostile_reference = HostileString(logical_reference("fixture/ordinary"))
    with pytest.raises(ValueError) as reference_error:
        SecretReference(hostile_reference)
    with pytest.raises(ConfigurationError) as loader_error:
        load_runtime_config(
            {
                "RAOS_ENVIRONMENT": HostileString("ENV-DEV"),
                "RAOS_SERVICE_NAME": "catalog-worker",
            }
        )
    with pytest.raises(ConfigurationError) as key_error:
        load_runtime_config(
            {
                HostileString("RAOS_ENVIRONMENT"): "ENV-DEV",
                "RAOS_SERVICE_NAME": "catalog-worker",
            }
        )
    with pytest.raises(ValidationError) as model_error:
        RuntimeConfig.model_validate(
            {
                "schema_version": 1,
                "environment": RuntimeEnvironment("ENV-DEV"),
                "service_name": "catalog-worker",
                "log_level": LogLevel("INFO"),
                "secret_references": {"database_primary": hostile_reference},
            }
        )

    surfaces = [
        str(reference_error.value),
        repr(reference_error.value),
        str(loader_error.value),
        repr(loader_error.value),
        str(key_error.value),
        repr(key_error.value),
        str(model_error.value),
        repr(model_error.value),
        repr(model_error.value.errors()),
        model_error.value.json(),
    ]
    assert all(reference_canary not in surface for surface in surfaces)


def test_missing_required_alias_error_does_not_echo_the_alias(
    minimal_source: dict[str, object],
) -> None:
    alias_canary = "marker_must_stay_private_91"

    with pytest.raises(ConfigurationError) as captured:
        load_runtime_config(
            minimal_source,
            required_secret_aliases=(alias_canary,),
        )

    assert alias_canary not in f"{captured.value!s} {captured.value!r}"
