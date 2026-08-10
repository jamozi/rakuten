"""Exact source and canonical contract observations for ST-1301."""

from __future__ import annotations

import hashlib
import json

import yaml

from conftest import REPOSITORY_ROOT
from raos.domain.finance.revenue_import import (
    RevenueEventType,
    RevenueRowParseStatus,
)


BOUND_HASHES = {
    "python/raos/domain/ops/object_intake.py": "7ba9fce9e91be4f4a76fe47c65b9582699b841743048a83629a12c8b54f916c7",
    "python/raos/application/ops/object_intake.py": "b75c86c003254436640ebecbf6f3c6aa399dbda334ca89cd4404102b800ca927",
    "python/raos/adapters/recorded_object_intake.py": "80e03fb20e2ae79ca3904993e092b2d9bb39d774eda17b4a91609dc36d9605cf",
    "changes/st-0305/contracts/publication-analytics-finance.v1.yaml": "2947fe100633a2611b9287c6530856b9679365bb10d4af4728a5148ed970377f",
    "contracts/raos-v0.4/contracts/schemas/imports/revenue-canonical-row.schema.json": "02bc3d854a7420a74a8b302342a9ad0e23cfe4529565716a185c333b43ebbff8",
    "contracts/raos-v0.4/contracts/schemas/jobs/finance-parse-revenue-csv-v1.schema.json": "1c537c4e76d8ff0a728e82ae69808ed8db6b11b45cff2d7e285ee1faaf0179c2",
    "contracts/raos-v0.4/contracts/catalogs/job-catalog.v0.4.yaml": "70a9926f1ac64bd47ce084c28ebb08792d63b07feb5ced85e40377815ba3aeb1",
    "contracts/raos-v0.4/contracts/catalogs/state-transition-catalog.v0.4.yaml": "203eb10d9b6fc6ba4fb0e9f0491f713c313a6a5627dcaf60b7ce53665ecec8a5",
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml": "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
}


def _yaml(path: str) -> object:
    return yaml.safe_load((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))


def test_exact_predecessor_and_canonical_bytes_are_bound() -> None:
    observed = {
        path: hashlib.sha256((REPOSITORY_ROOT / path).read_bytes()).hexdigest()
        for path in BOUND_HASHES
    }
    assert observed == BOUND_HASHES


def test_canonical_revenue_row_vocabulary_is_projected_without_extension() -> None:
    path = "contracts/raos-v0.4/contracts/schemas/imports/revenue-canonical-row.schema.json"
    schema = json.loads((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))
    properties = schema["properties"]
    assert schema["additionalProperties"] is False
    assert properties["provider_code"] == {"const": "RAKUTEN_AFFILIATE"}
    assert properties["currency"] == {"const": "JPY"}
    assert properties["event_type"]["enum"] == [
        value.value for value in RevenueEventType
    ]
    assert properties["confirmed_commission_jpy"]["type"] == ["integer", "null"]


def test_parse_status_vocabulary_is_closed() -> None:
    assert [value.value for value in RevenueRowParseStatus] == [
        "ACCEPTED",
        "REJECTED",
        "DUPLICATE",
        "IGNORED",
    ]


def test_parse_job_idempotency_basis_and_no_mutation_note_are_exact() -> None:
    catalog = _yaml("contracts/raos-v0.4/contracts/catalogs/job-catalog.v0.4.yaml")
    assert isinstance(catalog, dict)
    job = next(
        row
        for row in catalog["jobs"]
        if row["job_type"] == "finance.parse_revenue_csv.v1"
    )
    assert job["idempotency_basis"] == ["source_sha256", "parser_version_id", "dry_run"]
    assert job["lock_scope"] == "source_sha256"
    assert job["notes"] == ["No canonical commission mutation occurs in dry run."]


def test_revenue_state_order_and_guards_are_not_weakened() -> None:
    catalog = _yaml(
        "contracts/raos-v0.4/contracts/catalogs/state-transition-catalog.v0.4.yaml"
    )
    assert isinstance(catalog, dict)
    machine = next(
        row for row in catalog["machines"] if row["id"] == "SM-REVENUE-IMPORT"
    )
    assert machine["states"] == [
        "UPLOADED",
        "SCANNED",
        "PARSED",
        "DRY_RUN_READY",
        "CONFIRMED",
        "IMPORTED",
        "REJECTED",
        "FAILED",
    ]
    assert machine["guards"] == [
        "No commission mutation before CONFIRMED.",
        "Duplicate source SHA is rejected.",
    ]


def test_od003_remains_blocking_external_evidence_required() -> None:
    decisions = _yaml("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml")
    assert isinstance(decisions, dict)
    decision = next(row for row in decisions["items"] if row["id"] == "OD-003")
    assert decision == {
        "id": "OD-003",
        "topic": "rakuten_report_sample",
        "status": "EXTERNAL_EVIDENCE_REQUIRED",
        "required_by": "Finance adapter",
        "owner": "Business Owner",
        "decision_needed": "実際に利用可能な成果Reportの匿名化サンプル、列、状態、粒度を確認",
        "default_behavior": "Synthetic fixtureのみ。実成果帰属を未検証表示",
        "blocking": True,
    }


def test_story_remains_local_partial_and_formal_tests_unexecuted() -> None:
    stories = _yaml("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
    assert isinstance(stories, dict)
    story = next(row for row in stories["stories"] if row["id"] == "ST-1301")
    assert story["depends_on"] == ["ST-0406", "ST-0305"]
    assert story["open_decisions"] == ["OD-003"]
    assert story["test_suites"] == ["TST-026", "TST-030"]
    assert story["implementation_status"] == "NOT_STARTED"
    assert story["verification_status"] == "NOT_EXECUTED"
