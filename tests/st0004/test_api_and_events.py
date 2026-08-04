"""HTTP operation, authority, concurrency and no-event-delta contracts."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_ROOT = REPOSITORY_ROOT / "changes" / "st-0004"
CONTRACTS_ROOT = BUNDLE_ROOT / "contracts"
PREDECESSOR_ROOT = REPOSITORY_ROOT / "changes" / "st-0003"
EXPECTED_ADMIN_IDS = {f"ED-{number:03d}" for number in range(16, 31)}
EXPECTED_INTERNAL_IDS = {f"INT-{number:03d}" for number in range(5, 9)}
EXPECTED_ADMIN_SCOPES = {
    "content:config:read",
    "content:config:write",
    "content:article:read",
    "content:article:write",
    "content:review:approve",
    "media:read",
    "media:write",
    "evidence:experience:read",
    "evidence:experience:write",
}


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def operation_map(document: dict[str, Any]) -> dict[str, tuple[str, str, dict[str, Any]]]:
    result: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            operation_id = operation["operationId"]
            assert operation_id not in result, f"duplicate operationId {operation_id}"
            result[operation_id] = (path, method.lower(), operation)
    return result


def referenced_parameter_names(operation: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for parameter in operation.get("parameters", []):
        if isinstance(parameter, dict) and isinstance(parameter.get("name"), str):
            names.add(parameter["name"])
        elif isinstance(parameter, dict) and isinstance(parameter.get("$ref"), str):
            names.add(parameter["$ref"].rsplit("/", 1)[-1])
    return names


def event_surface(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "channels": document.get("channels"),
        "operations": document.get("operations"),
        "messages": document.get("components", {}).get("messages"),
    }


def test_exact_nineteen_content_operations_are_additive_and_uniquely_identified() -> None:
    admin_document = load_yaml(CONTRACTS_ROOT / "openapi-admin.v0.4.yaml")
    internal_document = load_yaml(CONTRACTS_ROOT / "openapi-internal.v0.4.yaml")
    admin = operation_map(admin_document)
    internal = operation_map(internal_document)
    previous_admin = operation_map(
        load_yaml(PREDECESSOR_ROOT / "contracts" / "openapi-admin.v0.3.yaml")
    )
    previous_internal = operation_map(
        load_yaml(PREDECESSOR_ROOT / "contracts" / "openapi-internal.v0.3.yaml")
    )
    assert set(admin) - set(previous_admin) == EXPECTED_ADMIN_IDS
    assert set(internal) - set(previous_internal) == EXPECTED_INTERNAL_IDS
    assert not (set(admin) & set(internal))
    assert len(EXPECTED_ADMIN_IDS | EXPECTED_INTERNAL_IDS) == 19
    for operation_id in EXPECTED_ADMIN_IDS | EXPECTED_INTERNAL_IDS:
        operation = (admin | internal)[operation_id][2]
        assert operation["x-raos-operation-id"] == operation_id
        assert operation["x-raos-implementation-slice"] == "ST-0004"
        assert operation["x-raos-requirements"] == ["FR-007", "FR-010"]
    for document in (admin_document, internal_document):
        for path, path_item in document["paths"].items():
            path_parameters = referenced_parameter_names(path_item)
            variables = set(re.findall(r"{([^{}]+)}", path))
            for operation in path_item.values():
                if not isinstance(operation, dict) or "operationId" not in operation:
                    continue
                declared = path_parameters | referenced_parameter_names(operation)
                assert variables <= declared, (
                    f"path parameters missing for {operation['operationId']}: "
                    f"{sorted(variables - declared)}"
                )


def test_all_nineteen_operations_have_exact_surface_authentication_boundaries() -> None:
    admin_document = load_yaml(CONTRACTS_ROOT / "openapi-admin.v0.4.yaml")
    admin = operation_map(admin_document)
    internal = operation_map(load_yaml(CONTRACTS_ROOT / "openapi-internal.v0.4.yaml"))
    used_admin_scopes: set[str] = set()
    for operation_id in EXPECTED_ADMIN_IDS:
        operation = admin[operation_id][2]
        assert len(operation["security"]) == 1
        scopes = operation["security"][0]["oidcOAuth2"]
        assert scopes and all(scope.startswith(("content:", "media:", "evidence:")) for scope in scopes)
        used_admin_scopes.update(scopes)
        assert operation["x-raos-authorization-context"] == "CONTENT"
        assert operation["x-raos-classification"] == "CONFIDENTIAL"
    declared_admin_scopes = set(
        admin_document["components"]["securitySchemes"]["oidcOAuth2"]["flows"]
        ["authorizationCode"]["scopes"]
    )
    assert used_admin_scopes == EXPECTED_ADMIN_SCOPES
    assert used_admin_scopes <= declared_admin_scopes
    all_used_admin_scopes = {
        scope
        for path_item in admin_document["paths"].values()
        if isinstance(path_item, dict)
        for operation in path_item.values()
        if isinstance(operation, dict)
        for requirement in operation.get("security", [])
        if isinstance(requirement, dict)
        for scope in requirement.get("oidcOAuth2", [])
    }
    assert all_used_admin_scopes <= declared_admin_scopes
    for operation_id in EXPECTED_INTERNAL_IDS:
        operation = internal[operation_id][2]
        assert operation["security"] == [{"serviceBearer": []}]
        assert operation["x-raos-authorization-context"] == "SERVICE"
        assert operation["x-raos-classification"] == "CONFIDENTIAL"


def test_commands_have_idempotency_or_concurrency_preconditions_and_exact_metadata() -> None:
    documents = (
        operation_map(load_yaml(CONTRACTS_ROOT / "openapi-admin.v0.4.yaml")),
        operation_map(load_yaml(CONTRACTS_ROOT / "openapi-internal.v0.4.yaml")),
    )
    operations = {
        key: value
        for document in documents
        for key, value in document.items()
        if key in EXPECTED_ADMIN_IDS | EXPECTED_INTERNAL_IDS
    }
    for operation_id, (_path, method, operation) in operations.items():
        parameters = referenced_parameter_names(operation)
        has_idempotency = "IdempotencyKey" in parameters or "Idempotency-Key" in parameters
        has_if_match = "IfMatch" in parameters or "If-Match" in parameters
        assert operation["x-raos-idempotency-required"] is has_idempotency
        assert operation["x-raos-concurrency-required"] is has_if_match
        assert operation["x-raos-success-etag-required"] is has_if_match
        if method == "post":
            assert has_idempotency, f"POST command lacks Idempotency-Key: {operation_id}"
        if method in {"put", "patch", "delete"}:
            assert has_if_match, f"existing-resource mutation lacks If-Match: {operation_id}"
            assert "412" in operation["responses"]
        if operation["x-raos-kind"] == "command":
            assert has_idempotency, f"command lacks Idempotency-Key: {operation_id}"
            assert operation["requestBody"]["required"] is True
            assert operation["x-raos-audit-action"]


def test_human_only_operations_are_step_up_separated_and_ai_service_forbidden() -> None:
    admin = operation_map(load_yaml(CONTRACTS_ROOT / "openapi-admin.v0.4.yaml"))
    human_only = {
        operation_id: value[2]
        for operation_id, value in admin.items()
        if operation_id in EXPECTED_ADMIN_IDS
        and value[2].get("x-raos-human-approval-required") is True
    }
    assert set(human_only) == {"ED-027", "ED-028", "ED-030"}
    for operation in human_only.values():
        assert operation["x-raos-step-up-authentication-required"] is True
        assert operation["x-raos-ai-principal-forbidden"] is True
        assert operation["x-raos-service-principal-forbidden"] is True
        assert operation["x-raos-author-final-approver-separation"] is True


def test_public_surface_is_byte_frozen_and_has_no_content_finance_or_evidence_delta() -> None:
    candidate = CONTRACTS_ROOT / "openapi-public.v0.1.yaml"
    predecessor = PREDECESSOR_ROOT / "contracts" / "openapi-public.v0.1.yaml"
    assert candidate.read_bytes() == predecessor.read_bytes()
    assert sha256(candidate.read_bytes()).hexdigest() == (
        "8122958e80e04096ba3b254b4a8d843138bb757c8fc4e71bd8406914dba80797"
    )
    surface = json.dumps(load_yaml(candidate), ensure_ascii=False, sort_keys=True).lower()
    assert "/content/" not in surface
    assert "firsthandexperience" not in surface
    assert "commission" not in surface and "affiliate_rate" not in surface


def test_asyncapi_surface_has_exactly_zero_delta_and_no_invented_content_events() -> None:
    candidate = load_yaml(CONTRACTS_ROOT / "asyncapi.v0.4.yaml")
    predecessor = load_yaml(PREDECESSOR_ROOT / "contracts" / "asyncapi.v0.3.yaml")
    assert event_surface(candidate) == event_surface(predecessor)
    metadata = candidate["x-raos-content-revision"]
    assert metadata == {
        **{key: value for key, value in metadata.items() if key not in {
            "event_delta", "existing_channels_operations_messages_preserved", "invented_content_events"
        }},
        "event_delta": "NONE",
        "existing_channels_operations_messages_preserved": True,
        "invented_content_events": False,
    }
    manifest = load_yaml(BUNDLE_ROOT / "manifest.yaml")
    assert manifest["contract_delta"]["event_types_added"] == []
    assert manifest["compatibility"]["async_event_delta"] == "NONE"
    assert manifest["compatibility"]["async_event_surface_hash_preserved"] is True
