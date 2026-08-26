"""Strict caller-bytes adapter for the ST-1901 synthetic label fixture."""

from __future__ import annotations

import json
from types import MappingProxyType
from typing import Mapping, NoReturn, SupportsIndex, cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.model_judge_calibration import (
    CalibrationRisk,
    CalibrationSlice,
    CalibrationSplit,
    EvidenceStatus,
    HumanLabelResolution,
    JudgeCalibrationReadCommand,
    RecordedHumanJudgeLabel,
    RecordedHumanLabelBatch,
    canonical_json_bytes,
    sha256_bytes,
)


_MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
_MAX_CASES = 1_000
_EXPECTED_SOURCES = {
    "predecessor_contract": "55044e7b2f030298d5ee61932122e5c0821491b23189bb57b9affc8c47bc043d",
    "predecessor_manifest": "3547a1d0df3e33c7f793e5d6f520596e1e48a4121b238dc185f642b294976930",
    "predecessor_suite": "7eb7edb3bf0139b89fb903d852eca9e49edb0c87f2b16ae281213ba677cdd427",
    "evaluation_catalog": "a94e94a90c5029e6169c753d2924c08c0e3dd388cb5e1ea9f343674818322de3",
    "human_review_rubric": "a346b6c046cdcc384aeb5993fcd09ca61da62cb9b19e3b229572e8251b5010d9",
    "judge_output_schema": "8d832fe5c58a7cfeb8bafa8dab18c64aa45bdb56c3282bd3d7d6e14cad6e87d4",
    "judge_calibration_schema": "014393354a47070c69a83b204b73703bea2b4267468e3584387b65b11b077a7e",
    "judge_calibration_create_schema": "2ae3d1711f269ded555cec983adce2a0aa601d908bfc2c192b954594c574837a",
}


@final
class RecordedModelJudgeCalibrationError(ValueError):
    """Single redacted adapter failure with no rejected bytes in its state."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_RECORDED_MODEL_JUDGE_CALIBRATION")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded calibration errors are not serializable")


def _fail() -> NoReturn:
    raise RecordedModelJudgeCalibrationError() from None


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in values:
        if type(key) is not str or key in result:
            _fail()
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    del value
    _fail()


def _json_artifact(value: object) -> dict[str, object]:
    if type(value) is not bytes or not 1 <= len(value) <= _MAX_ARTIFACT_BYTES:
        _fail()
    try:
        parsed = json.loads(
            value,
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except RecordedModelJudgeCalibrationError:
        raise
    except Exception:
        _fail()
    if type(parsed) is not dict:
        _fail()
    root = cast(dict[str, object], parsed)
    if canonical_json_bytes(root) + b"\n" != value:
        _fail()
    return root


def _mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _fail()
    mapping = cast(dict[object, object], value)
    if frozenset(mapping) != keys:
        _fail()
    return {key: mapping[key] for key in keys}


def _items(value: object, *, maximum: int = _MAX_CASES) -> list[object]:
    if type(value) is not list:
        _fail()
    items = cast(list[object], value)
    if not 1 <= len(items) <= maximum:
        _fail()
    return items


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


def _integer(value: object, *, minimum: int = 0, maximum: int = 1_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
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


def _validate_sources(
    *, runtime_contract_bytes: bytes, source_bytes: Mapping[str, bytes]
) -> None:
    if (
        type(runtime_contract_bytes) is not bytes
        or not 1 <= len(runtime_contract_bytes) <= _MAX_ARTIFACT_BYTES
    ):
        _fail()
    if type(source_bytes) is not dict:
        _fail()
    sources = cast(dict[object, object], source_bytes)
    if frozenset(sources) != frozenset(_EXPECTED_SOURCES):
        _fail()
    for name in _EXPECTED_SOURCES:
        value = sources[name]
        if (
            type(value) is not bytes
            or not 1 <= len(value) <= _MAX_ARTIFACT_BYTES
        ):
            _fail()


def _load_case(value: object) -> RecordedHumanJudgeLabel:
    item = _mapping(
        value,
        frozenset(
            {
                "adjudicated_score",
                "adjudicator_role",
                "candidate_identity_blinded",
                "case_id",
                "case_sha256",
                "human_zero_tolerance",
                "judge_needs_human_adjudication",
                "judge_score",
                "judge_zero_tolerance",
                "primary_score",
                "prompt_author_conflict",
                "resolution",
                "risk",
                "secondary_score",
                "slice",
                "split",
            }
        ),
    )
    adjudicator = item["adjudicator_role"]
    if adjudicator is not None:
        adjudicator = _string(adjudicator)
    try:
        return RecordedHumanJudgeLabel(
            case_id=_string(item["case_id"]),
            split=CalibrationSplit(_string(item["split"])),
            slice=CalibrationSlice(_string(item["slice"])),
            risk=CalibrationRisk(_string(item["risk"])),
            primary_score=_integer(item["primary_score"], maximum=4),
            secondary_score=_integer(item["secondary_score"], maximum=4),
            adjudicated_score=_integer(item["adjudicated_score"], maximum=4),
            resolution=HumanLabelResolution(_string(item["resolution"])),
            adjudicator_role=adjudicator,
            human_zero_tolerance=_boolean(item["human_zero_tolerance"]),
            judge_score=_integer(item["judge_score"], maximum=4),
            judge_zero_tolerance=_boolean(item["judge_zero_tolerance"]),
            judge_needs_human_adjudication=_boolean(
                item["judge_needs_human_adjudication"]
            ),
            candidate_identity_blinded=_boolean(item["candidate_identity_blinded"]),
            prompt_author_conflict=_boolean(item["prompt_author_conflict"]),
            case_sha256=_sha(item["case_sha256"]),
        )
    except RecordedModelJudgeCalibrationError:
        raise
    except Exception:
        _fail()


def load_recorded_model_judge_calibration(
    *,
    fixture_bytes: bytes,
    runtime_contract_bytes: bytes,
    source_bytes: Mapping[str, bytes],
) -> RecordedHumanLabelBatch:
    """Load exact caller-supplied fixture bytes without repair or inference."""

    if type(fixture_bytes) is not bytes:
        _fail()
    _validate_sources(
        runtime_contract_bytes=runtime_contract_bytes, source_bytes=source_bytes
    )
    root = _mapping(
        _json_artifact(fixture_bytes),
        frozenset({"dataset", "document", "fixture_content_sha256"}),
    )
    expected_content_sha = _sha(root["fixture_content_sha256"])
    if (
        sha256_bytes(
            canonical_json_bytes(
                {"dataset": root["dataset"], "document": root["document"]}
            )
        )
        != expected_content_sha
    ):
        _fail()
    document = _mapping(
        root["document"],
        frozenset(
            {
                "actual_human_activity",
                "authority",
                "id",
                "production_eligible",
                "provider_mode",
                "release_authorized",
                "story_id",
                "version",
            }
        ),
    )
    if document != {
        "actual_human_activity": False,
        "authority": "NONE",
        "id": "RAOS-ST1901-RECORDED-HUMAN-JUDGE-LABELS-001",
        "production_eligible": False,
        "provider_mode": "RECORDED_SYNTHETIC_ONLY",
        "release_authorized": False,
        "story_id": "ST-1901",
        "version": "1.0.0",
    }:
        _fail()
    dataset = _mapping(
        root["dataset"],
        frozenset(
            {
                "actual_human_activity",
                "calibration_scope",
                "calibration_scope_sha256",
                "case_count",
                "cases",
                "dataset_id",
                "dataset_sha256",
                "dataset_version",
                "human_label_authority",
                "privacy",
                "provenance",
                "release_eligible",
                "representative_dataset",
            }
        ),
    )
    scope = _mapping(
        dataset["calibration_scope"],
        frozenset(
            {
                "category_scope",
                "domain_scope",
                "evaluated_task_code",
                "grader_version",
                "judge_prompt_binding_status",
                "judge_route_binding_status",
                "resolved_model_binding_status",
                "rubric_sha256",
            }
        ),
    )
    if scope != {
        "category_scope": "SYNTHETIC_GENERAL",
        "domain_scope": "RAOS_SYNTHETIC_EDITORIAL",
        "evaluated_task_code": "ai.opportunity_assessment.v1",
        "grader_version": "grader.model_judge.v1",
        "judge_prompt_binding_status": "RECORDED_SYNTHETIC_ONLY",
        "judge_route_binding_status": "RECORDED_SYNTHETIC_ONLY",
        "resolved_model_binding_status": "UNAVAILABLE",
        "rubric_sha256": _EXPECTED_SOURCES["human_review_rubric"],
    } or sha256_bytes(canonical_json_bytes(scope)) != _sha(
        dataset["calibration_scope_sha256"]
    ):
        _fail()
    privacy = _mapping(
        dataset["privacy"],
        frozenset(
            {
                "affiliate_economics_present",
                "personal_data_present",
                "raw_output_present",
                "raw_prompt_present",
                "raw_review_body_present",
                "raw_source_present",
            }
        ),
    )
    if any(_boolean(value) is not False for value in privacy.values()):
        _fail()
    cases = tuple(_load_case(item) for item in _items(dataset["cases"]))
    if _integer(dataset["case_count"], minimum=1) != len(cases):
        _fail()
    dataset_without_hash = {
        key: value for key, value in dataset.items() if key != "dataset_sha256"
    }
    if sha256_bytes(canonical_json_bytes(dataset_without_hash)) != _sha(
        dataset["dataset_sha256"]
    ):
        _fail()
    if (
        dataset["provenance"] != "RECORDED_SYNTHETIC_HUMAN_LABEL_FIXTURE"
        or dataset["human_label_authority"]
        != "RECORDED_GOLD_SIDE_WITHIN_SYNTHETIC_FIXTURE"
        or _boolean(dataset["actual_human_activity"]) is not False
        or _boolean(dataset["representative_dataset"]) is not False
        or _boolean(dataset["release_eligible"]) is not False
    ):
        _fail()
    try:
        batch = RecordedHumanLabelBatch(
            fixture_id=_string(document["id"]),
            fixture_file_sha256=sha256_bytes(fixture_bytes),
            fixture_content_sha256=expected_content_sha,
            dataset_id=_string(dataset["dataset_id"]),
            dataset_version=_string(dataset["dataset_version"]),
            dataset_sha256=_sha(dataset["dataset_sha256"]),
            calibration_scope_sha256=_sha(dataset["calibration_scope_sha256"]),
            predecessor_manifest_sha256=sha256_bytes(source_bytes["predecessor_manifest"]),
            evaluation_catalog_sha256=sha256_bytes(source_bytes["evaluation_catalog"]),
            rubric_sha256=sha256_bytes(source_bytes["human_review_rubric"]),
            cases=cases,
            actual_human_activity=False,
            representative_dataset=False,
            release_eligible=False,
            resolved_model_binding_status=EvidenceStatus.UNAVAILABLE,
        )
        batch.require_valid()
        return batch
    except RecordedModelJudgeCalibrationError:
        raise
    except Exception:
        _fail()


@final
class RecordedModelJudgeCalibrationReader:
    """Immutable process-local reader; repeated exact reads are idempotent."""

    __slots__ = ("_batches",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        batches: tuple[tuple[str, RecordedHumanLabelBatch], ...],
    ) -> None:
        if (
            not _local_environment(environment)
            or type(batches) is not tuple
            or not 1 <= len(batches) <= 64
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or not item[0]
                or item[0] != item[0].strip()
                or len(item[0]) > 256
                or type(item[1]) is not RecordedHumanLabelBatch
                for item in batches
            )
            or len({item[0] for item in batches}) != len(batches)
        ):
            _fail()
        for fixture_id, batch in batches:
            batch.require_valid()
            if fixture_id != batch.fixture_id:
                _fail()
        self._batches: Mapping[str, RecordedHumanLabelBatch] = MappingProxyType(
            dict(batches)
        )

    def read(self, command: object) -> RecordedHumanLabelBatch | None:
        if type(command) is not JudgeCalibrationReadCommand:
            return None
        value = self._batches.get(command.fixture_id)
        if value is None or command.fixture_file_sha256 != value.fixture_file_sha256:
            return None
        try:
            value.require_valid()
        except Exception:
            return None
        return value


__all__ = [
    "RecordedModelJudgeCalibrationError",
    "RecordedModelJudgeCalibrationReader",
    "load_recorded_model_judge_calibration",
]
