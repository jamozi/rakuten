"""Owner-private Editorial V3 revenue intake and baseline reporting.

The tracked repository deliberately contains no live Rakuten column names,
provider rows, search queries, credentials, or financial values.  A parser
profile becomes usable only after an owner attests a sanitized real sample and
binds its exact header and status vocabulary.
"""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from collections.abc import Mapping, Sequence
import csv
from datetime import UTC, date, datetime, timedelta
from html import escape
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Final, NoReturn, cast
from urllib.parse import urlsplit

from raos.application.editorial.editorial_portfolio_v3 import (
    EditorialPortfolioV3,
)


MAX_PRIVATE_BYTES: Final = 32 * 1024 * 1024
MAX_COLUMNS: Final = 128
MAX_ROWS: Final = 1_000_000
MAX_CELL_LENGTH: Final = 16_384
SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
PRIVATE_NAME_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
FORMULA_PREFIXES: Final = ("=", "+", "-", "@")
ENCODINGS: Final = {"utf-8-sig", "cp932"}
DELIMITERS: Final = {"comma": ",", "tab": "\t"}
AMOUNT_FORMATS: Final = {"INTEGER_JPY", "GROUPED_INTEGER_JPY"}
DATE_FORMATS: Final = {
    "ISO_DATE": "%Y-%m-%d",
    "SLASH_YMD": "%Y/%m/%d",
    "JAPANESE_YMD": "%Y年%m月%d日",
    "ISO_DATETIME": "%Y-%m-%d %H:%M:%S",
    "SLASH_DATETIME": "%Y/%m/%d %H:%M:%S",
}
CANONICAL_STATUSES: Final = ("PENDING", "CONFIRMED", "CANCELLED")
ATTRIBUTION_BASES: Final = ("DIRECT", "ESTIMATED", "UNATTRIBUTED")
REQUIRED_GA4_EVENT_DIMENSIONS: Final = (
    "article_id",
    "snapshot_id",
    "cta_id",
    "offer_id",
    "product_id",
    "placement",
)
CTA_SCOPED_GA4_EVENTS: Final = (
    "affiliate_cta_impression",
    "affiliate_click",
    "product_card_view",
)
READBACK_COMPONENTS: Final = (
    "RAKUTEN_MEASUREMENT_IDS",
    "FIRST_PARTY_COLLECTOR",
    "GA4",
)
NEW_ARTICLE_CANDIDATE_ID: Final = "rakua-mini-color-vs-mini-plus"
NEW_ARTICLE_SOURCE_ID: Final = "solota-vs-rakua-mini-plus"
CANDIDATE_QUERY_DEMAND_SCHEMA: Final = "RAOS_EDITORIAL_V3_CANDIDATE_QUERY_DEMAND_V1"
CANDIDATE_QUERY_DEMAND_BASIS: Final = (
    "GSC_QUERY_DIMENSION_CANDIDATE_CLUSTER_NOT_ARTICLE_TOTAL"
)
RAKUTEN_ACTIVATION_DRY_RUN_SCHEMA: Final = (
    "RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_DRY_RUN_V2"
)


class EditorialEconomicsV3Failure(RuntimeError):
    """A stable, non-sensitive owner-private workflow failure."""


def _fail(code: str) -> NoReturn:
    raise EditorialEconomicsV3Failure(code) from None


def canonical_json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
                separators=(",", ": "),
            )
            + "\n"
        ).encode("utf-8")
    except TypeError, ValueError:
        _fail("RAOS_EDITORIAL_V3_JSON_INVALID")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _mapping(value: object) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail("RAOS_EDITORIAL_V3_DOCUMENT_INVALID")
    return cast(Mapping[str, object], value)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("RAOS_EDITORIAL_V3_PRIVATE_JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _list(value: object) -> list[object]:
    if type(value) is not list:
        _fail("RAOS_EDITORIAL_V3_DOCUMENT_INVALID")
    return cast(list[object], value)


def _text(value: object, *, maximum: int = MAX_CELL_LENGTH) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or "\x00" in value
    ):
        _fail("RAOS_EDITORIAL_V3_DOCUMENT_INVALID")
    return value


def _nonnegative_integer(value: object) -> int:
    if type(value) is not int or value < 0:
        _fail("RAOS_EDITORIAL_V3_DOCUMENT_INVALID")
    return value


def _positive_integer(value: object) -> int:
    result = _nonnegative_integer(value)
    if result == 0:
        _fail("RAOS_EDITORIAL_V3_DOCUMENT_INVALID")
    return result


def _sha256(value: object) -> str:
    result = _text(value, maximum=64)
    if SHA256_RE.fullmatch(result) is None:
        _fail("RAOS_EDITORIAL_V3_DOCUMENT_INVALID")
    return result


def _iso_date(value: object) -> str:
    result = _text(value, maximum=10)
    try:
        parsed = date.fromisoformat(result)
    except ValueError:
        _fail("RAOS_EDITORIAL_V3_DOCUMENT_INVALID")
    if parsed.isoformat() != result:
        _fail("RAOS_EDITORIAL_V3_DOCUMENT_INVALID")
    return result


def _iso_datetime(value: object) -> str:
    result = _text(value, maximum=40)
    try:
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError:
        _fail("RAOS_EDITORIAL_V3_DOCUMENT_INVALID")
    if parsed.tzinfo is None:
        _fail("RAOS_EDITORIAL_V3_DOCUMENT_INVALID")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def ensure_private_root(private_root: Path) -> Path:
    if not private_root.is_absolute():
        _fail("RAOS_EDITORIAL_V3_PRIVATE_ROOT_INVALID")
    try:
        private_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        metadata = private_root.lstat()
    except OSError:
        _fail("RAOS_EDITORIAL_V3_PRIVATE_ROOT_INVALID")
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        _fail("RAOS_EDITORIAL_V3_PRIVATE_ROOT_INVALID")
    return private_root


def private_path(private_root: Path, name: str) -> Path:
    root = ensure_private_root(private_root)
    if PRIVATE_NAME_RE.fullmatch(name) is None:
        _fail("RAOS_EDITORIAL_V3_PRIVATE_NAME_INVALID")
    return root / name


def read_private_bytes(private_root: Path, name: str) -> bytes:
    path = private_path(private_root, name)
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_PRIVATE_BYTES
        ):
            _fail("RAOS_EDITORIAL_V3_PRIVATE_FILE_INVALID")
        content = os.read(descriptor, before.st_size + 1)
        after = os.fstat(descriptor)
        if len(content) != before.st_size or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            _fail("RAOS_EDITORIAL_V3_PRIVATE_FILE_CHANGED")
        return content
    except EditorialEconomicsV3Failure:
        raise
    except OSError:
        _fail("RAOS_EDITORIAL_V3_PRIVATE_FILE_INVALID")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def read_private_json(private_root: Path, name: str) -> Mapping[str, object]:
    try:
        value = json.loads(
            read_private_bytes(private_root, name).decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_json_object,
        )
    except EditorialEconomicsV3Failure:
        raise
    except UnicodeError, json.JSONDecodeError:
        _fail("RAOS_EDITORIAL_V3_PRIVATE_JSON_INVALID")
    return _mapping(value)


def write_private_bytes(private_root: Path, name: str, content: bytes) -> Path:
    if not 1 <= len(content) <= MAX_PRIVATE_BYTES:
        _fail("RAOS_EDITORIAL_V3_PRIVATE_OUTPUT_INVALID")
    target = private_path(private_root, name)
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".next", dir=target.parent
        )
        temporary = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
        metadata = target.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            _fail("RAOS_EDITORIAL_V3_PRIVATE_OUTPUT_INVALID")
        return target
    except EditorialEconomicsV3Failure:
        raise
    except OSError:
        _fail("RAOS_EDITORIAL_V3_PRIVATE_OUTPUT_INVALID")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_private_json(
    private_root: Path, name: str, document: Mapping[str, object]
) -> Path:
    return write_private_bytes(private_root, name, canonical_json_bytes(document))


def _decode_csv(content: bytes, encoding: str) -> str:
    if encoding not in ENCODINGS:
        _fail("RAOS_EDITORIAL_V3_CSV_ENCODING_UNSUPPORTED")
    try:
        return content.decode(encoding, errors="strict")
    except UnicodeError:
        _fail("RAOS_EDITORIAL_V3_CSV_DECODE_FAILED")


def _csv_rows(
    content: bytes, *, encoding: str, delimiter_name: str
) -> tuple[tuple[str, ...], list[tuple[str, ...]]]:
    delimiter = DELIMITERS.get(delimiter_name)
    if delimiter is None:
        _fail("RAOS_EDITORIAL_V3_CSV_DELIMITER_UNSUPPORTED")
    try:
        reader = csv.reader(
            io.StringIO(_decode_csv(content, encoding), newline=""),
            delimiter=delimiter,
            strict=True,
        )
        rows = [tuple(row) for row in reader]
    except csv.Error, UnicodeError:
        _fail("RAOS_EDITORIAL_V3_CSV_INVALID")
    if not 2 <= len(rows) <= MAX_ROWS + 1:
        _fail("RAOS_EDITORIAL_V3_CSV_CARDINALITY_INVALID")
    header = rows[0]
    if (
        not 1 <= len(header) <= MAX_COLUMNS
        or len(set(header)) != len(header)
        or any(
            not cell
            or cell != cell.strip()
            or len(cell) > 300
            or "\x00" in cell
            or any(ord(character) < 32 for character in cell)
            for cell in header
        )
    ):
        _fail("RAOS_EDITORIAL_V3_CSV_HEADER_INVALID")
    body = rows[1:]
    if any(len(row) != len(header) for row in body):
        _fail("RAOS_EDITORIAL_V3_CSV_ROW_INVALID")
    if any(
        len(cell) > MAX_CELL_LENGTH or "\x00" in cell for row in body for cell in row
    ):
        _fail("RAOS_EDITORIAL_V3_CSV_CELL_INVALID")
    return header, body


def detect_rakuten_sample(
    content: bytes, *, encoding: str, delimiter_name: str
) -> dict[str, object]:
    header, rows = _csv_rows(content, encoding=encoding, delimiter_name=delimiter_name)
    return {
        "schema": "RAOS_EDITORIAL_V3_RAKUTEN_SCHEMA_DETECTION_V1",
        "version": "1.0.0",
        "state": "HEADER_DETECTED_PROFILE_NOT_BOUND",
        "source_sha256": sha256_bytes(content),
        "encoding": encoding,
        "delimiter": delimiter_name,
        "header": list(header),
        "row_count": len(rows),
        "owner_attestation_required": True,
        "live_parser_enabled": False,
    }


def rakuten_binding_template(
    detection: Mapping[str, object], *, detection_sha256: str
) -> dict[str, object]:
    _validate_detection(detection)
    return {
        "schema": "RAOS_EDITORIAL_V3_RAKUTEN_BIND_REQUEST_V1",
        "version": "1.0.0",
        "detection_receipt_sha256": detection_sha256,
        "detection_source_sha256": detection["source_sha256"],
        "owner_verified_sanitized_real_sample": False,
        "measurement_id_echo_verified_in_provider_report": False,
        "columns": {
            "provider_row_id": None,
            "status": None,
            "reward_jpy": None,
            "measurement_id": None,
            "occurred_on": None,
            "currency": None,
        },
        "status_values": {
            "PENDING": [],
            "CONFIRMED": [],
            "CANCELLED": [],
        },
        "amount_format": None,
        "date_format": None,
        "expected_currency": "JPY",
    }


def _validate_detection(detection: Mapping[str, object]) -> None:
    if set(detection) != {
        "schema",
        "version",
        "state",
        "source_sha256",
        "encoding",
        "delimiter",
        "header",
        "row_count",
        "owner_attestation_required",
        "live_parser_enabled",
    }:
        _fail("RAOS_EDITORIAL_V3_DETECTION_INVALID")
    header = [_text(value, maximum=300) for value in _list(detection["header"])]
    if (
        detection["schema"] != "RAOS_EDITORIAL_V3_RAKUTEN_SCHEMA_DETECTION_V1"
        or detection["version"] != "1.0.0"
        or detection["state"] != "HEADER_DETECTED_PROFILE_NOT_BOUND"
        or _sha256(detection["source_sha256"]) != detection["source_sha256"]
        or detection["encoding"] not in ENCODINGS
        or detection["delimiter"] not in DELIMITERS
        or not header
        or len(header) != len(set(header))
        or _positive_integer(detection["row_count"]) != detection["row_count"]
        or detection["owner_attestation_required"] is not True
        or detection["live_parser_enabled"] is not False
    ):
        _fail("RAOS_EDITORIAL_V3_DETECTION_INVALID")


def _parse_amount(value: str, amount_format: str) -> int:
    if amount_format == "INTEGER_JPY":
        normalized = value
        pattern = r"0|[1-9][0-9]*"
    elif amount_format == "GROUPED_INTEGER_JPY":
        normalized = value.replace(",", "")
        pattern = r"(?:0|[1-9][0-9]{0,2})(?:,[0-9]{3})*"
    else:
        _fail("RAOS_EDITORIAL_V3_AMOUNT_FORMAT_INVALID")
    if re.fullmatch(pattern, value) is None:
        _fail("RAOS_EDITORIAL_V3_REWARD_INVALID")
    result = int(normalized)
    if result > 10_000_000_000:
        _fail("RAOS_EDITORIAL_V3_REWARD_INVALID")
    return result


def _parse_date(value: str, date_format: str) -> str:
    pattern = DATE_FORMATS.get(date_format)
    if pattern is None:
        _fail("RAOS_EDITORIAL_V3_DATE_FORMAT_INVALID")
    try:
        parsed = datetime.strptime(value, pattern)
    except ValueError:
        _fail("RAOS_EDITORIAL_V3_REPORT_DATE_INVALID")
    return parsed.date().isoformat()


def _column_value(
    row: Sequence[str], header_index: Mapping[str, int], column: object
) -> str | None:
    if column is None:
        return None
    header = _text(column, maximum=300)
    position = header_index.get(header)
    if position is None:
        _fail("RAOS_EDITORIAL_V3_BOUND_COLUMN_INVALID")
    return row[position].strip()


def bind_rakuten_profile(
    *,
    sample_content: bytes,
    detection: Mapping[str, object],
    detection_content_sha256: str,
    request: Mapping[str, object],
    portfolio: EditorialPortfolioV3,
) -> dict[str, object]:
    _validate_detection(detection)
    expected_request_keys = {
        "schema",
        "version",
        "detection_receipt_sha256",
        "detection_source_sha256",
        "owner_verified_sanitized_real_sample",
        "measurement_id_echo_verified_in_provider_report",
        "columns",
        "status_values",
        "amount_format",
        "date_format",
        "expected_currency",
    }
    if set(request) != expected_request_keys:
        _fail("RAOS_EDITORIAL_V3_BIND_REQUEST_INVALID")
    if (
        request["schema"] != "RAOS_EDITORIAL_V3_RAKUTEN_BIND_REQUEST_V1"
        or request["version"] != "1.0.0"
        or _sha256(request["detection_receipt_sha256"]) != detection_content_sha256
        or _sha256(request["detection_source_sha256"]) != sha256_bytes(sample_content)
        or request["detection_source_sha256"] != detection["source_sha256"]
        or request["owner_verified_sanitized_real_sample"] is not True
        or request["measurement_id_echo_verified_in_provider_report"] is not True
        or request["amount_format"] not in AMOUNT_FORMATS
        or request["date_format"] not in DATE_FORMATS
        or request["expected_currency"] != "JPY"
    ):
        _fail("RAOS_EDITORIAL_V3_BIND_REQUEST_INVALID")
    columns = _mapping(request["columns"])
    if set(columns) != {
        "provider_row_id",
        "status",
        "reward_jpy",
        "measurement_id",
        "occurred_on",
        "currency",
    }:
        _fail("RAOS_EDITORIAL_V3_BIND_REQUEST_INVALID")
    for required in ("status", "reward_jpy", "measurement_id", "occurred_on"):
        _text(columns[required], maximum=300)
    for optional in ("provider_row_id", "currency"):
        if columns[optional] is not None:
            _text(columns[optional], maximum=300)
    mapped_headers = [
        _text(value, maximum=300) for value in columns.values() if value is not None
    ]
    detected_header = [
        _text(value, maximum=300) for value in _list(detection["header"])
    ]
    if len(mapped_headers) != len(set(mapped_headers)) or not set(
        mapped_headers
    ).issubset(detected_header):
        _fail("RAOS_EDITORIAL_V3_BOUND_COLUMN_INVALID")
    status_values_document = _mapping(request["status_values"])
    if set(status_values_document) != set(CANONICAL_STATUSES):
        _fail("RAOS_EDITORIAL_V3_STATUS_MAPPING_INVALID")
    status_values: dict[str, tuple[str, ...]] = {}
    flattened: list[str] = []
    for status in CANONICAL_STATUSES:
        values = tuple(
            _text(value, maximum=300) for value in _list(status_values_document[status])
        )
        if not values or len(values) != len(set(values)):
            _fail("RAOS_EDITORIAL_V3_STATUS_MAPPING_INVALID")
        status_values[status] = values
        flattened.extend(values)
    if len(flattened) != len(set(flattened)):
        _fail("RAOS_EDITORIAL_V3_STATUS_MAPPING_INVALID")

    encoding = _text(detection["encoding"])
    delimiter_name = _text(detection["delimiter"])
    header, rows = _csv_rows(
        sample_content, encoding=encoding, delimiter_name=delimiter_name
    )
    if list(header) != detected_header:
        _fail("RAOS_EDITORIAL_V3_SAMPLE_HEADER_CHANGED")
    header_index = {value: position for position, value in enumerate(header)}
    inverse_status = {
        provider_value: canonical
        for canonical, values in status_values.items()
        for provider_value in values
    }
    observed_statuses: set[str] = set()
    expected_measurements = set(portfolio.cta_by_measurement_id)
    matched_measurement_seen = False
    for row in rows:
        if any(value.lstrip().startswith(FORMULA_PREFIXES) for value in row):
            _fail("RAOS_EDITORIAL_V3_SAMPLE_FORMULA_CELL_REJECTED")
        provider_status = _column_value(row, header_index, columns["status"])
        if provider_status is None or provider_status not in inverse_status:
            _fail("RAOS_EDITORIAL_V3_SAMPLE_STATUS_UNBOUND")
        observed_statuses.add(inverse_status[provider_status])
        reward = _column_value(row, header_index, columns["reward_jpy"])
        occurred_on = _column_value(row, header_index, columns["occurred_on"])
        measurement = _column_value(row, header_index, columns["measurement_id"])
        if reward is None or occurred_on is None or measurement is None:
            _fail("RAOS_EDITORIAL_V3_SAMPLE_VALUE_INVALID")
        _parse_amount(reward, _text(request["amount_format"]))
        _parse_date(occurred_on, _text(request["date_format"]))
        matched_measurement_seen = (
            matched_measurement_seen or measurement in expected_measurements
        )
        currency = _column_value(row, header_index, columns["currency"])
        if currency is not None and currency != "JPY":
            _fail("RAOS_EDITORIAL_V3_SAMPLE_CURRENCY_INVALID")
    if observed_statuses != set(CANONICAL_STATUSES) or not matched_measurement_seen:
        _fail("RAOS_EDITORIAL_V3_SAMPLE_COVERAGE_INVALID")
    return {
        "schema": "RAOS_EDITORIAL_V3_RAKUTEN_PARSER_PROFILE_V1",
        "version": "1.0.0",
        "state": "VERIFIED_SAMPLE_BOUND",
        "parser_version": "rakuten-sanitized-csv.v1",
        "sample_source_sha256": sha256_bytes(sample_content),
        "detection_receipt_sha256": detection_content_sha256,
        "encoding": encoding,
        "delimiter": delimiter_name,
        "header": detected_header,
        "columns": dict(columns),
        "status_values": {
            status: list(status_values[status]) for status in CANONICAL_STATUSES
        },
        "amount_format": request["amount_format"],
        "date_format": request["date_format"],
        "expected_currency": "JPY",
        "measurement_id_echo_verified_in_provider_report": True,
        "direct_attribution_enabled": True,
        "estimated_attribution_enabled": False,
    }


def _validate_profile(profile: Mapping[str, object]) -> None:
    if set(profile) != {
        "schema",
        "version",
        "state",
        "parser_version",
        "sample_source_sha256",
        "detection_receipt_sha256",
        "encoding",
        "delimiter",
        "header",
        "columns",
        "status_values",
        "amount_format",
        "date_format",
        "expected_currency",
        "measurement_id_echo_verified_in_provider_report",
        "direct_attribution_enabled",
        "estimated_attribution_enabled",
    }:
        _fail("RAOS_EDITORIAL_V3_PROFILE_INVALID")
    if (
        profile["schema"] != "RAOS_EDITORIAL_V3_RAKUTEN_PARSER_PROFILE_V1"
        or profile["version"] != "1.0.0"
        or profile["state"] != "VERIFIED_SAMPLE_BOUND"
        or profile["parser_version"] != "rakuten-sanitized-csv.v1"
        or _sha256(profile["sample_source_sha256"]) != profile["sample_source_sha256"]
        or _sha256(profile["detection_receipt_sha256"])
        != profile["detection_receipt_sha256"]
        or profile["encoding"] not in ENCODINGS
        or profile["delimiter"] not in DELIMITERS
        or profile["amount_format"] not in AMOUNT_FORMATS
        or profile["date_format"] not in DATE_FORMATS
        or profile["expected_currency"] != "JPY"
        or profile["measurement_id_echo_verified_in_provider_report"] is not True
        or profile["direct_attribution_enabled"] is not True
        or profile["estimated_attribution_enabled"] is not False
    ):
        _fail("RAOS_EDITORIAL_V3_PROFILE_INVALID")
    header = [_text(value, maximum=300) for value in _list(profile["header"])]
    columns = _mapping(profile["columns"])
    if (
        not header
        or len(header) != len(set(header))
        or set(columns)
        != {
            "provider_row_id",
            "status",
            "reward_jpy",
            "measurement_id",
            "occurred_on",
            "currency",
        }
    ):
        _fail("RAOS_EDITORIAL_V3_PROFILE_INVALID")
    mapped: list[str] = []
    for name, value in columns.items():
        if value is None and name in {"provider_row_id", "currency"}:
            continue
        mapped.append(_text(value, maximum=300))
    if len(mapped) != len(set(mapped)) or not set(mapped).issubset(header):
        _fail("RAOS_EDITORIAL_V3_PROFILE_INVALID")
    statuses = _mapping(profile["status_values"])
    if set(statuses) != set(CANONICAL_STATUSES):
        _fail("RAOS_EDITORIAL_V3_PROFILE_INVALID")
    provider_values: list[str] = []
    for status in CANONICAL_STATUSES:
        values = [_text(value, maximum=300) for value in _list(statuses[status])]
        if not values or len(values) != len(set(values)):
            _fail("RAOS_EDITORIAL_V3_PROFILE_INVALID")
        provider_values.extend(values)
    if len(provider_values) != len(set(provider_values)):
        _fail("RAOS_EDITORIAL_V3_PROFILE_INVALID")


def parse_rakuten_report(
    *,
    content: bytes,
    profile: Mapping[str, object],
    profile_sha256: str,
    portfolio: EditorialPortfolioV3,
) -> dict[str, object]:
    _validate_profile(profile)
    _sha256(profile_sha256)
    encoding = _text(profile["encoding"])
    delimiter_name = _text(profile["delimiter"])
    header, rows = _csv_rows(content, encoding=encoding, delimiter_name=delimiter_name)
    expected_header = tuple(
        _text(value, maximum=300) for value in _list(profile["header"])
    )
    if header != expected_header:
        _fail("RAOS_EDITORIAL_V3_REPORT_HEADER_MISMATCH")
    columns = _mapping(profile["columns"])
    header_index = {value: position for position, value in enumerate(header)}
    statuses = _mapping(profile["status_values"])
    inverse_status = {
        _text(provider_value, maximum=300): canonical
        for canonical in CANONICAL_STATUSES
        for provider_value in _list(statuses[canonical])
    }
    cta_by_measurement = portfolio.cta_by_measurement_id
    totals = {status: 0 for status in CANONICAL_STATUSES}
    direct_by_article: dict[str, dict[str, int]] = {
        article.article_id: {status: 0 for status in CANONICAL_STATUSES}
        for article in portfolio.articles
    }
    basis_totals = {
        basis: {status: 0 for status in CANONICAL_STATUSES}
        for basis in ATTRIBUTION_BASES
    }
    dates: list[str] = []
    row_keys: set[str] = set()
    unmatched_measurement_count = 0
    formula_like_cells = 0
    for row in rows:
        for value in row:
            if value.lstrip().startswith(FORMULA_PREFIXES):
                formula_like_cells += 1
        if formula_like_cells:
            _fail("RAOS_EDITORIAL_V3_REPORT_FORMULA_CELL_REJECTED")
        provider_status = _column_value(row, header_index, columns["status"])
        if provider_status is None or provider_status not in inverse_status:
            _fail("RAOS_EDITORIAL_V3_REPORT_STATUS_UNBOUND")
        status = inverse_status[provider_status]
        reward_raw = _column_value(row, header_index, columns["reward_jpy"])
        occurred_raw = _column_value(row, header_index, columns["occurred_on"])
        measurement_id = _column_value(row, header_index, columns["measurement_id"])
        if reward_raw is None or occurred_raw is None or measurement_id is None:
            _fail("RAOS_EDITORIAL_V3_REPORT_ROW_INVALID")
        reward = _parse_amount(reward_raw, _text(profile["amount_format"]))
        occurred_on = _parse_date(occurred_raw, _text(profile["date_format"]))
        currency = _column_value(row, header_index, columns["currency"])
        if currency is not None and currency != "JPY":
            _fail("RAOS_EDITORIAL_V3_REPORT_CURRENCY_INVALID")
        provider_row_id = _column_value(row, header_index, columns["provider_row_id"])
        row_key_payload = (
            f"provider:{provider_row_id}"
            if provider_row_id
            else json.dumps(list(row), ensure_ascii=False, separators=(",", ":"))
        )
        row_key = sha256_bytes(row_key_payload.encode("utf-8"))
        if row_key in row_keys:
            _fail("RAOS_EDITORIAL_V3_REPORT_DUPLICATE_ROW")
        row_keys.add(row_key)
        dates.append(occurred_on)
        totals[status] += reward
        binding = cta_by_measurement.get(measurement_id)
        if binding is None:
            basis = "UNATTRIBUTED"
            unmatched_measurement_count += 1
        else:
            basis = "DIRECT"
            direct_by_article[binding.article_id][status] += reward
        basis_totals[basis][status] += reward

    return {
        "schema": "RAOS_EDITORIAL_V3_RAKUTEN_DRY_RUN_V1",
        "version": "1.0.0",
        "state": "DRY_RUN_NOT_COMMITTED",
        "source_sha256": sha256_bytes(content),
        "profile_sha256": profile_sha256,
        "parser_version": profile["parser_version"],
        "period": {"date_from": min(dates), "date_to": max(dates)},
        "row_count": len(rows),
        "currency": "JPY",
        "totals_jpy": totals,
        "attribution": {
            "DIRECT": {
                "state": "VERIFIED_MEASUREMENT_ID_MATCH",
                "totals_jpy": basis_totals["DIRECT"],
            },
            "ESTIMATED": {
                "state": "NOT_PRODUCED_BY_PROVIDER_REPORT_IMPORT",
                "totals_jpy": basis_totals["ESTIMATED"],
            },
            "UNATTRIBUTED": {
                "state": "NO_VERIFIED_MEASUREMENT_ID_MATCH",
                "totals_jpy": basis_totals["UNATTRIBUTED"],
            },
        },
        "direct_by_article_jpy": direct_by_article,
        "unmatched_measurement_row_count": unmatched_measurement_count,
        "raw_rows_persisted": False,
        "commit_gate": {
            "source_hash_equality_required": True,
            "profile_hash_equality_required": True,
            "provider_total_reconciliation_required": True,
        },
    }


def commit_rakuten_report(
    *,
    dry_run: Mapping[str, object],
    reparsed: Mapping[str, object],
    expected_source_sha256: str,
    provider_row_count: int,
    provider_totals_jpy: Mapping[str, int],
) -> dict[str, object]:
    if dry_run != reparsed:
        _fail("RAOS_EDITORIAL_V3_DRY_RUN_REPARSE_MISMATCH")
    if (
        dry_run.get("schema") != "RAOS_EDITORIAL_V3_RAKUTEN_DRY_RUN_V1"
        or dry_run.get("state") != "DRY_RUN_NOT_COMMITTED"
        or _sha256(expected_source_sha256) != dry_run.get("source_sha256")
        or _positive_integer(provider_row_count) != dry_run.get("row_count")
        or set(provider_totals_jpy) != set(CANONICAL_STATUSES)
    ):
        _fail("RAOS_EDITORIAL_V3_COMMIT_PRECONDITION_FAILED")
    normalized_provider_totals = {
        status: _nonnegative_integer(provider_totals_jpy[status])
        for status in CANONICAL_STATUSES
    }
    if normalized_provider_totals != dry_run.get("totals_jpy"):
        _fail("RAOS_EDITORIAL_V3_PROVIDER_RECONCILIATION_FAILED")
    return {
        **dry_run,
        "schema": "RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_V1",
        "state": "COMMITTED_OWNER_PRIVATE_RECONCILED",
        "reconciliation": {
            "status": "PASS",
            "provider_row_count": provider_row_count,
            "provider_totals_jpy": normalized_provider_totals,
            "source_sha256_equal_to_dry_run": True,
            "profile_sha256_equal_to_dry_run": True,
        },
    }


def cost_input_template(portfolio: EditorialPortfolioV3) -> dict[str, object]:
    return {
        "schema": "RAOS_EDITORIAL_V3_COST_INPUT_V1",
        "version": "1.0.0",
        "owner_attested": False,
        "period": {"date_from": None, "date_to": None},
        "approved_hourly_cost_jpy": None,
        "articles": [
            {
                "article_id": article.article_id,
                "editorial_minutes": None,
                "variable_external_cost_jpy": None,
            }
            for article in portfolio.articles
        ],
    }


def validate_cost_input(
    document: Mapping[str, object], portfolio: EditorialPortfolioV3
) -> dict[str, object]:
    if set(document) != {
        "schema",
        "version",
        "owner_attested",
        "period",
        "approved_hourly_cost_jpy",
        "articles",
    }:
        _fail("RAOS_EDITORIAL_V3_COST_INPUT_INVALID")
    period = _mapping(document["period"])
    if (
        document["schema"] != "RAOS_EDITORIAL_V3_COST_INPUT_V1"
        or document["version"] != "1.0.0"
        or document["owner_attested"] is not True
        or set(period) != {"date_from", "date_to"}
    ):
        _fail("RAOS_EDITORIAL_V3_COST_INPUT_INVALID")
    date_from = _iso_date(period["date_from"])
    date_to = _iso_date(period["date_to"])
    if date_from > date_to:
        _fail("RAOS_EDITORIAL_V3_COST_INPUT_INVALID")
    hourly = _nonnegative_integer(document["approved_hourly_cost_jpy"])
    expected_ids = {article.article_id for article in portfolio.articles}
    rows: dict[str, dict[str, int | str]] = {}
    for raw in _list(document["articles"]):
        row = _mapping(raw)
        if set(row) != {
            "article_id",
            "editorial_minutes",
            "variable_external_cost_jpy",
        }:
            _fail("RAOS_EDITORIAL_V3_COST_INPUT_INVALID")
        article_id = _text(row["article_id"])
        if article_id in rows:
            _fail("RAOS_EDITORIAL_V3_COST_INPUT_INVALID")
        rows[article_id] = {
            "article_id": article_id,
            "editorial_minutes": _nonnegative_integer(row["editorial_minutes"]),
            "variable_external_cost_jpy": _nonnegative_integer(
                row["variable_external_cost_jpy"]
            ),
        }
    if set(rows) != expected_ids:
        _fail("RAOS_EDITORIAL_V3_COST_INPUT_INVALID")
    return {
        "period": {"date_from": date_from, "date_to": date_to},
        "approved_hourly_cost_jpy": hourly,
        "articles": rows,
    }


def _validate_rakuten_activation_dry_run(
    *,
    document: Mapping[str, object],
    document_sha256: str,
    expected_portfolio_sha256: str,
    portfolio: EditorialPortfolioV3,
) -> dict[str, str]:
    """Validate the exact owner-private activation set bound to live readback."""

    if set(document) != {
        "schema",
        "version",
        "state",
        "portfolio_sha256",
        "admin_receipt_sha256",
        "money_link_mapping_sha256",
        "activation_inputs",
        "v2_materialization",
        "overlays",
        "materialized_set_sha256",
        "article_count",
        "cta_count",
        "provider_parameter_inference_used",
        "tracked_source_modified",
        "live_write_performed",
        "publication_authorized",
    }:
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID")
    dry_run_sha256 = _sha256(document_sha256)
    portfolio_sha256 = _sha256(document["portfolio_sha256"])
    expected_portfolio = _sha256(expected_portfolio_sha256)
    admin_receipt_sha256 = _sha256(document["admin_receipt_sha256"])
    money_link_mapping_sha256 = _sha256(document["money_link_mapping_sha256"])
    materialized_set_sha256 = _sha256(document["materialized_set_sha256"])
    expected_cta_count = sum(
        len(article.cta_bindings) for article in portfolio.articles
    )
    if (
        document["schema"] != RAKUTEN_ACTIVATION_DRY_RUN_SCHEMA
        or document["version"] != "2.1.0"
        or document["state"] != "OWNER_PRIVATE_MATERIALIZED_NOT_PUBLISHED"
        or portfolio_sha256 != expected_portfolio
        or expected_portfolio != portfolio.source_sha256
        or document["article_count"] != len(portfolio.articles)
        or document["cta_count"] != expected_cta_count
        or expected_cta_count != len(portfolio.cta_by_measurement_id)
        or document["provider_parameter_inference_used"] is not False
        or document["tracked_source_modified"] is not False
        or document["live_write_performed"] is not False
        or document["publication_authorized"] is not False
        or sha256_bytes(canonical_json_bytes(document)) != dry_run_sha256
    ):
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID")

    activation_inputs = _mapping(document["activation_inputs"])
    if set(activation_inputs) != {
        "admin_receipt_name",
        "money_link_mapping_name",
        "mapping_generated_at_utc",
        "admin_verified_at_utc",
        "activated_at_utc",
    }:
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID")
    admin_receipt_name = _text(activation_inputs["admin_receipt_name"], maximum=128)
    money_link_mapping_name = _text(
        activation_inputs["money_link_mapping_name"], maximum=128
    )
    mapping_generated_at = _iso_datetime(
        activation_inputs["mapping_generated_at_utc"]
    )
    admin_verified_at = _iso_datetime(activation_inputs["admin_verified_at_utc"])
    activated_at = _iso_datetime(activation_inputs["activated_at_utc"])
    mapping_time = datetime.fromisoformat(mapping_generated_at.replace("Z", "+00:00"))
    verified_time = datetime.fromisoformat(admin_verified_at.replace("Z", "+00:00"))
    activation_time = datetime.fromisoformat(activated_at.replace("Z", "+00:00"))
    if (
        PRIVATE_NAME_RE.fullmatch(admin_receipt_name) is None
        or PRIVATE_NAME_RE.fullmatch(money_link_mapping_name) is None
        or admin_receipt_name == money_link_mapping_name
        or mapping_time > verified_time
        or verified_time > activation_time
        or verified_time - mapping_time > timedelta(hours=24)
        or activation_time - verified_time > timedelta(minutes=15)
    ):
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID")

    v2 = _mapping(document["v2_materialization"])
    if set(v2) != {
        "portfolio_sha256",
        "evidence_status_sha256",
        "manufacturer_sales_state_sha256",
        "manufacturer_sales_state_checked_at_utc",
        "local_generated_at",
        "production_generated_at",
        "local_receipt_sha256",
        "production_receipt_sha256",
    }:
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID")
    v2_portfolio_sha256 = _sha256(v2["portfolio_sha256"])
    v2_evidence_status_sha256 = _sha256(v2["evidence_status_sha256"])
    v2_manufacturer_sales_state_sha256 = _sha256(
        v2["manufacturer_sales_state_sha256"]
    )
    v2_manufacturer_sales_state_checked_at_utc = _iso_datetime(
        v2["manufacturer_sales_state_checked_at_utc"]
    )
    v2_local_receipt_sha256 = _sha256(v2["local_receipt_sha256"])
    v2_production_receipt_sha256 = _sha256(v2["production_receipt_sha256"])
    _iso_datetime(v2["local_generated_at"])
    _iso_datetime(v2["production_generated_at"])

    overlays = _mapping(document["overlays"])
    if set(overlays) != {"local", "production"}:
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID")
    expected_articles = portfolio.article_by_id
    overlay_bindings: dict[str, dict[str, str]] = {}
    for mode in ("local", "production"):
        overlay = _mapping(overlays[mode])
        if set(overlay) != {
            "directory_name",
            "posts_sha256",
            "article_set_sha256",
            "overlay_receipt_sha256",
            "articles",
        }:
            _fail("RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID")
        posts_sha256 = _sha256(overlay["posts_sha256"])
        article_set_sha256 = _sha256(overlay["article_set_sha256"])
        overlay_receipt_sha256 = _sha256(overlay["overlay_receipt_sha256"])
        prefix = (
            "local-materialized-fixtures-v3-"
            if mode == "local"
            else "production-materialized-fixtures-v3-"
        )
        if overlay["directory_name"] != prefix + overlay_receipt_sha256[:16]:
            _fail("RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID")
        article_rows = _list(overlay["articles"])
        if len(article_rows) != len(expected_articles):
            _fail("RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID")
        normalized_rows: list[dict[str, object]] = []
        seen: set[str] = set()
        total_ctas = 0
        for raw in article_rows:
            row = _mapping(raw)
            if set(row) != {
                "article_id",
                "production_slug",
                "source_sha256",
                "materialized_sha256",
                "cta_count",
            }:
                _fail("RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID")
            article_id = _text(row["article_id"])
            article = expected_articles.get(article_id)
            source_sha256 = _sha256(row["source_sha256"])
            activated_sha256 = _sha256(row["materialized_sha256"])
            if (
                article is None
                or article_id in seen
                or row["production_slug"] != article.production_slug
                or row["cta_count"] != len(article.cta_bindings)
            ):
                _fail("RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID")
            seen.add(article_id)
            total_ctas += len(article.cta_bindings)
            normalized_rows.append(
                {
                    "article_id": article_id,
                    "production_slug": article.production_slug,
                    "source_sha256": source_sha256,
                    "materialized_sha256": activated_sha256,
                    "cta_count": len(article.cta_bindings),
                }
            )
        computed_article_set_sha256 = sha256_bytes(
            canonical_json_bytes(
                [
                    {
                        "article_id": row["article_id"],
                        "production_slug": row["production_slug"],
                        "sha256": row["materialized_sha256"],
                    }
                    for row in normalized_rows
                ]
            )
        )
        v2_receipt_sha256 = (
            v2_local_receipt_sha256
            if mode == "local"
            else v2_production_receipt_sha256
        )
        overlay_receipt = {
            "schema": "RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_OVERLAY_RECEIPT_V1",
            "version": "1.0.0",
            "mode": mode,
            "portfolio_sha256": portfolio_sha256,
            "v2_portfolio_sha256": v2_portfolio_sha256,
            "v2_evidence_status_sha256": v2_evidence_status_sha256,
            "v2_manufacturer_sales_state_sha256": (
                v2_manufacturer_sales_state_sha256
            ),
            "v2_manufacturer_sales_state_checked_at_utc": (
                v2_manufacturer_sales_state_checked_at_utc
            ),
            "v2_materialization_receipt_sha256": v2_receipt_sha256,
            "posts_sha256": posts_sha256,
            "article_set_sha256": article_set_sha256,
            "article_count": len(normalized_rows),
            "cta_count": total_ctas,
            "articles": normalized_rows,
        }
        if (
            seen != set(expected_articles)
            or total_ctas != expected_cta_count
            or computed_article_set_sha256 != article_set_sha256
            or sha256_bytes(canonical_json_bytes(overlay_receipt))
            != overlay_receipt_sha256
        ):
            _fail("RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID")
        overlay_bindings[mode] = {
            "posts_sha256": posts_sha256,
            "article_set_sha256": article_set_sha256,
            "overlay_receipt_sha256": overlay_receipt_sha256,
        }
    computed_materialized_set_sha256 = sha256_bytes(
        canonical_json_bytes(overlay_bindings)
    )
    if computed_materialized_set_sha256 != materialized_set_sha256:
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID")
    return {
        "dry_run_sha256": dry_run_sha256,
        "portfolio_sha256": portfolio_sha256,
        "admin_receipt_sha256": admin_receipt_sha256,
        "money_link_mapping_sha256": money_link_mapping_sha256,
        "v2_portfolio_sha256": v2_portfolio_sha256,
        "v2_evidence_status_sha256": v2_evidence_status_sha256,
        "v2_manufacturer_sales_state_sha256": v2_manufacturer_sales_state_sha256,
        "v2_manufacturer_sales_state_checked_at_utc": (
            v2_manufacturer_sales_state_checked_at_utc
        ),
        "v2_local_receipt_sha256": v2_local_receipt_sha256,
        "v2_production_receipt_sha256": v2_production_receipt_sha256,
        "production_posts_sha256": overlay_bindings["production"]["posts_sha256"],
        "production_article_set_sha256": overlay_bindings["production"][
            "article_set_sha256"
        ],
        "production_overlay_receipt_sha256": overlay_bindings["production"][
            "overlay_receipt_sha256"
        ],
        "materialized_set_sha256": materialized_set_sha256,
    }


def production_readback_template(
    portfolio: EditorialPortfolioV3,
) -> dict[str, object]:
    """Return a disabled template; it is not evidence until fully attested."""

    return {
        "schema": "RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INPUT_V2",
        "version": "2.0.0",
        "owner_attested": False,
        "target_origin": portfolio.target_origin,
        "analytics_site_binding": {
            "state": "NOT_RECORDED",
            "binding_sha256": None,
            "ga4_property_id_sha256": None,
            "ga4_configuration_response_sha256": None,
        },
        "observations": [
            {
                "component": "RAKUTEN_MEASUREMENT_IDS",
                "state": "NOT_RECORDED",
                "observed_at": None,
                "request_sha256": None,
                "response_sha256": None,
                "details": {
                    "measurement_ids": sorted(portfolio.cta_by_measurement_id),
                    "live_link_count": None,
                    "all_ids_echo_verified": False,
                    "activation_dry_run_sha256": None,
                    "materialized_set_sha256": None,
                    "production_posts_sha256": None,
                    "production_article_set_sha256": None,
                    "production_overlay_receipt_sha256": None,
                },
            },
            {
                "component": "FIRST_PARTY_COLLECTOR",
                "state": "NOT_RECORDED",
                "observed_at": None,
                "request_sha256": None,
                "response_sha256": None,
                "details": {
                    "endpoint": "/wp-json/raos/v1/events",
                    "http_status": None,
                    "aggregate_readback_observed": False,
                    "event_id_sha256": None,
                },
            },
            {
                "component": "GA4",
                "state": "NOT_RECORDED",
                "observed_at": None,
                "request_sha256": None,
                "response_sha256": None,
                "details": {
                    "property_id_sha256": None,
                    "configuration_response_sha256": None,
                    "analytics_site_binding_sha256": None,
                    "event_name": "article_view",
                    "article_id": None,
                    "event_observed": False,
                },
            },
        ],
    }


def establish_t0_receipt(
    *,
    document: Mapping[str, object],
    observation_sha256: str,
    rakuten_activation: Mapping[str, object],
    rakuten_activation_sha256: str,
    expected_portfolio_sha256: str,
    portfolio: EditorialPortfolioV3,
    evaluated_at: datetime | None = None,
) -> dict[str, object]:
    activation_binding = _validate_rakuten_activation_dry_run(
        document=rakuten_activation,
        document_sha256=rakuten_activation_sha256,
        expected_portfolio_sha256=expected_portfolio_sha256,
        portfolio=portfolio,
    )
    if set(document) != {
        "schema",
        "version",
        "owner_attested",
        "target_origin",
        "analytics_site_binding",
        "observations",
    }:
        _fail("RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID")
    binding = _mapping(document["analytics_site_binding"])
    if (
        set(binding)
        != {
            "state",
            "binding_sha256",
            "ga4_property_id_sha256",
            "ga4_configuration_response_sha256",
        }
        or binding["state"] != "OWNER_PRIVATE_READ_ONLY_BINDING_VERIFIED"
    ):
        _fail("RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID")
    binding_sha256 = _sha256(binding["binding_sha256"])
    expected_ga4_property_id_sha256 = _sha256(binding["ga4_property_id_sha256"])
    expected_ga4_configuration_sha256 = _sha256(
        binding["ga4_configuration_response_sha256"]
    )
    if (
        document["schema"] != "RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INPUT_V2"
        or document["version"] != "2.0.0"
        or document["owner_attested"] is not True
        or document["target_origin"] != portfolio.target_origin
    ):
        _fail("RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID")
    source_sha256 = _sha256(observation_sha256)
    now = (evaluated_at or datetime.now(UTC)).astimezone(UTC)
    expected_measurements = set(portfolio.cta_by_measurement_id)
    article_ids = set(portfolio.article_by_id)
    earliest_success: dict[str, dict[str, str]] = {}
    for raw in _list(document["observations"]):
        row = _mapping(raw)
        if set(row) != {
            "component",
            "state",
            "observed_at",
            "request_sha256",
            "response_sha256",
            "details",
        }:
            _fail("RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID")
        component = _text(row["component"])
        if component not in READBACK_COMPONENTS or row["state"] != "SUCCESS":
            _fail("RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID")
        observed_at = _iso_datetime(row["observed_at"])
        observed_time = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        request_sha256 = _sha256(row["request_sha256"])
        response_sha256 = _sha256(row["response_sha256"])
        if observed_time > now:
            _fail("RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID")
        details = _mapping(row["details"])
        if component == "RAKUTEN_MEASUREMENT_IDS":
            if set(details) != {
                "measurement_ids",
                "live_link_count",
                "all_ids_echo_verified",
                "activation_dry_run_sha256",
                "materialized_set_sha256",
                "production_posts_sha256",
                "production_article_set_sha256",
                "production_overlay_receipt_sha256",
            }:
                _fail("RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID")
            measurement_ids = {
                _text(value, maximum=64) for value in _list(details["measurement_ids"])
            }
            if (
                measurement_ids != expected_measurements
                or _positive_integer(details["live_link_count"])
                != len(expected_measurements)
                or details["all_ids_echo_verified"] is not True
                or _sha256(details["activation_dry_run_sha256"])
                != activation_binding["dry_run_sha256"]
                or _sha256(details["materialized_set_sha256"])
                != activation_binding["materialized_set_sha256"]
                or _sha256(details["production_posts_sha256"])
                != activation_binding["production_posts_sha256"]
                or _sha256(details["production_article_set_sha256"])
                != activation_binding["production_article_set_sha256"]
                or _sha256(details["production_overlay_receipt_sha256"])
                != activation_binding["production_overlay_receipt_sha256"]
            ):
                _fail("RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID")
        elif component == "FIRST_PARTY_COLLECTOR":
            if set(details) != {
                "endpoint",
                "http_status",
                "aggregate_readback_observed",
                "event_id_sha256",
            } or (
                details["endpoint"] != "/wp-json/raos/v1/events"
                or details["http_status"] != 202
                or details["aggregate_readback_observed"] is not True
                or _sha256(details["event_id_sha256"]) != details["event_id_sha256"]
            ):
                _fail("RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID")
        else:
            if set(details) != {
                "property_id_sha256",
                "configuration_response_sha256",
                "analytics_site_binding_sha256",
                "event_name",
                "article_id",
                "event_observed",
            } or (
                _sha256(details["property_id_sha256"]) != details["property_id_sha256"]
                or details["property_id_sha256"] != expected_ga4_property_id_sha256
                or _sha256(details["configuration_response_sha256"])
                != details["configuration_response_sha256"]
                or details["configuration_response_sha256"]
                != expected_ga4_configuration_sha256
                or _sha256(details["analytics_site_binding_sha256"])
                != details["analytics_site_binding_sha256"]
                or details["analytics_site_binding_sha256"] != binding_sha256
                or details["event_name"] != "article_view"
                or details["article_id"] not in article_ids
                or details["event_observed"] is not True
            ):
                _fail("RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID")
        candidate = {
            "component": component,
            "observed_at": observed_at,
            "request_sha256": request_sha256,
            "response_sha256": response_sha256,
        }
        if component == "RAKUTEN_MEASUREMENT_IDS":
            candidate["activation_dry_run_sha256"] = activation_binding[
                "dry_run_sha256"
            ]
            candidate["materialized_set_sha256"] = activation_binding[
                "materialized_set_sha256"
            ]
            candidate["production_posts_sha256"] = activation_binding[
                "production_posts_sha256"
            ]
            candidate["production_article_set_sha256"] = activation_binding[
                "production_article_set_sha256"
            ]
            candidate["production_overlay_receipt_sha256"] = activation_binding[
                "production_overlay_receipt_sha256"
            ]
        previous = earliest_success.get(component)
        if previous is None or observed_at < previous["observed_at"]:
            earliest_success[component] = candidate
    if set(earliest_success) != set(READBACK_COMPONENTS):
        _fail("RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INCOMPLETE")
    ordered = [earliest_success[component] for component in READBACK_COMPONENTS]
    t0 = max(row["observed_at"] for row in ordered)
    return {
        "schema": "RAOS_EDITORIAL_V3_T0_RECEIPT_V2",
        "version": "2.0.0",
        "state": "ESTABLISHED_FROM_EXACT_PRODUCTION_READBACKS",
        "target_origin": portfolio.target_origin,
        "analytics_site_binding": {
            "binding_sha256": binding_sha256,
            "ga4_property_id_sha256": expected_ga4_property_id_sha256,
            "ga4_configuration_response_sha256": (expected_ga4_configuration_sha256),
        },
        "rakuten_activation_binding": activation_binding,
        "observation_sha256": source_sha256,
        "t0": t0,
        "derivation": "MAX_OF_EARLIEST_SUCCESS_PER_REQUIRED_COMPONENT",
        "components": ordered,
        "automatic_publication": False,
        "external_mutation_performed": False,
    }


def validate_t0_receipt(
    document: Mapping[str, object], portfolio: EditorialPortfolioV3
) -> str:
    if set(document) != {
        "schema",
        "version",
        "state",
        "target_origin",
        "analytics_site_binding",
        "rakuten_activation_binding",
        "observation_sha256",
        "t0",
        "derivation",
        "components",
        "automatic_publication",
        "external_mutation_performed",
    }:
        _fail("RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID")
    if (
        document["schema"] != "RAOS_EDITORIAL_V3_T0_RECEIPT_V2"
        or document["version"] != "2.0.0"
        or document["state"] != "ESTABLISHED_FROM_EXACT_PRODUCTION_READBACKS"
        or document["target_origin"] != portfolio.target_origin
        or _sha256(document["observation_sha256"]) != document["observation_sha256"]
        or document["derivation"] != "MAX_OF_EARLIEST_SUCCESS_PER_REQUIRED_COMPONENT"
        or document["automatic_publication"] is not False
        or document["external_mutation_performed"] is not False
    ):
        _fail("RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID")
    binding = _mapping(document["analytics_site_binding"])
    if set(binding) != {
        "binding_sha256",
        "ga4_property_id_sha256",
        "ga4_configuration_response_sha256",
    }:
        _fail("RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID")
    _sha256(binding["binding_sha256"])
    _sha256(binding["ga4_property_id_sha256"])
    _sha256(binding["ga4_configuration_response_sha256"])
    activation = _mapping(document["rakuten_activation_binding"])
    if set(activation) != {
        "dry_run_sha256",
        "portfolio_sha256",
        "admin_receipt_sha256",
        "money_link_mapping_sha256",
        "v2_portfolio_sha256",
        "v2_evidence_status_sha256",
        "v2_manufacturer_sales_state_sha256",
        "v2_manufacturer_sales_state_checked_at_utc",
        "v2_local_receipt_sha256",
        "v2_production_receipt_sha256",
        "production_posts_sha256",
        "production_article_set_sha256",
        "production_overlay_receipt_sha256",
        "materialized_set_sha256",
    }:
        _fail("RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID")
    for name, value in activation.items():
        if name == "v2_manufacturer_sales_state_checked_at_utc":
            _iso_datetime(value)
        else:
            _sha256(value)
    if activation["portfolio_sha256"] != portfolio.source_sha256:
        _fail("RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID")
    components: list[Mapping[str, object]] = []
    for raw in _list(document["components"]):
        row = _mapping(raw)
        component = row.get("component")
        expected_fields = {
            "component",
            "observed_at",
            "request_sha256",
            "response_sha256",
        }
        if component == "RAKUTEN_MEASUREMENT_IDS":
            expected_fields |= {
                "activation_dry_run_sha256",
                "materialized_set_sha256",
                "production_posts_sha256",
                "production_article_set_sha256",
                "production_overlay_receipt_sha256",
            }
        if set(row) != expected_fields:
            _fail("RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID")
        _iso_datetime(row["observed_at"])
        _sha256(row["request_sha256"])
        _sha256(row["response_sha256"])
        if component == "RAKUTEN_MEASUREMENT_IDS" and (
            _sha256(row["activation_dry_run_sha256"])
            != activation["dry_run_sha256"]
            or _sha256(row["materialized_set_sha256"])
            != activation["materialized_set_sha256"]
            or _sha256(row["production_posts_sha256"])
            != activation["production_posts_sha256"]
            or _sha256(row["production_article_set_sha256"])
            != activation["production_article_set_sha256"]
            or _sha256(row["production_overlay_receipt_sha256"])
            != activation["production_overlay_receipt_sha256"]
        ):
            _fail("RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID")
        components.append(row)
    if [row["component"] for row in components] != list(READBACK_COMPONENTS):
        _fail("RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID")
    expected_t0 = max(_text(row["observed_at"]) for row in components)
    t0 = _iso_datetime(document["t0"])
    if t0 != expected_t0:
        _fail("RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID")
    return t0


def _strict_number(value: object, *, minimum: float = 0.0) -> float:
    if type(value) not in {int, float}:
        _fail("RAOS_EDITORIAL_V3_GOOGLE_INPUT_INVALID")
    result = float(cast(int | float, value))
    if result < minimum or result != result or result in {float("inf"), -float("inf")}:
        _fail("RAOS_EDITORIAL_V3_GOOGLE_INPUT_INVALID")
    return result


def _validate_google_root(
    document: Mapping[str, object], source: str
) -> tuple[str, str, str]:
    expected = {
        "schema_version",
        "source",
        "site_id",
        "date_from",
        "date_to",
        "retrieved_at",
        "request_sha256",
        "row_count",
        "rows",
    }
    if source == "GA4":
        expected.add("configuration")
    if set(document) != expected:
        _fail("RAOS_EDITORIAL_V3_GOOGLE_INPUT_INVALID")
    if document["schema_version"] != 1 or document["source"] != source:
        _fail("RAOS_EDITORIAL_V3_GOOGLE_INPUT_INVALID")
    _text(document["site_id"], maximum=300)
    date_from = _iso_date(document["date_from"])
    date_to = _iso_date(document["date_to"])
    retrieved_at = _iso_datetime(document["retrieved_at"])
    _sha256(document["request_sha256"])
    rows = _list(document["rows"])
    if date_from > date_to or _nonnegative_integer(document["row_count"]) != len(rows):
        _fail("RAOS_EDITORIAL_V3_GOOGLE_INPUT_INVALID")
    return date_from, date_to, retrieved_at


def summarize_gsc(
    document: Mapping[str, object], portfolio: EditorialPortfolioV3
) -> dict[str, object]:
    date_from, date_to, retrieved_at = _validate_google_root(document, "GSC")
    by_article: dict[str, dict[str, float | int]] = {
        article.article_id: {
            "clicks": 0,
            "impressions": 0,
            "position_weighted_sum": 0.0,
        }
        for article in portfolio.articles
    }
    slug_to_id = {
        article.production_slug: article.article_id for article in portfolio.articles
    }
    target = urlsplit(portfolio.target_origin)
    unmapped_rows = 0
    for raw in _list(document["rows"]):
        row = _mapping(raw)
        if set(row) != {
            "metric_date",
            "query_text",
            "page_url",
            "country_code",
            "device",
            "clicks",
            "impressions",
            "ctr",
            "average_position",
            "request_sha256",
        }:
            _fail("RAOS_EDITORIAL_V3_GSC_ROW_INVALID")
        metric_date = _iso_date(row["metric_date"])
        if not date_from <= metric_date <= date_to:
            _fail("RAOS_EDITORIAL_V3_GSC_ROW_INVALID")
        _text(row["query_text"], maximum=4096)
        page_url = _text(row["page_url"], maximum=4096)
        parsed = urlsplit(page_url)
        country = _text(row["country_code"], maximum=3)
        _text(row["device"], maximum=100)
        clicks = _nonnegative_integer(row["clicks"])
        impressions = _nonnegative_integer(row["impressions"])
        ctr = _strict_number(row["ctr"])
        position = _strict_number(row["average_position"])
        _sha256(row["request_sha256"])
        if (
            len(country) != 3
            or clicks > impressions
            or ctr > 1.0
            or (impressions == 0 and (clicks != 0 or ctr != 0.0))
            or parsed.scheme != "https"
            or parsed.hostname != target.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            _fail("RAOS_EDITORIAL_V3_GSC_ROW_INVALID")
        slug = parsed.path.strip("/")
        article_id = slug_to_id.get(slug)
        if article_id is None:
            unmapped_rows += 1
            continue
        aggregate = by_article[article_id]
        aggregate["clicks"] = cast(int, aggregate["clicks"]) + clicks
        aggregate["impressions"] = cast(int, aggregate["impressions"]) + impressions
        aggregate["position_weighted_sum"] = (
            cast(float, aggregate["position_weighted_sum"]) + position * impressions
        )
    normalized: dict[str, dict[str, object]] = {}
    for article_id, values in by_article.items():
        impressions = cast(int, values["impressions"])
        clicks = cast(int, values["clicks"])
        normalized[article_id] = {
            "state": "OBSERVED",
            "clicks": clicks,
            "impressions": impressions,
            "ctr": clicks / impressions if impressions else "UNAVAILABLE",
            "average_position": (
                cast(float, values["position_weighted_sum"]) / impressions
                if impressions
                else "UNAVAILABLE"
            ),
        }
    return {
        "period": {"date_from": date_from, "date_to": date_to},
        "retrieved_at": retrieved_at,
        "by_article": normalized,
        "unmapped_row_count": unmapped_rows,
        "raw_queries_included": False,
    }


def _name_value_rows(value: object) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in _list(value):
        row = _mapping(raw)
        if set(row) != {"name", "value"}:
            _fail("RAOS_EDITORIAL_V3_GA4_ROW_INVALID")
        name = _text(row["name"], maximum=300)
        cell = _text(row["value"], maximum=4096)
        if name in result:
            _fail("RAOS_EDITORIAL_V3_GA4_ROW_INVALID")
        result[name] = cell
    return result


def summarize_ga4(
    document: Mapping[str, object], portfolio: EditorialPortfolioV3
) -> dict[str, object]:
    date_from, date_to, retrieved_at = _validate_google_root(document, "GA4")
    configuration = _mapping(document["configuration"])
    if set(configuration) != {
        "property_id",
        "property_resource",
        "display_name",
        "time_zone",
        "currency_code",
        "reporting_identity",
        "required_event_custom_dimensions",
        "retrieved_at",
        "response_sha256",
    }:
        _fail("RAOS_EDITORIAL_V3_GA4_CONFIGURATION_INVALID")
    for name in (
        "property_id",
        "property_resource",
        "display_name",
        "time_zone",
        "reporting_identity",
    ):
        _text(configuration[name], maximum=1000)
    if (
        configuration["currency_code"] != "JPY"
        or [
            _text(item, maximum=300)
            for item in _list(configuration["required_event_custom_dimensions"])
        ]
        != list(REQUIRED_GA4_EVENT_DIMENSIONS)
        or _iso_datetime(configuration["retrieved_at"]) != configuration["retrieved_at"]
        or _sha256(configuration["response_sha256"]) != configuration["response_sha256"]
    ):
        _fail("RAOS_EDITORIAL_V3_GA4_CONFIGURATION_INVALID")
    article_ids = {article.article_id for article in portfolio.articles}
    article_by_id = portfolio.article_by_id
    cta_by_id = {
        binding.cta_id: binding
        for article in portfolio.articles
        for binding in article.cta_bindings
    }
    event_counts: dict[str, dict[str, int]] = {
        article_id: defaultdict(int) for article_id in article_ids
    }
    thresholded_rows = 0
    unattributed_event_count = 0
    for raw in _list(document["rows"]):
        row = _mapping(raw)
        if set(row) != {
            "metric_date",
            "dimensions",
            "metrics",
            "grain_sha256",
            "is_thresholded",
            "request_sha256",
        }:
            _fail("RAOS_EDITORIAL_V3_GA4_ROW_INVALID")
        metric_date = _iso_date(row["metric_date"])
        if not date_from <= metric_date <= date_to:
            _fail("RAOS_EDITORIAL_V3_GA4_ROW_INVALID")
        dimensions = _name_value_rows(row["dimensions"])
        metrics = _name_value_rows(row["metrics"])
        _sha256(row["grain_sha256"])
        _sha256(row["request_sha256"])
        if type(row["is_thresholded"]) is not bool:
            _fail("RAOS_EDITORIAL_V3_GA4_ROW_INVALID")
        if row["is_thresholded"]:
            thresholded_rows += 1
        article_id = dimensions.get("article_id")
        event_name = dimensions.get("eventName")
        event_count_raw = metrics.get("eventCount")
        if (
            event_name is None
            or event_count_raw is None
            or re.fullmatch(r"0|[1-9][0-9]*", event_count_raw) is None
        ):
            _fail("RAOS_EDITORIAL_V3_GA4_ROW_INVALID")
        event_count = int(event_count_raw)
        if article_id not in article_ids:
            unattributed_event_count += event_count
            continue
        normalized_article_id = article_id
        if not set(REQUIRED_GA4_EVENT_DIMENSIONS).issubset(dimensions):
            _fail("RAOS_EDITORIAL_V3_GA4_ROW_INVALID")
        article = article_by_id[normalized_article_id]
        if dimensions["snapshot_id"] != article.snapshot_id:
            _fail("RAOS_EDITORIAL_V3_GA4_ROW_INVALID")
        cta_values = tuple(
            dimensions[name]
            for name in ("cta_id", "offer_id", "product_id", "placement")
        )
        cta_unavailable = len(set(cta_values)) == 1 and cta_values[0] in {
            "(not set)",
            "UNAVAILABLE",
        }
        if cta_unavailable:
            if event_name in CTA_SCOPED_GA4_EVENTS:
                _fail("RAOS_EDITORIAL_V3_GA4_ROW_INVALID")
        else:
            binding = cta_by_id.get(dimensions["cta_id"])
            if (
                binding is None
                or binding.article_id != normalized_article_id
                or binding.snapshot_id != dimensions["snapshot_id"]
                or binding.offer_id != dimensions["offer_id"]
                or binding.product_id != dimensions["product_id"]
                or binding.placement != dimensions["placement"]
            ):
                _fail("RAOS_EDITORIAL_V3_GA4_ROW_INVALID")
        event_counts[normalized_article_id][event_name] += event_count
    return {
        "period": {"date_from": date_from, "date_to": date_to},
        "retrieved_at": retrieved_at,
        "configuration": dict(configuration),
        "by_article": {
            article_id: {
                "state": "OBSERVED",
                "events": dict(sorted(counts.items())),
            }
            for article_id, counts in sorted(event_counts.items())
        },
        "thresholded_row_count": thresholded_rows,
        "unattributed_event_count": unattributed_event_count,
    }


def _validate_rakuten_commit(
    document: Mapping[str, object], portfolio: EditorialPortfolioV3
) -> dict[str, object]:
    if (
        document.get("schema") != "RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_V1"
        or document.get("state") != "COMMITTED_OWNER_PRIVATE_RECONCILED"
        or _mapping(document.get("reconciliation")).get("status") != "PASS"
        or document.get("currency") != "JPY"
        or document.get("raw_rows_persisted") is not False
    ):
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_INVALID")
    period = _mapping(document.get("period"))
    if set(period) != {"date_from", "date_to"}:
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_INVALID")
    date_from = _iso_date(period["date_from"])
    date_to = _iso_date(period["date_to"])
    totals = _mapping(document.get("totals_jpy"))
    if set(totals) != set(CANONICAL_STATUSES):
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_INVALID")
    normalized_totals = {
        status: _nonnegative_integer(totals[status]) for status in CANONICAL_STATUSES
    }
    direct = _mapping(document.get("direct_by_article_jpy"))
    expected_ids = {article.article_id for article in portfolio.articles}
    if set(direct) != expected_ids:
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_INVALID")
    normalized_direct: dict[str, dict[str, int]] = {}
    for article_id, raw in direct.items():
        row = _mapping(raw)
        if set(row) != set(CANONICAL_STATUSES):
            _fail("RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_INVALID")
        normalized_direct[article_id] = {
            status: _nonnegative_integer(row[status]) for status in CANONICAL_STATUSES
        }
    attribution = _mapping(document.get("attribution"))
    if set(attribution) != set(ATTRIBUTION_BASES):
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_INVALID")
    expected_attribution_states = {
        "DIRECT": "VERIFIED_MEASUREMENT_ID_MATCH",
        "ESTIMATED": "NOT_PRODUCED_BY_PROVIDER_REPORT_IMPORT",
        "UNATTRIBUTED": "NO_VERIFIED_MEASUREMENT_ID_MATCH",
    }
    normalized_attribution: dict[str, dict[str, object]] = {}
    for basis in ATTRIBUTION_BASES:
        basis_row = _mapping(attribution[basis])
        if (
            set(basis_row) != {"state", "totals_jpy"}
            or basis_row["state"] != expected_attribution_states[basis]
        ):
            _fail("RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_INVALID")
        basis_totals = _mapping(basis_row["totals_jpy"])
        if set(basis_totals) != set(CANONICAL_STATUSES):
            _fail("RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_INVALID")
        normalized_attribution[basis] = {
            "state": basis_row["state"],
            **{
                status: _nonnegative_integer(basis_totals[status])
                for status in CANONICAL_STATUSES
            },
        }
    for status in CANONICAL_STATUSES:
        if sum(
            cast(int, normalized_attribution[basis][status])
            for basis in ATTRIBUTION_BASES
        ) != normalized_totals[status] or sum(
            normalized_direct[article_id][status] for article_id in expected_ids
        ) != cast(int, normalized_attribution["DIRECT"][status]):
            _fail("RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_INVALID")
    unattributed = normalized_attribution["UNATTRIBUTED"]
    return {
        "period": {"date_from": date_from, "date_to": date_to},
        "source_sha256": _sha256(document["source_sha256"]),
        "totals_jpy": normalized_totals,
        "direct_by_article_jpy": normalized_direct,
        "attribution_jpy": normalized_attribution,
        "unattributed_jpy": {
            status: cast(int, unattributed[status]) for status in CANONICAL_STATUSES
        },
    }


def _source_state(value: object | None) -> str:
    return "OBSERVED" if value is not None else "UNAVAILABLE"


def _observation_cohort(period: Mapping[str, str], normalized_t0: str | None) -> str:
    if normalized_t0 is None:
        return "PRE_T0_BASELINE"
    if period.get("date_from") == "UNAVAILABLE":
        return "UNAVAILABLE"
    first_day = date.fromisoformat(_iso_date(period.get("date_from")))
    last_day = date.fromisoformat(_iso_date(period.get("date_to")))
    t0_day = datetime.fromisoformat(normalized_t0.replace("Z", "+00:00")).date()
    if last_day < t0_day:
        return "PRE_T0_BASELINE"
    # Provider aggregates are date-grained.  A row for T0's calendar day can
    # contain observations from before the exact readback timestamp, so only
    # the following day and later form an unambiguously post-T0 cohort.
    if first_day > t0_day:
        return "POST_T0_COHORT"
    return "MIXED_T0_BOUNDARY"


def _freshness_projection(
    source: Mapping[str, object] | None,
    *,
    retrieved_at: object | None = None,
) -> dict[str, object]:
    if source is None:
        return {
            "state": "UNAVAILABLE",
            "period": {"date_from": "UNAVAILABLE", "date_to": "UNAVAILABLE"},
            "retrieved_at": "UNAVAILABLE",
            "observed_through": "UNAVAILABLE",
        }
    period = _mapping(source["period"])
    date_from = _iso_date(period["date_from"])
    date_to = _iso_date(period["date_to"])
    return {
        "state": "OBSERVED",
        "period": {"date_from": date_from, "date_to": date_to},
        "retrieved_at": (
            _iso_datetime(retrieved_at) if retrieved_at is not None else "UNAVAILABLE"
        ),
        "observed_through": date_to,
    }


def build_baseline_report(
    *,
    portfolio: EditorialPortfolioV3,
    rakuten_commit: Mapping[str, object] | None,
    cost_input: Mapping[str, object] | None,
    gsc_input: Mapping[str, object] | None,
    ga4_input: Mapping[str, object] | None,
    t0_receipt: Mapping[str, object] | None,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    rakuten = (
        _validate_rakuten_commit(rakuten_commit, portfolio)
        if rakuten_commit is not None
        else None
    )
    costs = (
        validate_cost_input(cost_input, portfolio) if cost_input is not None else None
    )
    gsc = summarize_gsc(gsc_input, portfolio) if gsc_input is not None else None
    ga4 = summarize_ga4(ga4_input, portfolio) if ga4_input is not None else None
    normalized_t0 = (
        validate_t0_receipt(t0_receipt, portfolio) if t0_receipt is not None else None
    )
    now = (generated_at or datetime.now(UTC)).astimezone(UTC)
    periods = [
        cast(Mapping[str, str], source["period"])
        for source in (rakuten, costs, gsc, ga4)
        if source is not None
    ]
    period_pairs = {(period["date_from"], period["date_to"]) for period in periods}
    period_alignment = (
        "PASS"
        if periods and len(period_pairs) == 1
        else "UNAVAILABLE"
        if not periods
        else "MISMATCH"
    )
    report_period = (
        {"date_from": periods[0]["date_from"], "date_to": periods[0]["date_to"]}
        if period_alignment == "PASS"
        else {"date_from": "UNAVAILABLE", "date_to": "UNAVAILABLE"}
    )
    complete_calendar_month = False
    if period_alignment == "PASS":
        first_day = date.fromisoformat(periods[0]["date_from"])
        last_day = date.fromisoformat(periods[0]["date_to"])
        complete_calendar_month = (
            first_day.day == 1
            and first_day.year == last_day.year
            and first_day.month == last_day.month
            and last_day.day == monthrange(last_day.year, last_day.month)[1]
        )
    cohort = _observation_cohort(report_period, normalized_t0)
    source_freshness = {
        "rakuten": _freshness_projection(rakuten),
        "cost": _freshness_projection(costs),
        "gsc": _freshness_projection(
            gsc, retrieved_at=gsc["retrieved_at"] if gsc is not None else None
        ),
        "ga4": _freshness_projection(
            ga4, retrieved_at=ga4["retrieved_at"] if ga4 is not None else None
        ),
    }
    program_attribution = (
        cast(dict[str, dict[str, object]], rakuten["attribution_jpy"])
        if rakuten is not None
        else None
    )

    article_rows: list[dict[str, object]] = []
    total_external_cost = 0
    total_human_cost = 0
    for article in portfolio.articles:
        direct = (
            cast(dict[str, dict[str, int]], rakuten["direct_by_article_jpy"])[
                article.article_id
            ]
            if rakuten is not None
            else None
        )
        cost_row = (
            cast(dict[str, dict[str, int | str]], costs["articles"])[article.article_id]
            if costs is not None
            else None
        )
        if cost_row is not None and costs is not None:
            minutes = cast(int, cost_row["editorial_minutes"])
            external_cost = cast(int, cost_row["variable_external_cost_jpy"])
            hourly_cost = cast(int, costs["approved_hourly_cost_jpy"])
            human_cost = (minutes * hourly_cost + 59) // 60
            total_external_cost += external_cost
            total_human_cost += human_cost
            cost_projection: dict[str, object] = {
                "state": "OWNER_ATTESTED",
                "editorial_minutes": minutes,
                "approved_hourly_cost_jpy": hourly_cost,
                "human_cost_jpy": human_cost,
                "human_cost_rounding": "CEILING_TO_ONE_JPY",
                "variable_external_cost_jpy": external_cost,
            }
        else:
            human_cost = 0
            external_cost = 0
            cost_projection = {
                "state": "UNAVAILABLE",
                "reason": "OWNER_ATTESTED_COST_INPUT_MISSING",
            }
        if direct is not None and cost_row is not None and period_alignment == "PASS":
            contribution: dict[str, object] = {
                "state": "AVAILABLE_DIRECT_BASIS",
                "value_jpy": direct["CONFIRMED"] - external_cost - human_cost,
                "formula": (
                    "direct_confirmed_reward_jpy - variable_external_cost_jpy - "
                    "human_cost_jpy"
                ),
            }
        else:
            contribution = {
                "state": "UNAVAILABLE",
                "reason": (
                    "PERIOD_MISMATCH"
                    if period_alignment == "MISMATCH"
                    else "RECONCILED_REWARD_OR_OWNER_COST_MISSING"
                ),
            }
        direct_projection: dict[str, object] = (
            {"state": "RECONCILED", **direct}
            if direct is not None
            else {"state": "UNAVAILABLE"}
        )
        article_attribution: dict[str, dict[str, object]] = (
            {
                "DIRECT": direct_projection,
                "ESTIMATED": {
                    "state": "NOT_PRODUCED_BY_PROVIDER_REPORT_IMPORT",
                    **{status: "UNAVAILABLE" for status in CANONICAL_STATUSES},
                },
                "UNATTRIBUTED": {
                    "state": "NOT_ALLOCATED_TO_ARTICLE",
                    **{status: "UNAVAILABLE" for status in CANONICAL_STATUSES},
                },
            }
            if rakuten is not None
            else {basis: {"state": "UNAVAILABLE"} for basis in ATTRIBUTION_BASES}
        )
        article_data_quality = {
            "missing_is_zero": False,
            "gsc": _source_state(gsc),
            "ga4": _source_state(ga4),
            "rakuten": _source_state(rakuten),
            "cost": _source_state(costs),
            "unattributed_reward_allocated_to_article": False,
            "estimated_promoted_to_direct": False,
        }
        article_rows.append(
            {
                "article_id": article.article_id,
                "article_code": article.article_code,
                "production_slug": article.production_slug,
                "cluster_id": article.cluster_id,
                "gsc": (
                    cast(Mapping[str, object], gsc["by_article"])[article.article_id]
                    if gsc is not None
                    else {"state": "UNAVAILABLE"}
                ),
                "ga4": (
                    cast(Mapping[str, object], ga4["by_article"])[article.article_id]
                    if ga4 is not None
                    else {"state": "UNAVAILABLE"}
                ),
                "rakuten_direct_jpy": direct_projection,
                "rakuten_attribution_jpy": article_attribution,
                "cost": cost_projection,
                "confirmed_contribution_profit_jpy": contribution,
                "freshness": source_freshness,
                "attribution_basis": {
                    "rakuten": (
                        "DIRECT_VERIFIED_MEASUREMENT_ID_MATCH"
                        if rakuten is not None
                        else "UNAVAILABLE"
                    ),
                    "confirmed_contribution_profit": (
                        "DIRECT_CONFIRMED_REWARD_LESS_OWNER_ATTESTED_COST"
                        if contribution.get("state") == "AVAILABLE_DIRECT_BASIS"
                        else "UNAVAILABLE"
                    ),
                },
                "data_quality": article_data_quality,
            }
        )

    if rakuten is not None and costs is not None and period_alignment == "PASS":
        confirmed_reward = cast(dict[str, int], rakuten["totals_jpy"])["CONFIRMED"]
        north_star: dict[str, object] = {
            "state": "AVAILABLE_PROGRAM_BASIS",
            "metric": "CONFIRMED_CONTRIBUTION_PROFIT_JPY_ALIGNED_PERIOD",
            "value_jpy": confirmed_reward - total_external_cost - total_human_cost,
            "confirmed_reward_jpy": confirmed_reward,
            "variable_external_cost_jpy": total_external_cost,
            "human_cost_jpy": total_human_cost,
            "formula": (
                "confirmed_reward_jpy - variable_external_cost_jpy - human_cost_jpy"
            ),
            "unattributed_reward_included_at_program_level": True,
            "unattributed_reward_allocated_to_articles": False,
            "monthly_north_star_eligible": complete_calendar_month,
        }
    else:
        north_star = {
            "state": "UNAVAILABLE",
            "reason": (
                "PERIOD_MISMATCH"
                if period_alignment == "MISMATCH"
                else "RECONCILED_REWARD_OR_OWNER_COST_MISSING"
            ),
        }
    return {
        "schema": "RAOS_EDITORIAL_V3_ACTUAL_BASELINE_REPORT_V1",
        "version": "1.0.0",
        "classification": "OWNER_PRIVATE_FINANCIAL_AND_PROVIDER_DATA",
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "t0": normalized_t0 or "UNAVAILABLE",
        "t0_receipt_sha256": (
            sha256_bytes(canonical_json_bytes(t0_receipt))
            if t0_receipt is not None
            else "UNAVAILABLE"
        ),
        "cohort": cohort,
        "period": report_period,
        "period_alignment": period_alignment,
        "period_kind": (
            "COMPLETE_CALENDAR_MONTH"
            if complete_calendar_month
            else "PARTIAL_OR_NON_MONTHLY_BASELINE"
            if period_alignment == "PASS"
            else "UNAVAILABLE"
        ),
        "sources": {
            "rakuten": _source_state(rakuten),
            "cost": _source_state(costs),
            "gsc": _source_state(gsc),
            "ga4": _source_state(ga4),
            "t0_receipt": _source_state(t0_receipt),
        },
        "freshness": {
            "generated_at": now.isoformat().replace("+00:00", "Z"),
            "sources": source_freshness,
        },
        "attribution_basis": {
            "program_north_star": (
                "RECONCILED_PROGRAM_TOTAL_INCLUDES_UNATTRIBUTED"
                if rakuten is not None
                else "UNAVAILABLE"
            ),
            "article_profit": "DIRECT_VERIFIED_MEASUREMENT_ID_ONLY",
            "estimated_promoted_to_direct": False,
        },
        "north_star": north_star,
        "rakuten_attribution_jpy": (
            program_attribution
            if program_attribution is not None
            else {basis: {"state": "UNAVAILABLE"} for basis in ATTRIBUTION_BASES}
        ),
        "unattributed_reward_jpy": (
            {
                "state": "RECONCILED_NOT_ALLOCATED",
                **cast(dict[str, int], rakuten["unattributed_jpy"]),
            }
            if rakuten is not None
            else {"state": "UNAVAILABLE"}
        ),
        "articles": article_rows,
        "data_quality": {
            "missing_is_zero": False,
            "unattributed_article_allocation": False,
            "estimated_promoted_to_direct": False,
            "gsc_raw_queries_in_report": False,
            "rakuten_raw_rows_in_report": False,
            "ga4_thresholded_row_count": (
                ga4["thresholded_row_count"] if ga4 is not None else "UNAVAILABLE"
            ),
            "gsc_unmapped_row_count": (
                gsc["unmapped_row_count"] if gsc is not None else "UNAVAILABLE"
            ),
        },
    }


def candidate_query_demand_template() -> dict[str, object]:
    """Return an owner-private input skeleton for candidate-specific demand.

    Article/page totals are deliberately not accepted as candidate demand.  The
    query-cluster digest identifies an owner-private query definition without
    copying raw search queries into the baseline or follow-up report.
    """

    return {
        "schema": CANDIDATE_QUERY_DEMAND_SCHEMA,
        "version": "1.0.0",
        "candidate_id": NEW_ARTICLE_CANDIDATE_ID,
        "source": "GSC",
        "aggregation_basis": CANDIDATE_QUERY_DEMAND_BASIS,
        "period": {"date_from": None, "date_to": None},
        "retrieved_at": None,
        "request_sha256": None,
        "query_cluster_sha256": None,
        "impressions": None,
        "clicks": None,
        "raw_queries_included": False,
        "article_totals_reused": False,
    }


def _validate_candidate_query_demand(
    document: Mapping[str, object],
) -> dict[str, object]:
    if set(document) != {
        "schema",
        "version",
        "candidate_id",
        "source",
        "aggregation_basis",
        "period",
        "retrieved_at",
        "request_sha256",
        "query_cluster_sha256",
        "impressions",
        "clicks",
        "raw_queries_included",
        "article_totals_reused",
    }:
        _fail("RAOS_EDITORIAL_V3_CANDIDATE_QUERY_DEMAND_INVALID")
    if (
        document["schema"] != CANDIDATE_QUERY_DEMAND_SCHEMA
        or document["version"] != "1.0.0"
        or document["candidate_id"] != NEW_ARTICLE_CANDIDATE_ID
        or document["source"] != "GSC"
        or document["aggregation_basis"] != CANDIDATE_QUERY_DEMAND_BASIS
        or document["raw_queries_included"] is not False
        or document["article_totals_reused"] is not False
    ):
        _fail("RAOS_EDITORIAL_V3_CANDIDATE_QUERY_DEMAND_INVALID")
    period = _mapping(document["period"])
    if set(period) != {"date_from", "date_to"}:
        _fail("RAOS_EDITORIAL_V3_CANDIDATE_QUERY_DEMAND_INVALID")
    date_from = _iso_date(period["date_from"])
    date_to = _iso_date(period["date_to"])
    impressions = _nonnegative_integer(document["impressions"])
    clicks = _nonnegative_integer(document["clicks"])
    if date_from > date_to or clicks > impressions:
        _fail("RAOS_EDITORIAL_V3_CANDIDATE_QUERY_DEMAND_INVALID")
    return {
        "state": "OBSERVED_INDEPENDENT_QUERY_CLUSTER",
        "period": {"date_from": date_from, "date_to": date_to},
        "retrieved_at": _iso_datetime(document["retrieved_at"]),
        "request_sha256": _sha256(document["request_sha256"]),
        "query_cluster_sha256": _sha256(document["query_cluster_sha256"]),
        "impressions": impressions,
        "clicks": clicks,
        "raw_queries_included": False,
        "article_totals_reused": False,
    }


def _coverage_days(
    *, date_from: date, date_to: date, t0_day: date, as_of_date: date
) -> int:
    coverage_start = max(date_from, t0_day + timedelta(days=1))
    coverage_end = min(date_to, as_of_date)
    return max(0, (coverage_end - coverage_start).days + 1)


def evaluate_followups(
    *,
    baseline: Mapping[str, object],
    baseline_sha256: str,
    portfolio: EditorialPortfolioV3,
    as_of: str,
    candidate_query_demand: Mapping[str, object] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    if baseline.get("schema") != "RAOS_EDITORIAL_V3_ACTUAL_BASELINE_REPORT_V1":
        _fail("RAOS_EDITORIAL_V3_BASELINE_REPORT_INVALID")
    source_sha256 = _sha256(baseline_sha256)
    if _sha256(baseline.get("t0_receipt_sha256")) != baseline.get("t0_receipt_sha256"):
        _fail("RAOS_EDITORIAL_V3_BASELINE_REPORT_INVALID")
    t0 = baseline.get("t0")
    if t0 == "UNAVAILABLE":
        _fail("RAOS_EDITORIAL_V3_FOLLOWUP_T0_UNAVAILABLE")
    normalized_t0 = _iso_datetime(t0)
    t0_time = datetime.fromisoformat(normalized_t0.replace("Z", "+00:00"))
    as_of_date = date.fromisoformat(_iso_date(as_of))
    now = (generated_at or datetime.now(UTC)).astimezone(UTC)
    if as_of_date > now.date() or as_of_date < t0_time.date():
        _fail("RAOS_EDITORIAL_V3_FOLLOWUP_DATE_INVALID")
    elapsed_days = (as_of_date - t0_time.date()).days
    period = _mapping(baseline.get("period"))
    if set(period) != {"date_from", "date_to"}:
        _fail("RAOS_EDITORIAL_V3_BASELINE_REPORT_INVALID")
    period_date_from = period.get("date_from")
    period_date_to = period.get("date_to")
    coverage_days = 0
    if period_date_from != "UNAVAILABLE" and period_date_to != "UNAVAILABLE":
        coverage_days = _coverage_days(
            date_from=date.fromisoformat(_iso_date(period_date_from)),
            date_to=date.fromisoformat(_iso_date(period_date_to)),
            t0_day=t0_time.date(),
            as_of_date=as_of_date,
        )
    elif period_date_from != "UNAVAILABLE" or period_date_to != "UNAVAILABLE":
        _fail("RAOS_EDITORIAL_V3_BASELINE_REPORT_INVALID")
    cohort = baseline.get("cohort")
    if cohort not in {
        "POST_T0_COHORT",
        "MIXED_T0_BOUNDARY",
        "PRE_T0_BASELINE",
        "UNAVAILABLE",
        # Accepted only as a legacy mixed/unknown value; it is never eligible.
        "POST_T0_OR_MIXED_REVIEW_REQUIRED",
    }:
        _fail("RAOS_EDITORIAL_V3_BASELINE_REPORT_INVALID")
    post_t0_cohort = cohort == "POST_T0_COHORT"

    candidate_article = portfolio.article_by_id.get(NEW_ARTICLE_SOURCE_ID)
    if candidate_article is None:
        _fail("RAOS_EDITORIAL_V3_CANDIDATE_SOURCE_INVALID")
    article_rows = {
        _text(_mapping(raw).get("article_id")): _mapping(raw)
        for raw in _list(baseline.get("articles"))
    }
    if set(article_rows) != set(portfolio.article_by_id):
        _fail("RAOS_EDITORIAL_V3_BASELINE_REPORT_INVALID")
    source = article_rows[NEW_ARTICLE_SOURCE_ID]
    direct = _mapping(source.get("rakuten_direct_jpy"))
    demand = (
        _validate_candidate_query_demand(candidate_query_demand)
        if candidate_query_demand is not None
        else None
    )
    demand_coverage_days = 0
    independent_query_demand_confirmed = False
    if demand is not None:
        demand_period = _mapping(demand["period"])
        demand_date_from = date.fromisoformat(_iso_date(demand_period["date_from"]))
        demand_date_to = date.fromisoformat(_iso_date(demand_period["date_to"]))
        demand_coverage_days = _coverage_days(
            date_from=demand_date_from,
            date_to=demand_date_to,
            t0_day=t0_time.date(),
            as_of_date=as_of_date,
        )
        independent_query_demand_confirmed = (
            demand_date_from > t0_time.date() and demand_date_to <= as_of_date
        )
    impressions = cast(int, demand["impressions"]) if demand is not None else None
    clicks = cast(int, demand["clicks"]) if demand is not None else None
    confirmed_reward = (
        _nonnegative_integer(direct["CONFIRMED"])
        if post_t0_cohort
        and direct.get("state") == "RECONCILED"
        and "CONFIRMED" in direct
        else None
    )
    conditions = {
        "post_t0_cohort": post_t0_cohort,
        "independent_query_demand_confirmed": independent_query_demand_confirmed,
        "observation_days_ge_28": (
            elapsed_days >= 28
            and demand_coverage_days >= 28
            and independent_query_demand_confirmed
        ),
        "impressions_ge_200": (
            independent_query_demand_confirmed
            and impressions is not None
            and impressions >= 200
        ),
        "measurable_clicks": (
            independent_query_demand_confirmed and clicks is not None and clicks > 0
        ),
        "mature_confirmed_result": (
            confirmed_reward is not None and confirmed_reward > 0
        ),
    }
    eligible = all(conditions.values())

    def review(day: int, areas: Sequence[str]) -> dict[str, object]:
        due = elapsed_days >= day
        status = (
            "NOT_DUE"
            if not due
            else "HUMAN_REVIEW_REQUIRED"
            if post_t0_cohort
            else "BLOCKED_NON_POST_T0_COHORT"
        )
        return {
            "day": day,
            "due": due,
            "status": status,
            "data_cohort": cohort,
            "data_eligible": post_t0_cohort,
            "review_areas": list(areas),
            "automatic_pass": False,
            "automatic_publication": False,
        }

    return {
        "schema": "RAOS_EDITORIAL_V3_FOLLOWUP_EVALUATION_V1",
        "version": "1.0.0",
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "baseline_sha256": source_sha256,
        "t0": normalized_t0,
        "as_of": as_of_date.isoformat(),
        "elapsed_days": elapsed_days,
        "actual_data_coverage_days_after_t0": coverage_days,
        "data_cohort": cohort,
        "reviews": {
            "day_30": review(
                30,
                ("indexing", "search_intent", "cta", "generated_reward"),
            ),
            "day_90": review(
                90,
                ("confirmed_reward", "contribution_profit", "gate_readiness"),
            ),
        },
        "new_article_candidate_gate": {
            "candidate_id": NEW_ARTICLE_CANDIDATE_ID,
            "source_article_id": candidate_article.article_id,
            "source_article_code": candidate_article.article_code,
            "observations": {
                "independent_query_demand": (
                    demand if demand is not None else {"state": "UNAVAILABLE"}
                ),
                "query_demand_coverage_days_after_t0": demand_coverage_days,
                "impressions": impressions
                if impressions is not None
                else "UNAVAILABLE",
                "clicks": clicks if clicks is not None else "UNAVAILABLE",
                "direct_confirmed_reward_jpy": (
                    confirmed_reward if confirmed_reward is not None else "UNAVAILABLE"
                ),
            },
            "conditions": conditions,
            "status": ("ELIGIBLE_FOR_HUMAN_PROPOSAL" if eligible else "NOT_ELIGIBLE"),
            "automatic_article_creation": False,
            "automatic_pass": False,
            "automatic_publication": False,
        },
    }


def render_baseline_html(report: Mapping[str, object]) -> bytes:
    if report.get("schema") != "RAOS_EDITORIAL_V3_ACTUAL_BASELINE_REPORT_V1":
        _fail("RAOS_EDITORIAL_V3_BASELINE_REPORT_INVALID")
    rows: list[str] = []
    for raw in _list(report.get("articles")):
        row = _mapping(raw)
        contribution = _mapping(row.get("confirmed_contribution_profit_jpy"))
        value = (
            str(contribution["value_jpy"])
            if contribution.get("state") == "AVAILABLE_DIRECT_BASIS"
            else "UNAVAILABLE"
        )
        gsc = _mapping(row.get("gsc"))
        ga4 = _mapping(row.get("ga4"))
        direct = _mapping(row.get("rakuten_direct_jpy"))
        article_attribution_value = row.get("rakuten_attribution_jpy")
        article_attribution = _mapping(
            article_attribution_value if article_attribution_value is not None else {}
        )
        estimated_value = article_attribution.get("ESTIMATED")
        estimated = _mapping(estimated_value if estimated_value is not None else {})
        unattributed_value = article_attribution.get("UNATTRIBUTED")
        unattributed = _mapping(
            unattributed_value if unattributed_value is not None else {}
        )
        cost = _mapping(row.get("cost"))
        freshness_value = row.get("freshness")
        freshness = _mapping(freshness_value if freshness_value is not None else {})
        freshness_sources = "; ".join(
            f"{name}={_mapping(source).get('observed_through', 'UNAVAILABLE')}"
            for name, source in sorted(freshness.items())
        )
        attribution_basis_value = row.get("attribution_basis")
        attribution_basis = _mapping(
            attribution_basis_value if attribution_basis_value is not None else {}
        )
        data_quality_value = row.get("data_quality")
        data_quality = _mapping(
            data_quality_value if data_quality_value is not None else {}
        )
        events = (
            ", ".join(
                f"{_text(name, maximum=300)}={_nonnegative_integer(count)}"
                for name, count in sorted(_mapping(ga4.get("events")).items())
            )
            or "OBSERVED_NONE"
            if ga4.get("state") == "OBSERVED"
            else "UNAVAILABLE"
        )
        rows.append(
            "<tr>"
            f"<td>{escape(_text(row.get('article_code')))}</td>"
            f"<td>{escape(_text(row.get('production_slug')))}</td>"
            f"<td>{escape(str(gsc.get('impressions', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(str(gsc.get('clicks', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(str(gsc.get('ctr', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(str(gsc.get('average_position', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(events)}</td>"
            f"<td>{escape(str(direct.get('PENDING', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(str(direct.get('CONFIRMED', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(str(direct.get('CANCELLED', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(str(estimated.get('state', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(str(unattributed.get('state', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(str(cost.get('editorial_minutes', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(str(cost.get('variable_external_cost_jpy', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(str(cost.get('human_cost_jpy', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(freshness_sources)}</td>"
            f"<td>{escape(str(attribution_basis.get('rakuten', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(json.dumps(data_quality, ensure_ascii=False, sort_keys=True))}</td>"
            f"<td>{escape(value)}</td>"
            "</tr>"
        )
    north_star = _mapping(report.get("north_star"))
    north_star_value = (
        str(north_star["value_jpy"])
        if north_star.get("state") == "AVAILABLE_PROGRAM_BASIS"
        else "UNAVAILABLE"
    )
    program_attribution_value = report.get("rakuten_attribution_jpy")
    program_attribution = _mapping(
        program_attribution_value if program_attribution_value is not None else {}
    )
    attribution_rows: list[str] = []
    for basis in ATTRIBUTION_BASES:
        basis_value = program_attribution.get(basis)
        basis_row = _mapping(basis_value if basis_value is not None else {})
        attribution_rows.append(
            "<tr>"
            f"<td>{escape(basis)}</td>"
            f"<td>{escape(str(basis_row.get('state', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(str(basis_row.get('PENDING', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(str(basis_row.get('CONFIRMED', 'UNAVAILABLE')))}</td>"
            f"<td>{escape(str(basis_row.get('CANCELLED', 'UNAVAILABLE')))}</td>"
            "</tr>"
        )
    report_freshness_value = report.get("freshness")
    report_freshness = _mapping(
        report_freshness_value if report_freshness_value is not None else {}
    )
    report_data_quality_value = report.get("data_quality")
    report_data_quality = _mapping(
        report_data_quality_value if report_data_quality_value is not None else {}
    )
    report_attribution_basis_value = report.get("attribution_basis")
    report_attribution_basis = _mapping(
        report_attribution_basis_value
        if report_attribution_basis_value is not None
        else {}
    )
    html = "".join(
        (
            '<!doctype html><html lang="ja"><meta charset="utf-8">',
            '<meta name="robots" content="noindex,nofollow">',
            "<title>Editorial V3 owner-private baseline</title>",
            "<style>body{font-family:sans-serif;max-width:1200px;margin:2rem auto;",
            "padding:0 1rem;overflow-wrap:anywhere}table{border-collapse:collapse;",
            "width:100%;display:block;overflow-x:auto}",
            "th,td{border:1px solid #bbb;padding:.5rem;text-align:left}</style>",
            "<h1>Editorial V3 実データ基準値</h1>",
            f"<p>期間: {escape(str(_mapping(report.get('period')).get('date_from')))}",
            f"〜{escape(str(_mapping(report.get('period')).get('date_to')))}</p>",
            f"<p>T0: {escape(str(report.get('t0')))}</p>",
            f"<p>cohort: {escape(str(report.get('cohort')))}</p>",
            f"<p>freshness: {escape(json.dumps(report_freshness, ensure_ascii=False, sort_keys=True))}</p>",
            f"<p>attribution basis: {escape(json.dumps(report_attribution_basis, ensure_ascii=False, sort_keys=True))}</p>",
            f"<p>data quality: {escape(json.dumps(report_data_quality, ensure_ascii=False, sort_keys=True))}</p>",
            f"<p>確定貢献利益（全体）: {escape(north_star_value)} 円</p>",
            "<h2>楽天成果（プログラム全体・帰属別）</h2>",
            "<table><thead><tr><th>帰属</th><th>basis state</th>",
            "<th>pending</th><th>confirmed</th><th>cancelled</th>",
            "</tr></thead><tbody>",
            "".join(attribution_rows),
            "</tbody></table>",
            "<h2>記事別</h2>",
            "<table><thead><tr><th>記事</th><th>slug</th><th>GSC表示</th>",
            "<th>GSCクリック</th><th>GSC CTR</th><th>GSC平均順位</th>",
            "<th>GA4各イベント</th><th>楽天Direct pending</th>",
            "<th>楽天Direct confirmed</th><th>楽天Direct cancelled</th>",
            "<th>楽天Estimated</th><th>楽天Unattributed</th>",
            "<th>作業分</th><th>外部費</th><th>人件費</th><th>freshness</th>",
            "<th>attribution basis</th><th>data quality</th>",
            "<th>確定貢献利益（Direct）</th></tr></thead><tbody>",
            "".join(rows),
            "</tbody></table>",
            "<p>未帰属成果は記事へ配賦せず、欠損値は0ではなくUNAVAILABLEです。</p>",
            "</html>",
        )
    )
    return html.encode("utf-8")


__all__ = [
    "EditorialEconomicsV3Failure",
    "bind_rakuten_profile",
    "build_baseline_report",
    "candidate_query_demand_template",
    "canonical_json_bytes",
    "commit_rakuten_report",
    "cost_input_template",
    "detect_rakuten_sample",
    "ensure_private_root",
    "establish_t0_receipt",
    "evaluate_followups",
    "parse_rakuten_report",
    "private_path",
    "production_readback_template",
    "rakuten_binding_template",
    "read_private_bytes",
    "read_private_json",
    "render_baseline_html",
    "sha256_bytes",
    "summarize_ga4",
    "summarize_gsc",
    "validate_cost_input",
    "validate_t0_receipt",
    "write_private_bytes",
    "write_private_json",
]
