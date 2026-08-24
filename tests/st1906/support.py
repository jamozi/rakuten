"""Trusted fixture constructors for ST-1906 tests and owner generation."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any, cast

from raos.adapters.recorded_causal_attribution import (
    RecordedCausalAttributionSource,
)
from raos.application.analytics.causal_attribution import (
    CausalAttributionEvaluationService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.analytics.causal_attribution import (
    CausalAttributionCommand,
    CausalAttributionScope,
    PrivacyReviewEvidence,
    PrivacyReviewStatus,
    digest_bytes,
)
from raos.domain.finance.attribution import (
    ContractArticle,
    MeasurementAttributionContract,
    MeasurementPeriod,
)
from raos.domain.ops.object_intake import Sha256Digest


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    ROOT / "changes/st-1906/fixtures/recorded/causal-attribution.synthetic.v1.json"
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


def contract_for(payload: bytes | None = None) -> MeasurementAttributionContract:
    document = fixture_document(payload)["document"]
    row = document["contract"]
    return MeasurementAttributionContract(
        articles=tuple(
            ContractArticle(
                slot=item["slot"],
                article_id=item["article_id"],
                slug=item["slug"],
                packet_sha256=Sha256Digest(item["packet_sha256"]),
                intent_classification=item["intent_classification"],
            )
            for item in row["articles"]
        ),
        source_contract_sha256=Sha256Digest(row["source_contract_sha256"]),
        program=row["program"],
        schema_version=row["schema_version"],
    )


def period_for(value: dict[str, Any]) -> MeasurementPeriod:
    return MeasurementPeriod(
        start_date=date.fromisoformat(value["start_date"]),
        end_exclusive_date=date.fromisoformat(value["end_exclusive_date"]),
    )


def privacy_for(value: dict[str, Any]) -> PrivacyReviewEvidence:
    raw_hash = value["review_sha256"]
    return PrivacyReviewEvidence(
        status=PrivacyReviewStatus(value["status"]),
        review_sha256=None if raw_hash is None else Sha256Digest(raw_hash),
        scope=value["scope"],
        synthetic=value["synthetic"],
        aggregate_only=value["aggregate_only"],
        personal_data=value["personal_data"],
        persistent_identifier=value["persistent_identifier"],
        raw_ip=value["raw_ip"],
        full_user_agent=value["full_user_agent"],
        free_text=value["free_text"],
        tracking_activation=value["tracking_activation"],
    )


def command_for(
    payload: bytes | None = None,
    *,
    scope: CausalAttributionScope = (
        CausalAttributionScope.RECORDED_SYNTHETIC_AGGREGATE_EVALUATION_ONLY
    ),
) -> CausalAttributionCommand:
    raw = fixture_bytes() if payload is None else payload
    document = fixture_document(raw)["document"]
    return CausalAttributionCommand(
        recording_id=document["recording_id"],
        experiment_id=document["experiment_id"],
        source_sha256=digest_bytes(raw),
        source_bytes=len(raw),
        contract=contract_for(raw),
        program=document["program"],
        period=period_for(document["period"]),
        privacy_review=privacy_for(document["privacy_review"]),
        preregistration_sha256=Sha256Digest(document["preregistration_sha256"]),
        scope=scope,
    )


def service_for(
    payload: bytes | None = None,
) -> CausalAttributionEvaluationService:
    raw = fixture_bytes() if payload is None else payload
    return CausalAttributionEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=RecordedCausalAttributionSource(raw),
    )
