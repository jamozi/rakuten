"""Canonical byte bindings and static trust-boundary checks for ST-0707."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json

import yaml

from conftest import REPOSITORY_ROOT
from raos.application.ai.evaluation import BootstrapEvaluationRunner
from raos.domain.ai.evaluation import (
    BootstrapEvaluationReport,
    DeterministicCheckCode,
    EvaluationRisk,
    EvaluationSplit,
    ExpectedDisposition,
    ZeroToleranceClass,
)


DOMAIN = REPOSITORY_ROOT / "python/raos/domain/ai/evaluation.py"
APPLICATION = REPOSITORY_ROOT / "python/raos/application/ai/evaluation.py"
ST0705_CONTRACT = REPOSITORY_ROOT / (
    "changes/st-0705/contracts/ai-output-validation-reference-plan.v1.yaml"
)
ST0705_GENERATED = REPOSITORY_ROOT / (
    "changes/st-0705/generated/ai-output-validation-reference-plan.v1.json"
)
ST0705_MANIFEST = REPOSITORY_ROOT / "changes/st-0705/manifest.yaml"
CATALOG = REPOSITORY_ROOT / (
    "contracts/raos-v0.4/contracts/ai/RAOS_05_evaluation_catalog_v0.1.yaml"
)
CASE_SCHEMA = REPOSITORY_ROOT / (
    "contracts/raos-v0.4/contracts/ai/schemas/eval/evaluation_case.v1.schema.json"
)
DATASET_TEMPLATE = REPOSITORY_ROOT / (
    "contracts/raos-v0.4/contracts/ai/RAOS_05_eval_dataset_manifest_template_v0.1.yaml"
)
RUBRIC = REPOSITORY_ROOT / (
    "contracts/raos-v0.4/contracts/ai/RAOS_05_human_review_rubric_v0.1.yaml"
)
QUALITY_GATES = REPOSITORY_ROOT / (
    "contracts/raos-v0.4/contracts/ai/RAOS_05_quality_gate_catalog_v0.1.yaml"
)
RELEASE_TEMPLATE = REPOSITORY_ROOT / (
    "contracts/raos-v0.4/contracts/ai/RAOS_05_release_decision_template_v0.1.yaml"
)
FAILURE_TAXONOMY = REPOSITORY_ROOT / (
    "contracts/raos-v0.4/contracts/ai/RAOS_05_failure_taxonomy_v0.1.yaml"
)
SECURITY_CONTROLS = REPOSITORY_ROOT / (
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
)
MISSING_BOOTSTRAP_PAYLOADS = (
    REPOSITORY_ROOT
    / "contracts/raos-v0.4/contracts/ai/eval_cases/bootstrap_cases_v0.1.jsonl",
    REPOSITORY_ROOT
    / "docs/upstream/key_documents/eval_cases/bootstrap_cases_v0.1.jsonl",
)


EXPECTED_HASHES = {
    ST0705_CONTRACT: "ea935831a1bb667229ae5a5495a27a801b9c21ab3c3ddbe53e266b8f7c311c42",
    ST0705_GENERATED: "668706fa3629a0f730d31666561065dfe5954b5a61e5afe5df03326a830e69da",
    ST0705_MANIFEST: "27b384123442c1d8f557e6dd4944e07fb358a218221e8e90a4c77744de0be05c",
    CATALOG: "a94e94a90c5029e6169c753d2924c08c0e3dd388cb5e1ea9f343674818322de3",
    CASE_SCHEMA: "363094954df80ab4bd8c28804d27e4634f79210fcd28fa82062ea49729549b7a",
    DATASET_TEMPLATE: "3215018516a010a93b14d0e90f2b944532892c626ea9db7ea54cb578796b2c51",
    RUBRIC: "a346b6c046cdcc384aeb5993fcd09ca61da62cb9b19e3b229572e8251b5010d9",
    QUALITY_GATES: "a4664f082662ced52c3316ffa95ba0a7e0362d87401871e7fc7f5fbb6a77ecdc",
    RELEASE_TEMPLATE: "87be8f2b473a047a03c6b607834273bc499a584404f1bc94afd4188dfc8d1a44",
    FAILURE_TAXONOMY: "55db49d67678a1d8052fd4da9035ebfe2516913659c528bccd9f1a0313b38504",
    SECURITY_CONTROLS: "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
}


def test_exact_predecessor_and_canonical_source_bytes_are_pinned() -> None:
    assert {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in EXPECTED_HASHES
    } == EXPECTED_HASHES
    assert all(not path.exists() for path in MISSING_BOOTSTRAP_PAYLOADS)
    assert not tuple(REPOSITORY_ROOT.rglob("bootstrap_cases_v0.1.jsonl"))


def test_st0705_remains_non_executable_unevaluable_and_action_free() -> None:
    contract = yaml.safe_load(ST0705_CONTRACT.read_bytes())
    generated = json.loads(ST0705_GENERATED.read_bytes())
    assert contract["document"]["executable"] is False
    assert contract["document"]["decision"] == "NOT_READY"
    assert contract["document"]["story_acceptance"] is False
    assert contract["evaluation_boundary"] == {
        "candidate_validation": "UNEVALUABLE",
        "content_validation": "UNEVALUABLE",
        "decision": "NOT_READY",
        "story_acceptance_satisfied": False,
        "schema_only_acceptance_forbidden": True,
        "event_emission": False,
    }
    assert generated["document"]["executable"] is False
    assert generated["evaluation_boundary"] == contract["evaluation_boundary"]
    assert generated["execution_state"]["event"] == "NOT_EXECUTED"
    assert generated["execution_state"]["external_actions"] == []
    assert all(
        type(value) is int and value == 0
        for value in generated["execution_state"]["action_counts"].values()
    )


def test_exact_case_enum_and_zero_tolerance_vocabularies_match_canonical() -> None:
    schema = json.loads(CASE_SCHEMA.read_bytes())
    rubric = yaml.safe_load(RUBRIC.read_bytes())
    assert {item.value for item in EvaluationSplit} == set(
        schema["properties"]["split"]["enum"]
    )
    assert [item.value for item in EvaluationRisk] == schema["properties"][
        "risk_level"
    ]["enum"]
    assert [item.value for item in ExpectedDisposition] == schema["properties"][
        "expected_disposition"
    ]["enum"]
    assert [item.value for item in ZeroToleranceClass] == rubric["zero_tolerance"]
    assert [item.value for item in DeterministicCheckCode] == [
        "SCHEMA_VALID",
        "RESPONSE_COMPLETE",
        "EVIDENCE_REFERENCE_VALID",
        "NUMERIC_EXACTNESS",
        "PRODUCT_IDENTITY_ACCURATE",
        "FABRICATED_EXPERIENCE_ABSENT",
        "RAKUTEN_REVIEW_BODY_ABSENT",
        "AFFILIATE_BIAS_ABSENT",
        "PROMPT_INJECTION_NOT_FOLLOWED",
        "SECRET_OR_RESTRICTED_DATA_ABSENT",
    ]


def _public_methods(candidate: type[object]) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(candidate)
        if not name.startswith("_") and callable(member)
    }


def test_public_surface_has_one_pure_run_and_no_action_methods() -> None:
    assert _public_methods(BootstrapEvaluationRunner) == {"run"}
    action_names = {
        "activate",
        "approve",
        "clear",
        "delete",
        "export",
        "persist",
        "publish",
        "release",
    }
    assert not (_public_methods(BootstrapEvaluationReport) & action_names)


def test_ast_is_inward_only_and_has_no_external_capability_or_st0706_import() -> None:
    banned_import_roots = {
        "asyncio",
        "boto3",
        "celery",
        "concurrent",
        "fastapi",
        "http",
        "httpx",
        "logging",
        "multiprocessing",
        "openai",
        "os",
        "pathlib",
        "requests",
        "socket",
        "sqlalchemy",
        "subprocess",
        "threading",
        "urllib",
    }
    banned_calls = {
        "connect",
        "create_task",
        "emit",
        "execute",
        "getenv",
        "open",
        "publish",
        "request",
        "send",
        "spawn",
        "start",
        "system",
        "write",
    }
    source = ""
    imported: set[str] = set()
    called: set[str] = set()
    for path in (DOMAIN, APPLICATION):
        text = path.read_text(encoding="utf-8")
        source += text
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    called.add(node.func.attr)
    assert "st0706" not in source.lower()
    assert not any(name.split(".")[0] in banned_import_roots for name in imported)
    assert not (called & banned_calls)
    application_imports = {name for name in imported if name.startswith("raos.")}
    assert application_imports == {"raos.domain.ai.evaluation"}
