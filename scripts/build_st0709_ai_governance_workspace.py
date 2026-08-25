#!/usr/bin/env python3
"""Build the deterministic, recorded-only ST-0709 governance projection."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import NoReturn, cast

import yaml

from raos.adapters.recorded_ai_evaluation import load_recorded_evaluation_bundle
from raos.adapters.recorded_live_evaluation import (
    load_recorded_live_evaluation_result,
)
from raos.application.ai.evaluation_harness import RecordedEvaluationHarness
from raos.domain.ai.live_evaluation import (
    evaluate_recorded_live_evidence,
    report_projection,
)

try:
    from scripts import secure_generated_publication as _publication
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    import secure_generated_publication as _publication  # type: ignore[import-not-found, no-redef]


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = Path("changes/st-0709/contracts/ai-governance-workspace.v2.yaml")
FIXTURE_PATH = Path("changes/st-0709/generated/ai-governance-workspace.v2.json")
TYPESCRIPT_PATH = Path("packages/web-ui/src/ai-governance-recorded.v2.ts")
MANIFEST_PATH = Path("changes/st-0709/runtime-manifest.v2.json")
MAX_SOURCE_BYTES = 8 * 1024 * 1024

ST0707_PATHS = {
    "runtime_contract_bytes": Path(
        "changes/st-0707/contracts/evaluation-harness-runtime.v1.yaml"
    ),
    "runtime_manifest_bytes": Path("changes/st-0707/runtime-manifest.v1.json"),
    "suite_registry_bytes": Path(
        "changes/st-0707/generated/evaluation-suite-registry.v1.json"
    ),
    "dataset_bytes": Path("changes/st-0707/generated/locked-synthetic-holdout.v1.json"),
    "st0705_runtime_contract_bytes": Path(
        "changes/st-0705/contracts/ai-output-validation-runtime.v1.yaml"
    ),
    "st0705_profile_registry_bytes": Path(
        "changes/st-0705/generated/ai-output-validation-profiles.v1.json"
    ),
    "st0705_fixture_bytes": Path(
        "changes/st-0705/generated/ai-output-validation-pass.v1.json"
    ),
    "st0705_runtime_manifest_bytes": Path("changes/st-0705/runtime-manifest.v1.yaml"),
    "task_schema_bytes": Path(
        "contracts/raos-v0.4/contracts/ai/schemas/tasks/"
        "ai.opportunity_assessment.v1.output.schema.json"
    ),
    "evaluation_case_schema_bytes": Path(
        "contracts/raos-v0.4/contracts/ai/schemas/eval/evaluation_case.v1.schema.json"
    ),
}

ST0708_PATHS = {
    "runtime_contract_bytes": Path(
        "changes/st-0708/contracts/recorded-live-evaluation-runtime.v2.yaml"
    ),
    "runtime_manifest_bytes": Path("changes/st-0708/runtime-manifest.v2.json"),
    "request_artifact_bytes": Path(
        "changes/st-0708/generated/recorded-live-evaluation-request.v2.json"
    ),
    "report_artifact_bytes": Path(
        "changes/st-0708/generated/recorded-live-evaluation-report.v2.json"
    ),
    "historical_reference_plan_bytes": Path(
        "changes/st-0708/generated/"
        "openai-live-bounded-evaluation-reference-plan.v1.json"
    ),
    "publication_helper_bytes": Path("scripts/secure_generated_publication.py"),
    "evaluation_catalog_bytes": Path(
        "contracts/raos-v0.4/contracts/ai/RAOS_05_evaluation_catalog_v0.1.yaml"
    ),
    "task_catalog_bytes": Path(
        "contracts/raos-v0.4/contracts/ai/RAOS_05_ai_task_catalog_v0.1.yaml"
    ),
    "routing_catalog_bytes": Path(
        "contracts/raos-v0.4/contracts/ai/RAOS_05_model_routing_catalog_v0.1.yaml"
    ),
    "open_decisions_bytes": Path(
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
    ),
    "test_catalog_bytes": Path(
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
    ),
    "story_catalog_bytes": Path(
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
    ),
    "st0703_adapter_contract_bytes": Path(
        "changes/st-0703/contracts/openai-responses-adapter.v1.yaml"
    ),
    "st0703_fixture_registry_bytes": Path(
        "changes/st-0703/generated/recorded-fixture-registry.v1.json"
    ),
    "st0703_success_fixture_bytes": Path(
        "changes/st-0703/fixtures/recorded/success-structured.json"
    ),
    "st0703_binding_source_bytes": Path("tests/st0703/test_adapter.py"),
    "st0707_runtime_contract_bytes": ST0707_PATHS["runtime_contract_bytes"],
    "st0707_runtime_manifest_bytes": ST0707_PATHS["runtime_manifest_bytes"],
    "st0707_suite_registry_bytes": ST0707_PATHS["suite_registry_bytes"],
    "st0707_dataset_bytes": ST0707_PATHS["dataset_bytes"],
    "st0705_runtime_contract_bytes": ST0707_PATHS["st0705_runtime_contract_bytes"],
    "st0705_profile_registry_bytes": ST0707_PATHS["st0705_profile_registry_bytes"],
    "st0705_fixture_bytes": ST0707_PATHS["st0705_fixture_bytes"],
    "st0705_runtime_manifest_bytes": ST0707_PATHS["st0705_runtime_manifest_bytes"],
    "st0707_task_schema_bytes": ST0707_PATHS["task_schema_bytes"],
    "st0707_evaluation_case_schema_bytes": ST0707_PATHS["evaluation_case_schema_bytes"],
}


class St0709BuildError(RuntimeError):
    """Stable build refusal without source material echo."""


def _fail() -> NoReturn:
    raise St0709BuildError("ST0709_AI_GOVERNANCE_BUILD_FAILED") from None


def _sha(value: bytes) -> str:
    if type(value) is not bytes:
        _fail()
    return hashlib.sha256(value).hexdigest()


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        _fail()


def _json_output(value: object) -> bytes:
    return _canonical(value) + b"\n"


def _repository_path(root: object, relative: object) -> Path:
    if (
        not isinstance(root, Path)
        or not isinstance(relative, Path)
        or relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail()
    absolute_root = Path(os.path.abspath(root))
    candidate = Path(os.path.abspath(absolute_root / relative))
    try:
        candidate.relative_to(absolute_root)
    except ValueError:
        _fail()
    return candidate


def _read_regular(root: Path, relative: Path) -> bytes:
    path = _repository_path(root, relative)
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_SOURCE_BYTES
        ):
            _fail()
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
            ):
                _fail()
            chunks: list[bytes] = []
            remaining = opened.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    _fail()
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                _fail()
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
                _fail()
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except St0709BuildError:
        raise
    except Exception:
        _fail()


def _mapping(value: object, keys: frozenset[str] | None = None) -> dict[str, object]:
    if type(value) is not dict:
        _fail()
    result = cast(dict[str, object], value)
    if keys is not None and frozenset(result) != keys:
        _fail()
    return result


def _list(value: object, *, maximum: int = 256) -> list[object]:
    if type(value) is not list:
        _fail()
    items = cast(list[object], value)
    if len(items) > maximum:
        _fail()
    return items


def _string(value: object, maximum: int = 512) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or "\x00" in value
    ):
        _fail()
    return value


def _integer(value: object, maximum: int = 10_000_000) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        _fail()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _parse_json(payload: bytes) -> object:
    def reject_duplicate(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                _fail()
            result[key] = value
        return result

    try:
        return json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicate,
            parse_constant=lambda _value: _fail(),
        )
    except St0709BuildError:
        raise
    except Exception:
        _fail()


def _load_contract(root: Path) -> tuple[dict[str, object], bytes]:
    payload = _read_regular(root, CONTRACT_PATH)
    try:
        contract = _mapping(yaml.safe_load(payload))
    except yaml.YAMLError:
        _fail()
    if frozenset(contract) != frozenset(
        {
            "document",
            "formal_status",
            "outputs",
            "owned_runtime_sources",
            "projection_policy",
            "release_guard",
            "screen",
            "sections",
            "source_bindings",
        }
    ):
        _fail()
    document = _mapping(contract["document"])
    expected_false = (
        "default_enabled",
        "route_registration_allowed",
        "provider_allowed",
        "credential_allowed",
        "network_allowed",
        "persistence_allowed",
        "activation_allowed",
        "approval_allowed",
        "publication_allowed",
        "release_allowed",
        "production_write_allowed",
    )
    if (
        document.get("id") != "RAOS-ST0709-AI-GOVERNANCE-WORKSPACE-002"
        or document.get("version") != "2.0.0"
        or document.get("story_id") != "ST-0709"
        or document.get("status") != "LOCAL_IMPLEMENTATION_COMPLETE"
        or document.get("authority") != "NONE"
        or document.get("environment") != "LOCAL_RECORDED_ONLY"
        or any(document.get(key) is not False for key in expected_false)
    ):
        _fail()
    screen = _mapping(contract["screen"])
    if screen != {
        "id": "GOV-001",
        "name": "AI Governance",
        "route": "/admin/governance/ai",
        "area": "governance",
        "roles": ["PRODUCT_OWNER", "MANAGING_EDITOR", "SECURITY_AUDITOR"],
        "purpose": "Task/Prompt/Route/Evaluation/Releaseを表示",
        "story_objective": "Task/Prompt/Route/Eval/Costを表示",
        "mvp": True,
        "critical_action": False,
        "api_dependencies": [],
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "canonical_implementation_status": "NOT_STARTED",
        "canonical_runtime_verification": "NOT_EXECUTED",
    }:
        _fail()
    sections = _list(contract["sections"], maximum=6)
    if sections != [
        {
            "id": "TASK",
            "label": "Task",
            "source": "ST-0701",
            "availability": "AVAILABLE_RECORDED_CONFIGURATION",
        },
        {
            "id": "PROMPT",
            "label": "Prompt",
            "source": "ST-0701",
            "availability": "AVAILABLE_RECORDED_CONFIGURATION",
        },
        {
            "id": "ROUTE",
            "label": "Route",
            "source": "ST-0701",
            "availability": "AVAILABLE_RECORDED_CONFIGURATION",
        },
        {
            "id": "EVALUATION",
            "label": "Evaluation",
            "source": "ST-0707",
            "availability": "AVAILABLE_RECORDED_SYNTHETIC",
        },
        {
            "id": "RELEASE",
            "label": "Release",
            "source": "ST-0708",
            "availability": "AVAILABLE_REFUSAL_PROPOSAL",
        },
        {
            "id": "COST",
            "label": "Cost",
            "source": "ST-0701+ST-0706",
            "availability": "PARTIAL_CONFIGURED_LIMITS_ONLY",
        },
    ]:
        _fail()
    projection = _mapping(contract["projection_policy"])
    expected_projection = {
        "task_registry_count": 12,
        "prompt_registry_count": 12,
        "unique_route_count": 5,
        "evaluation_row_count": 1,
        "release_row_count": 1,
        "cost_limit_row_count": 12,
        "raw_prompt_allowed": False,
        "raw_source_allowed": False,
        "raw_provider_response_allowed": False,
        "raw_job_artifact_allowed": False,
        "secret_allowed": False,
        "personal_data_allowed": False,
        "review_body_allowed": False,
        "actual_cost_available": False,
        "unknown_cost_is_zero": False,
        "catalog_enabled_is_activation": False,
        "status_requires_text_code_icon": True,
        "status_color_only_allowed": False,
        "table_caption_required": True,
        "column_headers_required": True,
        "row_header_required": True,
    }
    if projection != expected_projection:
        _fail()
    guard = _mapping(contract["release_guard"])
    if guard != {
        "direct_activation": False,
        "action_count": 0,
        "approval_required": True,
        "approval_authority": "HUMAN_ONLY",
        "route_mutation": False,
        "provider_call": False,
        "publication": False,
        "release": False,
        "production_write": False,
    }:
        _fail()
    outputs = _mapping(contract["outputs"])
    if outputs != {
        "fixture": FIXTURE_PATH.as_posix(),
        "typescript_binding": TYPESCRIPT_PATH.as_posix(),
        "runtime_manifest": MANIFEST_PATH.as_posix(),
    }:
        _fail()
    return contract, payload


def _declared_bindings(root: Path, contract: dict[str, object]) -> list[dict[str, str]]:
    source = _mapping(contract["source_bindings"])
    if frozenset(source) != frozenset({"canonical", "dependencies", "helper"}):
        _fail()
    result: list[dict[str, str]] = []
    for scope in ("canonical", "dependencies"):
        values = _mapping(source[scope])
        for code in sorted(values):
            binding = _mapping(values[code], frozenset({"path", "sha256"}))
            path = Path(_string(binding["path"]))
            expected = _string(binding["sha256"], 64)
            if len(expected) != 64 or _sha(_read_regular(root, path)) != expected:
                _fail()
            result.append(
                {
                    "code": code,
                    "path": path.as_posix(),
                    "scope": scope.upper(),
                    "sha256": expected,
                }
            )
    helper = _mapping(source["helper"], frozenset({"path", "sha256"}))
    helper_path = Path(_string(helper["path"]))
    helper_sha = _string(helper["sha256"], 64)
    if len(helper_sha) != 64 or _sha(_read_regular(root, helper_path)) != helper_sha:
        _fail()
    result.append(
        {
            "code": "secure_generated_publication",
            "path": helper_path.as_posix(),
            "scope": "HELPER",
            "sha256": helper_sha,
        }
    )
    return result


def _status(code: str, text: str, icon: str) -> dict[str, object]:
    return {"code": code, "colorOnly": False, "icon": icon, "text": text}


def _table(
    *,
    caption: str,
    columns: tuple[tuple[str, str], ...],
    row_header_key: str,
    rows: list[dict[str, object]],
) -> dict[str, object]:
    if not rows or row_header_key not in {key for key, _label in columns}:
        _fail()
    return {
        "caption": caption,
        "columns": [
            {"key": key, "label": label, "semanticRole": "COLUMN_HEADER"}
            for key, label in columns
        ],
        "rowHeaderKey": row_header_key,
        "rows": rows,
    }


def _registry_rows(
    root: Path, contract: dict[str, object]
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    dependencies = _mapping(_mapping(contract["source_bindings"])["dependencies"])
    registry_binding = _mapping(
        dependencies["st0701_task_registry"], frozenset({"path", "sha256"})
    )
    registry_path = Path(_string(registry_binding["path"]))
    registry = _mapping(_parse_json(_read_regular(root, registry_path)))
    tasks = _list(registry.get("tasks"), maximum=12)
    if registry.get("task_count") != 12 or len(tasks) != 12:
        _fail()

    task_rows: list[dict[str, object]] = []
    prompt_rows: list[dict[str, object]] = []
    cost_rows: list[dict[str, object]] = []
    route_map: dict[str, dict[str, object]] = {}
    task_codes: set[str] = set()
    prompt_codes: set[str] = set()
    for raw in tasks:
        binding = _mapping(raw)
        task = _mapping(binding.get("task"))
        prompt = _mapping(binding.get("prompt"))
        route = _mapping(binding.get("route"))
        route_metadata = _mapping(route.get("metadata"))
        task_id = _string(task.get("id"))
        task_code = _string(task.get("task_code"))
        prompt_code = _string(prompt.get("prompt_code"))
        route_code = _string(route.get("route_code"))
        if task_code in task_codes or prompt_code in prompt_codes:
            _fail()
        task_codes.add(task_code)
        prompt_codes.add(prompt_code)
        task_hash = _string(binding.get("task_sha256"), 64)
        prompt_hash = _string(prompt.get("sha256"), 64)
        route_hash = _string(route.get("sha256"), 64)
        binding_hash = _string(binding.get("binding_sha256"), 64)
        if any(
            len(value) != 64
            for value in (task_hash, prompt_hash, route_hash, binding_hash)
        ):
            _fail()
        lifecycle = _string(task.get("lifecycle"))
        risk_level = _string(task.get("risk_level"))
        human_review = _boolean(task.get("human_review_required"))
        prompt_status = _string(prompt.get("status"))
        configured_cost = _integer(task.get("default_max_cost_jpy"), 1_000_000)
        display_status = (
            _status("DEFAULT_DISABLED", "既定で無効", "circle-stop")
            if prompt_status == "DISABLED" or "DISABLED" in lifecycle
            else _status("CONFIGURED_CANDIDATE", "候補構成", "circle-information")
        )
        task_rows.append(
            {
                "bindingSha256": binding_hash,
                "humanReviewRequired": human_review,
                "lifecycle": lifecycle,
                "maxInputTokens": _integer(task.get("max_input_tokens")),
                "maxOutputCharacters": task.get("max_output_characters"),
                "maxOutputTokens": _integer(task.get("max_output_tokens")),
                "name": _string(task.get("name")),
                "promptCode": prompt_code,
                "riskLevel": risk_level,
                "routeCode": route_code,
                "status": display_status,
                "taskCode": task_code,
                "taskId": task_id,
                "taskSha256": task_hash,
            }
        )
        prompt_rows.append(
            {
                "activationAuthorized": False,
                "humanReviewRequired": human_review,
                "locale": _string(prompt.get("locale")),
                "promptCode": prompt_code,
                "promptSha256": prompt_hash,
                "routeCode": route_code,
                "status": (
                    _status("DEFAULT_DISABLED", "既定で無効", "circle-stop")
                    if prompt_status == "DISABLED"
                    else _status("CANDIDATE", "候補", "circle-information")
                ),
                "taskCode": task_code,
                "version": _integer(prompt.get("version"), 1000),
            }
        )
        cost_rows.append(
            {
                "configuredCandidateCeilingJpy": configured_cost,
                "configuredUnit": "JPY_PER_TASK_CANDIDATE_LIMIT",
                "observedActualCostJpy": None,
                "observedCostStatus": _status(
                    "UNAVAILABLE", "実測値なし", "triangle-alert"
                ),
                "od009Resolution": "UNRESOLVED",
                "taskCode": task_code,
                "unknownTreatedAsZero": False,
            }
        )
        route_candidate = {
            "activationAuthorized": False,
            "catalogCandidateEnabled": _boolean(route_metadata.get("enabled")),
            "fallbackModelKey": route_metadata.get("fallback_model_key"),
            "maxFallbacks": _integer(route_metadata.get("max_fallbacks"), 16),
            "minimumEvaluationStatus": _string(
                route_metadata.get("minimum_eval_status")
            ),
            "primaryModelKey": _string(route_metadata.get("primary_model_key")),
            "releaseAuthorized": False,
            "routeCode": route_code,
            "routeSha256": route_hash,
            "status": _status(
                "CATALOG_CANDIDATE_ONLY", "カタログ候補のみ", "circle-information"
            ),
            "store": _boolean(route_metadata.get("store")),
            "strictStructuredOutput": _boolean(
                route_metadata.get("strict_structured_output")
            ),
        }
        existing = route_map.get(route_code)
        if existing is not None and existing != route_candidate:
            _fail()
        route_map[route_code] = route_candidate

    task_rows.sort(key=lambda item: cast(str, item["taskCode"]))
    prompt_rows.sort(key=lambda item: cast(str, item["promptCode"]))
    cost_rows.sort(key=lambda item: cast(str, item["taskCode"]))
    route_rows = [route_map[key] for key in sorted(route_map)]
    if tuple(map(len, (task_rows, prompt_rows, route_rows, cost_rows))) != (
        12,
        12,
        5,
        12,
    ):
        _fail()
    return task_rows, prompt_rows, route_rows, cost_rows


def _read_runtime_inputs(root: Path, paths: dict[str, Path]) -> dict[str, bytes]:
    return {name: _read_regular(root, path) for name, path in paths.items()}


def _evaluation_row(root: Path) -> dict[str, object]:
    bundle = load_recorded_evaluation_bundle(**_read_runtime_inputs(root, ST0707_PATHS))
    report = RecordedEvaluationHarness().run(bundle)
    document = _mapping(_parse_json(report.canonical_bytes()))
    proposal = _mapping(document.get("proposal"))
    if (
        proposal.get("outcome") != "REFUSED_INCOMPLETE_EVIDENCE"
        or proposal.get("authority") != "NONE"
        or proposal.get("decision_kind") != "PROPOSAL"
        or any(
            proposal.get(key) is not False
            for key in (
                "activation_authorized",
                "approval_authorized",
                "model_mutation_authorized",
                "publication_authorized",
                "release_authorized",
                "route_mutation_authorized",
                "production_eligible",
            )
        )
        or proposal.get("external_action_count") != 0
    ):
        _fail()
    return {
        "authority": "NONE",
        "caseCount": _integer(document.get("case_count"), 256),
        "datasetSha256": _string(document.get("dataset_sha256"), 64),
        "formalTst018": _string(document.get("formal_tst_018")),
        "formalTst019": _string(document.get("formal_tst_019")),
        "humanLabelStatus": _string(document.get("human_label_status")),
        "outcome": _string(proposal.get("outcome")),
        "reportSha256": _string(document.get("report_sha256"), 64),
        "status": _status(
            "REFUSED_INCOMPLETE_EVIDENCE",
            "証拠不足により拒否",
            "triangle-alert",
        ),
        "taskCode": _string(proposal.get("task_code")),
    }


def _release_row(root: Path) -> dict[str, object]:
    evidence = load_recorded_live_evaluation_result(
        **_read_runtime_inputs(root, ST0708_PATHS)
    )
    report = evaluate_recorded_live_evidence(evidence)
    document = report_projection(report) | {"report_sha256": report.report_sha256}
    operational = _mapping(document.get("operational_authority"))
    if (
        document.get("outcome") != "REFUSED_INCOMPLETE_EVIDENCE"
        or document.get("authority") != "NONE"
        or document.get("decision_kind") != "PROPOSAL"
        or any(value is not False for value in operational.values())
    ):
        _fail()
    return {
        "approvalAuthority": "HUMAN_ONLY",
        "authority": "NONE",
        "decisionKind": "PROPOSAL",
        "directActivation": False,
        "evaluationId": _string(document.get("evaluation_id")),
        "operationalAuthority": operational,
        "outcome": _string(document.get("outcome")),
        "reasons": _list(document.get("reasons"), maximum=64),
        "reportSha256": _string(document.get("report_sha256"), 64),
        "status": _status(
            "REFUSED_INCOMPLETE_EVIDENCE",
            "公開判断不可",
            "circle-stop",
        ),
        "targetTaskCode": _string(document.get("target_task_code")),
    }


def _sections(contract: dict[str, object], root: Path) -> list[dict[str, object]]:
    task_rows, prompt_rows, route_rows, cost_rows = _registry_rows(root, contract)
    evaluation_rows = [_evaluation_row(root)]
    release_rows = [_release_row(root)]
    section_contracts = {
        _string(_mapping(raw)["id"]): _mapping(raw)
        for raw in _list(contract["sections"], maximum=6)
    }
    definitions = (
        (
            "TASK",
            task_rows,
            "Task候補構成一覧",
            (
                ("taskCode", "Taskコード"),
                ("name", "名称"),
                ("lifecycle", "ライフサイクル"),
                ("riskLevel", "リスク"),
                ("promptCode", "Prompt"),
                ("routeCode", "Route"),
                ("status", "状態"),
            ),
            "taskCode",
        ),
        (
            "PROMPT",
            prompt_rows,
            "Prompt候補メタデータ一覧",
            (
                ("promptCode", "Promptコード"),
                ("version", "版"),
                ("taskCode", "Task"),
                ("locale", "言語"),
                ("status", "状態"),
                ("activationAuthorized", "有効化権限"),
            ),
            "promptCode",
        ),
        (
            "ROUTE",
            route_rows,
            "Route候補構成一覧",
            (
                ("routeCode", "Routeコード"),
                ("primaryModelKey", "Primary候補"),
                ("fallbackModelKey", "Fallback候補"),
                ("minimumEvaluationStatus", "最低評価状態"),
                ("status", "状態"),
                ("activationAuthorized", "有効化権限"),
            ),
            "routeCode",
        ),
        (
            "EVALUATION",
            evaluation_rows,
            "記録済み合成評価結果",
            (
                ("taskCode", "Taskコード"),
                ("caseCount", "ケース数"),
                ("humanLabelStatus", "人ラベル"),
                ("outcome", "結果"),
                ("status", "状態"),
            ),
            "taskCode",
        ),
        (
            "RELEASE",
            release_rows,
            "記録済み公開判断提案",
            (
                ("evaluationId", "評価ID"),
                ("targetTaskCode", "対象Task"),
                ("decisionKind", "判断種別"),
                ("outcome", "結果"),
                ("status", "状態"),
            ),
            "evaluationId",
        ),
        (
            "COST",
            cost_rows,
            "Task別候補上限と実測可用性",
            (
                ("taskCode", "Taskコード"),
                ("configuredCandidateCeilingJpy", "候補上限（円）"),
                ("configuredUnit", "単位"),
                ("observedActualCostJpy", "実測費用"),
                ("observedCostStatus", "実測状態"),
            ),
            "taskCode",
        ),
    )
    result: list[dict[str, object]] = []
    for section_id, rows, caption, columns, row_header in definitions:
        selected = section_contracts[section_id]
        result.append(
            {
                "actions": [],
                "availability": selected["availability"],
                "id": section_id,
                "label": selected["label"],
                "mode": "READ_ONLY",
                "recordCount": len(rows),
                "source": selected["source"],
                "table": _table(
                    caption=caption,
                    columns=columns,
                    row_header_key=row_header,
                    rows=rows,
                ),
            }
        )
    return result


def _fixture(
    root: Path,
    contract: dict[str, object],
    bindings: list[dict[str, str]],
) -> dict[str, object]:
    screen = _mapping(contract["screen"])
    formal = _mapping(contract["formal_status"])
    if set(formal.values()) != {"NOT_EXECUTED"}:
        _fail()
    guard = _mapping(contract["release_guard"])
    return {
        "accessibility": {
            "colorOnlyStatus": False,
            "columnHeaders": True,
            "keyboardActionCount": 0,
            "rowHeaders": True,
            "statusFields": ["text", "code", "icon"],
            "tableCaptions": True,
        },
        "authority": {
            "activation": False,
            "approval": False,
            "credentialRead": False,
            "network": False,
            "persistence": False,
            "productionWrite": False,
            "providerCall": False,
            "publication": False,
            "release": False,
            "routeMutation": False,
        },
        "document": {
            "authority": "NONE",
            "defaultEnabled": False,
            "environment": "LOCAL_RECORDED_ONLY",
            "id": "RAOS-ST0709-AI-GOVERNANCE-WORKSPACE-002",
            "status": "LOCAL_IMPLEMENTATION_COMPLETE",
            "storyId": "ST-0709",
            "version": "2.0.0",
        },
        "formalStatus": formal,
        "releaseGuard": guard,
        "route": {
            "authentication": "NOT_EXECUTED",
            "authorizationGranted": False,
            "navigation": "DISABLED",
            "path": screen["route"],
            "registration": "UNREGISTERED",
            "rendering": "NOT_EXECUTED",
        },
        "screen": {
            "apiDependencies": screen["api_dependencies"],
            "area": screen["area"],
            "canonicalImplementationStatus": screen["canonical_implementation_status"],
            "canonicalRuntimeVerification": screen["canonical_runtime_verification"],
            "criticalAction": screen["critical_action"],
            "designStatus": screen["design_status"],
            "id": screen["id"],
            "mvp": screen["mvp"],
            "name": screen["name"],
            "purpose": screen["purpose"],
            "roles": screen["roles"],
            "route": screen["route"],
            "storyObjective": screen["story_objective"],
        },
        "sectionOrder": ["TASK", "PROMPT", "ROUTE", "EVALUATION", "RELEASE", "COST"],
        "sections": _sections(contract, root),
        "sourceBindings": bindings,
    }


def _typescript_binding(fixture_bytes: bytes) -> bytes:
    canonical_text = fixture_bytes.decode("utf-8", errors="strict")
    literal = (
        "'"
        + canonical_text.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
        + "'"
    )
    digest = _sha(fixture_bytes)
    return (
        "// Generated by scripts/build_st0709_ai_governance_workspace.py; do not edit.\n"
        "export const AI_GOVERNANCE_RECORDED_V2_JSON =\n"
        f"  {literal} as const;\n"
        "export const AI_GOVERNANCE_RECORDED_V2_SHA256 =\n"
        f"  '{digest}' as const;\n"
    ).encode("utf-8", errors="strict")


def _manifest(
    root: Path,
    contract: dict[str, object],
    contract_bytes: bytes,
    bindings: list[dict[str, str]],
    fixture_payload: bytes,
    typescript_payload: bytes,
) -> dict[str, object]:
    owned_sources = _list(contract["owned_runtime_sources"], maximum=16)
    runtime_sources: list[dict[str, str]] = []
    for raw in owned_sources:
        path = Path(_string(raw))
        runtime_sources.append(
            {"path": path.as_posix(), "sha256": _sha(_read_regular(root, path))}
        )
    provisional: dict[str, object] = {
        "contractSha256": _sha(contract_bytes),
        "document": {
            "authority": "NONE",
            "defaultEnabled": False,
            "id": "RAOS-ST0709-AI-GOVERNANCE-RUNTIME-MANIFEST-002",
            "storyId": "ST-0709",
            "version": "2.0.0",
        },
        "formalStatus": contract["formal_status"],
        "outputs": [
            {
                "canonicalSha256": _sha(fixture_payload),
                "path": FIXTURE_PATH.as_posix(),
                "sha256": _sha(fixture_payload + b"\n"),
            },
            {
                "path": TYPESCRIPT_PATH.as_posix(),
                "sha256": _sha(typescript_payload),
            },
        ],
        "runtimeSources": runtime_sources,
        "security": {
            "actionCount": 0,
            "actualCostAvailable": False,
            "credentialsAllowed": False,
            "networkAllowed": False,
            "providerAllowed": False,
            "routeRegistrationAllowed": False,
            "unknownCostIsZero": False,
        },
        "sourceBindings": bindings,
    }
    return provisional | {"manifestSha256": _sha(_canonical(provisional))}


def build(root: Path) -> tuple[tuple[Path, bytes], ...]:
    contract, contract_bytes = _load_contract(root)
    bindings = _declared_bindings(root, contract)
    fixture = _fixture(root, contract, bindings)
    fixture_canonical = _canonical(fixture)
    fixture_output = fixture_canonical + b"\n"
    typescript_output = _typescript_binding(fixture_canonical)
    manifest = _manifest(
        root,
        contract,
        contract_bytes,
        bindings,
        fixture_canonical,
        typescript_output,
    )
    return (
        (_repository_path(root, FIXTURE_PATH), fixture_output),
        (_repository_path(root, TYPESCRIPT_PATH), typescript_output),
        (_repository_path(root, MANIFEST_PATH), _json_output(manifest)),
    )


def _check(outputs: tuple[tuple[Path, bytes], ...]) -> None:
    for path, expected in outputs:
        try:
            relative = path.relative_to(REPO_ROOT)
            if _read_regular(REPO_ROOT, relative) != expected:
                _fail()
        except St0709BuildError:
            raise
        except Exception:
            _fail()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        outputs = build(REPO_ROOT)
        if arguments.check:
            _check(outputs)
        else:
            _publication.publish_generated(
                outputs,
                namespace="st0709-v2",
                maximum_payload_bytes=MAX_SOURCE_BYTES,
            )
    except Exception as error:
        if isinstance(error, St0709BuildError):
            raise
        raise St0709BuildError("ST0709_AI_GOVERNANCE_BUILD_FAILED") from None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
