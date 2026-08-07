"""Frozen fixture and deterministic round-trip coverage for ST-0801."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time
from typing import Any

import pytest

from conftest import INVALID_FIXTURE_ROOT, VALID_FIXTURE_ROOT
import raos.domain.editorial.content_ast as loader_module
from raos.domain.editorial import (
    ContentAst,
    ContentAstValidationError,
    dump_content_ast_json,
    load_content_ast,
)


VALID_FIXTURES = tuple(sorted(VALID_FIXTURE_ROOT.glob("*.json")))
SCHEMA_INVALID_FIXTURES = tuple(sorted(INVALID_FIXTURE_ROOT.glob("INV-0*.json")))
DEFERRED_POLICY_FIXTURES = tuple(
    INVALID_FIXTURE_ROOT / name
    for name in (
        "INV-101-disclosure-not-first.json",
        "INV-102-missing-source-summary.json",
        "INV-103-missing-methodology-block.json",
        "INV-105-missing-required-article-block.json",
    )
)
DUPLICATE_BLOCK_FIXTURE = INVALID_FIXTURE_ROOT / "INV-104-duplicate-block-id.json"


@pytest.mark.parametrize("fixture", VALID_FIXTURES, ids=lambda path: path.stem)
def test_five_frozen_valid_fixtures_round_trip_deterministically(fixture) -> None:
    original = json.loads(fixture.read_text(encoding="utf-8"))

    content_ast = load_content_ast(fixture.read_bytes())
    first = dump_content_ast_json(content_ast)
    second = dump_content_ast_json(load_content_ast(first))

    assert isinstance(content_ast, ContentAst)
    assert json.loads(first) == original
    assert first == second


@pytest.mark.parametrize("fixture", SCHEMA_INVALID_FIXTURES, ids=lambda path: path.stem)
def test_ten_frozen_schema_invalid_fixtures_are_rejected(fixture) -> None:
    with pytest.raises(ContentAstValidationError) as captured:
        load_content_ast(fixture.read_bytes())

    assert captured.value.category == "SCHEMA"


def test_duplicate_block_id_fixture_is_the_only_ast_local_policy_rejection() -> None:
    with pytest.raises(ContentAstValidationError) as captured:
        load_content_ast(DUPLICATE_BLOCK_FIXTURE.read_bytes())

    assert captured.value.category == "AST_POLICY"
    assert captured.value.pointer == "/blocks"
    assert captured.value.keyword == "unique_block_id"


@pytest.mark.parametrize(
    "fixture", DEFERRED_POLICY_FIXTURES, ids=lambda path: path.stem
)
def test_template_policy_fixtures_remain_deferred_to_cont_slice_003(fixture) -> None:
    assert isinstance(load_content_ast(fixture.read_bytes()), ContentAst)


def test_frozen_fixture_inventory_is_exact() -> None:
    assert len(VALID_FIXTURES) == 5
    assert len(SCHEMA_INVALID_FIXTURES) == 10
    assert len(DEFERRED_POLICY_FIXTURES) == 4
    assert DUPLICATE_BLOCK_FIXTURE.is_file()


def test_serializer_rebuild_is_limited_to_exact_generated_regressions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = (
        "BlockDecisionSummary",
        "BlockSelectionCriteria",
        "BlockBulletList",
        "BlockNumberedList",
        "BlockProsCons",
        "BlockFaq",
    )
    assert (
        tuple(
            model_type.__name__
            for model_type in loader_module._SERIALIZER_REBUILD_MODELS
        )
        == expected
    )

    calls: list[str] = []

    def record_rebuild(
        model_type: type[object], *, force: bool, raise_errors: bool
    ) -> None:
        assert force is True
        assert raise_errors is False
        calls.append(model_type.__name__)

    for model_type in (
        *loader_module._SERIALIZER_REBUILD_MODELS,
        loader_module.ContentAst,
    ):
        monkeypatch.setattr(model_type, "model_rebuild", classmethod(record_rebuild))
    monkeypatch.setattr(loader_module, "_generated_models_ready", False)

    loader_module._ensure_generated_models_ready()
    loader_module._ensure_generated_models_ready()

    assert calls == [*expected, loader_module.ContentAst.__name__]


def test_concurrent_first_load_and_dump_rebuild_generated_models_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = VALID_FIXTURES[0]
    prepared = load_content_ast(fixture.read_bytes())
    model_types = (
        *loader_module._SERIALIZER_REBUILD_MODELS,
        loader_module.ContentAst,
    )
    calls: list[str] = []
    call_lock = threading.Lock()

    def replacement(name: str, original: Any) -> classmethod:
        def record_rebuild(
            model_type: type[object], *, force: bool, raise_errors: bool
        ) -> bool | None:
            del model_type
            with call_lock:
                calls.append(name)
            time.sleep(0.005)
            return original(force=force, raise_errors=raise_errors)

        return classmethod(record_rebuild)

    for model_type in model_types:
        monkeypatch.setattr(
            model_type,
            "model_rebuild",
            replacement(model_type.__name__, model_type.model_rebuild),
        )
    monkeypatch.setattr(loader_module, "_generated_models_ready", False)
    barrier = threading.Barrier(12)

    def run_load() -> ContentAst:
        barrier.wait()
        return load_content_ast(fixture.read_bytes())

    def run_dump() -> str:
        barrier.wait()
        return dump_content_ast_json(prepared)

    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(run_load) for _ in range(6)]
        futures.extend(executor.submit(run_dump) for _ in range(6))
        results = [future.result() for future in futures]

    assert sum(isinstance(result, ContentAst) for result in results) == 6
    assert sum(isinstance(result, str) for result in results) == 6
    assert calls == [model_type.__name__ for model_type in model_types]


def test_dump_reprojects_a_schema_valid_raw_block_snapshot() -> None:
    fixture = VALID_FIXTURES[0]
    content_ast = load_content_ast(fixture.read_bytes())
    original = json.loads(fixture.read_text(encoding="utf-8"))
    raw_block = content_ast.blocks[0].model_dump(
        mode="json", by_alias=True, exclude_unset=True
    )
    content_ast.blocks[0] = raw_block  # type: ignore[assignment]

    rendered = dump_content_ast_json(content_ast)

    assert json.loads(rendered) == original


def test_dump_rejects_invalid_raw_block_mutation_without_leaking_content(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = VALID_FIXTURES[0]
    content_ast = load_content_ast(fixture.read_bytes())
    raw_block = content_ast.blocks[1].model_dump(
        mode="json", by_alias=True, exclude_unset=True
    )
    raw_block["block_id"] = content_ast.blocks[0].block_id
    raw_block["content"][0]["text"] = "mutation-canary-secret"
    content_ast.blocks[1] = raw_block  # type: ignore[assignment]

    with pytest.raises(ContentAstValidationError) as captured:
        dump_content_ast_json(content_ast)

    rendered = f"{captured.value!s} {captured.value!r}"
    assert captured.value.category == "AST_POLICY"
    assert "mutation-canary" not in rendered
    assert capsys.readouterr() == ("", "")
