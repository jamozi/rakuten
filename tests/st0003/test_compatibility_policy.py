"""Positive and mutation-based compatibility proofs for the cumulative v0.3."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
from typing import Any

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PREDECESSOR_ROOT = REPOSITORY_ROOT / "changes" / "st-0002" / "contracts"
CANDIDATE_ROOT = REPOSITORY_ROOT / "changes" / "st-0003" / "contracts"
NARROWING_SCHEMA_KEYWORDS = {
    "$ref",
    "additionalProperties",
    "allOf",
    "anyOf",
    "const",
    "contains",
    "dependentRequired",
    "dependentSchemas",
    "enum",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "format",
    "if",
    "items",
    "maxContains",
    "maxItems",
    "maxLength",
    "maxProperties",
    "maximum",
    "minContains",
    "minItems",
    "minLength",
    "minProperties",
    "minimum",
    "multipleOf",
    "not",
    "oneOf",
    "pattern",
    "patternProperties",
    "prefixItems",
    "propertyNames",
    "required",
    "then",
    "type",
    "unevaluatedItems",
    "unevaluatedProperties",
    "uniqueItems",
}
JSON_SCHEMA_TYPES = {
    "array",
    "boolean",
    "integer",
    "null",
    "number",
    "object",
    "string",
}


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def normalized_schema_types(value: Any, *, location: str) -> set[str]:
    if isinstance(value, str):
        normalized = {value}
    else:
        assert isinstance(value, list) and value, (
            f"invalid type declaration at {location}"
        )
        assert all(isinstance(item, str) for item in value), (
            f"non-string type declaration at {location}"
        )
        normalized = set(value)
        assert len(normalized) == len(value), (
            f"duplicate type declaration at {location}"
        )
    assert normalized <= JSON_SCHEMA_TYPES, (
        f"unknown type declaration at {location}: {sorted(normalized)}"
    )
    return normalized


def assert_schema_nonbreaking(
    predecessor: Any,
    candidate: Any,
    *,
    location: str,
) -> None:
    """Conservative recursive check: additions may widen, old constraints stay."""

    assert type(candidate) is type(predecessor), f"type changed at {location}"
    if isinstance(predecessor, dict):
        for key in NARROWING_SCHEMA_KEYWORDS - predecessor.keys():
            if key not in candidate:
                continue
            if key == "additionalProperties" and candidate[key] is True:
                continue
            raise AssertionError(f"new {key} constraint at {location}")

        for key in (
            "$ref",
            "format",
            "const",
            "additionalProperties",
            "required",
            "pattern",
            "minLength",
            "maxLength",
            "minItems",
            "maxItems",
            "uniqueItems",
        ):
            if key in predecessor:
                assert key in candidate, f"{key} removed at {location}"
                assert candidate[key] == predecessor[key], (
                    f"{key} changed at {location}"
                )

        if "type" in predecessor:
            assert "type" in candidate, f"type removed at {location}"
            predecessor_types = normalized_schema_types(
                predecessor["type"],
                location=f"{location}.type",
            )
            candidate_types = normalized_schema_types(
                candidate["type"],
                location=f"{location}.type",
            )
            assert predecessor_types <= candidate_types, (
                f"type narrowed at {location}"
            )
            assert candidate_types - predecessor_types <= {"null"}, (
                f"type widened beyond null at {location}"
            )

        if "enum" in predecessor:
            assert "enum" in candidate, f"enum removed at {location}"
            assert set(predecessor["enum"]) <= set(candidate["enum"]), (
                f"enum shrank at {location}"
            )

        for lower_bound in ("minimum", "exclusiveMinimum"):
            if lower_bound in predecessor:
                assert lower_bound in candidate
                assert candidate[lower_bound] <= predecessor[lower_bound], (
                    f"{lower_bound} tightened at {location}"
                )
        for upper_bound in ("maximum", "exclusiveMaximum"):
            if upper_bound in predecessor:
                assert upper_bound in candidate
                assert candidate[upper_bound] >= predecessor[upper_bound], (
                    f"{upper_bound} tightened at {location}"
                )

        old_properties = predecessor.get("properties")
        if isinstance(old_properties, dict):
            new_properties = candidate.get("properties")
            assert isinstance(new_properties, dict)
            assert set(old_properties) <= set(new_properties), (
                f"properties removed at {location}"
            )
            for name, schema in old_properties.items():
                assert_schema_nonbreaking(
                    schema,
                    new_properties[name],
                    location=f"{location}.properties.{name}",
                )

        for key in ("items", "not"):
            if key in predecessor:
                assert key in candidate
                assert_schema_nonbreaking(
                    predecessor[key],
                    candidate[key],
                    location=f"{location}.{key}",
                )
        for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
            if key not in predecessor:
                continue
            assert key in candidate
            assert len(candidate[key]) == len(predecessor[key]), (
                f"{key} shape changed at {location}"
            )
            for index, schema in enumerate(predecessor[key]):
                assert_schema_nonbreaking(
                    schema,
                    candidate[key][index],
                    location=f"{location}.{key}[{index}]",
                )
    elif isinstance(predecessor, list):
        assert candidate == predecessor, f"list changed at {location}"
    else:
        assert candidate == predecessor, f"value changed at {location}"


def assert_admin_compatible(
    predecessor: dict[str, Any],
    candidate: dict[str, Any],
) -> None:
    for path, old_path_item in predecessor["paths"].items():
        assert path in candidate["paths"], f"Admin operation path removed: {path}"
        new_path_item = candidate["paths"][path]
        for method, old_operation in old_path_item.items():
            assert method in new_path_item, f"Admin method removed: {method} {path}"
            assert new_path_item[method] == old_operation, (
                f"existing Admin operation changed: {method} {path}"
            )

    old_components = predecessor["components"]
    new_components = candidate["components"]
    for section in ("parameters", "responses", "headers", "securitySchemes"):
        for name, old_value in old_components.get(section, {}).items():
            assert new_components[section][name] == old_value, (
                f"existing Admin component changed: {section}/{name}"
            )

    for name, old_schema in old_components["schemas"].items():
        assert name in new_components["schemas"], f"schema removed: {name}"
        assert_schema_nonbreaking(
            old_schema,
            new_components["schemas"][name],
            location=f"components.schemas.{name}",
        )


def assert_asyncapi_compatible(
    predecessor: dict[str, Any],
    candidate: dict[str, Any],
) -> None:
    assert candidate["servers"] == predecessor["servers"]
    for key in ("defaultContentType",):
        if key in predecessor:
            assert candidate[key] == predecessor[key]

    for name, old_channel in predecessor["channels"].items():
        assert name in candidate["channels"], f"AsyncAPI channel removed: {name}"
        new_channel = candidate["channels"][name]
        for key, value in old_channel.items():
            if key == "messages":
                assert set(value) <= set(new_channel[key])
                for message_name, message in value.items():
                    assert new_channel[key][message_name] == message
            else:
                assert new_channel[key] == value, (
                    f"AsyncAPI channel semantic changed: {name}/{key}"
                )

    for name, old_operation in predecessor["operations"].items():
        assert name in candidate["operations"], f"AsyncAPI operation removed: {name}"
        new_operation = candidate["operations"][name]
        for key, value in old_operation.items():
            if key == "messages":
                old_refs = [message["$ref"] for message in value]
                new_refs = [message["$ref"] for message in new_operation[key]]
                assert set(old_refs) <= set(new_refs)
            else:
                assert new_operation[key] == value, (
                    f"AsyncAPI operation semantic changed: {name}/{key}"
                )

    for name, old_message in predecessor["components"]["messages"].items():
        assert candidate["components"]["messages"][name] == old_message


def assert_predecessor_schema_bytes(candidate_root: Path) -> None:
    for old_path in PREDECESSOR_ROOT.joinpath("schemas").rglob("*.json"):
        relative = old_path.relative_to(PREDECESSOR_ROOT)
        new_path = candidate_root / relative
        assert new_path.is_file(), f"event/schema removed: {relative}"
        assert new_path.read_bytes() == old_path.read_bytes(), (
            f"event/schema wire contract changed: {relative}"
        )


def test_full_admin_and_asyncapi_predecessor_surfaces_are_compatible() -> None:
    assert_admin_compatible(
        load_yaml(PREDECESSOR_ROOT / "openapi-admin.v0.2.yaml"),
        load_yaml(CANDIDATE_ROOT / "openapi-admin.v0.3.yaml"),
    )
    assert_asyncapi_compatible(
        load_yaml(PREDECESSOR_ROOT / "asyncapi.v0.2.yaml"),
        load_yaml(CANDIDATE_ROOT / "asyncapi.v0.3.yaml"),
    )
    assert_predecessor_schema_bytes(CANDIDATE_ROOT)


def test_admin_comparator_rejects_operation_scope_status_and_required_mutations() -> None:
    predecessor = load_yaml(PREDECESSOR_ROOT / "openapi-admin.v0.2.yaml")

    removed = deepcopy(predecessor)
    del removed["paths"]["/api/v1/admin/ai/jobs"]["get"]
    with pytest.raises(AssertionError, match="method removed"):
        assert_admin_compatible(predecessor, removed)

    scope_changed = deepcopy(predecessor)
    scope_changed["paths"]["/api/v1/admin/ai/jobs"]["get"]["security"][0][
        "oidcOAuth2"
    ] = ["ai:job:write"]
    with pytest.raises(AssertionError, match="operation changed"):
        assert_admin_compatible(predecessor, scope_changed)

    status_removed = deepcopy(predecessor)
    del status_removed["paths"]["/api/v1/admin/ai/jobs"]["post"]["responses"]["202"]
    with pytest.raises(AssertionError, match="operation changed"):
        assert_admin_compatible(predecessor, status_removed)

    required_changed = deepcopy(predecessor)
    required_changed["components"]["schemas"]["AIJob"]["required"].append("status")
    with pytest.raises(AssertionError, match="required changed"):
        assert_admin_compatible(predecessor, required_changed)


def test_schema_comparator_rejects_enum_shrink() -> None:
    predecessor = load_yaml(PREDECESSOR_ROOT / "openapi-admin.v0.2.yaml")
    candidate = deepcopy(predecessor)
    schema = candidate["components"]["schemas"]["ActionDecisionRequest"]["properties"][
        "decision"
    ]
    assert len(schema["enum"]) > 1
    schema["enum"] = schema["enum"][:-1]

    with pytest.raises(AssertionError, match="enum shrank"):
        assert_admin_compatible(predecessor, candidate)


def test_schema_comparator_allows_only_well_formed_nullable_type_widening() -> None:
    assert_schema_nonbreaking(
        {"type": "boolean"},
        {"type": ["boolean", "null"]},
        location="nullable_boolean",
    )

    invalid_candidates = (
        ({"type": "null"}, "type narrowed"),
        ({"type": ["boolean", "string"]}, "type widened beyond null"),
        ({"type": []}, "invalid type declaration"),
        ({"type": ["boolean", 1]}, "non-string type declaration"),
        ({"type": ["boolean", "boolean"]}, "duplicate type declaration"),
        ({"type": ["boolean", "invalid"]}, "unknown type declaration"),
        ({}, "type removed"),
    )
    for candidate, message in invalid_candidates:
        with pytest.raises(AssertionError, match=message):
            assert_schema_nonbreaking(
                {"type": "boolean"},
                candidate,
                location="invalid_type",
            )


def test_schema_comparator_rejects_new_constraint_on_existing_property() -> None:
    predecessor = load_yaml(PREDECESSOR_ROOT / "openapi-admin.v0.2.yaml")
    candidate = deepcopy(predecessor)
    status = candidate["components"]["schemas"]["AIJob"]["properties"]["status"]
    assert "enum" not in status
    status["enum"] = ["REQUESTED", "RUNNING", "SUCCEEDED"]

    with pytest.raises(AssertionError, match="new enum constraint"):
        assert_admin_compatible(predecessor, candidate)


def test_wire_comparator_rejects_event_required_and_type_mutations(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "contracts"
    shutil.copytree(CANDIDATE_ROOT, candidate)
    event_path = (
        candidate / "schemas" / "events" / "jp-raos-ai-job-requested-v1.schema.json"
    )

    event = json.loads(event_path.read_text(encoding="utf-8"))
    data = event["allOf"][1]["properties"]["data"]
    data["required"] = data["required"][:-1]
    event_path.write_text(json.dumps(event, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="wire contract changed"):
        assert_predecessor_schema_bytes(candidate)

    shutil.rmtree(candidate)
    shutil.copytree(CANDIDATE_ROOT, candidate)
    event_path = (
        candidate / "schemas" / "events" / "jp-raos-ai-job-requested-v1.schema.json"
    )
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event["allOf"][1]["properties"]["data"]["properties"]["task_code"][
        "type"
    ] = "integer"
    event_path.write_text(json.dumps(event, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="wire contract changed"):
        assert_predecessor_schema_bytes(candidate)
