"""Bounded ENV-DEV/CI adapter for recorded ST-0605 snapshots and reports."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from threading import RLock
from typing import Any, NoReturn, SupportsIndex, cast, final
from uuid import UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.ids import ArticleVersionId
from raos.domain.evidence.claim_evidence import (
    ApprovedPacketBinding,
    ArticleEvidenceBinding,
    CitationId,
    ClaimEvidenceCoverageReport,
    ClaimEvidenceSnapshot,
    ClaimRequirementProof,
    ConflictId,
    ConflictStatus,
    CoverageContractBinding,
    CoverageRecordReceipt,
    EvidenceCitation,
    EvidenceConflict,
    EvidenceFact,
    EvidenceIdentityBinding,
    EvidenceLink,
    EvidenceOrigin,
    EvidenceSnapshot,
    EvidenceSource,
    EvidenceValidationAttestation,
    IdentityStatus,
    PolicyClaim,
    PolicyClaimType,
    PolicyLinkSupportType,
    PolicySourceTier,
    UnknownValueHandling,
    ValidationAttestationKind,
    ValidationAttestationOrigin,
    evaluate_claim_evidence,
)
from raos.domain.evidence.enums import (
    SourcePacketVersionStatus,
    SourceSnapshotValidationStatus,
)
from raos.domain.evidence.ids import (
    ClaimId,
    FactId,
    SourceId,
    SourcePacketId,
    SourcePacketVersionId,
    SourceSnapshotId,
)
from raos.domain.shared.persistence import AwareUtcDateTime, Sha256Digest


_MAX_FIXTURE_BYTES = 1_048_576
_MAX_CAPACITY = 10_000


class RecordedClaimEvidenceError(ValueError):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_RECORDED_CLAIM_EVIDENCE")


def _fail() -> NoReturn:
    raise RecordedClaimEvidenceError() from None


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail()
        result[key] = value
    return result


def _mapping(value: object, keys: tuple[str, ...]) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail()
    mapping = cast(dict[str, object], value)
    if tuple(mapping) != keys:
        _fail()
    return mapping


def _sequence(value: object) -> list[object]:
    if type(value) is not list:
        _fail()
    sequence = cast(list[object], value)
    if len(sequence) > _MAX_CAPACITY:
        _fail()
    return sequence


def _string(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _integer(value: object) -> int:
    if type(value) is not int or not 0 < value <= (1 << 53) - 1:
        _fail()
    return value


def _uuid(value: object) -> UUID:
    try:
        parsed = UUID(_string(value))
    except Exception:
        _fail()
    if parsed.int == 0 or str(parsed) != value:
        _fail()
    return parsed


def _sha(value: object) -> Sha256Digest:
    try:
        return Sha256Digest(_string(value))
    except Exception:
        _fail()


def _optional_sha(value: object) -> Sha256Digest | None:
    return None if value is None else _sha(value)


def _sha_list(value: object) -> tuple[Sha256Digest, ...]:
    values = tuple(_sha(item) for item in _sequence(value))
    if not values or len(values) != len(set(values)):
        _fail()
    return values


def _instant(value: object) -> AwareUtcDateTime:
    text = _string(value)
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        result = AwareUtcDateTime(parsed)
    except Exception:
        _fail()
    return result


def _enum(enum_type: type[Any], value: object) -> Any:
    try:
        result = enum_type(_string(value))
    except Exception:
        _fail()
    return result


def _id_list(value: object, id_type: type[Any]) -> tuple[Any, ...]:
    values = tuple(id_type(_uuid(item)) for item in _sequence(value))
    if len(values) != len(set(values)):
        _fail()
    return values


def _parse_claim(value: object) -> PolicyClaim:
    row = _mapping(
        value,
        (
            "claim_id",
            "article_version_id",
            "claim_text_sha256",
            "claim_type",
            "criticality",
            "affects_purchase_decision",
            "affects_ranking",
            "affects_price",
            "affects_safety",
            "affects_legal",
            "temporal_scope_required",
            "allowed_subject_identity_sha256s",
        ),
    )
    return PolicyClaim(
        claim_id=ClaimId(_uuid(row["claim_id"])),
        article_version_id=ArticleVersionId(_uuid(row["article_version_id"])),
        claim_text_sha256=_sha(row["claim_text_sha256"]),
        claim_type=_enum(PolicyClaimType, row["claim_type"]),
        criticality=_integer(row["criticality"]),
        affects_purchase_decision=_boolean(row["affects_purchase_decision"]),
        affects_ranking=_boolean(row["affects_ranking"]),
        affects_price=_boolean(row["affects_price"]),
        affects_safety=_boolean(row["affects_safety"]),
        affects_legal=_boolean(row["affects_legal"]),
        temporal_scope_required=_boolean(row["temporal_scope_required"]),
        allowed_subject_identity_sha256s=_sha_list(
            row["allowed_subject_identity_sha256s"]
        ),
    )


def _parse_proof(value: object) -> ClaimRequirementProof:
    row = _mapping(
        value,
        (
            "claim_id",
            "temporal_scope_sha256",
            "derivation_formula_sha256",
            "comparison_population_sha256",
            "recommendation_methodology_sha256",
            "experience_record_sha256",
            "experience_approved",
            "safety_compliance_review_sha256",
            "unknown_value_handling",
        ),
    )
    return ClaimRequirementProof(
        claim_id=ClaimId(_uuid(row["claim_id"])),
        temporal_scope_sha256=_optional_sha(row["temporal_scope_sha256"]),
        derivation_formula_sha256=_optional_sha(row["derivation_formula_sha256"]),
        comparison_population_sha256=_optional_sha(row["comparison_population_sha256"]),
        recommendation_methodology_sha256=_optional_sha(
            row["recommendation_methodology_sha256"]
        ),
        experience_record_sha256=_optional_sha(row["experience_record_sha256"]),
        experience_approved=_boolean(row["experience_approved"]),
        safety_compliance_review_sha256=_optional_sha(
            row["safety_compliance_review_sha256"]
        ),
        unknown_value_handling=_enum(
            UnknownValueHandling, row["unknown_value_handling"]
        ),
    )


def _parse_fact(value: object) -> EvidenceFact:
    row = _mapping(
        value,
        (
            "fact_id",
            "source_snapshot_id",
            "fact_sha256",
            "subject_identity_sha256",
        ),
    )
    return EvidenceFact(
        fact_id=FactId(_uuid(row["fact_id"])),
        source_snapshot_id=SourceSnapshotId(_uuid(row["source_snapshot_id"])),
        fact_sha256=_sha(row["fact_sha256"]),
        subject_identity_sha256=_sha(row["subject_identity_sha256"]),
    )


def _parse_link(value: object) -> EvidenceLink:
    row = _mapping(value, ("claim_id", "fact_id", "support_type"))
    return EvidenceLink(
        claim_id=ClaimId(_uuid(row["claim_id"])),
        fact_id=FactId(_uuid(row["fact_id"])),
        support_type=_enum(PolicyLinkSupportType, row["support_type"]),
    )


def _parse_source(value: object) -> EvidenceSource:
    row = _mapping(value, ("source_id", "tier", "origin", "active"))
    return EvidenceSource(
        source_id=SourceId(_uuid(row["source_id"])),
        tier=_enum(PolicySourceTier, row["tier"]),
        origin=_enum(EvidenceOrigin, row["origin"]),
        active=_boolean(row["active"]),
    )


def _parse_snapshot(value: object) -> EvidenceSnapshot:
    row = _mapping(
        value,
        (
            "source_snapshot_id",
            "source_id",
            "content_sha256",
            "validation_status",
            "acquired_at",
            "expires_at",
        ),
    )
    return EvidenceSnapshot(
        source_snapshot_id=SourceSnapshotId(_uuid(row["source_snapshot_id"])),
        source_id=SourceId(_uuid(row["source_id"])),
        content_sha256=_sha(row["content_sha256"]),
        validation_status=_enum(
            SourceSnapshotValidationStatus, row["validation_status"]
        ),
        acquired_at=_instant(row["acquired_at"]),
        expires_at=(None if row["expires_at"] is None else _instant(row["expires_at"])),
    )


def _parse_identity(value: object) -> EvidenceIdentityBinding:
    row = _mapping(
        value,
        (
            "fact_id",
            "status",
            "expected_subject_identity_sha256",
            "observed_subject_identity_sha256",
            "decision_sha256",
            "decided_at",
        ),
    )
    return EvidenceIdentityBinding(
        fact_id=FactId(_uuid(row["fact_id"])),
        status=_enum(IdentityStatus, row["status"]),
        expected_subject_identity_sha256=_sha(row["expected_subject_identity_sha256"]),
        observed_subject_identity_sha256=_sha(row["observed_subject_identity_sha256"]),
        decision_sha256=_sha(row["decision_sha256"]),
        decided_at=_instant(row["decided_at"]),
    )


def _parse_conflict(value: object) -> EvidenceConflict:
    row = _mapping(
        value,
        (
            "conflict_id",
            "fact_ids",
            "status",
            "resolution_decision_sha256",
            "reviewer_identity_sha256",
            "resolved_at",
        ),
    )
    return EvidenceConflict(
        conflict_id=ConflictId(_uuid(row["conflict_id"])),
        fact_ids=_id_list(row["fact_ids"], FactId),
        status=_enum(ConflictStatus, row["status"]),
        resolution_decision_sha256=_optional_sha(row["resolution_decision_sha256"]),
        reviewer_identity_sha256=_optional_sha(row["reviewer_identity_sha256"]),
        resolved_at=(
            None if row["resolved_at"] is None else _instant(row["resolved_at"])
        ),
    )


def _parse_attestation(value: object) -> EvidenceValidationAttestation:
    row = _mapping(
        value,
        (
            "kind",
            "owner_story_id",
            "contract_version",
            "contract_sha256",
            "origin",
            "subject_sha256",
            "input_sha256",
            "decision_sha256",
            "validated_at",
            "valid",
        ),
    )
    return EvidenceValidationAttestation(
        kind=_enum(ValidationAttestationKind, row["kind"]),
        owner_story_id=_string(row["owner_story_id"]),
        contract_version=_string(row["contract_version"]),
        contract_sha256=_sha(row["contract_sha256"]),
        origin=_enum(ValidationAttestationOrigin, row["origin"]),
        subject_sha256=_sha(row["subject_sha256"]),
        input_sha256=_sha(row["input_sha256"]),
        decision_sha256=_sha(row["decision_sha256"]),
        validated_at=_instant(row["validated_at"]),
        valid=_boolean(row["valid"]),
    )


def _parse_citation(value: object) -> EvidenceCitation:
    row = _mapping(
        value,
        (
            "citation_id",
            "claim_id",
            "fact_id",
            "support_type",
            "source_id",
            "source_snapshot_id",
        ),
    )
    return EvidenceCitation(
        citation_id=CitationId(_uuid(row["citation_id"])),
        claim_id=ClaimId(_uuid(row["claim_id"])),
        fact_id=FactId(_uuid(row["fact_id"])),
        support_type=_enum(PolicyLinkSupportType, row["support_type"]),
        source_id=SourceId(_uuid(row["source_id"])),
        source_snapshot_id=SourceSnapshotId(_uuid(row["source_snapshot_id"])),
    )


def load_recorded_claim_evidence_fixture(payload: bytes) -> ClaimEvidenceSnapshot:
    """Decode one closed generated synthetic fixture from caller-owned bytes."""

    if type(payload) is not bytes or not payload or len(payload) > _MAX_FIXTURE_BYTES:
        _fail()
    try:
        loaded = json.loads(payload, object_pairs_hook=_pairs)
    except Exception:
        _fail()
    root = _mapping(
        loaded,
        (
            "schema_version",
            "contract",
            "article",
            "approved_packet",
            "evaluated_at",
            "claims",
            "requirement_proofs",
            "facts",
            "links",
            "sources",
            "snapshots",
            "identities",
            "conflicts",
            "citations",
            "attestations",
        ),
    )
    if root["schema_version"] != 1 or type(root["schema_version"]) is not int:
        _fail()
    contract_row = _mapping(
        root["contract"],
        (
            "policy_document_id",
            "policy_version",
            "policy_sha256",
            "evaluator_version",
            "claim_set_profile",
        ),
    )
    contract = CoverageContractBinding(
        policy_document_id=_string(contract_row["policy_document_id"]),
        policy_version=_string(contract_row["policy_version"]),
        policy_sha256=_sha(contract_row["policy_sha256"]),
        evaluator_version=_string(contract_row["evaluator_version"]),
        claim_set_profile=_string(contract_row["claim_set_profile"]),
    )
    article_row = _mapping(
        root["article"],
        (
            "article_version_id",
            "article_body_sha256",
            "source_packet_version_id",
            "source_packet_content_sha256",
            "complete_claim_ids",
            "complete_claim_set_sha256",
        ),
    )
    article = ArticleEvidenceBinding(
        article_version_id=ArticleVersionId(_uuid(article_row["article_version_id"])),
        article_body_sha256=_sha(article_row["article_body_sha256"]),
        source_packet_version_id=SourcePacketVersionId(
            _uuid(article_row["source_packet_version_id"])
        ),
        source_packet_content_sha256=_sha(article_row["source_packet_content_sha256"]),
        complete_claim_ids=_id_list(article_row["complete_claim_ids"], ClaimId),
        complete_claim_set_sha256=_sha(article_row["complete_claim_set_sha256"]),
    )
    packet_row = _mapping(
        root["approved_packet"],
        (
            "source_packet_id",
            "source_packet_version_id",
            "version_no",
            "status",
            "content_sha256",
            "fact_ids",
            "approval_decision_sha256",
            "approved_at",
        ),
    )
    packet = ApprovedPacketBinding(
        source_packet_id=SourcePacketId(_uuid(packet_row["source_packet_id"])),
        source_packet_version_id=SourcePacketVersionId(
            _uuid(packet_row["source_packet_version_id"])
        ),
        version_no=_integer(packet_row["version_no"]),
        status=_enum(SourcePacketVersionStatus, packet_row["status"]),
        content_sha256=_sha(packet_row["content_sha256"]),
        fact_ids=_id_list(packet_row["fact_ids"], FactId),
        approval_decision_sha256=_sha(packet_row["approval_decision_sha256"]),
        approved_at=_instant(packet_row["approved_at"]),
    )
    try:
        result = ClaimEvidenceSnapshot(
            contract=contract,
            article=article,
            approved_packet=packet,
            evaluated_at=_instant(root["evaluated_at"]),
            claims=tuple(_parse_claim(item) for item in _sequence(root["claims"])),
            requirement_proofs=tuple(
                _parse_proof(item) for item in _sequence(root["requirement_proofs"])
            ),
            facts=tuple(_parse_fact(item) for item in _sequence(root["facts"])),
            links=tuple(_parse_link(item) for item in _sequence(root["links"])),
            sources=tuple(_parse_source(item) for item in _sequence(root["sources"])),
            snapshots=tuple(
                _parse_snapshot(item) for item in _sequence(root["snapshots"])
            ),
            identities=tuple(
                _parse_identity(item) for item in _sequence(root["identities"])
            ),
            conflicts=tuple(
                _parse_conflict(item) for item in _sequence(root["conflicts"])
            ),
            citations=tuple(
                _parse_citation(item) for item in _sequence(root["citations"])
            ),
            attestations=tuple(
                _parse_attestation(item) for item in _sequence(root["attestations"])
            ),
        )
    except RecordedClaimEvidenceError:
        raise
    except Exception:
        _fail()
    return result


def _validated_snapshot_report(
    snapshot: ClaimEvidenceSnapshot,
) -> ClaimEvidenceCoverageReport:
    try:
        report = evaluate_claim_evidence(snapshot)
        report.require_valid()
    except RecordedClaimEvidenceError:
        raise
    except Exception:
        _fail()
    return report


@final
class RecordedClaimEvidenceAdapter:
    """Process-local fixed snapshots plus metadata-only append receipts."""

    __slots__ = (
        "_capacity",
        "_environment",
        "_lock",
        "_report_anchors",
        "_snapshot_anchors",
        "_snapshots",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        capacity: int,
        snapshots: tuple[ClaimEvidenceSnapshot, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(capacity) is not int
            or not 0 < capacity <= _MAX_CAPACITY
            or type(snapshots) is not tuple
            or not snapshots
            or len(snapshots) > capacity
            or any(type(item) is not ClaimEvidenceSnapshot for item in snapshots)
        ):
            _fail()
        anchors: list[tuple[UUID, str]] = []
        try:
            for item in snapshots:
                report = _validated_snapshot_report(item)
                article_version_id = item.article.article_version_id
                evaluation_input_sha256 = report.evaluation_input_sha256
                if (
                    report.article_version_id != article_version_id
                    or evaluation_input_sha256 is None
                ):
                    _fail()
                anchors.append(
                    (
                        article_version_id.value,
                        evaluation_input_sha256.value,
                    )
                )
        except RecordedClaimEvidenceError:
            raise
        except Exception:
            _fail()
        if len(anchors) != len({article_id for article_id, _ in anchors}):
            _fail()
        self._environment = environment
        self._capacity = capacity
        self._snapshots = snapshots
        self._snapshot_anchors = tuple(anchors)
        self._report_anchors: tuple[tuple[str, bytes], ...] = ()
        self._lock = RLock()

    @property
    def environment(self) -> RuntimeEnvironment:
        return self._environment

    def get_snapshot(
        self,
        article_version_id: ArticleVersionId,
    ) -> ClaimEvidenceSnapshot | None:
        if type(article_version_id) is not ArticleVersionId:
            _fail()
        with self._lock:
            for snapshot, (anchored_id, anchored_input) in zip(
                self._snapshots,
                self._snapshot_anchors,
                strict=True,
            ):
                if anchored_id != article_version_id.value:
                    continue
                observed = _validated_snapshot_report(snapshot)
                if (
                    observed.article_version_id != article_version_id
                    or observed.evaluation_input_sha256 is None
                    or observed.evaluation_input_sha256.value != anchored_input
                ):
                    _fail()
                return snapshot
        return None

    def append_report(
        self,
        snapshot: ClaimEvidenceSnapshot,
        report: ClaimEvidenceCoverageReport,
    ) -> CoverageRecordReceipt:
        if (
            type(snapshot) is not ClaimEvidenceSnapshot
            or type(report) is not ClaimEvidenceCoverageReport
        ):
            _fail()
        try:
            article_version_id = snapshot.article.article_version_id
            report.require_valid()
        except Exception:
            _fail()
        with self._lock:
            stored: ClaimEvidenceSnapshot | None = None
            anchored_input: str | None = None
            for item, (anchored_id, candidate_input) in zip(
                self._snapshots,
                self._snapshot_anchors,
                strict=True,
            ):
                if anchored_id == article_version_id.value:
                    stored = item
                    anchored_input = candidate_input
                    break
            if stored is None or anchored_input is None:
                _fail()
            expected = _validated_snapshot_report(stored)
            observed = _validated_snapshot_report(snapshot)
            if (
                expected.evaluation_input_sha256 is None
                or observed.evaluation_input_sha256 is None
                or expected.evaluation_input_sha256.value != anchored_input
                or observed.evaluation_input_sha256.value != anchored_input
                or expected.canonical_bytes() != report.canonical_bytes()
                or observed.canonical_bytes() != report.canonical_bytes()
            ):
                _fail()
            report_sha256 = report.report_sha256.value
            report_bytes = report.canonical_bytes()
            for index, (current_sha256, current_bytes) in enumerate(
                self._report_anchors,
                start=1,
            ):
                if current_sha256 == report_sha256:
                    if current_bytes != report_bytes:
                        _fail()
                    receipt = CoverageRecordReceipt(
                        index,
                        Sha256Digest(current_sha256),
                    )
                    receipt.require_valid()
                    return receipt
            if len(self._report_anchors) >= self._capacity:
                _fail()
            self._report_anchors = (
                *self._report_anchors,
                (report_sha256, report_bytes),
            )
            receipt = CoverageRecordReceipt(
                len(self._report_anchors),
                Sha256Digest(report_sha256),
            )
            receipt.require_valid()
            return receipt

    def receipts(self) -> tuple[CoverageRecordReceipt, ...]:
        with self._lock:
            return tuple(
                CoverageRecordReceipt(index, Sha256Digest(report_sha256))
                for index, (report_sha256, _report_bytes) in enumerate(
                    self._report_anchors,
                    start=1,
                )
            )

    def __repr__(self) -> str:
        return "RecordedClaimEvidenceAdapter(<redacted-st0605>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded ST-0605 adapter serialization is not supported")


__all__ = [
    "RecordedClaimEvidenceAdapter",
    "RecordedClaimEvidenceError",
    "load_recorded_claim_evidence_fixture",
]
