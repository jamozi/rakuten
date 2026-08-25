"""Bounded recorded-synthetic adapter for the ST-0803 V2 runtime."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from threading import RLock
from typing import Any, NoReturn, SupportsIndex, cast, final
import unicodedata
from uuid import UUID

from raos.adapters.recorded_claim_evidence import (
    load_recorded_claim_evidence_fixture,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.ids import CanonicalProductId
from raos.domain.editorial.comparison_validation_v2 import (
    ArticleComparisonBinding,
    AxisCatalogId,
    CandidateUniverse,
    CandidateUniverseId,
    ComparisonAxisCatalog,
    ComparisonAxisDataType,
    ComparisonAxisDefinition,
    ComparisonCell,
    ComparisonCellStatus,
    ComparisonContractBinding,
    ComparisonFactBinding,
    ComparisonProduct,
    ComparisonRecordReceipt,
    ComparisonSnapshotV2,
    ComparisonValidationEnvelopeV2,
    ComparisonValidationReportV2,
    ComparisonValidationStatus,
    TypedComparisonValue,
    canonical_decimal,
    validate_comparison_v2,
)
from raos.domain.editorial.ids import ArticleId, ArticleVersionId, ComparisonAxisId
from raos.domain.evidence.ids import FactId, SourcePacketVersionId
from raos.domain.shared.persistence import AwareUtcDateTime, Sha256Digest


_MAX_FIXTURE_BYTES = 2_097_152
_MAX_CAPACITY = 10_000
_MAX_PRODUCTS = 20
_MAX_AXES = 30
_MAX_FACTS = 1_200
_MAX_CELLS = 600
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z", re.ASCII)
_UNIT_CODE = re.compile(r"[A-Z][A-Z0-9_.:-]{0,63}\Z", re.ASCII)


class RecordedComparisonValidationError(ValueError):
    """Closed adapter failure without caller-controlled text."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_RECORDED_COMPARISON_VALIDATION")


def _fail() -> NoReturn:
    raise RecordedComparisonValidationError() from None


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or len(key) > 80 or key in result:
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


def _sequence(value: object, *, maximum: int) -> list[object]:
    if type(value) is not list:
        _fail()
    sequence = cast(list[object], value)
    if len(sequence) > maximum:
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


def _integer(value: object, *, minimum: int = 1, maximum: int = (1 << 53) - 1) -> int:
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


def _instant(value: object) -> AwareUtcDateTime:
    text = _string(value, maximum=20)
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
            _fail()
        return AwareUtcDateTime(parsed)
    except RecordedComparisonValidationError:
        raise
    except Exception:
        _fail()


def _date(value: object) -> date:
    text = _string(value, maximum=10)
    try:
        parsed = date.fromisoformat(text)
    except Exception:
        _fail()
    if parsed.isoformat() != text:
        _fail()
    return parsed


def _enum(enum_type: type[Any], value: object) -> Any:
    try:
        return enum_type(_string(value, maximum=64))
    except Exception:
        _fail()


def _optional_code(value: object, *, unit: bool = False) -> str | None:
    if value is None:
        return None
    result = _string(value, maximum=64)
    pattern = _UNIT_CODE if unit else _CODE
    if pattern.fullmatch(result) is None:
        _fail()
    return result


def _bounded_json_tree(value: object, *, depth: int = 0) -> None:
    if depth > 32:
        _fail()
    if type(value) is dict:
        mapping = cast(dict[object, object], value)
        if len(mapping) > 10_000:
            _fail()
        for key, item in mapping.items():
            _string(key, maximum=80)
            _bounded_json_tree(item, depth=depth + 1)
        return
    if type(value) is list:
        sequence = cast(list[object], value)
        if len(sequence) > 10_000:
            _fail()
        for item in sequence:
            _bounded_json_tree(item, depth=depth + 1)
        return
    if type(value) is str:
        _string(value, maximum=4_096)
        return
    if type(value) is float:
        _fail()
    if type(value) is int and not -(1 << 53) + 1 <= value <= (1 << 53) - 1:
        _fail()
    if value is not None and type(value) not in {bool, int}:
        _fail()


def _typed_value(value: object) -> TypedComparisonValue:
    row = _mapping(value, ("data_type", "value"))
    data_type = cast(
        ComparisonAxisDataType,
        _enum(ComparisonAxisDataType, row["data_type"]),
    )
    raw = row["value"]
    try:
        if data_type is ComparisonAxisDataType.TEXT:
            return TypedComparisonValue(
                data_type=data_type,
                text_value=_string(raw, maximum=512),
            )
        if data_type is ComparisonAxisDataType.DECIMAL:
            rendered = _string(raw, maximum=32)
            parsed = Decimal(rendered)
            if canonical_decimal(parsed) != rendered:
                _fail()
            return TypedComparisonValue(data_type=data_type, decimal_value=parsed)
        if data_type is ComparisonAxisDataType.BOOLEAN:
            return TypedComparisonValue(
                data_type=data_type,
                boolean_value=_boolean(raw),
            )
        if data_type is ComparisonAxisDataType.DATE:
            return TypedComparisonValue(data_type=data_type, date_value=_date(raw))
        code = _string(raw, maximum=64)
        if _CODE.fullmatch(code) is None:
            _fail()
        return TypedComparisonValue(data_type=data_type, code_value=code)
    except RecordedComparisonValidationError:
        raise
    except Exception:
        _fail()


def _contract(value: object) -> ComparisonContractBinding:
    row = _mapping(
        value,
        (
            "contract_id",
            "contract_version",
            "evaluator_version",
            "comparison_schema_sha256",
            "identity_contract_sha256",
            "claim_evidence_contract_sha256",
            "article_lifecycle_source_sha256",
        ),
    )
    result = ComparisonContractBinding(
        contract_id=_string(row["contract_id"], maximum=80),
        contract_version=_string(row["contract_version"], maximum=20),
        evaluator_version=_string(row["evaluator_version"], maximum=80),
        comparison_schema_sha256=_sha(row["comparison_schema_sha256"]),
        identity_contract_sha256=_sha(row["identity_contract_sha256"]),
        claim_evidence_contract_sha256=_sha(row["claim_evidence_contract_sha256"]),
        article_lifecycle_source_sha256=_sha(row["article_lifecycle_source_sha256"]),
    )
    if result != ComparisonContractBinding.current():
        _fail()
    return result


def _article(value: object) -> ArticleComparisonBinding:
    row = _mapping(
        value,
        (
            "article_id",
            "article_version_id",
            "article_version_no",
            "article_body_sha256",
            "source_packet_version_id",
            "source_packet_content_sha256",
            "complete_claim_set_sha256",
            "binding_sha256",
        ),
    )
    return ArticleComparisonBinding(
        article_id=ArticleId(_uuid(row["article_id"])),
        article_version_id=ArticleVersionId(_uuid(row["article_version_id"])),
        article_version_no=_integer(row["article_version_no"]),
        article_body_sha256=_sha(row["article_body_sha256"]),
        source_packet_version_id=SourcePacketVersionId(
            _uuid(row["source_packet_version_id"])
        ),
        source_packet_content_sha256=_sha(row["source_packet_content_sha256"]),
        complete_claim_set_sha256=_sha(row["complete_claim_set_sha256"]),
        binding_sha256=_sha(row["binding_sha256"]),
    )


def _product(value: object) -> ComparisonProduct:
    row = _mapping(
        value,
        (
            "product_id",
            "variant_identity_sha256",
            "subject_identity_sha256",
            "inclusion_reason_code",
        ),
    )
    return ComparisonProduct(
        product_id=CanonicalProductId(_uuid(row["product_id"])),
        variant_identity_sha256=_sha(row["variant_identity_sha256"]),
        subject_identity_sha256=_sha(row["subject_identity_sha256"]),
        inclusion_reason_code=cast(str, _optional_code(row["inclusion_reason_code"])),
    )


def _candidate_universe(value: object) -> CandidateUniverse:
    row = _mapping(
        value,
        (
            "universe_id",
            "version_no",
            "products",
            "candidate_universe_sha256",
        ),
    )
    return CandidateUniverse(
        universe_id=CandidateUniverseId(_uuid(row["universe_id"])),
        version_no=_integer(row["version_no"]),
        products=tuple(
            _product(item) for item in _sequence(row["products"], maximum=_MAX_PRODUCTS)
        ),
        candidate_universe_sha256=_sha(row["candidate_universe_sha256"]),
    )


def _axis(value: object) -> ComparisonAxisDefinition:
    row = _mapping(
        value,
        (
            "axis_id",
            "axis_code",
            "label",
            "description",
            "data_type",
            "unit_family_code",
            "unit_code",
            "position",
            "required",
        ),
    )
    return ComparisonAxisDefinition(
        axis_id=ComparisonAxisId(_uuid(row["axis_id"])),
        axis_code=cast(str, _optional_code(row["axis_code"])),
        label=_string(row["label"], maximum=120),
        description=_string(row["description"], maximum=500),
        data_type=cast(
            ComparisonAxisDataType,
            _enum(ComparisonAxisDataType, row["data_type"]),
        ),
        unit_family_code=_optional_code(row["unit_family_code"], unit=True),
        unit_code=_optional_code(row["unit_code"], unit=True),
        position=_integer(row["position"], minimum=0, maximum=_MAX_AXES - 1),
        required=_boolean(row["required"]),
    )


def _axis_catalog(value: object) -> ComparisonAxisCatalog:
    row = _mapping(
        value,
        (
            "catalog_id",
            "version_no",
            "source_sha256",
            "axes",
            "axis_catalog_sha256",
        ),
    )
    return ComparisonAxisCatalog(
        catalog_id=AxisCatalogId(_uuid(row["catalog_id"])),
        version_no=_integer(row["version_no"]),
        source_sha256=_sha(row["source_sha256"]),
        axes=tuple(_axis(item) for item in _sequence(row["axes"], maximum=_MAX_AXES)),
        axis_catalog_sha256=_sha(row["axis_catalog_sha256"]),
    )


def _fact(value: object) -> ComparisonFactBinding:
    row = _mapping(
        value,
        (
            "fact_id",
            "fact_sha256",
            "product_id",
            "variant_identity_sha256",
            "subject_identity_sha256",
            "axis_id",
            "value",
            "unit_code",
            "observed_at",
            "valid_from",
            "valid_until",
        ),
    )
    return ComparisonFactBinding(
        fact_id=FactId(_uuid(row["fact_id"])),
        fact_sha256=_sha(row["fact_sha256"]),
        product_id=CanonicalProductId(_uuid(row["product_id"])),
        variant_identity_sha256=_sha(row["variant_identity_sha256"]),
        subject_identity_sha256=_sha(row["subject_identity_sha256"]),
        axis_id=ComparisonAxisId(_uuid(row["axis_id"])),
        value=_typed_value(row["value"]),
        unit_code=_optional_code(row["unit_code"], unit=True),
        observed_at=_instant(row["observed_at"]),
        valid_from=_instant(row["valid_from"]),
        valid_until=_instant(row["valid_until"]),
    )


def _cell(value: object) -> ComparisonCell:
    row = _mapping(
        value,
        (
            "product_id",
            "axis_id",
            "status",
            "value",
            "unit_code",
            "fact_ids",
            "reason_code",
            "imputed",
        ),
    )
    return ComparisonCell(
        product_id=CanonicalProductId(_uuid(row["product_id"])),
        axis_id=ComparisonAxisId(_uuid(row["axis_id"])),
        status=cast(
            ComparisonCellStatus,
            _enum(ComparisonCellStatus, row["status"]),
        ),
        value=None if row["value"] is None else _typed_value(row["value"]),
        unit_code=_optional_code(row["unit_code"], unit=True),
        fact_ids=tuple(
            FactId(_uuid(item)) for item in _sequence(row["fact_ids"], maximum=2)
        ),
        reason_code=_optional_code(row["reason_code"]),
        imputed=_boolean(row["imputed"]),
    )


def _comparison(value: object) -> ComparisonSnapshotV2:
    row = _mapping(
        value,
        (
            "contract",
            "article",
            "evaluated_at",
            "candidate_universe",
            "axis_catalog",
            "facts",
            "cells",
            "show_unknown_values",
            "fact_set_sha256",
            "temporal_scope_sha256",
            "evaluation_input_sha256",
        ),
    )
    return ComparisonSnapshotV2(
        contract=_contract(row["contract"]),
        article=_article(row["article"]),
        evaluated_at=_instant(row["evaluated_at"]),
        candidate_universe=_candidate_universe(row["candidate_universe"]),
        axis_catalog=_axis_catalog(row["axis_catalog"]),
        facts=tuple(
            _fact(item) for item in _sequence(row["facts"], maximum=_MAX_FACTS)
        ),
        cells=tuple(
            _cell(item) for item in _sequence(row["cells"], maximum=_MAX_CELLS)
        ),
        show_unknown_values=_boolean(row["show_unknown_values"]),
        fact_set_sha256=_sha(row["fact_set_sha256"]),
        temporal_scope_sha256=_sha(row["temporal_scope_sha256"]),
        evaluation_input_sha256=_sha(row["evaluation_input_sha256"]),
    )


def load_recorded_comparison_fixture(
    payload: bytes,
) -> ComparisonValidationEnvelopeV2:
    """Decode one closed generated fixture from caller-owned bytes."""

    if type(payload) is not bytes or not payload or len(payload) > _MAX_FIXTURE_BYTES:
        _fail()
    try:
        loaded = json.loads(payload, object_pairs_hook=_pairs)
    except Exception:
        _fail()
    root = _mapping(loaded, ("schema_version", "comparison", "claim_evidence"))
    if type(root["schema_version"]) is not int or root["schema_version"] != 2:
        _fail()
    claim_evidence = root["claim_evidence"]
    _bounded_json_tree(claim_evidence)
    try:
        claim_payload = json.dumps(
            claim_evidence,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("ascii")
        result = ComparisonValidationEnvelopeV2(
            comparison=_comparison(root["comparison"]),
            claim_evidence=load_recorded_claim_evidence_fixture(claim_payload),
        )
    except RecordedComparisonValidationError:
        raise
    except Exception:
        _fail()
    return result


def _validated_report(
    envelope: ComparisonValidationEnvelopeV2,
) -> ComparisonValidationReportV2:
    try:
        report = validate_comparison_v2(envelope)
        report.require_valid()
        return report
    except RecordedComparisonValidationError:
        raise
    except Exception:
        _fail()


@final
class RecordedComparisonValidationAdapter:
    """Fixed recorded bytes plus metadata-only idempotent report receipts."""

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
                envelope = load_recorded_comparison_fixture(owned)
                report = _validated_report(envelope)
                if (
                    report.status is not ComparisonValidationStatus.LOCAL_VALIDATED
                    or report.findings
                    or report.evaluation_input_sha256 is None
                ):
                    _fail()
                anchors.append(
                    (
                        envelope.comparison.article.article_version_id.value,
                        report.evaluation_input_sha256.value,
                        hashlib.sha256(owned).hexdigest(),
                    )
                )
                normalized.append(owned)
        except RecordedComparisonValidationError:
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
    ) -> ComparisonValidationEnvelopeV2 | None:
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
                envelope = load_recorded_comparison_fixture(bytes(payload))
                observed = _validated_report(envelope)
                if (
                    envelope.comparison.article.article_version_id != article_version_id
                    or observed.evaluation_input_sha256 is None
                    or observed.evaluation_input_sha256.value != anchored_input
                ):
                    _fail()
                return envelope
        return None

    def append_report(
        self,
        snapshot: ComparisonValidationEnvelopeV2,
        report: ComparisonValidationReportV2,
    ) -> ComparisonRecordReceipt:
        if (
            type(snapshot) is not ComparisonValidationEnvelopeV2
            or type(report) is not ComparisonValidationReportV2
        ):
            _fail()
        try:
            article_version_id = snapshot.comparison.article.article_version_id
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
            stored = load_recorded_comparison_fixture(bytes(stored_payload))
            expected = _validated_report(stored)
            observed = _validated_report(snapshot)
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
                    receipt = ComparisonRecordReceipt(
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
            receipt = ComparisonRecordReceipt(
                len(self._report_anchors),
                Sha256Digest(report_sha256),
            )
            receipt.require_valid()
            return receipt

    def receipts(self) -> tuple[ComparisonRecordReceipt, ...]:
        with self._lock:
            return tuple(
                ComparisonRecordReceipt(index, Sha256Digest(report_sha256))
                for index, (report_sha256, _report_bytes) in enumerate(
                    self._report_anchors,
                    start=1,
                )
            )

    def __repr__(self) -> str:
        return "RecordedComparisonValidationAdapter(<redacted-st0803-v2>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded ST-0803 V2 adapter serialization is not supported")


__all__ = [
    "RecordedComparisonValidationAdapter",
    "RecordedComparisonValidationError",
    "load_recorded_comparison_fixture",
]
