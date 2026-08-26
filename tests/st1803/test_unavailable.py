"""Missing, mismatched, immature, attribution and conservation boundaries."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from .support import PERIOD, rebuild_batch, replace_metric
from raos.domain.analytics.gate2_observation import (
    ArticleObservation,
    AttributionBasis,
    Availability,
    CohortMaturity,
    ObservationPeriod,
    ProgramObservation,
    RecordedObservationBatch,
    Sha256Digest,
    UnavailableReason,
    ValueState,
    build_gate2_observation_report,
    canonical_entry_digest,
)


def _metric(report, metric_id: str):
    return next(row for row in report.metrics if row.metric_id == metric_id)


def _clone_article(
    article: ArticleObservation, **changes: object
) -> ArticleObservation:
    values = {
        "sequence": article.sequence,
        "previous_entry_sha256": article.previous_entry_sha256,
        "slot": article.slot,
        "article_id": article.article_id,
        "slug": article.slug,
        "packet_sha256": article.packet_sha256,
        "period": article.period,
        "program_id": article.program_id,
        "cohort_maturity": article.cohort_maturity,
        "attribution_basis": article.attribution_basis,
        "attribution_verified": article.attribution_verified,
        "metrics": article.metrics,
    }
    values.update(changes)
    payload = {
        "article_id": values["article_id"],
        "attribution_basis": values["attribution_basis"].value,
        "attribution_verified": values["attribution_verified"],
        "cohort_maturity": values["cohort_maturity"].value,
        "metrics": [metric.payload() for metric in values["metrics"]],
        "packet_sha256": values["packet_sha256"].value,
        "period": values["period"].payload(),
        "program": values["program_id"],
        "slot": values["slot"],
        "slug": values["slug"],
    }
    digest = canonical_entry_digest(
        entry_type="ARTICLE",
        sequence=article.sequence,
        previous_entry_sha256=article.previous_entry_sha256,
        payload=payload,
    )
    return ArticleObservation(entry_sha256=digest, **values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("state", "value", "digest", "reason"),
    [
        (ValueState.NOT_OBSERVED, None, None, UnavailableReason.MISSING_INPUT),
        (ValueState.UNAVAILABLE, None, None, UnavailableReason.MISSING_INPUT),
        (
            ValueState.UNVERIFIED,
            100,
            Sha256Digest("1" * 64),
            UnavailableReason.UNVERIFIED_INPUT,
        ),
    ],
)
def test_missing_and_unverified_are_unavailable_never_zero(
    batch: RecordedObservationBatch,
    state: ValueState,
    value: int | None,
    digest: Sha256Digest | None,
    reason: UnavailableReason,
) -> None:
    changed = rebuild_batch(
        batch,
        article_transform=lambda article: (
            replace_metric(
                article,
                "search_impressions",
                state=state,
                value=value,
                input_sha256=digest,
            )
            if article.slot == 1
            else article
        ),
    )
    row = _metric(build_gate2_observation_report(changed), "search_ctr")
    assert row.availability is Availability.UNAVAILABLE
    assert row.value is None
    assert row.unavailable_reason is reason


def test_zero_denominator_is_unavailable_but_explicit_zero_numerator_is_zero(
    batch: RecordedObservationBatch,
) -> None:
    no_impressions = rebuild_batch(
        batch,
        article_transform=lambda article: replace_metric(
            replace_metric(
                article,
                "search_impressions",
                state=ValueState.OBSERVED_ZERO,
                value=0,
            ),
            "search_clicks",
            state=ValueState.OBSERVED_ZERO,
            value=0,
        ),
    )
    unavailable = _metric(build_gate2_observation_report(no_impressions), "search_ctr")
    assert unavailable.unavailable_reason is UnavailableReason.ZERO_DENOMINATOR
    zero_clicks = rebuild_batch(
        batch,
        article_transform=lambda article: replace_metric(
            article,
            "affiliate_clicks",
            state=ValueState.OBSERVED_ZERO,
            value=0,
        ),
    )
    available = _metric(
        build_gate2_observation_report(zero_clicks), "affiliate_click_rate"
    )
    assert available.availability is Availability.AVAILABLE
    assert str(available.value) == "0.000000"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        (
            {
                "period": ObservationPeriod(
                    date(2025, 1, 1), date(2025, 4, 1), date(2025, 4, 1)
                )
            },
            UnavailableReason.PERIOD_MISMATCH,
        ),
        ({"program_id": "OTHER_PROGRAM"}, UnavailableReason.PROGRAM_MISMATCH),
        (
            {"cohort_maturity": CohortMaturity.IMMATURE},
            UnavailableReason.COHORT_IMMATURE,
        ),
    ],
)
def test_mixed_period_program_and_immature_cohort_are_unavailable(
    batch: RecordedObservationBatch,
    changes: dict[str, object],
    reason: UnavailableReason,
) -> None:
    changed = rebuild_batch(
        batch,
        article_transform=lambda article: (
            _clone_article(article, **changes) if article.slot == 2 else article
        ),
    )
    row = _metric(build_gate2_observation_report(changed), "affiliate_click_rate")
    assert row.availability is Availability.UNAVAILABLE
    assert row.unavailable_reason is reason


def test_wrong_source_is_unavailable(
    batch: RecordedObservationBatch,
) -> None:
    changed = rebuild_batch(
        batch,
        article_transform=lambda article: (
            replace_metric(article, "article_views", source="SEARCH_CONSOLE")
            if article.slot == 1
            else article
        ),
    )
    row = _metric(build_gate2_observation_report(changed), "affiliate_click_rate")
    assert row.unavailable_reason is UnavailableReason.SOURCE_MISMATCH


@pytest.mark.parametrize(
    "changes",
    [
        {"attribution_verified": False},
        {"attribution_basis": AttributionBasis.UNVERIFIED},
    ],
)
def test_unverified_attribution_blocks_financial_metrics_only(
    batch: RecordedObservationBatch, changes: dict[str, object]
) -> None:
    changed = rebuild_batch(
        batch,
        article_transform=lambda article: (
            _clone_article(article, **changes) if article.slot == 4 else article
        ),
    )
    report = build_gate2_observation_report(changed)
    assert _metric(report, "search_ctr").availability is Availability.AVAILABLE
    assert (
        _metric(report, "confirmed_reward_per_click").unavailable_reason
        is UnavailableReason.ATTRIBUTION_UNVERIFIED
    )
    assert report.reward_conservation is Availability.UNAVAILABLE
    assert report.unattributed_confirmed_reward_jpy == 2500


def test_provider_total_mismatch_is_not_allocated_or_hidden(
    batch: RecordedObservationBatch,
) -> None:
    def alter(program: ProgramObservation) -> ProgramObservation:
        metrics = tuple(
            replace(metric, value=18000)
            if metric.metric_key == "provider_confirmed_reward_jpy"
            else metric
            for metric in program.metrics
        )
        payload = {
            "metrics": [metric.payload() for metric in metrics],
            "period": program.period.payload(),
            "program": program.program_id,
        }
        return ProgramObservation(
            sequence=6,
            previous_entry_sha256=program.previous_entry_sha256,
            entry_sha256=canonical_entry_digest(
                entry_type="PROGRAM",
                sequence=6,
                previous_entry_sha256=program.previous_entry_sha256,
                payload=payload,
            ),
            period=program.period,
            program_id=program.program_id,
            metrics=metrics,
        )

    changed = rebuild_batch(batch, program_transform=alter)
    report = build_gate2_observation_report(changed)
    assert report.reward_conservation is Availability.UNAVAILABLE
    assert report.reward_conservation_reason is UnavailableReason.CONSERVATION_MISMATCH
    assert report.direct_confirmed_reward_jpy == 15000
    assert report.unattributed_confirmed_reward_jpy == 2500
    assert report.provider_confirmed_reward_jpy == 18000


def test_finance_changes_cannot_change_candidate_selection(
    batch: RecordedObservationBatch,
) -> None:
    baseline = build_gate2_observation_report(batch)
    changed = rebuild_batch(
        batch,
        article_transform=lambda article: replace_metric(
            replace_metric(article, "direct_confirmed_reward_jpy", value=1),
            "incremental_cost_jpy",
            value=999999,
        ),
    )
    observed = build_gate2_observation_report(changed)
    assert observed.candidates == baseline.candidates
    assert _metric(observed, "search_ctr") == _metric(baseline, "search_ctr")
    assert observed.direct_confirmed_reward_jpy != baseline.direct_confirmed_reward_jpy


def test_period_context_itself_is_exact_and_immutable() -> None:
    assert PERIOD.elapsed_days == 90
    assert PERIOD.as_of_date == PERIOD.end_exclusive_date
