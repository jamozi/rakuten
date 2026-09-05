"""Authority-free plan generation is independent of actual private captures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from scripts import build_st1704_product_safety_manufacturer_plan as builder
from scripts.raos_build_core import (
    affected_owners,
    discover_registry,
    topological_order,
)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    relative = builder.owner.PORTFOLIO_RELATIVE_PATH
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    shutil.copyfile(builder.ROOT / relative, target)
    return tmp_path


def test_generation_uses_existing_owner_and_creates_no_verified_evidence(
    repository: Path,
) -> None:
    builder.generate(root=repository)
    builder.generate(root=repository, check=True)
    plan = builder.owner.load_product_safety_manufacturer_query_plan(repository)
    assert (
        plan.portfolio_sha256
        == hashlib.sha256(
            (repository / builder.owner.PORTFOLIO_RELATIVE_PATH).read_bytes()
        ).hexdigest()
    )
    empty = json.loads((repository / builder.OUTPUT_PATHS[1]).read_bytes())
    assert empty["publication_authority"] == "NONE"
    assert empty["tracked_document_is_evidence"] is False
    assert empty["evidence"] == []
    assert empty["expected_product_count"] == len(plan.products)
    assert not (repository / ".secrets").exists()


def test_article_edit_rebinds_only_empty_plan_not_capture_or_freshness(
    repository: Path,
) -> None:
    builder.generate(root=repository)
    before = {path: (repository / path).read_bytes() for path in builder.OUTPUT_PATHS}
    # Deliberately synthetic local bytes, never a real capture or credentials.
    sentinel = repository / ".secrets/synthetic-untouched.capture"
    sentinel.parent.mkdir(mode=0o700)
    sentinel.write_bytes(b"SYNTHETIC_NOT_AN_EVIDENCE_RECEIPT")
    sentinel_before = (sentinel.read_bytes(), sentinel.stat().st_mtime_ns)
    portfolio_path = repository / builder.owner.PORTFOLIO_RELATIVE_PATH
    portfolio = json.loads(portfolio_path.read_bytes())
    portfolio["articles"][-1]["title"] = "Synthetic title change"
    portfolio_path.write_text(
        json.dumps(portfolio, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(builder.GenerationFailure, match="PLAN_DRIFT"):
        builder.generate(root=repository, check=True)
    assert {
        path: (repository / path).read_bytes() for path in builder.OUTPUT_PATHS
    } == before
    builder.generate(root=repository)
    builder.generate(root=repository, check=True)
    assert all((repository / path).read_bytes() != before[path] for path in before)
    assert (sentinel.read_bytes(), sentinel.stat().st_mtime_ns) == sentinel_before
    empty = json.loads((repository / builder.OUTPUT_PATHS[1]).read_bytes())
    assert empty["evidence"] == []
    assert empty["tracked_document_is_evidence"] is False
    assert empty["publication_authority"] == "NONE"
    assert not ({"retrieved_at", "checked_at_utc", "verified"} & set(empty))


def test_invalid_portfolio_does_not_partially_write_generated_outputs(
    repository: Path,
) -> None:
    builder.generate(root=repository)
    before = {path: (repository / path).read_bytes() for path in builder.OUTPUT_PATHS}
    portfolio_path = repository / builder.owner.PORTFOLIO_RELATIVE_PATH
    portfolio = json.loads(portfolio_path.read_bytes())
    portfolio["schema"] = "SYNTHETIC_INVALID_SCHEMA"
    portfolio_path.write_text(json.dumps(portfolio), encoding="utf-8")
    with pytest.raises(builder.owner.ProductSafetyManufacturerCaptureFailure):
        builder.generate(root=repository)
    assert {
        path: (repository / path).read_bytes() for path in builder.OUTPUT_PATHS
    } == before


def test_output_symlink_cannot_redirect_generation(repository: Path) -> None:
    output = repository / builder.OUTPUT_PATHS[0]
    output.parent.mkdir(parents=True)
    unrelated = repository / "synthetic-unrelated.txt"
    unrelated.write_bytes(b"UNRELATED")
    output.symlink_to(unrelated)
    with pytest.raises(builder.GenerationFailure, match="OUTPUT_UNSAFE"):
        builder.generate(root=repository)
    assert unrelated.read_bytes() == b"UNRELATED"
    assert not (repository / builder.OUTPUT_PATHS[1]).exists()


def test_shared_generation_orders_empty_contract_before_consumers() -> None:
    registry = discover_registry()
    owner_id = "build_st1704_product_safety_manufacturer_plan"
    spec = registry[owner_id]
    assert set(spec.outputs) == set(builder.OUTPUT_PATHS)
    assert spec.supports_check is True
    assert spec.output_scope == "tracked"
    assert {item.uri for item in spec.inputs} >= {
        "repo://" + path.as_posix() for path in builder.INPUT_PATHS
    }
    assert owner_id in affected_owners(
        registry, [builder.owner.PORTFOLIO_RELATIVE_PATH]
    )
    ordered = topological_order(registry)
    for consumer in (
        "build_st1704_self_hosted_editorial_manifest",
        "build_st1704_reader_claim_coverage",
        "build_wordpress_mcp_v1",
    ):
        assert owner_id in registry[consumer].owner_dependencies
        assert ordered.index(owner_id) < ordered.index(consumer)


def test_tracked_empty_contracts_match_current_authoring() -> None:
    builder.generate(check=True)
