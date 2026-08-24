#!/usr/bin/env python3
"""Build deterministic, local-only ST-0705 profiles and evidence."""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
import errno
import hashlib
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
import os
from pathlib import Path
import stat
import sys
from typing import Final, NoReturn, cast

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "python") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "python"))

from raos.domain.ai.output_validation import (  # noqa: E402
    AiOutputValidationInput,
    CoverageMode,
    JsonLocator,
    OrderLocator,
    PROFILE_REGISTRY_VERSION,
    ProviderMode,
    RecordedOutputEnvelope,
    ReferenceFormat,
    ResourceBinding,
    ResourceKind,
    ResourceLocator,
    ResourceValidationStatus,
    RuntimeCheckBinding,
    ScalarKind,
    ScalarLocator,
    SemanticReceiptBinding,
    SemanticReceiptKind,
    SemanticReceiptRequirement,
    SemanticReceiptStatus,
    TaskValidationProfile,
    TRUSTED_PROFILE_REGISTRY_SHA256,
    TRUSTED_PROFILE_SHA256_BY_TASK,
    ValidationManifest,
    evaluate_ai_output,
)
from raos.domain.ai.provider import (  # noqa: E402
    CanonicalJsonObject,
    Sha256Digest,
    StructuredOutputSchema,
)


CONTRACT_PATH: Final = Path(
    "changes/st-0705/contracts/ai-output-validation-runtime.v1.yaml"
)
PROFILE_REGISTRY_PATH: Final = Path(
    "changes/st-0705/generated/ai-output-validation-profiles.v1.json"
)
PASS_FIXTURE_PATH: Final = Path(
    "changes/st-0705/generated/ai-output-validation-pass.v1.json"
)
RUNTIME_MANIFEST_PATH: Final = Path("changes/st-0705/runtime-manifest.v1.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0705_ai_output_validation_runtime.py")
DOMAIN_PATH: Final = Path("python/raos/domain/ai/output_validation.py")
PORT_PATH: Final = Path("python/raos/ports/ai_output_validation.py")
APPLICATION_PATH: Final = Path("python/raos/application/ai/output_validation.py")
ADAPTER_PATH: Final = Path("python/raos/adapters/recorded_ai_output_validation.py")
TASK_REGISTRY_PATH: Final = Path("changes/st-0701/generated/ai-task-registry.v1.json")
CONTEXT_CONTRACT_PATH: Final = Path(
    "changes/st-0702/contracts/context-pack-reference-plan.v1.yaml"
)
ALIGNMENT_PATH: Final = Path(
    "changes/st-0004/contracts/content/ai-content-alignment.v0.4.yaml"
)
PROVIDER_PATH: Final = Path("python/raos/domain/ai/provider.py")
COVERAGE_PATH: Final = Path("python/raos/domain/evidence/claim_evidence.py")
RUNTIME_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    DOMAIN_PATH,
    PORT_PATH,
    APPLICATION_PATH,
    ADAPTER_PATH,
    Path("changes/st-0705/README.md"),
    Path("changes/st-0705/RUNTIME.md"),
    Path("docs/execplans/ST-0705.md"),
    Path("docs/worklogs/ST-0705.md"),
    Path("tests/st0705_runtime/__init__.py"),
    Path("tests/st0705_runtime/conftest.py"),
    Path("tests/st0705_runtime/test_coverage_binding.py"),
    Path("tests/st0705_runtime/test_generation_security.py"),
    Path("tests/st0705_runtime/test_profiles_and_application.py"),
    Path("tests/st0705_runtime/test_task_semantics_and_limits.py"),
    Path("tests/st0705_runtime/test_validation_negative_paths.py"),
    Path("pyproject.toml"),
    Path("uv.lock"),
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
EXPECTED_PROFILE_IDS: Final = tuple(f"AIT-{number:03d}" for number in range(1, 13))
PINNED_INPUTS: Final[dict[Path, str]] = {
    TASK_REGISTRY_PATH: "33bbb3601aae2e02d37bf995a2522e67684befcd9a43ba4375b4a7685aedef07",
    CONTEXT_CONTRACT_PATH: "b684e534268de79e4b118713f07932cfa71d10bda2e092003f00985f76811eaf",
    ALIGNMENT_PATH: "7b141fdb7e401ee886efe59f65e9bdff6be4af566deca73d29ebc50a1f200477",
    PROVIDER_PATH: "179f608a54c87037556f3c202b08fc7be3207081e9737466e24b9de84392e991",
    COVERAGE_PATH: "97996a564e6fe21a417f06110fbb7dfd66d605bd2fa43aa9f19e9a4c11592c81",
    Path(
        "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
    ): "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    Path(
        "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
    ): "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    Path(
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
    ): "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    Path(
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
    ): "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
}
EXPECTED_TOOLCHAIN: Final = {
    "python_implementation": "cpython",
    "python_version": "3.14.6",
    "pyyaml": "6.0.3",
    "jsonschema": "4.26.0",
    "attrs": "26.1.0",
    "referencing": "0.37.0",
    "rpds-py": "2026.6.3",
}
RUNTIME_CHECK_BINDINGS: Final[dict[str, tuple[str, ...]]] = {
    "audit_manifest": ("AIOV-000", "AIOV-010"),
    "budget": ("RECEIPT:PROVIDER_SUCCESS_SAFETY",),
    "forbidden_content": ("AIOV-007",),
    "input_manifest": ("RECEIPT:CONTEXT_MANIFEST_BINDING",),
    "refusal_and_incomplete": ("RECEIPT:PROVIDER_SUCCESS_SAFETY",),
    "resource_reference": ("AIOV-003", "AIOV-004"),
    "strict_schema": ("AIOV-001", "AIOV-002"),
    "manifest_signature": ("RECEIPT:CONTEXT_MANIFEST_BINDING",),
    "no_forbidden_input_fields": ("AIOV-000", "AIOV-007"),
    "policy_bundle_active": ("RECEIPT:POLICY_BUNDLE_BINDING",),
    "schema_hash_match": ("AIOV-000", "AIOV-010"),
    "typed_arguments": ("RECEIPT:CONTEXT_MANIFEST_BINDING",),
}
EXPECTED_CONTEXT_ST0701_SEMANTICS: Final[dict[str, object]] = {
    "task_count": 12,
    "complete_binding_metadata": True,
    "source_packet_required_task_count": 9,
    "source_packet_not_required_task_count": 3,
    "typed_manifest_only": True,
    "tools_allowed": False,
    "task_activation": False,
    "selected_provider": None,
    "provider_call": "NOT_EXECUTED",
    "route_execution": "NOT_EXECUTED",
    "network_access": False,
    "state_change_allowed": False,
    "provider_storage_allowed": False,
    "strict_structured_output": True,
    "forbidden_inputs_excluded": True,
    "required_input_checks_complete": True,
    "formal_validation": "NOT_EXECUTED",
}
EXPECTED_CONTEXT_PACKING_RULES: Final[dict[str, object]] = {
    "typed_manifest_required": True,
    "input_manifest_check_required": True,
    "audit_manifest_check_required": True,
    "source_packet_requirement_is_task_scoped": True,
    "deterministic_repack_on_context_overflow_required": True,
    "silent_required_fact_truncation_forbidden": True,
    "only_allowlisted_inputs_may_be_considered": True,
    "denied_inputs_must_be_excluded": True,
    "task_input_and_output_bounds_are_descriptive_only": True,
}
EXPECTED_CONTEXT_ACTION_COUNTS: Final[dict[str, object]] = {
    "build": 0,
    "select": 0,
    "scan": 0,
    "pack": 0,
    "serialize": 0,
    "hash": 0,
    "estimate": 0,
    "reduce_scope": 0,
    "drop_item": 0,
    "create_manifest": 0,
    "provider_call": 0,
    "network": 0,
    "repository_write": 0,
    "database_write": 0,
    "job": 0,
    "event": 0,
    "external": 0,
}
EXPECTED_COMMON_RECEIPT_KINDS: Final = (
    SemanticReceiptKind.CONTEXT_MANIFEST_BINDING,
    SemanticReceiptKind.INPUT_TAINT_SCAN,
    SemanticReceiptKind.PROVIDER_SUCCESS_SAFETY,
    SemanticReceiptKind.POLICY_BUNDLE_BINDING,
    SemanticReceiptKind.REVIEW_CONTAMINATION_SCAN,
    SemanticReceiptKind.SENSITIVE_DATA_SCAN,
)


class St0705BuildError(ValueError):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_ST0705_AI_OUTPUT_VALIDATION_RUNTIME")


def _fail() -> NoReturn:
    raise St0705BuildError() from None


class _StrictLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if type(key) is not str or key in result:
            _fail()
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _repository_path(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        _fail()
    if root.is_symlink() or not root.is_dir():
        _fail()
    path = root / relative
    current = root
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            _fail()
    try:
        path.parent.resolve(strict=True).relative_to(root.resolve(strict=True))
    except OSError, ValueError:
        _fail()
    return path


def _read_regular(
    root: Path, relative: Path, *, maximum: int = MAX_SOURCE_BYTES
) -> bytes:
    path = _repository_path(root, relative)
    try:
        if path.is_symlink() or not path.is_file():
            _fail()
        data = path.read_bytes()
    except OSError:
        _fail()
    if not data or len(data) > maximum:
        _fail()
    return data


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_yaml_bytes(data: bytes) -> dict[str, object]:
    try:
        for token in yaml.scan(data):
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                _fail()
        loaded = yaml.load(data, Loader=_StrictLoader)
    except St0705BuildError:
        raise
    except Exception:
        _fail()
    if type(loaded) is not dict:
        _fail()
    return cast(dict[str, object], loaded)


def _load_json_bytes(data: bytes) -> dict[str, object]:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                _fail()
            result[key] = value
        return result

    try:
        loaded = json.loads(
            data,
            object_pairs_hook=pairs,
            parse_constant=lambda _value: _fail(),
        )
    except St0705BuildError:
        raise
    except Exception:
        _fail()
    if type(loaded) is not dict:
        _fail()
    return cast(dict[str, object], loaded)


def load_contract(root: Path = REPO_ROOT) -> dict[str, object]:
    return _load_yaml_bytes(_read_regular(root, CONTRACT_PATH))


def _mapping(value: object) -> dict[str, object]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        _fail()
    return cast(dict[str, object], value)


def _sequence(value: object) -> list[object]:
    if type(value) is not list or len(value) > 10_000:
        _fail()
    return cast(list[object], value)


def _string(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _integer(value: object) -> int:
    if type(value) is not int or value < 0:
        _fail()
    return value


def _check_pins(root: Path) -> None:
    for path, expected in PINNED_INPUTS.items():
        if _sha(_read_regular(root, path)) != expected:
            _fail()


def _exact_scalar_mapping(
    value: dict[str, object], expected: dict[str, object]
) -> None:
    if set(value) != set(expected):
        _fail()
    for key, expected_value in expected.items():
        actual = value[key]
        if type(actual) is not type(expected_value) or actual != expected_value:
            _fail()


def _validate_context_contract_semantics(root: Path) -> None:
    context = _load_yaml_bytes(_read_regular(root, CONTEXT_CONTRACT_PATH))
    document = _mapping(context.get("document"))
    if (
        document.get("story_id") != "ST-0702"
        or document.get("executable") is not False
        or document.get("interface_only") is not True
        or document.get("decision") != "NOT_READY"
        or document.get("story_acceptance") is not False
        or document.get("production_eligible") is not False
    ):
        _fail()

    predecessors = _mapping(context.get("predecessors"))
    st0701 = _mapping(predecessors.get("st0701"))
    _exact_scalar_mapping(
        _mapping(st0701.get("required_semantics")),
        EXPECTED_CONTEXT_ST0701_SEMANTICS,
    )
    packing = _mapping(context.get("packing_rules"))
    _exact_scalar_mapping(
        _mapping(packing.get("available")),
        EXPECTED_CONTEXT_PACKING_RULES,
    )
    execution = _mapping(context.get("execution_boundary"))
    _exact_scalar_mapping(
        _mapping(execution.get("action_counts")),
        EXPECTED_CONTEXT_ACTION_COUNTS,
    )
    build = _mapping(context.get("build_boundary"))
    if (
        build.get("build_permitted") is not False
        or build.get("provider_call_permitted") is not False
        or build.get("manifest_creation_permitted") is not False
        or build.get("decision") != "NOT_READY"
        or execution.get("provider_call") != "NOT_EXECUTED"
        or execution.get("network_access") != "NOT_EXECUTED"
        or execution.get("repository_write") != "NOT_EXECUTED"
        or execution.get("database_write") != "NOT_EXECUTED"
        or execution.get("event_emission") != "NOT_EXECUTED"
        or execution.get("external_action") != "NOT_EXECUTED"
        or execution.get("external_actions") != []
    ):
        _fail()


def _toolchain() -> dict[str, str]:
    versions: dict[str, str] = {
        "python_implementation": sys.implementation.name,
        "python_version": ".".join(str(item) for item in sys.version_info[:3]),
    }
    for distribution, key in (
        ("PyYAML", "pyyaml"),
        ("jsonschema", "jsonschema"),
        ("attrs", "attrs"),
        ("referencing", "referencing"),
        ("rpds-py", "rpds-py"),
    ):
        try:
            versions[key] = distribution_version(distribution)
        except PackageNotFoundError:
            _fail()
    if versions != EXPECTED_TOOLCHAIN:
        _fail()
    return versions


def _alignment(
    root: Path,
) -> tuple[dict[str, dict[str, tuple[str, ...]]], dict[str, str]]:
    document = _load_yaml_bytes(_read_regular(root, ALIGNMENT_PATH))
    canonical_names = {
        _string(key): _string(value)
        for key, value in _mapping(document["canonical_input_names"]).items()
    }
    result: dict[str, dict[str, tuple[str, ...]]] = {}
    for raw in _sequence(document["affected_tasks"]):
        row = _mapping(raw)
        task_id = _string(row["task_id"])
        source_inputs = tuple(
            _string(item)
            for item in _sequence(row.get("required_additional_inputs", []))
        )
        result[task_id] = {
            "required_inputs": tuple(
                canonical_names.get(item, item) for item in source_inputs
            ),
            "source_required_inputs": source_inputs,
            "required_outputs": tuple(
                _string(item) for item in _sequence(row.get("required_outputs", []))
            ),
            "prohibited_outputs": tuple(
                _string(item) for item in _sequence(row.get("prohibited_outputs", []))
            ),
        }
    return result, canonical_names


def _task_rows(root: Path) -> dict[str, dict[str, object]]:
    registry = _load_json_bytes(_read_regular(root, TASK_REGISTRY_PATH))
    rows: dict[str, dict[str, object]] = {}
    for raw in _sequence(registry["tasks"]):
        row = _mapping(raw)
        task_id = _string(_mapping(row["task"])["id"])
        if task_id in rows:
            _fail()
        rows[task_id] = row
    if tuple(sorted(rows)) != EXPECTED_PROFILE_IDS:
        _fail()
    return rows


def _receipt_requirement(
    root: Path, contract_sha256: str, raw: object
) -> SemanticReceiptRequirement:
    row = _mapping(raw)
    path = _string(row["owner_contract_path"])
    declared = _string(row["owner_contract_sha256"])
    if path == "SELF":
        if declared != "SELF":
            _fail()
        digest = contract_sha256
    else:
        relative = Path(path)
        digest = _sha(_read_regular(root, relative))
        if digest != declared:
            _fail()
    try:
        return SemanticReceiptRequirement(
            receipt_kind=SemanticReceiptKind(_string(row["receipt_kind"])),
            owner_story_id=_string(row["owner_story_id"]),
            owner_contract_sha256=Sha256Digest(digest),
        )
    except Exception:
        _fail()


def build_profiles(
    contract: dict[str, object], root: Path = REPO_ROOT
) -> tuple[TaskValidationProfile, ...]:
    _check_pins(root)
    _validate_context_contract_semantics(root)
    contract_bytes = _read_regular(root, CONTRACT_PATH)
    contract_sha256 = _sha(contract_bytes)
    profiles_raw = _mapping(contract.get("profiles"))
    if tuple(profiles_raw) != EXPECTED_PROFILE_IDS:
        _fail()
    task_rows = _task_rows(root)
    alignment, _canonical_names = _alignment(root)
    common = tuple(
        _receipt_requirement(root, contract_sha256, item)
        for item in _sequence(contract.get("common_semantic_receipts"))
    )
    if tuple(item.receipt_kind for item in common) != EXPECTED_COMMON_RECEIPT_KINDS:
        _fail()
    context_digest = Sha256Digest(PINNED_INPUTS[CONTEXT_CONTRACT_PATH])
    for item in common[:2]:
        if (
            item.owner_story_id != "ST-0702"
            or item.owner_contract_sha256 != context_digest
        ):
            _fail()
    built: list[TaskValidationProfile] = []
    for task_id in EXPECTED_PROFILE_IDS:
        spec = _mapping(profiles_raw[task_id])
        row = task_rows[task_id]
        task = _mapping(row["task"])
        prompt = _mapping(row["prompt"])
        prompt_metadata = _mapping(prompt["metadata"])
        route = _mapping(row["route"])
        output_schema = _mapping(row["output_schema"])
        artifact_path = Path(_string(output_schema["artifact_path"]))
        schema_path = Path("contracts/raos-v0.4") / artifact_path
        schema_bytes = _read_regular(root, schema_path)
        if _sha(schema_bytes) != _string(output_schema["sha256"]):
            _fail()
        alignment_row = alignment.get(
            task_id,
            {
                "required_inputs": (),
                "source_required_inputs": (),
                "required_outputs": (),
                "prohibited_outputs": (),
            },
        )
        resources: list[ResourceLocator] = []
        for raw_locator in _sequence(spec["resource_locators"]):
            locator = _mapping(raw_locator)
            resources.append(
                ResourceLocator(
                    locator=JsonLocator(
                        _string(locator["locator_id"]),
                        _string(locator["pointer"]),
                    ),
                    reference_format=ReferenceFormat(
                        _string(locator["reference_format"])
                    ),
                    resource_kind=ResourceKind(_string(locator["resource_kind"])),
                    membership_required=_boolean(locator["membership_required"]),
                )
            )
        scalars: list[ScalarLocator] = []
        for raw_locator in _sequence(spec["scalar_locators"]):
            locator = _mapping(raw_locator)
            scalars.append(
                ScalarLocator(
                    locator=JsonLocator(
                        _string(locator["locator_id"]),
                        _string(locator["pointer"]),
                    ),
                    scalar_kind=ScalarKind(_string(locator["scalar_kind"])),
                )
            )
        orders: list[OrderLocator] = []
        for raw_locator in _sequence(spec["order_locators"]):
            locator = _mapping(raw_locator)
            locator_id = _string(locator["locator_id"])
            orders.append(
                OrderLocator(
                    locator_id=locator_id,
                    collection=JsonLocator(
                        f"{locator_id}.collection",
                        _string(locator["collection_pointer"]),
                    ),
                    identity_field=_string(locator["identity_field"]),
                    rank_field=_string(locator["rank_field"]),
                )
            )
        claim_raw = spec["claim_collection"]
        claim_locator = None
        claim_maximum = 0
        if claim_raw is not None:
            claim = _mapping(claim_raw)
            claim_locator = JsonLocator(
                _string(claim["locator_id"]), _string(claim["pointer"])
            )
            claim_maximum = _integer(claim["maximum"])
        version_locators: list[JsonLocator] = []
        version_value: str | None = None
        for raw_version in _sequence(spec["schema_versions"]):
            version = _mapping(raw_version)
            observed_value = _string(version["value"])
            if version_value is not None and version_value != observed_value:
                _fail()
            version_value = observed_value
            version_locators.append(
                JsonLocator(_string(version["locator_id"]), _string(version["pointer"]))
            )
        receipts = common + tuple(
            _receipt_requirement(root, contract_sha256, item)
            for item in _sequence(spec["additional_receipts"])
        )
        if len({item.receipt_kind for item in receipts}) != len(receipts):
            _fail()
        task_checks = tuple(
            _string(item) for item in _sequence(task["required_runtime_checks"])
        )
        prompt_checks = tuple(
            _string(item)
            for item in _sequence(prompt_metadata["required_runtime_checks"])
        )
        all_checks = tuple(dict.fromkeys((*task_checks, *prompt_checks)))
        if any(item not in RUNTIME_CHECK_BINDINGS for item in all_checks):
            _fail()
        try:
            profile = TaskValidationProfile(
                task_id=task_id,
                task_code=_string(task["task_code"]),
                lifecycle=_string(task["lifecycle"]),
                output_schema_path=schema_path.as_posix(),
                output_schema_id=_string(output_schema["schema_id"]),
                output_schema_sha256=Sha256Digest(_string(output_schema["sha256"])),
                task_binding_sha256=Sha256Digest(_string(row["binding_sha256"])),
                task_sha256=Sha256Digest(_string(row["task_sha256"])),
                prompt_sha256=Sha256Digest(_string(prompt["sha256"])),
                route_sha256=Sha256Digest(_string(route["sha256"])),
                max_output_tokens=_integer(task["max_output_tokens"]),
                max_output_bytes=4 * 1024 * 1024,
                allowed_input_fields=tuple(
                    _string(item) for item in _sequence(task["input_allowlist"])
                ),
                denied_input_fields=tuple(
                    _string(item) for item in _sequence(task["input_denylist"])
                ),
                required_runtime_checks=task_checks,
                prompt_required_runtime_checks=prompt_checks,
                runtime_check_bindings=tuple(
                    RuntimeCheckBinding(
                        check_name=check,
                        enforcement_refs=RUNTIME_CHECK_BINDINGS[check],
                    )
                    for check in all_checks
                ),
                alignment_required_inputs=alignment_row["required_inputs"],
                alignment_required_outputs=alignment_row["required_outputs"],
                alignment_prohibited_outputs=alignment_row["prohibited_outputs"],
                required_semantic_receipts=receipts,
                semantic_capability_limitations=tuple(
                    _string(item)
                    for item in _sequence(spec["semantic_capability_limitations"])
                ),
                resource_locators=tuple(resources),
                scalar_locators=tuple(scalars),
                order_locators=tuple(orders),
                claim_collection=claim_locator,
                max_claim_count=claim_maximum,
                schema_version_locators=tuple(version_locators),
                schema_version_value=version_value,
                coverage_mode=CoverageMode(_string(spec["coverage_mode"])),
            )
        except Exception:
            _fail()
        built.append(profile)
    return tuple(built)


def _canonical_json(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )
    except Exception:
        _fail()


def profile_registry_bytes(
    contract: dict[str, object], root: Path = REPO_ROOT
) -> bytes:
    profiles = build_profiles(contract, root)
    alignment, canonical_names = _alignment(root)
    return _canonical_json(
        {
            "document": {
                "id": "RAOS-AI-OUTPUT-VALIDATION-PROFILES-001",
                "version": "1.0.0",
                "story_id": "ST-0705",
                "profile_registry_version": PROFILE_REGISTRY_VERSION,
                "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
                "authority": "NONE",
                "production_eligible": False,
            },
            "source_bindings": {
                "contract_sha256": _sha(_read_regular(root, CONTRACT_PATH)),
                "task_registry_sha256": PINNED_INPUTS[TASK_REGISTRY_PATH],
                "alignment_sha256": PINNED_INPUTS[ALIGNMENT_PATH],
            },
            "canonical_input_names": canonical_names,
            "alignment_source_required_inputs": {
                key: list(value["source_required_inputs"])
                for key, value in sorted(alignment.items())
            },
            "profiles": [
                {
                    **json.loads(profile.canonical_bytes()),
                    "profile_sha256": profile.profile_sha256.value,
                }
                for profile in profiles
            ],
        }
    )


def trust_anchors(
    contract: dict[str, object], root: Path = REPO_ROOT
) -> dict[str, object]:
    registry_bytes = profile_registry_bytes(contract, root)
    profiles = build_profiles(contract, root)
    return {
        "profile_registry_sha256": _sha(registry_bytes),
        "profile_sha256_by_task": {
            profile.task_id: profile.profile_sha256.value for profile in profiles
        },
    }


def _pass_fixture_bytes(contract: dict[str, object], root: Path = REPO_ROOT) -> bytes:
    profiles = {item.task_id: item for item in build_profiles(contract, root)}
    profile = profiles["AIT-001"]
    anchors = trust_anchors(contract, root)
    if (
        TRUSTED_PROFILE_REGISTRY_SHA256.value != anchors["profile_registry_sha256"]
        or {key: value.value for key, value in TRUSTED_PROFILE_SHA256_BY_TASK.items()}
        != anchors["profile_sha256_by_task"]
    ):
        _fail()
    fact_id = "66666666-6666-4666-8666-666666666666"
    output_document = {
        "schema_version": "1.0",
        "search_intent": "recorded synthetic decision intent",
        "decision_criteria": [],
        "content_gaps": [],
        "risks": [],
        "source_fact_ids": [fact_id],
    }
    output_bytes = CanonicalJsonObject(output_document).canonical_bytes()
    request_sha = Sha256Digest.of(b"ST0705_RECORDED_SYNTHETIC_REQUEST_V1")
    exchange_sha = Sha256Digest.of(b"ST0705_RECORDED_PROVIDER_EXCHANGE_V1")
    context_sha = Sha256Digest.of(b"ST0705_RECORDED_CONTEXT_MANIFEST_V1")
    envelope = RecordedOutputEnvelope(
        task_code=profile.task_code,
        provider_mode=ProviderMode.RECORDED_SYNTHETIC_ONLY,
        request_sha256=request_sha,
        provider_exchange_sha256=exchange_sha,
        raw_artifact_sha256=exchange_sha,
        output_bytes=output_bytes,
        raw_output_sha256=Sha256Digest.of(output_bytes),
    )
    if envelope.output_sha256 is None:
        _fail()
    receipts = tuple(
        SemanticReceiptBinding(
            receipt_kind=requirement.receipt_kind,
            owner_story_id=requirement.owner_story_id,
            owner_contract_sha256=requirement.owner_contract_sha256,
            request_sha256=request_sha,
            raw_output_sha256=envelope.raw_output_sha256,
            output_sha256=envelope.output_sha256,
            input_context_sha256=context_sha,
            evidence_sha256=Sha256Digest.of(
                f"ST0705:{requirement.receipt_kind.value}:PASS".encode()
            ),
            status=SemanticReceiptStatus.PASS,
        )
        for requirement in profile.required_semantic_receipts
    )
    resource_value_sha = Sha256Digest.of(b"ST0705_RECORDED_FACT_VALUE_V1")
    manifest = ValidationManifest(
        manifest_version="ST0705_VALIDATION_MANIFEST_V1",
        profile_registry_version=PROFILE_REGISTRY_VERSION,
        profile_registry_sha256=TRUSTED_PROFILE_REGISTRY_SHA256,
        task_id=profile.task_id,
        task_code=profile.task_code,
        profile_sha256=profile.profile_sha256,
        task_binding_sha256=profile.task_binding_sha256,
        task_sha256=profile.task_sha256,
        prompt_sha256=profile.prompt_sha256,
        route_sha256=profile.route_sha256,
        output_schema_id=profile.output_schema_id,
        output_schema_sha256=profile.output_schema_sha256,
        expected_request_sha256=request_sha,
        expected_raw_output_sha256=envelope.raw_output_sha256,
        expected_output_sha256=envelope.output_sha256,
        expected_input_context_sha256=context_sha,
        input_field_names=("approved_source_packet",),
        resources=(
            ResourceBinding(
                resource_id=fact_id,
                resource_kind=ResourceKind.FACT,
                validation_status=ResourceValidationStatus.VALID,
                value_sha256=resource_value_sha,
                expected_subject_identity_sha256=None,
                observed_subject_identity_sha256=None,
            ),
        ),
        scalar_expectations=(),
        order_expectations=(),
        semantic_receipts=receipts,
    )
    schema_bytes = _read_regular(root, Path(profile.output_schema_path))
    schema = StructuredOutputSchema(
        name="ai_opportunity_assessment_v1",
        uri=profile.output_schema_id,
        sha256=profile.output_schema_sha256,
        document_bytes=schema_bytes,
    )
    from datetime import datetime, timezone

    evaluated_at = datetime(2026, 8, 24, 0, 0, tzinfo=timezone.utc)
    value = AiOutputValidationInput(
        profile=profile,
        schema=schema,
        manifest=manifest,
        envelope=envelope,
        evaluated_at=evaluated_at,
    )
    report = evaluate_ai_output(value)
    if report.status.value != "LOCAL_VALIDATED":
        _fail()
    return _canonical_json(
        {
            "document": {
                "id": "RAOS-AI-OUTPUT-VALIDATION-PASS-001",
                "version": "1.0.0",
                "story_id": "ST-0705",
                "fixture_kind": "RECORDED_SYNTHETIC",
                "live_provider": False,
                "publication_authorized": False,
                "production_eligible": False,
            },
            "case": {
                "task_id": profile.task_id,
                "task_code": profile.task_code,
                "evaluated_at": evaluated_at.isoformat(),
                "output": output_document,
                "request_sha256": request_sha.value,
                "provider_exchange_sha256": exchange_sha.value,
                "output_sha256": envelope.output_sha256.value,
                "input_context_sha256": context_sha.value,
                "fact_id": fact_id,
                "fact_value_sha256": resource_value_sha.value,
                "semantic_receipts": [
                    {
                        "receipt_kind": item.receipt_kind.value,
                        "owner_story_id": item.owner_story_id,
                        "owner_contract_sha256": item.owner_contract_sha256.value,
                        "evidence_sha256": item.evidence_sha256.value,
                    }
                    for item in receipts
                ],
                "manifest_sha256": manifest.manifest_sha256.value,
            },
            "expected_report": json.loads(report.canonical_bytes()),
        }
    )


def render_outputs(
    contract: dict[str, object], root: Path = REPO_ROOT
) -> dict[Path, bytes]:
    _check_pins(root)
    toolchain = _toolchain()
    profiles = build_profiles(contract, root)
    registry = profile_registry_bytes(contract, root)
    fixture = _pass_fixture_bytes(contract, root)
    schema_paths = tuple(
        sorted({Path(profile.output_schema_path) for profile in profiles})
    )
    inventory_paths = tuple(dict.fromkeys((*RUNTIME_SOURCE_PATHS, *PINNED_INPUTS)))
    source_hashes = {
        path.as_posix(): _sha(_read_regular(root, path))
        for path in (*inventory_paths, *schema_paths)
    }
    generated_hashes = {
        PROFILE_REGISTRY_PATH.as_posix(): _sha(registry),
        PASS_FIXTURE_PATH.as_posix(): _sha(fixture),
    }
    manifest = yaml.safe_dump(
        {
            "document": {
                "id": "RAOS-ST0705-RUNTIME-MANIFEST-001",
                "version": "1.0.0",
                "story_id": "ST-0705",
                "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
                "authority": "NONE",
                "production_eligible": False,
            },
            "toolchain": toolchain,
            "source_sha256": source_hashes,
            "generated_sha256": generated_hashes,
            "profile_count": len(profiles),
            "schema_count": len(schema_paths),
            "local_status_vocabulary": [
                "LOCAL_VALIDATED",
                "BLOCKED",
                "UNEVALUABLE",
            ],
            "formal_tst_019": "NOT_EXECUTED",
            "formal_tst_020": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
        sort_keys=False,
        allow_unicode=True,
    ).encode("utf-8")
    return {
        PROFILE_REGISTRY_PATH: registry,
        PASS_FIXTURE_PATH: fixture,
        RUNTIME_MANIFEST_PATH: manifest,
    }


@dataclass(frozen=True, slots=True)
class _DirectoryBinding:
    descriptor: int
    identity: tuple[int, int, int]
    parent_descriptor: int | None = None
    name: str | None = None
    absolute_path: Path | None = None


@dataclass(slots=True)
class _StagedOutput:
    destination: Path
    descriptors: list[int]
    directory_bindings: list[_DirectoryBinding]
    parent_descriptor: int
    target_name: str
    temporary_name: str
    temporary_descriptor: int
    temporary_identity: tuple[int, ...]
    previous_identity: tuple[int, ...] | None
    commit_started: bool = False
    committed: bool = False


def _directory_identity(value: os.stat_result) -> tuple[int, int, int]:
    return (value.st_dev, value.st_ino, value.st_mode)


def _leaf_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
        value.st_nlink,
        value.st_size,
    )


_RENAME_NOREPLACE: Final = 1
_RENAME_EXCHANGE: Final = 2


def _renameat2(
    parent_descriptor: int, source: str, destination: str, flags: int
) -> None:
    if (
        type(parent_descriptor) is not int
        or parent_descriptor < 0
        or type(source) is not str
        or not source
        or "/" in source
        or "\x00" in source
        or type(destination) is not str
        or not destination
        or "/" in destination
        or "\x00" in destination
        or flags not in {_RENAME_NOREPLACE, _RENAME_EXCHANGE}
    ):
        _fail()
    try:
        function = ctypes.CDLL(None, use_errno=True).renameat2
        function.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        function.restype = ctypes.c_int
        result = function(
            parent_descriptor,
            os.fsencode(source),
            parent_descriptor,
            os.fsencode(destination),
            flags,
        )
    except AttributeError, OSError:
        _fail()
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number == errno.EEXIST:
            raise FileExistsError("ST0705_RENAME_DESTINATION_EXISTS") from None
        _fail()


def _rename_exchange(parent_descriptor: int, left: str, right: str) -> None:
    _renameat2(parent_descriptor, left, right, _RENAME_EXCHANGE)


def _rename_noreplace(parent_descriptor: int, source: str, destination: str) -> None:
    _renameat2(parent_descriptor, source, destination, _RENAME_NOREPLACE)


def _target_identity(parent_descriptor: int, name: str) -> tuple[int, ...] | None:
    try:
        value = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        _fail()
    return _leaf_identity(value)


def _validate_directories(bindings: tuple[_DirectoryBinding, ...]) -> None:
    for binding in reversed(bindings):
        opened = os.fstat(binding.descriptor)
        if binding.absolute_path is not None:
            named = binding.absolute_path.lstat()
        else:
            if binding.parent_descriptor is None or binding.name is None:
                _fail()
            named = os.stat(
                binding.name,
                dir_fd=binding.parent_descriptor,
                follow_symlinks=False,
            )
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(named.st_mode)
            or stat.S_ISLNK(named.st_mode)
            or _directory_identity(opened) != binding.identity
            or _directory_identity(named) != binding.identity
        ):
            _fail()


def _read_existing(parent_descriptor: int, name: str) -> tuple[int, ...] | None:
    identity = _target_identity(parent_descriptor, name)
    if identity is None:
        return None
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=parent_descriptor,
    )
    try:
        opened = os.fstat(descriptor)
        if _leaf_identity(opened) != identity or opened.st_size > MAX_SOURCE_BYTES:
            _fail()
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                _fail()
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail()
        if _leaf_identity(os.fstat(descriptor)) != identity:
            _fail()
        if _target_identity(parent_descriptor, name) != identity:
            _fail()
        return identity
    finally:
        os.close(descriptor)


def _create_staged_leaf(
    *,
    parent_descriptor: int,
    target_name: str,
    purpose: str,
    ordinal: int,
    payload: bytes,
    mode: int,
) -> tuple[str, int, tuple[int, ...]]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptor = -1
    name = ""
    for suffix in range(100):
        candidate = f".{target_name}.st0705-{purpose}-{os.getpid()}-{ordinal}-{suffix}"
        try:
            descriptor = os.open(
                candidate,
                flags,
                0o600,
                dir_fd=parent_descriptor,
            )
        except FileExistsError:
            continue
        name = candidate
        break
    if descriptor < 0 or not name:
        _fail()
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _fail()
            view = view[written:]
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
        opened = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        identity = _leaf_identity(opened)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_size != len(payload)
            or stat.S_IMODE(opened.st_mode) != mode
            or _leaf_identity(named) != identity
        ):
            _fail()
        return name, descriptor, identity
    except BaseException:
        try:
            if name and _target_identity(parent_descriptor, name) == _leaf_identity(
                os.fstat(descriptor)
            ):
                os.unlink(name, dir_fd=parent_descriptor)
                os.fsync(parent_descriptor)
        finally:
            os.close(descriptor)
        raise


def _open_output_parent(
    destination: Path,
) -> tuple[list[int], list[_DirectoryBinding], int]:
    absolute = Path(os.path.abspath(destination))
    if not absolute.is_absolute() or absolute.name != destination.name:
        _fail()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    filesystem_root = Path(absolute.anchor)
    root_before = filesystem_root.lstat()
    if not stat.S_ISDIR(root_before.st_mode) or stat.S_ISLNK(root_before.st_mode):
        _fail()
    descriptors: list[int] = []
    bindings: list[_DirectoryBinding] = []
    root_descriptor = os.open(filesystem_root, flags)
    descriptors.append(root_descriptor)
    root_identity = _directory_identity(root_before)
    if _directory_identity(os.fstat(root_descriptor)) != root_identity:
        _fail()
    bindings.append(
        _DirectoryBinding(
            descriptor=root_descriptor,
            identity=root_identity,
            absolute_path=filesystem_root,
        )
    )
    current = root_descriptor
    try:
        for part in absolute.parent.parts[1:]:
            before = os.stat(part, dir_fd=current, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
                _fail()
            child = os.open(part, flags, dir_fd=current)
            descriptors.append(child)
            identity = _directory_identity(before)
            if _directory_identity(os.fstat(child)) != identity:
                _fail()
            bindings.append(
                _DirectoryBinding(
                    descriptor=child,
                    identity=identity,
                    parent_descriptor=current,
                    name=part,
                )
            )
            current = child
        _validate_directories(tuple(bindings))
        return descriptors, bindings, current
    except BaseException:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def _stage_output(destination: Path, payload: bytes, ordinal: int) -> _StagedOutput:
    descriptors, bindings, parent_descriptor = _open_output_parent(destination)
    temporary_name = ""
    temporary_descriptor = -1
    try:
        previous_identity = _read_existing(parent_descriptor, destination.name)
        temporary_name, temporary_descriptor, temporary_identity = _create_staged_leaf(
            parent_descriptor=parent_descriptor,
            target_name=destination.name,
            purpose="new",
            ordinal=ordinal,
            payload=payload,
            mode=0o644,
        )
        _validate_directories(tuple(bindings))
        return _StagedOutput(
            destination=destination,
            descriptors=descriptors,
            directory_bindings=bindings,
            parent_descriptor=parent_descriptor,
            target_name=destination.name,
            temporary_name=temporary_name,
            temporary_descriptor=temporary_descriptor,
            temporary_identity=temporary_identity,
            previous_identity=previous_identity,
        )
    except BaseException:
        cleanup_failed = False
        if temporary_name and temporary_descriptor >= 0:
            try:
                if _target_identity(
                    parent_descriptor, temporary_name
                ) == _leaf_identity(os.fstat(temporary_descriptor)):
                    os.unlink(temporary_name, dir_fd=parent_descriptor)
            except BaseException:
                cleanup_failed = True
            try:
                os.close(temporary_descriptor)
            except BaseException:
                cleanup_failed = True
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except BaseException:
                cleanup_failed = True
        if cleanup_failed:
            _fail()
        raise


def _named_identity(stage: _StagedOutput, name: str) -> tuple[int, ...] | None:
    return _target_identity(stage.parent_descriptor, name)


def _named_raw_identity(stage: _StagedOutput, name: str) -> tuple[int, ...] | None:
    try:
        value = os.stat(name, dir_fd=stage.parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(value.st_mode):
        _fail()
    return _leaf_identity(value)


def _same_inode_material(left: tuple[int, ...], right: tuple[int, ...]) -> bool:
    return left[:5] == right[:5] and left[6:] == right[6:]


def _move_target_noreplace(stage: _StagedOutput, purpose: str) -> str:
    for suffix in range(100):
        destination = f".{stage.target_name}.st0705-{purpose}-{os.getpid()}-{suffix}"
        try:
            _rename_noreplace(
                stage.parent_descriptor,
                stage.target_name,
                destination,
            )
        except FileExistsError:
            continue
        return destination
    _fail()


def _rollback_stage(stage: _StagedOutput) -> None:
    current = _named_raw_identity(stage, stage.target_name)
    if current == stage.previous_identity:
        return
    if stage.previous_identity is not None:
        if current is None or not _same_inode_material(
            current, stage.temporary_identity
        ):
            _fail()
        displaced = _named_raw_identity(stage, stage.temporary_name)
        if displaced is None:
            _fail()
        _rename_exchange(
            stage.parent_descriptor,
            stage.target_name,
            stage.temporary_name,
        )
        if (
            _named_raw_identity(stage, stage.target_name) != displaced
            or _named_raw_identity(stage, stage.temporary_name) != current
        ):
            _fail()
        os.fsync(stage.parent_descriptor)
        return
    if current is None:
        return
    if not _same_inode_material(current, stage.temporary_identity):
        # A no-clobber install cannot own an unrelated target. Preserve it.
        return
    rollback_name = _move_target_noreplace(stage, "rollback")
    moved = _named_raw_identity(stage, rollback_name)
    if moved is None or not _same_inode_material(moved, stage.temporary_identity):
        if moved is not None:
            _rename_noreplace(
                stage.parent_descriptor,
                rollback_name,
                stage.target_name,
            )
        _fail()
    os.unlink(rollback_name, dir_fd=stage.parent_descriptor)
    os.fsync(stage.parent_descriptor)
    if _named_raw_identity(stage, stage.target_name) is not None:
        _fail()


def _cleanup_named_leaf(
    stage: _StagedOutput, name: str | None, identity: tuple[int, ...] | None
) -> None:
    if name is None:
        return
    current = _named_identity(stage, name)
    if current is None:
        return
    if identity is None or current != identity:
        _fail()
    os.unlink(name, dir_fd=stage.parent_descriptor)
    os.fsync(stage.parent_descriptor)


def _close_stage(stage: _StagedOutput) -> None:
    os.close(stage.temporary_descriptor)
    for descriptor in reversed(stage.descriptors):
        os.close(descriptor)


def _commit_stage(stage: _StagedOutput) -> None:
    stage.commit_started = True
    if stage.previous_identity is not None:
        _rename_exchange(
            stage.parent_descriptor,
            stage.temporary_name,
            stage.target_name,
        )
        target = _named_raw_identity(stage, stage.target_name)
        displaced = _named_raw_identity(stage, stage.temporary_name)
        if (
            target is None
            or displaced is None
            or not _same_inode_material(target, stage.temporary_identity)
            or displaced != stage.previous_identity
        ):
            # Exchange back atomically. Whatever raced into the target is
            # restored rather than overwritten or deleted.
            _rename_exchange(
                stage.parent_descriptor,
                stage.temporary_name,
                stage.target_name,
            )
            os.fsync(stage.parent_descriptor)
            if (
                _named_raw_identity(stage, stage.target_name) != displaced
                or _named_raw_identity(stage, stage.temporary_name) != target
            ):
                _fail()
            _fail()
    else:
        os.link(
            stage.temporary_name,
            stage.target_name,
            src_dir_fd=stage.parent_descriptor,
            dst_dir_fd=stage.parent_descriptor,
            follow_symlinks=False,
        )
        target = _named_raw_identity(stage, stage.target_name)
        temporary = _named_raw_identity(stage, stage.temporary_name)
        if (
            target is None
            or temporary is None
            or target != temporary
            or target[5] != 2
            or not _same_inode_material(target, stage.temporary_identity)
        ):
            _fail()
        os.unlink(stage.temporary_name, dir_fd=stage.parent_descriptor)
        stage.temporary_name = ""
        if _named_identity(stage, stage.target_name) != stage.temporary_identity:
            _fail()
    os.fsync(stage.parent_descriptor)
    stage.committed = True


def _replace_generated(artifacts: tuple[tuple[Path, bytes], ...]) -> None:
    if (
        not artifacts
        or any(
            not isinstance(path, Path)
            or not path.is_absolute()
            or type(payload) is not bytes
            or not payload
            or len(payload) > MAX_SOURCE_BYTES
            for path, payload in artifacts
        )
        or len({path for path, _payload in artifacts}) != len(artifacts)
    ):
        _fail()
    stages: list[_StagedOutput] = []
    primary: BaseException | None = None
    commits_complete = False
    try:
        for ordinal, (destination, payload) in enumerate(artifacts):
            stages.append(_stage_output(destination, payload, ordinal))
        for stage in stages:
            _validate_directories(tuple(stage.directory_bindings))
            if _named_identity(stage, stage.target_name) != stage.previous_identity:
                _fail()
            if _named_identity(stage, stage.temporary_name) != stage.temporary_identity:
                _fail()
            _commit_stage(stage)
            if _named_identity(stage, stage.target_name) != stage.temporary_identity:
                _fail()
            _validate_directories(tuple(stage.directory_bindings))
        commits_complete = True
        for stage in stages:
            if stage.previous_identity is not None:
                _cleanup_named_leaf(
                    stage,
                    stage.temporary_name,
                    stage.previous_identity,
                )
                stage.temporary_name = ""
    except BaseException as failure:
        primary = failure
        if commits_complete:
            if isinstance(failure, Exception):
                _fail()
            raise
        rollback_failed = False
        for stage in reversed(stages):
            if not stage.commit_started:
                continue
            try:
                _rollback_stage(stage)
            except BaseException:
                rollback_failed = True
        if rollback_failed:
            _fail()
        if isinstance(failure, Exception):
            _fail()
        raise
    finally:
        cleanup_failed = False
        for stage in stages:
            try:
                _cleanup_named_leaf(
                    stage,
                    stage.temporary_name or None,
                    stage.temporary_identity,
                )
            except BaseException:
                cleanup_failed = True
            try:
                _close_stage(stage)
            except BaseException:
                cleanup_failed = True
        if cleanup_failed and primary is None:
            _fail()


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    contract = load_contract(root)
    outputs = render_outputs(contract, root)
    if check:
        for relative, expected in outputs.items():
            try:
                observed = _read_regular(root, relative)
            except St0705BuildError:
                _fail()
            if observed != expected:
                _fail()
        return
    _replace_generated(
        tuple(
            (_repository_path(root, relative), payload)
            for relative, payload in outputs.items()
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--print-trust-anchors", action="store_true")
    arguments = parser.parse_args()
    try:
        contract = load_contract()
        if arguments.print_trust_anchors:
            print(json.dumps(trust_anchors(contract), sort_keys=True))
        else:
            build(check=arguments.check)
    except St0705BuildError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
