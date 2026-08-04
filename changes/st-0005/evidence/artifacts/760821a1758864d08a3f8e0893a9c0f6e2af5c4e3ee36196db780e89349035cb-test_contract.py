"""Canonical and semantic contract binding for ST-0203."""

from __future__ import annotations

from typing import Any

import yaml

from scripts import build_st0203_queue_fake as generator


def _record(document: dict[str, Any], collection: str, identity: str) -> dict[str, Any]:
    matches = [item for item in document[collection] if item["id"] == identity]
    assert len(matches) == 1
    return matches[0]


def test_contract_matches_complete_reviewed_model(
    queue_contract: dict[str, Any],
) -> None:
    assert queue_contract == generator.EXPECTED_CONTRACT
    assert queue_contract["document"]["formal_verification"] == "NOT_EXECUTED"
    assert queue_contract["boundary"]["effective_canonical_status"] == "UNCHANGED"


def test_canonical_story_is_exactly_the_approved_fake_scope() -> None:
    path = (
        generator.REPO_ROOT
        / "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
    )
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    story = _record(document, "stories", "ST-0203")

    assert story["title"] == "Local queue abstraction"
    assert story["objective"] == "at-least-onceを再現するQueue fake"
    assert story["depends_on"] == ["ST-0102"]
    assert story["deliverables"] == ["queue port", "fake", "duplicate fixture"]
    assert story["acceptance_criteria"] == ["duplicate/out-of-order injection"]
    assert story["test_suites"] == ["TST-013"]
    assert story["open_decisions"] == []
    assert story["implementation_status"] == "NOT_STARTED"
    assert story["verification_status"] == "NOT_EXECUTED"


def test_tst013_release_boundary_remains_formal_ci_only() -> None:
    path = (
        generator.REPO_ROOT
        / "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
    )
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    suite = _record(document, "suites", "TST-013")

    assert suite["name"] == "Async delivery and idempotency"
    assert suite["purpose"] == "重複、順不同、retry、DLQ、lease"
    assert suite["candidate_tools"] == ["queue fake", "LocalStack/recorded"]
    assert suite["release_blocking"] is True
    assert suite["environments"] == ["CI"]
    assert suite["execution_status"] == "NOT_EXECUTED"


def test_provider_and_consumer_responsibilities_are_not_claimed(
    queue_contract: dict[str, Any],
) -> None:
    boundary = queue_contract["boundary"]
    assert boundary["external_broker"] == "NOT_IMPLEMENTED"
    assert boundary["provider_adapter"] == "NOT_IMPLEMENTED"
    assert boundary["worker_runtime"] == "NOT_IMPLEMENTED"
    assert boundary["durable_persistence"] == "NOT_IMPLEMENTED"
    assert boundary["consumer_idempotency_store"] == "NOT_IMPLEMENTED"
    assert boundary["formal_tst_013"] == "NOT_EXECUTED"


def test_fake_contract_forbids_nondeterministic_external_runtime(
    queue_contract: dict[str, Any],
) -> None:
    fake = queue_contract["fake"]
    assert fake["clock"] == "EXPLICIT_MANUAL_AWARE_DATETIME"
    assert fake["background_threads"] == "FORBIDDEN"
    assert fake["sleeps"] == "FORBIDDEN"
    assert fake["network"] == "FORBIDDEN"
    assert fake["provider_sdk"] == "FORBIDDEN"
