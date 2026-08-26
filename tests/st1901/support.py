"""Shared fixed inputs and safe mutation helpers for ST-1901 tests."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Iterable, cast


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
for candidate in (str(PYTHON_ROOT), str(REPOSITORY_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from raos.adapters.recorded_model_judge_calibration import (  # noqa: E402
    RecordedModelJudgeCalibrationReader,
    load_recorded_model_judge_calibration,
)
from raos.domain.ai.model_judge_calibration import (  # noqa: E402
    JudgeCalibrationReadCommand,
    CalibrationRisk,
    CalibrationSlice,
    CalibrationSplit,
    HumanLabelResolution,
    RecordedHumanJudgeLabel,
    RecordedHumanLabelBatch,
    canonical_json_bytes,
    sha256_bytes,
)


CONTRACT_PATH = Path("changes/st-1901/contracts/model-judge-calibration.v1.yaml")
FIXTURE_PATH = Path(
    "changes/st-1901/fixtures/recorded/model-judge-human-labels.synthetic.v1.json"
)
REPORT_PATH = Path(
    "changes/st-1901/generated/model-judge-calibration-evaluation.v1.json"
)
MANIFEST_PATH = Path("changes/st-1901/manifest.yaml")

SOURCE_PATHS = {
    "predecessor_contract": Path(
        "changes/st-0707/contracts/evaluation-harness-runtime.v1.yaml"
    ),
    "predecessor_manifest": Path("changes/st-0707/runtime-manifest.v1.json"),
    "predecessor_suite": Path(
        "changes/st-0707/generated/evaluation-suite-registry.v1.json"
    ),
    "evaluation_catalog": Path(
        "contracts/raos-v0.4/contracts/ai/RAOS_05_evaluation_catalog_v0.1.yaml"
    ),
    "human_review_rubric": Path(
        "contracts/raos-v0.4/contracts/ai/RAOS_05_human_review_rubric_v0.1.yaml"
    ),
    "judge_output_schema": Path(
        "contracts/raos-v0.4/contracts/ai/schemas/eval/judge_output.v1.schema.json"
    ),
    "judge_calibration_schema": Path(
        "contracts/raos-v0.4/contracts/schemas/ai-governance/"
        "judge-calibration.v1.schema.json"
    ),
    "judge_calibration_create_schema": Path(
        "contracts/raos-v0.4/contracts/schemas/ai-governance/"
        "judge-calibration-create-request.v1.schema.json"
    ),
}


def source_bytes() -> dict[str, bytes]:
    return {
        name: (REPOSITORY_ROOT / path).read_bytes()
        for name, path in SOURCE_PATHS.items()
    }


def fixture_bytes() -> bytes:
    return (REPOSITORY_ROOT / FIXTURE_PATH).read_bytes()


def load_batch(payload: bytes | None = None) -> RecordedHumanLabelBatch:
    return load_recorded_model_judge_calibration(
        fixture_bytes=fixture_bytes() if payload is None else payload,
        runtime_contract_bytes=(REPOSITORY_ROOT / CONTRACT_PATH).read_bytes(),
        source_bytes=source_bytes(),
    )


def command_for(batch: RecordedHumanLabelBatch) -> JudgeCalibrationReadCommand:
    return JudgeCalibrationReadCommand(
        fixture_id=batch.fixture_id,
        fixture_file_sha256=batch.fixture_file_sha256,
    )


def reader_for(
    batch: RecordedHumanLabelBatch,
) -> RecordedModelJudgeCalibrationReader:
    from raos.config.runtime import RuntimeEnvironment

    return RecordedModelJudgeCalibrationReader(
        environment=RuntimeEnvironment.CI,
        batches=((batch.fixture_id, batch),),
    )


def relabel(
    label: RecordedHumanJudgeLabel,
    **changes: object,
) -> RecordedHumanJudgeLabel:
    allowed = {
        "adjudicated_score",
        "adjudicator_role",
        "candidate_identity_blinded",
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
    if not set(changes).issubset(allowed):
        raise ValueError("unsupported test label mutation")
    split = cast(CalibrationSplit, changes.get("split", label.split))
    slice_value = cast(CalibrationSlice, changes.get("slice", label.slice))
    risk = cast(CalibrationRisk, changes.get("risk", label.risk))
    primary_score = cast(int, changes.get("primary_score", label.primary_score))
    secondary_score = cast(int, changes.get("secondary_score", label.secondary_score))
    adjudicated_score = cast(
        int, changes.get("adjudicated_score", label.adjudicated_score)
    )
    resolution = cast(HumanLabelResolution, changes.get("resolution", label.resolution))
    adjudicator_role = cast(
        str | None, changes.get("adjudicator_role", label.adjudicator_role)
    )
    human_zero_tolerance = cast(
        bool,
        changes.get("human_zero_tolerance", label.human_zero_tolerance),
    )
    judge_score = cast(int, changes.get("judge_score", label.judge_score))
    judge_zero_tolerance = cast(
        bool, changes.get("judge_zero_tolerance", label.judge_zero_tolerance)
    )
    needs_adjudication = cast(
        bool,
        changes.get(
            "judge_needs_human_adjudication",
            label.judge_needs_human_adjudication,
        ),
    )
    identity_blinded = cast(
        bool,
        changes.get("candidate_identity_blinded", label.candidate_identity_blinded),
    )
    prompt_author_conflict = cast(
        bool,
        changes.get("prompt_author_conflict", label.prompt_author_conflict),
    )
    document = {
        "adjudicated_score": adjudicated_score,
        "adjudicator_role": adjudicator_role,
        "candidate_identity_blinded": identity_blinded,
        "case_id": label.case_id,
        "human_zero_tolerance": human_zero_tolerance,
        "judge_needs_human_adjudication": needs_adjudication,
        "judge_score": judge_score,
        "judge_zero_tolerance": judge_zero_tolerance,
        "primary_score": primary_score,
        "prompt_author_conflict": prompt_author_conflict,
        "resolution": resolution.value,
        "risk": risk.value,
        "secondary_score": secondary_score,
        "slice": slice_value.value,
        "split": split.value,
    }
    return RecordedHumanJudgeLabel(
        case_id=label.case_id,
        split=split,
        slice=slice_value,
        risk=risk,
        primary_score=primary_score,
        secondary_score=secondary_score,
        adjudicated_score=adjudicated_score,
        resolution=resolution,
        adjudicator_role=adjudicator_role,
        human_zero_tolerance=human_zero_tolerance,
        judge_score=judge_score,
        judge_zero_tolerance=judge_zero_tolerance,
        judge_needs_human_adjudication=needs_adjudication,
        candidate_identity_blinded=identity_blinded,
        prompt_author_conflict=prompt_author_conflict,
        case_sha256=sha256_bytes(canonical_json_bytes(document)),
    )


def batch_with_cases(
    original: RecordedHumanLabelBatch,
    cases: Iterable[RecordedHumanJudgeLabel],
) -> RecordedHumanLabelBatch:
    selected = tuple(cases)
    return RecordedHumanLabelBatch(
        fixture_id=original.fixture_id,
        fixture_file_sha256=original.fixture_file_sha256,
        fixture_content_sha256=original.fixture_content_sha256,
        dataset_id=original.dataset_id,
        dataset_version=original.dataset_version,
        dataset_sha256=original.dataset_sha256,
        calibration_scope_sha256=original.calibration_scope_sha256,
        predecessor_manifest_sha256=original.predecessor_manifest_sha256,
        evaluation_catalog_sha256=original.evaluation_catalog_sha256,
        rubric_sha256=original.rubric_sha256,
        cases=selected,
    )
