"""Fail-closed ENV-DEV/CI service for ST-1906 recorded causal analysis."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.analytics.causal_attribution import (
    CausalAttributionCommand,
    CausalAttributionFailure,
    CausalAttributionFailureCode,
    CausalAttributionReport,
    CausalAttributionScope,
    PrivacyReviewEvidence,
    RecordedCausalAttributionBatch,
    evaluate_recorded_causal_attribution,
    fail_causal_attribution,
)
from raos.domain.finance.attribution import (
    ContractArticle,
    MeasurementAttributionContract,
    MeasurementPeriod,
)
from raos.ports.causal_attribution import CausalAttributionEvidenceSource


def _local_environment(value: object) -> bool:
    return type(value) is RuntimeEnvironment and value in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }


def _validated_command(candidate: object) -> CausalAttributionCommand:
    if type(candidate) is not CausalAttributionCommand:
        fail_causal_attribution()
    try:
        contract = MeasurementAttributionContract(
            articles=tuple(
                ContractArticle(
                    slot=article.slot,
                    article_id=article.article_id,
                    slug=article.slug,
                    packet_sha256=article.packet_sha256,
                    intent_classification=article.intent_classification,
                )
                for article in candidate.contract.articles
            ),
            source_contract_sha256=candidate.contract.source_contract_sha256,
            program=candidate.contract.program,
            schema_version=candidate.contract.schema_version,
        )
        return CausalAttributionCommand(
            recording_id=candidate.recording_id,
            experiment_id=candidate.experiment_id,
            source_sha256=candidate.source_sha256,
            source_bytes=candidate.source_bytes,
            contract=contract,
            program=candidate.program,
            period=MeasurementPeriod(
                start_date=candidate.period.start_date,
                end_exclusive_date=candidate.period.end_exclusive_date,
            ),
            privacy_review=PrivacyReviewEvidence(
                status=candidate.privacy_review.status,
                review_sha256=candidate.privacy_review.review_sha256,
                scope=candidate.privacy_review.scope,
                synthetic=candidate.privacy_review.synthetic,
                aggregate_only=candidate.privacy_review.aggregate_only,
                personal_data=candidate.privacy_review.personal_data,
                persistent_identifier=candidate.privacy_review.persistent_identifier,
                raw_ip=candidate.privacy_review.raw_ip,
                full_user_agent=candidate.privacy_review.full_user_agent,
                free_text=candidate.privacy_review.free_text,
                tracking_activation=candidate.privacy_review.tracking_activation,
            ),
            preregistration_sha256=candidate.preregistration_sha256,
            release_decision_sha256=candidate.release_decision_sha256,
            method_version=candidate.method_version,
            parser_version=candidate.parser_version,
            scope=candidate.scope,
        )
    except CausalAttributionFailure:
        raise
    except Exception:
        fail_causal_attribution()


@final
class CausalAttributionEvaluationService:
    """Evaluate one aggregate recording with no operational authority."""

    __slots__ = ("_source",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        source: CausalAttributionEvidenceSource,
    ) -> None:
        try:
            implements = isinstance(
                cast(object, source), CausalAttributionEvidenceSource
            ) and callable(getattr(source, "read", None))
        except Exception:
            implements = False
        if not _local_environment(environment) or not implements:
            fail_causal_attribution()
        self._source = source

    def evaluate(self, command: CausalAttributionCommand) -> CausalAttributionReport:
        normalized = _validated_command(command)
        if (
            normalized.scope
            is not CausalAttributionScope.RECORDED_SYNTHETIC_AGGREGATE_EVALUATION_ONLY
        ):
            fail_causal_attribution(CausalAttributionFailureCode.FEATURE_DISABLED)
        observed: object = None
        try:
            observed = self._source.read(normalized)
        except CausalAttributionFailure:
            raise
        except Exception:
            fail_causal_attribution(CausalAttributionFailureCode.SOURCE_UNAVAILABLE)
        if type(observed) is not RecordedCausalAttributionBatch:
            fail_causal_attribution(CausalAttributionFailureCode.SOURCE_RESULT_INVALID)
        return evaluate_recorded_causal_attribution(normalized, observed)


__all__ = ("CausalAttributionEvaluationService",)
