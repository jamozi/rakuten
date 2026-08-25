"""Shared deterministic ST-1905 fixture helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import UUID

from raos.adapters.recorded_advanced_rank_provider import (
    RecordedAdvancedRankProviderSource,
)
from raos.application.analytics.advanced_rank_provider import (
    AdvancedRankProviderEvaluationService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.analytics.advanced_rank_provider import (
    AdvancedRankProviderCommand,
    AdvancedRankProviderScope,
)
from raos.domain.analytics.keyword_rank import KeywordRankPeriod, Sha256Digest


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    REPO_ROOT / "changes/st-1905/fixtures/recorded/advanced-rank-provider.v1.json"
)
SITE_ID = UUID("018f3e90-7b00-7000-8000-000000001900")


def fixture_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


def command_for(
    payload: bytes | None = None,
    *,
    scope: AdvancedRankProviderScope = (
        AdvancedRankProviderScope.RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY
    ),
    date_from: date = date(2026, 8, 3),
    date_to: date = date(2026, 8, 4),
) -> AdvancedRankProviderCommand:
    content = fixture_bytes() if payload is None else payload
    return AdvancedRankProviderCommand(
        recording_id="st1905_recorded_provider_v1",
        site_id=SITE_ID,
        source_sha256=Sha256Digest.of(content),
        source_bytes=len(content),
        period=KeywordRankPeriod(date_from=date_from, date_to=date_to),
        scope=scope,
    )


def service_for(
    payload: bytes | None = None,
) -> AdvancedRankProviderEvaluationService:
    content = fixture_bytes() if payload is None else payload
    return AdvancedRankProviderEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=RecordedAdvancedRankProviderSource(content),
    )
