"""Deterministic generation and adversarial source tests for ST-0701."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import build_st0701_ai_registry as generator
from raos.shared import ContractRepository


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPOSITORY_ROOT / "contracts" / "raos-v0.4"
TASK_REGISTRY_PATH = "contracts/ai/RAOS_05_ai_task_catalog_v0.1.yaml"
PROMPT_REGISTRY_PATH = "contracts/ai/RAOS_05_prompt_registry_v0.1.yaml"
ARTICLE_DRAFT_PROMPT_PATH = "contracts/ai/prompts/PROMPT-AI-ARTICLE-DRAFT_v1.md"


class FakeRepository:
    """In-memory mutation wrapper around an already verified repository."""

    def __init__(
        self,
        base: ContractRepository,
        replacements: dict[str, bytes],
        *,
        rebind_manifest: bool,
    ) -> None:
        self._base = base
        self._replacements = replacements
        artifacts: list[object] = []
        for artifact in base.artifacts:
            replacement = replacements.get(artifact.path)
            if replacement is None or not rebind_manifest:
                artifacts.append(artifact)
            else:
                artifacts.append(
                    SimpleNamespace(
                        path=artifact.path,
                        byte_count=len(replacement),
                        sha256=hashlib.sha256(replacement).hexdigest(),
                    )
                )
        self.artifacts = tuple(artifacts)

    def read_bytes(self, path: str) -> bytes:
        return self._replacements.get(path, self._base.read_bytes(path))


def _repin_registry(monkeypatch: pytest.MonkeyPatch, path: str, content: bytes) -> None:
    updated = tuple(
        replace(
            spec,
            byte_count=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
        if spec.path == path
        else spec
        for spec in generator.REGISTRY_SPECS
    )
    monkeypatch.setattr(generator, "REGISTRY_SPECS", updated)


def _snapshot(path: Path) -> tuple[int, int, int, int, int, int]:
    value = path.stat()
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_mode,
    )


def test_render_is_deterministic_and_matches_generated_files() -> None:
    first = generator.render_outputs(REPOSITORY_ROOT)
    second = generator.render_outputs(REPOSITORY_ROOT)
    assert first == second
    assert tuple(first) == (generator.OUTPUT_PATH, generator.MANIFEST_PATH)
    for relative, content in first.items():
        assert (REPOSITORY_ROOT / relative).read_bytes() == content


def test_cli_check_is_read_only() -> None:
    paths = tuple(
        REPOSITORY_ROOT / relative
        for relative in (generator.OUTPUT_PATH, generator.MANIFEST_PATH)
    )
    before = {path: _snapshot(path) for path in paths}
    result = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / generator.__file__), "--check"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert {path: _snapshot(path) for path in paths} == before


def test_check_detects_tampered_output_without_repairing_it(tmp_path: Path) -> None:
    expected = generator.render_outputs(REPOSITORY_ROOT)
    for relative, content in expected.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    target = tmp_path / generator.OUTPUT_PATH
    target.write_bytes(target.read_bytes() + b"\n")
    tampered = target.read_bytes()

    with pytest.raises(RuntimeError, match="out of date"):
        generator._check_outputs(expected, tmp_path)
    assert target.read_bytes() == tampered


def test_exact_pinned_canonical_anchors_compile_successfully() -> None:
    repository = ContractRepository(CONTRACT_ROOT)
    content = repository.read_bytes(TASK_REGISTRY_PATH)
    assert b"&id001" in content
    assert b"*id001" in content
    compiled = generator.compile_registry(repository)
    assert compiled["task_count"] == 12


def test_yaml_alias_cycles_and_amplification_fail_closed() -> None:
    with pytest.raises(RuntimeError, match="cycle"):
        generator._strict_yaml(b"root: &root\n  child: *root\n", source="cycle")

    lines = ["a0: &a0 [x, x]"]
    for index in range(1, 18):
        lines.append(f"a{index}: &a{index} [*a{index - 1}, *a{index - 1}]")
    lines.append("root: *a17")
    with pytest.raises(RuntimeError, match="graph limit"):
        generator._strict_yaml(("\n".join(lines) + "\n").encode(), source="bomb")


def test_duplicate_registry_key_fails_after_explicit_test_repin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = ContractRepository(CONTRACT_ROOT)
    content = base.read_bytes(TASK_REGISTRY_PATH)
    duplicate = content.replace(
        b"  task_code: ai.opportunity_assessment.v1\n",
        b"  task_code: ai.opportunity_assessment.v1\n"
        b"  task_code: ai.opportunity_assessment.v1\n",
        1,
    )
    _repin_registry(monkeypatch, TASK_REGISTRY_PATH, duplicate)
    repository = FakeRepository(
        base, {TASK_REGISTRY_PATH: duplicate}, rebind_manifest=True
    )
    with pytest.raises(RuntimeError, match="strict YAML"):
        generator.compile_registry(repository)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("path", "old", "new", "message"),
    [
        (
            PROMPT_REGISTRY_PATH,
            b"  task_code: ai.opportunity_assessment.v1\n",
            b"  task_code: ai.unregistered.v1\n",
            "frontmatter task_code conflict",
        ),
        (
            TASK_REGISTRY_PATH,
            b"  route_code: route.reasoning_high.v1\n",
            b"  route_code: route.unknown.v1\n",
            "broken Route reference",
        ),
    ],
)
def test_conflict_and_bad_reference_fail_after_explicit_test_repin(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    old: bytes,
    new: bytes,
    message: str,
) -> None:
    base = ContractRepository(CONTRACT_ROOT)
    content = base.read_bytes(path)
    mutated = content.replace(old, new, 1)
    assert mutated != content
    _repin_registry(monkeypatch, path, mutated)
    repository = FakeRepository(base, {path: mutated}, rebind_manifest=True)
    with pytest.raises(RuntimeError, match=message):
        generator.compile_registry(repository)  # type: ignore[arg-type]


def test_unpinned_registry_and_tampered_prompt_bytes_fail() -> None:
    base = ContractRepository(CONTRACT_ROOT)
    registry_content = base.read_bytes(TASK_REGISTRY_PATH) + b"\n"
    unpinned = FakeRepository(
        base, {TASK_REGISTRY_PATH: registry_content}, rebind_manifest=True
    )
    with pytest.raises(RuntimeError, match="manifest binding mismatch"):
        generator.compile_registry(unpinned)  # type: ignore[arg-type]

    prompt_content = base.read_bytes(ARTICLE_DRAFT_PROMPT_PATH) + b"\n"
    tampered = FakeRepository(
        base, {ARTICLE_DRAFT_PROMPT_PATH: prompt_content}, rebind_manifest=False
    )
    with pytest.raises(RuntimeError, match="artifact hash mismatch"):
        generator.compile_registry(tampered)  # type: ignore[arg-type]


def test_generation_has_no_network_path(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert generator.render_outputs(REPOSITORY_ROOT)[generator.OUTPUT_PATH]
