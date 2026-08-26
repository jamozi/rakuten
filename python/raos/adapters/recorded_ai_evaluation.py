"""Strict byte loader for the ST-0707 recorded/synthetic evaluation bundle."""

from __future__ import annotations

import json
from collections.abc import Iterator
from types import MappingProxyType
from typing import Mapping, NoReturn, Protocol, SupportsIndex, cast, final

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from raos.adapters.recorded_ai_output_validation import (
    load_recorded_ai_output_validation_fixture,
    load_trusted_ai_output_validation_profiles,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.evaluation_harness import (
    DatasetLockStatus,
    DatasetProvenance,
    EvaluationSplit,
    EvaluationSuite,
    HumanLabelStatus,
    LockedEvaluationCase,
    LockedEvaluationDataset,
    MetricThreshold,
    RecordedEvaluationBundle,
    canonical_json_bytes,
    sha256_bytes,
)
from raos.domain.ai.output_validation import evaluate_ai_output


_MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
_MAX_COLLECTION = 256
_EXPECTED_ST0705 = {
    "runtime_contract": "25e8696211025ee2581b0318ca2758dbcd4dccccd37447be1e8ad84667dbb02d",
    "profile_registry": "7266bb90e673320fc64b9c5344fcfefbda864a8ce41da10c5857f68682e9c8ed",
    "recorded_fixture": "e87088fc150bad7b7c4d863f540eac6f474591a1da86c830d5b7a3f942bcfaf2",
    "runtime_manifest": "d590ad333830cd9f8006400de2f23f82ca1daa36daac00bd8078e50fcd609747",
    "task_schema": "504cc8907a2d4dd6835adef13ad53d6e31e6a0f412102ec6a8495600e3242123",
}
_EXPECTED_EVALUATION_CASE_SCHEMA_SHA256 = (
    "363094954df80ab4bd8c28804d27e4634f79210fcd28fa82062ea49729549b7a"
)


class _JsonSchemaValidator(Protocol):
    def iter_errors(self, instance: object) -> Iterator[object]: ...


@final
class RecordedAiEvaluationError(ValueError):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_RECORDED_AI_EVALUATION")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded evaluation errors are not serializable")


def _fail() -> NoReturn:
    raise RecordedAiEvaluationError() from None


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


def _json_artifact(value: object) -> dict[str, object]:
    if type(value) is not bytes or not 1 <= len(value) <= _MAX_ARTIFACT_BYTES:
        _fail()
    try:
        parsed = json.loads(
            value,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except RecordedAiEvaluationError:
        raise
    except Exception:
        _fail()
    if type(parsed) is not dict:
        _fail()
    root = cast(dict[str, object], parsed)
    if canonical_json_bytes(root) + b"\n" != value:
        _fail()
    return root


def _json_document(value: object) -> dict[str, object]:
    if type(value) is not bytes or not 1 <= len(value) <= _MAX_ARTIFACT_BYTES:
        _fail()
    try:
        parsed = json.loads(
            value,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except RecordedAiEvaluationError:
        raise
    except Exception:
        _fail()
    if type(parsed) is not dict:
        _fail()
    return cast(dict[str, object], parsed)


def _mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _fail()
    mapping = cast(dict[object, object], value)
    if frozenset(mapping) != keys:
        _fail()
    return cast(dict[str, object], mapping)


def _string(value: object, *, maximum: int = 256) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        _fail()
    return value


def _sha(value: object) -> str:
    text = _string(value, maximum=64)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        _fail()
    return text


def _integer(value: object, *, maximum: int = 10_000_000) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        _fail()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _items(value: object, *, maximum: int = _MAX_COLLECTION) -> list[object]:
    if type(value) is not list:
        _fail()
    items = cast(list[object], value)
    if len(items) > maximum:
        _fail()
    return items


def _local_environment(value: object) -> bool:
    return type(value) is RuntimeEnvironment and value in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }


def _load_suite(root: dict[str, object]) -> EvaluationSuite:
    root = _mapping(
        root,
        frozenset({"bindings", "document", "registry_sha256", "suite"}),
    )
    expected_registry_sha = _sha(root["registry_sha256"])
    unhashed = {key: value for key, value in root.items() if key != "registry_sha256"}
    if sha256_bytes(canonical_json_bytes(unhashed)) != expected_registry_sha:
        _fail()
    document = _mapping(
        root["document"],
        frozenset(
            {
                "authority",
                "id",
                "live_provider",
                "production_eligible",
                "provider_mode",
                "release_authorized",
                "story_id",
                "version",
            }
        ),
    )
    if document != {
        "authority": "NONE",
        "id": "RAOS-ST0707-EVALUATION-SUITE-REGISTRY-001",
        "live_provider": False,
        "production_eligible": False,
        "provider_mode": "RECORDED_SYNTHETIC_ONLY",
        "release_authorized": False,
        "story_id": "ST-0707",
        "version": "1.0.0",
    }:
        _fail()
    bindings = _mapping(
        root["bindings"],
        frozenset(
            {
                "evaluation_catalog_sha256",
                "profile_registry_sha256",
                "st0705_runtime_contract_sha256",
                "st0705_runtime_manifest_sha256",
            }
        ),
    )
    suite = _mapping(
        root["suite"],
        frozenset(
            {
                "minimum_adjudicated_cases",
                "required_splits",
                "risk_level",
                "suite_code",
                "task_code",
                "thresholds",
                "zero_tolerance_classes",
            }
        ),
    )
    thresholds: list[MetricThreshold] = []
    for raw in _items(suite["thresholds"], maximum=64):
        item = _mapping(
            raw,
            frozenset(
                {
                    "code",
                    "direction",
                    "kind",
                    "operator",
                    "threshold_micros",
                    "unit",
                }
            ),
        )
        thresholds.append(
            MetricThreshold(
                code=_string(item["code"]),
                kind=_string(item["kind"]),
                direction=_string(item["direction"]),
                unit=_string(item["unit"]),
                operator=_string(item["operator"]),
                threshold_micros=_integer(item["threshold_micros"]),
            )
        )
    try:
        required_splits = tuple(
            EvaluationSplit(_string(item)) for item in _items(suite["required_splits"])
        )
    except Exception:
        _fail()
    zero_tolerance = tuple(
        _string(item, maximum=160)
        for item in _items(suite["zero_tolerance_classes"], maximum=8)
    )
    try:
        return EvaluationSuite(
            suite_code=_string(suite["suite_code"]),
            task_code=_string(suite["task_code"]),
            risk_level=_string(suite["risk_level"]),
            minimum_adjudicated_cases=_integer(
                suite["minimum_adjudicated_cases"], maximum=10_000
            ),
            required_splits=required_splits,
            thresholds=tuple(thresholds),
            zero_tolerance_classes=zero_tolerance,
            evaluation_catalog_sha256=_sha(bindings["evaluation_catalog_sha256"]),
            profile_registry_sha256=_sha(bindings["profile_registry_sha256"]),
            st0705_runtime_contract_sha256=_sha(
                bindings["st0705_runtime_contract_sha256"]
            ),
            st0705_runtime_manifest_sha256=_sha(
                bindings["st0705_runtime_manifest_sha256"]
            ),
            registry_sha256=expected_registry_sha,
        )
    except Exception:
        _fail()


def _load_dataset(
    root: dict[str, object], *, evaluation_case_schema_bytes: bytes
) -> LockedEvaluationDataset:
    root = _mapping(root, frozenset({"dataset", "document"}))
    document = _mapping(
        root["document"],
        frozenset(
            {
                "authority",
                "id",
                "live_provider",
                "production_eligible",
                "release_authorized",
                "story_id",
                "version",
            }
        ),
    )
    if document != {
        "authority": "NONE",
        "id": "RAOS-ST0707-LOCKED-SYNTHETIC-HOLDOUT-001",
        "live_provider": False,
        "production_eligible": False,
        "release_authorized": False,
        "story_id": "ST-0707",
        "version": "1.0.0",
    }:
        _fail()
    dataset = _mapping(
        root["dataset"],
        frozenset(
            {
                "canonical_dataset",
                "cases",
                "dataset_id",
                "dataset_sha256",
                "holdout_sha256",
                "human_label_status",
                "human_labeled",
                "label_provenance",
                "locked_at",
                "provenance",
                "release_eligible",
                "representative_dataset",
                "source_kind",
                "status",
                "version",
            }
        ),
    )
    labels = _items(dataset["label_provenance"])
    try:
        evaluation_case_schema = _json_document(evaluation_case_schema_bytes)
        Draft202012Validator.check_schema(evaluation_case_schema)
        evaluation_case_validator = Draft202012Validator(evaluation_case_schema)
    except Exception:
        _fail()
    cases: list[LockedEvaluationCase] = []
    for raw in _items(dataset["cases"]):
        item = _mapping(
            raw,
            frozenset(
                {
                    "case_id",
                    "case_sha256",
                    "category",
                    "evaluation_case",
                    "evaluation_case_sha256",
                    "output_sha256",
                    "profile_sha256",
                    "provenance",
                    "provider_exchange_sha256",
                    "split",
                    "st0705_report_sha256",
                    "validation_manifest_sha256",
                }
            ),
        )
        evaluation_case = _mapping(
            item["evaluation_case"],
            frozenset(
                {
                    "case_id",
                    "category",
                    "dataset_version",
                    "expected_disposition",
                    "expected_invariants",
                    "gold_artifact",
                    "input_fixture",
                    "metrics",
                    "notes",
                    "risk_level",
                    "split",
                    "tags",
                    "task_code",
                }
            ),
        )
        try:
            validator = cast(_JsonSchemaValidator, evaluation_case_validator)
            schema_errors = tuple(validator.iter_errors(evaluation_case))
        except Exception:
            _fail()
        if (
            schema_errors
            or sha256_bytes(canonical_json_bytes(evaluation_case))
            != _sha(item["evaluation_case_sha256"])
            or evaluation_case["case_id"] != item["case_id"]
            or evaluation_case["split"] != item["split"]
            or evaluation_case["category"] != item["category"]
            or evaluation_case["task_code"] != "ai.opportunity_assessment.v1"
            or evaluation_case["dataset_version"] != dataset["version"]
            or evaluation_case["gold_artifact"] is not None
        ):
            _fail()
        try:
            cases.append(
                LockedEvaluationCase(
                    case_id=_string(item["case_id"]),
                    split=EvaluationSplit(_string(item["split"])),
                    category=_string(item["category"]),
                    provenance=DatasetProvenance(_string(item["provenance"])),
                    st0705_report_sha256=_sha(item["st0705_report_sha256"]),
                    profile_sha256=_sha(item["profile_sha256"]),
                    validation_manifest_sha256=_sha(item["validation_manifest_sha256"]),
                    output_sha256=_sha(item["output_sha256"]),
                    provider_exchange_sha256=_sha(item["provider_exchange_sha256"]),
                    evaluation_case_sha256=_sha(item["evaluation_case_sha256"]),
                    case_sha256=_sha(item["case_sha256"]),
                )
            )
        except Exception:
            _fail()
    try:
        return LockedEvaluationDataset(
            dataset_id=_string(dataset["dataset_id"]),
            version=_string(dataset["version"]),
            status=DatasetLockStatus(_string(dataset["status"])),
            provenance=DatasetProvenance(_string(dataset["provenance"])),
            source_kind=_string(dataset["source_kind"]),
            locked_at=_string(dataset["locked_at"]),
            human_label_status=HumanLabelStatus(_string(dataset["human_label_status"])),
            label_provenance_count=len(labels),
            cases=tuple(cases),
            holdout_sha256=_sha(dataset["holdout_sha256"]),
            dataset_sha256=_sha(dataset["dataset_sha256"]),
            release_eligible=_boolean(dataset["release_eligible"]),
            canonical_dataset=_boolean(dataset["canonical_dataset"]),
            representative_dataset=_boolean(dataset["representative_dataset"]),
            human_labeled=_boolean(dataset["human_labeled"]),
        )
    except Exception:
        _fail()


def _validate_runtime_manifest(
    root: dict[str, object],
    *,
    runtime_contract_bytes: bytes,
    suite_registry_bytes: bytes,
    dataset_bytes: bytes,
    st0705_runtime_contract_bytes: bytes,
    st0705_profile_registry_bytes: bytes,
    st0705_fixture_bytes: bytes,
    st0705_runtime_manifest_bytes: bytes,
    task_schema_bytes: bytes,
    evaluation_case_schema_bytes: bytes,
) -> None:
    root = _mapping(
        root,
        frozenset(
            {
                "document",
                "formal_status",
                "generated_sha256",
                "source_sha256",
            }
        ),
    )
    document = _mapping(
        root["document"],
        frozenset(
            {
                "authority",
                "id",
                "production_eligible",
                "status",
                "story_id",
                "version",
            }
        ),
    )
    if document != {
        "authority": "NONE",
        "id": "RAOS-ST0707-RUNTIME-MANIFEST-001",
        "production_eligible": False,
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "story_id": "ST-0707",
        "version": "1.0.0",
    }:
        _fail()
    sources = cast(dict[str, object], root["source_sha256"])
    generated = _mapping(
        root["generated_sha256"],
        frozenset(
            {
                "changes/st-0707/generated/evaluation-suite-registry.v1.json",
                "changes/st-0707/generated/locked-synthetic-holdout.v1.json",
            }
        ),
    )
    if type(sources) is not dict:
        _fail()
    observed = {
        "changes/st-0707/contracts/evaluation-harness-runtime.v1.yaml": sha256_bytes(
            runtime_contract_bytes
        ),
        "changes/st-0705/contracts/ai-output-validation-runtime.v1.yaml": sha256_bytes(
            st0705_runtime_contract_bytes
        ),
        "changes/st-0705/generated/ai-output-validation-profiles.v1.json": sha256_bytes(
            st0705_profile_registry_bytes
        ),
        "changes/st-0705/generated/ai-output-validation-pass.v1.json": sha256_bytes(
            st0705_fixture_bytes
        ),
        "changes/st-0705/runtime-manifest.v1.yaml": sha256_bytes(
            st0705_runtime_manifest_bytes
        ),
        "contracts/raos-v0.4/contracts/ai/schemas/tasks/ai.opportunity_assessment.v1.output.schema.json": sha256_bytes(
            task_schema_bytes
        ),
        "contracts/raos-v0.4/contracts/ai/schemas/eval/evaluation_case.v1.schema.json": sha256_bytes(
            evaluation_case_schema_bytes
        ),
    }
    if any(sources.get(path) != digest for path, digest in observed.items()):
        _fail()
    if generated != {
        "changes/st-0707/generated/evaluation-suite-registry.v1.json": sha256_bytes(
            suite_registry_bytes
        ),
        "changes/st-0707/generated/locked-synthetic-holdout.v1.json": sha256_bytes(
            dataset_bytes
        ),
    }:
        _fail()
    formal = _mapping(
        root["formal_status"],
        frozenset(
            {
                "formal_tst_018",
                "formal_tst_019",
                "live",
                "production",
                "release",
                "staging",
            }
        ),
    )
    if any(value != "NOT_EXECUTED" for value in formal.values()):
        _fail()


def load_recorded_evaluation_bundle(
    *,
    runtime_contract_bytes: bytes,
    runtime_manifest_bytes: bytes,
    suite_registry_bytes: bytes,
    dataset_bytes: bytes,
    st0705_runtime_contract_bytes: bytes,
    st0705_profile_registry_bytes: bytes,
    st0705_fixture_bytes: bytes,
    st0705_runtime_manifest_bytes: bytes,
    task_schema_bytes: bytes,
    evaluation_case_schema_bytes: bytes,
) -> RecordedEvaluationBundle:
    """Load one exact content-addressed bundle; never repair or infer evidence."""

    supplied = (
        runtime_contract_bytes,
        runtime_manifest_bytes,
        suite_registry_bytes,
        dataset_bytes,
        st0705_runtime_contract_bytes,
        st0705_profile_registry_bytes,
        st0705_fixture_bytes,
        st0705_runtime_manifest_bytes,
        task_schema_bytes,
        evaluation_case_schema_bytes,
    )
    if any(
        type(item) is not bytes or not 1 <= len(item) <= _MAX_ARTIFACT_BYTES
        for item in supplied
    ):
        _fail()
    if (
        sha256_bytes(evaluation_case_schema_bytes)
        != _EXPECTED_EVALUATION_CASE_SCHEMA_SHA256
    ):
        _fail()
    manifest = _json_artifact(runtime_manifest_bytes)
    suite_root = _json_artifact(suite_registry_bytes)
    dataset_root = _json_artifact(dataset_bytes)
    _validate_runtime_manifest(
        manifest,
        runtime_contract_bytes=runtime_contract_bytes,
        suite_registry_bytes=suite_registry_bytes,
        dataset_bytes=dataset_bytes,
        st0705_runtime_contract_bytes=st0705_runtime_contract_bytes,
        st0705_profile_registry_bytes=st0705_profile_registry_bytes,
        st0705_fixture_bytes=st0705_fixture_bytes,
        st0705_runtime_manifest_bytes=st0705_runtime_manifest_bytes,
        task_schema_bytes=task_schema_bytes,
        evaluation_case_schema_bytes=evaluation_case_schema_bytes,
    )
    try:
        suite = _load_suite(suite_root)
        dataset = _load_dataset(
            dataset_root, evaluation_case_schema_bytes=evaluation_case_schema_bytes
        )
        profiles = load_trusted_ai_output_validation_profiles(
            st0705_profile_registry_bytes
        )
        evaluation_input = load_recorded_ai_output_validation_fixture(
            fixture_bytes=st0705_fixture_bytes,
            profiles=profiles,
            schema_bytes=task_schema_bytes,
        )
        report = evaluate_ai_output(evaluation_input)
        bundle = RecordedEvaluationBundle(
            runtime_contract_sha256=sha256_bytes(runtime_contract_bytes),
            runtime_manifest_sha256=sha256_bytes(runtime_manifest_bytes),
            suite=suite,
            dataset=dataset,
            reports=(report,),
        )
        bundle.require_valid()
        return bundle
    except RecordedAiEvaluationError:
        raise
    except Exception:
        _fail()


@final
class RecordedAiEvaluationBundleReader:
    """Immutable in-memory reader with no filesystem or provider capability."""

    __slots__ = ("_bundles",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        bundles: tuple[tuple[str, RecordedEvaluationBundle], ...],
    ) -> None:
        if (
            not _local_environment(environment)
            or type(bundles) is not tuple
            or len(bundles) > _MAX_COLLECTION
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or not item[0]
                or item[0] != item[0].strip()
                or len(item[0]) > 120
                or type(item[1]) is not RecordedEvaluationBundle
                for item in bundles
            )
            or len({item[0] for item in bundles}) != len(bundles)
        ):
            _fail()
        for _bundle_id, bundle in bundles:
            bundle.require_valid()
        self._bundles: Mapping[str, RecordedEvaluationBundle] = MappingProxyType(
            dict(bundles)
        )

    def get_bundle(self, bundle_id: str) -> RecordedEvaluationBundle | None:
        if (
            type(bundle_id) is not str
            or not bundle_id
            or bundle_id != bundle_id.strip()
            or len(bundle_id) > 120
        ):
            return None
        value = self._bundles.get(bundle_id)
        if value is None:
            return None
        try:
            value.require_valid()
        except Exception:
            return None
        return value


__all__ = [
    "RecordedAiEvaluationBundleReader",
    "RecordedAiEvaluationError",
    "load_recorded_evaluation_bundle",
]
