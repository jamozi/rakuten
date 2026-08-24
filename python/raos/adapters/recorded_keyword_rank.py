"""One-shot caller-bytes CSV adapter for the ST-1206 synthetic fixture."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re
from threading import RLock
from typing import NoReturn, SupportsIndex, final
from uuid import UUID

from raos.domain.analytics.keyword_rank import (
    KEYWORD_RANK_COLUMN_COUNT,
    KEYWORD_RANK_PARSER_VERSION,
    MAX_KEYWORD_RANK_ROWS,
    MAX_KEYWORD_RANK_SOURCE_BYTES,
    SYNTHETIC_FIXTURE_PROFILE,
    SYNTHETIC_PROVIDER_CODE,
    KeywordRankBatch,
    KeywordRankDevice,
    KeywordRankEvaluationCommand,
    KeywordRankFailure,
    KeywordRankFailureCode,
    KeywordRankMetricType,
    KeywordRankObservation,
    KeywordRankSourceKind,
    Sha256Digest,
    fail_keyword_rank,
)


_HEADER = (
    "synthetic_fixture,keyword_id,locale,device,observation_date,metric_type,"
    "value,unit,provider_code,confidence"
)
_FORMULA_PREFIXES = frozenset("=+-@")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MAX_CELL_BYTES = 256
_REDACTED = "<redacted-recorded-keyword-rank-source>"


def _invalid() -> NoReturn:
    fail_keyword_rank(KeywordRankFailureCode.SOURCE_DOCUMENT_INVALID)


def _canonical_decimal(value: str) -> Decimal:
    if not value or len(value) > 48:
        _invalid()
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        _invalid()
    if (
        not parsed.is_finite()
        or str(parsed) != value
        or len(parsed.as_tuple().digits) > 38
    ):
        _invalid()
    return parsed


def _canonical_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _invalid()
    if parsed.isoformat() != value:
        _invalid()
    return parsed


def _canonical_uuid(value: str) -> UUID:
    try:
        parsed = UUID(value)
    except ValueError:
        _invalid()
    if str(parsed) != value or parsed.int == 0:
        _invalid()
    return parsed


def _enum_value[T: KeywordRankDevice | KeywordRankMetricType](
    enum_type: type[T], value: str
) -> T:
    try:
        return enum_type(value)
    except ValueError:
        _invalid()


def _parse_row(raw_row: bytes) -> KeywordRankObservation:
    if not raw_row or len(raw_row) > KEYWORD_RANK_COLUMN_COUNT * _MAX_CELL_BYTES:
        _invalid()
    try:
        line = raw_row.decode("ascii", errors="strict")
    except UnicodeDecodeError:
        _invalid()
    if '"' in line or _CONTROL.search(line) is not None:
        _invalid()
    cells = line.split(",")
    if len(cells) != KEYWORD_RANK_COLUMN_COUNT:
        _invalid()
    if any(len(cell.encode("ascii")) > _MAX_CELL_BYTES for cell in cells):
        _invalid()
    if any(cell and cell[0] in _FORMULA_PREFIXES for cell in cells):
        _invalid()
    (
        fixture_profile,
        keyword_id,
        locale,
        device,
        observation_date,
        metric_type,
        value,
        unit,
        provider_code,
        confidence,
    ) = cells
    if (
        fixture_profile != SYNTHETIC_FIXTURE_PROFILE
        or provider_code != SYNTHETIC_PROVIDER_CODE
    ):
        _invalid()
    parsed_device = _enum_value(KeywordRankDevice, device)
    parsed_metric = _enum_value(KeywordRankMetricType, metric_type)
    if (
        type(parsed_device) is not KeywordRankDevice
        or type(parsed_metric) is not KeywordRankMetricType
    ):
        _invalid()
    try:
        return KeywordRankObservation(
            keyword_id=_canonical_uuid(keyword_id),
            locale=locale,
            device=parsed_device,
            observation_date=_canonical_date(observation_date),
            metric_type=parsed_metric,
            value=_canonical_decimal(value),
            unit=unit or None,
            provider_code=provider_code,
            confidence=_canonical_decimal(confidence),
            raw_row_sha256=Sha256Digest.of(raw_row),
        )
    except KeywordRankFailure as exc:
        if exc.code is KeywordRankFailureCode.SOURCE_DOCUMENT_INVALID:
            raise
        _invalid()


def _parse(command: KeywordRankEvaluationCommand, payload: bytes) -> KeywordRankBatch:
    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > MAX_KEYWORD_RANK_SOURCE_BYTES
        or len(payload) != command.source_bytes
        or Sha256Digest.of(payload) != command.source_sha256
    ):
        fail_keyword_rank(KeywordRankFailureCode.SOURCE_BYTES_MISMATCH)
    if (
        payload.startswith(b"\xef\xbb\xbf")
        or b"\r" in payload
        or not payload.endswith(b"\n")
        or b"\x00" in payload
    ):
        _invalid()
    physical_rows = payload[:-1].split(b"\n")
    if not physical_rows or any(not row for row in physical_rows):
        _invalid()
    try:
        header = physical_rows[0].decode("ascii", errors="strict")
    except UnicodeDecodeError:
        _invalid()
    if header != _HEADER:
        _invalid()
    data_rows = physical_rows[1:]
    if not data_rows or len(data_rows) > MAX_KEYWORD_RANK_ROWS:
        _invalid()
    try:
        observations = tuple(_parse_row(row) for row in data_rows)
    except KeywordRankFailure:
        raise
    except Exception:
        _invalid()
    return KeywordRankBatch(
        recording_id=command.recording_id,
        site_id=command.site_id,
        command_sha256=command.canonical_sha256,
        source_sha256=command.source_sha256,
        source_bytes=command.source_bytes,
        source_kind=KeywordRankSourceKind.RECORDED_MANUAL_CSV,
        parser_version=KEYWORD_RANK_PARSER_VERSION,
        observations=observations,
    )


@final
class RecordedKeywordRankCsvSource:
    """Consume one immutable, caller-supplied synthetic CSV exactly once."""

    __slots__ = ("_consumed", "_lock", "_payload")

    def __init__(self, payload: bytes) -> None:
        if type(payload) is not bytes:
            fail_keyword_rank()
        self._payload = payload
        self._consumed = False
        self._lock = RLock()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded keyword-rank sources cannot be serialized")

    def read(self, command: KeywordRankEvaluationCommand) -> KeywordRankBatch:
        with self._lock:
            if self._consumed:
                fail_keyword_rank(KeywordRankFailureCode.SOURCE_EXHAUSTED)
            self._consumed = True
            if type(command) is not KeywordRankEvaluationCommand:
                fail_keyword_rank()
            try:
                return _parse(command, self._payload)
            except KeywordRankFailure:
                raise
            except Exception:
                _invalid()


__all__ = ["RecordedKeywordRankCsvSource"]
