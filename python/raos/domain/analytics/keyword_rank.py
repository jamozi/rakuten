"""Provider-neutral values for the disabled ST-1206 rank import extension.

Only normalized keyword UUID observations cross this domain boundary.  Raw query
text, URLs, provider SDK values, credentials, persistence, and scraping are not
represented by these types.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex
from uuid import UUID


_REDACTED: Final = "<redacted-keyword-rank>"
_LOCALE = re.compile(r"[a-z]{2,3}(?:-[A-Z]{2})?\Z", re.ASCII)
_PROVIDER_CODE = re.compile(r"[A-Z][A-Z0-9_]{2,63}\Z", re.ASCII)
_RECORDING_ID = re.compile(r"[a-z0-9][a-z0-9_-]{1,63}\Z", re.ASCII)
_SAFE_UNIT = re.compile(r"[a-z0-9][a-z0-9_./-]{0,31}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)

KEYWORD_RANK_CONTRACT_VERSION: Final = "1.0.0"
KEYWORD_RANK_PARSER_VERSION: Final = "st1206-recorded-manual-csv.v1"
SYNTHETIC_FIXTURE_PROFILE: Final = "RAOS_ST1206_SYNTHETIC_V1"
SYNTHETIC_PROVIDER_CODE: Final = "RAOS_ST1206_SYNTHETIC"
MAX_KEYWORD_RANK_SOURCE_BYTES: Final = 1_048_576
MAX_KEYWORD_RANK_ROWS: Final = 10_000
KEYWORD_RANK_COLUMN_COUNT: Final = 10


class KeywordRankScope(str, Enum):
    """Closed feature states; there is deliberately no live-enabled state."""

    DISABLED = "DISABLED"
    RECORDED_SYNTHETIC_EVALUATION_ONLY = "RECORDED_SYNTHETIC_EVALUATION_ONLY"


DEFAULT_KEYWORD_RANK_SCOPE: Final = KeywordRankScope.DISABLED


class KeywordRankSourceKind(str, Enum):
    RECORDED_MANUAL_CSV = "RECORDED_MANUAL_CSV"


class KeywordRankDevice(str, Enum):
    DESKTOP = "DESKTOP"
    MOBILE = "MOBILE"
    TABLET = "TABLET"
    UNKNOWN = "UNKNOWN"


class KeywordRankMetricType(str, Enum):
    POSITION = "POSITION"
    SEARCH_VOLUME = "SEARCH_VOLUME"
    DIFFICULTY = "DIFFICULTY"


class KeywordRankImportState(str, Enum):
    EVALUATED_NOT_IMPORTED = "EVALUATED_NOT_IMPORTED"


class KeywordRankBoundaryStatus(str, Enum):
    DISABLED = "DISABLED"
    FORBIDDEN = "FORBIDDEN"
    NOT_EXECUTED = "NOT_EXECUTED"
    NOT_USED = "NOT_USED"
    DEFERRED_POST_MVP = "DEFERRED_POST_MVP"


class KeywordRankFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    SOURCE_BYTES_MISMATCH = "SOURCE_BYTES_MISMATCH"
    SOURCE_DOCUMENT_INVALID = "SOURCE_DOCUMENT_INVALID"
    SOURCE_EXHAUSTED = "SOURCE_EXHAUSTED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_RESULT_INVALID = "SOURCE_RESULT_INVALID"
    DUPLICATE_OBSERVATION = "DUPLICATE_OBSERVATION"
    OBSERVATION_OUT_OF_PERIOD = "OBSERVATION_OUT_OF_PERIOD"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("keyword-rank values cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class KeywordRankFailure(ValueError):
    """Closed error that never retains rejected CSV or provider material."""

    code: KeywordRankFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not KeywordRankFailureCode:
            raise TypeError("invalid keyword-rank failure code")
        ValueError.__init__(self, self.code.value)

    def __repr__(self) -> str:
        return f"KeywordRankFailure(code={self.code.value})"

    def __str__(self) -> str:
        return self.code.value

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("keyword-rank failures cannot be serialized")


def fail_keyword_rank(
    code: KeywordRankFailureCode = KeywordRankFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise KeywordRankFailure(code) from None


def _nonzero_uuid(value: object) -> UUID:
    if type(value) is not UUID or value.int == 0:
        fail_keyword_rank()
    return value


def _bounded_positive_int(value: object, *, maximum: int) -> int:
    if type(value) is not int or not 0 < value <= maximum:
        fail_keyword_rank()
    return value


def _bounded_nonnegative_int(value: object, *, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        fail_keyword_rank()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Digest(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            fail_keyword_rank()

    @classmethod
    def of(cls, content: bytes) -> Sha256Digest:
        if type(content) is not bytes:
            fail_keyword_rank()
        return cls(hashlib.sha256(content).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class KeywordRankPeriod(_RedactedValue):
    date_from: date
    date_to: date

    def __post_init__(self) -> None:
        if (
            type(self.date_from) is not date
            or type(self.date_to) is not date
            or self.date_from > self.date_to
            or (self.date_to - self.date_from).days > 366
        ):
            fail_keyword_rank()


@dataclass(frozen=True, slots=True, repr=False)
class KeywordRankEvaluationCommand(_RedactedValue):
    recording_id: str
    site_id: UUID
    source_sha256: Sha256Digest
    source_bytes: int
    period: KeywordRankPeriod
    parser_version: str = KEYWORD_RANK_PARSER_VERSION
    scope: KeywordRankScope = DEFAULT_KEYWORD_RANK_SCOPE

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not str
            or _RECORDING_ID.fullmatch(self.recording_id) is None
            or type(self.source_sha256) is not Sha256Digest
            or type(self.period) is not KeywordRankPeriod
            or type(self.parser_version) is not str
            or self.parser_version != KEYWORD_RANK_PARSER_VERSION
            or type(self.scope) is not KeywordRankScope
        ):
            fail_keyword_rank()
        _nonzero_uuid(self.site_id)
        _bounded_positive_int(self.source_bytes, maximum=MAX_KEYWORD_RANK_SOURCE_BYTES)

    @property
    def canonical_sha256(self) -> Sha256Digest:
        document = {
            "parser_version": self.parser_version,
            "period": {
                "date_from": self.period.date_from.isoformat(),
                "date_to": self.period.date_to.isoformat(),
            },
            "recording_id": self.recording_id,
            "scope": self.scope.value,
            "site_id": str(self.site_id),
            "source_bytes": self.source_bytes,
            "source_sha256": self.source_sha256.value,
        }
        encoded = json.dumps(
            document,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        return Sha256Digest.of(encoded)


@dataclass(frozen=True, slots=True, repr=False)
class KeywordRankObservation(_RedactedValue):
    keyword_id: UUID
    locale: str
    device: KeywordRankDevice
    observation_date: date
    metric_type: KeywordRankMetricType
    value: Decimal
    unit: str | None
    provider_code: str
    confidence: Decimal
    raw_row_sha256: Sha256Digest

    def __post_init__(self) -> None:
        _nonzero_uuid(self.keyword_id)
        if (
            type(self.locale) is not str
            or _LOCALE.fullmatch(self.locale) is None
            or type(self.device) is not KeywordRankDevice
            or type(self.observation_date) is not date
            or type(self.metric_type) is not KeywordRankMetricType
            or type(self.value) is not Decimal
            or not self.value.is_finite()
            or len(self.value.as_tuple().digits) > 38
            or (
                self.unit is not None
                and (
                    type(self.unit) is not str
                    or _SAFE_UNIT.fullmatch(self.unit) is None
                )
            )
            or type(self.provider_code) is not str
            or _PROVIDER_CODE.fullmatch(self.provider_code) is None
            or type(self.confidence) is not Decimal
            or not self.confidence.is_finite()
            or not Decimal("0") <= self.confidence <= Decimal("1")
            or type(self.raw_row_sha256) is not Sha256Digest
        ):
            fail_keyword_rank()
        if self.metric_type is KeywordRankMetricType.POSITION and self.value <= 0:
            fail_keyword_rank()
        if self.metric_type is KeywordRankMetricType.SEARCH_VOLUME and (
            self.value < 0 or self.value != self.value.to_integral_value()
        ):
            fail_keyword_rank()
        if self.metric_type is KeywordRankMetricType.DIFFICULTY and not (
            Decimal("0") <= self.value <= Decimal("100")
        ):
            fail_keyword_rank()

    @property
    def identity(
        self,
    ) -> tuple[UUID, str, KeywordRankDevice, date, KeywordRankMetricType]:
        return (
            self.keyword_id,
            self.locale,
            self.device,
            self.observation_date,
            self.metric_type,
        )

    def canonical_document(self) -> dict[str, object]:
        return {
            "confidence": str(self.confidence),
            "device": self.device.value,
            "keyword_id": str(self.keyword_id),
            "locale": self.locale,
            "metric_type": self.metric_type.value,
            "observation_date": self.observation_date.isoformat(),
            "provider_code": self.provider_code,
            "raw_row_sha256": self.raw_row_sha256.value,
            "unit": self.unit,
            "value": str(self.value),
        }


@dataclass(frozen=True, slots=True, repr=False)
class KeywordRankBatch(_RedactedValue):
    recording_id: str
    site_id: UUID
    command_sha256: Sha256Digest
    source_sha256: Sha256Digest
    source_bytes: int
    source_kind: KeywordRankSourceKind
    parser_version: str
    observations: tuple[KeywordRankObservation, ...]

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not str
            or _RECORDING_ID.fullmatch(self.recording_id) is None
            or type(self.command_sha256) is not Sha256Digest
            or type(self.source_sha256) is not Sha256Digest
            or type(self.source_kind) is not KeywordRankSourceKind
            or self.source_kind is not KeywordRankSourceKind.RECORDED_MANUAL_CSV
            or type(self.parser_version) is not str
            or self.parser_version != KEYWORD_RANK_PARSER_VERSION
            or type(self.observations) is not tuple
            or not self.observations
            or len(self.observations) > MAX_KEYWORD_RANK_ROWS
            or any(
                type(observation) is not KeywordRankObservation
                for observation in self.observations
            )
        ):
            fail_keyword_rank()
        _nonzero_uuid(self.site_id)
        _bounded_positive_int(self.source_bytes, maximum=MAX_KEYWORD_RANK_SOURCE_BYTES)

    @property
    def normalized_sha256(self) -> Sha256Digest:
        rows = sorted(
            (observation.canonical_document() for observation in self.observations),
            key=lambda row: (
                str(row["keyword_id"]),
                str(row["locale"]),
                str(row["device"]),
                str(row["observation_date"]),
                str(row["metric_type"]),
            ),
        )
        encoded = json.dumps(
            rows,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        return Sha256Digest.of(encoded)


@dataclass(frozen=True, slots=True, repr=False)
class KeywordRankMetricCount(_RedactedValue):
    metric_type: KeywordRankMetricType
    count: int

    def __post_init__(self) -> None:
        if type(self.metric_type) is not KeywordRankMetricType:
            fail_keyword_rank()
        _bounded_nonnegative_int(self.count, maximum=MAX_KEYWORD_RANK_ROWS)


@dataclass(frozen=True, slots=True, repr=False)
class KeywordRankEvaluationSnapshot(_RedactedValue):
    recording_id: str
    site_id: UUID
    command_sha256: Sha256Digest
    source_sha256: Sha256Digest
    normalized_sha256: Sha256Digest
    source_kind: KeywordRankSourceKind
    parser_version: str
    row_count: int
    unique_keyword_count: int
    metric_counts: tuple[KeywordRankMetricCount, ...]
    observation_from: date
    observation_to: date
    scope: KeywordRankScope
    default_scope: KeywordRankScope
    import_state: KeywordRankImportState
    persistence: KeywordRankBoundaryStatus
    provider: KeywordRankBoundaryStatus
    network: KeywordRankBoundaryStatus
    credentials: KeywordRankBoundaryStatus
    serp_scrape: KeywordRankBoundaryStatus
    tracking_activation: KeywordRankBoundaryStatus
    kpi_read_model_write: KeywordRankBoundaryStatus
    recommendation_input: KeywordRankBoundaryStatus
    formal_tst_030: KeywordRankBoundaryStatus
    canonical_status: KeywordRankBoundaryStatus

    def __post_init__(self) -> None:
        expected_metric_order = tuple(KeywordRankMetricType)
        if (
            type(self.recording_id) is not str
            or _RECORDING_ID.fullmatch(self.recording_id) is None
            or type(self.command_sha256) is not Sha256Digest
            or type(self.source_sha256) is not Sha256Digest
            or type(self.normalized_sha256) is not Sha256Digest
            or type(self.source_kind) is not KeywordRankSourceKind
            or type(self.parser_version) is not str
            or self.parser_version != KEYWORD_RANK_PARSER_VERSION
            or type(self.metric_counts) is not tuple
            or tuple(row.metric_type for row in self.metric_counts)
            != expected_metric_order
            or any(
                type(row) is not KeywordRankMetricCount for row in self.metric_counts
            )
            or type(self.observation_from) is not date
            or type(self.observation_to) is not date
            or self.observation_from > self.observation_to
            or self.scope is not KeywordRankScope.RECORDED_SYNTHETIC_EVALUATION_ONLY
            or self.default_scope is not KeywordRankScope.DISABLED
            or self.import_state is not KeywordRankImportState.EVALUATED_NOT_IMPORTED
            or self.persistence is not KeywordRankBoundaryStatus.NOT_EXECUTED
            or self.provider is not KeywordRankBoundaryStatus.NOT_EXECUTED
            or self.network is not KeywordRankBoundaryStatus.NOT_EXECUTED
            or self.credentials is not KeywordRankBoundaryStatus.NOT_USED
            or self.serp_scrape is not KeywordRankBoundaryStatus.FORBIDDEN
            or self.tracking_activation is not KeywordRankBoundaryStatus.DISABLED
            or self.kpi_read_model_write is not KeywordRankBoundaryStatus.NOT_EXECUTED
            or self.recommendation_input is not KeywordRankBoundaryStatus.DISABLED
            or self.formal_tst_030 is not KeywordRankBoundaryStatus.NOT_EXECUTED
            or self.canonical_status is not KeywordRankBoundaryStatus.DEFERRED_POST_MVP
        ):
            fail_keyword_rank()
        _nonzero_uuid(self.site_id)
        _bounded_positive_int(self.row_count, maximum=MAX_KEYWORD_RANK_ROWS)
        _bounded_positive_int(self.unique_keyword_count, maximum=MAX_KEYWORD_RANK_ROWS)
        if (
            self.unique_keyword_count > self.row_count
            or sum(row.count for row in self.metric_counts) != self.row_count
        ):
            fail_keyword_rank()


__all__ = [
    "DEFAULT_KEYWORD_RANK_SCOPE",
    "KEYWORD_RANK_COLUMN_COUNT",
    "KEYWORD_RANK_CONTRACT_VERSION",
    "KEYWORD_RANK_PARSER_VERSION",
    "MAX_KEYWORD_RANK_ROWS",
    "MAX_KEYWORD_RANK_SOURCE_BYTES",
    "SYNTHETIC_FIXTURE_PROFILE",
    "SYNTHETIC_PROVIDER_CODE",
    "KeywordRankBatch",
    "KeywordRankBoundaryStatus",
    "KeywordRankDevice",
    "KeywordRankEvaluationCommand",
    "KeywordRankEvaluationSnapshot",
    "KeywordRankFailure",
    "KeywordRankFailureCode",
    "KeywordRankImportState",
    "KeywordRankMetricCount",
    "KeywordRankMetricType",
    "KeywordRankObservation",
    "KeywordRankPeriod",
    "KeywordRankScope",
    "KeywordRankSourceKind",
    "Sha256Digest",
    "fail_keyword_rank",
]
