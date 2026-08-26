"""Closed runtime values for the ST-1704 self-hosted editorial pilot.

The module models immutable article preparation and an owner-gated review-draft
boundary.  It carries no publication, media-upload, taxonomy, plugin, theme,
delete, scheduling, or generic HTTP capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import math
import re
from typing import Final, NoReturn, SupportsIndex
from urllib.parse import SplitResult, parse_qsl, urlsplit


PILOT_ORIGIN: Final = "https://kurashinoshirube.com"
PILOT_REVIEW_STATUS: Final = "draft"
PILOT_POSTS_PATH: Final = "/wp-json/wp/v2/posts"
PILOT_CREATE_RESPONSE_FIELDS: Final = (
    "id%2Ctype%2Cslug%2Cstatus%2Ctitle.raw%2Cexcerpt.raw%2Ccontent.raw%2C"
    "meta._raos_publication_snapshot_v1"
)
PILOT_CREATE_PATH: Final = f"{PILOT_POSTS_PATH}?_fields={PILOT_CREATE_RESPONSE_FIELDS}"
PILOT_SNAPSHOT_META_KEY: Final = "_raos_publication_snapshot_v1"
PILOT_SNAPSHOT_SCHEMA: Final = "RAOS_PUBLICATION_SNAPSHOT_V1"
PILOT_AUTHOR_NAME: Final = "暮らしのしるべ編集部"
PILOT_CTA_LABEL: Final = "楽天市場で現在の価格・在庫・カラーを見る"
PILOT_RAKUTEN_CREDIT_LABEL: Final = "Supported by Rakuten Developers"
PILOT_RAKUTEN_CREDIT_URL: Final = "https://developers.rakuten.com/"
PILOT_RAKUTEN_EVIDENCE_SCHEMA: Final = "RAOS_ST1704_RAKUTEN_PRODUCT_EVIDENCE_V1"
PILOT_RAKUTEN_IDENTITY_SCHEMA: Final = "RAOS_ST1704_RAKUTEN_PROVIDER_IDENTITY_V1"
PILOT_RAKUTEN_AFFILIATE_IDENTITY_SCHEMA: Final = (
    "RAOS_ST1704_RAKUTEN_AFFILIATE_PROVIDER_IDENTITY_V1"
)
PILOT_RAKUTEN_REQUEST_SCHEMA: Final = "RAOS_ST1704_RAKUTEN_ITEM_SEARCH_REQUEST_V1"
PILOT_SOURCE_CAPTURE_SCHEMA: Final = "RAOS_ST1704_OFFICIAL_SOURCE_CAPTURE_V1"
PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID: Final = "st1703-first-suitcase-comparison"
PILOT_CARRY_ON_RECONCILIATION_PACKET_SHA256: Final = (
    "570708758b22b2af06e663d1e89dbb39bcd2bb4536e039a6c486e6d47405687c"
)
PILOT_CARRY_ON_RECONCILIATION_REQUEST_SHA256: Final = (
    "9ead64fcc0bedb35718d9e62c8f073cf89482d97a182243e5852feb4b272b516"
)
PILOT_CARRY_ON_RECONCILIATION_PAYLOAD_SHA256: Final = (
    "f743a2944f1adca0a8fef2cdd850567767f2257836bb807c47901b25c04fc942"
)
PILOT_CARRY_ON_RECONCILIATION_ARTIFACT_SHA256: Final = (
    "2305a5baa3ffc636b90194acdff651310d3ea070c16355cbc99cb958796d04ed"
)
PILOT_CARRY_ON_RECONCILIATION_TARGET_PUBLIC_POST_ID: Final = 19
PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID: Final = 26
PILOT_CARRY_ON_RECONCILIATION_JOURNAL_STATE: Final = "RECOVERY_ATTEMPTED"
PILOT_CARRY_ON_RECONCILIATION_STATUS: Final = "PENDING_HUMAN_EXCEPTION"
PILOT_PUBLIC_VERIFICATION_CHECKS: Final = (
    "WORDPRESS_PUBLISHED_POST",
    "REVIEW_DRAFT_URL_ANONYMOUS_404_NO_REDIRECT",
    "REVIEW_DRAFT_PUBLIC_REST_PROJECTION_EMPTY",
    "REVIEW_DRAFT_AUTHENTICATED_ID_26_EXACT_FOR_AT003_OR_ABSENT_AFTER_PROMOTION",
    "PUBLIC_ARTICLE_SEO_HEAD",
    "PUBLIC_ARTICLE_OPEN_GRAPH",
    "PUBLIC_ARTICLE_X_CARD",
    "PUBLIC_ARTICLE_RAOS_JSON_LD",
    "PUBLIC_ARTICLE_VISIBLE_BODY_EXACT",
    "PUBLIC_ARTICLE_CATEGORY_EXACT",
    "THEME_RELATED_NAVIGATION_EXACT",
    "PUBLIC_HOME_CLUSTER_NAVIGATION_EXACT",
    "PUBLIC_HOME_EXCLUDES_REVIEW_DRAFT_HREFS",
    "ROBOTS_YOAST_SITEMAP_REFERENCE",
    "YOAST_SITEMAP_INDEX_POSTS_AND_PAGES_ONLY",
    "YOAST_POST_SITEMAP_CONTAINS_CLEAN_CANONICAL_EXACTLY_ONCE",
    "YOAST_PAGE_SITEMAP_EXCLUDES_CLEAN_CANONICAL",
    "YOAST_POST_AND_PAGE_SITEMAPS_EXCLUDE_REVIEW_DRAFT_URLS",
    "WORDPRESS_CORE_SITEMAP_DISABLED",
)

_JPEG_ZIGZAG_TO_NATURAL: Final = (
    0,
    1,
    8,
    16,
    9,
    2,
    3,
    10,
    17,
    24,
    32,
    25,
    18,
    11,
    4,
    5,
    12,
    19,
    26,
    33,
    40,
    48,
    41,
    34,
    27,
    20,
    13,
    6,
    7,
    14,
    21,
    28,
    35,
    42,
    49,
    56,
    57,
    50,
    43,
    36,
    29,
    22,
    15,
    23,
    30,
    37,
    44,
    51,
    58,
    59,
    52,
    45,
    38,
    31,
    39,
    46,
    53,
    60,
    61,
    54,
    47,
    55,
    62,
    63,
)
_JPEG_IDCT_COS: Final = tuple(
    tuple(
        math.cos(((2 * coordinate + 1) * frequency * math.pi) / 16)
        for frequency in range(8)
    )
    for coordinate in range(8)
)


def decoded_baseline_jpeg_dimensions(
    raw: bytes,
    *,
    maximum: int,
    required_dimensions: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Fully entropy-decode one closed baseline JPEG scan and return its dimensions."""

    def invalid() -> NoReturn:
        raise ValueError("invalid baseline JPEG") from None

    if (
        type(raw) is not bytes
        or type(maximum) is not int
        or not 16 <= len(raw) <= maximum
        or not raw.startswith(b"\xff\xd8")
        or (
            required_dimensions is not None
            and (
                type(required_dimensions) is not tuple
                or len(required_dimensions) != 2
                or any(
                    type(value) is not int or value < 1 for value in required_dimensions
                )
            )
        )
    ):
        invalid()

    quantization: dict[int, tuple[int, ...]] = {}
    huffman: dict[tuple[int, int], dict[tuple[int, int], int]] = {}
    components: dict[int, tuple[int, int, int]] = {}
    width = 0
    height = 0
    restart_interval = 0
    scan_components: list[tuple[int, int, int]] = []
    scan_start = -1
    offset = 2
    while offset < len(raw):
        if raw[offset] != 0xFF:
            invalid()
        while offset < len(raw) and raw[offset] == 0xFF:
            offset += 1
        if offset >= len(raw):
            invalid()
        marker = raw[offset]
        offset += 1
        if marker in {0x00, 0x01, 0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            invalid()
        if offset + 2 > len(raw):
            invalid()
        length = int.from_bytes(raw[offset : offset + 2], "big")
        end = offset + length
        if length < 2 or end > len(raw):
            invalid()
        payload = raw[offset + 2 : end]
        offset = end

        if marker == 0xDB:
            position = 0
            while position < len(payload):
                information = payload[position]
                position += 1
                precision = information >> 4
                table_id = information & 0x0F
                if (
                    precision != 0
                    or table_id > 3
                    or table_id in quantization
                    or position + 64 > len(payload)
                ):
                    invalid()
                values = tuple(payload[position : position + 64])
                if any(value == 0 for value in values):
                    invalid()
                quantization[table_id] = values
                position += 64
            if position != len(payload):
                invalid()
            continue

        if marker == 0xC4:
            position = 0
            while position < len(payload):
                information = payload[position]
                position += 1
                table_class = information >> 4
                table_id = information & 0x0F
                if (
                    table_class not in {0, 1}
                    or table_id > 3
                    or (table_class, table_id) in huffman
                    or position + 16 > len(payload)
                ):
                    invalid()
                counts = payload[position : position + 16]
                position += 16
                symbol_count = sum(counts)
                if symbol_count < 1 or position + symbol_count > len(payload):
                    invalid()
                symbols = payload[position : position + symbol_count]
                position += symbol_count
                table: dict[tuple[int, int], int] = {}
                code = 0
                symbol_offset = 0
                for bit_length, count in enumerate(counts, start=1):
                    # T.81 reserves the all-ones Huffman code so marker padding
                    # cannot be decoded as a symbol.  Equality would assign that
                    # forbidden final code even though the tree is not oversubscribed.
                    if code + count >= 1 << bit_length:
                        invalid()
                    for _index in range(count):
                        table[(bit_length, code)] = symbols[symbol_offset]
                        symbol_offset += 1
                        code += 1
                    code <<= 1
                if symbol_offset != symbol_count:
                    invalid()
                huffman[(table_class, table_id)] = table
            if position != len(payload):
                invalid()
            continue

        if marker == 0xC0:
            if components or len(payload) < 9 or payload[0] != 8:
                invalid()
            height = int.from_bytes(payload[1:3], "big")
            width = int.from_bytes(payload[3:5], "big")
            component_count = payload[5]
            if (
                width < 1
                or height < 1
                or (
                    required_dimensions is not None
                    and (width, height) != required_dimensions
                )
                or component_count not in {1, 3}
                or len(payload) != 6 + (3 * component_count)
                or width * height > maximum
            ):
                invalid()
            for position in range(6, len(payload), 3):
                component_id = payload[position]
                sampling = payload[position + 1]
                horizontal = sampling >> 4
                vertical = sampling & 0x0F
                quantization_id = payload[position + 2]
                if (
                    component_id in components
                    or not 1 <= horizontal <= 4
                    or not 1 <= vertical <= 4
                    or quantization_id > 3
                ):
                    invalid()
                components[component_id] = (horizontal, vertical, quantization_id)
            if sum(value[0] * value[1] for value in components.values()) > 10:
                invalid()
            continue

        if marker == 0xDD:
            if len(payload) != 2 or restart_interval:
                invalid()
            restart_interval = int.from_bytes(payload, "big")
            if restart_interval < 1:
                invalid()
            continue

        if marker == 0xDA:
            if not components or scan_start >= 0 or len(payload) < 6:
                invalid()
            component_count = payload[0]
            if (
                component_count != len(components)
                or len(payload) != 4 + (2 * component_count)
                or payload[-3:] != b"\x00\x3f\x00"
            ):
                invalid()
            seen: set[int] = set()
            for position in range(1, 1 + (2 * component_count), 2):
                component_id = payload[position]
                selector = payload[position + 1]
                dc_table = selector >> 4
                ac_table = selector & 0x0F
                if (
                    component_id not in components
                    or component_id in seen
                    or (0, dc_table) not in huffman
                    or (1, ac_table) not in huffman
                ):
                    invalid()
                seen.add(component_id)
                scan_components.append((component_id, dc_table, ac_table))
            if seen != set(components):
                invalid()
            if any(value[2] not in quantization for value in components.values()):
                invalid()
            scan_start = offset
            break

        if marker == 0xFE or 0xE0 <= marker <= 0xEF:
            continue
        invalid()

    if scan_start < 0:
        invalid()

    segments: list[bytes] = []
    restart_markers: list[int] = []
    current = bytearray()
    offset = scan_start
    saw_end = False
    while offset < len(raw):
        value = raw[offset]
        offset += 1
        if value != 0xFF:
            current.append(value)
            continue
        fill_count = 1
        while offset < len(raw) and raw[offset] == 0xFF:
            fill_count += 1
            offset += 1
        if offset >= len(raw):
            invalid()
        marker = raw[offset]
        offset += 1
        if marker == 0x00:
            if fill_count != 1:
                invalid()
            current.append(0xFF)
            continue
        if 0xD0 <= marker <= 0xD7:
            if not current:
                invalid()
            segments.append(bytes(current))
            current.clear()
            restart_markers.append(marker)
            continue
        if marker == 0xD9:
            if not current or offset != len(raw):
                invalid()
            segments.append(bytes(current))
            saw_end = True
            break
        invalid()
    if not saw_end:
        invalid()

    maximum_horizontal = max(value[0] for value in components.values())
    maximum_vertical = max(value[1] for value in components.values())
    mcu_columns = (width + (8 * maximum_horizontal) - 1) // (8 * maximum_horizontal)
    mcu_rows = (height + (8 * maximum_vertical) - 1) // (8 * maximum_vertical)
    total_mcus = mcu_columns * mcu_rows
    if not 1 <= total_mcus <= maximum:
        invalid()
    if restart_interval:
        segment_mcus = [
            min(restart_interval, total_mcus - start)
            for start in range(0, total_mcus, restart_interval)
        ]
        if len(segments) != len(segment_mcus) or restart_markers != [
            0xD0 + (index % 8) for index in range(len(segment_mcus) - 1)
        ]:
            invalid()
    else:
        segment_mcus = [total_mcus]
        if len(segments) != 1 or restart_markers:
            invalid()

    def receive(bits: bytes, bit_offset: int, size: int) -> tuple[int, int]:
        if size < 0 or bit_offset + size > len(bits) * 8:
            invalid()
        value = 0
        for _index in range(size):
            byte = bits[bit_offset // 8]
            value = (value << 1) | ((byte >> (7 - (bit_offset % 8))) & 1)
            bit_offset += 1
        if size and value < 1 << (size - 1):
            value -= (1 << size) - 1
        return value, bit_offset

    def symbol(
        bits: bytes,
        bit_offset: int,
        table: dict[tuple[int, int], int],
    ) -> tuple[int, int]:
        code = 0
        for bit_length in range(1, 17):
            if bit_offset >= len(bits) * 8:
                invalid()
            byte = bits[bit_offset // 8]
            code = (code << 1) | ((byte >> (7 - (bit_offset % 8))) & 1)
            bit_offset += 1
            value = table.get((bit_length, code))
            if value is not None:
                return value, bit_offset
        invalid()

    def validate_samples(coefficients: list[int], table: tuple[int, ...]) -> None:
        natural = [0] * 64
        for zigzag, natural_index in enumerate(_JPEG_ZIGZAG_TO_NATURAL):
            natural[natural_index] = coefficients[zigzag] * table[zigzag]
        if all(value == 0 for value in natural[1:]):
            if not math.isfinite((natural[0] / 8) + 128):
                invalid()
            return
        for y in range(8):
            for x in range(8):
                total = 0.0
                for vertical in range(8):
                    vertical_scale = math.sqrt(0.5) if vertical == 0 else 1.0
                    for horizontal in range(8):
                        horizontal_scale = math.sqrt(0.5) if horizontal == 0 else 1.0
                        total += (
                            horizontal_scale
                            * vertical_scale
                            * natural[(vertical * 8) + horizontal]
                            * _JPEG_IDCT_COS[x][horizontal]
                            * _JPEG_IDCT_COS[y][vertical]
                        )
                if not math.isfinite((total / 4) + 128):
                    invalid()

    for bits, mcu_count in zip(segments, segment_mcus, strict=True):
        bit_offset = 0
        predictors = {component_id: 0 for component_id in components}
        for _mcu in range(mcu_count):
            for component_id, dc_table_id, ac_table_id in scan_components:
                horizontal, vertical, quantization_id = components[component_id]
                for _block in range(horizontal * vertical):
                    coefficients = [0] * 64
                    dc_size, bit_offset = symbol(
                        bits, bit_offset, huffman[(0, dc_table_id)]
                    )
                    if dc_size > 11:
                        invalid()
                    difference, bit_offset = receive(bits, bit_offset, dc_size)
                    predictors[component_id] += difference
                    coefficients[0] = predictors[component_id]
                    position = 1
                    while position < 64:
                        ac_value, bit_offset = symbol(
                            bits, bit_offset, huffman[(1, ac_table_id)]
                        )
                        if ac_value == 0:
                            break
                        if ac_value == 0xF0:
                            position += 16
                            if position > 64:
                                invalid()
                            continue
                        run = ac_value >> 4
                        size = ac_value & 0x0F
                        if size < 1 or size > 10:
                            invalid()
                        position += run
                        if position >= 64:
                            invalid()
                        coefficient, bit_offset = receive(bits, bit_offset, size)
                        coefficients[position] = coefficient
                        position += 1
                    validate_samples(coefficients, quantization[quantization_id])
        remaining = (len(bits) * 8) - bit_offset
        if remaining > 7:
            invalid()
        for position in range(bit_offset, len(bits) * 8):
            if not ((bits[position // 8] >> (7 - (position % 8))) & 1):
                invalid()
    return width, height


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_RFC3339_UTC_SECONDS = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z",
    re.ASCII,
)
_RFC3339_UTC = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z\Z",
    re.ASCII,
)
_ITEM_CODE = re.compile(r"[A-Za-z0-9._~-]{1,100}:[A-Za-z0-9._~-]{1,200}\Z", re.ASCII)
_SOURCE_REF = re.compile(r"SRC-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z", re.ASCII)
_JAN = re.compile(r"(?:[0-9]{8}|[0-9]{13})\Z", re.ASCII)
_RAKUTEN_ITEM_PATH = re.compile(
    r"/[A-Za-z0-9._~-]{1,100}/[A-Za-z0-9._~%+-]{1,300}/\Z", re.ASCII
)
_RAKUTEN_AFFILIATE_PATH = re.compile(r"/hgc/[A-Za-z0-9._~-]{1,300}/\Z", re.ASCII)
_SAFE_RAKUTEN_IMAGE_PATH = re.compile(r"/[A-Za-z0-9._~!$&()*+,;=:@%/-]+\Z", re.ASCII)
_MALFORMED_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})", re.ASCII)
_MAX_POST_ID = (1 << 63) - 1
_MAX_CONTENT_BYTES = 2_000_000


@dataclass(frozen=True, slots=True)
class PilotArticleIdentity:
    article_id: str
    slug: str
    article_type_code: str
    article_type: str
    section: str
    slot: int


PILOT_ARTICLE_IDENTITIES: Final[tuple[PilotArticleIdentity, ...]] = (
    PilotArticleIdentity(
        article_id="st1703-first-suitcase-comparison",
        slug="carry-on-suitcase-comparison",
        article_type_code="AT-003",
        article_type="product_comparison",
        section="移動",
        slot=1,
    ),
    PilotArticleIdentity(
        article_id="st1704-portable-power-station-guide",
        slug="portable-power-station-guide",
        article_type_code="AT-001",
        article_type="selection_guide",
        section="備え",
        slot=2,
    ),
    PilotArticleIdentity(
        article_id="st1704-anker-solix-c300-c800-c1000-differences",
        slug="anker-solix-c300-c800-c1000-differences",
        article_type_code="AT-004",
        article_type="model_generation_capacity_difference",
        section="備え",
        slot=3,
    ),
    PilotArticleIdentity(
        article_id="st1704-countertop-dishwasher-for-small-households",
        slug="countertop-dishwasher-for-small-households",
        article_type_code="AT-002",
        article_type="use_case_recommendation",
        section="家事",
        slot=4,
    ),
    PilotArticleIdentity(
        article_id="st1704-compact-robot-vacuum-shortlist",
        slug="compact-robot-vacuum-shortlist",
        article_type_code="AT-005",
        article_type="condition_filtering",
        section="家事",
        slot=5,
    ),
)
PILOT_ARTICLE_IDS: Final = frozenset(
    identity.article_id for identity in PILOT_ARTICLE_IDENTITIES
)


class EditorialPilotFailureCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PACKET_INVALID = "PACKET_INVALID"
    ARTICLE_NOT_ALLOWLISTED = "ARTICLE_NOT_ALLOWLISTED"
    ARTICLE_IDENTITY_MISMATCH = "ARTICLE_IDENTITY_MISMATCH"
    CONTENT_AST_INVALID = "CONTENT_AST_INVALID"
    RESOURCE_REFERENCE_INVALID = "RESOURCE_REFERENCE_INVALID"
    RESOURCE_NOT_READY = "RESOURCE_NOT_READY"
    REQUEST_INVALID = "REQUEST_INVALID"
    RECORDED_EVIDENCE_REQUIRED = "RECORDED_EVIDENCE_REQUIRED"
    RECORDED_RESPONSE_INVALID = "RECORDED_RESPONSE_INVALID"
    OWNER_GATE_REQUIRED = "OWNER_GATE_REQUIRED"
    CREDENTIAL_UNAVAILABLE = "CREDENTIAL_UNAVAILABLE"
    TRANSPORT_REFUSED = "TRANSPORT_REFUSED"
    OUTCOME_AMBIGUOUS = "OUTCOME_AMBIGUOUS"
    JOURNAL_UNSAFE = "JOURNAL_UNSAFE"
    JOURNAL_AMBIGUOUS = "JOURNAL_AMBIGUOUS"
    JOURNAL_MISMATCH = "JOURNAL_MISMATCH"
    PUBLIC_OBSERVATION_MISMATCH = "PUBLIC_OBSERVATION_MISMATCH"
    OPERATION_NOT_ALLOWED = "OPERATION_NOT_ALLOWED"
    LIVE_AUTHORITY_ABSENT = "LIVE_AUTHORITY_ABSENT"


class EditorialPilotFailure(RuntimeError):
    """Sanitized failure that never includes packet, URL, or response data."""

    __slots__ = ("_code",)

    def __init__(self, code: EditorialPilotFailureCode) -> None:
        if type(code) is not EditorialPilotFailureCode:
            raise TypeError("invalid editorial-pilot failure code")
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> EditorialPilotFailureCode:
        return self._code

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"EditorialPilotFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("editorial-pilot failure serialization is disabled")


def fail_editorial_pilot(
    code: EditorialPilotFailureCode = EditorialPilotFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise EditorialPilotFailure(code) from None


def canonical_json_bytes(value: object) -> bytes:
    """Return the snapshot contract's recursive canonical JSON encoding."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeError:
        fail_editorial_pilot()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def bytes_sha256(value: bytes) -> str:
    if type(value) is not bytes:
        fail_editorial_pilot()
    return hashlib.sha256(value).hexdigest()


def require_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_editorial_pilot()
    return value


def article_identity(article_id: object) -> PilotArticleIdentity:
    if type(article_id) is not str:
        fail_editorial_pilot(EditorialPilotFailureCode.ARTICLE_NOT_ALLOWLISTED)
    matches = [
        identity
        for identity in PILOT_ARTICLE_IDENTITIES
        if identity.article_id == article_id
    ]
    if len(matches) != 1:
        fail_editorial_pilot(EditorialPilotFailureCode.ARTICLE_NOT_ALLOWLISTED)
    return matches[0]


def _require_text(value: object, *, maximum: int) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        fail_editorial_pilot()
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_editorial_pilot()
    return value


def _require_optional_timestamp(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is not str or _RFC3339_UTC_SECONDS.fullmatch(value) is None:
        fail_editorial_pilot()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        fail_editorial_pilot()
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        fail_editorial_pilot()
    return value


def _require_evidence_timestamp(value: object) -> str:
    if type(value) is not str or _RFC3339_UTC.fullmatch(value) is None:
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    try:
        datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return value


def _url_parts(value: object) -> tuple[str, SplitResult]:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 4096
        or value != value.strip()
        or not value.isascii()
        or any(character.isspace() or ord(character) < 0x21 for character in value)
        or any(character in value for character in "\\\"'<>[]")
        or _MALFORMED_PERCENT_ESCAPE.search(value) is not None
    ):
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.fragment
    ):
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return value, parsed


def require_rakuten_item_url(value: object) -> str:
    raw, parsed = _url_parts(value)
    if (
        parsed.hostname != "item.rakuten.co.jp"
        or parsed.netloc != "item.rakuten.co.jp"
        or _RAKUTEN_ITEM_PATH.fullmatch(parsed.path) is None
        or parsed.query
    ):
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return raw


def canonical_rakuten_provider_item_url(value: object) -> str:
    """Return the canonical item URL from Rakuten's direct provider field."""

    raw, parsed = _url_parts(value)
    if not parsed.query:
        return require_rakuten_item_url(raw)
    try:
        pairs = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=1,
        )
    except ValueError:
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if (
        len(pairs) != 1
        or pairs[0][0] != "rafcid"
        or not 1 <= len(pairs[0][1]) <= 512
        or not pairs[0][1].isascii()
    ):
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return require_rakuten_item_url(parsed._replace(query="").geturl())


def require_rakuten_affiliate_url(value: object, *, item_url: str) -> str:
    raw, parsed = _url_parts(value)
    if (
        parsed.hostname != "hb.afl.rakuten.co.jp"
        or parsed.netloc != "hb.afl.rakuten.co.jp"
        or _RAKUTEN_AFFILIATE_PATH.fullmatch(parsed.path) is None
    ):
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    try:
        pairs = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=3,
        )
    except ValueError:
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    query = dict(pairs)
    if (
        len(pairs) != 3
        or len(query) != 3
        or set(query) != {"m", "pc", "rafcid"}
        or query["pc"] != item_url
        or not 1 <= len(query["rafcid"]) <= 512
        or not query["rafcid"].isascii()
    ):
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    try:
        mobile = urlsplit(query["m"])
        mobile_port = mobile.port
    except ValueError:
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if (
        mobile.scheme not in {"http", "https"}
        or mobile.hostname != "m.rakuten.co.jp"
        or mobile.netloc != "m.rakuten.co.jp"
        or mobile.username is not None
        or mobile.password is not None
        or mobile_port is not None
        or not mobile.path.startswith("/")
        or mobile.query
        or mobile.fragment
    ):
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return raw


def require_rakuten_image_url(value: object) -> str:
    raw, parsed = _url_parts(value)
    if (
        parsed.hostname != "thumbnail.image.rakuten.co.jp"
        or parsed.netloc != "thumbnail.image.rakuten.co.jp"
        or _SAFE_RAKUTEN_IMAGE_PATH.fullmatch(parsed.path) is None
        or any(component in {".", ".."} for component in parsed.path.split("/"))
    ):
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    try:
        pairs = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=1,
        )
    except ValueError:
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if pairs != [("_ex", "128x128")]:
        fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return raw


@dataclass(frozen=True, slots=True, repr=False)
class RakutenProductEvidence:
    product_id: str
    affiliate_ref: str
    media_asset_ref: str
    item_code: str
    item_name: str
    jan: str | None
    variant: str
    source_url: str
    destination_url: str
    image_url: str
    width: int
    height: int
    retrieved_at: str
    request_fingerprint: str
    response_sha256: str
    selected_result_sha256: str
    affiliate_request_fingerprint: str
    affiliate_response_sha256: str
    affiliate_selected_result_sha256: str
    image_sha256: str
    no_modification_policy: tuple[tuple[str, bool], ...]
    schema: str = PILOT_RAKUTEN_EVIDENCE_SCHEMA

    def __post_init__(self) -> None:
        expected_policy = (
            ("aspect_ratio_change_allowed", False),
            ("crop_allowed", False),
            ("modification_allowed", False),
            ("text_overlay_allowed", False),
            ("upscale_allowed", False),
        )
        if (
            self.schema != PILOT_RAKUTEN_EVIDENCE_SCHEMA
            or type(self.product_id) is not str
            or type(self.affiliate_ref) is not str
            or type(self.media_asset_ref) is not str
            or _ITEM_CODE.fullmatch(self.item_code) is None
            or type(self.item_name) is not str
            or (self.jan is not None and _JAN.fullmatch(self.jan) is None)
            or type(self.variant) is not str
            or not self.variant
            or type(self.width) is not int
            or type(self.height) is not int
            or self.width != 128
            or self.height != 128
            or self.no_modification_policy != expected_policy
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        item_url = require_rakuten_item_url(self.source_url)
        if urlsplit(item_url).path.split("/")[1] != self.item_code.split(":", 1)[0]:
            fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        require_rakuten_affiliate_url(self.destination_url, item_url=item_url)
        require_rakuten_image_url(self.image_url)
        _require_text(self.item_name, maximum=1000)
        _require_evidence_timestamp(self.retrieved_at)
        if require_sha256(self.request_fingerprint) != canonical_sha256(
            self.request_material(affiliate_id_supplied=False)
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        require_sha256(self.response_sha256)
        if require_sha256(self.selected_result_sha256) != canonical_sha256(
            self.identity_material()
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        if require_sha256(self.affiliate_request_fingerprint) != canonical_sha256(
            self.request_material(affiliate_id_supplied=True)
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        require_sha256(self.affiliate_response_sha256)
        if require_sha256(self.affiliate_selected_result_sha256) != canonical_sha256(
            self.affiliate_identity_material()
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        require_sha256(self.image_sha256)

    def identity_material(self) -> dict[str, object]:
        return {
            "image_url": self.image_url,
            "item_code": self.item_code,
            "item_name": self.item_name,
            "schema": PILOT_RAKUTEN_IDENTITY_SCHEMA,
            "source_url": self.source_url,
        }

    def affiliate_identity_material(self) -> dict[str, object]:
        return {
            "affiliate_url": self.destination_url,
            "image_url": self.image_url,
            "item_code": self.item_code,
            "item_name": self.item_name,
            "item_url": self.destination_url,
            "schema": PILOT_RAKUTEN_AFFILIATE_IDENTITY_SCHEMA,
        }

    def request_material(self, *, affiliate_id_supplied: bool) -> dict[str, object]:
        if type(affiliate_id_supplied) is not bool:
            fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        elements = [
            "itemCode",
            "itemName",
            "itemUrl",
            "mediumImageUrls",
        ]
        if affiliate_id_supplied:
            elements.insert(0, "affiliateUrl")
        return {
            "api_version": "2026-07-01",
            "elements": elements,
            "endpoint": (
                "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
            ),
            "format": "json",
            "format_version": 2,
            "affiliate_id_supplied": affiliate_id_supplied,
            "image_flag": 1,
            "item_code": self.item_code,
            "schema": PILOT_RAKUTEN_REQUEST_SCHEMA,
            "secret_fields_excluded": ["accessKey", "affiliateId", "applicationId"],
        }


@dataclass(frozen=True, slots=True, repr=False)
class OfficialSourceCaptureEvidence:
    source_ref: str
    final_url: str
    retrieved_at: str
    content_type: str
    body_sha256: str
    response_sha256: str
    locators: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...]
    http_status: int = 200
    schema: str = PILOT_SOURCE_CAPTURE_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema != PILOT_SOURCE_CAPTURE_SCHEMA
            or type(self.source_ref) is not str
            or _SOURCE_REF.fullmatch(self.source_ref) is None
            or type(self.final_url) is not str
            or type(self.http_status) is not int
            or self.http_status != 200
            or self.content_type not in {"application/pdf", "text/html"}
            or type(self.locators) is not tuple
            or not self.locators
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        _require_evidence_timestamp(self.retrieved_at)
        require_sha256(self.body_sha256)
        require_sha256(self.response_sha256)
        observed_claims: set[str] = set()
        for locator in self.locators:
            if type(locator) is not tuple or len(locator) != 3:
                fail_editorial_pilot(
                    EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID
                )
            claim_id, claim_statement_sha256, fragments = locator
            if type(fragments) is not tuple or not fragments:
                fail_editorial_pilot(
                    EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID
                )
            if (
                type(claim_id) is not str
                or not claim_id
                or claim_id in observed_claims
                or require_sha256(claim_statement_sha256) != claim_statement_sha256
            ):
                fail_editorial_pilot(
                    EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID
                )
            observed_claims.add(claim_id)
            observed_claim_fragments: set[str] = set()
            for fragment_record in fragments:
                if type(fragment_record) is not tuple or len(fragment_record) != 2:
                    fail_editorial_pilot(
                        EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID
                    )
                fragment, fragment_sha256 = fragment_record
                try:
                    fragment_bytes = fragment.encode("utf-8", errors="strict")
                except AttributeError, UnicodeError:
                    fail_editorial_pilot(
                        EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID
                    )
                if (
                    type(fragment) is not str
                    or not 1 <= len(fragment_bytes) <= 2000
                    or fragment != fragment.strip()
                    or fragment in observed_claim_fragments
                    or require_sha256(fragment_sha256) != bytes_sha256(fragment_bytes)
                ):
                    fail_editorial_pilot(
                        EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID
                    )
                observed_claim_fragments.add(fragment)
        if self.response_sha256 != canonical_sha256(self.response_material()):
            fail_editorial_pilot(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)

    def response_material(self) -> dict[str, object]:
        return {
            "body_sha256": self.body_sha256,
            "content_type": self.content_type,
            "final_url": self.final_url,
            "http_status": self.http_status,
            "retrieved_at": self.retrieved_at,
            "schema": self.schema,
            "source_ref": self.source_ref,
        }

    def value(self) -> dict[str, object]:
        return {
            **self.response_material(),
            "locators": [
                {
                    "claim_id": claim_id,
                    "claim_statement_sha256": claim_statement_sha256,
                    "exact_utf8_fragments": [
                        {
                            "exact_utf8_fragment": fragment,
                            "fragment_sha256": fragment_sha256,
                        }
                        for fragment, fragment_sha256 in fragments
                    ],
                }
                for claim_id, claim_statement_sha256, fragments in self.locators
            ],
            "response_sha256": self.response_sha256,
        }


@dataclass(frozen=True, slots=True, repr=False)
class PublicationSnapshotPayload:
    article_id: str
    packet_sha256: str
    slug: str
    title: str
    seo_title: str
    description: str
    canonical_url: str
    og_title: str
    og_description: str
    published_at: str | None
    modified_at: str | None
    author_name: str
    section: str
    visible_content_sha256: str

    def __post_init__(self) -> None:
        identity = article_identity(self.article_id)
        if (
            self.slug != identity.slug
            or self.canonical_url != f"{PILOT_ORIGIN}/{identity.slug}/"
            or self.author_name != PILOT_AUTHOR_NAME
            or self.section != identity.section
            or self.og_title != self.title
            or self.og_description != self.description
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.ARTICLE_IDENTITY_MISMATCH)
        _require_text(self.title, maximum=300)
        _require_text(self.seo_title, maximum=300)
        _require_text(self.description, maximum=500)
        _require_optional_timestamp(self.published_at)
        _require_optional_timestamp(self.modified_at)
        require_sha256(self.visible_content_sha256)
        require_sha256(self.packet_sha256)

    def value(self) -> dict[str, object]:
        return {
            "article_id": self.article_id,
            "author_name": self.author_name,
            "canonical_url": self.canonical_url,
            "description": self.description,
            "modified_at": self.modified_at,
            "og_description": self.og_description,
            "og_title": self.og_title,
            "packet_sha256": self.packet_sha256,
            "published_at": self.published_at,
            "section": self.section,
            "seo_title": self.seo_title,
            "slug": self.slug,
            "title": self.title,
            "visible_content_sha256": self.visible_content_sha256,
        }


@dataclass(frozen=True, slots=True, repr=False)
class PublicationSnapshot:
    payload: PublicationSnapshotPayload
    payload_sha256: str
    schema: str = PILOT_SNAPSHOT_SCHEMA

    def __post_init__(self) -> None:
        if (
            type(self.payload) is not PublicationSnapshotPayload
            or self.schema != PILOT_SNAPSHOT_SCHEMA
            or require_sha256(self.payload_sha256)
            != canonical_sha256(self.payload.value())
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.REQUEST_INVALID)

    @classmethod
    def bind(cls, payload: PublicationSnapshotPayload) -> PublicationSnapshot:
        if type(payload) is not PublicationSnapshotPayload:
            fail_editorial_pilot()
        return cls(
            payload=payload,
            payload_sha256=canonical_sha256(payload.value()),
        )

    def value(self) -> dict[str, object]:
        return {
            "payload": self.payload.value(),
            "payload_sha256": self.payload_sha256,
            "schema": self.schema,
        }

    def json_string(self) -> str:
        return canonical_json_bytes(self.value()).decode("utf-8", errors="strict")


def review_draft_slug(snapshot: PublicationSnapshot) -> str:
    """Derive the only draft slug from the public identity and snapshot digest."""

    if type(snapshot) is not PublicationSnapshot:
        fail_editorial_pilot(EditorialPilotFailureCode.REQUEST_INVALID)
    return f"raos-review-{snapshot.payload.slug}-{snapshot.payload_sha256}"


@dataclass(frozen=True, slots=True, repr=False)
class ReviewDraftRequest:
    article_id: str
    packet_sha256: str
    title: str
    slug: str
    excerpt: str
    content: str
    snapshot: PublicationSnapshot
    request_sha256: str
    origin: str = PILOT_ORIGIN
    path: str = PILOT_CREATE_PATH
    status: str = PILOT_REVIEW_STATUS
    live_authority: bool = False
    publication_authority: bool = False

    def __post_init__(self) -> None:
        identity = article_identity(self.article_id)
        if (
            self.origin != PILOT_ORIGIN
            or self.path != PILOT_CREATE_PATH
            or self.status != PILOT_REVIEW_STATUS
            or self.slug != review_draft_slug(self.snapshot)
            or self.snapshot.payload.article_id != self.article_id
            or self.snapshot.payload.packet_sha256 != self.packet_sha256
            or self.snapshot.payload.slug != identity.slug
            or self.snapshot.payload.title != self.title
            or self.live_authority is not False
            or self.publication_authority is not False
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.REQUEST_INVALID)
        _require_text(self.title, maximum=300)
        _require_text(self.excerpt, maximum=500)
        require_sha256(self.packet_sha256)
        require_sha256(self.request_sha256)
        if type(self.content) is not str or not self.content.strip():
            fail_editorial_pilot(EditorialPilotFailureCode.REQUEST_INVALID)
        try:
            content_bytes = self.content.encode("utf-8", errors="strict")
        except UnicodeError:
            fail_editorial_pilot(EditorialPilotFailureCode.REQUEST_INVALID)
        if (
            not 1 <= len(content_bytes) <= _MAX_CONTENT_BYTES
            or bytes_sha256(content_bytes)
            != self.snapshot.payload.visible_content_sha256
            or self.request_sha256 != canonical_sha256(self.request_material())
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.REQUEST_INVALID)

    @classmethod
    def bind(
        cls,
        *,
        article_id: str,
        packet_sha256: str,
        title: str,
        public_slug: str,
        excerpt: str,
        content: str,
        snapshot: PublicationSnapshot,
    ) -> ReviewDraftRequest:
        if (
            type(snapshot) is not PublicationSnapshot
            or public_slug != snapshot.payload.slug
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.REQUEST_INVALID)
        draft_slug = review_draft_slug(snapshot)
        material = {
            "body": cls.wordpress_body_for(
                title=title,
                slug=draft_slug,
                excerpt=excerpt,
                content=content,
                snapshot=snapshot,
            ),
            "origin": PILOT_ORIGIN,
            "path": PILOT_CREATE_PATH,
        }
        return cls(
            article_id=article_id,
            packet_sha256=packet_sha256,
            title=title,
            slug=draft_slug,
            excerpt=excerpt,
            content=content,
            snapshot=snapshot,
            request_sha256=canonical_sha256(material),
        )

    @staticmethod
    def wordpress_body_for(
        *,
        title: str,
        slug: str,
        excerpt: str,
        content: str,
        snapshot: PublicationSnapshot,
    ) -> dict[str, object]:
        if type(snapshot) is not PublicationSnapshot:
            fail_editorial_pilot(EditorialPilotFailureCode.REQUEST_INVALID)
        return {
            "content": content,
            "excerpt": excerpt,
            "meta": {PILOT_SNAPSHOT_META_KEY: snapshot.json_string()},
            "slug": slug,
            "status": PILOT_REVIEW_STATUS,
            "title": title,
        }

    def wordpress_body(self) -> dict[str, object]:
        return self.wordpress_body_for(
            title=self.title,
            slug=self.slug,
            excerpt=self.excerpt,
            content=self.content,
            snapshot=self.snapshot,
        )

    @property
    def public_slug(self) -> str:
        return self.snapshot.payload.slug

    def request_material(self) -> dict[str, object]:
        return {
            "body": self.wordpress_body(),
            "origin": self.origin,
            "path": self.path,
        }


@dataclass(frozen=True, slots=True, repr=False)
class CarryOnSingleUrlReconciliationBinding:
    """Exact read-only binding for the terminal AT-003 reconciliation exception."""

    request: ReviewDraftRequest
    request_artifact_sha256: str
    journal_state: str
    target_public_post_id: int
    expected_review_draft_post_id: int
    reconciliation_status: str = PILOT_CARRY_ON_RECONCILIATION_STATUS
    formal_gate_eligible: bool = False
    journal_mutated: bool = False
    production_evidence: bool = False
    publication_authority: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.request) is not ReviewDraftRequest
            or self.request.article_id != PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID
            or self.request.packet_sha256 != PILOT_CARRY_ON_RECONCILIATION_PACKET_SHA256
            or self.request.request_sha256
            != PILOT_CARRY_ON_RECONCILIATION_REQUEST_SHA256
            or self.request.snapshot.payload_sha256
            != PILOT_CARRY_ON_RECONCILIATION_PAYLOAD_SHA256
            or self.request_artifact_sha256
            != PILOT_CARRY_ON_RECONCILIATION_ARTIFACT_SHA256
            or self.journal_state != PILOT_CARRY_ON_RECONCILIATION_JOURNAL_STATE
            or self.target_public_post_id
            != PILOT_CARRY_ON_RECONCILIATION_TARGET_PUBLIC_POST_ID
            or self.expected_review_draft_post_id
            != PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID
            or self.reconciliation_status != PILOT_CARRY_ON_RECONCILIATION_STATUS
            or self.formal_gate_eligible is not False
            or self.journal_mutated is not False
            or self.production_evidence is not False
            or self.publication_authority is not False
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.JOURNAL_MISMATCH)
        require_sha256(self.request_artifact_sha256)


class ReviewDraftDisposition(StrEnum):
    RECORDED_CREATED = "RECORDED_CREATED"
    RECORDED_RECOVERED = "RECORDED_RECOVERED"
    LOCAL_REPLAY = "LOCAL_REPLAY"
    OWNER_LIVE_CREATED = "OWNER_LIVE_CREATED"
    OWNER_LIVE_RECOVERED = "OWNER_LIVE_RECOVERED"
    OWNER_LIVE_REPLAY = "OWNER_LIVE_REPLAY"


@dataclass(frozen=True, slots=True, repr=False)
class ReviewDraftReceipt:
    article_id: str
    packet_sha256: str
    request_sha256: str
    response_sha256: str
    draft_id: int
    disposition: ReviewDraftDisposition
    target_public_post_id: int | None = None
    status: str = PILOT_REVIEW_STATUS
    recorded_evidence_only: bool = True
    live_authority: bool = False
    publication_authority: bool = False

    def __post_init__(self) -> None:
        article_identity(self.article_id)
        recorded_dispositions = {
            ReviewDraftDisposition.RECORDED_CREATED,
            ReviewDraftDisposition.RECORDED_RECOVERED,
            ReviewDraftDisposition.LOCAL_REPLAY,
        }
        live_dispositions = {
            ReviewDraftDisposition.OWNER_LIVE_CREATED,
            ReviewDraftDisposition.OWNER_LIVE_RECOVERED,
            ReviewDraftDisposition.OWNER_LIVE_REPLAY,
        }
        if (
            type(self.draft_id) is not int
            or not 1 <= self.draft_id <= _MAX_POST_ID
            or type(self.disposition) is not ReviewDraftDisposition
            or self.status != PILOT_REVIEW_STATUS
            or self.publication_authority is not False
            or (
                self.disposition in recorded_dispositions
                and (
                    self.recorded_evidence_only is not True
                    or self.live_authority is not False
                )
            )
            or (
                self.disposition in live_dispositions
                and (
                    self.recorded_evidence_only is not False
                    or self.live_authority is not True
                )
            )
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.RECORDED_RESPONSE_INVALID)
        if self.target_public_post_id is not None and (
            type(self.target_public_post_id) is not int
            or not 1 <= self.target_public_post_id <= _MAX_POST_ID
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.RECORDED_RESPONSE_INVALID)
        if self.disposition in live_dispositions and (
            (
                self.article_id == "st1703-first-suitcase-comparison"
                and self.target_public_post_id is None
            )
            or (
                self.article_id != "st1703-first-suitcase-comparison"
                and self.target_public_post_id is not None
            )
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.RECORDED_RESPONSE_INVALID)
        require_sha256(self.packet_sha256)
        require_sha256(self.request_sha256)
        require_sha256(self.response_sha256)


@dataclass(frozen=True, slots=True, repr=False)
class PublicVerification:
    article_id: str
    packet_sha256: str
    request_sha256: str
    response_sha256: str
    post_id: int
    status: str
    expected_public_post_id: int | None = None
    target_public_post_id: int | None = None
    review_draft_post_id: int | None = None
    article_html_sha256: str | None = None
    category_sha256: str | None = None
    homepage_html_sha256: str | None = None
    homepage_targets_sha256: str | None = None
    robots_sha256: str | None = None
    sitemap_index_sha256: str | None = None
    post_sitemap_sha256: str | None = None
    page_sitemap_sha256: str | None = None
    related_target_sha256: str | None = None
    core_sitemap_sha256: str | None = None
    review_draft_rest_evidence_sha256: str | None = None
    review_public_rest_evidence_sha256: str | None = None
    review_url_html_evidence_sha256: str | None = None
    public_surface_sha256: str | None = None
    verified_checks: tuple[str, ...] = ()
    public_surface_verified: bool = False
    recorded_evidence_only: bool = True
    live_read: bool = False
    production_evidence: bool = False

    def __post_init__(self) -> None:
        article_identity(self.article_id)
        if (
            type(self.post_id) is not int
            or not 1 <= self.post_id <= _MAX_POST_ID
            or self.status != "publish"
            or self.production_evidence is not False
            or (self.recorded_evidence_only is self.live_read)
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        require_sha256(self.packet_sha256)
        require_sha256(self.request_sha256)
        require_sha256(self.response_sha256)
        if self.target_public_post_id is not None and (
            type(self.target_public_post_id) is not int
            or not 1 <= self.target_public_post_id <= _MAX_POST_ID
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        if self.expected_public_post_id is not None and (
            type(self.expected_public_post_id) is not int
            or not 1 <= self.expected_public_post_id <= _MAX_POST_ID
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        if self.review_draft_post_id is not None and (
            type(self.review_draft_post_id) is not int
            or not 1 <= self.review_draft_post_id <= _MAX_POST_ID
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        if self.live_read and (
            self.expected_public_post_id != self.post_id
            or (
                self.article_id == PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID
                and (
                    self.target_public_post_id != self.post_id
                    or self.review_draft_post_id
                    != PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID
                )
            )
            or (
                self.article_id != PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID
                and (
                    self.target_public_post_id is not None
                    or self.review_draft_post_id is not None
                )
            )
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        surface_hashes = {
            "article_html_sha256": self.article_html_sha256,
            "category_sha256": self.category_sha256,
            "core_sitemap_sha256": self.core_sitemap_sha256,
            "homepage_html_sha256": self.homepage_html_sha256,
            "homepage_targets_sha256": self.homepage_targets_sha256,
            "page_sitemap_sha256": self.page_sitemap_sha256,
            "post_sitemap_sha256": self.post_sitemap_sha256,
            "related_target_sha256": self.related_target_sha256,
            "review_draft_rest_evidence_sha256": (
                self.review_draft_rest_evidence_sha256
            ),
            "review_public_rest_evidence_sha256": (
                self.review_public_rest_evidence_sha256
            ),
            "review_url_html_evidence_sha256": self.review_url_html_evidence_sha256,
            "robots_sha256": self.robots_sha256,
            "sitemap_index_sha256": self.sitemap_index_sha256,
        }
        if self.public_surface_verified:
            if (
                self.live_read is not True
                or self.recorded_evidence_only is not False
                or self.verified_checks != PILOT_PUBLIC_VERIFICATION_CHECKS
                or any(value is None for value in surface_hashes.values())
            ):
                fail_editorial_pilot(
                    EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH
                )
            for value in surface_hashes.values():
                require_sha256(value)
            if self.public_surface_sha256 is None or require_sha256(
                self.public_surface_sha256
            ) != canonical_sha256(surface_hashes):
                fail_editorial_pilot(
                    EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH
                )
        elif (
            self.public_surface_sha256 is not None
            or self.verified_checks
            or self.review_draft_post_id is not None
            or any(value is not None for value in surface_hashes.values())
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)


@dataclass(frozen=True, slots=True, repr=False)
class CarryOnSingleUrlReconciliationEvidence:
    """Non-formal projection of one strict carry-on public-surface read."""

    article_id: str
    packet_sha256: str
    request_sha256: str
    payload_sha256: str
    request_artifact_sha256: str
    response_sha256: str
    post_id: int
    expected_public_post_id: int
    target_public_post_id: int
    expected_review_draft_post_id: int
    review_draft_post_id: int
    article_html_sha256: str
    category_sha256: str
    core_sitemap_sha256: str
    homepage_html_sha256: str
    homepage_targets_sha256: str
    page_sitemap_sha256: str
    post_sitemap_sha256: str
    related_target_sha256: str
    review_draft_rest_evidence_sha256: str
    review_public_rest_evidence_sha256: str
    review_url_html_evidence_sha256: str
    robots_sha256: str
    sitemap_index_sha256: str
    public_surface_sha256: str
    verified_checks: tuple[str, ...] = PILOT_PUBLIC_VERIFICATION_CHECKS
    authority: str = "OWNER_GATED_READ_ONLY_RECONCILIATION"
    command: str = "verify-carry-on-single-url"
    status: str = "READ_ONLY_RECONCILIATION_EVIDENCE"
    public_post_status: str = "publish"
    journal_state: str = PILOT_CARRY_ON_RECONCILIATION_JOURNAL_STATE
    reconciliation_status: str = PILOT_CARRY_ON_RECONCILIATION_STATUS
    formal_gate_eligible: bool = False
    journal_mutated: bool = False
    strict_public_checks_passed: bool = True
    public_surface_verified: bool = False
    live_read: bool = True
    production_evidence: bool = False
    publication_authority: bool = False

    def __post_init__(self) -> None:
        if (
            self.article_id != PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID
            or self.packet_sha256 != PILOT_CARRY_ON_RECONCILIATION_PACKET_SHA256
            or self.request_sha256 != PILOT_CARRY_ON_RECONCILIATION_REQUEST_SHA256
            or self.payload_sha256 != PILOT_CARRY_ON_RECONCILIATION_PAYLOAD_SHA256
            or self.request_artifact_sha256
            != PILOT_CARRY_ON_RECONCILIATION_ARTIFACT_SHA256
            or type(self.post_id) is not int
            or self.post_id != PILOT_CARRY_ON_RECONCILIATION_TARGET_PUBLIC_POST_ID
            or type(self.expected_public_post_id) is not int
            or self.expected_public_post_id
            != PILOT_CARRY_ON_RECONCILIATION_TARGET_PUBLIC_POST_ID
            or type(self.target_public_post_id) is not int
            or self.target_public_post_id
            != PILOT_CARRY_ON_RECONCILIATION_TARGET_PUBLIC_POST_ID
            or type(self.expected_review_draft_post_id) is not int
            or self.expected_review_draft_post_id
            != PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID
            or type(self.review_draft_post_id) is not int
            or self.review_draft_post_id
            != PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID
            or self.verified_checks != PILOT_PUBLIC_VERIFICATION_CHECKS
            or self.authority != "OWNER_GATED_READ_ONLY_RECONCILIATION"
            or self.command != "verify-carry-on-single-url"
            or self.status != "READ_ONLY_RECONCILIATION_EVIDENCE"
            or self.public_post_status != "publish"
            or self.journal_state != PILOT_CARRY_ON_RECONCILIATION_JOURNAL_STATE
            or self.reconciliation_status != PILOT_CARRY_ON_RECONCILIATION_STATUS
            or self.formal_gate_eligible is not False
            or self.journal_mutated is not False
            or self.strict_public_checks_passed is not True
            or self.public_surface_verified is not False
            or self.live_read is not True
            or self.production_evidence is not False
            or self.publication_authority is not False
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        surface_hashes = {
            "article_html_sha256": self.article_html_sha256,
            "category_sha256": self.category_sha256,
            "core_sitemap_sha256": self.core_sitemap_sha256,
            "homepage_html_sha256": self.homepage_html_sha256,
            "homepage_targets_sha256": self.homepage_targets_sha256,
            "page_sitemap_sha256": self.page_sitemap_sha256,
            "post_sitemap_sha256": self.post_sitemap_sha256,
            "related_target_sha256": self.related_target_sha256,
            "review_draft_rest_evidence_sha256": (
                self.review_draft_rest_evidence_sha256
            ),
            "review_public_rest_evidence_sha256": (
                self.review_public_rest_evidence_sha256
            ),
            "review_url_html_evidence_sha256": self.review_url_html_evidence_sha256,
            "robots_sha256": self.robots_sha256,
            "sitemap_index_sha256": self.sitemap_index_sha256,
        }
        for value in (
            self.packet_sha256,
            self.request_sha256,
            self.payload_sha256,
            self.request_artifact_sha256,
            self.response_sha256,
            *surface_hashes.values(),
        ):
            require_sha256(value)
        if require_sha256(self.public_surface_sha256) != canonical_sha256(
            surface_hashes
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)

    @classmethod
    def from_strict_verification(
        cls,
        binding: CarryOnSingleUrlReconciliationBinding,
        verification: PublicVerification,
    ) -> CarryOnSingleUrlReconciliationEvidence:
        """Copy a strict internal read into the non-formal public boundary."""

        if (
            type(binding) is not CarryOnSingleUrlReconciliationBinding
            or type(verification) is not PublicVerification
            or verification.article_id != binding.request.article_id
            or verification.packet_sha256 != binding.request.packet_sha256
            or verification.request_sha256 != binding.request.request_sha256
            or verification.post_id != binding.target_public_post_id
            or verification.expected_public_post_id != binding.target_public_post_id
            or verification.target_public_post_id != binding.target_public_post_id
            or verification.review_draft_post_id
            != binding.expected_review_draft_post_id
            or verification.verified_checks != PILOT_PUBLIC_VERIFICATION_CHECKS
            or verification.public_surface_verified is not True
            or verification.recorded_evidence_only is not False
            or verification.live_read is not True
            or verification.production_evidence is not False
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        return cls(
            article_id=verification.article_id,
            packet_sha256=verification.packet_sha256,
            request_sha256=verification.request_sha256,
            payload_sha256=binding.request.snapshot.payload_sha256,
            request_artifact_sha256=binding.request_artifact_sha256,
            response_sha256=verification.response_sha256,
            post_id=verification.post_id,
            expected_public_post_id=binding.target_public_post_id,
            target_public_post_id=binding.target_public_post_id,
            expected_review_draft_post_id=binding.expected_review_draft_post_id,
            review_draft_post_id=binding.expected_review_draft_post_id,
            article_html_sha256=require_sha256(verification.article_html_sha256),
            category_sha256=require_sha256(verification.category_sha256),
            core_sitemap_sha256=require_sha256(verification.core_sitemap_sha256),
            homepage_html_sha256=require_sha256(verification.homepage_html_sha256),
            homepage_targets_sha256=require_sha256(
                verification.homepage_targets_sha256
            ),
            page_sitemap_sha256=require_sha256(verification.page_sitemap_sha256),
            post_sitemap_sha256=require_sha256(verification.post_sitemap_sha256),
            related_target_sha256=require_sha256(verification.related_target_sha256),
            review_draft_rest_evidence_sha256=require_sha256(
                verification.review_draft_rest_evidence_sha256
            ),
            review_public_rest_evidence_sha256=require_sha256(
                verification.review_public_rest_evidence_sha256
            ),
            review_url_html_evidence_sha256=require_sha256(
                verification.review_url_html_evidence_sha256
            ),
            robots_sha256=require_sha256(verification.robots_sha256),
            sitemap_index_sha256=require_sha256(verification.sitemap_index_sha256),
            public_surface_sha256=require_sha256(verification.public_surface_sha256),
        )


__all__ = [
    "CarryOnSingleUrlReconciliationEvidence",
    "CarryOnSingleUrlReconciliationBinding",
    "EditorialPilotFailure",
    "EditorialPilotFailureCode",
    "PILOT_ARTICLE_IDENTITIES",
    "PILOT_ARTICLE_IDS",
    "PILOT_AUTHOR_NAME",
    "PILOT_CTA_LABEL",
    "PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID",
    "PILOT_CARRY_ON_RECONCILIATION_ARTIFACT_SHA256",
    "PILOT_CARRY_ON_RECONCILIATION_JOURNAL_STATE",
    "PILOT_CARRY_ON_RECONCILIATION_PACKET_SHA256",
    "PILOT_CARRY_ON_RECONCILIATION_PAYLOAD_SHA256",
    "PILOT_CARRY_ON_RECONCILIATION_REQUEST_SHA256",
    "PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID",
    "PILOT_CARRY_ON_RECONCILIATION_STATUS",
    "PILOT_CARRY_ON_RECONCILIATION_TARGET_PUBLIC_POST_ID",
    "PILOT_CREATE_PATH",
    "PILOT_CREATE_RESPONSE_FIELDS",
    "PILOT_ORIGIN",
    "PILOT_POSTS_PATH",
    "PILOT_PUBLIC_VERIFICATION_CHECKS",
    "PILOT_RAKUTEN_CREDIT_LABEL",
    "PILOT_RAKUTEN_CREDIT_URL",
    "PILOT_RAKUTEN_AFFILIATE_IDENTITY_SCHEMA",
    "PILOT_RAKUTEN_EVIDENCE_SCHEMA",
    "PILOT_RAKUTEN_IDENTITY_SCHEMA",
    "PILOT_RAKUTEN_REQUEST_SCHEMA",
    "PILOT_REVIEW_STATUS",
    "PILOT_SNAPSHOT_META_KEY",
    "PILOT_SNAPSHOT_SCHEMA",
    "PILOT_SOURCE_CAPTURE_SCHEMA",
    "OfficialSourceCaptureEvidence",
    "PilotArticleIdentity",
    "PublicationSnapshot",
    "PublicationSnapshotPayload",
    "PublicVerification",
    "RakutenProductEvidence",
    "ReviewDraftDisposition",
    "ReviewDraftReceipt",
    "ReviewDraftRequest",
    "article_identity",
    "bytes_sha256",
    "canonical_rakuten_provider_item_url",
    "canonical_json_bytes",
    "canonical_sha256",
    "decoded_baseline_jpeg_dimensions",
    "fail_editorial_pilot",
    "review_draft_slug",
    "require_sha256",
]
