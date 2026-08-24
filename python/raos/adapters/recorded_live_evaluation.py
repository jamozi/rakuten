"""Strict recorded/synthetic-only adapter for the ST-0708 evaluation port."""

from __future__ import annotations

import ast
import json
from typing import NoReturn, SupportsIndex, cast, final

import yaml
from yaml.tokens import AliasToken, AnchorToken

from raos.adapters.recorded_ai_evaluation import load_recorded_evaluation_bundle
from raos.application.ai.evaluation_harness import RecordedEvaluationHarness
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.live_evaluation import (
    EvidenceStatus,
    MetricObservation,
    RecordedCandidateBinding,
    RecordedHarnessReportBinding,
    RecordedLiveEvaluationRequest,
    RecordedLiveEvaluationResult,
    RiskThreshold,
    TRUSTED_RUNTIME_CONTRACT_SHA256,
    ZeroToleranceObservation,
    canonical_json_bytes,
    evaluate_recorded_live_evidence,
    report_projection,
    sha256_bytes,
)


_MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
_HELPER_SHA256 = "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e"
_RUNTIME_CONTRACT_PATH = (
    "changes/st-0708/contracts/recorded-live-evaluation-runtime.v2.yaml"
)
_REQUEST_ROOT_KEYS = frozenset({"document", "evidence", "evidence_sha256"})
_REQUEST_EVIDENCE_KEYS = frozenset(
    {
        "candidate",
        "formal_tst_018_executed",
        "metric_observations",
        "minimum_adjudicated_cases",
        "od_015_resolved",
        "request",
        "required_splits",
        "risk_level",
        "source_report",
        "st0703_binding_verified",
        "st0707_report_verified",
        "target_suite_code",
        "target_task_code",
        "thresholds",
        "zero_tolerance_classes",
        "zero_tolerance_observations",
    }
)
_REQUEST_KEYS = frozenset(
    {"evaluation_id", "request_sha256", "runtime_contract_sha256"}
)
_CANDIDATE_KEYS = frozenset(
    {
        "adapter_contract_sha256",
        "binding_sha256",
        "binding_source_sha256",
        "canonical_model_selected",
        "canonical_prompt_selected",
        "canonical_route_selected",
        "fixture_registry_sha256",
        "live_binding",
        "model_id",
        "prompt_version",
        "provenance",
        "recorded_task_id",
        "route_version",
        "success_fixture_sha256",
        "target_task_code",
    }
)
_SOURCE_REPORT_KEYS = frozenset(
    {
        "bundle_sha256",
        "dataset_provenance",
        "dataset_sha256",
        "holdout_sha256",
        "human_label_status",
        "observed_case_count",
        "observed_splits",
        "release_eligible",
        "report_outcome",
        "report_sha256",
        "source_task_code",
        "suite_code",
    }
)
_THRESHOLD_KEYS = frozenset(
    {"code", "direction", "kind", "operator", "threshold_micros", "unit"}
)
_METRIC_OBSERVATION_KEYS = frozenset({"code", "denominator", "numerator"})
_ZERO_OBSERVATION_KEYS = frozenset(
    {"denominator", "failure_class", "observed_failures"}
)
_FORMAL_STATUS_KEYS = frozenset(
    {"formal_tst_018", "live", "production", "release", "staging"}
)
_RUNTIME_MANIFEST_KEYS = frozenset(
    {
        "document",
        "formal_status",
        "generated_sha256",
        "helper",
        "manifest_sha256",
        "source_sha256",
    }
)
_REPORT_ROOT_KEYS = frozenset({"document", "formal_status", "report"})


@final
class RecordedLiveEvaluationError(ValueError):
    """Stable error that does not echo rejected artifact material."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_RECORDED_LIVE_EVALUATION")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded live evaluation errors are not serializable")


def _fail() -> NoReturn:
    raise RecordedLiveEvaluationError() from None


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in values:
        if type(key) is not str or key in result:
            _fail()
        result[key] = value
    return result


def _reject_float(value: str) -> NoReturn:
    del value
    _fail()


def _json_document(value: object, *, canonical: bool = False) -> dict[str, object]:
    if type(value) is not bytes or not 1 <= len(value) <= _MAX_ARTIFACT_BYTES:
        _fail()
    try:
        parsed = json.loads(
            value,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except RecordedLiveEvaluationError:
        raise
    except Exception:
        _fail()
    if type(parsed) is not dict:
        _fail()
    root = cast(dict[str, object], parsed)
    if canonical and canonical_json_bytes(root) + b"\n" != value:
        _fail()
    return root


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueSafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key == "<<" or key in result:
            _fail()
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _yaml_document(value: object, *, allow_aliases: bool = False) -> dict[str, object]:
    if type(value) is not bytes or not 1 <= len(value) <= _MAX_ARTIFACT_BYTES:
        _fail()
    try:
        text = value.decode("utf-8", errors="strict")
        for token in yaml.scan(text):
            if not allow_aliases and isinstance(token, (AliasToken, AnchorToken)):
                _fail()
        parsed = yaml.load(text, Loader=_UniqueSafeLoader)
    except RecordedLiveEvaluationError:
        raise
    except Exception:
        _fail()
    if type(parsed) is not dict:
        _fail()
    return cast(dict[str, object], parsed)


def _mapping(value: object, keys: frozenset[str] | None = None) -> dict[str, object]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        _fail()
    result = cast(dict[str, object], value)
    if keys is not None and frozenset(result) != keys:
        _fail()
    return result


def _items(value: object, maximum: int = 256) -> list[object]:
    if type(value) is not list or len(value) > maximum:
        _fail()
    return cast(list[object], value)


def _string(value: object, maximum: int = 512) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        _fail()
    return value


def _sha(value: object) -> str:
    text = _string(value, 64)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        _fail()
    return text


def _integer(value: object, maximum: int = 10_000_000) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        _fail()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _local_environment(value: object) -> bool:
    return type(value) is RuntimeEnvironment and value in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }


def _declared_hash(contract: dict[str, object], section: str, name: str) -> str:
    item = _mapping(_mapping(contract[section])[name], frozenset({"path", "sha256"}))
    return _sha(item["sha256"])


def _verify_contract_and_inputs(
    *,
    runtime_contract_bytes: bytes,
    evaluation_catalog_bytes: bytes,
    task_catalog_bytes: bytes,
    routing_catalog_bytes: bytes,
    open_decisions_bytes: bytes,
    test_catalog_bytes: bytes,
    story_catalog_bytes: bytes,
    st0703_adapter_contract_bytes: bytes,
    st0703_fixture_registry_bytes: bytes,
    st0703_success_fixture_bytes: bytes,
    st0703_binding_source_bytes: bytes,
    st0707_runtime_contract_bytes: bytes,
    st0707_runtime_manifest_bytes: bytes,
    st0707_suite_registry_bytes: bytes,
    st0707_dataset_bytes: bytes,
    st0705_runtime_contract_bytes: bytes,
    st0705_profile_registry_bytes: bytes,
    st0705_fixture_bytes: bytes,
    st0705_runtime_manifest_bytes: bytes,
    st0707_task_schema_bytes: bytes,
    st0707_evaluation_case_schema_bytes: bytes,
    publication_helper_bytes: bytes,
) -> dict[str, object]:
    if sha256_bytes(runtime_contract_bytes) != TRUSTED_RUNTIME_CONTRACT_SHA256:
        _fail()
    if sha256_bytes(publication_helper_bytes) != _HELPER_SHA256:
        _fail()
    contract = _yaml_document(runtime_contract_bytes)
    document = _mapping(contract.get("document"))
    if document != {
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
        _fail()
    supplied = {
        ("canonical_sources", "evaluation_catalog"): evaluation_catalog_bytes,
        ("canonical_sources", "task_catalog"): task_catalog_bytes,
        ("canonical_sources", "routing_catalog"): routing_catalog_bytes,
        ("canonical_sources", "open_decisions"): open_decisions_bytes,
        ("canonical_sources", "test_catalog"): test_catalog_bytes,
        ("canonical_sources", "story_catalog"): story_catalog_bytes,
        ("st0703_recorded_binding", "adapter_contract"): st0703_adapter_contract_bytes,
        ("st0703_recorded_binding", "fixture_registry"): st0703_fixture_registry_bytes,
        ("st0703_recorded_binding", "success_fixture"): st0703_success_fixture_bytes,
        ("st0703_recorded_binding", "binding_source"): st0703_binding_source_bytes,
        ("st0707_report_binding", "runtime_contract"): st0707_runtime_contract_bytes,
        ("st0707_report_binding", "runtime_manifest"): st0707_runtime_manifest_bytes,
        ("st0707_report_binding", "suite_registry"): st0707_suite_registry_bytes,
        ("st0707_report_binding", "locked_dataset"): st0707_dataset_bytes,
        (
            "st0707_report_binding",
            "st0705_runtime_contract",
        ): st0705_runtime_contract_bytes,
        (
            "st0707_report_binding",
            "st0705_profile_registry",
        ): st0705_profile_registry_bytes,
        ("st0707_report_binding", "st0705_fixture"): st0705_fixture_bytes,
        (
            "st0707_report_binding",
            "st0705_runtime_manifest",
        ): st0705_runtime_manifest_bytes,
        ("st0707_report_binding", "task_schema"): st0707_task_schema_bytes,
        (
            "st0707_report_binding",
            "evaluation_case_schema",
        ): st0707_evaluation_case_schema_bytes,
    }
    for (section, name), payload in supplied.items():
        if type(payload) is not bytes or not 1 <= len(payload) <= _MAX_ARTIFACT_BYTES:
            _fail()
        if sha256_bytes(payload) != _declared_hash(contract, section, name):
            _fail()
    policy = _mapping(contract.get("runtime_policy"))
    if (
        policy.get("unavailable_is_pass") is not False
        or policy.get("unknown_is_zero") is not False
        or policy.get("insufficient_is_pass") is not False
        or policy.get("zero_tolerance_waiver_allowed") is not False
        or policy.get("external_actions") is not False
        or policy.get("formal_tst_018") != "NOT_EXECUTED"
        or policy.get("od_015") != "EXTERNAL_EVIDENCE_REQUIRED"
    ):
        _fail()
    return contract


def _call_keywords(
    tree: ast.Module, function_name: str, call_name: str
) -> dict[str, str]:
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    ]
    if len(functions) != 1:
        _fail()
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
        _fail()
    result: dict[str, str] = {}
    for keyword in calls[0].keywords:
        if keyword.arg is not None and isinstance(keyword.value, ast.Constant):
            if type(keyword.value.value) is str:
                result[keyword.arg] = keyword.value.value
    return result


def _verify_st0703_semantics(
    contract: dict[str, object],
    *,
    st0703_adapter_contract_bytes: bytes,
    st0703_fixture_registry_bytes: bytes,
    st0703_success_fixture_bytes: bytes,
    st0703_binding_source_bytes: bytes,
) -> None:
    expected = _mapping(contract["st0703_recorded_binding"])
    try:
        tree = ast.parse(st0703_binding_source_bytes.decode("utf-8", errors="strict"))
    except Exception:
        _fail()
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
        _fail()
    fixture = _json_document(st0703_success_fixture_bytes)
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
        _fail()
    registry = _json_document(st0703_fixture_registry_bytes)
    matches = [
        _mapping(item)
        for item in _items(registry.get("fixtures"))
        if _mapping(item).get("path") == "success-structured.json"
    ]
    if len(matches) != 1 or matches[0].get("sha256") != sha256_bytes(
        st0703_success_fixture_bytes
    ):
        _fail()
    adapter_contract = _yaml_document(st0703_adapter_contract_bytes)
    authority = _mapping(adapter_contract.get("implementation_authority"))
    boundary = _mapping(adapter_contract.get("boundary"))
    if (
        authority.get("authority") != "ST0703_RECORDED_SCOPE_ONLY"
        or boundary.get("live_api") != "NOT_USED"
        or boundary.get("credential_or_secret_resolution") != "NOT_USED"
        or boundary.get("live_tst_018") != "NOT_EXECUTED"
        or boundary.get("production_readiness") != "NOT_READY"
    ):
        _fail()


def _thresholds_from_catalog(
    contract: dict[str, object], evaluation_catalog_bytes: bytes
) -> tuple[RiskThreshold, ...]:
    catalog = _yaml_document(evaluation_catalog_bytes, allow_aliases=True)
    target = _mapping(contract["target_suite"])
    suites = [
        _mapping(item)
        for item in _items(catalog.get("suites"))
        if _mapping(item).get("suite_code") == target.get("suite_code")
    ]
    if len(suites) != 1:
        _fail()
    suite = suites[0]
    if (
        suite.get("task_code") != target.get("task_code")
        or suite.get("risk_level") != target.get("risk_level")
        or suite.get("minimum_adjudicated_cases")
        != target.get("minimum_adjudicated_cases")
        or suite.get("required_splits") != target.get("required_splits")
    ):
        _fail()
    metrics = {
        _string(_mapping(item).get("code")): _mapping(item)
        for item in _items(catalog.get("metrics"))
    }
    raw_thresholds = _mapping(suite.get("thresholds"))
    result: list[RiskThreshold] = []
    for code in sorted(raw_thresholds):
        raw = _mapping(raw_thresholds[code], frozenset({"operator", "value"}))
        definition = metrics.get(code)
        if definition is None or type(raw["value"]) not in {int, float}:
            _fail()
        scaled = int(str(raw["value"]).replace(".", ""))
        decimal_places = (
            len(str(raw["value"]).split(".", 1)[1]) if "." in str(raw["value"]) else 0
        )
        threshold_micros = scaled * 10 ** (6 - decimal_places)
        threshold = RiskThreshold(
            code=code,
            kind=_string(definition.get("kind")),
            direction=_string(definition.get("direction")),
            unit=_string(definition.get("unit")),
            operator=_string(raw["operator"]),
            threshold_micros=threshold_micros,
        )
        threshold.require_valid()
        result.append(threshold)
    return tuple(result)


def _request_from_artifact(value: bytes) -> RecordedLiveEvaluationResult:
    root = _mapping(_json_document(value, canonical=True), _REQUEST_ROOT_KEYS)
    document = _mapping(root.get("document"))
    if document != {
        "authority": "NONE",
        "default_enabled": False,
        "id": "RAOS-ST0708-RECORDED-LIVE-EVALUATION-REQUEST-002",
        "live_provider": False,
        "production_eligible": False,
        "release_authorized": False,
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "story_id": "ST-0708",
        "version": "2.0.0",
    }:
        _fail()
    evidence = _mapping(root.get("evidence"), _REQUEST_EVIDENCE_KEYS)
    request_raw = _mapping(evidence.get("request"), _REQUEST_KEYS)
    request = RecordedLiveEvaluationRequest(
        evaluation_id=_string(request_raw.get("evaluation_id")),
        runtime_contract_sha256=_sha(request_raw.get("runtime_contract_sha256")),
        request_sha256=_sha(request_raw.get("request_sha256")),
    )
    candidate_raw = _mapping(evidence.get("candidate"), _CANDIDATE_KEYS)
    candidate = RecordedCandidateBinding(
        recorded_task_id=_string(candidate_raw.get("recorded_task_id")),
        target_task_code=_string(candidate_raw.get("target_task_code")),
        route_version=_string(candidate_raw.get("route_version")),
        prompt_version=_string(candidate_raw.get("prompt_version")),
        model_id=_string(candidate_raw.get("model_id")),
        provenance=_string(candidate_raw.get("provenance")),
        adapter_contract_sha256=_sha(candidate_raw.get("adapter_contract_sha256")),
        fixture_registry_sha256=_sha(candidate_raw.get("fixture_registry_sha256")),
        success_fixture_sha256=_sha(candidate_raw.get("success_fixture_sha256")),
        binding_source_sha256=_sha(candidate_raw.get("binding_source_sha256")),
        canonical_route_selected=_boolean(
            candidate_raw.get("canonical_route_selected")
        ),
        canonical_model_selected=_boolean(
            candidate_raw.get("canonical_model_selected")
        ),
        canonical_prompt_selected=_boolean(
            candidate_raw.get("canonical_prompt_selected")
        ),
        live_binding=_boolean(candidate_raw.get("live_binding")),
        binding_sha256=_sha(candidate_raw.get("binding_sha256")),
    )
    source_raw = _mapping(evidence.get("source_report"), _SOURCE_REPORT_KEYS)
    source_report = RecordedHarnessReportBinding(
        source_task_code=_string(source_raw.get("source_task_code")),
        suite_code=_string(source_raw.get("suite_code")),
        bundle_sha256=_sha(source_raw.get("bundle_sha256")),
        report_sha256=_sha(source_raw.get("report_sha256")),
        report_outcome=_string(source_raw.get("report_outcome")),
        dataset_sha256=_sha(source_raw.get("dataset_sha256")),
        holdout_sha256=_sha(source_raw.get("holdout_sha256")),
        observed_case_count=_integer(source_raw.get("observed_case_count"), 10_000),
        observed_splits=tuple(
            sorted(
                _string(item) for item in _items(source_raw.get("observed_splits"), 8)
            )
        ),
        dataset_provenance=_string(source_raw.get("dataset_provenance")),
        human_label_status=EvidenceStatus(
            _string(source_raw.get("human_label_status"))
        ),
        release_eligible=_boolean(source_raw.get("release_eligible")),
    )
    thresholds = tuple(
        RiskThreshold(
            code=_string(_mapping(item, _THRESHOLD_KEYS).get("code")),
            kind=_string(_mapping(item, _THRESHOLD_KEYS).get("kind")),
            direction=_string(_mapping(item, _THRESHOLD_KEYS).get("direction")),
            unit=_string(_mapping(item, _THRESHOLD_KEYS).get("unit")),
            operator=_string(_mapping(item, _THRESHOLD_KEYS).get("operator")),
            threshold_micros=_integer(
                _mapping(item, _THRESHOLD_KEYS).get("threshold_micros"),
                5_000_000,
            ),
        )
        for item in _items(evidence.get("thresholds"), 32)
    )
    observations = tuple(
        MetricObservation(
            code=_string(_mapping(item, _METRIC_OBSERVATION_KEYS).get("code")),
            numerator=(
                None
                if _mapping(item, _METRIC_OBSERVATION_KEYS).get("numerator") is None
                else _integer(_mapping(item, _METRIC_OBSERVATION_KEYS).get("numerator"))
            ),
            denominator=(
                None
                if _mapping(item, _METRIC_OBSERVATION_KEYS).get("denominator") is None
                else _integer(
                    _mapping(item, _METRIC_OBSERVATION_KEYS).get("denominator")
                )
            ),
        )
        for item in _items(evidence.get("metric_observations"), 32)
    )
    zero_observations = tuple(
        ZeroToleranceObservation(
            failure_class=_string(
                _mapping(item, _ZERO_OBSERVATION_KEYS).get("failure_class"), 200
            ),
            observed_failures=(
                None
                if _mapping(item, _ZERO_OBSERVATION_KEYS).get("observed_failures")
                is None
                else _integer(
                    _mapping(item, _ZERO_OBSERVATION_KEYS).get("observed_failures")
                )
            ),
            denominator=(
                None
                if _mapping(item, _ZERO_OBSERVATION_KEYS).get("denominator") is None
                else _integer(_mapping(item, _ZERO_OBSERVATION_KEYS).get("denominator"))
            ),
        )
        for item in _items(evidence.get("zero_tolerance_observations"), 8)
    )
    result = RecordedLiveEvaluationResult(
        request=request,
        candidate=candidate,
        source_report=source_report,
        target_suite_code=_string(evidence.get("target_suite_code")),
        target_task_code=_string(evidence.get("target_task_code")),
        risk_level=_string(evidence.get("risk_level")),
        minimum_adjudicated_cases=_integer(
            evidence.get("minimum_adjudicated_cases"), 10_000
        ),
        required_splits=tuple(
            _string(item) for item in _items(evidence.get("required_splits"), 8)
        ),
        thresholds=thresholds,
        zero_tolerance_classes=tuple(
            _string(item, 200)
            for item in _items(evidence.get("zero_tolerance_classes"), 8)
        ),
        metric_observations=observations,
        zero_tolerance_observations=zero_observations,
        st0703_binding_verified=_boolean(evidence.get("st0703_binding_verified")),
        st0707_report_verified=_boolean(evidence.get("st0707_report_verified")),
        formal_tst_018_executed=_boolean(evidence.get("formal_tst_018_executed")),
        od_015_resolved=_boolean(evidence.get("od_015_resolved")),
        evidence_sha256=_sha(root.get("evidence_sha256")),
    )
    result.require_valid()
    return result


def _manifest_source_paths(contract: dict[str, object]) -> frozenset[str]:
    paths = {_RUNTIME_CONTRACT_PATH}
    for section_name in (
        "canonical_sources",
        "st0703_recorded_binding",
        "st0707_report_binding",
    ):
        for value in _mapping(contract.get(section_name)).values():
            if type(value) is not dict:
                continue
            item = _mapping(value, frozenset({"path", "sha256"}))
            paths.add(_string(item.get("path")))
    for value in _items(contract.get("owned_sources"), 64):
        paths.add(_string(value))
    if not 1 <= len(paths) <= 64:
        _fail()
    return frozenset(paths)


def _verify_runtime_manifest(
    value: bytes,
    *,
    contract: dict[str, object],
    request_artifact_bytes: bytes,
    report_artifact_bytes: bytes,
    historical_reference_plan_bytes: bytes,
    publication_helper_bytes: bytes,
) -> None:
    root = _mapping(
        _json_document(value, canonical=True),
        _RUNTIME_MANIFEST_KEYS,
    )
    manifest_sha256 = _sha(root.get("manifest_sha256"))
    manifest_material = {
        key: item for key, item in root.items() if key != "manifest_sha256"
    }
    if sha256_bytes(canonical_json_bytes(manifest_material)) != manifest_sha256:
        _fail()
    document = _mapping(root.get("document"))
    if document != {
        "authority": "NONE",
        "id": "RAOS-ST0708-RUNTIME-MANIFEST-002",
        "production_eligible": False,
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "story_id": "ST-0708",
        "version": "2.0.0",
    }:
        _fail()
    formal = _mapping(root.get("formal_status"), _FORMAL_STATUS_KEYS)
    if any(item != "NOT_EXECUTED" for item in formal.values()):
        _fail()
    generated = _mapping(root.get("generated_sha256"))
    if generated != {
        "changes/st-0708/generated/openai-live-bounded-evaluation-reference-plan.v1.json": sha256_bytes(
            historical_reference_plan_bytes
        ),
        "changes/st-0708/generated/recorded-live-evaluation-report.v2.json": sha256_bytes(
            report_artifact_bytes
        ),
        "changes/st-0708/generated/recorded-live-evaluation-request.v2.json": sha256_bytes(
            request_artifact_bytes
        ),
    }:
        _fail()
    helper = _mapping(root.get("helper"))
    if (
        helper
        != {
            "path": "scripts/secure_generated_publication.py",
            "sha256": _HELPER_SHA256,
        }
        or sha256_bytes(publication_helper_bytes) != _HELPER_SHA256
    ):
        _fail()
    sources = _mapping(root.get("source_sha256"))
    if frozenset(sources) != _manifest_source_paths(contract):
        _fail()
    for digest in sources.values():
        _sha(digest)
    if (
        sources.get(_RUNTIME_CONTRACT_PATH) != TRUSTED_RUNTIME_CONTRACT_SHA256
        or sources.get("scripts/secure_generated_publication.py") != _HELPER_SHA256
    ):
        _fail()
    for section_name in (
        "canonical_sources",
        "st0703_recorded_binding",
        "st0707_report_binding",
    ):
        for section_value in _mapping(contract.get(section_name)).values():
            if type(section_value) is not dict:
                continue
            item = _mapping(section_value, frozenset({"path", "sha256"}))
            if sources.get(_string(item.get("path"))) != _sha(item.get("sha256")):
                _fail()


def _verify_report_artifact(value: bytes, result: RecordedLiveEvaluationResult) -> None:
    root = _mapping(_json_document(value, canonical=True), _REPORT_ROOT_KEYS)
    document = _mapping(root.get("document"))
    if document != {
        "authority": "NONE",
        "id": "RAOS-ST0708-RECORDED-LIVE-EVALUATION-REPORT-002",
        "production_eligible": False,
        "release_authorized": False,
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "story_id": "ST-0708",
        "version": "2.0.0",
    }:
        _fail()
    formal = _mapping(root.get("formal_status"), _FORMAL_STATUS_KEYS)
    if any(value != "NOT_EXECUTED" for value in formal.values()):
        _fail()
    report = evaluate_recorded_live_evidence(result)
    expected = report_projection(report) | {"report_sha256": report.report_sha256}
    if root.get("report") != expected:
        _fail()


def load_recorded_live_evaluation_result(
    *,
    runtime_contract_bytes: bytes,
    runtime_manifest_bytes: bytes,
    request_artifact_bytes: bytes,
    report_artifact_bytes: bytes,
    historical_reference_plan_bytes: bytes,
    publication_helper_bytes: bytes,
    evaluation_catalog_bytes: bytes,
    task_catalog_bytes: bytes,
    routing_catalog_bytes: bytes,
    open_decisions_bytes: bytes,
    test_catalog_bytes: bytes,
    story_catalog_bytes: bytes,
    st0703_adapter_contract_bytes: bytes,
    st0703_fixture_registry_bytes: bytes,
    st0703_success_fixture_bytes: bytes,
    st0703_binding_source_bytes: bytes,
    st0707_runtime_contract_bytes: bytes,
    st0707_runtime_manifest_bytes: bytes,
    st0707_suite_registry_bytes: bytes,
    st0707_dataset_bytes: bytes,
    st0705_runtime_contract_bytes: bytes,
    st0705_profile_registry_bytes: bytes,
    st0705_fixture_bytes: bytes,
    st0705_runtime_manifest_bytes: bytes,
    st0707_task_schema_bytes: bytes,
    st0707_evaluation_case_schema_bytes: bytes,
) -> RecordedLiveEvaluationResult:
    """Validate every exact binding and return one immutable recorded result."""

    try:
        contract = _verify_contract_and_inputs(
            runtime_contract_bytes=runtime_contract_bytes,
            evaluation_catalog_bytes=evaluation_catalog_bytes,
            task_catalog_bytes=task_catalog_bytes,
            routing_catalog_bytes=routing_catalog_bytes,
            open_decisions_bytes=open_decisions_bytes,
            test_catalog_bytes=test_catalog_bytes,
            story_catalog_bytes=story_catalog_bytes,
            st0703_adapter_contract_bytes=st0703_adapter_contract_bytes,
            st0703_fixture_registry_bytes=st0703_fixture_registry_bytes,
            st0703_success_fixture_bytes=st0703_success_fixture_bytes,
            st0703_binding_source_bytes=st0703_binding_source_bytes,
            st0707_runtime_contract_bytes=st0707_runtime_contract_bytes,
            st0707_runtime_manifest_bytes=st0707_runtime_manifest_bytes,
            st0707_suite_registry_bytes=st0707_suite_registry_bytes,
            st0707_dataset_bytes=st0707_dataset_bytes,
            st0705_runtime_contract_bytes=st0705_runtime_contract_bytes,
            st0705_profile_registry_bytes=st0705_profile_registry_bytes,
            st0705_fixture_bytes=st0705_fixture_bytes,
            st0705_runtime_manifest_bytes=st0705_runtime_manifest_bytes,
            st0707_task_schema_bytes=st0707_task_schema_bytes,
            st0707_evaluation_case_schema_bytes=st0707_evaluation_case_schema_bytes,
            publication_helper_bytes=publication_helper_bytes,
        )
        _verify_st0703_semantics(
            contract,
            st0703_adapter_contract_bytes=st0703_adapter_contract_bytes,
            st0703_fixture_registry_bytes=st0703_fixture_registry_bytes,
            st0703_success_fixture_bytes=st0703_success_fixture_bytes,
            st0703_binding_source_bytes=st0703_binding_source_bytes,
        )
        result = _request_from_artifact(request_artifact_bytes)
        if result.thresholds != _thresholds_from_catalog(
            contract, evaluation_catalog_bytes
        ):
            _fail()
        bundle = load_recorded_evaluation_bundle(
            runtime_contract_bytes=st0707_runtime_contract_bytes,
            runtime_manifest_bytes=st0707_runtime_manifest_bytes,
            suite_registry_bytes=st0707_suite_registry_bytes,
            dataset_bytes=st0707_dataset_bytes,
            st0705_runtime_contract_bytes=st0705_runtime_contract_bytes,
            st0705_profile_registry_bytes=st0705_profile_registry_bytes,
            st0705_fixture_bytes=st0705_fixture_bytes,
            st0705_runtime_manifest_bytes=st0705_runtime_manifest_bytes,
            task_schema_bytes=st0707_task_schema_bytes,
            evaluation_case_schema_bytes=st0707_evaluation_case_schema_bytes,
        )
        source = RecordedEvaluationHarness().run(bundle)
        if (
            bundle.bundle_sha256 != result.source_report.bundle_sha256
            or source.report_sha256 != result.source_report.report_sha256
            or source.proposal.outcome.value != result.source_report.report_outcome
            or source.dataset_sha256 != result.source_report.dataset_sha256
            or source.holdout_sha256 != result.source_report.holdout_sha256
            or source.case_count != result.source_report.observed_case_count
            or bundle.suite.task_code != result.source_report.source_task_code
            or bundle.suite.suite_code != result.source_report.suite_code
            or tuple(sorted({item.split.value for item in bundle.dataset.cases}))
            != result.source_report.observed_splits
            or bundle.dataset.provenance.value
            != result.source_report.dataset_provenance
            or bundle.dataset.human_label_status.value
            != result.source_report.human_label_status.value
            or bundle.dataset.release_eligible != result.source_report.release_eligible
        ):
            _fail()
        _verify_report_artifact(report_artifact_bytes, result)
        _verify_runtime_manifest(
            runtime_manifest_bytes,
            contract=contract,
            request_artifact_bytes=request_artifact_bytes,
            report_artifact_bytes=report_artifact_bytes,
            historical_reference_plan_bytes=historical_reference_plan_bytes,
            publication_helper_bytes=publication_helper_bytes,
        )
        result.require_valid()
        return result
    except RecordedLiveEvaluationError:
        raise
    except Exception:
        _fail()


@final
class RecordedLiveEvaluationAdapter:
    """In-memory exact-request adapter with no provider or I/O capability."""

    __slots__ = ("_result",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        result: RecordedLiveEvaluationResult,
    ) -> None:
        if (
            not _local_environment(environment)
            or type(result) is not RecordedLiveEvaluationResult
        ):
            _fail()
        result.require_valid()
        self._result = result

    def execute(
        self, request: RecordedLiveEvaluationRequest
    ) -> RecordedLiveEvaluationResult | None:
        if type(request) is not RecordedLiveEvaluationRequest:
            return None
        try:
            request.require_valid()
            self._result.require_valid()
        except Exception:
            return None
        if request != self._result.request:
            return None
        return self._result


__all__ = [
    "RecordedLiveEvaluationAdapter",
    "RecordedLiveEvaluationError",
    "load_recorded_live_evaluation_result",
]
