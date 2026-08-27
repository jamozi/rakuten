"""Strict recorded-response and owner-private journal adapters for ST-1704."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Generator, Mapping
from decimal import Decimal, InvalidOperation
import fcntl
import json
import os
from pathlib import Path
import re
import stat
from typing import Final, NoReturn, cast, final
import zlib

from raos.domain.editorial.self_hosted_editorial_pilot import (
    CarryOnSingleUrlReconciliationBinding,
    EditorialPilotFailure,
    EditorialPilotFailureCode,
    PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID,
    PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID,
    PILOT_ORIGIN,
    PILOT_REVIEW_STATUS,
    PILOT_SNAPSHOT_META_KEY,
    OfficialSourceCaptureEvidence,
    PublicationSnapshot,
    PublicationSnapshotPayload,
    PublicVerification,
    RakutenProductEvidence,
    ReviewDraftDisposition,
    ReviewDraftReceipt,
    ReviewDraftRequest,
    article_identity,
    bytes_sha256,
    canonical_rakuten_provider_item_url,
    canonical_json_bytes,
    canonical_sha256,
    decoded_baseline_jpeg_dimensions,
    fail_editorial_pilot,
    require_sha256,
)
from raos.ports.self_hosted_editorial_pilot import (
    OwnerOperatedWordPressPort,
    RecordedReviewDraftPort,
    ReviewDraftRevisionBinding,
    ReviewDraftRevisionDisposition,
    ReviewDraftRevisionObservation,
)


OWNER_DIRECTORY: Final = "st1704-self-hosted-editorial-pilot"
RECORDED_DIRECTORY: Final = "recorded"
JOURNAL_DIRECTORY: Final = "review-draft-journals"
REQUEST_DIRECTORY: Final = "immutable-review-draft-requests"
GENERATION_DIRECTORY: Final = "review-draft-generations"
RAKUTEN_DIRECTORY: Final = "rakuten"
SOURCE_DIRECTORY: Final = "sources"
LOCK_FILE: Final = "journal.lock"
MAX_RECORDED_BYTES: Final = 4_000_000
MAX_JOURNAL_BYTES: Final = 64_000
MAX_REQUEST_ARTIFACT_BYTES: Final = 4_000_000
MAX_RAKUTEN_EVIDENCE_BYTES: Final = 64_000
MAX_RAKUTEN_RESPONSE_BYTES: Final = 4_000_000
MAX_RAKUTEN_IMAGE_BYTES: Final = 2_000_000
MAX_SOURCE_EVIDENCE_BYTES: Final = 262_144
MAX_SOURCE_BODY_BYTES: Final = 8_000_000

_CREATE_SCHEMA: Final = "RAOS_RECORDED_WORDPRESS_CREATE_REVIEW_DRAFT_V1"
_RECOVERY_SCHEMA: Final = "RAOS_RECORDED_WORDPRESS_RECOVER_REVIEW_DRAFT_V1"
_PUBLIC_SCHEMA: Final = "RAOS_RECORDED_WORDPRESS_VERIFY_PUBLIC_V1"
_JOURNAL_SCHEMA: Final = "RAOS_ST1704_REVIEW_DRAFT_JOURNAL_V1"
_LIVE_JOURNAL_SCHEMA: Final = "RAOS_ST1704_OWNER_LIVE_REVIEW_DRAFT_JOURNAL_V1"
_REQUEST_ARTIFACT_SCHEMA: Final = "RAOS_ST1704_OWNER_IMMUTABLE_REVIEW_DRAFT_REQUEST_V1"
_GENERATION_LEDGER_SCHEMA: Final = "RAOS_ST1704_REVIEW_DRAFT_GENERATION_LEDGER_V1"
_MAX_REVIEW_DRAFT_GENERATIONS: Final = 32
_PRIVATE_DIRECTORY_MODE: Final = 0o700
_PRIVATE_FILE_MODE: Final = 0o600
_PRODUCT_ID = re.compile(r"PRD-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z", re.ASCII)
_SOURCE_REF = re.compile(r"SRC-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z", re.ASCII)


def _fail(
    code: EditorialPilotFailureCode = EditorialPilotFailureCode.RECORDED_RESPONSE_INVALID,
) -> NoReturn:
    fail_editorial_pilot(code)


def _pairs(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail()
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    del value
    _fail()


def decode_strict_json(raw: bytes, *, maximum_bytes: int) -> object:
    if (
        type(raw) is not bytes
        or not 1 <= len(raw) <= maximum_bytes
        or raw.startswith(b"\xef\xbb\xbf")
    ):
        _fail()
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except EditorialPilotFailure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError:
        _fail()


def _mapping(value: object) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail()
    return cast(Mapping[str, object], value)


def _exact_keys(value: Mapping[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        _fail()


def _positive_post_id(value: object) -> int:
    if type(value) is not int or not 1 <= value <= (1 << 63) - 1:
        _fail()
    return value


def _recorded_post(
    value: object,
    *,
    request: ReviewDraftRequest,
    expected_status: str,
) -> int:
    post = _mapping(value)
    _exact_keys(
        post,
        {
            "content_raw",
            "excerpt_raw",
            "id",
            "meta",
            "slug",
            "status",
            "title_raw",
            "type",
        },
    )
    meta = _mapping(post["meta"])
    _exact_keys(meta, {PILOT_SNAPSHOT_META_KEY})
    if (
        post["type"] != "post"
        or post["status"] != expected_status
        or post["slug"]
        != (
            request.slug
            if expected_status == PILOT_REVIEW_STATUS
            else request.snapshot.payload.slug
        )
        or post["title_raw"] != request.title
        or post["excerpt_raw"] != request.excerpt
        or post["content_raw"] != request.content
        or meta[PILOT_SNAPSHOT_META_KEY] != request.snapshot.json_string()
    ):
        _fail()
    return _positive_post_id(post["id"])


def _recorded_envelope(
    raw: bytes,
    *,
    schema: str,
    request: ReviewDraftRequest,
    response_kind: type[dict[object, object]] | type[list[object]],
    expected_http_status: int,
) -> tuple[object, str]:
    parsed = _mapping(decode_strict_json(raw, maximum_bytes=MAX_RECORDED_BYTES))
    _exact_keys(
        parsed,
        {"http_status", "origin", "request_sha256", "response", "schema"},
    )
    response = parsed["response"]
    if (
        parsed["schema"] != schema
        or parsed["origin"] != PILOT_ORIGIN
        or parsed["request_sha256"] != request.request_sha256
        or parsed["http_status"] != expected_http_status
        or type(response) is not response_kind
    ):
        _fail()
    return response, bytes_sha256(raw)


@final
class RecordedWordPressReviewDraftAdapter:
    """Validate sanitized captured responses; never construct a transport."""

    __slots__ = ()

    def create(
        self, request: ReviewDraftRequest, recorded_response: bytes
    ) -> ReviewDraftReceipt:
        if type(request) is not ReviewDraftRequest:
            _fail()
        response, response_sha256 = _recorded_envelope(
            recorded_response,
            schema=_CREATE_SCHEMA,
            request=request,
            response_kind=dict,
            expected_http_status=201,
        )
        draft_id = _recorded_post(
            response,
            request=request,
            expected_status=PILOT_REVIEW_STATUS,
        )
        return ReviewDraftReceipt(
            article_id=request.article_id,
            packet_sha256=request.packet_sha256,
            request_sha256=request.request_sha256,
            response_sha256=response_sha256,
            draft_id=draft_id,
            disposition=ReviewDraftDisposition.RECORDED_CREATED,
        )

    def recover(
        self, request: ReviewDraftRequest, recorded_response: bytes
    ) -> ReviewDraftReceipt:
        if type(request) is not ReviewDraftRequest:
            _fail()
        response, response_sha256 = _recorded_envelope(
            recorded_response,
            schema=_RECOVERY_SCHEMA,
            request=request,
            response_kind=list,
            expected_http_status=200,
        )
        posts = cast(list[object], response)
        if len(posts) != 1:
            _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
        draft_id = _recorded_post(
            posts[0],
            request=request,
            expected_status=PILOT_REVIEW_STATUS,
        )
        return ReviewDraftReceipt(
            article_id=request.article_id,
            packet_sha256=request.packet_sha256,
            request_sha256=request.request_sha256,
            response_sha256=response_sha256,
            draft_id=draft_id,
            disposition=ReviewDraftDisposition.RECORDED_RECOVERED,
        )


@final
class RecordedWordPressPublicReadAdapter:
    """Validate one sanitized captured public post without network access."""

    __slots__ = ()

    def verify(
        self, request: ReviewDraftRequest, recorded_response: bytes
    ) -> PublicVerification:
        if type(request) is not ReviewDraftRequest:
            _fail()
        response, response_sha256 = _recorded_envelope(
            recorded_response,
            schema=_PUBLIC_SCHEMA,
            request=request,
            response_kind=dict,
            expected_http_status=200,
        )
        post_id = _recorded_post(
            response,
            request=request,
            expected_status="publish",
        )
        return PublicVerification(
            article_id=request.article_id,
            packet_sha256=request.packet_sha256,
            request_sha256=request.request_sha256,
            response_sha256=response_sha256,
            post_id=post_id,
            status="publish",
        )


def recorded_fixture_relative_path(article_id: str, command: str) -> Path:
    allowed_commands = {
        "create-review-draft",
        "recover-create-review-draft",
        "verify-public",
    }
    from raos.domain.editorial.self_hosted_editorial_pilot import article_identity

    article_identity(article_id)
    if command not in allowed_commands:
        _fail(EditorialPilotFailureCode.OPERATION_NOT_ALLOWED)
    return Path(
        ".secrets",
        OWNER_DIRECTORY,
        RECORDED_DIRECTORY,
        f"{article_id}.{command}.v1.json",
    )


def _require_safe_existing_directory(path: Path, *, exact_mode: int | None) -> None:
    try:
        observed = path.lstat()
    except OSError:
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or stat.S_ISLNK(observed.st_mode)
        or observed.st_uid != os.getuid()
        or (exact_mode is not None and stat.S_IMODE(observed.st_mode) != exact_mode)
    ):
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)


def _private_child(
    parent: Path,
    name: str,
    *,
    create: bool,
    missing_code: EditorialPilotFailureCode = (
        EditorialPilotFailureCode.RECORDED_EVIDENCE_REQUIRED
    ),
) -> Path:
    child = parent / name
    created = False
    if create:
        try:
            child.mkdir(mode=_PRIVATE_DIRECTORY_MODE)
            created = True
        except FileExistsError:
            pass
        except OSError:
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        if created:
            try:
                child.chmod(_PRIVATE_DIRECTORY_MODE)
            except OSError:
                _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    elif not child.exists():
        _fail(missing_code)
    _require_safe_existing_directory(child, exact_mode=_PRIVATE_DIRECTORY_MODE)
    return child


def _owner_base_layout(
    repository_root: Path,
    *,
    create: bool,
    missing_code: EditorialPilotFailureCode,
) -> tuple[Path, Path]:
    if not repository_root.is_absolute():
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    _require_safe_existing_directory(repository_root, exact_mode=None)
    secrets = repository_root / ".secrets"
    if not secrets.exists() and not create:
        _fail(missing_code)
    secrets = _private_child(
        repository_root,
        ".secrets",
        create=create,
        missing_code=missing_code,
    )
    owner = _private_child(
        secrets,
        OWNER_DIRECTORY,
        create=create,
        missing_code=missing_code,
    )
    return owner, secrets


def _owner_layout(repository_root: Path, *, create: bool) -> tuple[Path, Path, Path]:
    owner, secrets = _owner_base_layout(
        repository_root,
        create=create,
        missing_code=EditorialPilotFailureCode.RECORDED_EVIDENCE_REQUIRED,
    )
    journal = _private_child(
        owner,
        JOURNAL_DIRECTORY,
        create=create,
        missing_code=EditorialPilotFailureCode.RECORDED_EVIDENCE_REQUIRED,
    )
    return owner, journal, secrets


def _request_layout(
    repository_root: Path,
    *,
    create: bool,
    missing_code: EditorialPilotFailureCode,
) -> Path:
    owner, _secrets = _owner_base_layout(
        repository_root,
        create=create,
        missing_code=missing_code,
    )
    return _private_child(
        owner,
        REQUEST_DIRECTORY,
        create=create,
        missing_code=missing_code,
    )


def _read_private_file(
    path: Path, *, maximum_bytes: int, missing_code: EditorialPilotFailureCode
) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        _fail(missing_code)
    except OSError:
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != _PRIVATE_FILE_MODE
            or before.st_nlink != 1
            or not 1 <= before.st_size <= maximum_bytes
        ):
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        after = os.fstat(descriptor)
        if (
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
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        return b"".join(chunks)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def read_recorded_fixture(
    repository_root: Path, *, article_id: str, command: str
) -> bytes:
    owner, _journal, _secrets = _owner_layout(repository_root, create=False)
    recorded = _private_child(owner, RECORDED_DIRECTORY, create=False)
    expected = recorded_fixture_relative_path(article_id, command).name
    return _read_private_file(
        recorded / expected,
        maximum_bytes=MAX_RECORDED_BYTES,
        missing_code=EditorialPilotFailureCode.RECORDED_EVIDENCE_REQUIRED,
    )


def rakuten_evidence_relative_path(product_id: str) -> Path:
    if type(product_id) is not str or _PRODUCT_ID.fullmatch(product_id) is None:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return Path(
        ".secrets",
        OWNER_DIRECTORY,
        RAKUTEN_DIRECTORY,
        f"{product_id}.v1.json",
    )


def source_evidence_relative_path(source_ref: str) -> Path:
    if type(source_ref) is not str or _SOURCE_REF.fullmatch(source_ref) is None:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return Path(
        ".secrets",
        OWNER_DIRECTORY,
        SOURCE_DIRECTORY,
        f"{source_ref}.v1.json",
    )


def source_body_relative_path(source_ref: str) -> Path:
    if type(source_ref) is not str or _SOURCE_REF.fullmatch(source_ref) is None:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return Path(
        ".secrets",
        OWNER_DIRECTORY,
        SOURCE_DIRECTORY,
        f"{source_ref}.body",
    )


def rakuten_response_relative_path(product_id: str) -> Path:
    if type(product_id) is not str or _PRODUCT_ID.fullmatch(product_id) is None:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return Path(
        ".secrets",
        OWNER_DIRECTORY,
        RAKUTEN_DIRECTORY,
        f"{product_id}.item-search-response.v1.json",
    )


def rakuten_affiliate_response_relative_path(product_id: str) -> Path:
    if type(product_id) is not str or _PRODUCT_ID.fullmatch(product_id) is None:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return Path(
        ".secrets",
        OWNER_DIRECTORY,
        RAKUTEN_DIRECTORY,
        f"{product_id}.affiliate-item-search-response.v1.json",
    )


def rakuten_image_relative_path(product_id: str) -> Path:
    if type(product_id) is not str or _PRODUCT_ID.fullmatch(product_id) is None:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return Path(
        ".secrets",
        OWNER_DIRECTORY,
        RAKUTEN_DIRECTORY,
        f"{product_id}.image",
    )


def _finite_decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if not parsed.is_finite():
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return parsed


def _decode_rakuten_response(raw: bytes) -> object:
    if (
        type(raw) is not bytes
        or not 1 <= len(raw) <= MAX_RAKUTEN_RESPONSE_BYTES
        or raw.startswith(b"\xef\xbb\xbf")
    ):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_finite_decimal,
            parse_constant=_reject_number,
        )
    except EditorialPilotFailure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)


def _png_scanline_layout(
    width: int, height: int, bit_depth: int, color_type: int, interlace: int
) -> tuple[tuple[int, int, int], ...]:
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    bits_per_pixel = channels * bit_depth
    if interlace == 0:
        return ((width, height, (width * bits_per_pixel + 7) // 8),)
    passes = (
        (0, 0, 8, 8),
        (4, 0, 8, 8),
        (0, 4, 4, 8),
        (2, 0, 4, 4),
        (0, 2, 2, 4),
        (1, 0, 2, 2),
        (0, 1, 1, 2),
    )
    layout: list[tuple[int, int, int]] = []
    for start_x, start_y, step_x, step_y in passes:
        pass_width = 0 if width <= start_x else (width - start_x + step_x - 1) // step_x
        pass_height = (
            0 if height <= start_y else (height - start_y + step_y - 1) // step_y
        )
        if pass_width and pass_height:
            layout.append(
                (
                    pass_width,
                    pass_height,
                    (pass_width * bits_per_pixel + 7) // 8,
                )
            )
    return tuple(layout)


def _validate_png_pixels(
    compressed: bytes,
    *,
    width: int,
    height: int,
    bit_depth: int,
    color_type: int,
    interlace: int,
    palette_entries: int | None,
) -> None:
    layout = _png_scanline_layout(width, height, bit_depth, color_type, interlace)
    expected = sum(rows * (row_bytes + 1) for _width, rows, row_bytes in layout)
    if (
        not compressed
        or not 1 <= expected <= MAX_RAKUTEN_IMAGE_BYTES
        or (
            color_type == 3
            and (
                type(palette_entries) is not int
                or not 1 <= palette_entries <= 1 << bit_depth
            )
        )
    ):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    try:
        decompressor = zlib.decompressobj()
        decoded = decompressor.decompress(compressed, expected + 1)
    except zlib.error:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if (
        len(decoded) != expected
        or not decompressor.eof
        or decompressor.unused_data
        or decompressor.unconsumed_tail
    ):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    decoded_offset = 0
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    filter_bytes_per_pixel = max(1, (channels * bit_depth + 7) // 8)
    for pass_width, rows, row_bytes in layout:
        previous = bytes(row_bytes)
        for _row in range(rows):
            filter_type = decoded[decoded_offset]
            if filter_type > 4:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            encoded = decoded[decoded_offset + 1 : decoded_offset + 1 + row_bytes]
            decoded_offset += row_bytes + 1
            if color_type != 3:
                continue
            reconstructed = bytearray(row_bytes)
            for index, value in enumerate(encoded):
                left = (
                    reconstructed[index - filter_bytes_per_pixel]
                    if index >= filter_bytes_per_pixel
                    else 0
                )
                up = previous[index]
                upper_left = (
                    previous[index - filter_bytes_per_pixel]
                    if index >= filter_bytes_per_pixel
                    else 0
                )
                if filter_type == 0:
                    predictor = 0
                elif filter_type == 1:
                    predictor = left
                elif filter_type == 2:
                    predictor = up
                elif filter_type == 3:
                    predictor = (left + up) // 2
                else:
                    estimate = left + up - upper_left
                    distances = (
                        abs(estimate - left),
                        abs(estimate - up),
                        abs(estimate - upper_left),
                    )
                    predictor = (left, up, upper_left)[distances.index(min(distances))]
                reconstructed[index] = (value + predictor) & 0xFF
            entries = cast(int, palette_entries)
            mask = (1 << bit_depth) - 1
            for pixel in range(pass_width):
                bit_offset = pixel * bit_depth
                shift = 8 - bit_depth - (bit_offset % 8)
                palette_index = (reconstructed[bit_offset // 8] >> shift) & mask
                if palette_index >= entries:
                    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            previous = bytes(reconstructed)
    if decoded_offset != len(decoded):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)


def _png_dimensions(raw: bytes) -> tuple[int, int]:
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    offset = 8
    image_header: tuple[int, int, int, int, int] | None = None
    compressed = bytearray()
    idat_closed = False
    saw_idat = False
    palette_entries: int | None = None
    while offset + 12 <= len(raw):
        length = int.from_bytes(raw[offset : offset + 4], "big")
        chunk_type = raw[offset + 4 : offset + 8]
        end = offset + 12 + length
        if (
            length > MAX_RAKUTEN_IMAGE_BYTES
            or end > len(raw)
            or any(
                not (65 <= value <= 90 or 97 <= value <= 122) for value in chunk_type
            )
            or chunk_type[2] & 0x20
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        data = raw[offset + 8 : offset + 8 + length]
        expected_crc = int.from_bytes(raw[offset + 8 + length : end], "big")
        if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != expected_crc:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        if chunk_type == b"IHDR":
            if offset != 8 or length != 13 or image_header is not None:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            width = int.from_bytes(data[0:4], "big")
            height = int.from_bytes(data[4:8], "big")
            bit_depth = data[8]
            color_type = data[9]
            valid_depths = {
                0: {1, 2, 4, 8, 16},
                2: {8, 16},
                3: {1, 2, 4, 8},
                4: {8, 16},
                6: {8, 16},
            }
            if (
                (width, height) != (128, 128)
                or color_type not in valid_depths
                or bit_depth not in valid_depths[color_type]
                or data[10:12] != b"\x00\x00"
                or data[12] not in {0, 1}
            ):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            image_header = (width, height, bit_depth, color_type, data[12])
        elif chunk_type == b"PLTE":
            if (
                image_header is None
                or saw_idat
                or palette_entries is not None
                or image_header[3] in {0, 4}
                or not 3 <= length <= 768
                or length % 3 != 0
                or (image_header[3] == 3 and length > 3 * (1 << image_header[2]))
            ):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            palette_entries = length // 3
        elif chunk_type == b"IDAT":
            if (
                image_header is None
                or idat_closed
                or (image_header[3] == 3 and palette_entries is None)
            ):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            saw_idat = True
            if len(compressed) + len(data) > MAX_RAKUTEN_IMAGE_BYTES:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            compressed.extend(data)
        elif chunk_type == b"IEND":
            if length != 0 or image_header is None or not compressed or end != len(raw):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            width, height, bit_depth, color_type, interlace = image_header
            _validate_png_pixels(
                bytes(compressed),
                width=width,
                height=height,
                bit_depth=bit_depth,
                color_type=color_type,
                interlace=interlace,
                palette_entries=palette_entries,
            )
            return width, height
        elif image_header is None:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        elif not chunk_type[0] & 0x20:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        elif saw_idat:
            idat_closed = True
        offset = end
    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)


def _gif_sub_blocks(raw: bytes, offset: int) -> tuple[bytes, int]:
    chunks: list[bytes] = []
    while offset < len(raw):
        length = raw[offset]
        offset += 1
        if length == 0:
            return b"".join(chunks), offset
        if offset + length > len(raw):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        chunks.append(raw[offset : offset + length])
        offset += length
    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)


def _validate_gif_lzw(
    data: bytes,
    *,
    minimum_code_size: int,
    expected_pixels: int,
    palette_entries: int,
) -> None:
    if (
        not data
        or not 2 <= minimum_code_size <= 8
        or not 1 <= expected_pixels <= MAX_RAKUTEN_IMAGE_BYTES
        or not 2 <= palette_entries <= 256
    ):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    clear_code = 1 << minimum_code_size
    end_code = clear_code + 1
    table: dict[int, bytes] = {}
    code_size = minimum_code_size + 1
    next_code = end_code + 1
    previous: bytes | None = None
    bit_offset = 0
    decoded_pixels = 0
    saw_clear = False

    def reset() -> None:
        nonlocal table, code_size, next_code, previous
        table = {index: bytes((index,)) for index in range(clear_code)}
        code_size = minimum_code_size + 1
        next_code = end_code + 1
        previous = None

    reset()
    while bit_offset + code_size <= len(data) * 8:
        byte_offset = bit_offset // 8
        shift = bit_offset % 8
        window = int.from_bytes(data[byte_offset : byte_offset + 3], "little")
        code = (window >> shift) & ((1 << code_size) - 1)
        bit_offset += code_size
        if code == clear_code:
            reset()
            saw_clear = True
            continue
        if not saw_clear:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        if code == end_code:
            if decoded_pixels != expected_pixels:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            return
        if previous is None:
            entry = table.get(code)
            if entry is None:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        else:
            entry = table.get(code)
            if entry is None:
                if code != next_code:
                    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
                entry = previous + previous[:1]
            if next_code < 4096:
                table[next_code] = previous + entry[:1]
                next_code += 1
                if next_code == 1 << code_size and code_size < 12:
                    code_size += 1
        if any(index >= palette_entries for index in entry):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        decoded_pixels += len(entry)
        if decoded_pixels > expected_pixels:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        previous = entry
    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)


def _gif_dimensions(raw: bytes) -> tuple[int, int]:
    if not raw.startswith((b"GIF87a", b"GIF89a")) or len(raw) < 14:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    width = int.from_bytes(raw[6:8], "little")
    height = int.from_bytes(raw[8:10], "little")
    if (width, height) != (128, 128):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    packed = raw[10]
    global_entries = 1 << ((packed & 0x07) + 1) if packed & 0x80 else 0
    offset = 13 + (3 * global_entries)
    if offset > len(raw):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    saw_image = False
    while offset < len(raw):
        introducer = raw[offset]
        offset += 1
        if introducer == 0x3B:
            if not saw_image or offset != len(raw):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            return width, height
        if introducer == 0x21:
            if offset >= len(raw):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            offset += 1
            _extension, offset = _gif_sub_blocks(raw, offset)
            continue
        if introducer != 0x2C or offset + 9 > len(raw):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        descriptor = raw[offset : offset + 9]
        offset += 9
        left = int.from_bytes(descriptor[0:2], "little")
        top = int.from_bytes(descriptor[2:4], "little")
        image_width = int.from_bytes(descriptor[4:6], "little")
        image_height = int.from_bytes(descriptor[6:8], "little")
        local_packed = descriptor[8]
        if (
            image_width < 1
            or image_height < 1
            or left + image_width > width
            or top + image_height > height
            or local_packed & 0x18
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        local_entries = 0
        if local_packed & 0x80:
            local_entries = 1 << ((local_packed & 0x07) + 1)
            offset += 3 * local_entries
        if offset >= len(raw) or not 2 <= raw[offset] <= 8:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        minimum_code_size = raw[offset]
        offset += 1
        image_data, offset = _gif_sub_blocks(raw, offset)
        _validate_gif_lzw(
            image_data,
            minimum_code_size=minimum_code_size,
            expected_pixels=image_width * image_height,
            palette_entries=local_entries or global_entries,
        )
        saw_image = True
    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)


def _jpeg_dimensions(raw: bytes) -> tuple[int, int]:
    try:
        return decoded_baseline_jpeg_dimensions(
            raw,
            maximum=MAX_RAKUTEN_IMAGE_BYTES,
            required_dimensions=(128, 128),
        )
    except ValueError:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)


def _image_dimensions(raw: bytes) -> tuple[int, int]:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return _png_dimensions(raw)
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return _gif_dimensions(raw)
    if raw.startswith(b"\xff\xd8"):
        return _jpeg_dimensions(raw)
    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)


def _validate_source_capture_body(raw: bytes, *, content_type: str) -> None:
    """Reject metadata-only captures and obviously corrupt HTML/PDF bodies."""

    if type(raw) is not bytes or not raw:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    stripped = raw.lstrip(b"\t\n\r ")
    if content_type == "application/pdf":
        if (
            not stripped.startswith(b"%PDF-")
            or len(stripped) < 16
            or not stripped.rstrip(b"\t\n\r ").endswith(b"%%EOF")
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        return
    if content_type == "text/html":
        prefix = stripped[:4096].lower()
        if (
            not (prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html"))
            or b"<html" not in prefix
            or not stripped.rstrip(b"\t\n\r ").lower().endswith(b"</html>")
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        return
    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)


def _validate_rakuten_response(
    raw: bytes, *, evidence: RakutenProductEvidence, affiliate_id_supplied: bool
) -> None:
    if type(affiliate_id_supplied) is not bool:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    expected_response_sha256 = (
        evidence.affiliate_response_sha256
        if affiliate_id_supplied
        else evidence.response_sha256
    )
    if bytes_sha256(raw) != expected_response_sha256:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    response = _mapping(_decode_rakuten_response(raw))
    aliases = {"items", "Items"} & set(response)
    summary_fields = frozenset({"count", "page", "first", "last", "hits", "pageCount"})
    if set(response) == {"Items"}:
        rows = response["Items"]
    elif len(aliases) == 1:
        alias = aliases.pop()
        expected_root = summary_fields | {alias}
        if "carrier" in response:
            expected_root = expected_root | {"carrier"}
        if frozenset(response) != expected_root or (
            "carrier" in response
            and (type(response["carrier"]) is not int or response["carrier"] != 0)
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        rows = response[alias]
    else:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if type(rows) is not list:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    provider_rows = cast(list[object], rows)
    if len(provider_rows) > 1:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if set(response) != {"Items"}:
        summary = tuple(response[field] for field in summary_fields)
        if any(type(value) is not int for value in summary):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        count = cast(int, response["count"])
        page = cast(int, response["page"])
        first = cast(int, response["first"])
        last = cast(int, response["last"])
        hits = cast(int, response["hits"])
        page_count = cast(int, response["pageCount"])
        returned = len(provider_rows)
        if (
            page != 1
            or hits != 1
            or (returned == 0 and (count, first, last, page_count) != (0, 0, 0, 0))
            or (
                returned > 0
                and (
                    count < returned
                    or first != 1
                    or last != returned
                    or page_count != min((count + hits - 1) // hits, 100)
                )
            )
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    matches: list[Mapping[str, object]] = []
    for raw_row in provider_rows:
        item = _mapping(raw_row)
        required = {
            "itemCode",
            "itemName",
            "itemUrl",
            "mediumImageUrls",
        }
        if affiliate_id_supplied:
            required.add("affiliateUrl")
        if set(item) != required:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        if item["itemCode"] == evidence.item_code:
            matches.append(item)
    if len(matches) != 1:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    selected = matches[0]
    raw_images = selected["mediumImageUrls"]
    if type(raw_images) is not list:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    image_urls: list[str] = []
    for raw_image in cast(list[object], raw_images):
        if type(raw_image) is not str:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        image_urls.append(raw_image)
    if (
        selected["itemName"] != evidence.item_name
        or image_urls.count(evidence.image_url) != 1
    ):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if affiliate_id_supplied:
        if (
            selected["itemUrl"] != evidence.destination_url
            or selected["affiliateUrl"] != evidence.destination_url
            or evidence.affiliate_selected_result_sha256
            != canonical_sha256(evidence.affiliate_identity_material())
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    elif canonical_rakuten_provider_item_url(
        selected["itemUrl"]
    ) != evidence.source_url or evidence.selected_result_sha256 != canonical_sha256(
        evidence.identity_material()
    ):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)


def read_official_source_capture_evidence(
    repository_root: Path, *, source_ref: str
) -> OfficialSourceCaptureEvidence:
    """Read one current owner capture and prove every locator exists in its raw body."""

    relative = source_evidence_relative_path(source_ref)
    owner, _secrets = _owner_base_layout(
        repository_root,
        create=False,
        missing_code=EditorialPilotFailureCode.RESOURCE_NOT_READY,
    )
    sources = _private_child(
        owner,
        SOURCE_DIRECTORY,
        create=False,
        missing_code=EditorialPilotFailureCode.RESOURCE_NOT_READY,
    )
    raw = _read_private_file(
        sources / relative.name,
        maximum_bytes=MAX_SOURCE_EVIDENCE_BYTES,
        missing_code=EditorialPilotFailureCode.RESOURCE_NOT_READY,
    )
    try:
        parsed = _mapping(
            decode_strict_json(raw, maximum_bytes=MAX_SOURCE_EVIDENCE_BYTES)
        )
        _exact_keys(
            parsed,
            {
                "body_sha256",
                "content_type",
                "final_url",
                "http_status",
                "locators",
                "response_sha256",
                "retrieved_at",
                "schema",
                "source_ref",
            },
        )
        raw_locators = parsed["locators"]
        if type(raw_locators) is not list:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        locators: list[tuple[str, str, tuple[tuple[str, str], ...]]] = []
        for raw_locator in cast(list[object], raw_locators):
            locator = _mapping(raw_locator)
            _exact_keys(
                locator,
                {
                    "claim_id",
                    "claim_statement_sha256",
                    "exact_utf8_fragments",
                },
            )
            raw_fragments = locator["exact_utf8_fragments"]
            if type(raw_fragments) is not list:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            fragments: list[tuple[str, str]] = []
            for raw_fragment in cast(list[object], raw_fragments):
                fragment = _mapping(raw_fragment)
                _exact_keys(
                    fragment,
                    {"exact_utf8_fragment", "fragment_sha256"},
                )
                fragments.append(
                    (
                        cast(str, fragment["exact_utf8_fragment"]),
                        cast(str, fragment["fragment_sha256"]),
                    )
                )
            locators.append(
                (
                    cast(str, locator["claim_id"]),
                    cast(str, locator["claim_statement_sha256"]),
                    tuple(fragments),
                )
            )
        evidence = OfficialSourceCaptureEvidence(
            schema=cast(str, parsed["schema"]),
            source_ref=cast(str, parsed["source_ref"]),
            final_url=cast(str, parsed["final_url"]),
            retrieved_at=cast(str, parsed["retrieved_at"]),
            http_status=cast(int, parsed["http_status"]),
            content_type=cast(str, parsed["content_type"]),
            body_sha256=cast(str, parsed["body_sha256"]),
            response_sha256=cast(str, parsed["response_sha256"]),
            locators=tuple(locators),
        )
    except EditorialPilotFailure as error:
        if error.code is EditorialPilotFailureCode.RESOURCE_NOT_READY:
            raise
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if evidence.source_ref != source_ref:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    body = _read_private_file(
        sources / source_body_relative_path(source_ref).name,
        maximum_bytes=MAX_SOURCE_BODY_BYTES,
        missing_code=EditorialPilotFailureCode.RESOURCE_NOT_READY,
    )
    if bytes_sha256(body) != evidence.body_sha256:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    _validate_source_capture_body(body, content_type=evidence.content_type)
    for _claim_id, _statement_sha256, locator_fragments in evidence.locators:
        for exact_fragment, _fragment_sha256 in locator_fragments:
            try:
                fragment_bytes = exact_fragment.encode("utf-8", errors="strict")
            except UnicodeError:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            if body.count(fragment_bytes) != 1:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if (
        _read_private_file(
            sources / relative.name,
            maximum_bytes=MAX_SOURCE_EVIDENCE_BYTES,
            missing_code=EditorialPilotFailureCode.RESOURCE_NOT_READY,
        )
        != raw
    ):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return evidence


def read_rakuten_product_evidence(
    repository_root: Path, *, product_id: str
) -> RakutenProductEvidence:
    """Read one exact owner-installed product resource; never fetch or discover it."""

    relative = rakuten_evidence_relative_path(product_id)
    owner, _secrets = _owner_base_layout(
        repository_root,
        create=False,
        missing_code=EditorialPilotFailureCode.RESOURCE_NOT_READY,
    )
    rakuten = _private_child(
        owner,
        RAKUTEN_DIRECTORY,
        create=False,
        missing_code=EditorialPilotFailureCode.RESOURCE_NOT_READY,
    )
    raw = _read_private_file(
        rakuten / relative.name,
        maximum_bytes=MAX_RAKUTEN_EVIDENCE_BYTES,
        missing_code=EditorialPilotFailureCode.RESOURCE_NOT_READY,
    )
    try:
        parsed = _mapping(
            decode_strict_json(raw, maximum_bytes=MAX_RAKUTEN_EVIDENCE_BYTES)
        )
        _exact_keys(
            parsed,
            {
                "affiliate_ref",
                "affiliate_request_fingerprint",
                "affiliate_response_sha256",
                "affiliate_selected_result_sha256",
                "destination_url",
                "height",
                "image_sha256",
                "image_url",
                "item_code",
                "item_name",
                "jan",
                "media_asset_ref",
                "no_modification_policy",
                "product_id",
                "request_fingerprint",
                "response_sha256",
                "retrieved_at",
                "schema",
                "selected_result_sha256",
                "source_url",
                "variant",
                "width",
            },
        )
        policy = _mapping(parsed["no_modification_policy"])
        _exact_keys(
            policy,
            {
                "aspect_ratio_change_allowed",
                "crop_allowed",
                "modification_allowed",
                "text_overlay_allowed",
                "upscale_allowed",
            },
        )
        if any(type(value) is not bool for value in policy.values()):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        evidence = RakutenProductEvidence(
            schema=cast(str, parsed["schema"]),
            product_id=cast(str, parsed["product_id"]),
            affiliate_ref=cast(str, parsed["affiliate_ref"]),
            affiliate_request_fingerprint=cast(
                str, parsed["affiliate_request_fingerprint"]
            ),
            affiliate_response_sha256=cast(str, parsed["affiliate_response_sha256"]),
            affiliate_selected_result_sha256=cast(
                str, parsed["affiliate_selected_result_sha256"]
            ),
            media_asset_ref=cast(str, parsed["media_asset_ref"]),
            item_code=cast(str, parsed["item_code"]),
            item_name=cast(str, parsed["item_name"]),
            jan=cast(str | None, parsed["jan"]),
            variant=cast(str, parsed["variant"]),
            source_url=cast(str, parsed["source_url"]),
            destination_url=cast(str, parsed["destination_url"]),
            image_url=cast(str, parsed["image_url"]),
            width=cast(int, parsed["width"]),
            height=cast(int, parsed["height"]),
            retrieved_at=cast(str, parsed["retrieved_at"]),
            request_fingerprint=cast(str, parsed["request_fingerprint"]),
            response_sha256=cast(str, parsed["response_sha256"]),
            selected_result_sha256=cast(str, parsed["selected_result_sha256"]),
            image_sha256=cast(str, parsed["image_sha256"]),
            no_modification_policy=tuple(sorted(cast(dict[str, bool], policy).items())),
        )
    except EditorialPilotFailure as error:
        if error.code is EditorialPilotFailureCode.RESOURCE_NOT_READY:
            raise
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if evidence.product_id != product_id:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    response_raw = _read_private_file(
        rakuten / rakuten_response_relative_path(product_id).name,
        maximum_bytes=MAX_RAKUTEN_RESPONSE_BYTES,
        missing_code=EditorialPilotFailureCode.RESOURCE_NOT_READY,
    )
    _validate_rakuten_response(
        response_raw, evidence=evidence, affiliate_id_supplied=False
    )
    affiliate_response_raw = _read_private_file(
        rakuten / rakuten_affiliate_response_relative_path(product_id).name,
        maximum_bytes=MAX_RAKUTEN_RESPONSE_BYTES,
        missing_code=EditorialPilotFailureCode.RESOURCE_NOT_READY,
    )
    _validate_rakuten_response(
        affiliate_response_raw, evidence=evidence, affiliate_id_supplied=True
    )
    image_raw = _read_private_file(
        rakuten / rakuten_image_relative_path(product_id).name,
        maximum_bytes=MAX_RAKUTEN_IMAGE_BYTES,
        missing_code=EditorialPilotFailureCode.RESOURCE_NOT_READY,
    )
    if bytes_sha256(image_raw) != evidence.image_sha256 or _image_dimensions(
        image_raw
    ) != (evidence.width, evidence.height):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return evidence


def _journal_material(
    request: ReviewDraftRequest,
    *,
    state: str,
    create_response_sha256: str,
    recovery_response_sha256: str | None,
    draft_id: int | None,
    committed_response_sha256: str | None,
) -> dict[str, object]:
    return {
        "article_id": request.article_id,
        "committed_response_sha256": committed_response_sha256,
        "create_response_sha256": create_response_sha256,
        "draft_id": draft_id,
        "packet_sha256": request.packet_sha256,
        "recovery_response_sha256": recovery_response_sha256,
        "request_sha256": request.request_sha256,
        "schema": _JOURNAL_SCHEMA,
        "state": state,
    }


def _journal_document(material: dict[str, object]) -> dict[str, object]:
    return {**material, "integrity_sha256": canonical_sha256(material)}


def _decode_journal(raw: bytes, request: ReviewDraftRequest) -> dict[str, object]:
    document = _mapping(decode_strict_json(raw, maximum_bytes=MAX_JOURNAL_BYTES))
    _exact_keys(
        document,
        {
            "article_id",
            "committed_response_sha256",
            "create_response_sha256",
            "draft_id",
            "integrity_sha256",
            "packet_sha256",
            "recovery_response_sha256",
            "request_sha256",
            "schema",
            "state",
        },
    )
    material = {
        key: value for key, value in document.items() if key != "integrity_sha256"
    }
    if (
        document["schema"] != _JOURNAL_SCHEMA
        or document["article_id"] != request.article_id
        or document["packet_sha256"] != request.packet_sha256
        or document["request_sha256"] != request.request_sha256
        or document["state"] not in {"INTENT", "RECOVERY_ATTEMPTED", "COMMITTED"}
        or document["integrity_sha256"] != canonical_sha256(material)
    ):
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    require_sha256(document["create_response_sha256"])
    recovery_digest = document["recovery_response_sha256"]
    committed_digest = document["committed_response_sha256"]
    if recovery_digest is not None:
        require_sha256(recovery_digest)
    if committed_digest is not None:
        require_sha256(committed_digest)
    state = document["state"]
    draft_id = document["draft_id"]
    if state == "COMMITTED":
        _positive_post_id(draft_id)
        if committed_digest is None:
            _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    elif draft_id is not None or committed_digest is not None:
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    if state == "INTENT" and recovery_digest is not None:
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    if state == "RECOVERY_ATTEMPTED" and recovery_digest is None:
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    return dict(document)


def _write_private_atomic(path: Path, document: dict[str, object]) -> None:
    payload = canonical_json_bytes(document) + b"\n"
    if len(payload) > MAX_JOURNAL_BYTES:
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    parent = path.parent
    stage = parent / f".{path.name}.preparing"
    descriptor = -1
    try:
        descriptor = os.open(
            stage,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            _PRIVATE_FILE_MODE,
        )
        os.fchmod(descriptor, _PRIVATE_FILE_MODE)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
            offset += written
        os.fsync(descriptor)
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != os.getuid()
            or stat.S_IMODE(observed.st_mode) != _PRIVATE_FILE_MODE
            or observed.st_nlink != 1
            or observed.st_size != len(payload)
        ):
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        os.close(descriptor)
        descriptor = -1
        os.replace(stage, path)
        parent_descriptor = os.open(
            parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    except EditorialPilotFailure:
        raise
    except OSError:
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            stage.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)


def _write_private_immutable(path: Path, document: dict[str, object]) -> bytes:
    payload = canonical_json_bytes(document) + b"\n"
    if len(payload) > MAX_REQUEST_ARTIFACT_BYTES:
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    parent = path.parent
    stage = parent / f".{path.name}.preparing"
    descriptor = -1
    installed = False
    try:
        descriptor = os.open(
            stage,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            _PRIVATE_FILE_MODE,
        )
        os.fchmod(descriptor, _PRIVATE_FILE_MODE)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
            offset += written
        os.fsync(descriptor)
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != os.getuid()
            or stat.S_IMODE(observed.st_mode) != _PRIVATE_FILE_MODE
            or observed.st_nlink != 1
            or observed.st_size != len(payload)
        ):
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        os.close(descriptor)
        descriptor = -1
        os.link(stage, path, follow_symlinks=False)
        installed = True
        stage.unlink()
        parent_descriptor = os.open(
            parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    except EditorialPilotFailure:
        raise
    except FileExistsError:
        _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
    except OSError:
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not installed:
            try:
                stage.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    observed_payload = _read_private_file(
        path,
        maximum_bytes=MAX_REQUEST_ARTIFACT_BYTES,
        missing_code=EditorialPilotFailureCode.JOURNAL_UNSAFE,
    )
    if observed_payload != payload:
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    return payload


@contextmanager
def _journal_lock(path: Path) -> Generator[None, None, None]:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            _PRIVATE_FILE_MODE,
        )
        os.fchmod(descriptor, _PRIVATE_FILE_MODE)
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != os.getuid()
            or stat.S_IMODE(observed.st_mode) != _PRIVATE_FILE_MODE
            or observed.st_nlink != 1
        ):
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except EditorialPilotFailure:
        raise
    except OSError:
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    finally:
        if descriptor >= 0:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(descriptor)


@final
class OwnerPrivateReviewDraftJournal:
    """Digest-keyed no-resend journal for recorded-only draft evidence."""

    __slots__ = ("_attempt", "_root")

    def __init__(
        self,
        repository_root: Path,
        recorded_port: RecordedReviewDraftPort,
    ) -> None:
        if not repository_root.is_absolute() or not isinstance(
            cast(object, recorded_port), RecordedReviewDraftPort
        ):
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        self._root = repository_root
        self._attempt = recorded_port

    def _paths(self, request: ReviewDraftRequest) -> tuple[Path, Path]:
        _owner, journal, _secrets = _owner_layout(self._root, create=True)
        name = f"{request.article_id}.{request.packet_sha256}.v1.json"
        return journal / name, journal / LOCK_FILE

    def _replay(
        self, request: ReviewDraftRequest, state: Mapping[str, object]
    ) -> ReviewDraftReceipt:
        return ReviewDraftReceipt(
            article_id=request.article_id,
            packet_sha256=request.packet_sha256,
            request_sha256=request.request_sha256,
            response_sha256=cast(str, state["committed_response_sha256"]),
            draft_id=cast(int, state["draft_id"]),
            disposition=ReviewDraftDisposition.LOCAL_REPLAY,
        )

    def create(
        self, request: ReviewDraftRequest, recorded_response: bytes
    ) -> ReviewDraftReceipt:
        if (
            type(request) is not ReviewDraftRequest
            or type(recorded_response) is not bytes
        ):
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        journal_path, lock_path = self._paths(request)
        create_digest = bytes_sha256(recorded_response)
        with _journal_lock(lock_path):
            if journal_path.exists() or journal_path.is_symlink():
                state = _decode_journal(
                    _read_private_file(
                        journal_path,
                        maximum_bytes=MAX_JOURNAL_BYTES,
                        missing_code=EditorialPilotFailureCode.JOURNAL_UNSAFE,
                    ),
                    request,
                )
                if state["state"] == "COMMITTED":
                    return self._replay(request, state)
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            intent = _journal_material(
                request,
                state="INTENT",
                create_response_sha256=create_digest,
                recovery_response_sha256=None,
                draft_id=None,
                committed_response_sha256=None,
            )
            _write_private_atomic(journal_path, _journal_document(intent))
            receipt = self._attempt.create(request, recorded_response)
            if (
                receipt.article_id != request.article_id
                or receipt.packet_sha256 != request.packet_sha256
                or receipt.request_sha256 != request.request_sha256
                or receipt.response_sha256 != create_digest
                or receipt.disposition is not ReviewDraftDisposition.RECORDED_CREATED
            ):
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            committed = _journal_material(
                request,
                state="COMMITTED",
                create_response_sha256=create_digest,
                recovery_response_sha256=None,
                draft_id=receipt.draft_id,
                committed_response_sha256=receipt.response_sha256,
            )
            _write_private_atomic(journal_path, _journal_document(committed))
            return receipt

    def recover(
        self, request: ReviewDraftRequest, recorded_response: bytes
    ) -> ReviewDraftReceipt:
        if (
            type(request) is not ReviewDraftRequest
            or type(recorded_response) is not bytes
        ):
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        journal_path, lock_path = self._paths(request)
        recovery_digest = bytes_sha256(recorded_response)
        with _journal_lock(lock_path):
            if not journal_path.exists() or journal_path.is_symlink():
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            state = _decode_journal(
                _read_private_file(
                    journal_path,
                    maximum_bytes=MAX_JOURNAL_BYTES,
                    missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
                ),
                request,
            )
            if state["state"] == "COMMITTED":
                return self._replay(request, state)
            if state["state"] != "INTENT":
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            attempted = _journal_material(
                request,
                state="RECOVERY_ATTEMPTED",
                create_response_sha256=cast(str, state["create_response_sha256"]),
                recovery_response_sha256=recovery_digest,
                draft_id=None,
                committed_response_sha256=None,
            )
            _write_private_atomic(journal_path, _journal_document(attempted))
            receipt = self._attempt.recover(request, recorded_response)
            if (
                receipt.article_id != request.article_id
                or receipt.packet_sha256 != request.packet_sha256
                or receipt.request_sha256 != request.request_sha256
                or receipt.response_sha256 != recovery_digest
                or receipt.disposition is not ReviewDraftDisposition.RECORDED_RECOVERED
            ):
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            committed = _journal_material(
                request,
                state="COMMITTED",
                create_response_sha256=cast(str, state["create_response_sha256"]),
                recovery_response_sha256=recovery_digest,
                draft_id=receipt.draft_id,
                committed_response_sha256=receipt.response_sha256,
            )
            _write_private_atomic(journal_path, _journal_document(committed))
            return receipt


def _request_artifact_name_for(
    article_id: str, packet_sha256: str, request_sha256: str
) -> str:
    article_identity(article_id)
    require_sha256(packet_sha256)
    require_sha256(request_sha256)
    return f"{article_id}.{packet_sha256}.{request_sha256}.request.v1.json"


def request_artifact_relative_path(request: ReviewDraftRequest) -> Path:
    if type(request) is not ReviewDraftRequest:
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    return Path(
        ".secrets",
        OWNER_DIRECTORY,
        REQUEST_DIRECTORY,
        _request_artifact_name_for(
            request.article_id, request.packet_sha256, request.request_sha256
        ),
    )


def _request_artifact_material(request: ReviewDraftRequest) -> dict[str, object]:
    return {
        "article_id": request.article_id,
        "packet_sha256": request.packet_sha256,
        "request": {
            "content": request.content,
            "excerpt": request.excerpt,
            "origin": request.origin,
            "path": request.path,
            "slug": request.slug,
            "snapshot": request.snapshot.value(),
            "status": request.status,
            "title": request.title,
        },
        "request_sha256": request.request_sha256,
        "schema": _REQUEST_ARTIFACT_SCHEMA,
    }


def _request_artifact_document(request: ReviewDraftRequest) -> dict[str, object]:
    material = _request_artifact_material(request)
    return {**material, "integrity_sha256": canonical_sha256(material)}


def _decode_request_artifact(
    raw: bytes, *, expected_article_id: str
) -> tuple[ReviewDraftRequest, str]:
    try:
        article_identity(expected_article_id)
        document = _mapping(
            decode_strict_json(raw, maximum_bytes=MAX_REQUEST_ARTIFACT_BYTES)
        )
        _exact_keys(
            document,
            {
                "article_id",
                "integrity_sha256",
                "packet_sha256",
                "request",
                "request_sha256",
                "schema",
            },
        )
        material = {
            key: value for key, value in document.items() if key != "integrity_sha256"
        }
        if (
            raw != canonical_json_bytes(dict(document)) + b"\n"
            or document["schema"] != _REQUEST_ARTIFACT_SCHEMA
            or document["article_id"] != expected_article_id
            or document["integrity_sha256"] != canonical_sha256(material)
        ):
            _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
        packet_sha256 = require_sha256(document["packet_sha256"])
        request_sha256 = require_sha256(document["request_sha256"])
        stored = _mapping(document["request"])
        _exact_keys(
            stored,
            {
                "content",
                "excerpt",
                "origin",
                "path",
                "slug",
                "snapshot",
                "status",
                "title",
            },
        )
        snapshot_document = _mapping(stored["snapshot"])
        _exact_keys(snapshot_document, {"payload", "payload_sha256", "schema"})
        payload_document = _mapping(snapshot_document["payload"])
        _exact_keys(
            payload_document,
            {
                "article_id",
                "author_name",
                "canonical_url",
                "description",
                "modified_at",
                "og_description",
                "og_title",
                "packet_sha256",
                "published_at",
                "section",
                "seo_title",
                "slug",
                "title",
                "visible_content_sha256",
            },
        )
        payload = PublicationSnapshotPayload(
            article_id=cast(str, payload_document["article_id"]),
            packet_sha256=cast(str, payload_document["packet_sha256"]),
            slug=cast(str, payload_document["slug"]),
            title=cast(str, payload_document["title"]),
            seo_title=cast(str, payload_document["seo_title"]),
            description=cast(str, payload_document["description"]),
            canonical_url=cast(str, payload_document["canonical_url"]),
            og_title=cast(str, payload_document["og_title"]),
            og_description=cast(str, payload_document["og_description"]),
            published_at=cast(str | None, payload_document["published_at"]),
            modified_at=cast(str | None, payload_document["modified_at"]),
            author_name=cast(str, payload_document["author_name"]),
            section=cast(str, payload_document["section"]),
            visible_content_sha256=cast(
                str, payload_document["visible_content_sha256"]
            ),
        )
        snapshot = PublicationSnapshot(
            payload=payload,
            payload_sha256=cast(str, snapshot_document["payload_sha256"]),
            schema=cast(str, snapshot_document["schema"]),
        )
        request = ReviewDraftRequest.bind(
            article_id=expected_article_id,
            packet_sha256=packet_sha256,
            title=cast(str, stored["title"]),
            public_slug=payload.slug,
            excerpt=cast(str, stored["excerpt"]),
            content=cast(str, stored["content"]),
            snapshot=snapshot,
        )
        if (
            request.request_sha256 != request_sha256
            or request.origin != stored["origin"]
            or request.path != stored["path"]
            or request.slug != stored["slug"]
            or request.status != stored["status"]
            or _request_artifact_material(request) != material
        ):
            _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    except EditorialPilotFailure as error:
        if error.code in {
            EditorialPilotFailureCode.JOURNAL_MISMATCH,
            EditorialPilotFailureCode.JOURNAL_UNSAFE,
        }:
            raise
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    except TypeError, ValueError, KeyError, UnicodeError:
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    return request, bytes_sha256(raw)


def _request_artifact_candidates(directory: Path, article_id: str) -> list[Path]:
    article_identity(article_id)
    prefix = article_id + "."
    pattern = re.compile(
        re.escape(prefix) + r"[0-9a-f]{64}\.[0-9a-f]{64}\.request\.v1\.json\Z",
        re.ASCII,
    )
    try:
        candidates: list[Path] = []
        for path in directory.iterdir():
            if not path.name.startswith(prefix):
                continue
            if pattern.fullmatch(path.name) is None:
                _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
            candidates.append(path)
    except EditorialPilotFailure:
        raise
    except OSError:
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    return sorted(candidates, key=lambda value: value.name)


def _ensure_request_artifact(
    repository_root: Path, request: ReviewDraftRequest
) -> tuple[str, str]:
    directory = _request_layout(
        repository_root,
        create=True,
        missing_code=EditorialPilotFailureCode.JOURNAL_UNSAFE,
    )
    name = request_artifact_relative_path(request).name
    candidates = _request_artifact_candidates(directory, request.article_id)
    exact = [candidate for candidate in candidates if candidate.name == name]
    if exact:
        if len(exact) != 1:
            _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
        raw = _read_private_file(
            exact[0],
            maximum_bytes=MAX_REQUEST_ARTIFACT_BYTES,
            missing_code=EditorialPilotFailureCode.JOURNAL_UNSAFE,
        )
        observed, artifact_sha256 = _decode_request_artifact(
            raw, expected_article_id=request.article_id
        )
        if observed != request:
            _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
        return name, artifact_sha256
    payload = _write_private_immutable(
        directory / name, _request_artifact_document(request)
    )
    observed, artifact_sha256 = _decode_request_artifact(
        payload, expected_article_id=request.article_id
    )
    if observed != request:
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    return name, artifact_sha256


def _live_journal_material(
    request: ReviewDraftRequest,
    *,
    state: str,
    response_sha256: str | None,
    draft_id: int | None,
    target_public_post_id: int | None,
    request_artifact_name: str,
    request_artifact_sha256: str,
) -> dict[str, object]:
    return {
        "article_id": request.article_id,
        "draft_id": draft_id,
        "packet_sha256": request.packet_sha256,
        "request_artifact_name": request_artifact_name,
        "request_artifact_sha256": request_artifact_sha256,
        "request_sha256": request.request_sha256,
        "response_sha256": response_sha256,
        "schema": _LIVE_JOURNAL_SCHEMA,
        "state": state,
        "target_public_post_id": target_public_post_id,
    }


def _decode_live_journal_header_unchecked(
    raw: bytes, *, expected_article_id: str
) -> dict[str, object]:
    document = _mapping(decode_strict_json(raw, maximum_bytes=MAX_JOURNAL_BYTES))
    _exact_keys(
        document,
        {
            "article_id",
            "draft_id",
            "integrity_sha256",
            "packet_sha256",
            "request_artifact_name",
            "request_artifact_sha256",
            "request_sha256",
            "response_sha256",
            "schema",
            "state",
            "target_public_post_id",
        },
    )
    material = {
        key: value for key, value in document.items() if key != "integrity_sha256"
    }
    state = document["state"]
    packet_sha256 = require_sha256(document["packet_sha256"])
    request_sha256 = require_sha256(document["request_sha256"])
    request_artifact_sha256 = require_sha256(document["request_artifact_sha256"])
    expected_artifact_name = _request_artifact_name_for(
        expected_article_id, packet_sha256, request_sha256
    )
    if (
        raw != canonical_json_bytes(dict(document)) + b"\n"
        or document["schema"] != _LIVE_JOURNAL_SCHEMA
        or document["article_id"] != expected_article_id
        or document["request_artifact_name"] != expected_artifact_name
        or state not in {"INTENT", "RECOVERY_ATTEMPTED", "COMMITTED"}
        or document["integrity_sha256"] != canonical_sha256(material)
    ):
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    response_sha256 = document["response_sha256"]
    draft_id = document["draft_id"]
    target_public_post_id = document["target_public_post_id"]
    if (
        expected_article_id == "st1703-first-suitcase-comparison"
        and _positive_post_id(target_public_post_id) <= 0
    ) or (
        expected_article_id != "st1703-first-suitcase-comparison"
        and target_public_post_id is not None
    ):
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    if state == "COMMITTED":
        require_sha256(response_sha256)
        _positive_post_id(draft_id)
    elif response_sha256 is not None or draft_id is not None:
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    del request_artifact_sha256
    return dict(document)


def _decode_live_journal_header(
    raw: bytes, *, expected_article_id: str
) -> dict[str, object]:
    try:
        return _decode_live_journal_header_unchecked(
            raw, expected_article_id=expected_article_id
        )
    except EditorialPilotFailure as error:
        if error.code in {
            EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
            EditorialPilotFailureCode.JOURNAL_MISMATCH,
            EditorialPilotFailureCode.JOURNAL_UNSAFE,
        }:
            raise
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    except TypeError, ValueError, KeyError, UnicodeError:
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)


def _decode_live_journal(
    raw: bytes,
    request: ReviewDraftRequest,
    *,
    request_artifact_name: str,
    request_artifact_sha256: str,
) -> dict[str, object]:
    document = _decode_live_journal_header(raw, expected_article_id=request.article_id)
    if (
        document["packet_sha256"] != request.packet_sha256
        or document["request_sha256"] != request.request_sha256
        or document["request_artifact_name"] != request_artifact_name
        or document["request_artifact_sha256"] != request_artifact_sha256
    ):
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    return document


def _live_journal_name_for(article_id: str, packet_sha256: str) -> str:
    article_identity(article_id)
    require_sha256(packet_sha256)
    return f"{article_id}.{packet_sha256}.live.v1.json"


def _live_journal_candidates(directory: Path, article_id: str) -> list[Path]:
    article_identity(article_id)
    prefix = article_id + "."
    pattern = re.compile(
        re.escape(prefix) + r"[0-9a-f]{64}\.live\.v1\.json\Z",
        re.ASCII,
    )
    try:
        candidates: list[Path] = []
        for path in directory.iterdir():
            if not path.name.startswith(prefix) or not path.name.endswith(
                ".live.v1.json"
            ):
                continue
            if pattern.fullmatch(path.name) is None:
                _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
            candidates.append(path)
    except EditorialPilotFailure:
        raise
    except OSError:
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    return sorted(candidates, key=lambda value: value.name)


def _load_exact_request_artifact(
    repository_root: Path,
    request: ReviewDraftRequest,
    *,
    missing_code: EditorialPilotFailureCode,
) -> tuple[str, str]:
    directory = _request_layout(
        repository_root,
        create=False,
        missing_code=missing_code,
    )
    name = request_artifact_relative_path(request).name
    raw = _read_private_file(
        directory / name,
        maximum_bytes=MAX_REQUEST_ARTIFACT_BYTES,
        missing_code=missing_code,
    )
    observed, artifact_sha256 = _decode_request_artifact(
        raw, expected_article_id=request.article_id
    )
    if observed != request:
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    return name, artifact_sha256


def _load_journal_bound_request_locked(
    repository_root: Path,
    journal_directory: Path,
    *,
    article_id: str,
    required_state: str,
) -> tuple[ReviewDraftRequest, dict[str, object]]:
    if required_state not in {"INTENT", "COMMITTED"}:
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    candidates = _live_journal_candidates(journal_directory, article_id)
    if len(candidates) != 1:
        _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
    journal_raw = _read_private_file(
        candidates[0],
        maximum_bytes=MAX_JOURNAL_BYTES,
        missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
    )
    header = _decode_live_journal_header(journal_raw, expected_article_id=article_id)
    if (
        candidates[0].name
        != _live_journal_name_for(article_id, cast(str, header["packet_sha256"]))
        or header["state"] != required_state
    ):
        _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
    request_directory = _request_layout(
        repository_root,
        create=False,
        missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
    )
    artifact_name = cast(str, header["request_artifact_name"])
    artifact_raw = _read_private_file(
        request_directory / artifact_name,
        maximum_bytes=MAX_REQUEST_ARTIFACT_BYTES,
        missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
    )
    request, artifact_sha256 = _decode_request_artifact(
        artifact_raw, expected_article_id=article_id
    )
    if artifact_sha256 != header["request_artifact_sha256"]:
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    state = _decode_live_journal(
        journal_raw,
        request,
        request_artifact_name=artifact_name,
        request_artifact_sha256=artifact_sha256,
    )
    return request, state


def _load_terminal_reconciliation_request_read_only(
    repository_root: Path,
    journal_directory: Path,
    *,
    article_id: str,
) -> tuple[ReviewDraftRequest, dict[str, object], str]:
    """Read the sole terminal exception without creating or locking journal state."""

    if article_id != PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID:
        _fail(EditorialPilotFailureCode.OPERATION_NOT_ALLOWED)
    candidates = _live_journal_candidates(journal_directory, article_id)
    if len(candidates) != 1:
        _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
    journal_path = candidates[0]
    journal_raw = _read_private_file(
        journal_path,
        maximum_bytes=MAX_JOURNAL_BYTES,
        missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
    )
    header = _decode_live_journal_header(journal_raw, expected_article_id=article_id)
    if (
        journal_path.name
        != _live_journal_name_for(article_id, cast(str, header["packet_sha256"]))
        or header["state"] != "RECOVERY_ATTEMPTED"
    ):
        _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
    request_directory = _request_layout(
        repository_root,
        create=False,
        missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
    )
    artifact_name = cast(str, header["request_artifact_name"])
    artifact_candidates = _request_artifact_candidates(request_directory, article_id)
    if len(artifact_candidates) != 1 or artifact_candidates[0].name != artifact_name:
        _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
    artifact_path = artifact_candidates[0]
    artifact_raw = _read_private_file(
        artifact_path,
        maximum_bytes=MAX_REQUEST_ARTIFACT_BYTES,
        missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
    )
    request, artifact_sha256 = _decode_request_artifact(
        artifact_raw, expected_article_id=article_id
    )
    if artifact_sha256 != header["request_artifact_sha256"]:
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    state = _decode_live_journal(
        journal_raw,
        request,
        request_artifact_name=artifact_name,
        request_artifact_sha256=artifact_sha256,
    )
    if (
        _read_private_file(
            journal_path,
            maximum_bytes=MAX_JOURNAL_BYTES,
            missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
        )
        != journal_raw
        or _read_private_file(
            artifact_path,
            maximum_bytes=MAX_REQUEST_ARTIFACT_BYTES,
            missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
        )
        != artifact_raw
        or _live_journal_candidates(journal_directory, article_id) != candidates
        or _request_artifact_candidates(request_directory, article_id)
        != artifact_candidates
    ):
        _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
    return request, state, artifact_sha256


def _generation_ledger_name_for(article_id: str) -> str:
    article_identity(article_id)
    return f"{article_id}.generations.v1.json"


def _generation_entry(
    request: ReviewDraftRequest,
    *,
    generation: int,
    predecessor_generation: int | None,
    operation_sha256: str | None,
    outcome: str,
    response_sha256: str | None,
    request_artifact_name: str,
    request_artifact_sha256: str,
) -> dict[str, object]:
    return {
        "generation": generation,
        "operation_sha256": operation_sha256,
        "outcome": outcome,
        "packet_sha256": request.packet_sha256,
        "predecessor_generation": predecessor_generation,
        "request_artifact_name": request_artifact_name,
        "request_artifact_sha256": request_artifact_sha256,
        "request_sha256": request.request_sha256,
        "response_sha256": response_sha256,
    }


def _generation_ledger_material(
    *,
    article_id: str,
    draft_id: int,
    active_generation: int,
    generations: list[dict[str, object]],
    pending: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "active_generation": active_generation,
        "article_id": article_id,
        "draft_id": draft_id,
        "generations": generations,
        "pending": pending,
        "schema": _GENERATION_LEDGER_SCHEMA,
    }


def _decode_generation_ledger(
    raw: bytes, *, expected_article_id: str
) -> dict[str, object]:
    """Decode the small mutable pointer ledger without trusting its artifacts."""

    try:
        document = _mapping(decode_strict_json(raw, maximum_bytes=MAX_JOURNAL_BYTES))
        _exact_keys(
            document,
            {
                "active_generation",
                "article_id",
                "draft_id",
                "generations",
                "integrity_sha256",
                "pending",
                "schema",
            },
        )
        material = {
            key: value for key, value in document.items() if key != "integrity_sha256"
        }
        draft_id = _positive_post_id(document["draft_id"])
        active_generation = document["active_generation"]
        generations_value = document["generations"]
        if (
            raw != canonical_json_bytes(dict(document)) + b"\n"
            or document["schema"] != _GENERATION_LEDGER_SCHEMA
            or document["article_id"] != expected_article_id
            or document["integrity_sha256"] != canonical_sha256(material)
            or type(active_generation) is not int
            or type(generations_value) is not list
            or not 1 <= len(generations_value) <= _MAX_REVIEW_DRAFT_GENERATIONS
            or not 1 <= active_generation <= len(generations_value)
        ):
            _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
        del draft_id
        entries: list[dict[str, object]] = []
        simulated_active = 1
        pending_entries = 0
        completed_outcomes = {
            disposition.value for disposition in ReviewDraftRevisionDisposition
        }
        for expected_generation, raw_entry in enumerate(generations_value, start=1):
            entry = _mapping(raw_entry)
            _exact_keys(
                entry,
                {
                    "generation",
                    "operation_sha256",
                    "outcome",
                    "packet_sha256",
                    "predecessor_generation",
                    "request_artifact_name",
                    "request_artifact_sha256",
                    "request_sha256",
                    "response_sha256",
                },
            )
            packet_sha256 = require_sha256(entry["packet_sha256"])
            request_sha256 = require_sha256(entry["request_sha256"])
            artifact_sha256 = require_sha256(entry["request_artifact_sha256"])
            if (
                entry["generation"] != expected_generation
                or entry["request_artifact_name"]
                != _request_artifact_name_for(
                    expected_article_id, packet_sha256, request_sha256
                )
            ):
                _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
            operation_sha256 = entry["operation_sha256"]
            predecessor_generation = entry["predecessor_generation"]
            response_sha256 = entry["response_sha256"]
            outcome = entry["outcome"]
            if expected_generation == 1:
                if (
                    predecessor_generation is not None
                    or operation_sha256 is not None
                    or outcome != "LEGACY_COMMITTED"
                ):
                    _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
                require_sha256(response_sha256)
            else:
                require_sha256(operation_sha256)
                if (
                    type(predecessor_generation) is not int
                    or predecessor_generation != simulated_active
                    or not 1 <= predecessor_generation < expected_generation
                    or outcome not in completed_outcomes | {"PENDING"}
                ):
                    _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
                if outcome == "PENDING":
                    pending_entries += 1
                    if (
                        expected_generation != len(generations_value)
                        or response_sha256 is not None
                    ):
                        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
                else:
                    require_sha256(response_sha256)
                    if (
                        outcome
                        != ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_PREDECESSOR.value
                    ):
                        simulated_active = expected_generation
            del artifact_sha256
            entries.append(dict(entry))
        pending_value = document["pending"]
        if pending_value is None:
            if pending_entries != 0:
                _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
        else:
            pending = _mapping(pending_value)
            _exact_keys(
                pending,
                {
                    "operation_sha256",
                    "predecessor_generation",
                    "state",
                    "successor_generation",
                },
            )
            successor_generation = pending["successor_generation"]
            if (
                pending_entries != 1
                or pending["state"] not in {"PROPOSED", "ATTEMPTED"}
                or type(successor_generation) is not int
                or successor_generation != len(entries)
                or pending["predecessor_generation"] != simulated_active
                or pending["operation_sha256"]
                != entries[successor_generation - 1]["operation_sha256"]
                or pending["predecessor_generation"]
                != entries[successor_generation - 1]["predecessor_generation"]
            ):
                _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
            require_sha256(pending["operation_sha256"])
        if simulated_active != active_generation:
            _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
        active_outcome = entries[active_generation - 1]["outcome"]
        if active_outcome in {
            "PENDING",
            ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_PREDECESSOR.value,
        }:
            _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
        return dict(document)
    except EditorialPilotFailure as error:
        if error.code in {
            EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
            EditorialPilotFailureCode.JOURNAL_MISMATCH,
            EditorialPilotFailureCode.JOURNAL_UNSAFE,
        }:
            raise
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    except TypeError, ValueError, KeyError, IndexError, UnicodeError:
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)


def _optional_private_directory(parent: Path, name: str) -> Path | None:
    path = parent / name
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    _require_safe_existing_directory(path, exact_mode=_PRIVATE_DIRECTORY_MODE)
    return path


def _optional_generation_ledger_path(
    generation_directory: Path | None, article_id: str
) -> Path | None:
    if generation_directory is None:
        return None
    path = generation_directory / _generation_ledger_name_for(article_id)
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
    return path


def _request_for_generation_entry(
    repository_root: Path,
    *,
    article_id: str,
    entry: Mapping[str, object],
) -> ReviewDraftRequest:
    request_directory = _request_layout(
        repository_root,
        create=False,
        missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
    )
    artifact_name = cast(str, entry["request_artifact_name"])
    raw = _read_private_file(
        request_directory / artifact_name,
        maximum_bytes=MAX_REQUEST_ARTIFACT_BYTES,
        missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
    )
    request, artifact_sha256 = _decode_request_artifact(
        raw, expected_article_id=article_id
    )
    if (
        artifact_sha256 != entry["request_artifact_sha256"]
        or request.packet_sha256 != entry["packet_sha256"]
        or request.request_sha256 != entry["request_sha256"]
    ):
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    return request


def _binding_for_generation(
    requests: list[ReviewDraftRequest],
    entries: list[dict[str, object]],
    *,
    draft_id: int,
    generation: int,
) -> ReviewDraftRevisionBinding:
    if not 2 <= generation <= len(entries):
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    entry = entries[generation - 1]
    predecessor_generation = entry["predecessor_generation"]
    if type(predecessor_generation) is not int:
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    return ReviewDraftRevisionBinding(
        predecessor=requests[predecessor_generation - 1],
        successor=requests[generation - 1],
        draft_id=draft_id,
        generation=generation,
        operation_sha256=cast(str, entry["operation_sha256"]),
    )


def _load_generation_ledger_locked(
    repository_root: Path,
    journal_directory: Path,
    generation_path: Path,
    *,
    article_id: str,
) -> tuple[dict[str, object], list[dict[str, object]], list[ReviewDraftRequest]]:
    raw = _read_private_file(
        generation_path,
        maximum_bytes=MAX_JOURNAL_BYTES,
        missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
    )
    document = _decode_generation_ledger(raw, expected_article_id=article_id)
    entries = [
        dict(_mapping(value)) for value in cast(list[object], document["generations"])
    ]
    requests = [
        _request_for_generation_entry(
            repository_root, article_id=article_id, entry=entry
        )
        for entry in entries
    ]
    legacy_request, legacy_state = _load_journal_bound_request_locked(
        repository_root,
        journal_directory,
        article_id=article_id,
        required_state="COMMITTED",
    )
    first = entries[0]
    if (
        requests[0] != legacy_request
        or document["draft_id"] != legacy_state["draft_id"]
        or first["request_artifact_name"]
        != legacy_state["request_artifact_name"]
        or first["request_artifact_sha256"]
        != legacy_state["request_artifact_sha256"]
        or first["response_sha256"] != legacy_state["response_sha256"]
    ):
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    draft_id = cast(int, document["draft_id"])
    for generation in range(2, len(entries) + 1):
        binding = _binding_for_generation(
            requests, entries, draft_id=draft_id, generation=generation
        )
        if binding.operation_sha256 != entries[generation - 1]["operation_sha256"]:
            _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    return document, entries, requests


@final
class OwnerPrivateReviewDraftGenerationLedger:
    """Atomic active-generation pointer for fixed-ID committed Draft revisions."""

    __slots__ = ("_root",)

    def __init__(self, repository_root: Path) -> None:
        if not repository_root.is_absolute():
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        self._root = repository_root

    def _owner_and_journal(self) -> tuple[Path, Path]:
        owner, _secrets = _owner_base_layout(
            self._root,
            create=False,
            missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
        )
        journal = _private_child(
            owner,
            JOURNAL_DIRECTORY,
            create=False,
            missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
        )
        return owner, journal

    def _legacy_active_locked(
        self, journal: Path, article_id: str
    ) -> tuple[ReviewDraftRequest, dict[str, object]]:
        return _load_journal_bound_request_locked(
            self._root,
            journal,
            article_id=article_id,
            required_state="COMMITTED",
        )

    def _loaded_locked(
        self, owner: Path, journal: Path, article_id: str
    ) -> tuple[
        Path | None,
        dict[str, object] | None,
        list[dict[str, object]] | None,
        list[ReviewDraftRequest] | None,
    ]:
        generation_directory = _optional_private_directory(
            owner, GENERATION_DIRECTORY
        )
        generation_path = _optional_generation_ledger_path(
            generation_directory, article_id
        )
        if generation_path is None:
            return None, None, None, None
        document, entries, requests = _load_generation_ledger_locked(
            self._root,
            journal,
            generation_path,
            article_id=article_id,
        )
        return generation_path, document, entries, requests

    @staticmethod
    def _assert_binding(
        expected: ReviewDraftRevisionBinding,
        observed: ReviewDraftRevisionBinding,
    ) -> None:
        if type(expected) is not ReviewDraftRevisionBinding or expected != observed:
            _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)

    @staticmethod
    def _assert_observation(
        binding: ReviewDraftRevisionBinding,
        observation: ReviewDraftRevisionObservation,
        *,
        allowed: set[ReviewDraftRevisionDisposition],
    ) -> None:
        if (
            type(observation) is not ReviewDraftRevisionObservation
            or observation.operation_sha256 != binding.operation_sha256
            or observation.draft_id != binding.draft_id
            or observation.disposition not in allowed
        ):
            _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)

    @staticmethod
    def _material_from(
        document: Mapping[str, object],
        *,
        active_generation: int,
        entries: list[dict[str, object]],
        pending: dict[str, object] | None,
    ) -> dict[str, object]:
        return _generation_ledger_material(
            article_id=cast(str, document["article_id"]),
            draft_id=cast(int, document["draft_id"]),
            active_generation=active_generation,
            generations=entries,
            pending=pending,
        )

    def propose(
        self, binding: ReviewDraftRevisionBinding
    ) -> ReviewDraftRevisionBinding:
        if type(binding) is not ReviewDraftRevisionBinding:
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        owner, journal = self._owner_and_journal()
        with _journal_lock(journal / LOCK_FILE):
            generation_path, document, entries, requests = self._loaded_locked(
                owner, journal, binding.successor.article_id
            )
            if document is None:
                predecessor, legacy_state = self._legacy_active_locked(
                    journal, binding.successor.article_id
                )
                if (
                    binding.generation != 2
                    or binding.predecessor != predecessor
                    or binding.draft_id != legacy_state["draft_id"]
                ):
                    _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
                generation_directory = _private_child(
                    owner,
                    GENERATION_DIRECTORY,
                    create=True,
                    missing_code=EditorialPilotFailureCode.JOURNAL_UNSAFE,
                )
                generation_path = (
                    generation_directory
                    / _generation_ledger_name_for(binding.successor.article_id)
                )
                entries = [
                    _generation_entry(
                        predecessor,
                        generation=1,
                        predecessor_generation=None,
                        operation_sha256=None,
                        outcome="LEGACY_COMMITTED",
                        response_sha256=cast(str, legacy_state["response_sha256"]),
                        request_artifact_name=cast(
                            str, legacy_state["request_artifact_name"]
                        ),
                        request_artifact_sha256=cast(
                            str, legacy_state["request_artifact_sha256"]
                        ),
                    )
                ]
                requests = [predecessor]
                active_generation = 1
                draft_id = binding.draft_id
            else:
                if entries is None or requests is None or generation_path is None:
                    _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
                draft_id = cast(int, document["draft_id"])
                active_generation = cast(int, document["active_generation"])
                pending = document["pending"]
                if pending is not None:
                    pending_generation = cast(
                        int, _mapping(pending)["successor_generation"]
                    )
                    observed = _binding_for_generation(
                        requests,
                        entries,
                        draft_id=draft_id,
                        generation=pending_generation,
                    )
                    self._assert_binding(binding, observed)
                    return observed
                if (
                    len(entries) >= _MAX_REVIEW_DRAFT_GENERATIONS
                    or binding.generation != len(entries) + 1
                    or binding.draft_id != draft_id
                    or binding.predecessor != requests[active_generation - 1]
                ):
                    _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
            artifact_name, artifact_sha256 = _ensure_request_artifact(
                self._root, binding.successor
            )
            entries.append(
                _generation_entry(
                    binding.successor,
                    generation=binding.generation,
                    predecessor_generation=active_generation,
                    operation_sha256=binding.operation_sha256,
                    outcome="PENDING",
                    response_sha256=None,
                    request_artifact_name=artifact_name,
                    request_artifact_sha256=artifact_sha256,
                )
            )
            pending_document: dict[str, object] = {
                "operation_sha256": binding.operation_sha256,
                "predecessor_generation": active_generation,
                "state": "PROPOSED",
                "successor_generation": binding.generation,
            }
            material = _generation_ledger_material(
                article_id=binding.successor.article_id,
                draft_id=draft_id,
                active_generation=active_generation,
                generations=entries,
                pending=pending_document,
            )
            _write_private_atomic(generation_path, _journal_document(material))
            return binding

    def _pending_locked(
        self,
        owner: Path,
        journal: Path,
        binding: ReviewDraftRevisionBinding,
    ) -> tuple[
        Path,
        dict[str, object],
        list[dict[str, object]],
        list[ReviewDraftRequest],
        dict[str, object],
    ]:
        path, document, entries, requests = self._loaded_locked(
            owner, journal, binding.successor.article_id
        )
        if (
            path is None
            or document is None
            or entries is None
            or requests is None
            or document["pending"] is None
        ):
            _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
        pending = dict(_mapping(document["pending"]))
        observed = _binding_for_generation(
            requests,
            entries,
            draft_id=cast(int, document["draft_id"]),
            generation=cast(int, pending["successor_generation"]),
        )
        self._assert_binding(binding, observed)
        return path, document, entries, requests, pending

    def mark_attempted(
        self, binding: ReviewDraftRevisionBinding
    ) -> ReviewDraftRevisionBinding:
        if type(binding) is not ReviewDraftRevisionBinding:
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        owner, journal = self._owner_and_journal()
        with _journal_lock(journal / LOCK_FILE):
            replay = self._completed_replay_locked(
                owner,
                journal,
                binding,
                required_outcomes={
                    ReviewDraftRevisionDisposition.OWNER_LIVE_APPLIED,
                    ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED,
                    ReviewDraftRevisionDisposition.OWNER_LIVE_VERIFIED,
                },
                activate_successor=True,
            )
            if replay is not None:
                return binding
            path, document, entries, _requests, pending = self._pending_locked(
                owner, journal, binding
            )
            if pending["state"] == "ATTEMPTED":
                return binding
            if pending["state"] != "PROPOSED":
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            pending["state"] = "ATTEMPTED"
            material = self._material_from(
                document,
                active_generation=cast(int, document["active_generation"]),
                entries=entries,
                pending=pending,
            )
            _write_private_atomic(path, _journal_document(material))
            return binding

    def _active_result(
        self,
        document: Mapping[str, object],
        requests: list[ReviewDraftRequest],
    ) -> tuple[ReviewDraftRequest, int, int]:
        generation = cast(int, document["active_generation"])
        return (
            requests[generation - 1],
            cast(int, document["draft_id"]),
            generation,
        )

    def _complete_pending_locked(
        self,
        owner: Path,
        journal: Path,
        binding: ReviewDraftRevisionBinding,
        observation: ReviewDraftRevisionObservation,
        *,
        activate_successor: bool,
    ) -> tuple[ReviewDraftRequest, int, int]:
        path, document, entries, requests, pending = self._pending_locked(
            owner, journal, binding
        )
        recoverable_without_local_attempt = (
            pending["state"] == "PROPOSED"
            and observation.disposition
            in {
                ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED,
                ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_PREDECESSOR,
            }
        )
        if pending["state"] != "ATTEMPTED" and not recoverable_without_local_attempt:
            _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
        completed = dict(entries[binding.generation - 1])
        completed["outcome"] = observation.disposition.value
        completed["response_sha256"] = observation.response_sha256
        entries[binding.generation - 1] = completed
        active_generation = (
            binding.generation
            if activate_successor
            else cast(int, document["active_generation"])
        )
        material = self._material_from(
            document,
            active_generation=active_generation,
            entries=entries,
            pending=None,
        )
        _write_private_atomic(path, _journal_document(material))
        updated = {**material, "integrity_sha256": canonical_sha256(material)}
        return self._active_result(updated, requests)

    def _completed_replay_locked(
        self,
        owner: Path,
        journal: Path,
        binding: ReviewDraftRevisionBinding,
        *,
        required_outcomes: set[ReviewDraftRevisionDisposition],
        activate_successor: bool,
    ) -> tuple[ReviewDraftRequest, int, int] | None:
        _path, document, entries, requests = self._loaded_locked(
            owner, journal, binding.successor.article_id
        )
        if document is None or entries is None or requests is None:
            return None
        if binding.generation > len(entries):
            return None
        if document["pending"] is not None:
            pending_generation = cast(
                int,
                _mapping(document["pending"])["successor_generation"],
            )
            if pending_generation == binding.generation:
                return None
        observed = _binding_for_generation(
            requests,
            entries,
            draft_id=cast(int, document["draft_id"]),
            generation=binding.generation,
        )
        self._assert_binding(binding, observed)
        entry_outcome = entries[binding.generation - 1]["outcome"]
        if entry_outcome not in {outcome.value for outcome in required_outcomes}:
            _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
        expected_active_generation = (
            binding.generation
            if activate_successor
            else cast(
                int,
                entries[binding.generation - 1]["predecessor_generation"],
            )
        )
        if document["active_generation"] != expected_active_generation:
            _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
        return self._active_result(document, requests)

    def commit(
        self,
        binding: ReviewDraftRevisionBinding,
        observation: ReviewDraftRevisionObservation,
    ) -> tuple[ReviewDraftRequest, int, int]:
        self._assert_observation(
            binding,
            observation,
            allowed={ReviewDraftRevisionDisposition.OWNER_LIVE_APPLIED},
        )
        owner, journal = self._owner_and_journal()
        with _journal_lock(journal / LOCK_FILE):
            replay = self._completed_replay_locked(
                owner,
                journal,
                binding,
                required_outcomes={
                    ReviewDraftRevisionDisposition.OWNER_LIVE_APPLIED
                },
                activate_successor=True,
            )
            if replay is not None:
                if replay[2] != binding.generation:
                    _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
                return replay
            return self._complete_pending_locked(
                owner,
                journal,
                binding,
                observation,
                activate_successor=True,
            )

    def recover(
        self,
        binding: ReviewDraftRevisionBinding,
        observation: ReviewDraftRevisionObservation,
    ) -> tuple[ReviewDraftRequest, int, int]:
        allowed = {
            ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED,
            ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_PREDECESSOR,
        }
        self._assert_observation(binding, observation, allowed=allowed)
        owner, journal = self._owner_and_journal()
        with _journal_lock(journal / LOCK_FILE):
            replay = self._completed_replay_locked(
                owner,
                journal,
                binding,
                required_outcomes=(
                    {
                        ReviewDraftRevisionDisposition.OWNER_LIVE_APPLIED,
                        ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED,
                        ReviewDraftRevisionDisposition.OWNER_LIVE_VERIFIED,
                    }
                    if observation.disposition
                    is ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED
                    else {
                        ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_PREDECESSOR
                    }
                ),
                activate_successor=(
                    observation.disposition
                    is ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED
                ),
            )
            if replay is not None:
                expected_generation = (
                    binding.generation
                    if observation.disposition
                    is ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED
                    else None
                )
                if expected_generation is not None and replay[2] != expected_generation:
                    _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
                return replay
            return self._complete_pending_locked(
                owner,
                journal,
                binding,
                observation,
                activate_successor=(
                    observation.disposition
                    is ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED
                ),
            )

    def verify(
        self,
        binding: ReviewDraftRevisionBinding,
        observation: ReviewDraftRevisionObservation,
    ) -> tuple[ReviewDraftRequest, int, int]:
        self._assert_observation(
            binding,
            observation,
            allowed={ReviewDraftRevisionDisposition.OWNER_LIVE_VERIFIED},
        )
        owner, journal = self._owner_and_journal()
        with _journal_lock(journal / LOCK_FILE):
            path, document, entries, requests = self._loaded_locked(
                owner, journal, binding.successor.article_id
            )
            if path is None or document is None or entries is None or requests is None:
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            replay = self._completed_replay_locked(
                owner,
                journal,
                binding,
                required_outcomes={
                    ReviewDraftRevisionDisposition.OWNER_LIVE_APPLIED,
                    ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED,
                    ReviewDraftRevisionDisposition.OWNER_LIVE_VERIFIED,
                },
                activate_successor=True,
            )
            if replay is not None:
                return replay
            if document["pending"] is None:
                observed = _binding_for_generation(
                    requests,
                    entries,
                    draft_id=cast(int, document["draft_id"]),
                    generation=binding.generation,
                )
                self._assert_binding(binding, observed)
                if document["active_generation"] != binding.generation:
                    _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
                return self._active_result(document, requests)
            return self._complete_pending_locked(
                owner,
                journal,
                binding,
                observation,
                activate_successor=True,
            )

    def active_request(
        self, article_id: str
    ) -> tuple[ReviewDraftRequest, int, int]:
        article_identity(article_id)
        owner, journal = self._owner_and_journal()
        with _journal_lock(journal / LOCK_FILE):
            _path, document, _entries, requests = self._loaded_locked(
                owner, journal, article_id
            )
            if document is None:
                request, state = self._legacy_active_locked(journal, article_id)
                return request, _positive_post_id(state["draft_id"]), 1
            if requests is None:
                _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
            return self._active_result(document, requests)

    def revision_preparation_context(
        self, article_id: str
    ) -> tuple[ReviewDraftRequest, int, int]:
        """Return the active predecessor and monotonic next generation."""

        article_identity(article_id)
        owner, journal = self._owner_and_journal()
        with _journal_lock(journal / LOCK_FILE):
            _path, document, entries, requests = self._loaded_locked(
                owner, journal, article_id
            )
            if document is None:
                request, state = self._legacy_active_locked(journal, article_id)
                return request, _positive_post_id(state["draft_id"]), 2
            if (
                entries is None
                or requests is None
                or document["pending"] is not None
                or len(entries) >= _MAX_REVIEW_DRAFT_GENERATIONS
            ):
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            active, draft_id, _active_generation = self._active_result(
                document, requests
            )
            return active, draft_id, len(entries) + 1

    def pending_binding(self, article_id: str) -> ReviewDraftRevisionBinding:
        article_identity(article_id)
        owner, journal = self._owner_and_journal()
        with _journal_lock(journal / LOCK_FILE):
            _path, document, entries, requests = self._loaded_locked(
                owner, journal, article_id
            )
            if (
                document is None
                or entries is None
                or requests is None
                or document["pending"] is None
            ):
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            generation = cast(
                int, _mapping(document["pending"])["successor_generation"]
            )
            return _binding_for_generation(
                requests,
                entries,
                draft_id=cast(int, document["draft_id"]),
                generation=generation,
            )

    def revision_binding(
        self, article_id: str, operation_sha256: str | None = None
    ) -> ReviewDraftRevisionBinding:
        article_identity(article_id)
        if operation_sha256 is not None:
            require_sha256(operation_sha256)
        owner, journal = self._owner_and_journal()
        with _journal_lock(journal / LOCK_FILE):
            _path, document, entries, requests = self._loaded_locked(
                owner, journal, article_id
            )
            if document is None or entries is None or requests is None:
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            if operation_sha256 is not None:
                matching_generations = tuple(
                    generation
                    for generation in range(2, len(entries) + 1)
                    if entries[generation - 1]["operation_sha256"]
                    == operation_sha256
                )
                if len(matching_generations) != 1:
                    _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
                generation = matching_generations[0]
            elif document["pending"] is not None:
                generation = cast(
                    int, _mapping(document["pending"])["successor_generation"]
                )
            else:
                generation = cast(int, document["active_generation"])
                if generation == 1:
                    _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            binding = _binding_for_generation(
                requests,
                entries,
                draft_id=cast(int, document["draft_id"]),
                generation=generation,
            )
            if operation_sha256 is not None and binding.operation_sha256 != (
                operation_sha256
            ):
                _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
            return binding

    def revision_bindings(
        self, article_id: str
    ) -> tuple[ReviewDraftRevisionBinding, ...]:
        """Return every immutable revision generation for exact intent recovery."""

        article_identity(article_id)
        owner, journal = self._owner_and_journal()
        with _journal_lock(journal / LOCK_FILE):
            _path, document, entries, requests = self._loaded_locked(
                owner, journal, article_id
            )
            if document is None or entries is None or requests is None:
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            draft_id = cast(int, document["draft_id"])
            return tuple(
                _binding_for_generation(
                    requests,
                    entries,
                    draft_id=draft_id,
                    generation=generation,
                )
                for generation in range(2, len(entries) + 1)
            )


@final
class OwnerPrivateLiveReviewDraftJournal:
    """Write durable intent before the sole owner-gated live POST or recovery GET."""

    __slots__ = ("_attempt", "_root")

    def __init__(
        self,
        repository_root: Path,
        live_port: OwnerOperatedWordPressPort,
    ) -> None:
        if not repository_root.is_absolute() or not isinstance(
            cast(object, live_port), OwnerOperatedWordPressPort
        ):
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        self._root = repository_root
        self._attempt = live_port

    def _paths(self, request: ReviewDraftRequest) -> tuple[Path, Path]:
        _owner, journal, _secrets = _owner_layout(self._root, create=True)
        name = _live_journal_name_for(request.article_id, request.packet_sha256)
        return journal / name, journal / LOCK_FILE

    def _request_for_state(
        self, article_id: str, state: str
    ) -> tuple[ReviewDraftRequest, dict[str, object]]:
        article_identity(article_id)
        owner, _secrets = _owner_base_layout(
            self._root,
            create=False,
            missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
        )
        journal = _private_child(
            owner,
            JOURNAL_DIRECTORY,
            create=False,
            missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
        )
        with _journal_lock(journal / LOCK_FILE):
            return _load_journal_bound_request_locked(
                self._root,
                journal,
                article_id=article_id,
                required_state=state,
            )

    def _replay(
        self, request: ReviewDraftRequest, state: Mapping[str, object]
    ) -> ReviewDraftReceipt:
        return ReviewDraftReceipt(
            article_id=request.article_id,
            packet_sha256=request.packet_sha256,
            request_sha256=request.request_sha256,
            response_sha256=cast(str, state["response_sha256"]),
            draft_id=cast(int, state["draft_id"]),
            disposition=ReviewDraftDisposition.OWNER_LIVE_REPLAY,
            target_public_post_id=cast(int | None, state["target_public_post_id"]),
            recorded_evidence_only=False,
            live_authority=True,
        )

    def create(self, request: ReviewDraftRequest) -> ReviewDraftReceipt:
        if type(request) is not ReviewDraftRequest:
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        self._attempt.preflight(request, "create-review-draft")
        journal_path, lock_path = self._paths(request)
        with _journal_lock(lock_path):
            existing_journals = _live_journal_candidates(
                journal_path.parent, request.article_id
            )
            if existing_journals:
                if len(existing_journals) != 1 or existing_journals[0] != journal_path:
                    _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
                artifact_name, artifact_sha256 = _load_exact_request_artifact(
                    self._root,
                    request,
                    missing_code=EditorialPilotFailureCode.JOURNAL_MISMATCH,
                )
                state = _decode_live_journal(
                    _read_private_file(
                        journal_path,
                        maximum_bytes=MAX_JOURNAL_BYTES,
                        missing_code=EditorialPilotFailureCode.JOURNAL_UNSAFE,
                    ),
                    request,
                    request_artifact_name=artifact_name,
                    request_artifact_sha256=artifact_sha256,
                )
                if state["state"] == "COMMITTED":
                    return self._replay(request, state)
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            target_public_post_id = self._attempt.resolve_public_target(
                request, "create-review-draft"
            )
            artifact_name, artifact_sha256 = _ensure_request_artifact(
                self._root, request
            )
            intent = _live_journal_material(
                request,
                state="INTENT",
                response_sha256=None,
                draft_id=None,
                target_public_post_id=target_public_post_id,
                request_artifact_name=artifact_name,
                request_artifact_sha256=artifact_sha256,
            )
            _write_private_atomic(journal_path, _journal_document(intent))
            receipt = self._attempt.create(request)
            if (
                receipt.article_id != request.article_id
                or receipt.packet_sha256 != request.packet_sha256
                or receipt.request_sha256 != request.request_sha256
                or receipt.disposition is not ReviewDraftDisposition.OWNER_LIVE_CREATED
                or receipt.recorded_evidence_only is not False
                or receipt.live_authority is not True
                or receipt.target_public_post_id != target_public_post_id
            ):
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            committed = _live_journal_material(
                request,
                state="COMMITTED",
                response_sha256=receipt.response_sha256,
                draft_id=receipt.draft_id,
                target_public_post_id=target_public_post_id,
                request_artifact_name=artifact_name,
                request_artifact_sha256=artifact_sha256,
            )
            _write_private_atomic(journal_path, _journal_document(committed))
            return receipt

    def recover(self, request: ReviewDraftRequest) -> ReviewDraftReceipt:
        if type(request) is not ReviewDraftRequest:
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        self._attempt.preflight(request, "recover-create-review-draft")
        journal_path, lock_path = self._paths(request)
        with _journal_lock(lock_path):
            existing_journals = _live_journal_candidates(
                journal_path.parent, request.article_id
            )
            if len(existing_journals) != 1 or existing_journals[0] != journal_path:
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            artifact_name, artifact_sha256 = _load_exact_request_artifact(
                self._root,
                request,
                missing_code=EditorialPilotFailureCode.JOURNAL_MISMATCH,
            )
            state = _decode_live_journal(
                _read_private_file(
                    journal_path,
                    maximum_bytes=MAX_JOURNAL_BYTES,
                    missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
                ),
                request,
                request_artifact_name=artifact_name,
                request_artifact_sha256=artifact_sha256,
            )
            if state["state"] != "INTENT":
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            target_public_post_id = self._attempt.resolve_public_target(
                request, "recover-create-review-draft"
            )
            if target_public_post_id != state["target_public_post_id"]:
                _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
            attempted = _live_journal_material(
                request,
                state="RECOVERY_ATTEMPTED",
                response_sha256=None,
                draft_id=None,
                target_public_post_id=target_public_post_id,
                request_artifact_name=artifact_name,
                request_artifact_sha256=artifact_sha256,
            )
            _write_private_atomic(journal_path, _journal_document(attempted))
            receipt = self._attempt.recover(request)
            if (
                receipt.article_id != request.article_id
                or receipt.packet_sha256 != request.packet_sha256
                or receipt.request_sha256 != request.request_sha256
                or receipt.disposition
                is not ReviewDraftDisposition.OWNER_LIVE_RECOVERED
                or receipt.recorded_evidence_only is not False
                or receipt.live_authority is not True
                or receipt.target_public_post_id != target_public_post_id
            ):
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            committed = _live_journal_material(
                request,
                state="COMMITTED",
                response_sha256=receipt.response_sha256,
                draft_id=receipt.draft_id,
                target_public_post_id=target_public_post_id,
                request_artifact_name=artifact_name,
                request_artifact_sha256=artifact_sha256,
            )
            _write_private_atomic(journal_path, _journal_document(committed))
            return receipt

    def request_for_recovery(self, article_id: str) -> ReviewDraftRequest:
        """Load the sole INTENT-bound immutable request without live evidence."""

        request, _state = self._request_for_state(article_id, "INTENT")
        return request

    def committed_request(self, article_id: str) -> tuple[ReviewDraftRequest, int]:
        """Load the unique active generation, with a legacy-only fallback."""

        if article_id != PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID:
            request, draft_id, _generation = OwnerPrivateReviewDraftGenerationLedger(
                self._root
            ).active_request(article_id)
            return request, draft_id
        request, state = self._request_for_state(article_id, "COMMITTED")
        return request, _positive_post_id(state["target_public_post_id"])

    def carry_on_single_url_reconciliation_binding(
        self, article_id: str
    ) -> CarryOnSingleUrlReconciliationBinding:
        """Read the one fixed RECOVERY_ATTEMPTED exception without journal writes."""

        if article_id != PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID:
            _fail(EditorialPilotFailureCode.OPERATION_NOT_ALLOWED)
        owner, _secrets = _owner_base_layout(
            self._root,
            create=False,
            missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
        )
        journal = _private_child(
            owner,
            JOURNAL_DIRECTORY,
            create=False,
            missing_code=EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
        )
        request, state, artifact_sha256 = (
            _load_terminal_reconciliation_request_read_only(
                self._root,
                journal,
                article_id=article_id,
            )
        )
        return CarryOnSingleUrlReconciliationBinding(
            request=request,
            request_artifact_sha256=artifact_sha256,
            journal_state=cast(str, state["state"]),
            target_public_post_id=_positive_post_id(state["target_public_post_id"]),
            expected_review_draft_post_id=(
                PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID
            ),
        )

    def public_target(self, request: ReviewDraftRequest) -> int | None:
        """Read the committed publication target without any external action."""

        if type(request) is not ReviewDraftRequest:
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        if request.article_id != PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID:
            stored, _draft_id = self.committed_request(request.article_id)
            if stored != request:
                _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
            return None
        stored, state = self._request_for_state(request.article_id, "COMMITTED")
        if stored != request:
            _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
        return cast(int | None, state["target_public_post_id"])

    def expected_public_post_id(self, request: ReviewDraftRequest) -> int:
        """Bind public verification to the created draft or AT-003 target ID."""

        if type(request) is not ReviewDraftRequest:
            _fail(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        stored, expected_public_post_id = self.committed_request(request.article_id)
        if stored != request:
            _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
        return expected_public_post_id


__all__ = [
    "GENERATION_DIRECTORY",
    "JOURNAL_DIRECTORY",
    "MAX_JOURNAL_BYTES",
    "MAX_REQUEST_ARTIFACT_BYTES",
    "MAX_RAKUTEN_EVIDENCE_BYTES",
    "MAX_RAKUTEN_IMAGE_BYTES",
    "MAX_RAKUTEN_RESPONSE_BYTES",
    "MAX_SOURCE_BODY_BYTES",
    "MAX_SOURCE_EVIDENCE_BYTES",
    "MAX_RECORDED_BYTES",
    "OWNER_DIRECTORY",
    "OwnerPrivateLiveReviewDraftJournal",
    "OwnerPrivateReviewDraftGenerationLedger",
    "OwnerPrivateReviewDraftJournal",
    "RECORDED_DIRECTORY",
    "RAKUTEN_DIRECTORY",
    "REQUEST_DIRECTORY",
    "SOURCE_DIRECTORY",
    "RecordedWordPressPublicReadAdapter",
    "RecordedWordPressReviewDraftAdapter",
    "decode_strict_json",
    "read_recorded_fixture",
    "read_official_source_capture_evidence",
    "read_rakuten_product_evidence",
    "rakuten_affiliate_response_relative_path",
    "rakuten_evidence_relative_path",
    "rakuten_image_relative_path",
    "rakuten_response_relative_path",
    "request_artifact_relative_path",
    "source_body_relative_path",
    "source_evidence_relative_path",
    "recorded_fixture_relative_path",
]
