#!/usr/bin/env python3
"""Build and check the evidence-bound ST-0403 authorization registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import NoReturn, NotRequired, TypedDict, cast

import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import secure_generated_publication  # noqa: E402


CONTRACT = ROOT / "changes/st-0403/contracts/authorization-registry.v1.json"
DURABLE_CONTRACT = (
    ROOT / "changes/st-0403/contracts/durable-authorization-runtime.v2.json"
)
GENERATED_JSON = ROOT / "changes/st-0403/generated/authorization-registry.v1.json"
GENERATED_PYTHON = (
    ROOT / "python/raos/adapters/generated_st0403_authorization_registry.py"
)
MANIFEST = ROOT / "changes/st-0403/manifest.json"
_MAX_SOURCE_BYTES = 8 * 1024 * 1024
_MAX_GENERATED_BYTES = 2 * 1024 * 1024
_EXPECTED_CONTRACT_SHA256 = (
    "a2ef5f7df66492164128ba8ffffcceb254b58bedc5cac7d03716d20700bc1093"
)
_EXPECTED_DURABLE_CONTRACT_SHA256 = (
    "478626abf1649682c173ecb45dd6abdf56932bd013cbee88f7c2d4753dab27f0"
)
_EXPECTED_SECURE_HELPER_SHA256 = (
    "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e"
)
_EXPECTED_SOURCE_BINDINGS: dict[str, tuple[str, str]] = {
    "role_matrix": (
        "docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml",
        "dfd67960ca8a004bbe6f3249ca9fa64ab1b24e94a57a2e88fc282267adc8b984",
    ),
    "security_design": (
        "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md",
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b",
    ),
    "admin_openapi": (
        "contracts/raos-v0.4/contracts/openapi-admin.v0.4.yaml",
        "6a22ee7a5f13ed89ac3bb6ceeffe49aad8b11e4f2a3a137c927542461c2ace70",
    ),
    "internal_openapi": (
        "contracts/raos-v0.4/contracts/openapi-internal.v0.4.yaml",
        "616ea270aec830a987679853869c0d22e1114a95bcf0279d6e635a5f359a6f21",
    ),
    "state_catalog": (
        "contracts/raos-v0.4/contracts/catalogs/state-transition-catalog.v0.4.yaml",
        "203eb10d9b6fc6ba4fb0e9f0491f713c313a6a5627dcaf60b7ce53665ecec8a5",
    ),
    "authentication_contract": (
        "changes/st-0401/contracts/local-auth-runtime.v2.json",
        "6f91b6619b318e954a7f5b1ef996918755ed8cbd412f4cda7050bb17ab0cdaad",
    ),
    "step_up_contract": (
        "changes/st-0402/contracts/local-step-up-runtime.v2.json",
        "62c057afde754c2aa74226cc3ae6e896e0cfaa5aaf54bdc0b21a54301a462b8e",
    ),
    "database_role_contract": (
        "changes/st-0306/contracts/database-roles-grants.v1.yaml",
        "b35770ca163ce53b8df31b62b1a0f92322997bc699bb7a251e15b036af4408f3",
    ),
    "final_approval_reference": (
        "changes/st-0902/contracts/final-approval-reference-plan.v1.yaml",
        "450ed0f299bcd1f1f99a242d8a6661a9ab2a886ce8f67818def79618c2163567",
    ),
}
_IMPLEMENTATION_PATHS = (
    ROOT / "changes/st-0403/README.md",
    ROOT / "scripts/build_st0403_authorization_runtime.py",
    ROOT / "scripts/secure_generated_publication.py",
    ROOT / "python/raos/domain/iam/authorization.py",
    ROOT / "python/raos/ports/authorization.py",
    ROOT / "python/raos/application/iam/authorization.py",
    ROOT / "python/raos/adapters/recorded_authorization.py",
    ROOT / "python/raos/adapters/disabled_admin_authorization_http.py",
    ROOT / "python/raos/adapters/disabled_service_authorization.py",
    ROOT / "tests/st0403/conftest.py",
    ROOT / "tests/st0403/test_authorization.py",
    ROOT / "tests/st0403/test_boundaries.py",
    ROOT / "tests/st0403/test_durable_authorization.py",
    ROOT / "tests/st0403/test_authorization_http_and_enforcement.py",
    ROOT / "tests/st0403/test_generation.py",
)


class RegistrySources(TypedDict):
    role_matrix: str
    security_design: str
    admin_openapi: str
    internal_openapi: str
    state_catalog: str
    authentication_contract: str
    step_up_contract: str
    database_role_contract: str
    final_approval_reference: str


class MatrixRow(TypedDict):
    action: str
    data_class: str
    allowed_roles: list[str]
    mfa_required: bool
    step_up_required: bool
    separation_of_duties: bool
    blocked_reason: NotRequired[str]
    required_evidence: NotRequired[list[str]]


class BindingRow(TypedDict):
    operation_id: str
    action: str
    permission_scope: str
    resource_kind: str
    allowed_states: list[str]
    status: str
    block_reason: NotRequired[str]
    required_evidence: NotRequired[list[str]]
    step_up_action: NotRequired[str]
    step_up_resource_type: NotRequired[str]


class ServicePrincipalBoundary(TypedDict):
    status: str
    database_workload_roles: list[str]
    required_evidence: str


class ValueTrustBoundary(TypedDict):
    status: str
    constructor_scope: str
    external_input_construction: str
    unforgeable_capability: bool
    runtime_enforcement_entrypoints: list[str]
    business_action_execution: bool


class RegistryContract(TypedDict):
    schema_version: int
    story_id: str
    sources: RegistrySources
    matrix: list[MatrixRow]
    bindings: list[BindingRow]
    service_principal: ServicePrincipalBoundary
    value_trust_boundary: ValueTrustBoundary


def _stop(message: str) -> NoReturn:
    raise SystemExit(f"ST0403_REGISTRY_BUILD_FAILED: {message}")


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def _bytes(path: Path) -> bytes:
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > _MAX_SOURCE_BYTES
        ):
            _stop(f"invalid regular input: {path.relative_to(ROOT)}")
        value = path.read_bytes()
        after = path.lstat()
        if (
            _file_identity(before) != _file_identity(after)
            or len(value) != before.st_size
        ):
            _stop(f"changed input: {path.relative_to(ROOT)}")
        return value
    except OSError as error:
        _stop(f"unreadable input: {path.relative_to(ROOT)}: {error.__class__.__name__}")


def _sha(path: Path) -> str:
    return hashlib.sha256(_bytes(path)).hexdigest()


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in values:
        if key in result:
            _stop("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    del value
    _stop("non-finite JSON value")


def _json(path: Path) -> dict[str, object]:
    try:
        value: object = json.loads(
            _bytes(path),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        _stop(f"invalid JSON: {path.relative_to(ROOT)}: {error.__class__.__name__}")
    return _mapping(value, f"JSON root {path.relative_to(ROOT)}")


def _yaml(path: Path) -> dict[str, object]:
    try:
        value: object = yaml.safe_load(_bytes(path))
    except (UnicodeError, yaml.YAMLError) as error:
        _stop(f"invalid YAML: {path.relative_to(ROOT)}: {error.__class__.__name__}")
    return _mapping(value, f"YAML root {path.relative_to(ROOT)}")


def _mapping(value: object, label: str) -> dict[str, object]:
    if type(value) is not dict:
        _stop(f"{label} is not a string-keyed object")
    mapped = cast(dict[object, object], value)
    if any(type(key) is not str for key in mapped):
        _stop(f"{label} is not a string-keyed object")
    return cast(dict[str, object], mapped)


def _require_keys(value: object, expected: set[str], label: str) -> dict[str, object]:
    mapped = _mapping(value, label)
    if set(mapped) != expected:
        _stop(f"{label} has unexpected keys")
    return mapped


def _list(value: object, label: str) -> list[object]:
    if type(value) is not list:
        _stop(f"{label} is not a list")
    return cast(list[object], value)


def _string(value: object, label: str = "string") -> str:
    if type(value) is not str or not value or value != value.strip():
        _stop(f"{label} is invalid")
    return value


def _string_values(value: object, label: str) -> list[str]:
    values = _list(value, label)
    result = [_string(item, label) for item in values]
    if len(result) != len(set(result)):
        _stop(f"{label} contains a duplicate string")
    return result


def _strings(value: object, label: str) -> list[str]:
    result = _string_values(value, label)
    if result != sorted(result):
        _stop(f"{label} is not sorted")
    return result


def _validate_contract_shape(value: dict[str, object]) -> RegistryContract:
    root = _require_keys(
        value,
        {
            "schema_version",
            "story_id",
            "sources",
            "matrix",
            "bindings",
            "service_principal",
            "value_trust_boundary",
        },
        "contract",
    )
    if root["schema_version"] != 1 or root["story_id"] != "ST-0403":
        _stop("contract identity mismatch")
    sources = _require_keys(
        root["sources"],
        {
            "role_matrix",
            "security_design",
            "admin_openapi",
            "internal_openapi",
            "state_catalog",
            "authentication_contract",
            "step_up_contract",
            "database_role_contract",
            "final_approval_reference",
        },
        "sources",
    )
    for name, source in sources.items():
        _string(source, f"sources.{name}")

    matrix_base = {
        "action",
        "data_class",
        "allowed_roles",
        "mfa_required",
        "step_up_required",
        "separation_of_duties",
    }
    for index, item in enumerate(_list(root["matrix"], "matrix")):
        row = _mapping(item, f"matrix[{index}]")
        extra = set(row) - matrix_base
        if extra not in (set(), {"blocked_reason", "required_evidence"}):
            _stop(f"matrix[{index}] has unexpected keys")
        if not matrix_base <= set(row):
            _stop(f"matrix[{index}] is incomplete")
        for field in ("action", "data_class"):
            _string(row[field], f"matrix[{index}].{field}")
        _strings(row["allowed_roles"], f"matrix[{index}].allowed_roles")
        if any(
            type(row[field]) is not bool
            for field in (
                "mfa_required",
                "step_up_required",
                "separation_of_duties",
            )
        ):
            _stop(f"matrix[{index}] boolean field is invalid")
        if extra:
            _string(row["blocked_reason"], f"matrix[{index}].blocked_reason")
            if not _strings(
                row["required_evidence"], f"matrix[{index}].required_evidence"
            ):
                _stop(f"matrix[{index}] required evidence is empty")

    binding_base = {
        "operation_id",
        "action",
        "permission_scope",
        "resource_kind",
        "allowed_states",
        "status",
    }
    optional_groups = (
        {"block_reason", "required_evidence"},
        {"step_up_action", "step_up_resource_type"},
    )
    for index, item in enumerate(_list(root["bindings"], "bindings")):
        row = _mapping(item, f"bindings[{index}]")
        if not binding_base <= set(row):
            _stop(f"bindings[{index}] is incomplete")
        extra = set(row) - binding_base
        if any(bool(extra & group) != (group <= extra) for group in optional_groups):
            _stop(f"bindings[{index}] has a partial optional group")
        if extra - set().union(*optional_groups):
            _stop(f"bindings[{index}] has unexpected keys")
        for field in (
            "operation_id",
            "action",
            "permission_scope",
            "resource_kind",
            "status",
        ):
            _string(row[field], f"bindings[{index}].{field}")
        _strings(row["allowed_states"], f"bindings[{index}].allowed_states")
        if "block_reason" in row:
            _string(row["block_reason"], f"bindings[{index}].block_reason")
            if not _strings(
                row["required_evidence"], f"bindings[{index}].required_evidence"
            ):
                _stop(f"bindings[{index}] required evidence is empty")
        if "step_up_action" in row:
            _string(row["step_up_action"], f"bindings[{index}].step_up_action")
            _string(
                row["step_up_resource_type"],
                f"bindings[{index}].step_up_resource_type",
            )

    service = _require_keys(
        root["service_principal"],
        {"status", "database_workload_roles", "required_evidence"},
        "service_principal",
    )
    _string(service["status"], "service_principal.status")
    _strings(
        service["database_workload_roles"],
        "service_principal.database_workload_roles",
    )
    _string(service["required_evidence"], "service_principal.required_evidence")
    value_boundary = _require_keys(
        root["value_trust_boundary"],
        {
            "status",
            "constructor_scope",
            "external_input_construction",
            "unforgeable_capability",
            "runtime_enforcement_entrypoints",
            "business_action_execution",
        },
        "value_trust_boundary",
    )
    if (
        value_boundary["status"] != "TRUSTED_IN_PROCESS_TCB_ONLY"
        or value_boundary["constructor_scope"]
        != "INTERNAL_VALUE_NORMALIZATION_NOT_SERVICE_PROVENANCE"
        or value_boundary["external_input_construction"] != "FORBIDDEN"
        or value_boundary["unforgeable_capability"] is not False
        or value_boundary["business_action_execution"] is not False
        or _strings(
            value_boundary["runtime_enforcement_entrypoints"],
            "value_trust_boundary.runtime_enforcement_entrypoints",
        )
        != [
            "AuthorizationGuard.require",
            "DurableAuthorizationService.evaluate_admin",
            "DurableAuthorizationService.require_admin",
        ]
    ):
        _stop("value trust boundary drift")
    return cast(RegistryContract, root)


def _source_paths(contract: RegistryContract) -> dict[str, Path]:
    sources = contract["sources"]
    sources_by_name = {
        "role_matrix": sources["role_matrix"],
        "security_design": sources["security_design"],
        "admin_openapi": sources["admin_openapi"],
        "internal_openapi": sources["internal_openapi"],
        "state_catalog": sources["state_catalog"],
        "authentication_contract": sources["authentication_contract"],
        "step_up_contract": sources["step_up_contract"],
        "database_role_contract": sources["database_role_contract"],
        "final_approval_reference": sources["final_approval_reference"],
    }
    paths: dict[str, Path] = {}
    for name, raw in sources_by_name.items():
        expected_binding = _EXPECTED_SOURCE_BINDINGS.get(name)
        if expected_binding is None or raw != expected_binding[0]:
            _stop(f"source binding drift: {name}")
        if raw.startswith("/") or ".." in raw.split("/"):
            _stop(f"invalid source path: {name}")
        path = ROOT / raw
        if not path.is_file():
            _stop(f"missing source path: {name}")
        if _sha(path) != expected_binding[1]:
            _stop(f"source hash drift: {name}")
        paths[name] = path
    if set(paths) != set(_EXPECTED_SOURCE_BINDINGS):
        _stop("source inventory drift")
    return paths


def _validate_matrix(contract: RegistryContract, sources: dict[str, Path]) -> None:
    source = _yaml(sources["role_matrix"])
    source_by_action: dict[str, dict[str, object]] = {}
    for index, value in enumerate(
        _list(source.get("permissions"), "Canonical permissions")
    ):
        row = _mapping(value, f"Canonical permissions[{index}]")
        action = _string(row.get("action"), "Canonical permission action")
        if action in source_by_action:
            _stop(f"duplicate Canonical matrix action: {action}")
        source_by_action[action] = row
    configured_by_action = {row["action"]: row for row in contract["matrix"]}
    if (
        set(source_by_action) != set(configured_by_action)
        or len(contract["matrix"]) != 19
    ):
        _stop("configured matrix does not cover the exact 19 Canonical actions")
    security_text = _bytes(sources["security_design"]).decode("utf-8")
    for action, configured_row in configured_by_action.items():
        source_row = source_by_action[action]
        for field in (
            "data_class",
            "mfa_required",
            "separation_of_duties",
        ):
            if configured_row[field] != source_row.get(field):
                _stop(f"matrix drift for {action}.{field}")
        canonical_roles = _string_values(
            source_row.get("allowed_roles"), f"Canonical {action}.allowed_roles"
        )
        if configured_row["allowed_roles"] != sorted(canonical_roles):
            _stop(f"matrix role drift for {action}")
        configured_step_up = configured_row["step_up_required"]
        source_step_up = source_row.get("step_up_required")
        if configured_step_up != source_step_up:
            if not (
                action == "final_approve"
                and configured_step_up is True
                and source_step_up is False
                and "Final Approval、Publish、Rollback" in security_text
            ):
                _stop(f"unapproved step-up drift for {action}")


def _admin_operations(source: dict[str, object]) -> dict[str, set[str]]:
    paths = _mapping(source.get("paths"), "Admin OpenAPI paths")
    operations: dict[str, set[str]] = {}
    for raw_path_item in paths.values():
        if type(raw_path_item) is not dict:
            continue
        path_item = _mapping(cast(object, raw_path_item), "Admin OpenAPI path item")
        for raw_operation in path_item.values():
            if type(raw_operation) is not dict:
                continue
            operation = _mapping(cast(object, raw_operation), "Admin OpenAPI operation")
            operation_id = operation.get("operationId")
            if type(operation_id) is not str:
                continue
            scopes: set[str] = set()
            security = operation.get("security")
            if type(security) is list:
                for raw_requirement in cast(list[object], security):
                    if type(raw_requirement) is dict:
                        requirement = _mapping(
                            cast(object, raw_requirement),
                            "Admin OpenAPI security requirement",
                        )
                        for raw_values in requirement.values():
                            if type(raw_values) is list:
                                scopes.update(
                                    value
                                    for value in cast(list[object], raw_values)
                                    if type(value) is str
                                )
            if operation_id in operations:
                _stop(f"duplicate Admin OpenAPI operation: {operation_id}")
            operations[operation_id] = scopes
    return operations


def _validate_closed_dependency(
    document: dict[str, object], *, story_id: str
) -> dict[str, object]:
    if document.get("story_id") != story_id or document.get("status") != (
        "LOCAL_CODE_COMPLETE"
    ):
        _stop(f"{story_id} dependency identity drift")
    authority = _mapping(document.get("authority"), f"{story_id} authority")
    if not authority or any(
        type(value) is not bool or value for value in authority.values()
    ):
        _stop(f"{story_id} external authority is not closed")
    runtime = _mapping(document.get("runtime"), f"{story_id} runtime")
    if runtime.get("external_provider_calls") is not False:
        _stop(f"{story_id} external provider boundary drift")
    transport = _mapping(runtime.get("transport"), f"{story_id} transport")
    if transport.get("route_registration") is not False:
        _stop(f"{story_id} route boundary drift")
    return runtime


def _validate_authentication_boundary(sources: dict[str, Path]) -> None:
    _validate_closed_dependency(
        _json(sources["authentication_contract"]), story_id="ST-0401"
    )


def _validate_bindings(contract: RegistryContract, sources: dict[str, Path]) -> None:
    bindings = contract["bindings"]
    if not bindings:
        _stop("operation bindings are absent")
    operations = _admin_operations(_yaml(sources["admin_openapi"]))
    states_source = _bytes(sources["state_catalog"]).decode("utf-8")
    step_up = _json(sources["step_up_contract"])
    runtime = _validate_closed_dependency(step_up, story_id="ST-0402")
    binding_boundary = _mapping(runtime.get("binding"), "ST-0402 binding")
    if binding_boundary.get("role_authorization_granted") is not False:
        _stop("ST-0402 role authorization boundary drift")
    action_policy = _mapping(runtime.get("action_policy"), "ST-0402 action policy")
    mapping = _mapping(action_policy.get("mapping"), "ST-0402 action mapping")
    seen: set[tuple[str, str]] = set()
    for index, binding in enumerate(bindings):
        operation_id = binding["operation_id"]
        action = binding["action"]
        scope = binding["permission_scope"]
        key = (operation_id, action)
        if key in seen:
            _stop(f"duplicate or invalid binding {index}")
        seen.add(key)
        if operation_id not in operations or scope not in operations[operation_id]:
            _stop(f"OpenAPI scope drift for {operation_id}/{scope}")
        allowed_states = binding["allowed_states"]
        if any(f"- {state}\n" not in states_source for state in allowed_states):
            _stop(f"state catalog drift for {operation_id}")
        step_action = binding.get("step_up_action")
        step_resource = binding.get("step_up_resource_type")
        if (step_action is None) != (step_resource is None):
            _stop(f"partial step-up mapping for {operation_id}")
        if step_action is not None and mapping.get(step_action) != step_resource:
            _stop(f"ST-0402 mapping drift for {operation_id}")


def _validate_service_boundary(
    contract: RegistryContract, sources: dict[str, Path]
) -> None:
    service = contract["service_principal"]
    if service["status"] != "DISABLED_MAPPING_UNRESOLVED":
        _stop("service authorization must remain disabled")
    database = _yaml(sources["database_role_contract"])
    if service["database_workload_roles"] != sorted(
        _string_values(database.get("roles"), "database workload roles")
    ):
        _stop("database workload-role inventory drift")
    internal = _yaml(sources["internal_openapi"])
    components = _mapping(internal.get("components"), "Internal OpenAPI components")
    schemes = _mapping(
        components.get("securitySchemes"), "Internal OpenAPI security schemes"
    )
    if set(schemes) != {"serviceBearer"}:
        _stop("unexpected internal service security scheme inventory")


def _python_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _enum_tuple(*, field: str, values: list[str], expression: str) -> list[str]:
    prefix = f"        {field}="
    rendered = [expression.format(value=value) for value in values]
    if not rendered:
        return [prefix + "(),"]
    if len(rendered) == 1:
        return [prefix + f"({rendered[0]},),"]
    return [
        prefix + "(",
        *(f"            {value}," for value in rendered),
        "        ),",
    ]


def _string_tuple(*, field: str, values: list[str]) -> list[str]:
    prefix = f"        {field}="
    rendered = [_python_string(value) for value in values]
    if not rendered:
        return [prefix + "(),"]
    if len(rendered) == 1:
        return [prefix + f"({rendered[0]},),"]
    return [
        prefix + "(",
        *(f"            {value}," for value in rendered),
        "        ),",
    ]


def _python(contract: RegistryContract) -> bytes:
    lines = [
        '"""Generated by scripts/build_st0403_authorization_runtime.py; do not edit."""',
        "",
        "from raos.domain.iam.authorization import (",
        "    AuthorizationBindingBlockReason,",
        "    AuthorizationBindingStatus,",
        "    AuthorizationDataClass,",
        "    BusinessRole,",
        "    CanonicalAuthorizationRegistry,",
        "    MatrixAction,",
        "    MatrixPermissionDefinition,",
        "    OperationAuthorizationBinding,",
        "    OperationId,",
        "    PermissionScope,",
        "    ResourceScopeKind,",
        "    ResourceState,",
        ")",
        "from raos.domain.iam.step_up import CriticalStepUpAction, StepUpResourceType",
        "",
        "",
        "MATRIX_DEFINITIONS = (",
    ]
    for matrix_row in contract["matrix"]:
        lines.extend(
            [
                "    MatrixPermissionDefinition(",
                f"        action=MatrixAction.{matrix_row['action'].upper()},",
                "        data_class="
                f"AuthorizationDataClass.{matrix_row['data_class']},",
            ]
        )
        lines.extend(
            _enum_tuple(
                field="allowed_roles",
                values=matrix_row["allowed_roles"],
                expression="BusinessRole.{value}",
            )
        )
        lines.extend(
            [
                f"        mfa_required={matrix_row['mfa_required']!r},",
                f"        step_up_required={matrix_row['step_up_required']!r},",
                f"        separation_of_duties={matrix_row['separation_of_duties']!r},",
            ]
        )
        if "blocked_reason" in matrix_row:
            required_evidence = matrix_row.get("required_evidence")
            if required_evidence is None:
                _stop("matrix blocked row lost required evidence")
            lines.append(
                "        blocked_reason="
                "AuthorizationBindingBlockReason."
                f"{matrix_row['blocked_reason']},"
            )
            lines.extend(
                _string_tuple(field="required_evidence", values=required_evidence)
            )
        lines.append("    ),")
    lines.extend([")", "", "", "OPERATION_BINDINGS = ("])
    for binding_row in contract["bindings"]:
        lines.extend(
            [
                "    OperationAuthorizationBinding(",
                "        operation_id="
                f"OperationId({_python_string(binding_row['operation_id'])}),",
                f"        action=MatrixAction.{binding_row['action'].upper()},",
                "        permission_scope="
                "PermissionScope("
                f"{_python_string(binding_row['permission_scope'])}),",
                "        resource_kind="
                f"ResourceScopeKind.{binding_row['resource_kind']},",
            ]
        )
        lines.extend(
            _enum_tuple(
                field="allowed_states",
                values=binding_row["allowed_states"],
                expression='ResourceState("{value}")',
            )
        )
        lines.extend(
            [
                f"        status=AuthorizationBindingStatus.{binding_row['status']},",
            ]
        )
        if "block_reason" in binding_row:
            required_evidence = binding_row.get("required_evidence")
            if required_evidence is None:
                _stop("blocked binding lost required evidence")
            lines.append(
                "        block_reason="
                "AuthorizationBindingBlockReason."
                f"{binding_row['block_reason']},"
            )
            lines.extend(
                _string_tuple(field="required_evidence", values=required_evidence)
            )
        if "step_up_action" in binding_row:
            step_up_resource_type = binding_row.get("step_up_resource_type")
            if step_up_resource_type is None:
                _stop("step-up binding lost resource type")
            lines.extend(
                [
                    "        step_up_action=CriticalStepUpAction."
                    f"{binding_row['step_up_action'].upper()},",
                    "        step_up_resource_type="
                    f"StepUpResourceType.{step_up_resource_type},",
                ]
            )
        lines.append("    ),")
    lines.extend(
        [
            ")",
            "",
            "",
            "CANONICAL_AUTHORIZATION_REGISTRY = CanonicalAuthorizationRegistry(",
            "    definitions=MATRIX_DEFINITIONS,",
            "    bindings=OPERATION_BINDINGS,",
            ")",
            "",
            "",
            "__all__ = [",
            '    "CANONICAL_AUTHORIZATION_REGISTRY",',
            '    "MATRIX_DEFINITIONS",',
            '    "OPERATION_BINDINGS",',
            "]",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _outputs(contract: RegistryContract, sources: dict[str, Path]) -> dict[Path, bytes]:
    source_hashes = {
        str(path.relative_to(ROOT)): _sha(path)
        for path in sorted(sources.values(), key=lambda item: str(item))
    }
    generated_document = {
        "schema_version": 1,
        "story_id": "ST-0403",
        "status": "LOCAL_CODE_COMPLETE",
        "source_sha256": source_hashes,
        "matrix": contract["matrix"],
        "bindings": contract["bindings"],
        "service_principal": contract["service_principal"],
        "value_trust_boundary": contract["value_trust_boundary"],
    }
    generated_json = _json_bytes(generated_document)
    generated_python = _python(contract)
    artifact_hashes = {
        str(CONTRACT.relative_to(ROOT)): _sha(CONTRACT),
        str(DURABLE_CONTRACT.relative_to(ROOT)): _sha(DURABLE_CONTRACT),
        str(GENERATED_JSON.relative_to(ROOT)): hashlib.sha256(
            generated_json
        ).hexdigest(),
        str(GENERATED_PYTHON.relative_to(ROOT)): hashlib.sha256(
            generated_python
        ).hexdigest(),
    }
    implementation_hashes = {
        str(path.relative_to(ROOT)): _sha(path)
        for path in sorted(_IMPLEMENTATION_PATHS, key=lambda item: str(item))
    }
    manifest = _json_bytes(
        {
            "schema_version": 1,
            "story_id": "ST-0403",
            "status": "LOCAL_CODE_COMPLETE",
            "generator": "scripts/build_st0403_authorization_runtime.py",
            "artifacts_sha256": artifact_hashes,
            "implementation_sha256": implementation_hashes,
            "source_sha256": source_hashes,
            "authority": {
                "external_http": False,
                "live_provider": False,
                "service_principal": False,
                "business_action_execution": False,
                "publication": False,
                "production": False,
            },
        }
    )
    return {
        GENERATED_JSON: generated_json,
        GENERATED_PYTHON: generated_python,
        MANIFEST: manifest,
    }


def _write_or_check(outputs: dict[Path, bytes], *, check: bool) -> None:
    mismatches: list[str] = []
    for path, content in outputs.items():
        if check:
            if not path.is_file() or _bytes(path) != content:
                mismatches.append(str(path.relative_to(ROOT)))
    if mismatches:
        _stop("generated drift: " + ", ".join(sorted(mismatches)))
    if not check:
        try:
            secure_generated_publication.publish_generated(
                tuple(outputs.items()),
                namespace="st0403v1",
                maximum_payload_bytes=_MAX_GENERATED_BYTES,
            )
        except secure_generated_publication.SecurePublicationError:
            _stop("secure generated publication failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    if _sha(CONTRACT) != _EXPECTED_CONTRACT_SHA256:
        _stop("contract hash drift")
    if _sha(DURABLE_CONTRACT) != _EXPECTED_DURABLE_CONTRACT_SHA256:
        _stop("durable contract hash drift")
    durable_contract = _json(DURABLE_CONTRACT)
    if (
        durable_contract.get("schema_version") != 2
        or durable_contract.get("story_id") != "ST-0403"
        or durable_contract.get("status") != "LOCAL_CODE_COMPLETE_CANDIDATE"
    ):
        _stop("durable contract identity mismatch")
    durable_runtime = _mapping(
        durable_contract.get("runtime"), "durable contract runtime"
    )
    durable_authority = _mapping(
        durable_contract.get("authority"), "durable contract authority"
    )
    if (
        type(durable_runtime.get("external_action_count")) is not int
        or durable_runtime.get("external_action_count") != 0
        or durable_runtime.get("business_action_execution") is not False
        or set(
            _string_values(
                durable_runtime.get("environments"),
                "durable contract environments",
            )
        )
        != {"CI", "ENV-DEV"}
        or not durable_authority
        or any(value is not False for value in durable_authority.values())
    ):
        _stop("durable contract authority boundary mismatch")
    if (
        _sha(ROOT / "scripts/secure_generated_publication.py")
        != _EXPECTED_SECURE_HELPER_SHA256
    ):
        _stop("secure publication helper drift")
    contract = _validate_contract_shape(_json(CONTRACT))
    sources = _source_paths(contract)
    _validate_matrix(contract, sources)
    _validate_authentication_boundary(sources)
    _validate_bindings(contract, sources)
    _validate_service_boundary(contract, sources)
    _write_or_check(_outputs(contract, sources), check=arguments.check)


if __name__ == "__main__":
    main()
