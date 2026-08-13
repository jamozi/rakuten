"""Compose exact ST-0805/ST-0502 results into one local draft exchange."""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
import re
from typing import Any, NoReturn, cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search import (
    CanonicalItemSearchPage,
    PersistenceExecutionStatus,
    ProviderMode,
    RateLimitMetadata,
    RakutenItemSearchResult,
    RawResponseReceipt,
    StorageExecutionStatus,
)
from raos.domain.editorial.market_learning_pilot import (
    BoundWordPressDraft,
    DraftDisposition,
    DraftOperation,
    MarketLearningPilotFailure,
    MarketLearningPilotFailureCode,
    MarketLearningPilotResult,
    POLICY_SERIALIZATION_PROFILE,
    PilotEconomics,
    PilotEvidenceRecord,
    PilotExecutionStatus,
    WORDPRESS_DRAFT_STATUS,
    WordPressDraftIntent,
    WordPressDraftReceipt,
    fail_market_learning_pilot,
)
from raos.domain.editorial.policy_engine import (
    ExecutionStatus,
    LocalEvaluationStatus,
    PUBLISH_THRESHOLD,
    PolicyEvaluationResult,
)
from raos.ports.wordpress_draft import WordPressDraftPort


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_POLICY_RESULT_KEYS = {
    "article_version_id",
    "authority",
    "contracts",
    "derived",
    "evaluated_at",
    "gates",
    "policy_assessments",
    "policy_findings",
    "predecessors",
    "profile",
    "quality_axes",
    "status",
    "waiver_attempts",
    "waiver_evaluations",
    "zero_tolerance",
}


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except TypeError:
        return False


def _policy_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.POLICY_RESULT_INVALID
            )
        result[key] = value
    return result


def _reject_policy_constant(value: str) -> NoReturn:
    del value
    fail_market_learning_pilot(MarketLearningPilotFailureCode.POLICY_RESULT_INVALID)


def _valid_policy_score(value: object) -> bool:
    if type(value) is not Decimal or not value.is_finite():
        return False
    representation = value.as_tuple()
    exponent = representation.exponent
    return bool(
        type(exponent) is int
        and len(representation.digits) <= 28
        and -12 <= exponent <= 12
        and PUBLISH_THRESHOLD <= value <= Decimal("100")
    )


def _policy_article_version_id(result: PolicyEvaluationResult) -> str:
    if (
        result.status is not LocalEvaluationStatus.EVALUATED
        or result.input_findings != ()
        or result.policy_findings != ()
        or result.waiver_evaluations != ()
        or not _valid_policy_score(result.raw_quality_score)
        or result.quality_threshold_met is not True
        or result.quality_floors_met is not True
        or result.policy_rules_passed is not True
        or result.zero_tolerance_clear is not True
        or result.quality_gates_passed is not True
        or result.predecessors_available is not True
        or result.local_eligibility is not True
        or result.post_publication_required_action is not None
    ):
        fail_market_learning_pilot(MarketLearningPilotFailureCode.POLICY_INELIGIBLE)
    if (
        result.local_result_serialization_profile != POLICY_SERIALIZATION_PROFILE
        or type(result.local_result_json) is not str
        or type(result.local_result_digest) is not str
        or _SHA256.fullmatch(result.local_result_digest) is None
        or result.publication_authorized is not False
        or result.production_eligible is not False
        or any(
            status is not ExecutionStatus.NOT_EXECUTED
            for status in (
                result.formal_test_status,
                result.live_validation_status,
                result.staging_status,
                result.release_status,
                result.production_status,
            )
        )
    ):
        fail_market_learning_pilot(MarketLearningPilotFailureCode.POLICY_RESULT_INVALID)
    try:
        encoded = result.local_result_json.encode("utf-8", errors="strict")
        payload = json.loads(
            result.local_result_json,
            object_pairs_hook=_policy_json_pairs,
            parse_constant=_reject_policy_constant,
        )
        canonical = json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except UnicodeError, ValueError, RecursionError:
        fail_market_learning_pilot(MarketLearningPilotFailureCode.POLICY_RESULT_INVALID)
    if (
        hashlib.sha256(encoded).hexdigest() != result.local_result_digest
        or canonical != result.local_result_json
        or type(payload) is not dict
        or set(payload) != _POLICY_RESULT_KEYS
        or payload.get("profile") != POLICY_SERIALIZATION_PROFILE
        or payload.get("status") != LocalEvaluationStatus.EVALUATED.value
        or type(payload.get("article_version_id")) is not str
    ):
        fail_market_learning_pilot(MarketLearningPilotFailureCode.POLICY_RESULT_INVALID)
    mapping = cast(dict[str, object], payload)
    authority = mapping.get("authority")
    derived = mapping.get("derived")
    exact_score = cast(Decimal, result.raw_quality_score)
    if exact_score.is_zero():
        raw_quality_score = "0"
    else:
        raw_quality_score = format(exact_score, "f")
        if "." in raw_quality_score:
            raw_quality_score = raw_quality_score.rstrip("0").rstrip(".")
    expected_derived: dict[str, object] = {
        "local_eligibility": True,
        "policy_rules_passed": True,
        "post_publication_required_action": None,
        "predecessors_available": True,
        "quality_floors_met": True,
        "quality_gates_passed": True,
        "quality_threshold_met": True,
        "raw_quality_score": raw_quality_score,
        "zero_tolerance_clear": True,
    }
    if (
        type(authority) is not dict
        or authority
        != {
            "formal_test": "NOT_EXECUTED",
            "live_validation": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "publication_authorized": False,
            "production_eligible": False,
            "release": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
        }
        or type(derived) is not dict
        or derived != expected_derived
        or mapping.get("policy_findings") != []
        or mapping.get("waiver_attempts") != []
        or mapping.get("waiver_evaluations") != []
    ):
        fail_market_learning_pilot(MarketLearningPilotFailureCode.POLICY_RESULT_INVALID)
    return cast(str, mapping["article_version_id"])


def _validate_rakuten(result: RakutenItemSearchResult) -> tuple[str, str]:
    page = result.page
    rate = result.rate
    if (
        result.provider_mode is not ProviderMode.RECORDED_TEST_ONLY
        or type(page) is not CanonicalItemSearchPage
        or type(rate) is not RateLimitMetadata
        or result.storage_status is not StorageExecutionStatus.NOT_EXECUTED
        or result.persistence_status is not PersistenceExecutionStatus.NOT_EXECUTED
        or result.live_eligible is not False
    ):
        fail_market_learning_pilot(
            MarketLearningPilotFailureCode.RAKUTEN_RESULT_INVALID
        )
    raw_artifact = page.raw_artifact
    if (
        type(raw_artifact) is not RawResponseReceipt
        or page.provider != "RAKUTEN_ICHIBA"
        or page.api_version != "2026-07-01"
        or page.page != 1
        or type(page.request_sha256) is not str
        or _SHA256.fullmatch(page.request_sha256) is None
        or raw_artifact.storage_status is not StorageExecutionStatus.NOT_EXECUTED
        or raw_artifact.uri is not None
        or type(raw_artifact.sha256) is not str
        or _SHA256.fullmatch(raw_artifact.sha256) is None
        or type(page.provider_rate_limit) is not RateLimitMetadata
        or page.provider_rate_limit != rate
    ):
        fail_market_learning_pilot(
            MarketLearningPilotFailureCode.RAKUTEN_RESULT_INVALID
        )
    return page.request_sha256, raw_artifact.sha256


@final
class MarketLearningPilotService:
    """Run one fail-closed local recorded draft operation."""

    __slots__ = ("_draft_port",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        draft_port: WordPressDraftPort,
    ) -> None:
        if type(environment) is not RuntimeEnvironment or environment not in {
            RuntimeEnvironment.ENV_DEV,
            RuntimeEnvironment.CI,
        }:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.ENVIRONMENT_DISABLED
            )
        if not _implements(draft_port, WordPressDraftPort):
            fail_market_learning_pilot()
        self._draft_port = draft_port

    def execute(
        self,
        *,
        pilot: PilotEconomics,
        intent: WordPressDraftIntent,
        policy_result: PolicyEvaluationResult,
        rakuten_result: RakutenItemSearchResult,
    ) -> MarketLearningPilotResult:
        if (
            type(pilot) is not PilotEconomics
            or type(intent) is not WordPressDraftIntent
            or type(policy_result) is not PolicyEvaluationResult
        ):
            fail_market_learning_pilot()
        if type(rakuten_result) is not RakutenItemSearchResult:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.RAKUTEN_RESULT_INVALID
            )
        article_version_id = _policy_article_version_id(policy_result)
        if article_version_id != intent.article_version_id:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.POLICY_RESULT_INVALID
            )
        request_fingerprint, raw_response_sha256 = _validate_rakuten(rakuten_result)
        candidate = BoundWordPressDraft.bind(
            intent=intent,
            pilot=pilot,
            policy_local_result_digest=policy_result.local_result_digest,
            rakuten_request_fingerprint=request_fingerprint,
            rakuten_raw_response_sha256=raw_response_sha256,
        )
        try:
            receipt = self._draft_port.apply(candidate)
        except MarketLearningPilotFailure:
            raise
        except Exception:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.DRAFT_EXCHANGE_UNAVAILABLE
            )
        self._validate_receipt(candidate, receipt)
        evidence = PilotEvidenceRecord.from_draft(candidate=candidate, receipt=receipt)
        return MarketLearningPilotResult(
            candidate=candidate,
            receipt=receipt,
            evidence=evidence,
        )

    @staticmethod
    def _validate_receipt(
        candidate: BoundWordPressDraft,
        receipt: object,
    ) -> None:
        if (
            type(receipt) is not WordPressDraftReceipt
            or type(receipt.draft_id) is not int
            or not 1 <= receipt.draft_id <= (1 << 63) - 1
            or receipt.operation is not candidate.intent.operation
            or type(receipt.disposition) is not DraftDisposition
            or receipt.status != WORDPRESS_DRAFT_STATUS
            or type(receipt.content_binding_sha256) is not str
            or _SHA256.fullmatch(receipt.content_binding_sha256) is None
            or receipt.content_binding_sha256 != candidate.content_binding_sha256
            or type(receipt.operation_binding_sha256) is not str
            or _SHA256.fullmatch(receipt.operation_binding_sha256) is None
            or receipt.operation_binding_sha256 != candidate.operation_binding_sha256
            or type(receipt.logical_draft_sha256) is not str
            or _SHA256.fullmatch(receipt.logical_draft_sha256) is None
            or receipt.network_status is not PilotExecutionStatus.NOT_EXECUTED
            or receipt.publication_authorized is not False
            or receipt.production_eligible is not False
        ):
            fail_market_learning_pilot(MarketLearningPilotFailureCode.OUTCOME_MISMATCH)
        if candidate.intent.operation is DraftOperation.CREATE_DRAFT:
            valid_dispositions = {
                DraftDisposition.CREATED,
                DraftDisposition.REPLAYED,
            }
        else:
            valid_dispositions = {
                DraftDisposition.UPDATED,
                DraftDisposition.REPLAYED,
            }
        if receipt.disposition not in valid_dispositions or (
            candidate.intent.existing_draft_id is not None
            and receipt.draft_id != candidate.intent.existing_draft_id
        ):
            fail_market_learning_pilot(MarketLearningPilotFailureCode.OUTCOME_MISMATCH)


__all__ = ["MarketLearningPilotService"]
