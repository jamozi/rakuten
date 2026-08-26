"""Pure domain coverage for ST-1407 V2."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from uuid import UUID

import pytest

from raos.domain.editorial.policy_engine import POLICY_DEFINITIONS
from raos.domain.ops.external_policy_registry import (
    ALERT_CATALOG_ID,
    EXTERNAL_RULE_POLICY_LINKS,
    RUNBOOK_ID,
    EmptyAffectedMeaning,
    ExecutionStatus,
    ImpactQueryStatus,
    NotificationRoute,
    ReviewDueState,
    evaluate_external_policy_registry,
    registry_report_json,
    registry_report_payload,
    registry_request_payload,
)

from .support import (
    ACQUIRED_AT,
    DUE_AT,
    RULE_MAP,
    build_not_due_empty_request,
    build_request,
)


@pytest.mark.parametrize(
    ("external_rule_id", "policy_ids"),
    EXTERNAL_RULE_POLICY_LINKS,
)
def test_every_external_rule_has_exact_version_links_and_is_evaluable(
    external_rule_id: str,
    policy_ids: tuple[str, ...],
) -> None:
    request = build_request(external_rule_id=external_rule_id)

    report = evaluate_external_policy_registry(request)

    assert report.impact.status is ImpactQueryStatus.LOCAL_EVALUATED
    assert report.impact.changed_policy_ids == tuple(sorted(policy_ids))
    expected_matches = tuple(
        tuple(sorted(set(policy_ids).intersection(article.policy_ids)))
        for article in request.article_bindings
        if set(policy_ids).intersection(article.policy_ids)
    )
    assert (
        tuple(item.matched_policy_ids for item in report.impact.affected_articles)
        == expected_matches
    )


def test_external_rule_mapping_is_exactly_13_rules_and_only_st0805_policies() -> None:
    policy_ids = {definition.policy_id for definition in POLICY_DEFINITIONS}

    assert len(EXTERNAL_RULE_POLICY_LINKS) == 13
    assert tuple(RULE_MAP) == tuple(item[0] for item in EXTERNAL_RULE_POLICY_LINKS)
    assert {
        policy_id
        for _external_rule_id, linked in EXTERNAL_RULE_POLICY_LINKS
        for policy_id in linked
    } <= policy_ids


def test_impact_query_returns_only_exact_intersection() -> None:
    report = evaluate_external_policy_registry(build_request())

    assert len(report.impact.affected_articles) == 1
    affected = report.impact.affected_articles[0]
    assert str(affected.article_id) == "20000000-0000-4000-8000-000000001407"
    assert affected.matched_policy_ids == ("POL-CONT-010",)
    assert report.impact.empty_affected_meaning is EmptyAffectedMeaning.NOT_EMPTY


def test_empty_result_is_scoped_to_exact_complete_recorded_fixture() -> None:
    request = build_not_due_empty_request()

    report = evaluate_external_policy_registry(request)

    assert report.impact.affected_articles == ()
    assert (
        report.impact.empty_affected_meaning
        is EmptyAffectedMeaning.ZERO_WITHIN_EXACT_COMPLETE_RECORDED_FIXTURE
    )


@pytest.mark.parametrize(
    ("evaluated_at", "expected_state", "has_alert"),
    (
        (DUE_AT - timedelta(microseconds=1), ReviewDueState.NOT_DUE, False),
        (DUE_AT, ReviewDueState.DUE, False),
        (DUE_AT + timedelta(microseconds=1), ReviewDueState.OVERDUE, True),
    ),
)
def test_due_boundary_uses_only_explicit_utc_coordinates(
    evaluated_at: datetime,
    expected_state: ReviewDueState,
    has_alert: bool,
) -> None:
    request = build_request(evaluated_at=evaluated_at)

    report = evaluate_external_policy_registry(request)

    assert report.review.state is expected_state
    assert (report.review.alert_candidate is not None) is has_alert
    assert report.review.cadence_inferred is False


def test_overdue_alert_is_local_non_deliverable_candidate() -> None:
    report = evaluate_external_policy_registry(build_request())
    alert = report.review.alert_candidate

    assert alert is not None
    assert alert.alert_catalog_id == ALERT_CATALOG_ID
    assert alert.runbook_id == RUNBOOK_ID
    assert alert.severity == "SEV4"
    assert alert.route is NotificationRoute.LOCAL_LOG_ONLY
    assert alert.delivery_authorized is False
    assert alert.reviewer_assignment_authorized is False
    assert alert.audit_write_authorized is False
    assert alert.external_action_authorized is False


def test_report_never_grants_external_or_publication_authority() -> None:
    report = evaluate_external_policy_registry(build_request())

    assert report.official_source_attested is False
    assert report.current_source_verified is False
    assert report.legal_review_completed is False
    assert report.notification_delivered is False
    assert report.audit_written is False
    assert report.activation_authorized is False
    assert report.publication_authorized is False
    assert report.impact.article_mutation_authorized is False
    assert report.impact.recommendation_mutation_authorized is False
    assert report.impact.publication_authorized is False
    assert {
        report.live_status,
        report.staging_status,
        report.release_status,
        report.production_status,
    } == {ExecutionStatus.NOT_EXECUTED}


def test_report_json_is_byte_stable_and_self_hashing() -> None:
    request = build_request()
    left = evaluate_external_policy_registry(request)
    right = evaluate_external_policy_registry(request)

    assert left == right
    assert left.fingerprint == right.fingerprint
    assert registry_report_json(left) == registry_report_json(right)
    assert json.loads(registry_report_json(left)) == registry_report_payload(left)


@pytest.mark.parametrize(
    "variant",
    (
        "source_hash",
        "snapshot_id",
        "evaluated_at",
        "due_at",
        "external_rule",
    ),
)
def test_request_and_report_hashes_change_for_every_authority_coordinate(
    variant: str,
) -> None:
    base = build_request()
    if variant == "source_hash":
        changed = build_request(source_content_sha256="a" * 64)
    elif variant == "snapshot_id":
        changed = build_request(
            snapshot_id=UUID("10000000-0000-4000-8000-000000001408")
        )
    elif variant == "evaluated_at":
        changed = build_request(evaluated_at=base.evaluated_at + timedelta(seconds=1))
    elif variant == "due_at":
        changed = build_request(
            review_due_at=base.snapshot.review_due_at + timedelta(seconds=1)
        )
    else:
        changed = build_request(external_rule_id="EXT-RAKUTEN-003")

    base_report = evaluate_external_policy_registry(base)
    changed_report = evaluate_external_policy_registry(changed)

    assert changed.fingerprint != base.fingerprint
    assert changed_report.fingerprint != base_report.fingerprint


def test_request_payload_contains_no_url_body_legal_notification_or_finance_surface() -> (
    None
):
    payload = json.dumps(
        registry_request_payload(build_request()),
        ensure_ascii=True,
        sort_keys=True,
    ).lower()

    for prohibited in (
        "https://",
        "source_body",
        "raw_content",
        "legal_conclusion",
        "notification_destination",
        "review_body",
        "prompt",
        "secret",
        "commission",
        "epc",
        "rpm",
        "profit",
    ):
        assert prohibited not in payload


def test_request_time_cannot_precede_recorded_acquisition() -> None:
    with pytest.raises(ValueError, match="INVALID_ARGUMENT"):
        build_request(evaluated_at=ACQUIRED_AT - timedelta(microseconds=1))
