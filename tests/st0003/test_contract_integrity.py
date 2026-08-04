"""TST-002/TST-003 contract, provenance, and isolation evidence for ST-0003."""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import shutil
from typing import Any
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

from jsonschema import Draft202012Validator
import pytest
import yaml

from scripts import build_st0003_revision as revision


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_ROOT = REPOSITORY_ROOT / "changes" / "st-0003"
CONTRACTS_ROOT = BUNDLE_ROOT / "contracts"
PREDECESSOR_CONTRACTS_ROOT = (
    REPOSITORY_ROOT / "changes" / "st-0002" / "contracts"
)
MANIFEST_PATH = BUNDLE_ROOT / "manifest.yaml"
AI_PACKAGE = (
    REPOSITORY_ROOT / "docs" / "upstream" / "RAOS_05_ai_design_package_v0.1.zip"
)
API_PACKAGE = (
    REPOSITORY_ROOT / "docs" / "upstream" / "RAOS_04_api_contract_package_v0.1.zip"
)
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
RESOURCE_CATALOG_MAP = {
    "ai-task-definition.v1.schema.json": ("AITaskDefinition", "ai.task_definition"),
    "ai-job.v1.schema.json": ("AIJob", "ai.ai_job"),
    "prompt-version.v1.schema.json": ("PromptVersion", "ai.prompt_version"),
    "model-definition.v1.schema.json": ("ModelDefinition", "ai.model_definition"),
    "model-route-version.v1.schema.json": (
        "ModelRouteVersion",
        "ai.model_route_version",
    ),
    "evaluation-suite.v1.schema.json": ("EvaluationSuite", "ai.evaluation_suite"),
    "evaluation-dataset-version.v1.schema.json": (
        "EvaluationDatasetVersion",
        "ai.evaluation_dataset_version",
    ),
    "evaluation-case.v1.schema.json": ("EvaluationCase", "ai.evaluation_case"),
    "evaluation-run.v1.schema.json": ("EvaluationRun", "ai.evaluation_run"),
    "evaluation-case-result.v1.schema.json": (
        "EvaluationCaseResult",
        "ai.evaluation_case_result",
    ),
    "human-evaluation.v1.schema.json": (
        "HumanEvaluation",
        "ai.human_evaluation",
    ),
    "judge-calibration.v1.schema.json": (
        "JudgeCalibration",
        "ai.judge_calibration",
    ),
    "release-decision.v1.schema.json": (
        "ReleaseDecision",
        "ai.release_decision",
    ),
    "release-approval.v1.schema.json": (
        "ReleaseApproval",
        "ai.release_approval",
    ),
}
EXPECTED_EVALUATION_COMPLETION_EXECUTION_SECURITY = {
    "security_definer_owner": {
        "functions": [
            "ai.guard_evaluation_run_mutation()",
            "ai.guard_evaluation_run_start_integrity()",
            "ai.guard_evaluation_run_completion_evidence()",
        ],
        "must_match_relation_owner": "ai.evaluation_run",
        "live_verified_by": (
            "202607300010_ai_governance_contract_prepare.sql"
        ),
    },
    "evaluation_run_trigger_guards": [
        {
            "function": "ai.guard_evaluation_run_mutation()",
            "trigger": "trg_ai_eval_run_mutation",
            "security_mode": "SECURITY_DEFINER",
            "fixed_search_path": ["pg_catalog", "ai", "pg_temp"],
        },
        {
            "function": "ai.guard_evaluation_run_start_integrity()",
            "trigger": "trg_ai_eval_run_start_integrity",
            "security_mode": "SECURITY_DEFINER",
            "fixed_search_path": ["pg_catalog", "ai", "policy", "pg_temp"],
        },
        {
            "function": "ai.guard_evaluation_run_completion_evidence()",
            "trigger": "trg_ai_eval_run_completion_evidence",
            "security_mode": "SECURITY_DEFINER",
            "fixed_search_path": ["pg_catalog", "ai", "pg_temp"],
            "invokes": "ai.assert_evaluation_run_evidence(uuid, boolean)",
        },
    ],
    "worker_direct_execute": {
        "role": "raos_worker_rw",
        "policy": "REVOKED",
        "functions": [
            "ai.guard_evaluation_run_mutation()",
            "ai.guard_evaluation_run_start_integrity()",
            "ai.guard_evaluation_run_completion_evidence()",
            "ai.assert_evaluation_run_evidence(uuid, boolean)",
            "ai.artifact_matches_immutable_hash(uuid, text)",
        ],
        "allowed_path": "TRIGGER_OR_AUTHORIZED_WRAPPER_ONLY",
    },
    "public_execute": {
        "policy": "REVOKED",
        "functions": [
            "ai.guard_evaluation_run_mutation()",
            "ai.guard_evaluation_run_start_integrity()",
            "ai.guard_evaluation_run_completion_evidence()",
            "ai.assert_evaluation_run_evidence(uuid, boolean)",
            "ai.artifact_matches_immutable_hash(uuid, text)",
        ],
    },
}


def load_yaml(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"expected YAML mapping: {path}"
    return document


def load_document(path: Path) -> Any:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def walk_refs(document: Any) -> Iterator[str]:
    if isinstance(document, dict):
        for key, value in document.items():
            if key == "$ref":
                assert isinstance(value, str)
                yield value
            yield from walk_refs(value)
    elif isinstance(document, list):
        for value in document:
            yield from walk_refs(value)


def resolve_pointer(document: Any, fragment: str, *, source: Path) -> Any:
    pointer = unquote(fragment)
    if pointer == "":
        return document
    assert pointer.startswith("/"), (
        f"only JSON Pointer fragments are allowed in {source}: #{fragment}"
    )
    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            assert token in current, (
                f"missing JSON Pointer token {token!r} in {source}: #{fragment}"
            )
            current = current[token]
        elif isinstance(current, list):
            assert token.isdecimal(), (
                f"non-numeric list token {token!r} in {source}: #{fragment}"
            )
            index = int(token)
            assert index < len(current), (
                f"list token out of range in {source}: #{fragment}"
            )
            current = current[index]
        else:
            raise AssertionError(
                f"JSON Pointer traverses a scalar in {source}: #{fragment}"
            )
    return current


def resolve_ref(source: Path, reference: str) -> tuple[Path, str]:
    parsed = urlsplit(reference)
    assert not parsed.scheme and not parsed.netloc, (
        f"remote reference is forbidden in {source}: {reference}"
    )
    assert not parsed.query, f"query component is forbidden in {source}: {reference}"
    assert "\\" not in parsed.path, (
        f"backslash path is forbidden in {source}: {reference}"
    )

    relative_path = unquote(parsed.path)
    if relative_path:
        assert not PurePosixPath(relative_path).is_absolute(), (
            f"absolute reference is forbidden in {source}: {reference}"
        )
        target = (source.parent / relative_path).resolve()
    else:
        target = source.resolve()

    try:
        target.relative_to(CONTRACTS_ROOT.resolve())
    except ValueError as exc:
        raise AssertionError(
            f"reference escapes the contract tree in {source}: {reference}"
        ) from exc
    assert target.is_file(), f"reference target is missing: {source}: {reference}"
    assert not target.is_symlink(), (
        f"reference target must not be a symlink: {source}: {reference}"
    )
    return target, parsed.fragment


def safe_repository_path(raw_path: str) -> Path:
    assert "\\" not in raw_path, f"backslash manifest path: {raw_path}"
    logical = PurePosixPath(raw_path)
    assert raw_path == logical.as_posix(), f"non-canonical path: {raw_path}"
    assert not logical.is_absolute(), f"absolute manifest path: {raw_path}"
    assert ".." not in logical.parts, f"escaping manifest path: {raw_path}"

    lexical = REPOSITORY_ROOT.joinpath(*logical.parts)
    resolved = lexical.resolve()
    try:
        resolved.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError as exc:
        raise AssertionError(f"manifest path escapes repository: {raw_path}") from exc
    assert lexical.is_file(), f"manifest artifact is missing: {raw_path}"
    assert not lexical.is_symlink(), f"manifest artifact is a symlink: {raw_path}"
    return lexical


def zip_member_with_suffix(archive: ZipFile, suffix: str) -> str:
    matches = [name for name in archive.namelist() if name.endswith(suffix)]
    assert len(matches) == 1, (suffix, matches)
    return matches[0]


def schema_documents() -> dict[str, tuple[Path, dict[str, Any]]]:
    schemas: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(CONTRACTS_ROOT.rglob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("$schema") != JSON_SCHEMA_DIALECT or "$id" not in document:
            continue
        relative = path.relative_to(CONTRACTS_ROOT).as_posix()
        schemas[relative] = (path, document)
    return schemas


def assert_predecessor_schema_compatibility(candidate_root: Path) -> None:
    predecessor = {
        path.relative_to(PREDECESSOR_CONTRACTS_ROOT).as_posix(): path.read_bytes()
        for path in PREDECESSOR_CONTRACTS_ROOT.joinpath("schemas").rglob("*.json")
    }
    candidate = {
        path.relative_to(candidate_root).as_posix(): path.read_bytes()
        for path in candidate_root.joinpath("schemas").rglob("*.json")
    }
    missing = predecessor.keys() - candidate.keys()
    changed = {
        relative
        for relative in predecessor.keys() & candidate.keys()
        if predecessor[relative] != candidate[relative]
    }
    assert not missing, f"predecessor schemas removed: {sorted(missing)}"
    assert not changed, f"predecessor schemas changed in place: {sorted(changed)}"


def assert_public_isolation(public: dict[str, Any]) -> None:
    paths = public.get("paths", {})
    assert isinstance(paths, dict)
    assert not any("/ai" in path.lower() for path in paths)

    components = public.get("components", {})
    component_names: set[str] = set()
    if isinstance(components, dict):
        for section in components.values():
            if isinstance(section, dict):
                component_names.update(str(name) for name in section)
    forbidden_names = (
        "AIJob",
        "PromptVersion",
        "ModelRoute",
        "EvaluationDataset",
        "EvaluationRun",
        "JudgeCalibration",
        "ReleaseDecision",
        "ReleaseApproval",
    )
    assert not (set(forbidden_names) & component_names)

    references = tuple(walk_refs(public))
    assert not any("ai-governance" in reference.lower() for reference in references)
    assert not any("/ai/" in reference.lower() for reference in references)


def test_revision_metadata_and_manifest_provenance_are_consistent() -> None:
    manifest = load_yaml(MANIFEST_PATH)
    admin = load_yaml(CONTRACTS_ROOT / "openapi-admin.v0.3.yaml")
    internal = load_yaml(CONTRACTS_ROOT / "openapi-internal.v0.3.yaml")
    asyncapi = load_yaml(CONTRACTS_ROOT / "asyncapi.v0.3.yaml")

    assert manifest["document"] == {
        "id": revision.REVISION_ID,
        "version": revision.REVISION_VERSION,
        "story_id": "ST-0003",
        "status": "IMPLEMENTATION_CANDIDATE",
        "generated_by": "scripts/build_st0003_revision.py",
    }
    for contract in (admin, internal, asyncapi):
        info = contract["info"]
        assert info["version"] == revision.REVISION_VERSION
        assert info["x-raos-revision-id"] == revision.REVISION_ID
        assert info["x-raos-story-id"] == "ST-0003"
        assert info["x-raos-decision-id"] == "INT-DEC-004"
        assert info["x-raos-base-version"] == "0.1"
        assert info["x-raos-predecessor-version"] == "0.2"
        assert (
            info["x-raos-predecessor-manifest-sha256"]
            == revision.PREDECESSOR_MANIFEST_HASH
        )

    assert manifest["provenance"]["requirement_ids"] == ["FR-018"]
    assert manifest["provenance"]["decision_ids"] == ["INT-DEC-004"]
    predecessor = manifest["provenance"]["predecessor"]
    assert predecessor == {
        "id": revision.PREDECESSOR_ID,
        "version": "0.2",
        "manifest_path": "changes/st-0002/manifest.yaml",
        "manifest_sha256": revision.PREDECESSOR_MANIFEST_HASH,
        "job_state_sha256": revision.JOB_STATE_HASH,
        "complete_artifact_verification": True,
    }
    assert manifest["compatibility"]["existing_schema_paths_preserved"] is True
    assert manifest["compatibility"]["public_ai_surface"] == "NONE"
    assert asyncapi["info"]["x-raos-wire-change"] == "NONE"


def test_all_yaml_and_json_contract_documents_parse() -> None:
    paths = sorted(
        path
        for path in CONTRACTS_ROOT.rglob("*")
        if path.is_file() and path.suffix in {".yaml", ".yml", ".json"}
    )
    assert paths
    for path in paths:
        document = load_document(path)
        assert document is not None, f"empty contract document: {path}"


def test_all_contract_references_are_local_safe_and_resolvable() -> None:
    sources = sorted(
        path
        for path in CONTRACTS_ROOT.rglob("*")
        if path.is_file() and path.suffix in {".yaml", ".yml", ".json"}
    )
    documents = {path.resolve(): load_document(path) for path in sources}
    resolved_count = 0

    for source in sources:
        for reference in walk_refs(documents[source.resolve()]):
            target, fragment = resolve_ref(source, reference)
            assert target.resolve() in documents, (
                f"reference target is not a parsed contract document: {target}"
            )
            resolve_pointer(documents[target.resolve()], fragment, source=target)
            resolved_count += 1

    assert resolved_count > 2_900


def test_schema_registry_is_complete_hashed_unique_and_meta_valid() -> None:
    registry_path = CONTRACTS_ROOT / "catalogs" / "schema-registry.v0.3.yaml"
    registry = load_yaml(registry_path)
    entries = {entry["path"]: entry for entry in registry["schemas"]}
    actual = schema_documents()

    assert registry["dialect"] == JSON_SCHEMA_DIALECT
    assert len(entries) == len(registry["schemas"])
    assert len({path.casefold() for path in entries}) == len(entries)
    assert set(entries) == set(actual)

    ids: set[str] = set()
    for relative, (path, schema) in actual.items():
        entry = entries[relative]
        content = path.read_bytes()
        Draft202012Validator.check_schema(schema)
        assert entry["id"] == schema["$id"]
        assert entry["title"] == schema["title"]
        assert entry["sha256"] == sha256(content).hexdigest()
        assert schema["$id"] not in ids, f"duplicate schema id: {schema['$id']}"
        ids.add(schema["$id"])


def test_resource_catalog_matches_schemas_without_classification_downgrade() -> None:
    catalog = load_yaml(
        CONTRACTS_ROOT / "catalogs" / "resource-contracts.v0.3.yaml"
    )
    predecessor = load_yaml(
        PREDECESSOR_CONTRACTS_ROOT
        / "catalogs"
        / "resource-contracts.v0.2.yaml"
    )
    entries = {
        entry["name"]: entry
        for entry in catalog["resources"]
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    predecessor_entries = {
        entry["name"]: entry
        for entry in predecessor["resources"]
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    classification_rank = {
        "PUBLIC": 0,
        "INTERNAL": 1,
        "CONFIDENTIAL": 2,
        "RESTRICTED": 3,
    }

    assert catalog["ai_governance_resource_count"] == 14
    assert catalog["public_ai_resource_count"] == 0
    for filename, (name, source_table) in RESOURCE_CATALOG_MAP.items():
        entry = entries[name]
        schema_path = (
            CONTRACTS_ROOT / "schemas" / "ai-governance" / filename
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        assert entry["source_tables"] == [source_table]
        assert entry["schema_ref"] == f"../schemas/ai-governance/{filename}"
        assert entry["classification"] == schema["x-raos-classification"]
        assert entry["classification"] != "PUBLIC"

        fields = entry["fields"]
        assert len(fields) == len({field["name"] for field in fields})
        assert {field["name"] for field in fields} == set(schema["properties"])
        for field in fields:
            assert field["schema"] == schema["properties"][field["name"]]

        old_entry = predecessor_entries.get(name)
        if old_entry is not None:
            assert (
                classification_rank[entry["classification"]]
                >= classification_rank[old_entry["classification"]]
            ), f"classification downgraded for {name}"


def test_evaluation_completion_execution_security_is_exact_and_consistent() -> None:
    evaluation_run = json.loads(
        CONTRACTS_ROOT.joinpath(
            "schemas",
            "ai-governance",
            "evaluation-run.v1.schema.json",
        ).read_text(encoding="utf-8")
    )
    catalog = load_yaml(
        CONTRACTS_ROOT / "catalogs" / "resource-contracts.v0.3.yaml"
    )
    catalog_resources = {
        resource["name"]: resource
        for resource in catalog["resources"]
        if isinstance(resource, dict) and isinstance(resource.get("name"), str)
    }
    internal = load_yaml(CONTRACTS_ROOT / "openapi-internal.v0.3.yaml")
    manifest = load_yaml(MANIFEST_PATH)

    expected = EXPECTED_EVALUATION_COMPLETION_EXECUTION_SECURITY
    copies = (
        evaluation_run["x-raos-completion-execution-security-invariants"],
        evaluation_run["x-raos-completion-evidence-invariants"][
            "execution_security"
        ],
        catalog_resources["EvaluationRun"][
            "x-raos-completion-execution-security-invariants"
        ],
        catalog_resources["EvaluationRun"][
            "x-raos-completion-evidence-invariants"
        ]["execution_security"],
        catalog_resources["EvaluationResult"][
            "x-raos-completion-evidence-invariants"
        ]["execution_security"],
        catalog["evaluation_completion_execution_security_invariants"],
        catalog["evaluation_run_completion_evidence_invariants"][
            "execution_security"
        ],
        internal["x-raos-ai-governance"]["database_execution_security"],
        manifest["database_execution_security"],
    )
    assert all(copy == expected for copy in copies)
    assert "completion_trigger_wrapper" not in json.dumps(copies, sort_keys=True)


def test_catalog_evaluation_result_passed_is_nullable_with_exact_p95_truth() -> None:
    catalog = load_yaml(
        CONTRACTS_ROOT / "catalogs" / "resource-contracts.v0.3.yaml"
    )
    evaluation_result = next(
        resource
        for resource in catalog["resources"]
        if resource.get("name") == "EvaluationResult"
    )
    passed = next(
        field
        for field in evaluation_result["fields"]
        if field.get("name") == "passed"
    )
    assert passed["schema"]["type"] == ["boolean", "null"]
    assert passed["read_only"] is False

    cost_latency = evaluation_result[
        "x-raos-cost-latency-reporting-completeness-invariants"
    ]
    assert cost_latency["passed_truth_table"] == {
        "current_frozen_canonical_report_only_p95": "MUST_BE_NULL",
        "required_p95": "MUST_BE_NON_NULL_DATABASE_EXACT",
        "legacy_or_non_report_only_metric": "MUST_BE_NON_NULL_DATABASE_EXACT",
    }


def test_nested_resource_json_is_preserved_but_create_requests_reject_unknowns() -> None:
    schema_root = CONTRACTS_ROOT / "schemas" / "ai-governance"
    uuid = "00000000-0000-7000-8000-000000000001"
    timestamp = "2026-07-31T00:00:00Z"

    route_resource_schema = json.loads(
        schema_root.joinpath("model-route-version.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    route_resource = {
        "id": uuid,
        "route_code": "route.example.v1",
        "version_no": 1,
        "task_definition_id": uuid,
        "primary_model_id": uuid,
        "fallback_model_id": None,
        "route_config": {
            "provider_options": {
                "response": {"verbosity": "low", "metadata": {"nested": True}}
            }
        },
        "monthly_budget_jpy": 1000,
        "per_job_budget_jpy": 10,
        "status": "DRAFT",
        "effective_from": None,
        "effective_to": None,
        "approved_by_principal_id": None,
        "created_at": timestamp,
        "updated_at": timestamp,
        "lock_version": 0,
    }
    assert Draft202012Validator(route_resource_schema).is_valid(route_resource)

    dataset_resource_schema = json.loads(
        schema_root.joinpath(
            "evaluation-dataset-version.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    dataset_resource = {
        "id": uuid,
        "display_id": "AID-EXAMPLE-1",
        "dataset_code": "dataset.example.v1",
        "version_no": 1,
        "purpose": "Nested metadata round-trip example",
        "split_policy": {
            "allocation": {
                "holdout": {"share": 0.5},
                "regression": {"share": 0.5},
            }
        },
        "dataset_artifact_id": uuid,
        "dataset_sha256": "a" * 64,
        "case_count": 200,
        "status": "DRAFT",
        "locked_by_principal_id": None,
        "locked_at": None,
        "compromised_at": None,
        "created_at": timestamp,
        "updated_at": timestamp,
        "lock_version": 0,
    }
    assert Draft202012Validator(dataset_resource_schema).is_valid(
        dataset_resource
    )

    route_request_schema = json.loads(
        schema_root.joinpath(
            "model-route-version-create-request.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    route_request = {
        "route_code": "route.example.v1",
        "version_no": 1,
        "task_definition_id": uuid,
        "primary_model_id": uuid,
        "fallback_model_id": None,
        "route_config": {
            "reasoning_effort": "medium",
            "temperature": 0.2,
            "max_output_tokens": 1000,
            "timeout_seconds": 60,
            "max_fallbacks": 1,
            "fallback_on": ["RATE_LIMIT"],
            "never_fallback_on": ["POLICY"],
            "minimum_eval_status": "CERTIFIED",
            "canary_max_percent": 10,
            "batch_eligible": False,
            "prompt_cache_eligible": True,
            "enabled": True,
            "store": False,
            "strict_structured_output": True,
        },
        "monthly_budget_jpy": 1000,
        "per_job_budget_jpy": 10,
    }
    route_validator = Draft202012Validator(route_request_schema)
    assert route_validator.is_valid(route_request)
    unknown_route = deepcopy(route_request)
    unknown_route["route_config"]["provider_secret_override"] = "forbidden"
    assert any(
        error.validator == "additionalProperties"
        for error in route_validator.iter_errors(unknown_route)
    )

    dataset_request_schema = json.loads(
        schema_root.joinpath(
            "evaluation-dataset-create-request.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    dataset_request = {
        "dataset_code": "dataset.example.v1",
        "version_no": 1,
        "purpose": "Strict split policy example",
        "split_policy": {
            "dev_share": 0.10,
            "calibration_share": 0.20,
            "holdout_share": 0.30,
            "adversarial_share": 0.20,
            "regression_share": 0.20,
            "holdout_blinded": True,
            "labels_hidden_from_prompt_authors": True,
        },
        "dataset_artifact_id": uuid,
        "dataset_sha256": "a" * 64,
        "case_count": 200,
    }
    dataset_validator = Draft202012Validator(dataset_request_schema)
    assert dataset_validator.is_valid(dataset_request)
    unknown_split = deepcopy(dataset_request)
    unknown_split["split_policy"]["raw_holdout_labels"] = True
    assert any(
        error.validator == "additionalProperties"
        for error in dataset_validator.iter_errors(unknown_split)
    )


def test_manifest_paths_hashes_sizes_and_owned_file_set_are_complete() -> None:
    manifest = load_yaml(MANIFEST_PATH)
    sections = (
        manifest["inputs"],
        manifest["source_artifacts"],
        manifest["generated_artifacts"],
    )
    for entries in sections:
        paths = [entry["path"] for entry in entries]
        assert len(paths) == len(set(paths))
        assert len(paths) == len({path.casefold() for path in paths})
        for entry in entries:
            path = safe_repository_path(entry["path"])
            content = path.read_bytes()
            if "bytes" in entry:
                assert entry["bytes"] == len(content)
            assert entry["sha256"] == sha256(content).hexdigest()

    assert {
        entry["path"]: entry["sha256"] for entry in manifest["inputs"]
    } == revision.EXPECTED_INPUT_HASHES

    actual_generated = {
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in CONTRACTS_ROOT.rglob("*")
        if path.is_file()
    }
    actual_generated.add("changes/st-0003/job-state.v1.yaml")
    manifest_generated = {
        entry["path"] for entry in manifest["generated_artifacts"]
    }
    assert manifest_generated == actual_generated
    assert manifest["generated_artifact_count"] == len(actual_generated)

    predecessor = manifest["provenance"]["predecessor"]
    predecessor_manifest = safe_repository_path(predecessor["manifest_path"])
    assert sha256(predecessor_manifest.read_bytes()).hexdigest() == (
        predecessor["manifest_sha256"]
    )
    predecessor_job_state = (
        REPOSITORY_ROOT / "changes" / "st-0002" / "job-state.v1.yaml"
    )
    assert sha256(predecessor_job_state.read_bytes()).hexdigest() == (
        predecessor["job_state_sha256"]
    )


def test_every_predecessor_schema_is_byte_identical() -> None:
    assert_predecessor_schema_compatibility(CONTRACTS_ROOT)

    predecessor_paths = {
        path.relative_to(PREDECESSOR_CONTRACTS_ROOT).as_posix()
        for path in PREDECESSOR_CONTRACTS_ROOT.joinpath("schemas").rglob("*.json")
    }
    assert len(predecessor_paths) == 126
    assert all((CONTRACTS_ROOT / path).is_file() for path in predecessor_paths)


def test_four_legacy_ai_schema_ids_remain_unchanged_and_new_ids_are_additive() -> None:
    legacy_paths = (
        "schemas/ai/article-draft-output.schema.json",
        "schemas/ai/claim-extraction-output.schema.json",
        "schemas/ai/opportunity-assessment-output.schema.json",
        "schemas/ai/policy-assist-output.schema.json",
    )
    for relative in legacy_paths:
        assert (
            CONTRACTS_ROOT.joinpath(relative).read_bytes()
            == PREDECESSOR_CONTRACTS_ROOT.joinpath(relative).read_bytes()
        )

    with ZipFile(AI_PACKAGE) as archive:
        upstream_ids = {
            json.loads(archive.read(name))["$id"]
            for name in archive.namelist()
            if (
                "/schemas/tasks/" in name or "/schemas/eval/" in name
            )
            and name.endswith(".json")
        }
    legacy_ids = {
        json.loads(CONTRACTS_ROOT.joinpath(path).read_text(encoding="utf-8"))["$id"]
        for path in legacy_paths
    }
    assert len(upstream_ids) == 14
    assert upstream_ids.isdisjoint(legacy_ids)


def test_all_fourteen_ai_source_schemas_are_adopted_byte_for_byte() -> None:
    with ZipFile(AI_PACKAGE) as archive:
        members = sorted(
            name
            for name in archive.namelist()
            if (
                "/schemas/tasks/" in name or "/schemas/eval/" in name
            )
            and name.endswith(".json")
        )
        assert len(members) == 14
        for member in members:
            relative = member.split("/schemas/", 1)[1]
            candidate = CONTRACTS_ROOT / "ai" / "schemas" / relative
            assert candidate.is_file(), f"missing adopted AI schema: {relative}"
            assert candidate.read_bytes() == archive.read(member)


def test_all_twelve_prompts_are_adopted_byte_for_byte() -> None:
    with ZipFile(AI_PACKAGE) as archive:
        members = sorted(
            name
            for name in archive.namelist()
            if "/prompts/" in name and name.endswith(".md")
        )
        assert len(members) == 12
        for member in members:
            relative = member.split("/prompts/", 1)[1]
            candidate = CONTRACTS_ROOT / "ai" / "prompts" / relative
            assert candidate.is_file(), f"missing adopted AI prompt: {relative}"
            assert candidate.read_bytes() == archive.read(member)


def test_ai_archive_exact_inventory_and_all_sha256sum_entries_are_valid() -> None:
    with ZipFile(AI_PACKAGE) as archive:
        members = archive.namelist()
        assert len(members) == 98
        assert len(members) == len(set(members))
        assert all(not name.endswith("/") for name in members)

        checksum_member = zip_member_with_suffix(archive, "/SHA256SUMS.txt")
        package_prefix = checksum_member.removesuffix("SHA256SUMS.txt")
        checksum_lines = (
            archive.read(checksum_member).decode("utf-8").splitlines()
        )
        assert len(checksum_lines) == 97

        declared: dict[str, str] = {}
        for line in checksum_lines:
            digest, separator, relative = line.partition("  ")
            assert separator == "  "
            assert len(digest) == 64
            assert all(character in "0123456789abcdef" for character in digest)
            assert relative and relative not in declared
            declared[relative] = digest

        expected_relatives = {
            name.removeprefix(package_prefix)
            for name in members
            if name != checksum_member
        }
        assert set(declared) == expected_relatives
        for relative, expected_digest in declared.items():
            assert (
                sha256(archive.read(package_prefix + relative)).hexdigest()
                == expected_digest
            )


def test_public_openapi_is_upstream_byte_frozen_and_ai_isolated() -> None:
    public_path = CONTRACTS_ROOT / "openapi-public.v0.1.yaml"
    with ZipFile(API_PACKAGE) as archive:
        member = zip_member_with_suffix(
            archive, "/RAOS_04_openapi_public_v0.1.yaml"
        )
        assert public_path.read_bytes() == archive.read(member)

    assert_public_isolation(load_yaml(public_path))


def test_compatibility_guards_reject_negative_mutations(tmp_path: Path) -> None:
    candidate = tmp_path / "contracts"
    shutil.copytree(CONTRACTS_ROOT, candidate)

    predecessor_schema = (
        candidate / "schemas" / "ai" / "claim-extraction-output.schema.json"
    )
    original = json.loads(predecessor_schema.read_text(encoding="utf-8"))
    original["title"] = "mutated in place"
    predecessor_schema.write_text(
        json.dumps(original, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="changed in place"):
        assert_predecessor_schema_compatibility(candidate)

    public = load_yaml(CONTRACTS_ROOT / "openapi-public.v0.1.yaml")
    public["paths"]["/api/v1/public/ai/jobs"] = {"get": {"responses": {}}}
    with pytest.raises(AssertionError):
        assert_public_isolation(public)
