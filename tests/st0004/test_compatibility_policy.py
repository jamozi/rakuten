"""Goal-backward compatibility proofs for the cumulative v0.4 contracts."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PREDECESSOR_BUNDLE = REPOSITORY_ROOT / "changes" / "st-0003"
CANDIDATE_BUNDLE = REPOSITORY_ROOT / "changes" / "st-0004"
PREDECESSOR_ROOT = PREDECESSOR_BUNDLE / "contracts"
CANDIDATE_ROOT = CANDIDATE_BUNDLE / "contracts"
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
    assert isinstance(value, dict), path
    return value


def normalized_schema_types(value: Any, *, location: str) -> set[str]:
    if isinstance(value, str):
        normalized = {value}
    else:
        assert isinstance(value, list) and value, f"invalid type at {location}"
        assert all(isinstance(item, str) for item in value)
        normalized = set(value)
        assert len(normalized) == len(value), f"duplicate type at {location}"
    assert normalized <= JSON_SCHEMA_TYPES, f"unknown type at {location}"
    return normalized


def assert_schema_nonbreaking(predecessor: Any, candidate: Any, *, location: str) -> None:
    """Conservatively prove that an existing JSON Schema was not narrowed."""

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
                assert candidate[key] == predecessor[key], f"{key} changed at {location}"

        if "type" in predecessor:
            assert "type" in candidate, f"type removed at {location}"
            old_types = normalized_schema_types(
                predecessor["type"], location=f"{location}.type"
            )
            new_types = normalized_schema_types(candidate["type"], location=f"{location}.type")
            assert old_types <= new_types, f"type narrowed at {location}"
            assert new_types - old_types <= {"null"}, f"type over-widened at {location}"

        if "enum" in predecessor:
            assert "enum" in candidate
            assert set(predecessor["enum"]) <= set(candidate["enum"]), (
                f"enum shrank at {location}"
            )
        for key in ("minimum", "exclusiveMinimum"):
            if key in predecessor:
                assert key in candidate and candidate[key] <= predecessor[key], (
                    f"{key} tightened at {location}"
                )
        for key in ("maximum", "exclusiveMaximum"):
            if key in predecessor:
                assert key in candidate and candidate[key] >= predecessor[key], (
                    f"{key} tightened at {location}"
                )

        old_properties = predecessor.get("properties")
        if isinstance(old_properties, dict):
            new_properties = candidate.get("properties")
            assert isinstance(new_properties, dict)
            assert set(old_properties) <= set(new_properties), f"properties removed at {location}"
            for name, old_schema in old_properties.items():
                assert_schema_nonbreaking(
                    old_schema,
                    new_properties[name],
                    location=f"{location}.properties.{name}",
                )

        for key in ("items", "not"):
            if key in predecessor:
                assert key in candidate
                assert_schema_nonbreaking(
                    predecessor[key], candidate[key], location=f"{location}.{key}"
                )
        for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
            if key in predecessor:
                assert key in candidate and len(candidate[key]) == len(predecessor[key])
                for index, old_schema in enumerate(predecessor[key]):
                    assert_schema_nonbreaking(
                        old_schema,
                        candidate[key][index],
                        location=f"{location}.{key}[{index}]",
                    )
    elif isinstance(predecessor, list):
        assert candidate == predecessor, f"list changed at {location}"
    else:
        assert candidate == predecessor, f"value changed at {location}"


def assert_openapi_compatible(
    predecessor: dict[str, Any], candidate: dict[str, Any], *, surface: str
) -> None:
    for path, old_path_item in predecessor["paths"].items():
        assert path in candidate["paths"], f"{surface} path removed: {path}"
        for method, old_operation in old_path_item.items():
            assert method in candidate["paths"][path], f"{surface} method removed: {method} {path}"
            assert candidate["paths"][path][method] == old_operation, (
                f"existing {surface} operation changed: {method} {path}"
            )
    old_components = predecessor.get("components", {})
    new_components = candidate.get("components", {})
    for section in ("parameters", "responses", "headers"):
        for name, value in old_components.get(section, {}).items():
            assert new_components[section][name] == value, (
                f"existing {surface} component changed: {section}/{name}"
            )
    for name, old_scheme in old_components.get("securitySchemes", {}).items():
        new_scheme = new_components["securitySchemes"][name]
        if old_scheme.get("type") != "oauth2":
            assert new_scheme == old_scheme, (
                f"existing {surface} component changed: securitySchemes/{name}"
            )
            continue
        old_without_scopes = deepcopy(old_scheme)
        new_without_scopes = deepcopy(new_scheme)
        old_scopes = old_without_scopes["flows"]["authorizationCode"].pop("scopes")
        new_scopes = new_without_scopes["flows"]["authorizationCode"].pop("scopes")
        assert new_without_scopes == old_without_scopes, (
            f"existing {surface} OAuth scheme changed: {name}"
        )
        for scope, description in old_scopes.items():
            assert scope in new_scopes, f"OAuth scope removed: {scope}"
            assert new_scopes[scope] == description, f"OAuth scope changed: {scope}"
    for name, old_schema in old_components.get("schemas", {}).items():
        assert name in new_components["schemas"], f"{surface} schema removed: {name}"
        assert_schema_nonbreaking(
            old_schema,
            new_components["schemas"][name],
            location=f"{surface}.components.schemas.{name}",
        )


def async_surface(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "servers": document.get("servers"),
        "defaultContentType": document.get("defaultContentType"),
        "channels": document.get("channels"),
        "operations": document.get("operations"),
        "messages": document.get("components", {}).get("messages"),
    }


def test_existing_admin_and_internal_operations_and_schemas_are_nonbreaking() -> None:
    assert_openapi_compatible(
        load_yaml(PREDECESSOR_ROOT / "openapi-admin.v0.3.yaml"),
        load_yaml(CANDIDATE_ROOT / "openapi-admin.v0.4.yaml"),
        surface="Admin",
    )
    assert_openapi_compatible(
        load_yaml(PREDECESSOR_ROOT / "openapi-internal.v0.3.yaml"),
        load_yaml(CANDIDATE_ROOT / "openapi-internal.v0.4.yaml"),
        surface="Internal",
    )


def test_asyncapi_wire_surface_and_event_schema_bytes_are_exact() -> None:
    predecessor = load_yaml(PREDECESSOR_ROOT / "asyncapi.v0.3.yaml")
    candidate = load_yaml(CANDIDATE_ROOT / "asyncapi.v0.4.yaml")
    assert async_surface(candidate) == async_surface(predecessor)

    old_events = PREDECESSOR_ROOT / "schemas" / "events"
    new_events = CANDIDATE_ROOT / "schemas" / "events"
    old_files = {
        path.relative_to(old_events).as_posix(): path.read_bytes()
        for path in old_events.rglob("*.json")
    }
    new_files = {
        path.relative_to(new_events).as_posix(): path.read_bytes()
        for path in new_events.rglob("*.json")
    }
    assert new_files == old_files


def test_every_predecessor_json_schema_is_preserved_byte_for_byte() -> None:
    for old_path in PREDECESSOR_ROOT.joinpath("schemas").rglob("*.json"):
        relative = old_path.relative_to(PREDECESSOR_ROOT)
        new_path = CANDIDATE_ROOT / relative
        assert new_path.is_file(), f"predecessor schema removed: {relative}"
        assert new_path.read_bytes() == old_path.read_bytes(), (
            f"predecessor schema bytes changed: {relative}"
        )


def test_public_openapi_and_job_state_are_immutable_bytes() -> None:
    assert (CANDIDATE_ROOT / "openapi-public.v0.1.yaml").read_bytes() == (
        PREDECESSOR_ROOT / "openapi-public.v0.1.yaml"
    ).read_bytes()
    assert (CANDIDATE_BUNDLE / "job-state.v1.yaml").read_bytes() == (
        PREDECESSOR_BUNDLE / "job-state.v1.yaml"
    ).read_bytes()


def test_comparator_rejects_removed_operation_scope_and_schema_narrowing() -> None:
    predecessor = load_yaml(PREDECESSOR_ROOT / "openapi-admin.v0.3.yaml")

    removed = deepcopy(predecessor)
    path = next(iter(removed["paths"]))
    method = next(iter(removed["paths"][path]))
    del removed["paths"][path][method]
    with pytest.raises(AssertionError, match="method removed"):
        assert_openapi_compatible(predecessor, removed, surface="Admin")

    operation_path = next(
        path
        for path, item in predecessor["paths"].items()
        if any(isinstance(op, dict) and op.get("security") for op in item.values())
    )
    operation_method = next(
        method
        for method, op in predecessor["paths"][operation_path].items()
        if isinstance(op, dict) and op.get("security")
    )
    scope_changed = deepcopy(predecessor)
    security = scope_changed["paths"][operation_path][operation_method]["security"]
    scheme = next(iter(security[0]))
    security[0][scheme] = ["invented:scope"]
    with pytest.raises(AssertionError, match="operation changed"):
        assert_openapi_compatible(predecessor, scope_changed, surface="Admin")

    declaration_removed = deepcopy(predecessor)
    declared_scopes = declaration_removed["components"]["securitySchemes"]["oidcOAuth2"][
        "flows"
    ]["authorizationCode"]["scopes"]
    del declared_scopes[next(iter(declared_scopes))]
    with pytest.raises(AssertionError, match="OAuth scope removed"):
        assert_openapi_compatible(predecessor, declaration_removed, surface="Admin")

    schema_name, schema = next(
        (name, value)
        for name, value in predecessor["components"]["schemas"].items()
        if isinstance(value, dict) and isinstance(value.get("properties"), dict)
    )
    narrowed = deepcopy(predecessor)
    narrowed["components"]["schemas"][schema_name]["required"] = [
        next(iter(schema["properties"]))
    ]
    with pytest.raises(AssertionError, match="new required constraint|required changed"):
        assert_openapi_compatible(predecessor, narrowed, surface="Admin")


def test_schema_comparator_rejects_enum_shrink_and_new_pattern() -> None:
    with pytest.raises(AssertionError, match="enum shrank"):
        assert_schema_nonbreaking(
            {"type": "string", "enum": ["A", "B"]},
            {"type": "string", "enum": ["A"]},
            location="fixture.enum",
        )
    with pytest.raises(AssertionError, match="new pattern constraint"):
        assert_schema_nonbreaking(
            {"type": "string"},
            {"type": "string", "pattern": "^narrow$"},
            location="fixture.pattern",
        )
