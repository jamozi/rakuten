"""Trusted fixture constructors for ST-1907 tests and owner generation."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any, cast

from raos.adapters.recorded_content_portfolio_optimizer import (
    RecordedContentPortfolioOptimizerSource,
)
from raos.application.portfolio.content_optimizer import (
    ContentPortfolioOptimizerService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.portfolio.content_optimizer import (
    PortfolioOptimizerCommand,
    PortfolioOptimizerScope,
    ObservationPeriod,
    Sha256Digest,
    digest_bytes,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "changes/st-1907/contracts/content-portfolio-optimizer.v1.yaml"
FIXTURE_PATH = ROOT / (
    "changes/st-1907/fixtures/recorded/"
    "content-portfolio-optimizer.blocked.synthetic.v1.json"
)


def fixture_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


def fixture_document(payload: bytes | None = None) -> dict[str, Any]:
    raw = fixture_bytes() if payload is None else payload
    return cast(dict[str, Any], json.loads(raw))


def canonical_payload(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def period_for(value: dict[str, Any]) -> ObservationPeriod:
    return ObservationPeriod(
        start_date=date.fromisoformat(value["start_date"]),
        end_exclusive_date=date.fromisoformat(value["end_exclusive_date"]),
    )


def command_for(
    payload: bytes | None = None,
    *,
    scope: PortfolioOptimizerScope = (
        PortfolioOptimizerScope.RECORDED_SYNTHETIC_PROPOSAL_EVALUATION_ONLY
    ),
) -> PortfolioOptimizerCommand:
    raw = fixture_bytes() if payload is None else payload
    document = fixture_document(raw)["document"]
    return PortfolioOptimizerCommand(
        recording_id=document["recording_id"],
        source_sha256=digest_bytes(raw),
        source_bytes=len(raw),
        contract_sha256=digest_bytes(CONTRACT_PATH.read_bytes()),
        expected_dependency_pack_sha256=Sha256Digest(
            document["dependency"]["pack_sha256"]
        ),
        measurement_contract_sha256=Sha256Digest(
            document["measurement_contract_sha256"]
        ),
        signal_policy_sha256=Sha256Digest(document["signal_policy_sha256"]),
        program=document["program"],
        period=period_for(document["period"]),
        scope=scope,
    )


def service_for(
    payload: bytes | None = None,
) -> ContentPortfolioOptimizerService:
    raw = fixture_bytes() if payload is None else payload
    return ContentPortfolioOptimizerService(
        environment=RuntimeEnvironment.CI,
        source=RecordedContentPortfolioOptimizerSource(raw),
    )


def ready_document() -> dict[str, Any]:
    value = fixture_document()
    dependency = value["document"]["dependency"]
    dependency.update(
        {
            "acceptance_criteria_satisfied": True,
            "actual_observation_count": 3,
            "human_decision_present": True,
            "local_integration_complete": True,
            "readiness": "VERIFIED_HUMAN_DECISION",
            "source_authorized": True,
            "source_outcome": None,
            "source_overall": None,
        }
    )
    value["signals"] = [
        signal(
            signal_id="withdraw-one",
            action="WITHDRAW",
            basis="VERIFIED_UNSUPPORTED_VALUE_REVIEW",
            article_ids=["article-z"],
        ),
        signal(
            signal_id="consolidate-one",
            action="CONSOLIDATE",
            basis="VERIFIED_DUPLICATE_INTENT_REVIEW",
            article_ids=["article-b", "article-c"],
        ),
        signal(
            signal_id="strengthen-one",
            action="STRENGTHEN",
            basis="MEASURED_VALUE_GAP_REVIEW",
            article_ids=["article-a"],
        ),
    ]
    return value


def signal(
    *,
    signal_id: str,
    action: str,
    basis: str,
    article_ids: list[str],
) -> dict[str, object]:
    return {
        "action": action,
        "article_ids": article_ids,
        "basis": basis,
        "cohort": "MATURE",
        "denominator_count": 100,
        "finance_signal_present": False,
        "period": {
            "duration_days": 14,
            "end_exclusive_date": "2026-01-15",
            "start_date": "2026-01-01",
        },
        "personal_data_present": False,
        "program": "WORDPRESS_BLOG_RAKUTEN_AFFILIATE",
        "publication_mutation_requested": False,
        "recommendation_order_change_requested": False,
        "signal_id": signal_id,
        "signal_policy_sha256": (
            "10871f65afe59fb6e44c6ac5401ce5e4b1b5cb0024497ae19fc43d6f6b997256"
        ),
        "source_sha256": "a" * 64,
        "verification": "VERIFIED",
    }
