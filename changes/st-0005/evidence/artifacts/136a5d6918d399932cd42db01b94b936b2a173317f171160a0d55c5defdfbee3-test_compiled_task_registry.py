from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from raos.adapters import ai_contract_registry as adapter_module
from raos.adapters.ai_contract_registry import CompiledTaskRegistry
from raos.domain.ai import (
    OutputSchemaContract,
    PromptContract,
    RouteContract,
    TaskContract,
)
from raos.ports import (
    InvalidTaskCode,
    TaskRegistry,
    TaskRegistryIntegrityError,
    UnknownTaskContract,
)
from raos.shared import ContractRepository


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPOSITORY_ROOT / "contracts" / "raos-v0.4"
GENERATED_REGISTRY = (
    REPOSITORY_ROOT / "changes" / "st-0701" / "generated" / "ai-task-registry.v1.json"
)
GENERATED_REGISTRY_SHA256 = (
    "33bbb3601aae2e02d37bf995a2522e67684befcd9a43ba4375b4a7685aedef07"
)
EXPECTED_TASK_CODES = (
    "ai.article_draft.v1",
    "ai.article_outline.v1",
    "ai.claim_extraction.v1",
    "ai.comparison_axis_suggestion.v1",
    "ai.internal_link_suggestion.v1",
    "ai.opportunity_assessment.v1",
    "ai.policy_assist.v1",
    "ai.quality_remediation.v1",
    "ai.refresh_diff_summary.v1",
    "ai.search_intent_classification.v1",
    "ai.source_packet_gap_analysis.v1",
    "ai.update_priority_explanation.v1",
)
PROMPT_PATH = "contracts/ai/prompts/PROMPT-AI-ARTICLE-DRAFT_v1.md"
PROMPT_SHA256 = "b868eb4e131da15cfc7c7be20dc538dd70a5fe58b42f04f8e69414d0ffee294c"
SCHEMA_PATH = "contracts/ai/schemas/tasks/ai.article_draft.v1.output.schema.json"
SCHEMA_ID = "https://schemas.raos.local/ai/article_draft/v1"
SCHEMA_SHA256 = "3f7fe932eee1d967455a2613000bda988edd1b1848bca52933cc56d9ed985eae"


def canonical_sha256(value: object) -> str:
    content = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def compiled_document(*, prompt_sha256: str = PROMPT_SHA256) -> dict[str, Any]:
    task = {
        "id": "AIT-004",
        "task_code": "ai.article_draft.v1",
        "lifecycle": "MVP",
        "risk_level": "CRITICAL",
        "prompt_code": "PROMPT-AI-ARTICLE-DRAFT",
        "route_code": "route.editorial_balanced.v1",
        "output_schema": "schemas/tasks/ai.article_draft.v1.output.schema.json",
        "output_schema_sha256": SCHEMA_SHA256,
    }
    route = {
        "route_code": "route.editorial_balanced.v1",
        "enabled": True,
        "status_boundary": "CANDIDATE_METADATA_ONLY",
    }
    unsigned_entry = {
        "task": task,
        "task_sha256": canonical_sha256(task),
        "prompt": {
            "prompt_code": "PROMPT-AI-ARTICLE-DRAFT",
            "version": 1,
            "task_code": "ai.article_draft.v1",
            "status": "CANDIDATE",
            "locale": "ja-JP",
            "artifact_path": PROMPT_PATH,
            "sha256": prompt_sha256,
            "metadata": {
                "prompt_code": "PROMPT-AI-ARTICLE-DRAFT",
                "task_code": "ai.article_draft.v1",
                "input_variables": ["task_context_json", "source_packet_json"],
            },
        },
        "output_schema": {
            "schema_id": SCHEMA_ID,
            "artifact_path": SCHEMA_PATH,
            "sha256": SCHEMA_SHA256,
            "metadata": {
                "schema_id": SCHEMA_ID,
                "path": "schemas/tasks/ai.article_draft.v1.output.schema.json",
                "kind": "task_output",
            },
        },
        "route": {
            "route_code": "route.editorial_balanced.v1",
            "sha256": canonical_sha256(route),
            "metadata": route,
        },
    }
    entry = {**unsigned_entry, "binding_sha256": canonical_sha256(unsigned_entry)}
    return {
        "document": {
            "id": "RAOS-AI-TASK-REGISTRY-001",
            "version": "1.0.0",
            "story_id": "ST-0701",
            "status": "IMPLEMENTATION_CANDIDATE",
        },
        "task_count": 1,
        "tasks": [entry],
    }


def write_compiled_registry(path: Path, document: object) -> str:
    content = (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def repin_binding(entry: dict[str, Any]) -> None:
    unsigned = {key: value for key, value in entry.items() if key != "binding_sha256"}
    entry["binding_sha256"] = canonical_sha256(unsigned)


def invalid_inner_registry_content(defect: str) -> bytes:
    document = compiled_document()
    entry = document["tasks"][0]

    if defect == "duplicate_json_key":
        content = (
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        existing_key = b'  "task_count": 1,\n'
        assert content.count(existing_key) == 1
        return content.replace(existing_key, existing_key * 2, 1)
    if defect == "wrong_exact_key_set":
        document["unexpected_CANARY"] = True
    elif defect == "task_count_mismatch":
        document["task_count"] = 2
    elif defect == "duplicate_task":
        document["task_count"] = 2
        document["tasks"].append(json.loads(json.dumps(entry)))
    elif defect == "stale_binding_sha256":
        entry["binding_sha256"] = "0" * 64
    elif defect == "stale_task_sha256":
        entry["task_sha256"] = "0" * 64
        repin_binding(entry)
    elif defect == "stale_route_sha256":
        entry["route"]["sha256"] = "0" * 64
        repin_binding(entry)
    elif defect == "schema_id_mismatch":
        wrong_schema_id = "https://schemas.raos.local/ai/CANARY/v1"
        entry["output_schema"]["schema_id"] = wrong_schema_id
        entry["output_schema"]["metadata"]["schema_id"] = wrong_schema_id
        repin_binding(entry)
    elif defect == "task_schema_binding_mismatch":
        entry["task"]["output_schema_sha256"] = "0" * 64
        entry["task_sha256"] = canonical_sha256(entry["task"])
        repin_binding(entry)
    else:  # pragma: no cover - the parameter table is closed below.
        raise AssertionError(f"unknown test defect: {defect}")

    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def test_happy_lookup_returns_deeply_immutable_hash_bound_contract(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ai-task-registry.v1.json"
    expected_sha256 = write_compiled_registry(path, compiled_document())
    registry = CompiledTaskRegistry(
        ContractRepository(CONTRACT_ROOT), path, expected_sha256=expected_sha256
    )

    assert isinstance(registry, TaskRegistry)
    assert registry.task_codes == ("ai.article_draft.v1",)
    contract = registry.get("ai.article_draft.v1")
    assert contract.catalog_id == "AIT-004"
    assert contract.prompt.sha256 == PROMPT_SHA256
    assert contract.output_schema.schema_id == SCHEMA_ID
    assert contract.route.route_code == "route.editorial_balanced.v1"
    assert contract.prompt.content.startswith("---\nprompt_code:")

    with pytest.raises(TypeError):
        contract.metadata["task_code"] = "changed"  # type: ignore[index]
    input_variables = contract.prompt.metadata["input_variables"]
    assert isinstance(input_variables, tuple)


def test_unknown_task_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "ai-task-registry.v1.json"
    expected_sha256 = write_compiled_registry(path, compiled_document())
    registry = CompiledTaskRegistry(
        ContractRepository(CONTRACT_ROOT), path, expected_sha256=expected_sha256
    )

    with pytest.raises(UnknownTaskContract, match="not registered"):
        registry.get("ai.unknown.v1")


def test_compiled_registry_hash_mismatch_fails_before_lookup(tmp_path: Path) -> None:
    path = tmp_path / "ai-task-registry.v1.json"
    write_compiled_registry(path, compiled_document())

    with pytest.raises(TaskRegistryIntegrityError, match="SHA-256 mismatch"):
        CompiledTaskRegistry(
            ContractRepository(CONTRACT_ROOT), path, expected_sha256="0" * 64
        )


@pytest.mark.parametrize(
    ("defect", "expected_message"),
    [
        ("duplicate_json_key", "invalid compiled AI registry JSON"),
        ("wrong_exact_key_set", "unexpected object shape in compiled registry"),
        ("task_count_mismatch", "compiled registry task count mismatch"),
        (
            "duplicate_task",
            "compiled tasks must be uniquely sorted by task_code",
        ),
        ("stale_binding_sha256", "task binding SHA-256 mismatch"),
        ("stale_task_sha256", "task SHA-256 mismatch"),
        ("stale_route_sha256", "route SHA-256 mismatch"),
        ("schema_id_mismatch", "task/output-schema binding mismatch"),
        ("task_schema_binding_mismatch", "task/output-schema binding mismatch"),
    ],
)
def test_valid_outer_hash_rejects_one_inner_registry_defect_with_sanitized_error(
    tmp_path: Path, defect: str, expected_message: str
) -> None:
    content = invalid_inner_registry_content(defect)
    path = tmp_path / "ai-task-registry.v1.json"
    path.write_bytes(content)
    expected_sha256 = hashlib.sha256(content).hexdigest()

    with pytest.raises(TaskRegistryIntegrityError) as captured:
        CompiledTaskRegistry(
            ContractRepository(CONTRACT_ROOT), path, expected_sha256=expected_sha256
        )
    assert str(captured.value) == expected_message
    assert "CANARY" not in str(captured.value)


def test_prompt_hash_mismatch_fails_during_construction(tmp_path: Path) -> None:
    path = tmp_path / "ai-task-registry.v1.json"
    document = compiled_document(prompt_sha256="0" * 64)
    expected_sha256 = write_compiled_registry(path, document)

    with pytest.raises(TaskRegistryIntegrityError, match="prompt SHA-256 mismatch"):
        CompiledTaskRegistry(
            ContractRepository(CONTRACT_ROOT), path, expected_sha256=expected_sha256
        )


def test_generated_registry_loads_all_exact_task_prompt_schema_route_bindings() -> None:
    repository = ContractRepository(CONTRACT_ROOT)
    registry = CompiledTaskRegistry(
        repository,
        GENERATED_REGISTRY,
        expected_sha256=GENERATED_REGISTRY_SHA256,
    )

    assert registry.task_codes == EXPECTED_TASK_CODES
    for task_code in EXPECTED_TASK_CODES:
        contract = registry.get(task_code)
        assert contract.task_code == task_code
        assert contract.metadata["prompt_code"] == contract.prompt.prompt_code
        assert contract.metadata["route_code"] == contract.route.route_code
        assert (
            contract.metadata["output_schema_sha256"] == contract.output_schema.sha256
        )
        assert contract.prompt.metadata["task_code"] == task_code
        assert contract.prompt.metadata["frontmatter"]["task_code"] == task_code  # type: ignore[index]
        assert (
            contract.output_schema.metadata["schema_id"]
            == contract.output_schema.schema_id
        )
        assert (
            repository.path_for_id(contract.output_schema.schema_id)
            == contract.output_schema.artifact_path
        )
        assert (
            hashlib.sha256(
                repository.read_bytes(contract.prompt.artifact_path)
            ).hexdigest()
            == contract.prompt.sha256
        )
        assert (
            hashlib.sha256(
                repository.read_bytes(contract.output_schema.artifact_path)
            ).hexdigest()
            == contract.output_schema.sha256
        )
        assert (
            repository.read_text(contract.prompt.artifact_path)
            == contract.prompt.content
        )
        assert (
            contract.output_schema.document["$id"] == contract.output_schema.schema_id
        )

    disabled = {
        task_code
        for task_code in EXPECTED_TASK_CODES
        if registry.get(task_code).prompt.status == "DISABLED"
    }
    assert disabled == {
        "ai.refresh_diff_summary.v1",
        "ai.source_packet_gap_analysis.v1",
    }


def test_generated_registry_unknown_task_fails_closed() -> None:
    registry = CompiledTaskRegistry(
        ContractRepository(CONTRACT_ROOT),
        GENERATED_REGISTRY,
        expected_sha256=GENERATED_REGISTRY_SHA256,
    )

    with pytest.raises(UnknownTaskContract, match="not registered"):
        registry.get("ai.not-registered.v1")


def test_generated_registry_rechecks_selected_prompt_bytes_on_lookup(
    tmp_path: Path,
) -> None:
    copied_contract_root = tmp_path / "raos-v0.4"
    shutil.copytree(CONTRACT_ROOT, copied_contract_root)
    repository = ContractRepository(copied_contract_root)
    registry = CompiledTaskRegistry(
        repository,
        GENERATED_REGISTRY,
        expected_sha256=GENERATED_REGISTRY_SHA256,
    )
    task_code = "ai.article_draft.v1"
    prompt_path = copied_contract_root / registry.get(task_code).prompt.artifact_path
    prompt_path.write_bytes(
        prompt_path.read_bytes() + b"\npost-construction mutation\n"
    )

    with pytest.raises(
        TaskRegistryIntegrityError, match="cannot read registered prompt artifact"
    ):
        registry.get(task_code)


def test_runtime_adapter_has_no_yaml_provider_network_or_database_import() -> None:
    source_path = (
        REPOSITORY_ROOT / "python" / "raos" / "adapters" / "ai_contract_registry.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.partition(".")[0])

    assert imported_roots.isdisjoint(
        {
            "alembic",
            "boto3",
            "httpx",
            "openai",
            "psycopg",
            "requests",
            "socket",
            "sqlalchemy",
            "urllib",
            "yaml",
        }
    )


def test_compiled_registry_path_must_be_absolute_and_normalized() -> None:
    with pytest.raises(TaskRegistryIntegrityError, match="absolute and normalized"):
        CompiledTaskRegistry(
            ContractRepository(CONTRACT_ROOT),
            Path("changes/st-0701/generated/ai-task-registry.v1.json"),
            expected_sha256=GENERATED_REGISTRY_SHA256,
        )

    with pytest.raises(TaskRegistryIntegrityError, match="cannot resolve"):
        CompiledTaskRegistry(
            ContractRepository(CONTRACT_ROOT),
            Path("/tmp/registry\0.json"),
            expected_sha256=GENERATED_REGISTRY_SHA256,
        )


def test_compiled_registry_fifo_and_open_errors_use_integrity_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fifo = tmp_path / "registry.fifo"
    os.mkfifo(fifo)
    with pytest.raises(TaskRegistryIntegrityError, match="not a regular file"):
        adapter_module._read_regular_file(fifo)

    regular = tmp_path / "registry.json"
    regular.write_text("{}\n", encoding="utf-8")

    def denied_open(*_args: object, **_kwargs: object) -> int:
        raise PermissionError("denied canary")

    monkeypatch.setattr(adapter_module.os, "open", denied_open)
    with pytest.raises(TaskRegistryIntegrityError, match="cannot open") as captured:
        adapter_module._read_regular_file(regular)
    assert "denied canary" not in str(captured.value)


def test_compiled_registry_open_uses_required_nonblocking_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "registry.json"
    path.write_text("{}\n", encoding="utf-8")
    original_open = adapter_module.os.open
    observed_flags: list[int] = []

    def recording_open(
        target: os.PathLike[str] | str, flags: int, *args: object, **kwargs: object
    ) -> int:
        observed_flags.append(flags)
        return original_open(target, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(adapter_module.os, "open", recording_open)
    assert adapter_module._read_regular_file(path) == b"{}\n"
    assert len(observed_flags) == 1
    required = os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    assert observed_flags[0] & required == required


def test_task_codes_and_unknown_lookup_revalidate_compiled_bytes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ai-task-registry.v1.json"
    expected_sha256 = write_compiled_registry(path, compiled_document())
    registry = CompiledTaskRegistry(
        ContractRepository(CONTRACT_ROOT), path, expected_sha256=expected_sha256
    )
    path.unlink()

    with pytest.raises(TaskRegistryIntegrityError, match="cannot resolve"):
        _ = registry.task_codes
    with pytest.raises(TaskRegistryIntegrityError, match="cannot resolve"):
        registry.get("ai.unknown.v1")


def test_nested_metadata_graph_limit_is_contained_by_integrity_error(
    tmp_path: Path,
) -> None:
    document = compiled_document()
    entry = document["tasks"][0]
    nested: dict[str, object] = {}
    cursor = nested
    for _ in range(102):
        child: dict[str, object] = {}
        cursor["next"] = child
        cursor = child
    entry["prompt"]["metadata"] = nested
    unsigned = {key: value for key, value in entry.items() if key != "binding_sha256"}
    entry["binding_sha256"] = canonical_sha256(unsigned)
    path = tmp_path / "ai-task-registry.v1.json"
    expected_sha256 = write_compiled_registry(path, document)

    with pytest.raises(TaskRegistryIntegrityError, match="JSON graph limit"):
        CompiledTaskRegistry(
            ContractRepository(CONTRACT_ROOT), path, expected_sha256=expected_sha256
        )


def test_public_domain_values_enforce_exact_nested_types_and_prompt_contract() -> None:
    digest = "0" * 64
    prompt_arguments: dict[str, object] = {
        "prompt_code": "PROMPT-CODE",
        "version": 1,
        "task_code": "ai.test.v1",
        "status": "CANDIDATE",
        "locale": "ja-JP",
        "artifact_path": "contracts/ai/prompts/PROMPT-CODE_v1.md",
        "sha256": digest,
        "content": "prompt body",
        "metadata": {},
    }
    with pytest.raises(ValueError, match="positive exact integer"):
        PromptContract(**{**prompt_arguments, "version": 0})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exact non-empty string"):
        PromptContract(**{**prompt_arguments, "content": 123})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="printable"):
        PromptContract(  # type: ignore[arg-type]
            **{**prompt_arguments, "prompt_code": "PROMPT\nINJECT"}
        )

    schema = OutputSchemaContract(
        schema_id="https://schemas.raos.local/ai/test/v1",
        artifact_path="contracts/ai/schemas/tasks/ai.test.v1.output.schema.json",
        sha256=digest,
        document={"$id": "https://schemas.raos.local/ai/test/v1"},
        metadata={},
    )
    route = RouteContract(
        route_code="route.test.v1",
        sha256=digest,
        metadata={"route_code": "route.test.v1"},
    )
    with pytest.raises(ValueError, match="exact PromptContract"):
        TaskContract(
            task_code="ai.test.v1",
            catalog_id="AIT-TEST",
            lifecycle="MVP",
            risk_level="LOW",
            sha256=digest,
            binding_sha256=digest,
            prompt=object(),  # type: ignore[arg-type]
            output_schema=schema,
            route=route,
            metadata={"route_code": "route.test.v1"},
        )


@pytest.mark.parametrize(
    "task_code",
    ["ai.bad\nlog.v1", "x" * 201, " ai.test.v1", "ai.test.v1\t"],
)
def test_invalid_task_code_is_rejected_without_echo(
    tmp_path: Path, task_code: str
) -> None:
    path = tmp_path / "ai-task-registry.v1.json"
    expected_sha256 = write_compiled_registry(path, compiled_document())
    registry = CompiledTaskRegistry(
        ContractRepository(CONTRACT_ROOT), path, expected_sha256=expected_sha256
    )

    with pytest.raises(InvalidTaskCode) as captured:
        registry.get(task_code)
    assert task_code not in str(captured.value)
