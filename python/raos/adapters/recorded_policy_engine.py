"""Strict recorded-synthetic adapter for the ST-0805 policy runtime V2."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from threading import RLock
from typing import Any, NoReturn, SupportsIndex, cast, final
import unicodedata
from uuid import UUID

from raos.adapters.recorded_comparison_validation import (
    load_recorded_comparison_fixture,
)
from raos.adapters.recorded_recommendation import (
    load_recorded_recommendation_fixture,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.article_lifecycle import (
    ArticleVersionState,
    BodySha256,
    SourcePacketVerification,
    VersionDisplayId,
    VersionSnapshot,
)
from raos.domain.editorial.article_plan import ArticlePlanType
from raos.domain.editorial.content_ast import load_content_ast
from raos.domain.editorial.ids import ArticleVersionId
from raos.domain.editorial.policy_engine import (
    CONTENT_TEST_MATRIX_SHA256,
    POLICY_CATALOG_ID,
    POLICY_CATALOG_SHA256,
    POLICY_CATALOG_VERSION,
    POLICY_DEFINITIONS,
    QUALITY_AXIS_DEFINITIONS,
    QUALITY_CATALOG_ID,
    QUALITY_CATALOG_SHA256,
    QUALITY_CATALOG_VERSION,
    QUALITY_GATE_DEFINITIONS,
    QUALITY_MODEL_VERSION,
    REVIEW_CHECKLIST_ID,
    REVIEW_CHECKLIST_SHA256,
    REVIEW_CHECKLIST_VERSION,
    ZERO_TOLERANCE_LABELS,
    AxisAssessmentState,
    BoundReference,
    ContractBindings,
    FindingTarget,
    FindingTargetType,
    GateAssessmentState,
    LocalEvaluationStatus,
    PolicyAssessment,
    PolicyEvaluationInput,
    PolicyRuleResult,
    PredecessorAssessment,
    PredecessorState,
    PredecessorStory,
    QualityAxisAssessment,
    QualityGateAssessment,
    ReferenceId,
    Sha256Digest as LegacySha256Digest,
    UtcInstant,
    VersionRef,
    WaiverAttempt,
    WaiverAuthorityClaim,
    WaiverScopeType,
    ZeroToleranceAssessment,
    ZeroToleranceState,
    evaluate_editorial_policy,
)
from raos.domain.editorial.policy_engine_v2 import (
    DraftAstBindingV2,
    PolicyContractBindingV2,
    PolicyEvaluationEnvelopeV2,
    PolicyEvaluationRecordReceiptV2,
    PolicyEvaluationReportV2,
    coverage_receipt_sha256,
    draft_ast_sha256,
    draft_binding_sha256,
    evaluate_editorial_policy_v2,
    recommendation_receipt_sha256,
)
from raos.domain.editorial.recommendation_v2 import (
    RecommendationRecordReceipt,
    evaluate_recommendations_v2,
    prohibited_ranking_alias,
)
from raos.domain.evidence.claim_evidence import (
    CoverageRecordReceipt,
    evaluate_claim_evidence,
)
from raos.domain.portfolio.workflow import EntityVersion, StrongEtag, UtcTimestamp
from raos.domain.shared.persistence import Sha256Digest


_MAX_FIXTURE_BYTES = 8 * 1024 * 1024
_MAX_JSON_NODES = 100_000
_MAX_COLLECTION = 4096
_SHA = frozenset("0123456789abcdef")
_ARTICLE_VERSION_REF = ReferenceId("ARTICLE-VERSION-0805-V2")
_ROOT_KEYS = (
    "schema_version",
    "local_status",
    "contract",
    "draft",
    "coverage",
    "recommendation",
    "policy_seed",
    "declared_hashes",
)


class RecordedPolicyError(ValueError):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_RECORDED_ST0805_V2")


class ProhibitedPolicyInputError(ValueError):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("PROHIBITED_ST0805_POLICY_INPUT")


def _fail() -> NoReturn:
    raise RecordedPolicyError() from None


def _reject_prohibited() -> NoReturn:
    raise ProhibitedPolicyInputError() from None


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or not key or len(key) > 120 or key in result:
            _fail()
        result[key] = value
    return result


def _mapping(value: object, keys: tuple[str, ...]) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail()
    mapping = cast(dict[object, object], value)
    if tuple(mapping) != keys:
        _fail()
    return cast(Mapping[str, object], mapping)


def _sequence(
    value: object,
    *,
    minimum: int = 0,
    maximum: int = _MAX_COLLECTION,
) -> list[object]:
    if type(value) is not list:
        _fail()
    sequence = cast(list[object], value)
    if not minimum <= len(sequence) <= maximum:
        _fail()
    return sequence


def _string(value: object, *, maximum: int = 512) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value != value.strip()
        or unicodedata.normalize("NFC", value) != value
        or any(unicodedata.category(character).startswith("C") for character in value)
    ):
        _fail()
    return value


def _integer(value: object, *, minimum: int = 0, maximum: int = (1 << 53) - 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _uuid(value: object) -> UUID:
    text = _string(value, maximum=36)
    try:
        parsed = UUID(text)
    except Exception:
        _fail()
    if str(parsed) != text or parsed.int == 0:
        _fail()
    return parsed


def _sha(value: object) -> Sha256Digest:
    text = _string(value, maximum=64)
    if len(text) != 64 or any(character not in _SHA for character in text):
        _fail()
    try:
        return Sha256Digest(text)
    except Exception:
        _fail()


def _instant(value: object) -> datetime:
    text = _string(value, maximum=32)
    if not text.endswith("Z"):
        _fail()
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except Exception:
        _fail()
    if (
        parsed.tzinfo is not timezone.utc
        or parsed.fold
        or parsed.isoformat().replace("+00:00", "Z") != text
    ):
        _fail()
    return parsed


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except Exception:
        _fail()


def _ordered_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("ascii")
    except Exception:
        _fail()


def _key_is_prohibited(value: str) -> bool:
    if value == "affiliate_content":
        return False
    normalized = unicodedata.normalize("NFKC", value).casefold()
    compact = "".join(character for character in normalized if character.isalnum())
    japanese = ("料率", "報酬", "収益", "利益", "成果報酬")
    return (
        prohibited_ranking_alias(value)
        or any(term in normalized for term in japanese)
        or any(
            term in compact
            for term in (
                "affiliate",
                "commission",
                "finance",
                "financial",
                "reward",
                "revenue",
                "profit",
                "sponsorbenefit",
                "epc",
                "rpm",
            )
        )
    )


def _bounded_tree(
    value: object,
    *,
    depth: int = 0,
    counter: list[int] | None = None,
) -> None:
    nodes = [0] if counter is None else counter
    nodes[0] += 1
    if depth > 40 or nodes[0] > _MAX_JSON_NODES:
        _fail()
    if type(value) is dict:
        mapping = cast(dict[object, object], value)
        if len(mapping) > _MAX_COLLECTION:
            _fail()
        for key, item in mapping.items():
            if type(key) is not str or not key or len(key) > 120:
                _fail()
            if _key_is_prohibited(key):
                _reject_prohibited()
            _bounded_tree(item, depth=depth + 1, counter=nodes)
    elif type(value) is list:
        sequence = cast(list[object], value)
        if len(sequence) > _MAX_COLLECTION:
            _fail()
        for item in sequence:
            _bounded_tree(item, depth=depth + 1, counter=nodes)
    elif value is None or type(value) in {str, int, bool}:
        if type(value) is str and len(value) > 1_048_576:
            _fail()
    else:
        _fail()


def _contract(value: object) -> PolicyContractBindingV2:
    mapping = _mapping(
        value,
        (
            "contract_id",
            "contract_version",
            "evaluator_version",
            "policy_catalog_sha256",
            "quality_catalog_sha256",
            "claim_evidence_policy_sha256",
            "recommendation_methodology_sha256",
            "legacy_policy_engine_sha256",
            "article_lifecycle_sha256",
            "content_ast_source_sha256",
            "st0804_domain_sha256",
        ),
    )
    result = PolicyContractBindingV2(
        contract_id=_string(mapping["contract_id"], maximum=80),
        contract_version=_string(mapping["contract_version"], maximum=32),
        evaluator_version=_string(mapping["evaluator_version"], maximum=80),
        policy_catalog_sha256=_sha(mapping["policy_catalog_sha256"]),
        quality_catalog_sha256=_sha(mapping["quality_catalog_sha256"]),
        claim_evidence_policy_sha256=_sha(mapping["claim_evidence_policy_sha256"]),
        recommendation_methodology_sha256=_sha(
            mapping["recommendation_methodology_sha256"]
        ),
        legacy_policy_engine_sha256=_sha(mapping["legacy_policy_engine_sha256"]),
        article_lifecycle_sha256=_sha(mapping["article_lifecycle_sha256"]),
        content_ast_source_sha256=_sha(mapping["content_ast_source_sha256"]),
        st0804_domain_sha256=_sha(mapping["st0804_domain_sha256"]),
    )
    if result != PolicyContractBindingV2.current():
        _fail()
    return result


def _draft(value: object) -> DraftAstBindingV2:
    mapping = _mapping(
        value,
        (
            "version_id",
            "display_id",
            "article_id",
            "version_no",
            "article_type",
            "title",
            "source_packet_version_id",
            "source_packet_verification",
            "based_on_version_id",
            "content_ast",
            "body_sha256",
            "state",
            "version",
            "etag",
            "created_at",
            "updated_at",
            "canonical_ast_sha256",
            "binding_sha256",
        ),
    )
    based_raw = mapping["based_on_version_id"]
    based_on_version_id = None if based_raw is None else _uuid(based_raw)
    content = mapping["content_ast"]
    try:
        ast = load_content_ast(_canonical_json_bytes(content))
        snapshot = VersionSnapshot(
            version_id=_uuid(mapping["version_id"]),
            display_id=VersionDisplayId(_string(mapping["display_id"], maximum=80)),
            article_id=_uuid(mapping["article_id"]),
            version_no=_integer(mapping["version_no"], minimum=1),
            article_type=ArticlePlanType(_string(mapping["article_type"], maximum=80)),
            title=_string(mapping["title"], maximum=300),
            source_packet_version_id=_uuid(mapping["source_packet_version_id"]),
            source_packet_verification=SourcePacketVerification(
                _string(mapping["source_packet_verification"], maximum=32)
            ),
            based_on_version_id=based_on_version_id,
            content_ast=ast,
            body_sha256=BodySha256(_sha(mapping["body_sha256"]).value),
            state=ArticleVersionState(_string(mapping["state"], maximum=32)),
            submitted_at=None,
            reviewed_at=None,
            approved_at=None,
            published_at=None,
            version=EntityVersion(_integer(mapping["version"])),
            etag=StrongEtag(_string(mapping["etag"], maximum=128)),
            created_at=UtcTimestamp(_instant(mapping["created_at"])),
            updated_at=UtcTimestamp(_instant(mapping["updated_at"])),
        )
        result = DraftAstBindingV2(
            snapshot=snapshot,
            canonical_ast_sha256=_sha(mapping["canonical_ast_sha256"]),
            binding_sha256=_sha(mapping["binding_sha256"]),
        )
    except RecordedPolicyError, ProhibitedPolicyInputError:
        raise
    except Exception:
        _fail()
    if result.canonical_ast_sha256 != draft_ast_sha256(
        snapshot
    ) or result.binding_sha256 != draft_binding_sha256(snapshot):
        _fail()
    return result


def _legacy_digest(label: str) -> LegacySha256Digest:
    return LegacySha256Digest(hashlib.sha256(label.encode("ascii")).hexdigest())


def _bound(reference: str, digest: str | None = None) -> BoundReference:
    return BoundReference(
        ReferenceId(reference),
        LegacySha256Digest(digest) if digest is not None else _legacy_digest(reference),
    )


def _legacy_contract() -> ContractBindings:
    return ContractBindings(
        policy_catalog_id=ReferenceId(POLICY_CATALOG_ID),
        policy_catalog_version=VersionRef(POLICY_CATALOG_VERSION),
        policy_catalog_sha256=LegacySha256Digest(POLICY_CATALOG_SHA256),
        quality_catalog_id=ReferenceId(QUALITY_CATALOG_ID),
        quality_catalog_version=VersionRef(QUALITY_CATALOG_VERSION),
        quality_model_version=VersionRef(QUALITY_MODEL_VERSION),
        quality_catalog_sha256=LegacySha256Digest(QUALITY_CATALOG_SHA256),
        review_checklist_id=ReferenceId(REVIEW_CHECKLIST_ID),
        review_checklist_version=VersionRef(REVIEW_CHECKLIST_VERSION),
        review_checklist_sha256=LegacySha256Digest(REVIEW_CHECKLIST_SHA256),
        content_test_matrix_sha256=LegacySha256Digest(CONTENT_TEST_MATRIX_SHA256),
    )


def _seed_records(
    value: object,
    *,
    identifier_key: str,
    state_key: str,
    expected_ids: tuple[str, ...],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in _sequence(value, minimum=len(expected_ids), maximum=len(expected_ids)):
        mapping = _mapping(raw, (identifier_key, state_key))
        identifier = _string(mapping[identifier_key], maximum=160)
        state = _string(mapping[state_key], maximum=64)
        if identifier in result:
            _fail()
        result[identifier] = state
    if tuple(sorted(result)) != tuple(sorted(expected_ids)):
        _fail()
    return result


def build_policy_input_from_seed(
    value: object,
    *,
    draft: DraftAstBindingV2,
    coverage_report_sha256: str,
    coverage_receipt_digest: str,
    recommendation_report_sha256: str,
    recommendation_receipt_digest: str,
) -> PolicyEvaluationInput:
    mapping = _mapping(
        value,
        (
            "evaluated_at",
            "policy_results",
            "axis_assessments",
            "zero_tolerance_assessments",
            "gate_assessments",
            "waiver_policy_ids",
        ),
    )
    policy_states = _seed_records(
        mapping["policy_results"],
        identifier_key="policy_id",
        state_key="result",
        expected_ids=tuple(item.policy_id for item in POLICY_DEFINITIONS),
    )
    axis_seed: dict[str, tuple[str, Decimal | None]] = {}
    for raw in _sequence(
        mapping["axis_assessments"],
        minimum=len(QUALITY_AXIS_DEFINITIONS),
        maximum=len(QUALITY_AXIS_DEFINITIONS),
    ):
        item = _mapping(raw, ("axis_id", "state", "score"))
        axis_id = _string(item["axis_id"], maximum=32)
        if axis_id in axis_seed:
            _fail()
        state = _string(item["state"], maximum=32)
        score_raw = item["score"]
        score: Decimal | None = None
        if score_raw is not None:
            rendered = _string(score_raw, maximum=32)
            try:
                score = Decimal(rendered)
            except Exception:
                _fail()
            if not score.is_finite() or format(score, "f") != rendered:
                _fail()
        axis_seed[axis_id] = (state, score)
    if tuple(sorted(axis_seed)) != tuple(
        sorted(item.axis_id for item in QUALITY_AXIS_DEFINITIONS)
    ):
        _fail()
    signal_states = _seed_records(
        mapping["zero_tolerance_assessments"],
        identifier_key="label",
        state_key="state",
        expected_ids=ZERO_TOLERANCE_LABELS,
    )
    gate_states = _seed_records(
        mapping["gate_assessments"],
        identifier_key="gate_id",
        state_key="state",
        expected_ids=tuple(item.gate_id for item in QUALITY_GATE_DEFINITIONS),
    )
    waiver_ids = tuple(
        _string(item, maximum=32)
        for item in _sequence(
            mapping["waiver_policy_ids"], maximum=len(POLICY_DEFINITIONS)
        )
    )
    if len(waiver_ids) != len(set(waiver_ids)) or any(
        item not in policy_states for item in waiver_ids
    ):
        _fail()
    evaluated_at = UtcInstant(_instant(mapping["evaluated_at"]))
    predecessor_material = {
        PredecessorStory.ST_0605: (
            "RESULT-ST_0605",
            coverage_report_sha256,
            "PROVENANCE-ST_0605",
            coverage_receipt_digest,
        ),
        PredecessorStory.ST_0802: (
            "RESULT-ST_0802",
            draft.binding_sha256.value,
            "PROVENANCE-ST_0802",
            draft.canonical_ast_sha256.value,
        ),
        PredecessorStory.ST_0804: (
            "RESULT-ST_0804",
            recommendation_report_sha256,
            "PROVENANCE-ST_0804",
            recommendation_receipt_digest,
        ),
    }
    predecessors = tuple(
        PredecessorAssessment(
            story_id=story,
            article_version_id=_ARTICLE_VERSION_REF,
            state=PredecessorState.AVAILABLE,
            result=_bound(result_ref, result_digest),
            provenance=_bound(provenance_ref, provenance_digest),
        )
        for story, (
            result_ref,
            result_digest,
            provenance_ref,
            provenance_digest,
        ) in predecessor_material.items()
    )
    policies: list[PolicyAssessment] = []
    for policy_definition in POLICY_DEFINITIONS:
        rule_result = PolicyRuleResult(policy_states[policy_definition.policy_id])
        suffix = policy_definition.policy_id.removeprefix("POL-CONT-")
        policies.append(
            PolicyAssessment(
                policy_id=policy_definition.policy_id,
                policy_version=VersionRef(POLICY_CATALOG_VERSION),
                policy_source_sha256=LegacySha256Digest(POLICY_CATALOG_SHA256),
                article_version_id=_ARTICLE_VERSION_REF,
                stage=policy_definition.stage,
                result=rule_result,
                target=FindingTarget(
                    FindingTargetType.ARTICLE_VERSION, _ARTICLE_VERSION_REF
                ),
                evidence=(
                    (_bound(f"EVIDENCE-POLICY-{suffix}"),)
                    if rule_result is not PolicyRuleResult.NOT_EVALUATED
                    else ()
                ),
                detector=_bound(f"DETECTOR-POLICY-{suffix}"),
            )
        )
    axes: list[QualityAxisAssessment] = []
    for axis_definition in QUALITY_AXIS_DEFINITIONS:
        raw_state, score = axis_seed[axis_definition.axis_id]
        state = AxisAssessmentState(raw_state)
        suffix = axis_definition.axis_id.removeprefix("QAX-")
        if (state is AxisAssessmentState.EVALUATED) != (score is not None):
            _fail()
        axes.append(
            QualityAxisAssessment(
                axis_id=axis_definition.axis_id,
                axis_code=axis_definition.code,
                quality_model_version=VersionRef(QUALITY_MODEL_VERSION),
                quality_source_sha256=LegacySha256Digest(QUALITY_CATALOG_SHA256),
                article_version_id=_ARTICLE_VERSION_REF,
                state=state,
                score=score,
                evidence=(
                    (_bound(f"EVIDENCE-AXIS-{suffix}"),)
                    if state is AxisAssessmentState.EVALUATED
                    else ()
                ),
                evaluator=_bound(f"EVALUATOR-AXIS-{suffix}"),
            )
        )
    signals = tuple(
        ZeroToleranceAssessment(
            label=label,
            article_version_id=_ARTICLE_VERSION_REF,
            state=ZeroToleranceState(signal_states[label]),
            evidence=(
                (_bound(f"EVIDENCE-SIGNAL-{index:03d}"),)
                if ZeroToleranceState(signal_states[label])
                is not ZeroToleranceState.NOT_EVALUATED
                else ()
            ),
            detector=_bound(f"DETECTOR-SIGNAL-{index:03d}"),
        )
        for index, label in enumerate(ZERO_TOLERANCE_LABELS, start=1)
    )
    gates: list[QualityGateAssessment] = []
    for gate_definition in QUALITY_GATE_DEFINITIONS:
        state = GateAssessmentState(gate_states[gate_definition.gate_id])
        suffix = gate_definition.gate_id.removeprefix("QG-CONT-")
        gates.append(
            QualityGateAssessment(
                gate_id=gate_definition.gate_id,
                stage=gate_definition.stage,
                quality_catalog_version=VersionRef(QUALITY_CATALOG_VERSION),
                quality_source_sha256=LegacySha256Digest(QUALITY_CATALOG_SHA256),
                article_version_id=_ARTICLE_VERSION_REF,
                state=state,
                failure_action=gate_definition.failure_action,
                evidence=(
                    (_bound(f"EVIDENCE-GATE-{suffix}"),)
                    if state is not GateAssessmentState.NOT_EVALUATED
                    else ()
                ),
                evaluator=_bound(f"EVALUATOR-GATE-{suffix}"),
            )
        )
    waivers: list[WaiverAttempt] = []
    for policy_id in waiver_ids:
        if PolicyRuleResult(policy_states[policy_id]) is not PolicyRuleResult.FAIL:
            _fail()
        suffix = policy_id.removeprefix("POL-CONT-")
        waivers.append(
            WaiverAttempt(
                policy_id=policy_id,
                policy_version=VersionRef(POLICY_CATALOG_VERSION),
                policy_source_sha256=LegacySha256Digest(POLICY_CATALOG_SHA256),
                article_version_id=_ARTICLE_VERSION_REF,
                scope_type=WaiverScopeType.ARTICLE_VERSION,
                scope_ref=_ARTICLE_VERSION_REF,
                reason=_bound(f"REASON-REF-{suffix}"),
                evidence=(_bound(f"WAIVER-EVIDENCE-{suffix}"),),
                expiry_at=UtcInstant(datetime(2026, 9, 30, tzinfo=timezone.utc)),
                compliance_approver=_bound(f"COMPLIANCE-APPROVER-{suffix}"),
                audit_event=_bound(f"AUDIT-EVENT-{suffix}"),
                authority_claim=WaiverAuthorityClaim.REQUESTED,
            )
        )
    policy_input = PolicyEvaluationInput(
        article_version_id=_ARTICLE_VERSION_REF,
        evaluated_at=evaluated_at,
        contracts=_legacy_contract(),
        predecessors=predecessors,
        policy_assessments=tuple(policies),
        axis_assessments=tuple(axes),
        zero_tolerance_assessments=signals,
        gate_assessments=tuple(gates),
        waiver_attempts=tuple(waivers),
    )
    evaluated = evaluate_editorial_policy(policy_input)
    if evaluated.status is LocalEvaluationStatus.INVALID_INPUT:
        _fail()
    return policy_input


def load_recorded_policy_fixture(payload: bytes) -> PolicyEvaluationEnvelopeV2:
    if type(payload) is not bytes or not payload or len(payload) > _MAX_FIXTURE_BYTES:
        _fail()
    try:
        root = json.loads(payload, object_pairs_hook=_pairs)
    except RecordedPolicyError:
        raise
    except Exception:
        _fail()
    _bounded_tree(root)
    mapping = _mapping(root, _ROOT_KEYS)
    if (
        _integer(mapping["schema_version"]) != 2
        or mapping["local_status"] != "LOCAL_IMPLEMENTATION_COMPLETE"
    ):
        _fail()
    contract = _contract(mapping["contract"])
    draft = _draft(mapping["draft"])
    recommendation_section = _mapping(
        mapping["recommendation"], ("request", "report", "receipt")
    )
    request_material = recommendation_section["request"]
    recommendation = load_recorded_recommendation_fixture(
        _ordered_json_bytes(request_material)
    )
    recommendation_report = evaluate_recommendations_v2(recommendation)
    recommendation_report.require_valid()
    if (
        _canonical_json_bytes(recommendation_section["report"])
        != recommendation_report.canonical_bytes()
    ):
        _fail()
    recommendation_receipt_mapping = _mapping(
        recommendation_section["receipt"],
        (
            "sequence",
            "report_sha256",
            "publication_authorized",
            "ranking_authorized",
        ),
    )
    recommendation_receipt = RecommendationRecordReceipt(
        sequence=_integer(recommendation_receipt_mapping["sequence"], minimum=1),
        report_sha256=_sha(recommendation_receipt_mapping["report_sha256"]),
        publication_authorized=_boolean(
            recommendation_receipt_mapping["publication_authorized"]
        ),
        ranking_authorized=_boolean(
            recommendation_receipt_mapping["ranking_authorized"]
        ),
    )
    recommendation_receipt.require_valid()
    if recommendation_receipt.report_sha256 != recommendation_report.report_sha256:
        _fail()
    coverage_section = _mapping(mapping["coverage"], ("request", "report", "receipt"))
    try:
        typed_request = cast(Mapping[str, object], request_material)
        comparison_request = cast(
            Mapping[str, object], typed_request["comparison_request"]
        )
        comparison_material = comparison_request["comparison"]
    except Exception:
        _fail()
    coverage_wrapper = {
        "schema_version": 2,
        "comparison": comparison_material,
        "claim_evidence": coverage_section["request"],
    }
    coverage_snapshot = load_recorded_comparison_fixture(
        _ordered_json_bytes(coverage_wrapper)
    ).claim_evidence
    coverage_report = evaluate_claim_evidence(coverage_snapshot)
    coverage_report.require_valid()
    if (
        _canonical_json_bytes(coverage_section["report"])
        != coverage_report.canonical_bytes()
    ):
        _fail()
    coverage_receipt_mapping = _mapping(
        coverage_section["receipt"],
        ("sequence", "report_sha256", "publication_authorized"),
    )
    coverage_receipt = CoverageRecordReceipt(
        sequence=_integer(coverage_receipt_mapping["sequence"], minimum=1),
        report_sha256=_sha(coverage_receipt_mapping["report_sha256"]),
        publication_authorized=_boolean(
            coverage_receipt_mapping["publication_authorized"]
        ),
    )
    coverage_receipt.require_valid()
    if coverage_receipt.report_sha256 != coverage_report.report_sha256:
        _fail()
    policy_input = build_policy_input_from_seed(
        mapping["policy_seed"],
        draft=draft,
        coverage_report_sha256=coverage_report.report_sha256.value,
        coverage_receipt_digest=coverage_receipt_sha256(coverage_receipt).value,
        recommendation_report_sha256=recommendation_report.report_sha256.value,
        recommendation_receipt_digest=recommendation_receipt_sha256(
            recommendation_receipt
        ).value,
    )
    declared = _mapping(
        mapping["declared_hashes"],
        (
            "coverage_report_sha256",
            "coverage_receipt_sha256",
            "recommendation_report_sha256",
            "recommendation_receipt_sha256",
            "policy_result_sha256",
            "evaluation_input_sha256",
        ),
    )
    exact = (
        ("coverage_report_sha256", coverage_report.report_sha256),
        ("coverage_receipt_sha256", coverage_receipt_sha256(coverage_receipt)),
        ("recommendation_report_sha256", recommendation_report.report_sha256),
        (
            "recommendation_receipt_sha256",
            recommendation_receipt_sha256(recommendation_receipt),
        ),
    )
    if any(_sha(declared[key]) != expected for key, expected in exact):
        _fail()
    return PolicyEvaluationEnvelopeV2(
        contract=contract,
        draft=draft,
        coverage_snapshot=coverage_snapshot,
        coverage_report=coverage_report,
        coverage_receipt=coverage_receipt,
        recommendation=recommendation,
        recommendation_report=recommendation_report,
        recommendation_receipt=recommendation_receipt,
        policy_input=policy_input,
        policy_result_sha256=_sha(declared["policy_result_sha256"]),
        evaluation_input_sha256=_sha(declared["evaluation_input_sha256"]),
    )


@final
class RecordedPolicyAdapter:
    __slots__ = (
        "_capacity",
        "_environment",
        "_lock",
        "_report_anchors",
        "_snapshot_anchors",
        "_snapshot_bytes",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        fixtures: Sequence[bytes],
        capacity: int = 64,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(capacity) is not int
            or not 1 <= capacity <= _MAX_COLLECTION
        ):
            _fail()
        if type(fixtures) is not tuple:
            _fail()
        raw_fixtures = cast(tuple[object, ...], fixtures)
        if not 1 <= len(raw_fixtures) <= _MAX_COLLECTION:
            _fail()
        normalized: list[bytes] = []
        anchors: list[tuple[UUID, str, str]] = []
        for payload in raw_fixtures:
            if type(payload) is not bytes:
                _fail()
            owned = bytes(payload)
            envelope = load_recorded_policy_fixture(owned)
            version_id = envelope.draft.snapshot.version_id
            anchors.append(
                (
                    version_id,
                    envelope.evaluation_input_sha256.value,
                    hashlib.sha256(owned).hexdigest(),
                )
            )
            normalized.append(owned)
        if len({item[0] for item in anchors}) != len(anchors):
            _fail()
        self._environment = environment
        self._capacity = capacity
        self._snapshot_bytes = tuple(normalized)
        self._snapshot_anchors = tuple(anchors)
        self._report_anchors: tuple[tuple[str, bytes], ...] = ()
        self._lock = RLock()

    @property
    def environment(self) -> RuntimeEnvironment:
        return self._environment

    def get_snapshot(
        self, article_version_id: ArticleVersionId
    ) -> PolicyEvaluationEnvelopeV2 | None:
        if type(article_version_id) is not ArticleVersionId:
            _fail()
        with self._lock:
            for payload, (version_id, input_hash, payload_hash) in zip(
                self._snapshot_bytes, self._snapshot_anchors, strict=True
            ):
                if version_id != article_version_id.value:
                    continue
                if hashlib.sha256(payload).hexdigest() != payload_hash:
                    _fail()
                envelope = load_recorded_policy_fixture(bytes(payload))
                if (
                    envelope.draft.snapshot.version_id != version_id
                    or envelope.evaluation_input_sha256.value != input_hash
                ):
                    _fail()
                return envelope
        return None

    def append_report(
        self,
        snapshot: PolicyEvaluationEnvelopeV2,
        report: PolicyEvaluationReportV2,
    ) -> PolicyEvaluationRecordReceiptV2:
        if (
            type(snapshot) is not PolicyEvaluationEnvelopeV2
            or type(report) is not PolicyEvaluationReportV2
        ):
            _fail()
        report.require_valid()
        version_id = snapshot.draft.snapshot.version_id
        with self._lock:
            stored: PolicyEvaluationEnvelopeV2 | None = None
            for payload, (candidate_id, input_hash, payload_hash) in zip(
                self._snapshot_bytes, self._snapshot_anchors, strict=True
            ):
                if candidate_id != version_id:
                    continue
                if hashlib.sha256(payload).hexdigest() != payload_hash:
                    _fail()
                candidate = load_recorded_policy_fixture(bytes(payload))
                if candidate.evaluation_input_sha256.value != input_hash:
                    _fail()
                stored = candidate
                break
            if stored is None:
                _fail()
            expected = evaluate_editorial_policy_v2(stored)
            observed = evaluate_editorial_policy_v2(snapshot)
            if (
                expected.canonical_bytes() != report.canonical_bytes()
                or observed.canonical_bytes() != report.canonical_bytes()
            ):
                _fail()
            digest = report.report_sha256.value
            encoded = report.canonical_bytes()
            for index, (current_digest, current_bytes) in enumerate(
                self._report_anchors, start=1
            ):
                if current_digest == digest:
                    if current_bytes != encoded:
                        _fail()
                    receipt = PolicyEvaluationRecordReceiptV2(
                        index, Sha256Digest(digest)
                    )
                    receipt.require_valid()
                    return receipt
            if len(self._report_anchors) >= self._capacity:
                _fail()
            self._report_anchors = (*self._report_anchors, (digest, encoded))
            receipt = PolicyEvaluationRecordReceiptV2(
                len(self._report_anchors), Sha256Digest(digest)
            )
            receipt.require_valid()
            return receipt

    def receipts(self) -> tuple[PolicyEvaluationRecordReceiptV2, ...]:
        with self._lock:
            return tuple(
                PolicyEvaluationRecordReceiptV2(index, Sha256Digest(digest))
                for index, (digest, _payload) in enumerate(
                    self._report_anchors, start=1
                )
            )

    def __repr__(self) -> str:
        return "RecordedPolicyAdapter(<redacted-st0805-v2>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded ST-0805 V2 adapter serialization is not supported")


__all__ = [
    "ProhibitedPolicyInputError",
    "RecordedPolicyAdapter",
    "RecordedPolicyError",
    "build_policy_input_from_seed",
    "load_recorded_policy_fixture",
]
