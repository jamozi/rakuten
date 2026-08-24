from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import cast
from urllib.parse import parse_qs, urlencode, urlsplit
import zlib

import pytest

from raos.adapters import self_hosted_editorial_rakuten_capture as capture_module
from raos.adapters.self_hosted_editorial_pilot_json import (
    read_rakuten_product_evidence,
)
from raos.adapters.self_hosted_editorial_rakuten_capture import (
    MEDIA_REGISTRY_RELATIVE_PATH,
    ARTICLES_RELATIVE_PATH,
    SOURCE_REGISTRY_RELATIVE_PATH,
    ProductCaptureTarget,
    RakutenHttpsConnectionFactory,
    RakutenProductCaptureFailure,
    RakutenProductCaptureFailureCode,
    SystemRakutenHttpsConnectionFactory,
    _OwnerRequestPacer,
    capture_article_products,
    load_product_capture_plan,
)
from scripts import build_st1704_rakuten_capture_manifest as manifest_builder


ROOT = Path(__file__).resolve().parents[2]
ARTICLE_ID = "st1703-first-suitcase-comparison"
DISCOVERY_ARTICLE_ID = "st1704-compact-robot-vacuum-shortlist"
DISHWASHER_ARTICLE_ID = "st1704-countertop-dishwasher-for-small-households"


def _png(
    *,
    width: int = 128,
    height: int = 128,
    compressed_payload: bytes | None = None,
    color_type: int = 2,
    include_palette: bool = False,
    indexed_sample: int = 0,
    zero_idat_before_palette: bool = False,
) -> bytes:
    def chunk(name: bytes, payload: bytes) -> bytes:
        return (
            len(payload).to_bytes(4, "big")
            + name
            + payload
            + (zlib.crc32(name + payload) & 0xFFFFFFFF).to_bytes(4, "big")
        )

    channels = {2: 3, 3: 1}[color_type]
    ihdr = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + bytes((8, color_type, 0, 0, 0))
    )
    sample = bytes((indexed_sample,)) if color_type == 3 else b"\x00" * channels
    pixels = b"".join(b"\x00" + (sample * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + (
            chunk(b"IDAT", b"") + chunk(b"PLTE", b"\x00\x00\x00")
            if zero_idat_before_palette
            else b""
        )
        + (chunk(b"PLTE", b"\x00\x00\x00") if include_palette else b"")
        + chunk(
            b"IDAT",
            zlib.compress(pixels) if compressed_payload is None else compressed_payload,
        )
        + chunk(b"IEND", b"")
    )


def _gif(*, valid_lzw: bool, width: int = 128, height: int = 128) -> bytes:
    def blocks(payload: bytes) -> bytes:
        return (
            b"".join(
                bytes((len(payload[offset : offset + 255]),))
                + payload[offset : offset + 255]
                for offset in range(0, len(payload), 255)
            )
            + b"\x00"
        )

    if valid_lzw:
        codes = [4]
        for _pixel in range(width * height):
            codes.extend((0, 4))
        codes[-1] = 5
        packed = bytearray()
        buffer = 0
        buffered_bits = 0
        for code in codes:
            buffer |= code << buffered_bits
            buffered_bits += 3
            while buffered_bits >= 8:
                packed.append(buffer & 0xFF)
                buffer >>= 8
                buffered_bits -= 8
        if buffered_bits:
            packed.append(buffer & 0xFF)
        image_data = bytes(packed)
    else:
        image_data = b"\xff"
    screen_width = width.to_bytes(2, "little")
    screen_height = height.to_bytes(2, "little")
    return (
        b"GIF89a"
        + screen_width
        + screen_height
        + b"\x80\x00\x00"
        + b"\x00\x00\x00\xff\xff\xff"
        + b"\x2c\x00\x00\x00\x00"
        + screen_width
        + screen_height
        + b"\x00\x02"
        + blocks(image_data)
        + b"\x3b"
    )


def _jpeg(
    *,
    valid_entropy: bool,
    all_ones_huffman: bool = False,
    width: int = 128,
    height: int = 128,
) -> bytes:
    def segment(marker: int, payload: bytes) -> bytes:
        return (
            b"\xff" + bytes((marker,)) + (len(payload) + 2).to_bytes(2, "big") + payload
        )

    dqt = b"\x00" + (b"\x01" * 64)
    sof = (
        b"\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x01\x01\x11\x00"
    )
    counts = b"\x01" + (b"\x00" * 15)
    dc_counts = (b"\x02" + (b"\x00" * 15)) if all_ones_huffman else counts
    dc_symbols = b"\x00\x01" if all_ones_huffman else b"\x00"
    dht = b"\x00" + dc_counts + dc_symbols + b"\x10" + counts + b"\x00"
    sos = b"\x01\x01\x00\x00\x3f\x00"
    entropy_bits = ((width + 7) // 8) * ((height + 7) // 8) * 2
    entropy = b"\x00" * ((entropy_bits + 7) // 8 if valid_entropy else 1)
    return (
        b"\xff\xd8"
        + segment(0xDB, dqt)
        + segment(0xC0, sof)
        + segment(0xC4, dht)
        + segment(0xDA, sos)
        + entropy
        + b"\xff\xd9"
    )


@dataclass
class _Response:
    body: bytes
    content_type: str
    status: int = 200
    offset: int = 0

    def getheaders(self) -> list[tuple[str, str]]:
        return [
            ("Content-Length", str(len(self.body))),
            ("Content-Type", self.content_type),
        ]

    def read(self, amount: int | None = None) -> bytes:
        size = len(self.body) if amount is None else amount
        result = self.body[self.offset : self.offset + size]
        self.offset += len(result)
        return result


class _Connection:
    def __init__(self, factory: "_Factory", host: str) -> None:
        self.factory = factory
        self.host = host
        self.response: _Response | None = None

    def connect(self) -> None:
        return None

    def set_read_timeout(self, seconds: int) -> None:
        assert seconds == 20

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        assert method == "GET"
        self.response = self.factory.respond(self.host, path, headers)

    def getresponse(self) -> _Response:
        assert self.response is not None
        return self.response

    def close(self) -> None:
        return None


class _Factory:
    def __init__(
        self,
        targets: tuple[ProductCaptureTarget, ...],
        *,
        ambiguous: bool = False,
        compact_extra_row: bool = False,
        extra_provider_field: bool = False,
        first_image_not_square: bool = False,
        image_candidate_count: int | None = None,
        invalid_compressed_image: bool = False,
        indexed_image_without_palette: bool = False,
        indexed_image_outside_palette: bool = False,
        malformed_idat_sequence: bool = False,
        invalid_gif_image: bool = False,
        invalid_jpeg_image: bool = False,
        invalid_jpeg_huffman: bool = False,
        non_target_gif_dimensions: bool = False,
        non_target_jpeg_dimensions: bool = False,
        lowercase_envelope: bool = False,
        malformed_item_url: bool = False,
        malformed_provider_json: bool = False,
        mismatched_item_url_shop: bool = False,
        reflected_value: str | None = None,
        truncated_image: bool = False,
    ) -> None:
        self.targets = targets
        self.ambiguous = ambiguous
        self.compact_extra_row = compact_extra_row
        self.extra_provider_field = extra_provider_field
        self.first_image_not_square = first_image_not_square
        self.image_candidate_count = image_candidate_count
        self.reflected_value = reflected_value
        self.image = _png()
        self.non_square_image = _png(width=96)
        self.invalid_compressed_image = _png(compressed_payload=b"not-zlib-data")
        self.indexed_image_without_palette = _png(color_type=3)
        self.indexed_image_outside_palette = _png(
            color_type=3, include_palette=True, indexed_sample=1
        )
        self.malformed_idat_sequence = _png(zero_idat_before_palette=True)
        self.invalid_gif_image = _gif(valid_lzw=False)
        self.non_target_gif_dimensions = _gif(valid_lzw=True, width=96)
        self.invalid_jpeg_image = _jpeg(valid_entropy=False)
        self.invalid_jpeg_huffman = _jpeg(valid_entropy=True, all_ones_huffman=True)
        self.non_target_jpeg_dimensions = _jpeg(
            valid_entropy=True, width=129, height=128
        )
        self.truncated_image = self.image[:24]
        self.use_indexed_image_without_palette = indexed_image_without_palette
        self.use_indexed_image_outside_palette = indexed_image_outside_palette
        self.use_malformed_idat_sequence = malformed_idat_sequence
        self.use_invalid_gif_image = invalid_gif_image
        self.use_non_target_gif_dimensions = non_target_gif_dimensions
        self.use_invalid_jpeg_image = invalid_jpeg_image
        self.use_invalid_jpeg_huffman = invalid_jpeg_huffman
        self.use_non_target_jpeg_dimensions = non_target_jpeg_dimensions
        self.use_invalid_compressed_image = invalid_compressed_image
        self.lowercase_envelope = lowercase_envelope
        self.malformed_provider_json = malformed_provider_json
        self.malformed_item_url = malformed_item_url
        self.mismatched_item_url_shop = mismatched_item_url_shop
        self.use_truncated_image = truncated_image
        self.requests: list[tuple[str, str]] = []
        self.credentials_used = False
        self.by_variant = {
            variant: target for target in targets for variant in target.variants
        }
        self.by_code = {
            self._code(target, target.variants[0]): target for target in targets
        }

    def mark_credentials_used(self) -> None:
        self.credentials_used = True

    @staticmethod
    def _code(target: ProductCaptureTarget, variant: str) -> str:
        if target.fixed_item_code is not None:
            return target.fixed_item_code
        return f"{target.shop_code}:{target.product_id.lower().removeprefix('prd-')}-{variant.lower().replace(' ', '-').replace('+', 'plus')}"

    @staticmethod
    def _item_name(target: ProductCaptureTarget) -> str:
        return " ".join([*target.required_title_tokens, target.product_kind_tokens[0]])

    def _source_and_destination(
        self, target: ProductCaptureTarget, code: str
    ) -> tuple[str, str]:
        if target.fixed_destination_url is not None:
            destination = target.fixed_destination_url
            source = parse_qs(urlsplit(destination).query)["pc"][0]
            if not self.mismatched_item_url_shop:
                return source, destination
        tail = code.split(":", 1)[1]
        shop_code = (
            "different-shop" if self.mismatched_item_url_shop else target.shop_code
        )
        source = f"https://item.rakuten.co.jp/{shop_code}/{tail}/"
        destination = "https://hb.afl.rakuten.co.jp/hgc/test.abc/?" + urlencode(
            {
                "m": f"https://m.rakuten.co.jp/{shop_code}/i/{tail}/",
                "pc": source,
                "rafcid": "bounded-capture-test",
            }
        )
        return source, destination

    def _row(
        self, target: ProductCaptureTarget, code: str, *, affiliate: bool
    ) -> dict[str, object]:
        source, destination = self._source_and_destination(target, code)
        image = (
            f"https://thumbnail.image.rakuten.co.jp/@0_mall/{target.shop_code}/"
            f"cabinet/{code.split(':', 1)[1]}.png?_ex=128x128"
        )
        image_urls = [image]
        if self.first_image_not_square:
            image_urls = [
                image.replace(".png?_ex=128x128", "-non-square.png?_ex=128x128"),
                image,
            ]
        if self.image_candidate_count is not None:
            image_urls = [
                image.replace(".png?_ex=128x128", f"-{index}.png?_ex=128x128")
                for index in range(self.image_candidate_count)
            ]
        row: dict[str, object] = {
            "itemCode": code,
            "itemName": self._item_name(target),
            "itemUrl": destination if affiliate else source,
            "mediumImageUrls": image_urls,
            "shopCode": target.shop_code,
            "shopName": "Tracked selected shop",
        }
        if affiliate:
            row["affiliateUrl"] = destination
        elif self.malformed_item_url:
            row["itemUrl"] = "https://item.rakuten.co.jp/"
        if self.reflected_value is not None:
            row["itemName"] = f"{row['itemName']} {self.reflected_value}"
        if self.extra_provider_field:
            row["unexpectedProviderField"] = "not requested"
        return row

    def respond(self, host: str, path: str, headers: dict[str, str]) -> _Response:
        self.requests.append((host, path))
        if host == "thumbnail.image.rakuten.co.jp":
            assert "accessKey" not in headers
            image = (
                self.truncated_image
                if self.use_truncated_image
                else self.invalid_jpeg_image
                if self.use_invalid_jpeg_image
                else self.invalid_jpeg_huffman
                if self.use_invalid_jpeg_huffman
                else self.non_target_jpeg_dimensions
                if self.use_non_target_jpeg_dimensions
                else self.invalid_gif_image
                if self.use_invalid_gif_image
                else self.non_target_gif_dimensions
                if self.use_non_target_gif_dimensions
                else self.indexed_image_without_palette
                if self.use_indexed_image_without_palette
                else self.indexed_image_outside_palette
                if self.use_indexed_image_outside_palette
                else self.malformed_idat_sequence
                if self.use_malformed_idat_sequence
                else self.invalid_compressed_image
                if self.use_invalid_compressed_image
                else self.non_square_image
                if "-non-square.png" in path
                else self.image
            )
            return _Response(
                image,
                "image/jpeg"
                if (
                    self.use_invalid_jpeg_image
                    or self.use_invalid_jpeg_huffman
                    or self.use_non_target_jpeg_dimensions
                )
                else "image/gif"
                if self.use_invalid_gif_image or self.use_non_target_gif_dimensions
                else "image/png",
            )
        assert host == "openapi.rakuten.co.jp"
        assert headers["accessKey"] == "test-access"
        if self.malformed_provider_json:
            return _Response(b'{"Items":', "application/json; charset=UTF-8")
        query = parse_qs(urlsplit(path).query)
        if "keyword" in query:
            variant = query["keyword"][0]
            target = self.by_variant[variant]
            code = self._code(target, variant)
            rows = [self._row(target, code, affiliate=False)]
            if self.ambiguous:
                rows.append(
                    self._row(
                        target, f"another-shop:{code.split(':', 1)[1]}", affiliate=False
                    )
                )
        else:
            code = query["itemCode"][0]
            target = self.by_code[code]
            rows = [self._row(target, code, affiliate="affiliateId" in query)]
            if self.compact_extra_row:
                rows.append(
                    self._row(
                        target,
                        f"{target.shop_code}:unrelated-item",
                        affiliate="affiliateId" in query,
                    )
                )
            for row in rows:
                row.pop("shopCode")
                row.pop("shopName")
        hits = int(query["hits"][0])
        envelope: dict[str, object]
        if self.lowercase_envelope:
            envelope = {
                "carrier": 0,
                "count": len(rows),
                "first": 1 if rows else 0,
                "hits": hits,
                "items": rows,
                "last": len(rows),
                "page": 1,
                "pageCount": 1 if rows else 0,
            }
        else:
            envelope = {"Items": rows}
        body = json.dumps(
            envelope,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        return _Response(body, "application/json; charset=UTF-8")

    def open(
        self, *, host: str, port: int, connect_timeout_seconds: int, tls_context: object
    ) -> _Connection:
        assert port == 443
        assert connect_timeout_seconds == 10
        assert tls_context is not None
        return _Connection(self, host)


@pytest.fixture
def clean_network_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "ALL_PROXY",
        "CURL_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SSLKEYLOGFILE",
        "all_proxy",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "sslkeylogfile",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def private_root_path() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(
        prefix="raos-st1704-rakuten-capture-", dir="/var/tmp"
    ) as directory:
        yield Path(directory)


def _private_root(tmp_path: Path) -> Path:
    for relative in (
        ARTICLES_RELATIVE_PATH,
        SOURCE_REGISTRY_RELATIVE_PATH,
        MEDIA_REGISTRY_RELATIVE_PATH,
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    secrets = tmp_path / ".secrets"
    credential_directory = secrets / "rakuten-owner-local"
    secrets.mkdir(mode=0o700)
    credential_directory.mkdir(mode=0o700)
    credential = credential_directory / "credentials.v1.json"
    credential.write_text(
        '{"schema_version":1,"profile":"OWNER_LOCAL_RAKUTEN_PRODUCTION_API","application_id":"test-app","access_key":"test-access","affiliate_id":"test-affiliate"}',
        encoding="utf-8",
    )
    credential.chmod(0o600)
    return tmp_path


def test_capture_plan_binds_five_articles_and_eighteen_unique_products() -> None:
    plan = load_product_capture_plan(ROOT)
    rows = [plan.for_article(article_id) for article_id in manifest_builder.ARTICLE_IDS]
    assert [len(row) for row in rows] == [3, 4, 4, 4, 4]
    assert len({target.product_id for row in rows for target in row}) == 18
    assert [target.shop_code for target in rows[1]] == [
        "anker",
        "jackery-japan",
        "bluettijapan",
        "ecoflow",
    ]
    assert [target.fixed_item_code for target in rows[1]] == [
        "anker:10002036",
        "jackery-japan:10000000",
        "bluettijapan:10000107",
        "ecoflow:10000092",
    ]
    assert [target.fixed_item_code for target in rows[2]] == [
        "anker:10002036",
        "anker:10001890",
        "anker:10001654",
        "anker:10002336",
    ]
    assert [target.fixed_item_code for target in rows[3]] == [
        "panasonic-store:10000735",
        "thanko:000000004055",
        "siroca:10000024",
        "jyupro:10136298",
    ]
    assert [target.fixed_item_code for target in rows[4]] == [
        "irobotstore:f15",
        "switchbot:10000327",
        "switchbot:10000240",
        "edion:10909675",
    ]
    assert [target.fixed_item_code for target in rows[0]] == [
        "ace-store:10007275",
        "ace-store:10009372",
        "ace-store:10009099",
    ]


def test_bounded_capture_writes_exact_four_artifacts_per_product(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    plan = load_product_capture_plan(repository)
    targets = plan.for_article(ARTICLE_ID)
    factory = _Factory(targets)
    results = capture_article_products(
        repository,
        article_id=ARTICLE_ID,
        connection_factory=cast(RakutenHttpsConnectionFactory, factory),
        clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
    )
    assert len(results) == 3
    directory = repository / ".secrets/st1704-self-hosted-editorial-pilot/rakuten"
    for target in targets:
        evidence = read_rakuten_product_evidence(
            repository, product_id=target.product_id
        )
        assert evidence.width == evidence.height == 128
        assert evidence.no_modification_policy == (
            ("aspect_ratio_change_allowed", False),
            ("crop_allowed", False),
            ("modification_allowed", False),
            ("text_overlay_allowed", False),
            ("upscale_allowed", False),
        )
        for suffix in (
            ".v1.json",
            ".item-search-response.v1.json",
            ".affiliate-item-search-response.v1.json",
            ".image",
        ):
            path = directory / f"{target.product_id}{suffix}"
            assert path.is_file()
            assert path.stat().st_mode & 0o777 == 0o600


def test_capture_accepts_documented_lowercase_envelope_and_validates_evidence(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    results = capture_article_products(
        repository,
        article_id=ARTICLE_ID,
        connection_factory=cast(
            RakutenHttpsConnectionFactory,
            _Factory(targets, lowercase_envelope=True),
        ),
        clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
    )
    assert len(results) == 3
    for target in targets:
        evidence = read_rakuten_product_evidence(
            repository, product_id=target.product_id
        )
        assert evidence.item_code == target.fixed_item_code


def test_capture_selects_first_provider_image_with_exact_128_dimensions(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    factory = _Factory(targets, first_image_not_square=True)
    results = capture_article_products(
        repository,
        article_id=ARTICLE_ID,
        connection_factory=cast(RakutenHttpsConnectionFactory, factory),
        clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
    )

    for target in targets:
        evidence = read_rakuten_product_evidence(
            repository, product_id=target.product_id
        )
        assert "-non-square.png" not in evidence.image_url
        assert evidence.width == evidence.height == 128
    assert [result.request_count for result in results] == [4, 4, 4]


def test_capture_rejects_unrequested_provider_fields(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, extra_provider_field=True),
            ),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.RESPONSE_INVALID


def test_capture_rejects_compact_response_with_more_rows_than_requested(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, compact_extra_row=True),
            ),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.RESPONSE_INVALID
    assert captured.value.credentials_used is True


@pytest.mark.parametrize(
    "reflected_value",
    ("test-access", "test%2Daccess", "test-app", "test-affiliate"),
)
def test_capture_rejects_raw_and_percent_decoded_credential_reflection(
    private_root_path: Path,
    clean_network_environment: None,
    reflected_value: str,
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, reflected_value=reflected_value),
            ),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.CREDENTIAL_REFLECTION


def test_capture_rejects_truncated_image_with_valid_header_dimensions(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, truncated_image=True),
            ),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.IMAGE_INVALID


@pytest.mark.parametrize("raw", (_png(width=96), _gif(valid_lzw=True, width=96)))
def test_capture_image_parser_rejects_non_target_dimensions_at_header(
    raw: bytes,
) -> None:
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_module._image_dimensions(raw)  # type: ignore[attr-defined]
    assert captured.value.code is RakutenProductCaptureFailureCode.IMAGE_INVALID


def test_capture_rejects_crc_valid_png_with_invalid_compressed_pixels(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, invalid_compressed_image=True),
            ),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.IMAGE_INVALID


def test_capture_rejects_indexed_png_without_required_palette(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, indexed_image_without_palette=True),
            ),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.IMAGE_INVALID


def test_capture_rejects_indexed_png_sample_outside_palette(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, indexed_image_outside_palette=True),
            ),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.IMAGE_INVALID


def test_capture_rejects_palette_after_zero_length_idat(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, malformed_idat_sequence=True),
            ),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.IMAGE_INVALID


def test_capture_rejects_framed_gif_with_invalid_lzw_pixels(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, invalid_gif_image=True),
            ),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.IMAGE_INVALID


def test_capture_rejects_non_target_gif_dimensions_before_lzw_decode(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, non_target_gif_dimensions=True),
            ),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.IMAGE_INVALID


def test_capture_rejects_framed_jpeg_with_incomplete_entropy_pixels(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, invalid_jpeg_image=True),
            ),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.IMAGE_INVALID


def test_capture_rejects_jpeg_huffman_table_with_all_ones_code(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, invalid_jpeg_huffman=True),
            ),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.IMAGE_INVALID


def test_capture_rejects_non_target_jpeg_dimensions_before_scan_decode(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, non_target_jpeg_dimensions=True),
            ),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.IMAGE_INVALID


def test_malformed_credentialed_provider_item_url_is_a_response_failure(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, malformed_item_url=True),
            ),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.RESPONSE_INVALID
    assert captured.value.credentials_used is True


def test_capture_rejects_item_url_from_different_shop_than_item_code(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, mismatched_item_url_shop=True),
            ),
        )
    assert (
        captured.value.code is RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_INVALID
    )
    assert captured.value.credentials_used is True


def test_malformed_credentialed_provider_json_is_a_response_failure(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory,
                _Factory(targets, malformed_provider_json=True),
            ),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.RESPONSE_INVALID
    assert captured.value.credentials_used is True


def test_capture_rejects_oversized_provider_image_candidate_list_before_download(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    targets = load_product_capture_plan(repository).for_article(ARTICLE_ID)
    factory = _Factory(targets, image_candidate_count=4)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=ARTICLE_ID,
            connection_factory=cast(RakutenHttpsConnectionFactory, factory),
        )
    assert captured.value.code is RakutenProductCaptureFailureCode.IMAGE_INVALID
    assert not any(
        host == "thumbnail.image.rakuten.co.jp" for host, _path in factory.requests
    )


def test_owner_request_pacing_is_shared_between_instances(
    private_root_path: Path,
) -> None:
    directory = private_root_path / "pacing"
    directory.mkdir(mode=0o700)
    pacing_file = directory / "request-pacing.v1"
    observed_ns = [5_000_000_000]
    sleeps: list[float] = []

    def clock_ns() -> int:
        return observed_ns[0]

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        observed_ns[0] += round(seconds * 1_000_000_000)

    first = _OwnerRequestPacer(pacing_file, clock_ns=clock_ns, sleeper=sleeper)
    second = _OwnerRequestPacer(pacing_file, clock_ns=clock_ns, sleeper=sleeper)
    first_lease = first.acquire()
    probe = os.open(pacing_file, os.O_RDWR | os.O_CLOEXEC)
    try:
        with pytest.raises(BlockingIOError):
            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(probe)
    observed_ns[0] += 2_000_000_000
    first.release(first_lease)
    second_lease = second.acquire()
    second.release(second_lease)

    assert sleeps == [pytest.approx(1.1)]
    assert pacing_file.stat().st_mode & 0o777 == 0o600


def test_system_factory_accepts_absolute_posix_repository_path(
    private_root_path: Path,
) -> None:
    repository = _private_root(private_root_path)
    factory = SystemRakutenHttpsConnectionFactory(repository)
    assert type(factory) is SystemRakutenHttpsConnectionFactory


def test_system_factory_store_refusal_precedes_credentialed_request(
    private_root_path: Path,
) -> None:
    repository = _private_root(private_root_path)
    owner_directory = repository / ".secrets/st1704-self-hosted-editorial-pilot"
    owner_directory.mkdir(mode=0o700)
    owner_directory.chmod(0o755)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        SystemRakutenHttpsConnectionFactory(repository)
    assert captured.value.code is RakutenProductCaptureFailureCode.STORE_UNSAFE
    assert captured.value.credentials_used is False


def test_ambiguous_discovery_stops_before_discovered_product_evidence(
    private_root_path: Path,
    clean_network_environment: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _private_root(private_root_path)
    fixed_codes = dict(capture_module._FIXED_PRODUCT_ITEM_CODES)
    del fixed_codes["PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY"]
    monkeypatch.setattr(capture_module, "_FIXED_PRODUCT_ITEM_CODES", fixed_codes)
    targets = load_product_capture_plan(repository).for_article(DISCOVERY_ARTICLE_ID)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=DISCOVERY_ARTICLE_ID,
            connection_factory=cast(
                RakutenHttpsConnectionFactory, _Factory(targets, ambiguous=True)
            ),
            clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
        )
    assert (
        captured.value.code
        is RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_AMBIGUOUS
    )
    directory = repository / ".secrets/st1704-self-hosted-editorial-pilot/rakuten"
    discovered_target = next(
        target for target in targets if target.fixed_item_code is None
    )
    assert not (directory / f"{discovered_target.product_id}.v1.json").exists()


def test_discovery_aggregates_identity_across_every_allowed_variant(
    private_root_path: Path,
    clean_network_environment: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _private_root(private_root_path)
    fixed_codes = dict(capture_module._FIXED_PRODUCT_ITEM_CODES)
    del fixed_codes["PRD-THANKO-RAKUA-MINI-PLUS"]
    monkeypatch.setattr(capture_module, "_FIXED_PRODUCT_ITEM_CODES", fixed_codes)
    targets = load_product_capture_plan(repository).for_article(DISHWASHER_ARTICLE_ID)
    factory = _Factory(targets)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(
            repository,
            article_id=DISHWASHER_ARTICLE_ID,
            connection_factory=cast(RakutenHttpsConnectionFactory, factory),
        )
    assert (
        captured.value.code
        is RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_AMBIGUOUS
    )
    keyword_requests = [
        path
        for host, path in factory.requests
        if host == "openapi.rakuten.co.jp" and "keyword=" in path
    ]
    assert len(keyword_requests) == 2


def test_capture_failure_and_repr_never_expose_credentials(
    private_root_path: Path, clean_network_environment: None
) -> None:
    repository = _private_root(private_root_path)
    credential = repository / ".secrets/rakuten-owner-local/credentials.v1.json"
    credential.chmod(0o644)
    with pytest.raises(RakutenProductCaptureFailure) as captured:
        capture_article_products(repository, article_id=ARTICLE_ID)
    rendered = f"{captured.value!s} {captured.value!r}"
    assert captured.value.code is RakutenProductCaptureFailureCode.CREDENTIAL_UNSAFE
    assert captured.value.credentials_used is False
    assert "test-app" not in rendered
    assert "test-access" not in rendered
    assert "test-affiliate" not in rendered


def test_separate_manifest_keeps_publication_absent_and_wordpress_runtime_unchanged() -> (
    None
):
    manifest = json.loads(manifest_builder.build_manifest())
    assert manifest["external_action_authority"] == "HUMAN_OWNER_BOUNDED_RAKUTEN_READ"
    assert manifest["publication_authority"] == "NONE"
    assert manifest["article_ids"] == list(manifest_builder.ARTICLE_IDS)
    paths = [row["path"] for row in manifest["paths"]]
    assert paths == list(manifest_builder.REQUIRED_RUNTIME_PATHS)
    assert "scripts/st1704_self_hosted_editorial_pilot.py" not in paths
