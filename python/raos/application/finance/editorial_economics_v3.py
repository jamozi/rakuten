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
from datetime import UTC, date, datetime
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
CANDIDATE_QUERY_DEMAND_SCHEMA: Final = "RAOS_EDITORIAL_V3_CANDIDATE_QUERY_DEMAND_V1"
CANDIDATE_QUERY_DEMAND_BASIS: Final = (
    "GSC_QUERY_DIMENSION_CANDIDATE_CLUSTER_NOT_ARTICLE_TOTAL"
)
RAKUTEN_ACTIVATION_DRY_RUN_SCHEMA: Final = (
    "RAOS_EDITORIAL_V3_RAKUTEN_MEASUREMENT_DRY_RUN_V3"
)
RAKUTEN_BIND_REQUEST_SCHEMA: Final = "RAOS_EDITORIAL_V3_RAKUTEN_BIND_REQUEST_V2"
RAKUTEN_PARSER_PROFILE_SCHEMA: Final = "RAOS_EDITORIAL_V3_RAKUTEN_PARSER_PROFILE_V2"
RAKUTEN_REPORT_DRY_RUN_SCHEMA: Final = "RAOS_EDITORIAL_V3_RAKUTEN_DRY_RUN_V2"
RAKUTEN_REPORT_COMMIT_SCHEMA: Final = "RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_V2"
RAKUTEN_REPORT_DRY_RUN_KEYS: Final = frozenset(
    {
        "schema",
        "version",
        "state",
        "source_sha256",
        "profile_sha256",
        "parser_version",
        "period",
        "row_count",
        "currency",
        "totals_jpy",
        "attribution",
        "direct_by_article_jpy",
        "direct_by_provider_slot_jpy",
        "unmatched_measurement_row_count",
        "raw_rows_persisted",
        "commit_gate",
    }
)
PRODUCTION_READBACK_INPUT_SCHEMA: Final = (
    "RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INPUT_V4"
)
T0_RECEIPT_SCHEMA: Final = "RAOS_EDITORIAL_V3_T0_RECEIPT_V4"
TRUSTED_T0_EVIDENCE_REQUIRED: Final = "RAOS_EDITORIAL_V3_TRUSTED_T0_EVIDENCE_REQUIRED"
BASELINE_INCOMPLETE_STATE: Final = "INCOMPLETE_TRUSTED_T0_EVIDENCE_REQUIRED"
PUBLIC_READBACK_RECEIPT_SCHEMA: Final = "RAOS_WORDPRESS_PUBLIC_READBACK_RECEIPT_V1"
PROVIDER_SLOT_COUNT: Final = 20
INTERNAL_CTA_IDENTITY_COUNT: Final = 74
LIVE_LINK_COUNT: Final = 74
PUBLICATION_DOCUMENT_COUNT: Final = 13


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


def _csv_sections(
    content: bytes, *, encoding: str, delimiter_name: str
) -> tuple[int, list[dict[str, object]]]:
    delimiter = DELIMITERS.get(delimiter_name)
    if delimiter is None:
        _fail("RAOS_EDITORIAL_V3_CSV_DELIMITER_UNSUPPORTED")
    try:
        reader = csv.reader(
            io.StringIO(_decode_csv(content, encoding), newline=""),
            delimiter=delimiter,
            strict=True,
        )
        physical_rows = [tuple(row) for row in reader]
    except csv.Error, UnicodeError:
        _fail("RAOS_EDITORIAL_V3_CSV_INVALID")
    if not 2 <= len(physical_rows) <= MAX_ROWS + 1:
        _fail("RAOS_EDITORIAL_V3_CSV_CARDINALITY_INVALID")
    if any(
        len(row) > MAX_COLUMNS
        or any(len(cell) > MAX_CELL_LENGTH or "\x00" in cell for cell in row)
        for row in physical_rows
    ):
        _fail("RAOS_EDITORIAL_V3_CSV_CELL_INVALID")

    groups: list[tuple[int, list[tuple[str, ...]]]] = []
    current_start: int | None = None
    current_rows: list[tuple[str, ...]] = []
    for row_index, row in enumerate(physical_rows):
        is_blank = not row or all(not cell.strip() for cell in row)
        if is_blank:
            if current_start is not None:
                groups.append((current_start, current_rows))
                current_start = None
                current_rows = []
            continue
        if current_start is None:
            current_start = row_index
        current_rows.append(row)
    if current_start is not None:
        groups.append((current_start, current_rows))

    sections: list[dict[str, object]] = []
    for header_row_index, group in groups:
        # A single non-blank line is explanatory material, not a report table.
        if len(group) < 2:
            continue
        header = group[0]
        width = len(header)
        if width < 2 or any(len(row) != width for row in group):
            _fail("RAOS_EDITORIAL_V3_CSV_SECTION_INVALID")
        # Rakuten's order export can include a rectangular summary block whose
        # first row represents merged headings with empty CSV cells.  It is not
        # a bindable detail table, so ignore that block while retaining strict
        # validation for every non-empty candidate header.
        if any(not cell for cell in header):
            continue
        if len(set(header)) != len(header) or any(
            cell != cell.strip()
            or len(cell) > 300
            or "\x00" in cell
            or any(ord(character) < 32 for character in cell)
            for cell in header
        ):
            _fail("RAOS_EDITORIAL_V3_CSV_HEADER_INVALID")
        section_index = len(sections)
        section_rows = [list(row) for row in group]
        sections.append(
            {
                "section_index": section_index,
                "header_row_index": header_row_index,
                "column_count": width,
                "header": header,
                "rows": group[1:],
                "section_sha256": sha256_bytes(
                    canonical_json_bytes(
                        {
                            "section_index": section_index,
                            "header_row_index": header_row_index,
                            "rows": section_rows,
                        }
                    )
                ),
            }
        )
    if not sections:
        _fail("RAOS_EDITORIAL_V3_CSV_SECTION_INVALID")
    return len(physical_rows), sections


def detect_rakuten_sample(
    content: bytes, *, encoding: str, delimiter_name: str
) -> dict[str, object]:
    physical_row_count, sections = _csv_sections(
        content, encoding=encoding, delimiter_name=delimiter_name
    )
    return {
        "schema": "RAOS_EDITORIAL_V3_RAKUTEN_SCHEMA_DETECTION_V2",
        "version": "2.0.0",
        "state": "RECTANGULAR_SECTIONS_DETECTED_PROFILE_NOT_BOUND",
        "source_sha256": sha256_bytes(content),
        "encoding": encoding,
        "delimiter": delimiter_name,
        "physical_row_count": physical_row_count,
        "sections": [
            {
                "section_index": section["section_index"],
                "header_row_index": section["header_row_index"],
                "column_count": section["column_count"],
                "data_row_count": len(cast(list[tuple[str, ...]], section["rows"])),
                "header": list(cast(tuple[str, ...], section["header"])),
                "section_sha256": section["section_sha256"],
            }
            for section in sections
        ],
        "owner_attestation_required": True,
        "live_parser_enabled": False,
    }


def rakuten_binding_template(
    detection: Mapping[str, object],
    *,
    detection_sha256: str,
    portfolio: EditorialPortfolioV3,
) -> dict[str, object]:
    _validate_detection(detection)
    return {
        "schema": RAKUTEN_BIND_REQUEST_SCHEMA,
        "version": "2.0.0",
        "detection_receipt_sha256": detection_sha256,
        "detection_source_sha256": detection["source_sha256"],
        "owner_verified_sanitized_real_sample": False,
        "provider_measurement_id_echo_verified_in_provider_report": False,
        "section_selection": {
            "section_index": None,
            "header_row_index": None,
            "section_sha256": None,
        },
        "provider_slot_count": PROVIDER_SLOT_COUNT,
        "provider_measurement_id_count": PROVIDER_SLOT_COUNT,
        "provider_slots": [
            {
                "provider_slot_id": descriptor["provider_slot_id"],
                "rakuten_measurement_id": None,
            }
            for descriptor in _provider_slot_descriptors(portfolio)
        ],
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
        "physical_row_count",
        "sections",
        "owner_attestation_required",
        "live_parser_enabled",
    }:
        _fail("RAOS_EDITORIAL_V3_DETECTION_INVALID")
    if (
        detection["schema"] != "RAOS_EDITORIAL_V3_RAKUTEN_SCHEMA_DETECTION_V2"
        or detection["version"] != "2.0.0"
        or detection["state"] != "RECTANGULAR_SECTIONS_DETECTED_PROFILE_NOT_BOUND"
        or _sha256(detection["source_sha256"]) != detection["source_sha256"]
        or detection["encoding"] not in ENCODINGS
        or detection["delimiter"] not in DELIMITERS
        or _positive_integer(detection["physical_row_count"])
        != detection["physical_row_count"]
        or detection["owner_attestation_required"] is not True
        or detection["live_parser_enabled"] is not False
    ):
        _fail("RAOS_EDITORIAL_V3_DETECTION_INVALID")
    sections = _list(detection["sections"])
    if not sections:
        _fail("RAOS_EDITORIAL_V3_DETECTION_INVALID")
    for expected_index, raw in enumerate(sections):
        section = _mapping(raw)
        if set(section) != {
            "section_index",
            "header_row_index",
            "column_count",
            "data_row_count",
            "header",
            "section_sha256",
        }:
            _fail("RAOS_EDITORIAL_V3_DETECTION_INVALID")
        header = [_text(value, maximum=300) for value in _list(section["header"])]
        if (
            section["section_index"] != expected_index
            or _nonnegative_integer(section["header_row_index"])
            != section["header_row_index"]
            or _positive_integer(section["column_count"]) != len(header)
            or _positive_integer(section["data_row_count"]) != section["data_row_count"]
            or len(header) < 2
            or len(header) != len(set(header))
            or _sha256(section["section_sha256"]) != section["section_sha256"]
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


def _provider_slot_descriptors(
    portfolio: EditorialPortfolioV3,
) -> list[dict[str, str]]:
    descriptors = sorted(
        (
            {
                "provider_slot_id": slot.provider_slot_id,
                "article_id": slot.article_id,
                "placement": slot.placement,
            }
            for slot in portfolio.provider_slots
        ),
        key=lambda row: row["provider_slot_id"],
    )
    provider_slot_ids = {row["provider_slot_id"] for row in descriptors}
    provider_slot_keys = {(row["article_id"], row["placement"]) for row in descriptors}
    live_links = [
        binding for article in portfolio.articles for binding in article.cta_bindings
    ]
    if (
        len(descriptors) != PROVIDER_SLOT_COUNT
        or len(provider_slot_ids) != PROVIDER_SLOT_COUNT
        or len(provider_slot_keys) != PROVIDER_SLOT_COUNT
        or len(live_links) != LIVE_LINK_COUNT
        or any(
            binding.provider_slot_id not in provider_slot_ids
            or portfolio.provider_slot_by_id[binding.provider_slot_id].article_id
            != binding.article_id
            or portfolio.provider_slot_by_id[binding.provider_slot_id].placement
            != binding.placement
            for binding in live_links
        )
    ):
        _fail("RAOS_EDITORIAL_V3_PROVIDER_SLOT_CONTRACT_INVALID")
    return descriptors


def _provider_slot_set_sha256(portfolio: EditorialPortfolioV3) -> str:
    return sha256_bytes(canonical_json_bytes(_provider_slot_descriptors(portfolio)))


def _provider_measurement_mapping(
    value: object,
    *,
    portfolio: EditorialPortfolioV3,
    failure_code: str,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    expected_slot_ids = {
        descriptor["provider_slot_id"]
        for descriptor in _provider_slot_descriptors(portfolio)
    }
    normalized: list[dict[str, str]] = []
    slot_ids: set[str] = set()
    measurement_ids: set[str] = set()
    for raw in _list(value):
        row = _mapping(raw)
        if set(row) != {"provider_slot_id", "rakuten_measurement_id"}:
            _fail(failure_code)
        provider_slot_id = _text(row["provider_slot_id"], maximum=64)
        measurement_id = _text(row["rakuten_measurement_id"], maximum=64)
        if (
            provider_slot_id in slot_ids
            or measurement_id in measurement_ids
            or measurement_id.lstrip().startswith(FORMULA_PREFIXES)
        ):
            _fail(failure_code)
        slot_ids.add(provider_slot_id)
        measurement_ids.add(measurement_id)
        normalized.append(
            {
                "provider_slot_id": provider_slot_id,
                "rakuten_measurement_id": measurement_id,
            }
        )
    normalized.sort(key=lambda row: row["provider_slot_id"])
    if (
        slot_ids != expected_slot_ids
        or len(measurement_ids) != PROVIDER_SLOT_COUNT
        or len(normalized) != PROVIDER_SLOT_COUNT
    ):
        _fail(failure_code)
    return normalized, {
        row["rakuten_measurement_id"]: row["provider_slot_id"] for row in normalized
    }


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
        "provider_measurement_id_echo_verified_in_provider_report",
        "section_selection",
        "provider_slot_count",
        "provider_measurement_id_count",
        "provider_slots",
        "columns",
        "status_values",
        "amount_format",
        "date_format",
        "expected_currency",
    }
    if set(request) != expected_request_keys:
        _fail("RAOS_EDITORIAL_V3_BIND_REQUEST_INVALID")
    if (
        request["schema"] != RAKUTEN_BIND_REQUEST_SCHEMA
        or request["version"] != "2.0.0"
        or _sha256(request["detection_receipt_sha256"]) != detection_content_sha256
        or _sha256(request["detection_source_sha256"]) != sha256_bytes(sample_content)
        or request["detection_source_sha256"] != detection["source_sha256"]
        or request["owner_verified_sanitized_real_sample"] is not True
        or request["provider_measurement_id_echo_verified_in_provider_report"]
        is not True
        or request["provider_slot_count"] != PROVIDER_SLOT_COUNT
        or request["provider_measurement_id_count"] != PROVIDER_SLOT_COUNT
        or request["amount_format"] not in AMOUNT_FORMATS
        or request["date_format"] not in DATE_FORMATS
        or request["expected_currency"] != "JPY"
    ):
        _fail("RAOS_EDITORIAL_V3_BIND_REQUEST_INVALID")
    recomputed_detection = detect_rakuten_sample(
        sample_content,
        encoding=_text(detection["encoding"]),
        delimiter_name=_text(detection["delimiter"]),
    )
    if dict(detection) != recomputed_detection:
        _fail("RAOS_EDITORIAL_V3_DETECTION_INVALID")
    selection = _mapping(request["section_selection"])
    if set(selection) != {
        "section_index",
        "header_row_index",
        "section_sha256",
    }:
        _fail("RAOS_EDITORIAL_V3_BIND_REQUEST_INVALID")
    section_index = _nonnegative_integer(selection["section_index"])
    header_row_index = _nonnegative_integer(selection["header_row_index"])
    section_sha256 = _sha256(selection["section_sha256"])
    detected_sections = _list(detection["sections"])
    if section_index >= len(detected_sections):
        _fail("RAOS_EDITORIAL_V3_BIND_REQUEST_INVALID")
    selected_detection = _mapping(detected_sections[section_index])
    if (
        selected_detection["section_index"] != section_index
        or selected_detection["header_row_index"] != header_row_index
        or selected_detection["section_sha256"] != section_sha256
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
        _text(value, maximum=300) for value in _list(selected_detection["header"])
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

    provider_slots, provider_slot_by_measurement_id = _provider_measurement_mapping(
        request["provider_slots"],
        portfolio=portfolio,
        failure_code="RAOS_EDITORIAL_V3_BIND_REQUEST_INVALID",
    )
    provider_slot_set_sha256 = _provider_slot_set_sha256(portfolio)
    provider_measurement_binding_sha256 = sha256_bytes(
        canonical_json_bytes(provider_slots)
    )

    encoding = _text(detection["encoding"])
    delimiter_name = _text(detection["delimiter"])
    _physical_row_count, sections = _csv_sections(
        sample_content, encoding=encoding, delimiter_name=delimiter_name
    )
    selected_section = sections[section_index]
    header = cast(tuple[str, ...], selected_section["header"])
    rows = cast(list[tuple[str, ...]], selected_section["rows"])
    if list(header) != detected_header:
        _fail("RAOS_EDITORIAL_V3_SAMPLE_HEADER_CHANGED")
    if (
        selected_section["header_row_index"] != header_row_index
        or selected_section["section_sha256"] != section_sha256
    ):
        _fail("RAOS_EDITORIAL_V3_SAMPLE_SECTION_CHANGED")
    header_index = {value: position for position, value in enumerate(header)}
    inverse_status = {
        provider_value: canonical
        for canonical, values in status_values.items()
        for provider_value in values
    }
    observed_statuses: set[str] = set()
    expected_measurements = set(provider_slot_by_measurement_id)
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
        "schema": RAKUTEN_PARSER_PROFILE_SCHEMA,
        "version": "2.0.0",
        "state": "VERIFIED_SAMPLE_BOUND",
        "parser_version": "rakuten-sanitized-csv.v2",
        "sample_source_sha256": sha256_bytes(sample_content),
        "detection_receipt_sha256": detection_content_sha256,
        "encoding": encoding,
        "delimiter": delimiter_name,
        "section_selection": {
            "section_index": section_index,
            "header_row_index": header_row_index,
            "sample_section_sha256": section_sha256,
        },
        "header": detected_header,
        "columns": dict(columns),
        "status_values": {
            status: list(status_values[status]) for status in CANONICAL_STATUSES
        },
        "amount_format": request["amount_format"],
        "date_format": request["date_format"],
        "expected_currency": "JPY",
        "provider_measurement_id_echo_verified_in_provider_report": True,
        "provider_slot_count": PROVIDER_SLOT_COUNT,
        "provider_measurement_id_count": PROVIDER_SLOT_COUNT,
        "provider_slot_set_sha256": provider_slot_set_sha256,
        "provider_measurement_binding_sha256": (provider_measurement_binding_sha256),
        "provider_slots": provider_slots,
        "direct_attribution_enabled": True,
        "estimated_attribution_enabled": False,
    }


def _validate_profile(
    profile: Mapping[str, object], portfolio: EditorialPortfolioV3
) -> dict[str, str]:
    if set(profile) != {
        "schema",
        "version",
        "state",
        "parser_version",
        "sample_source_sha256",
        "detection_receipt_sha256",
        "encoding",
        "delimiter",
        "section_selection",
        "header",
        "columns",
        "status_values",
        "amount_format",
        "date_format",
        "expected_currency",
        "provider_measurement_id_echo_verified_in_provider_report",
        "provider_slot_count",
        "provider_measurement_id_count",
        "provider_slot_set_sha256",
        "provider_measurement_binding_sha256",
        "provider_slots",
        "direct_attribution_enabled",
        "estimated_attribution_enabled",
    }:
        _fail("RAOS_EDITORIAL_V3_PROFILE_INVALID")
    if (
        profile["schema"] != RAKUTEN_PARSER_PROFILE_SCHEMA
        or profile["version"] != "2.0.0"
        or profile["state"] != "VERIFIED_SAMPLE_BOUND"
        or profile["parser_version"] != "rakuten-sanitized-csv.v2"
        or _sha256(profile["sample_source_sha256"]) != profile["sample_source_sha256"]
        or _sha256(profile["detection_receipt_sha256"])
        != profile["detection_receipt_sha256"]
        or profile["encoding"] not in ENCODINGS
        or profile["delimiter"] not in DELIMITERS
        or profile["amount_format"] not in AMOUNT_FORMATS
        or profile["date_format"] not in DATE_FORMATS
        or profile["expected_currency"] != "JPY"
        or profile["provider_measurement_id_echo_verified_in_provider_report"]
        is not True
        or profile["provider_slot_count"] != PROVIDER_SLOT_COUNT
        or profile["provider_measurement_id_count"] != PROVIDER_SLOT_COUNT
        or _sha256(profile["provider_slot_set_sha256"])
        != _provider_slot_set_sha256(portfolio)
        or profile["direct_attribution_enabled"] is not True
        or profile["estimated_attribution_enabled"] is not False
    ):
        _fail("RAOS_EDITORIAL_V3_PROFILE_INVALID")
    header = [_text(value, maximum=300) for value in _list(profile["header"])]
    selection = _mapping(profile["section_selection"])
    columns = _mapping(profile["columns"])
    if (
        not header
        or len(header) != len(set(header))
        or set(selection)
        != {"section_index", "header_row_index", "sample_section_sha256"}
        or _nonnegative_integer(selection["section_index"])
        != selection["section_index"]
        or _nonnegative_integer(selection["header_row_index"])
        != selection["header_row_index"]
        or _sha256(selection["sample_section_sha256"])
        != selection["sample_section_sha256"]
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
    provider_slots, provider_slot_by_measurement_id = _provider_measurement_mapping(
        profile["provider_slots"],
        portfolio=portfolio,
        failure_code="RAOS_EDITORIAL_V3_PROFILE_INVALID",
    )
    if _sha256(profile["provider_measurement_binding_sha256"]) != sha256_bytes(
        canonical_json_bytes(provider_slots)
    ):
        _fail("RAOS_EDITORIAL_V3_PROFILE_INVALID")
    return provider_slot_by_measurement_id


def parse_rakuten_report(
    *,
    content: bytes,
    profile: Mapping[str, object],
    profile_sha256: str,
    portfolio: EditorialPortfolioV3,
) -> dict[str, object]:
    provider_slot_by_measurement_id = _validate_profile(profile, portfolio)
    _sha256(profile_sha256)
    encoding = _text(profile["encoding"])
    delimiter_name = _text(profile["delimiter"])
    _physical_row_count, sections = _csv_sections(
        content, encoding=encoding, delimiter_name=delimiter_name
    )
    selection = _mapping(profile["section_selection"])
    section_index = _nonnegative_integer(selection["section_index"])
    if section_index >= len(sections):
        _fail("RAOS_EDITORIAL_V3_REPORT_SECTION_MISMATCH")
    section = sections[section_index]
    header = cast(tuple[str, ...], section["header"])
    rows = cast(list[tuple[str, ...]], section["rows"])
    expected_header = tuple(
        _text(value, maximum=300) for value in _list(profile["header"])
    )
    if (
        header != expected_header
        or section["header_row_index"] != selection["header_row_index"]
    ):
        _fail("RAOS_EDITORIAL_V3_REPORT_HEADER_MISMATCH")
    columns = _mapping(profile["columns"])
    header_index = {value: position for position, value in enumerate(header)}
    statuses = _mapping(profile["status_values"])
    inverse_status = {
        _text(provider_value, maximum=300): canonical
        for canonical in CANONICAL_STATUSES
        for provider_value in _list(statuses[canonical])
    }
    provider_slots = portfolio.provider_slot_by_id
    totals = {status: 0 for status in CANONICAL_STATUSES}
    direct_by_article: dict[str, dict[str, int]] = {
        article.article_id: {status: 0 for status in CANONICAL_STATUSES}
        for article in portfolio.articles
    }
    direct_by_provider_slot: dict[str, dict[str, int]] = {
        slot.provider_slot_id: {status: 0 for status in CANONICAL_STATUSES}
        for slot in portfolio.provider_slots
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
        provider_slot_id = provider_slot_by_measurement_id.get(measurement_id)
        if provider_slot_id is None:
            basis = "UNATTRIBUTED"
            unmatched_measurement_count += 1
        else:
            basis = "DIRECT"
            direct_by_provider_slot[provider_slot_id][status] += reward
            direct_by_article[provider_slots[provider_slot_id].article_id][status] += (
                reward
            )
        basis_totals[basis][status] += reward

    for status in CANONICAL_STATUSES:
        if (
            sum(row[status] for row in direct_by_provider_slot.values())
            != sum(row[status] for row in direct_by_article.values())
            or sum(row[status] for row in direct_by_article.values())
            != basis_totals["DIRECT"][status]
        ):
            _fail("RAOS_EDITORIAL_V3_REPORT_ATTRIBUTION_RECONCILIATION_FAILED")

    return {
        "schema": RAKUTEN_REPORT_DRY_RUN_SCHEMA,
        "version": "2.0.0",
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
        "direct_by_provider_slot_jpy": direct_by_provider_slot,
        "unmatched_measurement_row_count": unmatched_measurement_count,
        "raw_rows_persisted": False,
        "commit_gate": {
            "source_hash_equality_required": True,
            "profile_hash_equality_required": True,
            "provider_total_reconciliation_required": True,
            "provider_slot_reconciliation_required": True,
        },
    }


def commit_rakuten_report(
    *,
    dry_run: Mapping[str, object],
    reparsed: Mapping[str, object],
    expected_source_sha256: str,
    provider_row_count: int,
    provider_totals_jpy: Mapping[str, int],
    portfolio: EditorialPortfolioV3,
) -> dict[str, object]:
    if dry_run != reparsed:
        _fail("RAOS_EDITORIAL_V3_DRY_RUN_REPARSE_MISMATCH")
    if (
        frozenset(dry_run) != RAKUTEN_REPORT_DRY_RUN_KEYS
        or dry_run.get("schema") != RAKUTEN_REPORT_DRY_RUN_SCHEMA
        or dry_run.get("version") != "2.0.0"
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
    direct_by_article = _mapping(dry_run.get("direct_by_article_jpy"))
    direct_by_provider_slot = _mapping(dry_run.get("direct_by_provider_slot_jpy"))
    attribution = _mapping(dry_run.get("attribution"))
    direct_attribution = _mapping(attribution.get("DIRECT"))
    direct_totals = _mapping(direct_attribution.get("totals_jpy"))
    if set(direct_by_article) != set(portfolio.article_by_id) or set(
        direct_by_provider_slot
    ) != set(portfolio.provider_slot_by_id):
        _fail("RAOS_EDITORIAL_V3_COMMIT_PRECONDITION_FAILED")
    normalized_article_direct: dict[str, dict[str, int]] = {}
    normalized_slot_direct: dict[str, dict[str, int]] = {}
    for identity, raw in direct_by_article.items():
        normalized_identity = _text(identity, maximum=128)
        row = _mapping(raw)
        if normalized_identity != identity or set(row) != set(CANONICAL_STATUSES):
            _fail("RAOS_EDITORIAL_V3_COMMIT_PRECONDITION_FAILED")
        normalized_article_direct[normalized_identity] = {
            status: _nonnegative_integer(row[status]) for status in CANONICAL_STATUSES
        }
    for identity, raw in direct_by_provider_slot.items():
        normalized_identity = _text(identity, maximum=64)
        row = _mapping(raw)
        if normalized_identity != identity or set(row) != set(CANONICAL_STATUSES):
            _fail("RAOS_EDITORIAL_V3_COMMIT_PRECONDITION_FAILED")
        normalized_slot_direct[normalized_identity] = {
            status: _nonnegative_integer(row[status]) for status in CANONICAL_STATUSES
        }
    if set(direct_totals) != set(CANONICAL_STATUSES) or any(
        sum(row[status] for row in normalized_slot_direct.values())
        != sum(row[status] for row in normalized_article_direct.values())
        or sum(row[status] for row in normalized_article_direct.values())
        != _nonnegative_integer(direct_totals[status])
        or any(
            sum(
                normalized_slot_direct[slot.provider_slot_id][status]
                for slot in portfolio.provider_slots
                if slot.article_id == article_id
            )
            != normalized_article_direct[article_id][status]
            for article_id in portfolio.article_by_id
        )
        for status in CANONICAL_STATUSES
    ):
        _fail("RAOS_EDITORIAL_V3_COMMIT_PRECONDITION_FAILED")
    return {
        **dry_run,
        "schema": RAKUTEN_REPORT_COMMIT_SCHEMA,
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
) -> dict[str, object]:
    """Validate the exact owner-private activation set bound to live readback."""

    if set(document) != {
        "schema",
        "version",
        "state",
        "portfolio_sha256",
        "admin_receipt_sha256",
        "money_link_mapping_sha256",
        "v2_materialization",
        "overlays",
        "materialized_set_sha256",
        "article_count",
        "cta_count",
        "provider_slot_count",
        "provider_measurement_id_count",
        "internal_cta_identity_count",
        "live_link_count",
        "provider_slot_set_sha256",
        "provider_measurement_binding_sha256",
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
    provider_slot_set_sha256 = _sha256(document["provider_slot_set_sha256"])
    provider_measurement_binding_sha256 = _sha256(
        document["provider_measurement_binding_sha256"]
    )
    expected_cta_count = sum(
        len(article.cta_bindings) for article in portfolio.articles
    )
    expected_provider_slot_set_sha256 = _provider_slot_set_sha256(portfolio)
    if (
        document["schema"] != RAKUTEN_ACTIVATION_DRY_RUN_SCHEMA
        or document["version"] != "3.0.0"
        or document["state"] != "OWNER_PRIVATE_MATERIALIZED_NOT_PUBLISHED"
        or portfolio_sha256 != expected_portfolio
        or expected_portfolio != portfolio.source_sha256
        or document["article_count"] != len(portfolio.articles)
        or document["cta_count"] != expected_cta_count
        or expected_cta_count != INTERNAL_CTA_IDENTITY_COUNT
        or document["provider_slot_count"] != PROVIDER_SLOT_COUNT
        or document["provider_measurement_id_count"] != PROVIDER_SLOT_COUNT
        or document["internal_cta_identity_count"] != INTERNAL_CTA_IDENTITY_COUNT
        or document["live_link_count"] != LIVE_LINK_COUNT
        or provider_slot_set_sha256 != expected_provider_slot_set_sha256
        or document["provider_parameter_inference_used"] is not False
        or document["tracked_source_modified"] is not False
        or document["live_write_performed"] is not False
        or document["publication_authorized"] is not False
        or sha256_bytes(canonical_json_bytes(document)) != dry_run_sha256
    ):
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID")

    v2 = _mapping(document["v2_materialization"])
    if set(v2) != {
        "portfolio_sha256",
        "evidence_status_sha256",
        "local_generated_at",
        "production_generated_at",
        "local_receipt_sha256",
        "production_receipt_sha256",
    }:
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID")
    v2_portfolio_sha256 = _sha256(v2["portfolio_sha256"])
    v2_evidence_status_sha256 = _sha256(v2["evidence_status_sha256"])
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
            v2_local_receipt_sha256 if mode == "local" else v2_production_receipt_sha256
        )
        overlay_receipt = {
            "schema": "RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_OVERLAY_RECEIPT_V2",
            "version": "2.0.0",
            "mode": mode,
            "portfolio_sha256": portfolio_sha256,
            "v2_portfolio_sha256": v2_portfolio_sha256,
            "v2_evidence_status_sha256": v2_evidence_status_sha256,
            "v2_materialization_receipt_sha256": v2_receipt_sha256,
            "posts_sha256": posts_sha256,
            "article_set_sha256": article_set_sha256,
            "article_count": len(normalized_rows),
            "provider_slot_count": PROVIDER_SLOT_COUNT,
            "provider_measurement_id_count": PROVIDER_SLOT_COUNT,
            "internal_cta_identity_count": INTERNAL_CTA_IDENTITY_COUNT,
            "live_link_count": LIVE_LINK_COUNT,
            "cta_count": total_ctas,
            "provider_slot_set_sha256": provider_slot_set_sha256,
            "provider_measurement_binding_sha256": (
                provider_measurement_binding_sha256
            ),
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
        "provider_slot_count": document["provider_slot_count"],
        "provider_measurement_id_count": document["provider_measurement_id_count"],
        "internal_cta_identity_count": document["internal_cta_identity_count"],
        "live_link_count": document["live_link_count"],
        "provider_slot_set_sha256": provider_slot_set_sha256,
        "provider_measurement_binding_sha256": (provider_measurement_binding_sha256),
        "v2_portfolio_sha256": v2_portfolio_sha256,
        "v2_evidence_status_sha256": v2_evidence_status_sha256,
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


def _validate_publication_binding(
    value: object, *, failure_code: str
) -> dict[str, object]:
    if type(value) is not dict:
        _fail(failure_code)
    binding = cast(Mapping[str, object], value)
    if set(binding) != {
        "separate_admin_apply_receipt_sha256",
        "separate_admin_apply_state",
        "separate_admin_verified",
        "self_approval_performed",
        "publication_receipt_sha256",
        "publication_receipt_state",
        "public_readback_receipt_sha256",
        "public_readback_receipt_state",
    }:
        _fail(failure_code)
    try:
        separate_admin_apply_receipt_sha256 = _sha256(
            binding["separate_admin_apply_receipt_sha256"]
        )
        publication_receipt_sha256 = _sha256(binding["publication_receipt_sha256"])
        public_readback_receipt_sha256 = _sha256(
            binding["public_readback_receipt_sha256"]
        )
    except EditorialEconomicsV3Failure:
        _fail(failure_code)
    if (
        binding["separate_admin_apply_state"] != "APPLIED"
        or binding["separate_admin_verified"] is not True
        or binding["self_approval_performed"] is not False
        or binding["publication_receipt_state"] != "APPLIED"
        or binding["public_readback_receipt_state"] != "READBACK_VERIFIED"
    ):
        _fail(failure_code)
    return {
        "separate_admin_apply_receipt_sha256": (separate_admin_apply_receipt_sha256),
        "separate_admin_apply_state": "APPLIED",
        "separate_admin_verified": True,
        "self_approval_performed": False,
        "publication_receipt_sha256": publication_receipt_sha256,
        "publication_receipt_state": "APPLIED",
        "public_readback_receipt_sha256": public_readback_receipt_sha256,
        "public_readback_receipt_state": "READBACK_VERIFIED",
    }


def _publication_evidence_document(content: bytes) -> Mapping[str, object]:
    failure_code = "RAOS_EDITORIAL_V3_PUBLICATION_EVIDENCE_INVALID"
    if type(content) is not bytes or not 1 <= len(content) <= MAX_PRIVATE_BYTES:
        _fail(failure_code)
    try:
        value = json.loads(
            content.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_json_object,
        )
    except EditorialEconomicsV3Failure, UnicodeError, json.JSONDecodeError:
        _fail(failure_code)
    if type(value) is not dict:
        _fail(failure_code)
    return cast(Mapping[str, object], value)


def _publication_evidence_sha256(value: object) -> str:
    try:
        return _sha256(value)
    except EditorialEconomicsV3Failure:
        _fail("RAOS_EDITORIAL_V3_PUBLICATION_EVIDENCE_INVALID")


def _publication_evidence_datetime(value: object) -> str:
    try:
        return _iso_datetime(value)
    except EditorialEconomicsV3Failure:
        _fail("RAOS_EDITORIAL_V3_PUBLICATION_EVIDENCE_INVALID")


def _validate_applied_operation_receipt(value: object) -> dict[str, object]:
    failure_code = "RAOS_EDITORIAL_V3_PUBLICATION_EVIDENCE_INVALID"
    if type(value) is not dict:
        _fail(failure_code)
    operation = cast(Mapping[str, object], value)
    if set(operation) != {
        "schema",
        "proposal_id",
        "operation_id",
        "state",
        "result_code",
        "before_sha256",
        "after_sha256",
        "audit_id",
    }:
        _fail(failure_code)
    proposal_id = _publication_evidence_sha256(operation["proposal_id"])
    operation_id = _publication_evidence_sha256(operation["operation_id"])
    after_sha256 = _publication_evidence_sha256(operation["after_sha256"])
    audit_id = _publication_evidence_sha256(operation["audit_id"])
    before_value = operation["before_sha256"]
    before_sha256 = (
        None if before_value is None else _publication_evidence_sha256(before_value)
    )
    if (
        operation["schema"] != "OperationReceiptV1"
        or operation["state"] != "APPLIED"
        or operation["result_code"]
        not in {"CONTENT_RELEASE_APPLIED", "THEME_RELEASE_APPLIED"}
    ):
        _fail(failure_code)
    return {
        "schema": "OperationReceiptV1",
        "proposal_id": proposal_id,
        "operation_id": operation_id,
        "state": "APPLIED",
        "result_code": operation["result_code"],
        "before_sha256": before_sha256,
        "after_sha256": after_sha256,
        "audit_id": audit_id,
    }


def _validate_separate_admin_apply_receipt(
    value: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    failure_code = "RAOS_EDITORIAL_V3_PUBLICATION_EVIDENCE_INVALID"
    if set(value) != {
        "schema",
        "batch_token",
        "batch_manifest_sha256",
        "proposal_count",
        "proposal_ids",
        "state",
        "receipts",
    }:
        _fail(failure_code)
    batch_token = _publication_evidence_sha256(value["batch_token"])
    manifest_sha256 = _publication_evidence_sha256(value["batch_manifest_sha256"])
    raw_proposal_ids = value["proposal_ids"]
    raw_receipts = value["receipts"]
    if type(raw_proposal_ids) is not list or type(raw_receipts) is not list:
        _fail(failure_code)
    raw_proposal_id_list = cast(list[object], raw_proposal_ids)
    raw_receipt_list = cast(list[object], raw_receipts)
    proposal_ids = [_publication_evidence_sha256(item) for item in raw_proposal_id_list]
    proposal_count = value["proposal_count"]
    if (
        value["schema"] != "ReleaseWaitApplyReceiptV1"
        or value["state"] != "APPLIED"
        or type(proposal_count) is not int
        or proposal_count
        not in {PUBLICATION_DOCUMENT_COUNT, PUBLICATION_DOCUMENT_COUNT + 1}
        or proposal_ids != sorted(proposal_ids)
        or len(proposal_ids) != proposal_count
        or len(set(proposal_ids)) != proposal_count
        or len(raw_receipt_list) != proposal_count
    ):
        _fail(failure_code)
    receipts = [_validate_applied_operation_receipt(item) for item in raw_receipt_list]
    by_proposal = {cast(str, row["proposal_id"]): row for row in receipts}
    if set(by_proposal) != set(proposal_ids):
        _fail(failure_code)
    return (
        {
            "schema": "ReleaseWaitApplyReceiptV1",
            "batch_token": batch_token,
            "batch_manifest_sha256": manifest_sha256,
            "proposal_count": proposal_count,
            "proposal_ids": proposal_ids,
            "state": "APPLIED",
            "receipts": receipts,
        },
        by_proposal,
    )


def _validate_publication_materialization_binding(
    value: object,
    *,
    expected_portfolio_sha256: str,
    expected_activation_binding: Mapping[str, object],
) -> None:
    failure_code = "RAOS_EDITORIAL_V3_PUBLICATION_EVIDENCE_INVALID"
    if type(value) is not dict:
        _fail(failure_code)
    binding = cast(Mapping[str, object], value)
    if (
        set(binding)
        != {
            "schema",
            "portfolio_sha256",
            "articles",
            "products",
            "activation",
        }
        or binding["schema"] != "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V3"
    ):
        _fail(failure_code)
    if (
        _publication_evidence_sha256(binding["portfolio_sha256"])
        != expected_portfolio_sha256
    ):
        _fail(failure_code)
    articles_value = binding["articles"]
    products_value = binding["products"]
    activation_value = binding["activation"]
    if type(articles_value) is not dict:
        _fail(failure_code)
    articles = cast(Mapping[object, object], articles_value)
    if len(articles) != 10 or any(
        type(slug) is not str
        or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) is None
        or SHA256_RE.fullmatch(str(digest)) is None
        for slug, digest in articles.items()
    ):
        _fail(failure_code)
    if type(products_value) is not dict:
        _fail(failure_code)
    products = cast(Mapping[object, object], products_value)
    if len(products) != 32 or type(activation_value) is not dict:
        _fail(failure_code)
    for product_id, raw_product in products.items():
        if type(product_id) is not str or type(raw_product) is not dict:
            _fail(failure_code)
        product = cast(Mapping[str, object], raw_product)
        if set(product) != {"state", "provider_binding_sha256"} or product.get(
            "state"
        ) not in {"verified", "not_found", "ambiguous", "expired"}:
            _fail(failure_code)
        _publication_evidence_sha256(product["provider_binding_sha256"])
    activation = cast(Mapping[str, object], activation_value)
    activation_hash_fields = {
        "dry_run_sha256",
        "admin_receipt_sha256",
        "money_link_mapping_sha256",
        "materialized_set_sha256",
        "local_article_set_sha256",
        "production_article_set_sha256",
        "local_overlay_receipt_sha256",
        "production_overlay_receipt_sha256",
        "provider_slot_set_sha256",
        "provider_measurement_binding_sha256",
    }
    activation_count_fields = {
        "article_count": 10,
        "cta_count": INTERNAL_CTA_IDENTITY_COUNT,
        "provider_slot_count": PROVIDER_SLOT_COUNT,
        "provider_measurement_id_count": PROVIDER_SLOT_COUNT,
        "internal_cta_identity_count": INTERNAL_CTA_IDENTITY_COUNT,
        "live_link_count": LIVE_LINK_COUNT,
    }
    if set(activation) != activation_hash_fields | set(activation_count_fields):
        _fail(failure_code)
    for name in activation_hash_fields:
        _publication_evidence_sha256(activation[name])
    if any(
        activation[name] != expected
        for name, expected in activation_count_fields.items()
    ):
        _fail(failure_code)
    expected_pairs = {
        "dry_run_sha256": "dry_run_sha256",
        "admin_receipt_sha256": "admin_receipt_sha256",
        "money_link_mapping_sha256": "money_link_mapping_sha256",
        "materialized_set_sha256": "materialized_set_sha256",
        "production_article_set_sha256": "production_article_set_sha256",
        "production_overlay_receipt_sha256": "production_overlay_receipt_sha256",
        "provider_slot_set_sha256": "provider_slot_set_sha256",
        "provider_measurement_binding_sha256": "provider_measurement_binding_sha256",
    }
    if any(
        activation[publication_name] != expected_activation_binding[activation_name]
        for publication_name, activation_name in expected_pairs.items()
    ):
        _fail(failure_code)


def _validate_applied_publication_receipt(
    value: Mapping[str, object],
    *,
    apply_receipt: Mapping[str, object],
    apply_operations: Mapping[str, Mapping[str, object]],
    expected_portfolio_sha256: str,
    expected_activation_binding: Mapping[str, object],
) -> tuple[list[str], Mapping[str, object]]:
    failure_code = "RAOS_EDITORIAL_V3_PUBLICATION_EVIDENCE_INVALID"
    if set(value) != {
        "schema",
        "receipt_path_sha256",
        "selected_slugs",
        "selected_documents",
        "desired_sha256",
        "desired_theme_tree_sha256",
        "desired_theme_runtime_revision",
        "state",
        "attempt_id",
        "attempt_created_at_gmt",
        "materialization_binding",
        "baselines",
        "drafts",
        "proposal_keys",
        "proposals",
        "operation_ids",
        "batch_registration",
        "review_url",
        "apply_receipt",
        "authenticated_readback",
        "prior_applied_reconciliation",
        "public_readback",
        "updated_at_gmt",
    }:
        _fail(failure_code)
    selected_value = value["selected_slugs"]
    selected_documents_value = value["selected_documents"]
    desired_value = value["desired_sha256"]
    proposals_value = value["proposals"]
    operation_ids_value = value["operation_ids"]
    registration_value = value["batch_registration"]
    authenticated_value = value["authenticated_readback"]
    public_readback_value = value["public_readback"]
    if (
        value["schema"] != "RAOS_WORDPRESS_PUBLICATION_REQUEST_RECEIPT_V1"
        or value["state"] != "APPLIED"
        or type(selected_value) is not list
        or type(selected_documents_value) is not dict
        or type(desired_value) is not dict
        or type(proposals_value) is not list
        or type(operation_ids_value) is not dict
        or type(registration_value) is not dict
        or type(authenticated_value) is not dict
        or type(public_readback_value) is not dict
        or type(value["baselines"]) is not dict
        or type(value["drafts"]) is not dict
        or type(value["proposal_keys"]) is not dict
        or type(value["review_url"]) is not str
        or not value["review_url"]
        or value["apply_receipt"] != apply_receipt
    ):
        _fail(failure_code)
    selected_slugs = cast(list[object], selected_value)
    if len(selected_slugs) != PUBLICATION_DOCUMENT_COUNT or any(
        type(slug) is not str or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) is None
        for slug in selected_slugs
    ):
        _fail(failure_code)
    selected = cast(list[str], selected_slugs)
    if selected != sorted(selected) or len(set(selected)) != PUBLICATION_DOCUMENT_COUNT:
        _fail(failure_code)
    selected_documents = cast(Mapping[str, object], selected_documents_value)
    desired = cast(Mapping[str, object], desired_value)
    if (
        set(selected_documents) != set(selected)
        or sum(kind == "post" for kind in selected_documents.values()) != 10
        or sum(kind == "page" for kind in selected_documents.values()) != 3
        or set(desired) != set(selected)
    ):
        _fail(failure_code)
    for digest in desired.values():
        _publication_evidence_sha256(digest)
    _publication_evidence_sha256(value["receipt_path_sha256"])
    desired_theme_tree_sha256 = _publication_evidence_sha256(
        value["desired_theme_tree_sha256"]
    )
    desired_theme_runtime_revision = _publication_evidence_sha256(
        value["desired_theme_runtime_revision"]
    )
    _publication_evidence_sha256(value["attempt_id"])
    _publication_evidence_datetime(value["attempt_created_at_gmt"])
    _publication_evidence_datetime(value["updated_at_gmt"])
    _validate_publication_materialization_binding(
        value["materialization_binding"],
        expected_portfolio_sha256=expected_portfolio_sha256,
        expected_activation_binding=expected_activation_binding,
    )
    proposal_by_id: dict[str, Mapping[str, object]] = {}
    content_by_slug: dict[str, Mapping[str, object]] = {}
    theme_count = 0
    for raw_proposal in cast(list[object], proposals_value):
        if type(raw_proposal) is not dict:
            _fail(failure_code)
        proposal = cast(Mapping[str, object], raw_proposal)
        kind = proposal.get("kind")
        expected_fields = {
            "kind",
            "slug",
            "proposal_id",
            "after_sha256",
            "expires_at_gmt",
            "idempotency_key",
        }
        if kind == "CONTENT_RELEASE":
            expected_fields.add("post_type")
        if set(proposal) != expected_fields:
            _fail(failure_code)
        proposal_id = _publication_evidence_sha256(proposal["proposal_id"])
        after_sha256 = _publication_evidence_sha256(proposal["after_sha256"])
        _publication_evidence_sha256(proposal["idempotency_key"])
        _publication_evidence_datetime(proposal["expires_at_gmt"])
        if proposal_id in proposal_by_id:
            _fail(failure_code)
        proposal_by_id[proposal_id] = proposal
        if kind == "THEME_RELEASE":
            theme_count += 1
            if (
                proposal["slug"] is not None
                or after_sha256 != desired_theme_tree_sha256
            ):
                _fail(failure_code)
        elif kind == "CONTENT_RELEASE":
            slug = proposal["slug"]
            if (
                type(slug) is not str
                or slug not in selected_documents
                or proposal["post_type"] != selected_documents[slug]
                or slug in content_by_slug
            ):
                _fail(failure_code)
            content_by_slug[slug] = proposal
        else:
            _fail(failure_code)
    if (
        set(content_by_slug) != set(selected)
        or theme_count not in {0, 1}
        or set(proposal_by_id) != set(apply_operations)
    ):
        _fail(failure_code)
    operation_ids = cast(Mapping[str, object], operation_ids_value)
    if set(operation_ids) != set(proposal_by_id) or any(
        operation_ids[proposal_id] != proposal_id for proposal_id in proposal_by_id
    ):
        _fail(failure_code)
    for proposal_id, proposal in proposal_by_id.items():
        operation = apply_operations[proposal_id]
        if (
            operation["operation_id"] != operation_ids[proposal_id]
            or operation["after_sha256"] != proposal["after_sha256"]
            or operation["result_code"]
            != (
                "THEME_RELEASE_APPLIED"
                if proposal["kind"] == "THEME_RELEASE"
                else "CONTENT_RELEASE_APPLIED"
            )
        ):
            _fail(failure_code)
    registration = cast(Mapping[str, object], registration_value)
    if set(registration) != {
        "schema",
        "batch_token",
        "batch_manifest_sha256",
        "expected_theme_tree_sha256",
        "proposal_count",
        "proposal_ids",
        "state",
        "expires_at_gmt",
        "review_url",
    } or (
        registration["schema"] != "RAOSWordPressPublicationBatchV1"
        or registration["batch_token"] != apply_receipt["batch_token"]
        or registration["batch_manifest_sha256"]
        != apply_receipt["batch_manifest_sha256"]
        or registration["expected_theme_tree_sha256"] != desired_theme_tree_sha256
        or registration["proposal_count"] != len(proposal_by_id)
        or registration["proposal_ids"] != sorted(proposal_by_id)
        or registration["state"] not in {"REGISTERED", "APPROVED"}
        or registration["review_url"] != value["review_url"]
    ):
        _fail(failure_code)
    _publication_evidence_datetime(registration["expires_at_gmt"])
    authenticated = cast(Mapping[str, object], authenticated_value)
    if set(authenticated) != {"documents", "operations", "public_pages", "theme"}:
        _fail(failure_code)
    documents_value = authenticated["documents"]
    operations_value = authenticated["operations"]
    authenticated_pages_value = authenticated["public_pages"]
    theme_value = authenticated["theme"]
    if (
        type(documents_value) is not dict
        or type(operations_value) is not dict
        or type(authenticated_pages_value) is not dict
        or type(theme_value) is not dict
    ):
        _fail(failure_code)
    documents = cast(Mapping[str, object], documents_value)
    operations = cast(Mapping[str, object], operations_value)
    authenticated_pages = cast(Mapping[str, object], authenticated_pages_value)
    public_readback = cast(Mapping[str, object], public_readback_value)
    theme = cast(Mapping[str, object], theme_value)
    if (
        set(documents) != set(selected)
        or set(authenticated_pages) != set(selected)
        or set(public_readback) != set(selected)
    ):
        _fail(failure_code)
    for slug, raw_document in documents.items():
        proposal = content_by_slug[slug]
        if type(raw_document) is not dict:
            _fail(failure_code)
        document = cast(Mapping[str, object], raw_document)
        if (
            set(document)
            != {
                "id",
                "slug",
                "post_type",
                "status",
                "content_sha256",
                "revision_id",
                "modified_gmt",
            }
            or document.get("slug") != slug
            or document.get("post_type") != selected_documents[slug]
            or document.get("status") != "publish"
            or document.get("content_sha256") != proposal["after_sha256"]
            or type(document.get("id")) is not int
            or cast(int, document["id"]) < 1
            or type(document.get("revision_id")) is not int
            or cast(int, document["revision_id"]) < 1
        ):
            _fail(failure_code)
        _publication_evidence_datetime(document["modified_gmt"])
    content_proposal_ids = {
        proposal_id
        for proposal_id, proposal in proposal_by_id.items()
        if proposal["kind"] == "CONTENT_RELEASE"
    }
    if set(operations) != content_proposal_ids:
        _fail(failure_code)
    for proposal_id, raw_operation in operations.items():
        if (
            _validate_applied_operation_receipt(raw_operation)
            != apply_operations[proposal_id]
        ):
            _fail(failure_code)
    if set(theme) != {
        "version",
        "runtime_version",
        "runtime_revision",
        "tree_sha256",
        "proposed",
    } or (
        theme["runtime_revision"] != desired_theme_runtime_revision
        or theme["tree_sha256"] != desired_theme_tree_sha256
        or type(theme["version"]) is not str
        or theme["runtime_version"] != theme["version"]
        or type(theme["proposed"]) is not bool
    ):
        _fail(failure_code)
    for pages in (public_readback, authenticated_pages):
        for raw_page in pages.values():
            if type(raw_page) is not dict:
                _fail(failure_code)
            page = cast(Mapping[str, object], raw_page)
            if (
                page.get("status") != 200
                or page.get("indexable") is not True
                or type(page.get("url")) is not str
                or type(page.get("canonical_url")) is not str
                or page.get("theme_runtime_revision") != desired_theme_runtime_revision
            ):
                _fail(failure_code)
    return selected, public_readback


def validate_t0_publication_receipts(
    *,
    separate_admin_apply_receipt_content: bytes,
    publication_receipt_content: bytes,
    public_readback_receipt_content: bytes,
    expected_target_origin: str,
    expected_portfolio_sha256: str,
    expected_activation_binding: Mapping[str, object],
) -> dict[str, object]:
    """Validate three exact, mutually bound owner-private publication receipts."""

    failure_code = "RAOS_EDITORIAL_V3_PUBLICATION_EVIDENCE_INVALID"
    expected_portfolio_sha256 = _publication_evidence_sha256(expected_portfolio_sha256)
    apply_document = _publication_evidence_document(
        separate_admin_apply_receipt_content
    )
    publication_document = _publication_evidence_document(publication_receipt_content)
    readback_document = _publication_evidence_document(public_readback_receipt_content)
    apply_receipt, apply_operations = _validate_separate_admin_apply_receipt(
        apply_document
    )
    selected_slugs, public_readback = _validate_applied_publication_receipt(
        publication_document,
        apply_receipt=apply_receipt,
        apply_operations=apply_operations,
        expected_portfolio_sha256=expected_portfolio_sha256,
        expected_activation_binding=expected_activation_binding,
    )
    try:
        expected_origin = urlsplit(expected_target_origin)
    except ValueError:
        _fail(failure_code)
    if (
        expected_origin.scheme != "https"
        or not expected_origin.netloc
        or expected_origin.path not in {"", "/"}
        or expected_origin.query
        or expected_origin.fragment
    ):
        _fail(failure_code)
    for slug in selected_slugs:
        page = cast(Mapping[str, object], public_readback[slug])
        for field in ("url", "canonical_url"):
            try:
                parsed = urlsplit(cast(str, page[field]))
            except ValueError:
                _fail(failure_code)
            if (
                parsed.scheme != expected_origin.scheme
                or parsed.netloc != expected_origin.netloc
                or parsed.path != f"/{slug}/"
                or parsed.query
                or parsed.fragment
            ):
                _fail(failure_code)
    if set(readback_document) != {
        "schema",
        "state",
        "target_origin",
        "verification_authority",
        "self_approval_performed",
        "separate_admin_apply_receipt_sha256",
        "publication_receipt_sha256",
        "public_readback_sha256",
        "selected_slugs_sha256",
        "verified_at",
    }:
        _fail(failure_code)
    apply_sha256 = sha256_bytes(separate_admin_apply_receipt_content)
    publication_sha256 = sha256_bytes(publication_receipt_content)
    public_readback_sha256 = sha256_bytes(canonical_json_bytes(public_readback))
    selected_slugs_sha256 = sha256_bytes(canonical_json_bytes(selected_slugs))
    separate_admin_verified = (
        readback_document["verification_authority"] == "SEPARATE_ADMIN"
    )
    self_approval_performed = readback_document["self_approval_performed"]
    if (
        readback_document["schema"] != PUBLIC_READBACK_RECEIPT_SCHEMA
        or readback_document["state"] != "READBACK_VERIFIED"
        or readback_document["target_origin"] != expected_target_origin
        or separate_admin_verified is not True
        or self_approval_performed is not False
        or _publication_evidence_sha256(
            readback_document["separate_admin_apply_receipt_sha256"]
        )
        != apply_sha256
        or _publication_evidence_sha256(readback_document["publication_receipt_sha256"])
        != publication_sha256
        or _publication_evidence_sha256(readback_document["public_readback_sha256"])
        != public_readback_sha256
        or _publication_evidence_sha256(readback_document["selected_slugs_sha256"])
        != selected_slugs_sha256
    ):
        _fail(failure_code)
    _publication_evidence_datetime(readback_document["verified_at"])
    return {
        "separate_admin_apply_receipt_sha256": apply_sha256,
        "separate_admin_apply_state": "APPLIED",
        "separate_admin_verified": separate_admin_verified,
        "self_approval_performed": self_approval_performed,
        "publication_receipt_sha256": publication_sha256,
        "publication_receipt_state": "APPLIED",
        "public_readback_receipt_sha256": sha256_bytes(public_readback_receipt_content),
        "public_readback_receipt_state": "READBACK_VERIFIED",
    }


def production_readback_template(
    portfolio: EditorialPortfolioV3,
) -> dict[str, object]:
    """Return a disabled template; it is not evidence until fully attested."""

    return {
        "schema": PRODUCTION_READBACK_INPUT_SCHEMA,
        "version": "4.0.0",
        "owner_attested": False,
        "target_origin": portfolio.target_origin,
        "publication_binding": {
            "separate_admin_apply_receipt_sha256": None,
            "separate_admin_apply_state": "NOT_RECORDED",
            "separate_admin_verified": False,
            "self_approval_performed": None,
            "publication_receipt_sha256": None,
            "publication_receipt_state": "NOT_RECORDED",
            "public_readback_receipt_sha256": None,
            "public_readback_receipt_state": "NOT_RECORDED",
        },
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
                    "provider_slot_count": PROVIDER_SLOT_COUNT,
                    "provider_measurement_id_count": None,
                    "internal_cta_identity_count": None,
                    "live_link_count": None,
                    "all_provider_measurement_ids_echo_verified": False,
                    "provider_slot_set_sha256": _provider_slot_set_sha256(portfolio),
                    "provider_measurement_binding_sha256": None,
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


def _derive_unsigned_t0_candidate(
    *,
    document: Mapping[str, object],
    observation_sha256: str,
    rakuten_activation: Mapping[str, object],
    rakuten_activation_sha256: str,
    expected_portfolio_sha256: str,
    portfolio: EditorialPortfolioV3,
    separate_admin_apply_receipt_content: bytes,
    publication_receipt_content: bytes,
    public_readback_receipt_content: bytes,
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
        "publication_binding",
        "analytics_site_binding",
        "observations",
    }:
        _fail("RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID")
    claimed_publication_binding = _validate_publication_binding(
        document["publication_binding"],
        failure_code="RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID",
    )
    publication_binding = validate_t0_publication_receipts(
        separate_admin_apply_receipt_content=(separate_admin_apply_receipt_content),
        publication_receipt_content=publication_receipt_content,
        public_readback_receipt_content=public_readback_receipt_content,
        expected_target_origin=portfolio.target_origin,
        expected_portfolio_sha256=expected_portfolio_sha256,
        expected_activation_binding=activation_binding,
    )
    if publication_binding != claimed_publication_binding:
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
        document["schema"] != PRODUCTION_READBACK_INPUT_SCHEMA
        or document["version"] != "4.0.0"
        or document["owner_attested"] is not True
        or document["target_origin"] != portfolio.target_origin
    ):
        _fail("RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID")
    source_sha256 = _sha256(observation_sha256)
    now = (evaluated_at or datetime.now(UTC)).astimezone(UTC)
    article_ids = set(portfolio.article_by_id)
    earliest_success: dict[str, dict[str, object]] = {}
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
                "provider_slot_count",
                "provider_measurement_id_count",
                "internal_cta_identity_count",
                "live_link_count",
                "all_provider_measurement_ids_echo_verified",
                "provider_slot_set_sha256",
                "provider_measurement_binding_sha256",
                "activation_dry_run_sha256",
                "materialized_set_sha256",
                "production_posts_sha256",
                "production_article_set_sha256",
                "production_overlay_receipt_sha256",
            }:
                _fail("RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID")
            if (
                _positive_integer(details["provider_slot_count"]) != PROVIDER_SLOT_COUNT
                or _positive_integer(details["provider_measurement_id_count"])
                != PROVIDER_SLOT_COUNT
                or _positive_integer(details["internal_cta_identity_count"])
                != INTERNAL_CTA_IDENTITY_COUNT
                or _positive_integer(details["live_link_count"]) != LIVE_LINK_COUNT
                or details["all_provider_measurement_ids_echo_verified"] is not True
                or _sha256(details["provider_slot_set_sha256"])
                != activation_binding["provider_slot_set_sha256"]
                or _sha256(details["provider_measurement_binding_sha256"])
                != activation_binding["provider_measurement_binding_sha256"]
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
        candidate: dict[str, object] = {
            "component": component,
            "observed_at": observed_at,
            "request_sha256": request_sha256,
            "response_sha256": response_sha256,
        }
        if component == "RAKUTEN_MEASUREMENT_IDS":
            candidate["provider_slot_count"] = PROVIDER_SLOT_COUNT
            candidate["provider_measurement_id_count"] = PROVIDER_SLOT_COUNT
            candidate["internal_cta_identity_count"] = INTERNAL_CTA_IDENTITY_COUNT
            candidate["live_link_count"] = LIVE_LINK_COUNT
            candidate["provider_slot_set_sha256"] = activation_binding[
                "provider_slot_set_sha256"
            ]
            candidate["provider_measurement_binding_sha256"] = activation_binding[
                "provider_measurement_binding_sha256"
            ]
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
        if previous is None or observed_at < _text(previous["observed_at"]):
            earliest_success[component] = candidate
    if set(earliest_success) != set(READBACK_COMPONENTS):
        _fail("RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INCOMPLETE")
    ordered = [earliest_success[component] for component in READBACK_COMPONENTS]
    t0 = max(_text(row["observed_at"]) for row in ordered)
    return {
        "schema": T0_RECEIPT_SCHEMA,
        "version": "4.0.0",
        "state": "ESTABLISHED_FROM_APPLIED_PUBLICATION_AND_EXACT_READBACKS",
        "target_origin": portfolio.target_origin,
        "publication_binding": publication_binding,
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


def establish_t0_receipt(
    *,
    document: Mapping[str, object],
    observation_sha256: str,
    rakuten_activation: Mapping[str, object],
    rakuten_activation_sha256: str,
    expected_portfolio_sha256: str,
    portfolio: EditorialPortfolioV3,
    separate_admin_apply_receipt_content: bytes,
    publication_receipt_content: bytes,
    public_readback_receipt_content: bytes,
    evaluated_at: datetime | None = None,
) -> dict[str, object]:
    """Reject unsigned evidence after preserving strict structural validation.

    The current inputs are useful validation candidates, but none carries an
    independently verifiable signature or trusted provider execution receipt.
    They therefore cannot cross the public T0 establishment boundary.
    """

    _derive_unsigned_t0_candidate(
        document=document,
        observation_sha256=observation_sha256,
        rakuten_activation=rakuten_activation,
        rakuten_activation_sha256=rakuten_activation_sha256,
        expected_portfolio_sha256=expected_portfolio_sha256,
        portfolio=portfolio,
        separate_admin_apply_receipt_content=(separate_admin_apply_receipt_content),
        publication_receipt_content=publication_receipt_content,
        public_readback_receipt_content=public_readback_receipt_content,
        evaluated_at=evaluated_at,
    )
    _fail(TRUSTED_T0_EVIDENCE_REQUIRED)


def validate_t0_receipt(
    document: Mapping[str, object], portfolio: EditorialPortfolioV3
) -> str:
    if set(document) != {
        "schema",
        "version",
        "state",
        "target_origin",
        "publication_binding",
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
        document["schema"] != T0_RECEIPT_SCHEMA
        or document["version"] != "4.0.0"
        or document["state"]
        != "ESTABLISHED_FROM_APPLIED_PUBLICATION_AND_EXACT_READBACKS"
        or document["target_origin"] != portfolio.target_origin
        or _sha256(document["observation_sha256"]) != document["observation_sha256"]
        or document["derivation"] != "MAX_OF_EARLIEST_SUCCESS_PER_REQUIRED_COMPONENT"
        or document["automatic_publication"] is not False
        or document["external_mutation_performed"] is not False
    ):
        _fail("RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID")
    _validate_publication_binding(
        document["publication_binding"],
        failure_code="RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID",
    )
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
        "provider_slot_count",
        "provider_measurement_id_count",
        "internal_cta_identity_count",
        "live_link_count",
        "provider_slot_set_sha256",
        "provider_measurement_binding_sha256",
        "v2_portfolio_sha256",
        "v2_evidence_status_sha256",
        "v2_local_receipt_sha256",
        "v2_production_receipt_sha256",
        "production_posts_sha256",
        "production_article_set_sha256",
        "production_overlay_receipt_sha256",
        "materialized_set_sha256",
    }:
        _fail("RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID")
    digest_fields = {
        "dry_run_sha256",
        "portfolio_sha256",
        "admin_receipt_sha256",
        "money_link_mapping_sha256",
        "provider_slot_set_sha256",
        "provider_measurement_binding_sha256",
        "v2_portfolio_sha256",
        "v2_evidence_status_sha256",
        "v2_local_receipt_sha256",
        "v2_production_receipt_sha256",
        "production_posts_sha256",
        "production_article_set_sha256",
        "production_overlay_receipt_sha256",
        "materialized_set_sha256",
    }
    for field in digest_fields:
        _sha256(activation[field])
    if (
        activation["portfolio_sha256"] != portfolio.source_sha256
        or activation["provider_slot_count"] != PROVIDER_SLOT_COUNT
        or activation["provider_measurement_id_count"] != PROVIDER_SLOT_COUNT
        or activation["internal_cta_identity_count"] != INTERNAL_CTA_IDENTITY_COUNT
        or activation["live_link_count"] != LIVE_LINK_COUNT
        or activation["provider_slot_set_sha256"]
        != _provider_slot_set_sha256(portfolio)
    ):
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
                "provider_slot_count",
                "provider_measurement_id_count",
                "internal_cta_identity_count",
                "live_link_count",
                "provider_slot_set_sha256",
                "provider_measurement_binding_sha256",
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
            _positive_integer(row["provider_slot_count"])
            != activation["provider_slot_count"]
            or _positive_integer(row["provider_measurement_id_count"])
            != activation["provider_measurement_id_count"]
            or _positive_integer(row["internal_cta_identity_count"])
            != activation["internal_cta_identity_count"]
            or _positive_integer(row["live_link_count"])
            != activation["live_link_count"]
            or _sha256(row["provider_slot_set_sha256"])
            != activation["provider_slot_set_sha256"]
            or _sha256(row["provider_measurement_binding_sha256"])
            != activation["provider_measurement_binding_sha256"]
            or _sha256(row["activation_dry_run_sha256"]) != activation["dry_run_sha256"]
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
    _fail(TRUSTED_T0_EVIDENCE_REQUIRED)


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
        frozenset(document) != RAKUTEN_REPORT_DRY_RUN_KEYS | {"reconciliation"}
        or document.get("schema") != RAKUTEN_REPORT_COMMIT_SCHEMA
        or document.get("version") != "2.0.0"
        or document.get("state") != "COMMITTED_OWNER_PRIVATE_RECONCILED"
        or _mapping(document.get("reconciliation")).get("status") != "PASS"
        or document.get("currency") != "JPY"
        or document.get("raw_rows_persisted") is not False
    ):
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_INVALID")
    commit_gate = _mapping(document["commit_gate"])
    reconciliation = _mapping(document["reconciliation"])
    if (
        commit_gate
        != {
            "source_hash_equality_required": True,
            "profile_hash_equality_required": True,
            "provider_total_reconciliation_required": True,
            "provider_slot_reconciliation_required": True,
        }
        or set(reconciliation)
        != {
            "status",
            "provider_row_count",
            "provider_totals_jpy",
            "source_sha256_equal_to_dry_run",
            "profile_sha256_equal_to_dry_run",
        }
        or reconciliation["status"] != "PASS"
        or reconciliation["source_sha256_equal_to_dry_run"] is not True
        or reconciliation["profile_sha256_equal_to_dry_run"] is not True
        or _positive_integer(reconciliation["provider_row_count"])
        != _positive_integer(document["row_count"])
        or _mapping(reconciliation["provider_totals_jpy"])
        != _mapping(document["totals_jpy"])
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
    direct_by_provider_slot = _mapping(document.get("direct_by_provider_slot_jpy"))
    expected_provider_slot_ids = set(portfolio.provider_slot_by_id)
    if set(direct_by_provider_slot) != expected_provider_slot_ids:
        _fail("RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_INVALID")
    normalized_slot_direct: dict[str, dict[str, int]] = {}
    for provider_slot_id, raw in direct_by_provider_slot.items():
        row = _mapping(raw)
        if set(row) != set(CANONICAL_STATUSES):
            _fail("RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_INVALID")
        normalized_slot_direct[provider_slot_id] = {
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
        direct_total = cast(int, normalized_attribution["DIRECT"][status])
        if (
            sum(
                cast(int, normalized_attribution[basis][status])
                for basis in ATTRIBUTION_BASES
            )
            != normalized_totals[status]
            or sum(normalized_direct[article_id][status] for article_id in expected_ids)
            != direct_total
            or sum(
                normalized_slot_direct[provider_slot_id][status]
                for provider_slot_id in expected_provider_slot_ids
            )
            != direct_total
            or any(
                sum(
                    normalized_slot_direct[slot.provider_slot_id][status]
                    for slot in portfolio.provider_slots
                    if slot.article_id == article_id
                )
                != normalized_direct[article_id][status]
                for article_id in expected_ids
            )
        ):
            _fail("RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_INVALID")
    unattributed = normalized_attribution["UNATTRIBUTED"]
    return {
        "period": {"date_from": date_from, "date_to": date_to},
        "source_sha256": _sha256(document["source_sha256"]),
        "totals_jpy": normalized_totals,
        "direct_by_article_jpy": normalized_direct,
        "direct_by_provider_slot_jpy": normalized_slot_direct,
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
    # T0 V4 is an unsigned, self-contained candidate.  Keep its strict parser
    # available for diagnostics, but never let either a well-formed candidate
    # or a synthetic/modified document establish the baseline epoch.  A future
    # trusted-evidence schema must update this boundary explicitly.
    if t0_receipt is not None:
        try:
            validate_t0_receipt(t0_receipt, portfolio)
        except EditorialEconomicsV3Failure:
            pass
    normalized_t0: str | None = None
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
        "state": BASELINE_INCOMPLETE_STATE,
        "classification": "OWNER_PRIVATE_FINANCIAL_AND_PROVIDER_DATA",
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "t0": "UNAVAILABLE",
        "t0_receipt_sha256": "UNAVAILABLE",
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
            "t0_receipt": TRUSTED_T0_EVIDENCE_REQUIRED,
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


def evaluate_followups(
    *,
    baseline: Mapping[str, object],
    baseline_sha256: str,
    portfolio: EditorialPortfolioV3,
    as_of: str,
    candidate_query_demand: Mapping[str, object] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Reject follow-ups until a trusted T0 evidence verifier exists."""

    del (
        baseline,
        baseline_sha256,
        portfolio,
        as_of,
        candidate_query_demand,
        generated_at,
    )
    _fail(TRUSTED_T0_EVIDENCE_REQUIRED)


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
            f"<p>state: {escape(str(report.get('state')))}</p>",
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
    "BASELINE_INCOMPLETE_STATE",
    "EditorialEconomicsV3Failure",
    "TRUSTED_T0_EVIDENCE_REQUIRED",
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
    "validate_t0_publication_receipts",
    "validate_t0_receipt",
    "write_private_bytes",
    "write_private_json",
]
