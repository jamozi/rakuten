"""Bounded recorded-synthetic adapter for ST-0804 recommendation runtime V2."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
import hashlib
import json
import re
from threading import RLock
from typing import Any, NoReturn, SupportsIndex, cast, final
import unicodedata
from uuid import UUID

from raos.adapters.recorded_comparison_validation import (
    load_recorded_comparison_fixture,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.ids import CanonicalProductId
from raos.domain.editorial.comparison_validation_v2 import (
    ComparisonCellStatus,
    ComparisonRecordReceipt,
    ComparisonValidationEnvelopeV2,
    ComparisonValidationStatus,
    canonical_decimal,
    validate_comparison_v2,
)
from raos.domain.editorial.ids import ArticleId, ArticleVersionId, ComparisonAxisId
from raos.domain.editorial.recommendation_v2 import (
    ArticleRecommendationContextV2,
    ConflictState,
    DecisionContextId,
    DimensionAssessmentV2,
    HardConstraintState,
    MethodologyBindingV2,
    NormalizationBasis,
    RecommendationContractBinding,
    RecommendationDimensionV2,
    RecommendationEnvelopeV2,
    RecommendationRecordReceipt,
    RecommendationReportV2,
    RecommendationRuleBinding,
    StalenessState,
    assessment_set_sha256,
    comparison_receipt_sha256,
    decision_context_sha256,
    dimension_set_sha256,
    evaluate_recommendations_v2,
    prohibited_ranking_alias,
    recommendation_input_sha256,
)
from raos.domain.evidence.ids import FactId
from raos.domain.shared.persistence import Sha256Digest


_MAX_FIXTURE_BYTES = 4_194_304
_MAX_CAPACITY = 10_000
_MAX_PRODUCTS = 20
_MAX_AXES = 30
_MAX_ASSESSMENTS = _MAX_PRODUCTS * _MAX_AXES
_MAX_JSON_NODES = 50_000
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CODE = re.compile(r"[A-Z][A-Z0-9_.:-]{0,79}\Z", re.ASCII)
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z", re.ASCII)


class RecordedRecommendationError(ValueError):
    """Closed adapter failure without caller-controlled material."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_RECORDED_RECOMMENDATION")


class ProhibitedRecommendationInputError(ValueError):
    """Closed rejection of finance/affiliate ranking aliases."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("PROHIBITED_RECOMMENDATION_INPUT")


def _fail() -> NoReturn:
    raise RecordedRecommendationError() from None


def _reject_prohibited() -> NoReturn:
    raise ProhibitedRecommendationInputError() from None


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or not key or len(key) > 80 or key in result:
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
    maximum: int,
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


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _integer(
    value: object,
    *,
    minimum: int = 1,
    maximum: int = (1 << 53) - 1,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def _uuid(value: object) -> UUID:
    try:
        text = _string(value, maximum=36)
        parsed = UUID(text)
    except Exception:
        _fail()
    if parsed.int == 0 or str(parsed) != text:
        _fail()
    return parsed


def _sha(value: object) -> Sha256Digest:
    text = _string(value, maximum=64)
    if _SHA.fullmatch(text) is None:
        _fail()
    try:
        return Sha256Digest(text)
    except Exception:
        _fail()


def _code(value: object) -> str:
    text = _string(value, maximum=80)
    if _CODE.fullmatch(text) is None:
        _fail()
    if prohibited_ranking_alias(text):
        _reject_prohibited()
    return text


def _decimal(
    value: object,
    *,
    minimum: Decimal,
    maximum: Decimal,
) -> Decimal:
    rendered = _string(value, maximum=64)
    try:
        parsed = Decimal(rendered)
        if canonical_decimal(parsed) != rendered:
            _fail()
    except RecordedRecommendationError, ProhibitedRecommendationInputError:
        raise
    except Exception:
        _fail()
    if parsed < minimum or parsed > maximum:
        _fail()
    return parsed


def _enum(enum_type: type[Any], value: object) -> Any:
    try:
        return enum_type(_string(value, maximum=64))
    except Exception:
        _fail()


def _bounded_json_tree(
    value: object,
    *,
    depth: int = 0,
    nodes: list[int] | None = None,
) -> None:
    counter = [0] if nodes is None else nodes
    counter[0] += 1
    if depth > 32 or counter[0] > _MAX_JSON_NODES:
        _fail()
    if type(value) is dict:
        mapping = cast(dict[object, object], value)
        if len(mapping) > 10_000:
            _fail()
        for key, item in mapping.items():
            checked_key = _string(key, maximum=80)
            if prohibited_ranking_alias(checked_key):
                _reject_prohibited()
            _bounded_json_tree(item, depth=depth + 1, nodes=counter)
        return
    if type(value) is list:
        sequence = cast(list[object], value)
        if len(sequence) > 10_000:
            _fail()
        for item in sequence:
            _bounded_json_tree(item, depth=depth + 1, nodes=counter)
        return
    if type(value) is str:
        checked_value = _string(value, maximum=4_096)
        if prohibited_ranking_alias(checked_value):
            _reject_prohibited()
        return
    if type(value) is float:
        _fail()
    if type(value) is int and not -(1 << 53) + 1 <= value <= (1 << 53) - 1:
        _fail()
    if value is not None and type(value) not in {bool, int}:
        _fail()


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


def _contract(value: object) -> RecommendationContractBinding:
    row = _mapping(
        value,
        (
            "contract_id",
            "contract_version",
            "evaluator_version",
            "methodology_source_sha256",
            "st0803_contract_sha256",
            "st0803_domain_sha256",
            "st0803_recorded_fixture_sha256",
            "st0803_runtime_manifest_sha256",
        ),
    )
    result = RecommendationContractBinding(
        contract_id=_code(row["contract_id"]),
        contract_version=_string(row["contract_version"], maximum=20),
        evaluator_version=_code(row["evaluator_version"]),
        methodology_source_sha256=_sha(row["methodology_source_sha256"]),
        st0803_contract_sha256=_sha(row["st0803_contract_sha256"]),
        st0803_domain_sha256=_sha(row["st0803_domain_sha256"]),
        st0803_recorded_fixture_sha256=_sha(row["st0803_recorded_fixture_sha256"]),
        st0803_runtime_manifest_sha256=_sha(row["st0803_runtime_manifest_sha256"]),
    )
    if result != RecommendationContractBinding.current():
        _fail()
    return result


def _rule(value: object) -> RecommendationRuleBinding:
    row = _mapping(value, ("rule_id", "version", "source_sha256"))
    version = _string(row["version"], maximum=20)
    if _VERSION.fullmatch(version) is None:
        _fail()
    return RecommendationRuleBinding(
        rule_id=_code(row["rule_id"]),
        version=version,
        source_sha256=_sha(row["source_sha256"]),
    )


def _methodology(value: object) -> MethodologyBindingV2:
    row = _mapping(
        value,
        (
            "methodology_id",
            "methodology_version",
            "source_sha256",
            "hard_constraint_rule",
            "weighting_rule",
            "normalization_rule",
            "coverage_rule",
            "conflict_penalty_rule",
            "staleness_penalty_rule",
            "tie_rule",
        ),
    )
    result = MethodologyBindingV2(
        methodology_id=_code(row["methodology_id"]),
        methodology_version=_string(row["methodology_version"], maximum=20),
        source_sha256=_sha(row["source_sha256"]),
        hard_constraint_rule=_rule(row["hard_constraint_rule"]),
        weighting_rule=_rule(row["weighting_rule"]),
        normalization_rule=_rule(row["normalization_rule"]),
        coverage_rule=_rule(row["coverage_rule"]),
        conflict_penalty_rule=_rule(row["conflict_penalty_rule"]),
        staleness_penalty_rule=_rule(row["staleness_penalty_rule"]),
        tie_rule=_rule(row["tie_rule"]),
    )
    if result != MethodologyBindingV2.current():
        _fail()
    return result


def _context(value: object) -> ArticleRecommendationContextV2:
    row = _mapping(
        value,
        (
            "article_id",
            "article_version_id",
            "article_binding_sha256",
            "decision_context_id",
            "decision_context_version_no",
            "target_reader_code",
            "use_case_code",
            "budget_context_code",
            "context_source_sha256",
            "binding_sha256",
        ),
    )
    result = ArticleRecommendationContextV2(
        article_id=ArticleId(_uuid(row["article_id"])),
        article_version_id=ArticleVersionId(_uuid(row["article_version_id"])),
        article_binding_sha256=_sha(row["article_binding_sha256"]),
        decision_context_id=DecisionContextId(_uuid(row["decision_context_id"])),
        decision_context_version_no=_integer(row["decision_context_version_no"]),
        target_reader_code=_code(row["target_reader_code"]),
        use_case_code=_code(row["use_case_code"]),
        budget_context_code=_code(row["budget_context_code"]),
        context_source_sha256=_sha(row["context_source_sha256"]),
        binding_sha256=_sha(row["binding_sha256"]),
    )
    if decision_context_sha256(result) != result.binding_sha256:
        _fail()
    return result


def _dimension(value: object) -> RecommendationDimensionV2:
    row = _mapping(
        value,
        (
            "axis_id",
            "axis_definition_sha256",
            "weight",
            "critical",
            "hard_constraint",
            "normalization_basis",
            "normalization_rule",
        ),
    )
    return RecommendationDimensionV2(
        axis_id=ComparisonAxisId(_uuid(row["axis_id"])),
        axis_definition_sha256=_sha(row["axis_definition_sha256"]),
        weight=_decimal(row["weight"], minimum=Decimal("0.0001"), maximum=Decimal("1")),
        critical=_boolean(row["critical"]),
        hard_constraint=_boolean(row["hard_constraint"]),
        normalization_basis=cast(
            NormalizationBasis,
            _enum(NormalizationBasis, row["normalization_basis"]),
        ),
        normalization_rule=_rule(row["normalization_rule"]),
    )


def _assessment(value: object) -> DimensionAssessmentV2:
    row = _mapping(
        value,
        (
            "product_id",
            "axis_id",
            "cell_status",
            "fact_ids",
            "normalization_basis",
            "normalized_score",
            "hard_constraint_state",
            "conflict_state",
            "conflict_penalty",
            "staleness_state",
            "staleness_penalty",
            "normalization_input_sha256",
            "normalization_decision_sha256",
        ),
    )
    basis = cast(
        NormalizationBasis,
        _enum(NormalizationBasis, row["normalization_basis"]),
    )
    raw_score = row["normalized_score"]
    return DimensionAssessmentV2(
        product_id=CanonicalProductId(_uuid(row["product_id"])),
        axis_id=ComparisonAxisId(_uuid(row["axis_id"])),
        cell_status=cast(
            ComparisonCellStatus,
            _enum(ComparisonCellStatus, row["cell_status"]),
        ),
        fact_ids=tuple(
            FactId(_uuid(item)) for item in _sequence(row["fact_ids"], maximum=2)
        ),
        normalization_basis=basis,
        normalized_score=(
            None
            if raw_score is None
            else _decimal(raw_score, minimum=Decimal("0"), maximum=Decimal("1"))
        ),
        hard_constraint_state=cast(
            HardConstraintState,
            _enum(HardConstraintState, row["hard_constraint_state"]),
        ),
        conflict_state=cast(
            ConflictState,
            _enum(ConflictState, row["conflict_state"]),
        ),
        conflict_penalty=_decimal(
            row["conflict_penalty"], minimum=Decimal("0"), maximum=Decimal("20")
        ),
        staleness_state=cast(
            StalenessState,
            _enum(StalenessState, row["staleness_state"]),
        ),
        staleness_penalty=_decimal(
            row["staleness_penalty"], minimum=Decimal("0"), maximum=Decimal("20")
        ),
        normalization_input_sha256=_sha(row["normalization_input_sha256"]),
        normalization_decision_sha256=_sha(row["normalization_decision_sha256"]),
    )


def _comparison_request(value: object) -> ComparisonValidationEnvelopeV2:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("ascii")
        return load_recorded_comparison_fixture(payload)
    except RecordedRecommendationError, ProhibitedRecommendationInputError:
        raise
    except Exception:
        _fail()


def load_recorded_recommendation_fixture(payload: bytes) -> RecommendationEnvelopeV2:
    """Decode one closed, generated ST-0804 fixture from caller-owned bytes."""

    if type(payload) is not bytes or not payload or len(payload) > _MAX_FIXTURE_BYTES:
        _fail()
    try:
        loaded = json.loads(payload, object_pairs_hook=_pairs)
    except RecordedRecommendationError, ProhibitedRecommendationInputError:
        raise
    except Exception:
        _fail()
    _bounded_json_tree(loaded)
    root = _mapping(
        loaded,
        (
            "schema_version",
            "local_status",
            "contract",
            "comparison_request",
            "comparison_report",
            "comparison_record_receipt",
            "context",
            "methodology",
            "dimensions",
            "assessments",
            "declared_hashes",
        ),
    )
    if type(root["schema_version"]) is not int or root["schema_version"] != 2:
        _fail()
    if root["local_status"] != "LOCAL_IMPLEMENTATION_COMPLETE":
        _fail()
    try:
        comparison = _comparison_request(root["comparison_request"])
        comparison_report = validate_comparison_v2(comparison)
        comparison_report.require_valid()
        if (
            comparison_report.status is not ComparisonValidationStatus.LOCAL_VALIDATED
            or comparison_report.findings
            or _canonical_json_bytes(root["comparison_report"])
            != comparison_report.canonical_bytes()
        ):
            _fail()
        receipt_row = _mapping(
            root["comparison_record_receipt"],
            ("sequence", "report_sha256", "publication_authorized"),
        )
        comparison_receipt = ComparisonRecordReceipt(
            sequence=_integer(receipt_row["sequence"]),
            report_sha256=_sha(receipt_row["report_sha256"]),
            publication_authorized=_boolean(receipt_row["publication_authorized"]),
        )
        comparison_receipt.require_valid()
        if comparison_receipt.report_sha256 != comparison_report.report_sha256:
            _fail()
        dimensions = tuple(
            _dimension(item)
            for item in _sequence(root["dimensions"], minimum=1, maximum=_MAX_AXES)
        )
        assessments = tuple(
            _assessment(item)
            for item in _sequence(
                root["assessments"], minimum=1, maximum=_MAX_ASSESSMENTS
            )
        )
        hashes = _mapping(
            root["declared_hashes"],
            (
                "comparison_request_sha256",
                "comparison_report_sha256",
                "comparison_receipt_sha256",
                "decision_context_sha256",
                "dimension_set_sha256",
                "assessment_set_sha256",
                "recommendation_input_sha256",
            ),
        )
        envelope = RecommendationEnvelopeV2(
            contract=_contract(root["contract"]),
            comparison=comparison,
            comparison_report=comparison_report,
            comparison_receipt=comparison_receipt,
            context=_context(root["context"]),
            methodology=_methodology(root["methodology"]),
            dimensions=dimensions,
            assessments=assessments,
            dimension_set_sha256=_sha(hashes["dimension_set_sha256"]),
            assessment_set_sha256=_sha(hashes["assessment_set_sha256"]),
            recommendation_input_sha256=_sha(hashes["recommendation_input_sha256"]),
        )
        if (
            _sha(hashes["comparison_request_sha256"])
            != comparison.comparison.evaluation_input_sha256
            or _sha(hashes["comparison_report_sha256"])
            != comparison_report.report_sha256
            or _sha(hashes["comparison_receipt_sha256"])
            != comparison_receipt_sha256(comparison_receipt)
            or _sha(hashes["decision_context_sha256"])
            != envelope.context.binding_sha256
            or dimension_set_sha256(dimensions) != envelope.dimension_set_sha256
            or assessment_set_sha256(assessments) != envelope.assessment_set_sha256
            or recommendation_input_sha256(envelope)
            != envelope.recommendation_input_sha256
        ):
            _fail()
        report = evaluate_recommendations_v2(envelope)
        report.require_valid()
        if not report.locally_calculated:
            _fail()
        return envelope
    except RecordedRecommendationError, ProhibitedRecommendationInputError:
        raise
    except Exception:
        _fail()


def _validated_report(envelope: RecommendationEnvelopeV2) -> RecommendationReportV2:
    try:
        report = evaluate_recommendations_v2(envelope)
        report.require_valid()
        return report
    except RecordedRecommendationError, ProhibitedRecommendationInputError:
        raise
    except Exception:
        _fail()


@final
class RecordedRecommendationAdapter:
    """Fixed fixture bytes plus metadata-only idempotent report receipts."""

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
        capacity: int,
        snapshot_bytes: tuple[bytes, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(capacity) is not int
            or not 0 < capacity <= _MAX_CAPACITY
            or type(snapshot_bytes) is not tuple
            or not snapshot_bytes
            or len(snapshot_bytes) > capacity
            or any(type(item) is not bytes for item in snapshot_bytes)
        ):
            _fail()
        anchors: list[tuple[UUID, str, str]] = []
        normalized: list[bytes] = []
        try:
            for payload in snapshot_bytes:
                owned = bytes(payload)
                envelope = load_recorded_recommendation_fixture(owned)
                report = _validated_report(envelope)
                if not report.locally_calculated:
                    _fail()
                anchors.append(
                    (
                        envelope.context.article_version_id.value,
                        envelope.recommendation_input_sha256.value,
                        hashlib.sha256(owned).hexdigest(),
                    )
                )
                normalized.append(owned)
        except RecordedRecommendationError, ProhibitedRecommendationInputError:
            raise
        except Exception:
            _fail()
        if len(anchors) != len({item[0] for item in anchors}):
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
        self,
        article_version_id: ArticleVersionId,
    ) -> RecommendationEnvelopeV2 | None:
        if type(article_version_id) is not ArticleVersionId:
            _fail()
        with self._lock:
            for payload, (anchored_id, anchored_input, anchored_payload) in zip(
                self._snapshot_bytes,
                self._snapshot_anchors,
                strict=True,
            ):
                if anchored_id != article_version_id.value:
                    continue
                if hashlib.sha256(payload).hexdigest() != anchored_payload:
                    _fail()
                envelope = load_recorded_recommendation_fixture(bytes(payload))
                if (
                    envelope.context.article_version_id != article_version_id
                    or envelope.recommendation_input_sha256.value != anchored_input
                ):
                    _fail()
                return envelope
        return None

    def append_report(
        self,
        snapshot: RecommendationEnvelopeV2,
        report: RecommendationReportV2,
    ) -> RecommendationRecordReceipt:
        if (
            type(snapshot) is not RecommendationEnvelopeV2
            or type(report) is not RecommendationReportV2
        ):
            _fail()
        try:
            article_version_id = snapshot.context.article_version_id
            report.require_valid()
        except Exception:
            _fail()
        with self._lock:
            stored_payload: bytes | None = None
            anchored_input: str | None = None
            for payload, (anchored_id, candidate_input, anchored_payload) in zip(
                self._snapshot_bytes,
                self._snapshot_anchors,
                strict=True,
            ):
                if anchored_id == article_version_id.value:
                    if hashlib.sha256(payload).hexdigest() != anchored_payload:
                        _fail()
                    stored_payload = payload
                    anchored_input = candidate_input
                    break
            if stored_payload is None or anchored_input is None:
                _fail()
            stored = load_recorded_recommendation_fixture(bytes(stored_payload))
            expected = _validated_report(stored)
            observed = _validated_report(snapshot)
            if (
                stored.recommendation_input_sha256.value != anchored_input
                or snapshot.recommendation_input_sha256.value != anchored_input
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
                    receipt = RecommendationRecordReceipt(
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
            receipt = RecommendationRecordReceipt(
                len(self._report_anchors),
                Sha256Digest(report_sha256),
            )
            receipt.require_valid()
            return receipt

    def receipts(self) -> tuple[RecommendationRecordReceipt, ...]:
        with self._lock:
            return tuple(
                RecommendationRecordReceipt(index, Sha256Digest(report_sha256))
                for index, (report_sha256, _report_bytes) in enumerate(
                    self._report_anchors,
                    start=1,
                )
            )

    def __repr__(self) -> str:
        return "RecordedRecommendationAdapter(<redacted-st0804-v2>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded ST-0804 V2 adapter serialization is not supported")


__all__ = [
    "ProhibitedRecommendationInputError",
    "RecordedRecommendationAdapter",
    "RecordedRecommendationError",
    "load_recorded_recommendation_fixture",
]
