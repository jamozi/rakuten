from __future__ import annotations

from pathlib import Path

from raos.adapters.recorded_ai_evaluation import load_recorded_evaluation_bundle
from raos.domain.ai.evaluation_harness import RecordedEvaluationBundle


ROOT = Path(__file__).resolve().parents[2]

PATHS = {
    "runtime_contract_bytes": ROOT
    / "changes/st-0707/contracts/evaluation-harness-runtime.v1.yaml",
    "runtime_manifest_bytes": ROOT / "changes/st-0707/runtime-manifest.v1.json",
    "suite_registry_bytes": ROOT
    / "changes/st-0707/generated/evaluation-suite-registry.v1.json",
    "dataset_bytes": ROOT
    / "changes/st-0707/generated/locked-synthetic-holdout.v1.json",
    "st0705_runtime_contract_bytes": ROOT
    / "changes/st-0705/contracts/ai-output-validation-runtime.v1.yaml",
    "st0705_profile_registry_bytes": ROOT
    / "changes/st-0705/generated/ai-output-validation-profiles.v1.json",
    "st0705_fixture_bytes": ROOT
    / "changes/st-0705/generated/ai-output-validation-pass.v1.json",
    "st0705_runtime_manifest_bytes": ROOT / "changes/st-0705/runtime-manifest.v1.yaml",
    "task_schema_bytes": ROOT
    / "contracts/raos-v0.4/contracts/ai/schemas/tasks/ai.opportunity_assessment.v1.output.schema.json",
    "evaluation_case_schema_bytes": ROOT
    / "contracts/raos-v0.4/contracts/ai/schemas/eval/evaluation_case.v1.schema.json",
}


def artifact_bytes(**overrides: bytes) -> dict[str, bytes]:
    values = {name: path.read_bytes() for name, path in PATHS.items()}
    values.update(overrides)
    return values


def load_bundle(**overrides: bytes) -> RecordedEvaluationBundle:
    return load_recorded_evaluation_bundle(**artifact_bytes(**overrides))
