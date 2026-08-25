"""Shared exact ST-1803 fixtures and immutable rebuild helpers."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
import sys
from typing import Callable

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "python"))

from raos.adapters.recorded_gate2_observation import (  # noqa: E402
    RecordedGate2ObservationAdapter,
)
from raos.application.analytics.gate2_observation import (  # noqa: E402
    RecordedGate2ObservationJob,
)
from raos.domain.analytics.gate2_observation import (  # noqa: E402
    ArticleObservation,
    FixtureByteLength,
    Gate2ObservationReport,
    ObservationCommand,
    ObservationPeriod,
    PROGRAM,
    ProgramObservation,
    RecordedObservationBatch,
    Sha256Digest,
    canonical_entry_digest,
    canonical_input_digest,
)


CONTRACT_DIGEST = Sha256Digest(
    "a362c5cbef19c87dd518813460b1b2f9cecacff76bd008071a25eaffa865befe"
)
INPUT_DIGEST = Sha256Digest(
    "5dd59db906b6c3fbb234ec725fef375280f2b8234ceb94e339270b5abddb4e62"
)
FIXTURE_PATH = REPOSITORY_ROOT / (
    "changes/st-1803/fixtures/recorded-synthetic-gate2-observation.v1.json"
)
PERIOD = ObservationPeriod(date(2026, 1, 1), date(2026, 4, 1), date(2026, 4, 1))


@pytest.fixture
def fixture_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


@pytest.fixture
def command(fixture_bytes: bytes) -> ObservationCommand:
    return ObservationCommand(
        recording_id="five-slot-complete",
        fixture_digest=Sha256Digest.of(fixture_bytes),
        fixture_length=FixtureByteLength(len(fixture_bytes)),
        contract_digest=CONTRACT_DIGEST,
        expected_input_digest=INPUT_DIGEST,
        period=PERIOD,
        program_id=PROGRAM,
    )


@pytest.fixture
def batch(
    fixture_bytes: bytes, command: ObservationCommand
) -> RecordedObservationBatch:
    return RecordedGate2ObservationAdapter(fixture_bytes).read(command)


@pytest.fixture
def report(fixture_bytes: bytes, command: ObservationCommand) -> Gate2ObservationReport:
    return RecordedGate2ObservationJob(
        exchange=RecordedGate2ObservationAdapter(fixture_bytes)
    ).observe(command)


def rebuild_batch(
    original: RecordedObservationBatch,
    *,
    article_transform: Callable[[ArticleObservation], ArticleObservation] | None = None,
    program_transform: Callable[[ProgramObservation], ProgramObservation] | None = None,
) -> RecordedObservationBatch:
    """Re-chain a deliberate typed mutation without bypassing domain invariants."""

    rebuilt_articles: list[ArticleObservation] = []
    previous = Sha256Digest("0" * 64)
    for source in original.articles:
        transformed = source if article_transform is None else article_transform(source)
        payload = {
            "article_id": transformed.article_id,
            "attribution_basis": transformed.attribution_basis.value,
            "attribution_verified": transformed.attribution_verified,
            "cohort_maturity": transformed.cohort_maturity.value,
            "metrics": [metric.payload() for metric in transformed.metrics],
            "packet_sha256": transformed.packet_sha256.value,
            "period": transformed.period.payload(),
            "program": transformed.program_id,
            "slot": transformed.slot,
            "slug": transformed.slug,
        }
        entry = canonical_entry_digest(
            entry_type="ARTICLE",
            sequence=transformed.sequence,
            previous_entry_sha256=previous,
            payload=payload,
        )
        rebuilt = ArticleObservation(
            sequence=transformed.sequence,
            previous_entry_sha256=previous,
            entry_sha256=entry,
            slot=transformed.slot,
            article_id=transformed.article_id,
            slug=transformed.slug,
            packet_sha256=transformed.packet_sha256,
            period=transformed.period,
            program_id=transformed.program_id,
            cohort_maturity=transformed.cohort_maturity,
            attribution_basis=transformed.attribution_basis,
            attribution_verified=transformed.attribution_verified,
            metrics=transformed.metrics,
        )
        rebuilt_articles.append(rebuilt)
        previous = entry
    program_source = (
        original.program_observation
        if program_transform is None
        else program_transform(original.program_observation)
    )
    program_payload = {
        "metrics": [metric.payload() for metric in program_source.metrics],
        "period": program_source.period.payload(),
        "program": program_source.program_id,
    }
    program_entry = canonical_entry_digest(
        entry_type="PROGRAM",
        sequence=6,
        previous_entry_sha256=previous,
        payload=program_payload,
    )
    rebuilt_program = ProgramObservation(
        sequence=6,
        previous_entry_sha256=previous,
        entry_sha256=program_entry,
        period=program_source.period,
        program_id=program_source.program_id,
        metrics=program_source.metrics,
    )
    articles = tuple(rebuilt_articles)
    input_digest = canonical_input_digest(articles, rebuilt_program)
    return RecordedObservationBatch(
        recording_id=original.recording_id,
        recorded_at=original.recorded_at,
        fixture_digest=original.fixture_digest,
        fixture_length=original.fixture_length,
        contract_digest=original.contract_digest,
        input_digest=input_digest,
        context_period=original.context_period,
        program_id=original.program_id,
        articles=articles,
        program_observation=rebuilt_program,
        synthetic=True,
        append_only=True,
        immutable=True,
    )


def replace_metric(
    article: ArticleObservation, key: str, **changes: object
) -> ArticleObservation:
    metrics = tuple(
        replace(metric, **changes) if metric.metric_key == key else metric
        for metric in article.metrics
    )
    # This temporary object cannot be constructed with the stale entry hash, so
    # return an unchecked carrier shape through a fresh hash immediately.
    payload = {
        "article_id": article.article_id,
        "attribution_basis": article.attribution_basis.value,
        "attribution_verified": article.attribution_verified,
        "cohort_maturity": article.cohort_maturity.value,
        "metrics": [metric.payload() for metric in metrics],
        "packet_sha256": article.packet_sha256.value,
        "period": article.period.payload(),
        "program": article.program_id,
        "slot": article.slot,
        "slug": article.slug,
    }
    entry = canonical_entry_digest(
        entry_type="ARTICLE",
        sequence=article.sequence,
        previous_entry_sha256=article.previous_entry_sha256,
        payload=payload,
    )
    return ArticleObservation(
        sequence=article.sequence,
        previous_entry_sha256=article.previous_entry_sha256,
        entry_sha256=entry,
        slot=article.slot,
        article_id=article.article_id,
        slug=article.slug,
        packet_sha256=article.packet_sha256,
        period=article.period,
        program_id=article.program_id,
        cohort_maturity=article.cohort_maturity,
        attribution_basis=article.attribution_basis,
        attribution_verified=article.attribution_verified,
        metrics=metrics,
    )


__all__ = [
    "CONTRACT_DIGEST",
    "FIXTURE_PATH",
    "INPUT_DIGEST",
    "PERIOD",
    "REPOSITORY_ROOT",
    "rebuild_batch",
    "replace_metric",
]
