#!/usr/bin/env python3
# ST-0708 owner generator; generated artifacts must not be hand-edited.
"""Build the historical plan and the recorded-only ST-0708 V2 runtime."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Mapping, Sequence
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Final, NoReturn, cast

import yaml
from yaml.tokens import AliasToken, AnchorToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPO_ROOT / "python"
for _import_root in (REPO_ROOT, PYTHON_ROOT):
    if str(_import_root) not in sys.path:
        sys.path.insert(0, str(_import_root))

from raos.domain.ai.live_evaluation import (  # noqa: E402
    EvidenceStatus,
    RecordedCandidateBinding,
    RecordedHarnessReportBinding,
    RecordedLiveEvaluationRequest,
    RecordedLiveEvaluationResult,
    RiskThreshold,
    canonical_json_bytes,
    evaluate_recorded_live_evidence,
    evidence_projection,
    finalize_candidate_binding,
    finalize_evidence,
    finalize_request,
    report_projection,
)
from scripts import secure_generated_publication as _publication  # noqa: E402


REFERENCE_CONTRACT_PATH: Final = Path(
    "changes/st-0708/contracts/openai-live-bounded-evaluation-reference-plan.v1.yaml"
)
CONTRACT_PATH: Final = REFERENCE_CONTRACT_PATH  # historical public alias
RUNTIME_CONTRACT_PATH: Final = Path(
    "changes/st-0708/contracts/recorded-live-evaluation-runtime.v2.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0708/generated/openai-live-bounded-evaluation-reference-plan.v1.json"
)
REQUEST_PATH: Final = Path(
    "changes/st-0708/generated/recorded-live-evaluation-request.v2.json"
)
REPORT_PATH: Final = Path(
    "changes/st-0708/generated/recorded-live-evaluation-report.v2.json"
)
RUNTIME_MANIFEST_PATH: Final = Path("changes/st-0708/runtime-manifest.v2.json")
MANIFEST_PATH: Final = Path("changes/st-0708/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st0708_openai_live_bounded_evaluation_reference_plan.py"
)
HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
HELPER_SHA256: Final = (
    "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e"
)
CONTRACT_SHA256: Final = (
    "4252b0dd7c92a494b281ca406183b593b5d8ea6fb8b1f54d57c3d73efc6a1f65"
)
RUNTIME_CONTRACT_SHA256: Final = (
    "e8b2607955b3e5de9dad1b50bb028710e49e71af8bd40805ee2ef46fa50946af"
)
BASE_COMMIT: Final = "71c709844d625ee26026b2ba8555a16fa351b982"
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
METRIC_SCALE: Final = 1_000_000
GENERATED_PATHS: Final = (
    REFERENCE_PLAN_PATH,
    REQUEST_PATH,
    REPORT_PATH,
    RUNTIME_MANIFEST_PATH,
    MANIFEST_PATH,
)
CONTRACT_KEYS: Final = (
    "document",
    "authority",
    "story",
    "dependencies",
    "open_decision",
    "candidate_selection",
    "dataset_boundary",
    "thresholds",
    "execution_configuration",
    "observations",
    "verification_boundary",
    "activation_boundary",
    "command_surface",
)
ACTION_COUNT_KEYS: Final = (
    "provider_call",
    "network",
    "credential_read",
    "filesystem_write",
    "repository_write",
    "database_write",
    "job_dispatch",
    "event_publish",
    "retry",
    "create",
    "update",
    "delete",
    "approve",
    "release",
    "external",
)


class OpenAiLiveBoundedEvaluationReferenceError(RuntimeError):
    """Stable sanitized ST-0708 build failure."""

    __slots__ = ("code",)

    def __init__(self, code: str = "ST0708_BUILD_FAILED") -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str = "ST0708_BUILD_FAILED") -> NoReturn:
    raise OpenAiLiveBoundedEvaluationReferenceError(code) from None


def _sha256(content: bytes) -> str:
    if type(content) is not bytes:
        _fail()
    return hashlib.sha256(content).hexdigest()


def _repository_path(root: Path, relative: Path) -> Path:
    if (
        not isinstance(root, Path)
        or not isinstance(relative, Path)
        or relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("FILE_BOUNDARY_VIOLATION")
    absolute_root = Path(os.path.abspath(root))
    candidate = Path(os.path.abspath(absolute_root / relative))
    try:
        candidate.relative_to(absolute_root)
    except ValueError:
        _fail("FILE_BOUNDARY_VIOLATION")
    return candidate


def _read(root: Path, relative: Path) -> bytes:
    path = _repository_path(root, relative)
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_SOURCE_BYTES
        ):
            _fail("FILE_BOUNDARY_VIOLATION")
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
            ):
                _fail("FILE_BOUNDARY_VIOLATION")
            chunks: list[bytes] = []
            remaining = opened.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    _fail("FILE_BOUNDARY_VIOLATION")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                _fail("FILE_BOUNDARY_VIOLATION")
            after = os.fstat(descriptor)
            named = path.lstat()
            if (after.st_dev, after.st_ino, after.st_size) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
            ) or (named.st_dev, named.st_ino, named.st_size) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
            ):
                _fail("FILE_BOUNDARY_VIOLATION")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except OpenAiLiveBoundedEvaluationReferenceError:
        raise
    except Exception:
        _fail("FILE_BOUNDARY_VIOLATION")


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueSafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key == "<<" or key in result:
            _fail("SOURCE_PARSE_FAILED")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _mapping(value: object) -> dict[str, Any]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        _fail("TYPE_MISMATCH")
    return cast(dict[str, Any], value)


def _rows(value: object, maximum: int = 256) -> list[dict[str, Any]]:
    if type(value) is not list or len(value) > maximum:
        _fail("TYPE_MISMATCH")
    return [_mapping(row) for row in cast(list[object], value)]


def _string(value: object, maximum: int = 512) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        _fail("TYPE_MISMATCH")
    return value


def _integer(value: object, maximum: int = 10_000_000) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        _fail("TYPE_MISMATCH")
    return value


def _parse_yaml_bytes(content: bytes, *, allow_aliases: bool = False) -> dict[str, Any]:
    if type(content) is not bytes or not 1 <= len(content) <= MAX_SOURCE_BYTES:
        _fail("SOURCE_PARSE_FAILED")
    try:
        text = content.decode("utf-8", errors="strict")
        for token in yaml.scan(text):
            if not allow_aliases and isinstance(token, (AliasToken, AnchorToken)):
                _fail("SOURCE_PARSE_FAILED")
        parsed = yaml.load(text, Loader=_UniqueSafeLoader)
    except OpenAiLiveBoundedEvaluationReferenceError:
        raise
    except Exception:
        _fail("SOURCE_PARSE_FAILED")
    return _mapping(parsed)


def _parse_json_bytes(content: bytes) -> dict[str, Any]:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                _fail("SOURCE_PARSE_FAILED")
            result[key] = value
        return result

    def reject_float(value: str) -> NoReturn:
        del value
        _fail("SOURCE_PARSE_FAILED")

    try:
        parsed = json.loads(
            content,
            object_pairs_hook=pairs,
            parse_float=reject_float,
            parse_constant=reject_float,
        )
    except OpenAiLiveBoundedEvaluationReferenceError:
        raise
    except Exception:
        _fail("SOURCE_PARSE_FAILED")
    return _mapping(parsed)


def _find(rows: object, identity: str, key: str = "id") -> dict[str, Any]:
    matches = [row for row in _rows(rows) if row.get(key) == identity]
    if len(matches) != 1:
        _fail("SOURCE_RECORD_DRIFT")
    return matches[0]


def _parse_reference_contract(root: Path) -> dict[str, Any]:
    content = _read(root, REFERENCE_CONTRACT_PATH)
    if _sha256(content) != CONTRACT_SHA256:
        _fail("CONTRACT_BYTE_DRIFT")
    return _parse_yaml_bytes(content)


def validate_contract(contract: Mapping[str, Any]) -> None:
    if tuple(contract) != CONTRACT_KEYS or dict(contract) != _parse_reference_contract(
        REPO_ROOT
    ):
        _fail("CONTRACT_BOUNDARY_VIOLATION")
    document = _mapping(contract["document"])
    decision = _mapping(contract["open_decision"])
    activation = _mapping(contract["activation_boundary"])
    counts = _mapping(activation["action_counts"])
    if (
        document.get("executable") is not False
        or document.get("interface_only") is not True
        or document.get("runtime_eligible") is not False
        or document.get("decision") != "NOT_READY"
        or decision.get("safe_default") != "RECORDED_FIXTURE_ONLY"
        or decision.get("resolved") is not False
        or activation.get("external_actions") != []
        or tuple(counts) != ACTION_COUNT_KEYS
        or any(type(value) is not int or value != 0 for value in counts.values())
    ):
        _fail("SAFE_BOUNDARY_VIOLATION")


def load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    contract = _parse_reference_contract(root)
    if tuple(contract) != CONTRACT_KEYS or contract != _parse_reference_contract(
        REPO_ROOT
    ):
        _fail("CONTRACT_BOUNDARY_VIOLATION")
    return contract


def reference_plan(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> dict[str, Any]:
    del root
    validate_contract(contract)
    try:
        return cast(
            dict[str, Any],
            json.loads(json.dumps(contract, allow_nan=False, ensure_ascii=False)),
        )
    except Exception:
        _fail("JSON_RENDER_FAILED")


def _runtime_contract(root: Path) -> dict[str, Any]:
    content = _read(root, RUNTIME_CONTRACT_PATH)
    if _sha256(content) != RUNTIME_CONTRACT_SHA256:
        _fail("RUNTIME_CONTRACT_BYTE_DRIFT")
    contract = _parse_yaml_bytes(content)
    expected_keys = frozenset(
        {
            "canonical_sources",
            "document",
            "outputs",
            "owned_sources",
            "runtime_policy",
            "st0703_recorded_binding",
            "st0707_report_binding",
            "target_suite",
        }
    )
    document = _mapping(contract.get("document"))
    if frozenset(contract) != expected_keys or document != {
        "id": "RAOS-ST0708-RECORDED-LIVE-EVALUATION-RUNTIME-002",
        "version": "2.0.0",
        "story_id": "ST-0708",
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "authority": "NONE",
        "default_enabled": False,
        "provider_mode": "RECORDED_SYNTHETIC_ONLY",
        "live_provider_allowed": False,
        "credentials_allowed": False,
        "network_allowed": False,
        "route_mutation_allowed": False,
        "activation_allowed": False,
        "approval_allowed": False,
        "publication_allowed": False,
        "release_authorized": False,
        "production_eligible": False,
    }:
        _fail("RUNTIME_CONTRACT_BOUNDARY_VIOLATION")
    policy = _mapping(contract["runtime_policy"])
    if (
        policy.get("unavailable_is_pass") is not False
        or policy.get("unknown_is_zero") is not False
        or policy.get("insufficient_is_pass") is not False
        or policy.get("zero_tolerance_waiver_allowed") is not False
        or policy.get("synthetic_release_eligible") is not False
        or policy.get("external_actions") is not False
        or policy.get("formal_tst_018") != "NOT_EXECUTED"
        or policy.get("od_015") != "EXTERNAL_EVIDENCE_REQUIRED"
    ):
        _fail("RUNTIME_CONTRACT_BOUNDARY_VIOLATION")
    return contract


def _declared_file(root: Path, raw: object) -> tuple[Path, bytes, str]:
    binding = _mapping(raw)
    if frozenset(binding) != frozenset({"path", "sha256"}):
        _fail("BINDING_INVALID")
    path = Path(_string(binding["path"]))
    expected = _string(binding["sha256"], 64)
    content = _read(root, path)
    if _sha256(content) != expected:
        _fail("PINNED_INPUT_DRIFT")
    return path, content, expected


def _inputs(root: Path, contract: dict[str, Any]) -> dict[str, tuple[Path, bytes, str]]:
    result: dict[str, tuple[Path, bytes, str]] = {}
    for name, raw in _mapping(contract["canonical_sources"]).items():
        result[name] = _declared_file(root, raw)
    st0703 = _mapping(contract["st0703_recorded_binding"])
    for name in (
        "adapter_contract",
        "fixture_registry",
        "success_fixture",
        "binding_source",
    ):
        result[f"st0703_{name}"] = _declared_file(root, st0703[name])
    st0707 = _mapping(contract["st0707_report_binding"])
    for name in (
        "runtime_contract",
        "runtime_manifest",
        "suite_registry",
        "locked_dataset",
        "st0705_runtime_contract",
        "st0705_profile_registry",
        "st0705_fixture",
        "st0705_runtime_manifest",
        "task_schema",
        "evaluation_case_schema",
    ):
        result[f"st0707_{name}"] = _declared_file(root, st0707[name])
    if _sha256(_read(root, HELPER_PATH)) != HELPER_SHA256:
        _fail("HELPER_DRIFT")
    return result


def _verify_authority(inputs: dict[str, tuple[Path, bytes, str]]) -> None:
    story = _find(
        _parse_yaml_bytes(inputs["story_catalog"][1]).get("stories"), "ST-0708"
    )
    if (
        story.get("depends_on") != ["ST-0707", "ST-0703"]
        or story.get("acceptance_criteria") != ["risk-specific thresholds"]
        or story.get("test_suites") != ["TST-018"]
        or story.get("open_decisions") != ["OD-015"]
        or story.get("design_status") != "APPROVED_FOR_IMPLEMENTATION"
        or story.get("implementation_status") != "NOT_STARTED"
        or story.get("verification_status") != "NOT_EXECUTED"
    ):
        _fail("STORY_SEMANTIC_DRIFT")
    decision = _find(
        _parse_yaml_bytes(inputs["open_decisions"][1]).get("items"), "OD-015"
    )
    if (
        decision.get("status") != "EXTERNAL_EVIDENCE_REQUIRED"
        or decision.get("default_behavior") != "Recorded fixtureのみ"
        or decision.get("blocking") is not True
    ):
        _fail("OPEN_DECISION_SEMANTIC_DRIFT")
    test = _find(_parse_yaml_bytes(inputs["test_catalog"][1]).get("suites"), "TST-018")
    if (
        test.get("environments") != ["staging"]
        or test.get("release_blocking") is not True
        or test.get("execution_status") != "NOT_EXECUTED"
    ):
        _fail("TEST_SUITE_SEMANTIC_DRIFT")


def _call_keywords(
    tree: ast.Module, function_name: str, call_name: str
) -> dict[str, str]:
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    ]
    if len(functions) != 1:
        _fail("ST0703_BINDING_DRIFT")
    calls = [
        node
        for node in ast.walk(functions[0])
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name)
            and node.func.id == call_name
            or isinstance(node.func, ast.Attribute)
            and node.func.attr == call_name
        )
    ]
    if len(calls) != 1:
        _fail("ST0703_BINDING_DRIFT")
    result: dict[str, str] = {}
    for keyword in calls[0].keywords:
        if keyword.arg is not None and isinstance(keyword.value, ast.Constant):
            if type(keyword.value.value) is str:
                result[keyword.arg] = keyword.value.value
    return result


def _verify_st0703(
    contract: dict[str, Any], inputs: dict[str, tuple[Path, bytes, str]]
) -> None:
    expected = _mapping(contract["st0703_recorded_binding"])
    try:
        tree = ast.parse(
            inputs["st0703_binding_source"][1].decode("utf-8", errors="strict")
        )
    except Exception:
        _fail("ST0703_BINDING_DRIFT")
    route = _call_keywords(tree, "_route", "OpenAIResponseRoute")
    request = _call_keywords(tree, "_request", "StructuredTaskRequest")
    quote = _call_keywords(tree, "_quote", "SyntheticPricingQuote")
    if (
        route.get("route_version") != expected.get("route_version")
        or route.get("model_id") != expected.get("model_id")
        or request.get("task_code") != expected.get("recorded_task_id")
        or request.get("model_route_version") != expected.get("route_version")
        or request.get("prompt_version") != expected.get("prompt_version")
        or quote.get("model_id") != expected.get("model_id")
    ):
        _fail("ST0703_BINDING_DRIFT")
    fixture = _parse_json_bytes(inputs["st0703_success_fixture"][1])
    expected_request = _mapping(fixture.get("expected_request"))
    pricing = _mapping(fixture.get("pricing"))
    body = _mapping(_mapping(fixture.get("transport")).get("body"))
    if (
        fixture.get("synthetic") != "SYNTHETIC_TEST_ONLY"
        or expected_request.get("model") != expected.get("model_id")
        or expected_request.get("store") is not False
        or expected_request.get("tools") != []
        or pricing.get("model_id") != expected.get("model_id")
        or body.get("model") != expected.get("model_id")
        or body.get("store") is not False
        or body.get("tools") != []
    ):
        _fail("ST0703_FIXTURE_DRIFT")
    registry = _parse_json_bytes(inputs["st0703_fixture_registry"][1])
    row = _find(registry.get("fixtures"), "success-structured.json", "path")
    if row.get("sha256") != inputs["st0703_success_fixture"][2]:
        _fail("ST0703_FIXTURE_DRIFT")
    adapter_contract = _parse_yaml_bytes(inputs["st0703_adapter_contract"][1])
    authority = _mapping(adapter_contract.get("implementation_authority"))
    boundary = _mapping(adapter_contract.get("boundary"))
    if (
        authority.get("authority") != "ST0703_RECORDED_SCOPE_ONLY"
        or boundary.get("live_api") != "NOT_USED"
        or boundary.get("credential_or_secret_resolution") != "NOT_USED"
        or boundary.get("live_tst_018") != "NOT_EXECUTED"
        or boundary.get("production_readiness") != "NOT_READY"
    ):
        _fail("ST0703_BOUNDARY_DRIFT")


def _threshold_micros(value: object) -> int:
    if type(value) not in {int, float}:
        _fail("THRESHOLD_DRIFT")
    try:
        scaled = Decimal(str(value)) * Decimal(METRIC_SCALE)
    except Exception:
        _fail("THRESHOLD_DRIFT")
    integral = scaled.to_integral_value()
    if scaled != integral or not 0 <= integral <= 5 * METRIC_SCALE:
        _fail("THRESHOLD_DRIFT")
    return int(integral)


def _target_thresholds(
    contract: dict[str, Any], inputs: dict[str, tuple[Path, bytes, str]]
) -> tuple[tuple[RiskThreshold, ...], tuple[str, ...]]:
    target = _mapping(contract["target_suite"])
    task = _find(
        _parse_yaml_bytes(inputs["task_catalog"][1], allow_aliases=True).get("tasks"),
        _string(target["task_id"]),
    )
    if (
        task.get("task_code") != target.get("task_code")
        or task.get("risk_level") != target.get("risk_level")
        or task.get("route_code") != "route.editorial_balanced.v1"
        or task.get("prompt_code") != "PROMPT-AI-ARTICLE-DRAFT"
        or task.get("can_change_state") is not False
        or task.get("tools_allowed") is not False
        or task.get("network_access") is not False
    ):
        _fail("TARGET_TASK_DRIFT")
    route = _find(
        _parse_yaml_bytes(inputs["routing_catalog"][1]).get("routes"),
        "route.editorial_balanced.v1",
        "route_code",
    )
    if (
        route.get("store") is not False
        or route.get("strict_structured_output") is not True
        or route.get("minimum_eval_status") != "CERTIFIED"
    ):
        _fail("TARGET_ROUTE_DRIFT")
    catalog = _parse_yaml_bytes(inputs["evaluation_catalog"][1], allow_aliases=True)
    suite = _find(catalog.get("suites"), _string(target["suite_code"]), "suite_code")
    if (
        suite.get("task_code") != target.get("task_code")
        or suite.get("risk_level") != target.get("risk_level")
        or suite.get("minimum_adjudicated_cases")
        != target.get("minimum_adjudicated_cases")
        or suite.get("required_splits") != target.get("required_splits")
        or suite.get("promotion_policy") != target.get("expected_promotion_policy")
    ):
        _fail("TARGET_SUITE_DRIFT")
    metrics = {
        _string(item.get("code")): item for item in _rows(catalog.get("metrics"), 128)
    }
    raw_thresholds = _mapping(suite.get("thresholds"))
    thresholds: list[RiskThreshold] = []
    for code in sorted(raw_thresholds):
        definition = metrics.get(code)
        raw = _mapping(raw_thresholds[code])
        if definition is None or frozenset(raw) != frozenset({"operator", "value"}):
            _fail("THRESHOLD_DRIFT")
        threshold = RiskThreshold(
            code=code,
            kind=_string(definition.get("kind")),
            direction=_string(definition.get("direction")),
            unit=_string(definition.get("unit")),
            operator=_string(raw.get("operator")),
            threshold_micros=_threshold_micros(raw.get("value")),
        )
        threshold.require_valid()
        thresholds.append(threshold)
    zero = tuple(
        sorted(_string(item, 200) for item in suite["zero_tolerance_failures"])
    )
    if len(zero) != 8 or len(set(zero)) != 8:
        _fail("ZERO_TOLERANCE_DRIFT")
    return tuple(thresholds), zero


def _build_evidence(
    contract: dict[str, Any], inputs: dict[str, tuple[Path, bytes, str]]
) -> RecordedLiveEvaluationResult:
    _verify_authority(inputs)
    _verify_st0703(contract, inputs)
    thresholds, zero = _target_thresholds(contract, inputs)
    st0703 = _mapping(contract["st0703_recorded_binding"])
    candidate = finalize_candidate_binding(
        RecordedCandidateBinding(
            recorded_task_id=_string(st0703["recorded_task_id"]),
            target_task_code=_string(st0703["target_task_code"]),
            route_version=_string(st0703["route_version"]),
            prompt_version=_string(st0703["prompt_version"]),
            model_id=_string(st0703["model_id"]),
            provenance=_string(st0703["provenance"]),
            adapter_contract_sha256=inputs["st0703_adapter_contract"][2],
            fixture_registry_sha256=inputs["st0703_fixture_registry"][2],
            success_fixture_sha256=inputs["st0703_success_fixture"][2],
            binding_source_sha256=inputs["st0703_binding_source"][2],
            canonical_route_selected=bool(st0703["canonical_route_selected"]),
            canonical_model_selected=bool(st0703["canonical_model_selected"]),
            canonical_prompt_selected=bool(st0703["canonical_prompt_selected"]),
            live_binding=bool(st0703["live_binding"]),
            binding_sha256="0" * 64,
        )
    )
    policy = _mapping(contract["runtime_policy"])
    request = finalize_request(
        RecordedLiveEvaluationRequest(
            evaluation_id=_string(policy["evaluation_id"]),
            runtime_contract_sha256=RUNTIME_CONTRACT_SHA256,
            request_sha256="0" * 64,
        )
    )
    st0707 = _mapping(contract["st0707_report_binding"])
    source_report = RecordedHarnessReportBinding(
        source_task_code=_string(st0707["source_task_code"]),
        suite_code=_string(st0707["suite_code"]),
        bundle_sha256=_string(st0707["bundle_sha256"], 64),
        report_sha256=_string(st0707["report_sha256"], 64),
        report_outcome=_string(st0707["report_outcome"]),
        dataset_sha256=_string(st0707["dataset_sha256"], 64),
        holdout_sha256=_string(st0707["holdout_sha256"], 64),
        observed_case_count=_integer(st0707["observed_case_count"], 10_000),
        observed_splits=tuple(
            sorted(
                _string(item) for item in cast(list[object], st0707["observed_splits"])
            )
        ),
        dataset_provenance=_string(st0707["dataset_provenance"]),
        human_label_status=EvidenceStatus(_string(st0707["human_label_status"])),
        release_eligible=bool(st0707["release_eligible"]),
    )
    source_report.require_valid()
    target = _mapping(contract["target_suite"])
    return finalize_evidence(
        RecordedLiveEvaluationResult(
            request=request,
            candidate=candidate,
            source_report=source_report,
            target_suite_code=_string(target["suite_code"]),
            target_task_code=_string(target["task_code"]),
            risk_level=_string(target["risk_level"]),
            minimum_adjudicated_cases=_integer(
                target["minimum_adjudicated_cases"], 10_000
            ),
            required_splits=tuple(
                _string(item) for item in cast(list[object], target["required_splits"])
            ),
            thresholds=thresholds,
            zero_tolerance_classes=zero,
            metric_observations=(),
            zero_tolerance_observations=(),
            st0703_binding_verified=True,
            st0707_report_verified=True,
            formal_tst_018_executed=False,
            od_015_resolved=False,
            evidence_sha256="0" * 64,
        )
    )


def _canonical_output(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _json_bytes(value: object) -> bytes:
    """Historical reference-plan serializer retained for compatibility."""

    try:
        return (
            json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        ).encode("utf-8", errors="strict")
    except Exception:
        _fail("JSON_RENDER_FAILED")


def _source_hashes(
    root: Path,
    contract: dict[str, Any],
    inputs: dict[str, tuple[Path, bytes, str]],
) -> dict[str, str]:
    paths = {RUNTIME_CONTRACT_PATH, *(item[0] for item in inputs.values())}
    paths.update(
        Path(_string(item)) for item in cast(list[object], contract["owned_sources"])
    )
    return {
        path.as_posix(): _sha256(_read(root, path))
        for path in sorted(paths, key=lambda item: item.as_posix())
    }


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative)
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(
    generated: Mapping[Path, bytes], sources: Mapping[str, str]
) -> bytes:
    manifest = {
        "document": {
            "authority": "NONE",
            "id": "RAOS-ST0708-RECORDED-LIVE-EVALUATION-MANIFEST-002",
            "production_eligible": False,
            "status": "LOCAL_IMPLEMENTATION_COMPLETE",
            "story_id": "ST-0708",
            "version": "2.0.0",
        },
        "provenance": {
            "base_commit": BASE_COMMIT,
            "runtime_contract_sha256": RUNTIME_CONTRACT_SHA256,
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "source_artifact_count": len(sources),
        "source_sha256": dict(sources),
        "generated_artifact_count": len(generated),
        "generated_artifacts": [
            {
                "uri": f"repo://{path.as_posix()}",
                "bytes": len(payload),
                "sha256": _sha256(payload),
            }
            for path, payload in generated.items()
        ],
        "boundary": {
            "classification": "RECORDED_SYNTHETIC_ONLY_RELEASE_DECISION_PROPOSAL",
            "default_enabled": False,
            "provider_called": False,
            "network_used": False,
            "credential_read": False,
            "route_mutated": False,
            "activation_allowed": False,
            "approval_allowed": False,
            "publication_allowed": False,
            "release_authorized": False,
            "production_eligible": False,
            "od_015": "EXTERNAL_EVIDENCE_REQUIRED",
            "formal_tst_018": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    try:
        return yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False).encode(
            "utf-8", errors="strict"
        )
    except Exception:
        _fail("MANIFEST_RENDER_FAILED")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    reference = _json_bytes(reference_plan(load_contract(root)))
    contract = _runtime_contract(root)
    inputs = _inputs(root, contract)
    evidence = _build_evidence(contract, inputs)
    report = evaluate_recorded_live_evidence(evidence)
    request_bytes = _canonical_output(
        {
            "document": {
                "authority": "NONE",
                "default_enabled": False,
                "id": "RAOS-ST0708-RECORDED-LIVE-EVALUATION-REQUEST-002",
                "live_provider": False,
                "production_eligible": False,
                "release_authorized": False,
                "status": "LOCAL_IMPLEMENTATION_COMPLETE",
                "story_id": "ST-0708",
                "version": "2.0.0",
            },
            "evidence": evidence_projection(evidence),
            "evidence_sha256": evidence.evidence_sha256,
        }
    )
    report_bytes = _canonical_output(
        {
            "document": {
                "authority": "NONE",
                "id": "RAOS-ST0708-RECORDED-LIVE-EVALUATION-REPORT-002",
                "production_eligible": False,
                "release_authorized": False,
                "status": "LOCAL_IMPLEMENTATION_COMPLETE",
                "story_id": "ST-0708",
                "version": "2.0.0",
            },
            "formal_status": {
                "formal_tst_018": "NOT_EXECUTED",
                "live": "NOT_EXECUTED",
                "production": "NOT_EXECUTED",
                "release": "NOT_EXECUTED",
                "staging": "NOT_EXECUTED",
            },
            "report": report_projection(report)
            | {"report_sha256": report.report_sha256},
        }
    )
    sources = _source_hashes(root, contract, inputs)
    runtime_manifest_material = {
        "document": {
            "authority": "NONE",
            "id": "RAOS-ST0708-RUNTIME-MANIFEST-002",
            "production_eligible": False,
            "status": "LOCAL_IMPLEMENTATION_COMPLETE",
            "story_id": "ST-0708",
            "version": "2.0.0",
        },
        "formal_status": {
            "formal_tst_018": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
        },
        "generated_sha256": {
            REFERENCE_PLAN_PATH.as_posix(): _sha256(reference),
            REQUEST_PATH.as_posix(): _sha256(request_bytes),
            REPORT_PATH.as_posix(): _sha256(report_bytes),
        },
        "helper": {
            "path": HELPER_PATH.as_posix(),
            "sha256": HELPER_SHA256,
        },
        "source_sha256": sources,
    }
    runtime_manifest = _canonical_output(
        runtime_manifest_material
        | {"manifest_sha256": _sha256(canonical_json_bytes(runtime_manifest_material))}
    )
    without_owner_manifest: dict[Path, bytes] = {
        REFERENCE_PLAN_PATH: reference,
        REQUEST_PATH: request_bytes,
        REPORT_PATH: report_bytes,
        RUNTIME_MANIFEST_PATH: runtime_manifest,
    }
    return without_owner_manifest | {
        MANIFEST_PATH: _manifest_bytes(without_owner_manifest, sources)
    }


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if tuple(expected) != GENERATED_PATHS:
        _fail("GENERATED_INVENTORY_DRIFT")
    for relative in GENERATED_PATHS:
        if _read(root, relative) != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT")


def _ensure_output_parents(root: Path) -> None:
    generated = _repository_path(root, REFERENCE_PLAN_PATH).parent
    try:
        generated.mkdir(mode=0o755, parents=False, exist_ok=True)
        value = generated.lstat()
    except Exception:
        _fail("OUTPUT_WRITE_FAILED")
    if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode):
        _fail("OUTPUT_WRITE_FAILED")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    _ensure_output_parents(root)
    try:
        _publication.publish_generated(
            tuple(
                (_repository_path(root, relative), payload)
                for relative, payload in outputs.items()
            ),
            namespace="st0708",
            maximum_payload_bytes=MAX_SOURCE_BYTES,
        )
    except _publication.SecurePublicationError:
        _fail("OUTPUT_WRITE_FAILED")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--check"]):
        raise SystemExit(2)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(arguments)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        build(check=bool(arguments.check))
    except OpenAiLiveBoundedEvaluationReferenceError as failure:
        print(f"ERROR code={failure.code}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE", file=sys.stderr)
        return 1
    print(
        "ST-0708 recorded live-evaluation runtime checked"
        if arguments.check
        else "ST-0708 recorded live-evaluation runtime generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
