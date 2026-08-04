"""Canonical, semantic, and JSON Schema bindings for ST-0204."""

from __future__ import annotations

import json
from typing import Any

import yaml
from jsonschema.validators import Draft202012Validator

from conftest import CANONICAL_ENVIRONMENTS, EXPECTED_TOOLCHAIN, logical_reference
from raos.config import LogLevel, RuntimeConfig
from scripts import build_st0204_config_loader as generator


def _record(document: dict[str, Any], collection: str, identity: str) -> dict[str, Any]:
    matches = [item for item in document[collection] if item["id"] == identity]
    assert len(matches) == 1
    return matches[0]


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def _objects(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def test_contract_matches_the_complete_reviewed_model(
    config_contract: dict[str, Any],
) -> None:
    assert config_contract == generator.EXPECTED_CONTRACT
    assert config_contract["document"]["formal_verification"] == "NOT_EXECUTED"
    assert config_contract["story"]["required_suites"] == ["TST-005", "TST-031"]
    assert config_contract["story"]["open_decisions"] == []
    assert config_contract["toolchain"] == EXPECTED_TOOLCHAIN
    assert config_contract["boundary"]["effective_canonical_status"] == "UNCHANGED"


def test_canonical_story_is_exactly_the_approved_config_loader_scope() -> None:
    path = (
        generator.REPO_ROOT
        / "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
    )
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    story = _record(document, "stories", "ST-0204")

    assert story["title"] == "Configuration and secret loader"
    assert story["objective"] == "環境別typed configとSecret reference"
    assert story["depends_on"] == ["ST-0102", "ST-0103"]
    assert story["design_refs"] == ["RAOS-SEC-001"]
    assert story["deliverables"] == ["config schema", "redacted diagnostics"]
    assert story["acceptance_criteria"] == [
        "secret not logged",
        "missing required fails",
    ]
    assert story["test_suites"] == ["TST-005", "TST-031"]
    assert story["open_decisions"] == []
    assert story["design_status"] == "APPROVED_FOR_IMPLEMENTATION"
    assert story["implementation_status"] == "NOT_STARTED"
    assert story["verification_status"] == "NOT_EXECUTED"


def test_required_suites_remain_release_blocking_and_formally_unexecuted() -> None:
    path = (
        generator.REPO_ROOT
        / "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
    )
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    unit = _record(document, "suites", "TST-005")
    privacy = _record(document, "suites", "TST-031")

    assert unit == {
        "id": "TST-005",
        "name": "Python unit",
        "layer": "unit",
        "purpose": "Domain value/object/policyの局所Test",
        "candidate_tools": ["pytest"],
        "release_blocking": True,
        "environments": ["CI"],
        "owner": "Engineering",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    }
    assert privacy == {
        "id": "TST-031",
        "name": "Privacy and retention",
        "layer": "privacy",
        "purpose": "PII scan、consent、deletion、access",
        "candidate_tools": ["schema scan", "manual"],
        "release_blocking": True,
        "environments": ["CI", "staging"],
        "owner": "Privacy/Security",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    }


def test_security_controls_and_future_provider_boundary_are_not_overclaimed(
    config_contract: dict[str, Any],
) -> None:
    assert [
        mapping["id"] for mapping in config_contract["security"]["control_mappings"]
    ] == ["SEC-APP-001", "SEC-APP-010", "SEC-DATA-003", "SEC-DATA-007", "SEC-SDLC-006"]
    boundary = config_contract["boundary"]
    assert boundary["production_secret_resolution"] == "NOT_IMPLEMENTED"
    assert boundary["secret_manager_adapter"] == "NOT_IMPLEMENTED"
    assert boundary["workload_identity"] == "NOT_IMPLEMENTED"
    assert boundary["rotation_hooks"] == "NOT_IMPLEMENTED"
    assert boundary["formal_tst_005"] == "NOT_EXECUTED"
    assert boundary["formal_tst_031"] == "NOT_EXECUTED"
    assert boundary["security_owner_review"] == "NOT_EXECUTED"


def test_supported_validation_boundary_excludes_low_level_pydantic_bypasses(
    config_contract: dict[str, Any],
) -> None:
    hygiene = config_contract["error_hygiene"]

    assert (
        config_contract["schema"]["pattern_end_semantics"]
        == "ABSOLUTE_END_ECMA_262_AND_PYTHON"
    )
    assert hygiene["model_json_maximum_input_bytes"] == 32768
    assert hygiene["model_json_duplicate_members"] == "REJECT_WITHOUT_ECHO"
    assert hygiene["model_json_mutable_bytearray"] == "IMMUTABLE_SNAPSHOT"
    assert hygiene["supported_pydantic_entrypoints"] == [
        "RUNTIME_CONFIG_CONSTRUCTOR",
        "MODEL_VALIDATE",
        "MODEL_VALIDATE_JSON",
    ]
    assert hygiene["low_level_type_adapter"] == "UNSUPPORTED_BYPASS"
    assert (
        hygiene["base_model_unvalidated_escape_hatches"]
        == "UNSUPPORTED_TRUSTED_CODE_BYPASS"
    )
    assert hygiene["security_boundary_subclassing"] == "FORBIDDEN"
    assert hygiene["existing_model_instances"] == "REVALIDATE_AND_NORMALIZE"
    assert hygiene["nested_secret_reference_instances"] == "EXACT_TYPE_ONLY"


def test_runtime_schema_is_byte_deterministic_and_json_safe() -> None:
    first = RuntimeConfig.model_json_schema()
    second = RuntimeConfig.model_json_schema()

    assert _canonical_json(first) == _canonical_json(second)
    assert json.loads(_canonical_json(first)) == first


def test_runtime_schema_is_closed_and_contains_exact_public_enums() -> None:
    schema = RuntimeConfig.model_json_schema()
    objects = tuple(_objects(schema))
    enum_sets = {
        tuple(item["enum"]) for item in objects if isinstance(item.get("enum"), list)
    }

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "schema_version",
        "environment",
        "service_name",
        "secret_references",
    }
    assert tuple(CANONICAL_ENVIRONMENTS) in enum_sets
    assert tuple(level.value for level in LogLevel) in enum_sets
    assert any(item.get("const") == 1 for item in objects)


def test_runtime_schema_carries_bounded_string_and_map_constraints() -> None:
    schema: dict[str, Any] = RuntimeConfig.model_json_schema()
    objects = tuple(_objects(schema))

    assert any(item.get("maxLength") == 63 for item in objects)
    assert any(item.get("maxLength") == 64 for item in objects)
    assert any(item.get("maxLength") == 512 for item in objects)
    assert any(item.get("maxProperties") == 64 for item in objects)
    assert any(
        isinstance(item.get("pattern"), str) and "secret" in item["pattern"].casefold()
        for item in objects
    )


def test_runtime_schema_rejects_trailing_line_feed_in_all_patterned_names() -> None:
    schema: dict[str, Any] = RuntimeConfig.model_json_schema()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    reference = logical_reference("local/reference")
    valid = {
        "schema_version": 1,
        "environment": "ENV-DEV",
        "service_name": "catalog-worker",
        "secret_references": {"database_primary": reference},
    }
    invalid = (
        {**valid, "service_name": "catalog-worker\n"},
        {
            **valid,
            "secret_references": {"database_primary\n": reference},
        },
        {
            **valid,
            "secret_references": {"database_primary": f"{reference}\n"},
        },
    )

    assert validator.is_valid(valid)
    assert all(not validator.is_valid(document) for document in invalid)

    properties = schema["properties"]
    patterns = (
        properties["service_name"]["pattern"],
        properties["secret_references"]["propertyNames"]["pattern"],
        properties["secret_references"]["additionalProperties"]["pattern"],
    )
    assert all(pattern.endswith(r"$(?![\s\S])") for pattern in patterns)


def test_schema_defaults_never_contain_a_logical_reference() -> None:
    defaults = [
        item["default"]
        for item in _objects(RuntimeConfig.model_json_schema())
        if "default" in item
    ]
    rendered = _canonical_json(defaults).decode()

    assert logical_reference("") not in rendered
