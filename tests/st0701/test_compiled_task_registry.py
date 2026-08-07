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
    path = tmp_path / "nested" / "registry.json"
    path.parent.mkdir()
    path.write_text("{}\n", encoding="utf-8")
    original_open = adapter_module.os.open
    calls: list[tuple[str, int, int | None, int]] = []

    def recording_open(
        target: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = original_open(target, flags, mode, dir_fd=dir_fd)
        calls.append((os.fsdecode(target), flags, dir_fd, descriptor))
        return descriptor

    monkeypatch.setattr(adapter_module.os, "open", recording_open)
    assert adapter_module._read_regular_file(path) == b"{}\n"
    absolute = Path(os.path.abspath(path))
    assert [target for target, *_rest in calls] == [
        absolute.anchor,
        *absolute.parts[1:],
    ]
    assert calls[0][2] is None
    for previous, current in zip(calls, calls[1:]):
        assert current[2] == previous[3]
        assert "/" not in current[0]
    assert all(flags & os.O_NOFOLLOW for _path, flags, _dir_fd, _fd in calls)
    assert all(flags & os.O_CLOEXEC for _path, flags, _dir_fd, _fd in calls)
    assert all(flags & os.O_DIRECTORY for _path, flags, _dir_fd, _fd in calls[:-1])
    assert all(not flags & os.O_NONBLOCK for _path, flags, _dir_fd, _fd in calls[:-1])
    assert calls[-1][1] & os.O_NONBLOCK
    assert not calls[-1][1] & os.O_DIRECTORY


@pytest.mark.parametrize(
    "flag_name",
    ["O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC"],
)
def test_compiled_registry_fails_closed_without_required_filesystem_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flag_name: str,
) -> None:
    path = tmp_path / "registry.json"
    path.write_bytes(b"safe\n")
    monkeypatch.setattr(adapter_module.os, flag_name, 0)

    with pytest.raises(
        TaskRegistryIntegrityError, match="filesystem safety is unavailable"
    ):
        adapter_module._read_regular_file(path)


def test_compiled_registry_missing_file_uses_sanitized_integrity_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(TaskRegistryIntegrityError, match="cannot resolve") as captured:
        adapter_module._read_regular_file(tmp_path / "private-missing-canary.json")
    assert "private-missing-canary" not in str(captured.value)


@pytest.mark.parametrize("link_leaf", [False, True], ids=["ancestor", "leaf"])
def test_compiled_registry_rejects_symlinks(
    tmp_path: Path,
    link_leaf: bool,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "registry.json").write_bytes(b"outside\n")
    if link_leaf:
        path = tmp_path / "linked.json"
        path.symlink_to(outside / "registry.json")
    else:
        linked = tmp_path / "linked"
        linked.symlink_to(outside, target_is_directory=True)
        path = linked / "registry.json"

    with pytest.raises(TaskRegistryIntegrityError, match="symlink"):
        adapter_module._read_regular_file(path)


def test_compiled_registry_rejects_hardlinked_file(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_bytes(b"linked\n")
    os.link(path, tmp_path / "second-name.json")

    with pytest.raises(TaskRegistryIntegrityError, match="one filesystem link"):
        adapter_module._read_regular_file(path)


def test_compiled_registry_rejects_filesystem_root_swap_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "registry.json"
    path.write_bytes(b"trusted\n")
    replacement = tmp_path / "replacement-root"
    replacement.mkdir()
    real_open = os.open
    swapped = False

    def open_replacement_root(
        target: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if os.fsdecode(target) == os.sep and dir_fd is None and not swapped:
            swapped = True
            return real_open(replacement, flags, mode)
        return real_open(target, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(adapter_module.os, "open", open_replacement_root)

    with pytest.raises(TaskRegistryIntegrityError, match="changed before open"):
        adapter_module._read_regular_file(path)
    assert swapped


def test_compiled_registry_rejects_filesystem_root_swap_after_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "registry.json"
    path.write_bytes(b"trusted\n")
    replacement = tmp_path / "replacement-root"
    replacement.mkdir()
    real_lstat = Path.lstat
    root_stats = 0

    def swapped_root_lstat(candidate: Path) -> os.stat_result:
        nonlocal root_stats
        if candidate == Path(os.sep):
            root_stats += 1
            if root_stats > 1:
                return real_lstat(replacement)
        return real_lstat(candidate)

    monkeypatch.setattr(adapter_module.Path, "lstat", swapped_root_lstat)

    with pytest.raises(TaskRegistryIntegrityError, match="path changed during read"):
        adapter_module._read_regular_file(path)
    assert root_stats == 2


def test_compiled_registry_rejects_ancestor_swap_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted = tmp_path / "trusted"
    (trusted / "nested").mkdir(parents=True)
    (trusted / "nested" / "registry.json").write_bytes(b"trusted\n")
    replacement = tmp_path / "replacement"
    (replacement / "nested").mkdir(parents=True)
    (replacement / "nested" / "registry.json").write_bytes(b"replacement\n")
    real_open = os.open
    swapped = False

    def swap_then_open(
        target: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if os.fsdecode(target) == "trusted" and not swapped:
            swapped = True
            trusted.rename(tmp_path / "captured-trusted")
            replacement.rename(trusted)
        return real_open(target, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(adapter_module.os, "open", swap_then_open)

    with pytest.raises(TaskRegistryIntegrityError, match="changed before open"):
        adapter_module._read_regular_file(trusted / "nested" / "registry.json")
    assert swapped


def test_compiled_registry_rejects_ancestor_swap_after_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted = tmp_path / "trusted"
    (trusted / "nested").mkdir(parents=True)
    (trusted / "nested" / "registry.json").write_bytes(b"trusted\n")
    replacement = tmp_path / "replacement"
    (replacement / "nested").mkdir(parents=True)
    (replacement / "nested" / "registry.json").write_bytes(b"replacement\n")
    real_open = os.open
    swapped = False

    def swap_after_open(
        target: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        descriptor = real_open(target, flags, mode, dir_fd=dir_fd)
        if os.fsdecode(target) == "trusted" and not swapped:
            swapped = True
            trusted.rename(tmp_path / "captured-trusted")
            replacement.rename(trusted)
        return descriptor

    monkeypatch.setattr(adapter_module.os, "open", swap_after_open)

    with pytest.raises(TaskRegistryIntegrityError) as exc_info:
        adapter_module._read_regular_file(trusted / "nested" / "registry.json")
    assert str(exc_info.value) in {
        "compiled registry path changed before open",
        "compiled registry path changed during read",
    }
    assert swapped


@pytest.mark.parametrize("swap_before_open", [True, False], ids=["before", "after"])
def test_compiled_registry_rejects_leaf_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    swap_before_open: bool,
) -> None:
    path = tmp_path / "registry.json"
    path.write_bytes(b"trusted\n")
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(b"replacement\n")
    real_open = os.open
    real_read = os.read
    target_descriptor: int | None = None
    swapped = False

    def tracked_open(
        target: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped, target_descriptor
        if os.fsdecode(target) == path.name and swap_before_open and not swapped:
            swapped = True
            path.rename(tmp_path / "captured-registry.json")
            replacement.rename(path)
        descriptor = real_open(target, flags, mode, dir_fd=dir_fd)
        if os.fsdecode(target) == path.name:
            target_descriptor = descriptor
        return descriptor

    def swap_then_read(descriptor: int, count: int) -> bytes:
        nonlocal swapped
        if descriptor == target_descriptor and not swap_before_open and not swapped:
            swapped = True
            path.rename(tmp_path / "captured-registry.json")
            replacement.rename(path)
        return real_read(descriptor, count)

    monkeypatch.setattr(adapter_module.os, "open", tracked_open)
    monkeypatch.setattr(adapter_module.os, "read", swap_then_read)

    expected_message = (
        "changed before open" if swap_before_open else "changed during read"
    )
    with pytest.raises(TaskRegistryIntegrityError, match=expected_message):
        adapter_module._read_regular_file(path)
    assert swapped


@pytest.mark.parametrize(
    "replacement",
    [b"mutated!", b"x", b"extended-content"],
    ids=["same-size", "truncated", "extended"],
)
def test_compiled_registry_rejects_same_inode_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: bytes,
) -> None:
    path = tmp_path / "registry.bin"
    path.write_bytes(b"original")
    real_read = os.read
    mutated = False

    def mutate_then_read(descriptor: int, count: int) -> bytes:
        nonlocal mutated
        if not mutated:
            mutated = True
            path.write_bytes(replacement)
            metadata = path.stat()
            os.utime(
                path,
                ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000_000),
            )
        return real_read(descriptor, count)

    monkeypatch.setattr(adapter_module.os, "read", mutate_then_read)

    with pytest.raises(
        TaskRegistryIntegrityError,
        match="changed during read|short compiled registry read",
    ):
        adapter_module._read_regular_file(path)
    assert mutated


def test_compiled_registry_enforces_exact_four_mibibyte_limit(
    tmp_path: Path,
) -> None:
    path = tmp_path / "registry.bin"
    path.write_bytes(b"x" * adapter_module.MAX_COMPILED_REGISTRY_BYTES)
    assert len(adapter_module._read_regular_file(path)) == 4 * 1024 * 1024

    path.write_bytes(b"x" * (adapter_module.MAX_COMPILED_REGISTRY_BYTES + 1))
    with pytest.raises(TaskRegistryIntegrityError, match="exceeds size limit"):
        adapter_module._read_regular_file(path)


def test_compiled_registry_rejects_short_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "registry.bin"
    path.write_bytes(b"content")
    monkeypatch.setattr(adapter_module.os, "read", lambda _descriptor, _count: b"")

    with pytest.raises(
        TaskRegistryIntegrityError, match="short compiled registry read"
    ):
        adapter_module._read_regular_file(path)


def test_compiled_registry_sanitizes_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "private-read-failure-canary"
    path = tmp_path / "registry.bin"
    path.write_bytes(b"content")

    def fail_read(_descriptor: int, _count: int) -> bytes:
        raise OSError(canary)

    monkeypatch.setattr(adapter_module.os, "read", fail_read)
    with pytest.raises(TaskRegistryIntegrityError, match="cannot read") as captured:
        adapter_module._read_regular_file(path)
    assert canary not in str(captured.value)


def test_compiled_registry_sanitizes_close_failure_and_closes_once_in_reverse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "private-close-failure-canary"
    path = tmp_path / "nested" / "registry.bin"
    path.parent.mkdir()
    path.write_bytes(b"content")
    real_open = os.open
    real_close = os.close
    opened: list[int] = []
    closed: list[int] = []
    failed = False

    def tracked_open(
        target: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = real_open(target, flags, mode, dir_fd=dir_fd)
        opened.append(descriptor)
        return descriptor

    def close_then_fail(descriptor: int) -> None:
        nonlocal failed
        real_close(descriptor)
        closed.append(descriptor)
        if not failed:
            failed = True
            raise OSError(canary)

    monkeypatch.setattr(adapter_module.os, "open", tracked_open)
    monkeypatch.setattr(adapter_module.os, "close", close_then_fail)
    with pytest.raises(TaskRegistryIntegrityError, match="cannot close") as captured:
        adapter_module._read_regular_file(path)
    assert canary not in str(captured.value)
    assert closed == list(reversed(opened))
    assert len(closed) == len(set(closed))


def test_compiled_registry_preserves_primary_failure_when_close_also_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "registry.bin"
    path.write_bytes(b"x" * (adapter_module.MAX_COMPILED_REGISTRY_BYTES + 1))
    real_close = os.close

    def close_then_fail(descriptor: int) -> None:
        real_close(descriptor)
        raise OSError("private cleanup detail")

    monkeypatch.setattr(adapter_module.os, "close", close_then_fail)
    with pytest.raises(TaskRegistryIntegrityError, match="exceeds size limit") as info:
        adapter_module._read_regular_file(path)
    assert "descriptor cleanup also failed" in getattr(info.value, "__notes__", ())


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
