from __future__ import annotations

from pathlib import Path

from raos.adapters.recorded_live_evaluation import (
    load_recorded_live_evaluation_result,
)
from raos.domain.ai.live_evaluation import RecordedLiveEvaluationResult


ROOT = Path(__file__).resolve().parents[2]

PATHS = {
    "runtime_contract_bytes": ROOT
    / "changes/st-0708/contracts/recorded-live-evaluation-runtime.v2.yaml",
    "runtime_manifest_bytes": ROOT / "changes/st-0708/runtime-manifest.v2.json",
    "request_artifact_bytes": ROOT
    / "changes/st-0708/generated/recorded-live-evaluation-request.v2.json",
    "report_artifact_bytes": ROOT
    / "changes/st-0708/generated/recorded-live-evaluation-report.v2.json",
    "historical_reference_plan_bytes": ROOT
    / "changes/st-0708/generated/openai-live-bounded-evaluation-reference-plan.v1.json",
    "publication_helper_bytes": ROOT / "scripts/secure_generated_publication.py",
    "evaluation_catalog_bytes": ROOT
    / "contracts/raos-v0.4/contracts/ai/RAOS_05_evaluation_catalog_v0.1.yaml",
    "task_catalog_bytes": ROOT
    / "contracts/raos-v0.4/contracts/ai/RAOS_05_ai_task_catalog_v0.1.yaml",
    "routing_catalog_bytes": ROOT
    / "contracts/raos-v0.4/contracts/ai/RAOS_05_model_routing_catalog_v0.1.yaml",
    "open_decisions_bytes": ROOT
    / "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
    "test_catalog_bytes": ROOT
    / "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
    "story_catalog_bytes": ROOT
    / "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
    "st0703_adapter_contract_bytes": ROOT
    / "changes/st-0703/contracts/openai-responses-adapter.v1.yaml",
    "st0703_fixture_registry_bytes": ROOT
    / "changes/st-0703/generated/recorded-fixture-registry.v1.json",
    "st0703_success_fixture_bytes": ROOT
    / "changes/st-0703/fixtures/recorded/success-structured.json",
    "st0703_binding_source_bytes": ROOT / "tests/st0703/test_adapter.py",
    "st0707_runtime_contract_bytes": ROOT
    / "changes/st-0707/contracts/evaluation-harness-runtime.v1.yaml",
    "st0707_runtime_manifest_bytes": ROOT / "changes/st-0707/runtime-manifest.v1.json",
    "st0707_suite_registry_bytes": ROOT
    / "changes/st-0707/generated/evaluation-suite-registry.v1.json",
    "st0707_dataset_bytes": ROOT
    / "changes/st-0707/generated/locked-synthetic-holdout.v1.json",
    "st0705_runtime_contract_bytes": ROOT
    / "changes/st-0705/contracts/ai-output-validation-runtime.v1.yaml",
    "st0705_profile_registry_bytes": ROOT
    / "changes/st-0705/generated/ai-output-validation-profiles.v1.json",
    "st0705_fixture_bytes": ROOT
    / "changes/st-0705/generated/ai-output-validation-pass.v1.json",
    "st0705_runtime_manifest_bytes": ROOT / "changes/st-0705/runtime-manifest.v1.yaml",
    "st0707_task_schema_bytes": ROOT
    / "contracts/raos-v0.4/contracts/ai/schemas/tasks/ai.opportunity_assessment.v1.output.schema.json",
    "st0707_evaluation_case_schema_bytes": ROOT
    / "contracts/raos-v0.4/contracts/ai/schemas/eval/evaluation_case.v1.schema.json",
}


def artifact_bytes(**overrides: bytes) -> dict[str, bytes]:
    values = {name: path.read_bytes() for name, path in PATHS.items()}
    values.update(overrides)
    return values


def load_result(**overrides: bytes) -> RecordedLiveEvaluationResult:
    return load_recorded_live_evaluation_result(**artifact_bytes(**overrides))
