"""Preparation, owner evidence, HTTPS, and CLI tests for ST-1704."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
from types import SimpleNamespace
from typing import cast
from urllib.parse import parse_qs, urlencode, urlsplit
import zlib

import pytest

import raos.adapters.self_hosted_editorial_pilot_https as https_module
import raos.adapters.self_hosted_editorial_pilot_json as json_module
import raos.application.editorial.self_hosted_editorial_pilot as application_module
import raos.domain.editorial.self_hosted_editorial_pilot as domain_module
from raos.adapters.self_hosted_editorial_pilot_https import (
    OWNER_GATE_AUTHORITY,
    OWNER_GATE_DIRECTORY,
    OWNER_GATE_SCHEMA,
    OfficialSelfHostedEditorialPilotWordPressAdapter,
    SELF_HOSTED_WORDPRESS_HOST,
    SELF_HOSTED_WORDPRESS_PORT,
    owner_gate_relative_path,
    require_owner_live_gate,
)
from raos.adapters.self_hosted_editorial_pilot_json import (
    JOURNAL_DIRECTORY,
    OWNER_DIRECTORY,
    OwnerPrivateLiveReviewDraftJournal,
    RAKUTEN_DIRECTORY,
    SOURCE_DIRECTORY,
    read_official_source_capture_evidence,
    read_rakuten_product_evidence,
    rakuten_affiliate_response_relative_path,
    rakuten_image_relative_path,
    rakuten_response_relative_path,
    request_artifact_relative_path,
    source_body_relative_path,
    source_evidence_relative_path,
)
from raos.application.editorial.self_hosted_editorial_pilot import (
    prepare_editorial_article,
)
from raos.domain.editorial.self_hosted_editorial_pilot import (
    CarryOnSingleUrlReconciliationBinding,
    CarryOnSingleUrlReconciliationEvidence,
    EditorialPilotFailure,
    EditorialPilotFailureCode,
    PILOT_ARTICLE_IDENTITIES,
    PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID,
    PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID,
    PILOT_CARRY_ON_RECONCILIATION_TARGET_PUBLIC_POST_ID,
    PILOT_CREATE_PATH,
    PILOT_CTA_LABEL,
    PILOT_PUBLIC_VERIFICATION_CHECKS,
    PILOT_SNAPSHOT_META_KEY,
    OfficialSourceCaptureEvidence,
    PublicVerification,
    RakutenProductEvidence,
    ReviewDraftDisposition,
    ReviewDraftReceipt,
    ReviewDraftRequest,
    bytes_sha256,
    canonical_json_bytes,
    canonical_sha256,
)
from .test_self_hosted_editorial_pilot import request


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SLICE_ROOT = REPOSITORY_ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1"
SCRIPT = REPOSITORY_ROOT / "scripts/st1704_self_hosted_editorial_pilot.py"
_POLICY = (
    ("aspect_ratio_change_allowed", False),
    ("crop_allowed", False),
    ("modification_allowed", False),
    ("text_overlay_allowed", False),
    ("upscale_allowed", False),
)
_WORDPRESS_API_DISCOVERY_LINK = (
    '<https://kurashinoshirube.com/wp-json/>; rel="https://api.w.org/"'
)


def _fixed_clock() -> datetime:
    return datetime(2026, 8, 26, 11, 30, tzinfo=timezone.utc)


def _documents() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    return tuple(  # type: ignore[return-value]
        json.loads((SLICE_ROOT / relative).read_text(encoding="utf-8"))
        for relative in (
            "content/articles.v1.json",
            "sources/source-registry.v1.json",
            "media/product-media-registry.v1.json",
        )
    )


def _synthetic_evidence(product_id: str) -> RakutenProductEvidence:
    _articles, sources, media = _documents()
    asset = next(
        cast(dict[str, object], value)
        for value in cast(list[object], media["assets"])
        if cast(dict[str, object], value)["product_id"] == product_id
    )
    affiliate = next(
        cast(dict[str, object], value)
        for value in cast(list[object], sources["affiliate_resources"])
        if cast(dict[str, object], value)["product_id"] == product_id
    )
    tail = product_id.lower().removeprefix("prd-")
    item_url = f"https://item.rakuten.co.jp/test-shop/{tail}/"
    assert affiliate["destination_url"] is None
    assert affiliate["evidence"] is None
    destination = "https://hb.afl.rakuten.co.jp/hgc/test.abc/?" + urlencode(
        {
            "m": f"https://m.rakuten.co.jp/test-shop/i/{tail}/",
            "pc": item_url,
            "rafcid": "synthetic-test",
        }
    )
    item_code = f"{urlsplit(item_url).path.split('/')[1]}:{tail}"
    identity = cast(dict[str, object], asset["identity"])
    jan = cast(str | None, identity["jan"])
    variant = cast(list[str], identity["allowed_variants"])[0]
    required_tokens = cast(list[str], identity["required_title_tokens"])
    kind_token = cast(list[str], identity["product_kind_tokens"])[0]
    item_name = " ".join(
        [cast(str, asset["product_name"]), *required_tokens, kind_token]
    )
    response = (
        canonical_json_bytes(
            {
                "Items": [
                    {
                        "itemCode": item_code,
                        "itemName": item_name,
                        "itemUrl": item_url,
                        "mediumImageUrls": [
                            "https://thumbnail.image.rakuten.co.jp/@0_mall/test-shop/"
                            f"cabinet/{tail}.jpg?_ex=128x128"
                        ],
                    }
                ],
            }
        )
        + b"\n"
    )
    image = _synthetic_image_bytes()
    request_material = {
        "api_version": "2026-07-01",
        "elements": [
            "itemCode",
            "itemName",
            "itemUrl",
            "mediumImageUrls",
        ],
        "endpoint": (
            "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
        ),
        "format": "json",
        "format_version": 2,
        "affiliate_id_supplied": False,
        "image_flag": 1,
        "item_code": item_code,
        "schema": "RAOS_ST1704_RAKUTEN_ITEM_SEARCH_REQUEST_V1",
        "secret_fields_excluded": ["accessKey", "affiliateId", "applicationId"],
    }
    image_url = (
        "https://thumbnail.image.rakuten.co.jp/@0_mall/test-shop/"
        f"cabinet/{tail}.jpg?_ex=128x128"
    )
    selected_result = {
        "image_url": image_url,
        "item_code": item_code,
        "item_name": item_name,
        "jan": jan,
        "schema": "RAOS_ST1704_RAKUTEN_PROVIDER_IDENTITY_V1",
        "source_url": item_url,
    }
    affiliate_request_material = {
        **request_material,
        "affiliate_id_supplied": True,
        "elements": [
            "affiliateUrl",
            "itemCode",
            "itemName",
            "itemUrl",
            "mediumImageUrls",
        ],
    }
    affiliate_response = (
        canonical_json_bytes(
            {
                "Items": [
                    {
                        "affiliateUrl": destination,
                        "itemCode": item_code,
                        "itemName": item_name,
                        "itemUrl": destination,
                        "mediumImageUrls": [image_url],
                    }
                ],
            }
        )
        + b"\n"
    )
    affiliate_selected_result = {
        "affiliate_url": destination,
        "image_url": image_url,
        "item_code": item_code,
        "item_name": item_name,
        "item_url": destination,
        "jan": jan,
        "schema": "RAOS_ST1704_RAKUTEN_AFFILIATE_PROVIDER_IDENTITY_V1",
    }
    return RakutenProductEvidence(
        product_id=product_id,
        affiliate_ref=cast(str, affiliate["affiliate_ref"]),
        media_asset_ref=cast(str, asset["media_asset_ref"]),
        item_code=item_code,
        item_name=item_name,
        jan=jan,
        variant=variant,
        source_url=item_url,
        destination_url=cast(str, destination),
        image_url=image_url,
        width=128,
        height=128,
        retrieved_at="2026-08-26T11:00:00Z",
        request_fingerprint=canonical_sha256(request_material),
        response_sha256=bytes_sha256(response),
        selected_result_sha256=canonical_sha256(selected_result),
        affiliate_request_fingerprint=canonical_sha256(affiliate_request_material),
        affiliate_response_sha256=bytes_sha256(affiliate_response),
        affiliate_selected_result_sha256=canonical_sha256(affiliate_selected_result),
        image_sha256=bytes_sha256(image),
        no_modification_policy=_POLICY,
    )


def _synthetic_image_bytes(
    *,
    compressed_payload: bytes | None = None,
    color_type: int = 2,
    include_palette: bool = False,
    indexed_sample: int = 0,
    width: int = 128,
    height: int = 128,
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


def _synthetic_gif_bytes(
    *, valid_lzw: bool, width: int = 128, height: int = 128
) -> bytes:
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


def _synthetic_jpeg_bytes(
    *, valid_entropy: bool, width: int = 128, height: int = 128
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
    dht = b"\x00" + counts + b"\x00" + b"\x10" + counts + b"\x00"
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


def _synthetic_response_bytes(evidence: RakutenProductEvidence) -> bytes:
    return (
        canonical_json_bytes(
            {
                "Items": [
                    {
                        "itemCode": evidence.item_code,
                        "itemName": evidence.item_name,
                        "itemUrl": evidence.source_url,
                        "mediumImageUrls": [evidence.image_url],
                    }
                ],
            }
        )
        + b"\n"
    )


def _synthetic_affiliate_response_bytes(evidence: RakutenProductEvidence) -> bytes:
    return (
        canonical_json_bytes(
            {
                "Items": [
                    {
                        "affiliateUrl": evidence.destination_url,
                        "itemCode": evidence.item_code,
                        "itemName": evidence.item_name,
                        "itemUrl": evidence.destination_url,
                        "mediumImageUrls": [evidence.image_url],
                    }
                ],
            }
        )
        + b"\n"
    )


def _reader(repository_root: Path, *, product_id: str) -> RakutenProductEvidence:
    assert repository_root == REPOSITORY_ROOT
    return _synthetic_evidence(product_id)


def _source_reader(
    repository_root: Path, *, source_ref: str
) -> OfficialSourceCaptureEvidence:
    assert repository_root == REPOSITORY_ROOT
    _articles, sources, _media = _documents()
    registry_sources = [
        *cast(list[dict[str, object]], sources["sources"]),
        *cast(list[dict[str, object]], sources["policy_sources"]),
    ]
    source = next(
        value for value in registry_sources if value["source_ref"] == source_ref
    )
    policy_refs = {
        value["source_ref"]
        for value in cast(list[dict[str, object]], sources["policy_sources"])
    }
    if source_ref in policy_refs:
        claim_records = [("POLICY-SOURCE-STATEMENT", cast(str, source["title"]))]
    else:
        claim_records = sorted(
            (cast(str, claim["claim_id"]), cast(str, claim["statement"]))
            for packet in cast(list[dict[str, object]], sources["source_packets"])
            for claim in cast(list[dict[str, object]], packet["claims"])
            if source_ref in cast(list[str], claim["evidence_refs"])
        )
    locators = tuple(
        (
            claim_id,
            bytes_sha256(statement.encode()),
            (
                (
                    f"{claim_id}: {statement}",
                    bytes_sha256(f"{claim_id}: {statement}".encode()),
                ),
            ),
        )
        for claim_id, statement in claim_records
    )
    retrieved_at = f"{cast(str, source['retrieved_on'])}T00:00:00Z"
    content_type = (
        "application/pdf" if source["source_type"] == "PRODUCT_MANUAL" else "text/html"
    )
    body = _source_body_bytes(content_type, locators)
    body_sha256 = bytes_sha256(body)
    material = {
        "body_sha256": body_sha256,
        "content_type": content_type,
        "final_url": source["url"],
        "http_status": 200,
        "retrieved_at": retrieved_at,
        "schema": "RAOS_ST1704_OFFICIAL_SOURCE_CAPTURE_V1",
        "source_ref": source_ref,
    }
    return OfficialSourceCaptureEvidence(
        source_ref=source_ref,
        final_url=cast(str, source["url"]),
        retrieved_at=retrieved_at,
        content_type=content_type,
        body_sha256=body_sha256,
        response_sha256=canonical_sha256(material),
        locators=locators,
    )


def _source_body_bytes(
    content_type: str,
    locators: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...],
) -> bytes:
    fragments = "\n".join(
        fragment
        for _claim, _statement, fragment_records in locators
        for fragment, _hash in fragment_records
    )
    if content_type == "application/pdf":
        return f"%PDF-1.7\n{fragments}\n%%EOF\n".encode()
    if content_type == "text/html":
        return f"<!doctype html><html><body>{fragments}</body></html>".encode()
    raise AssertionError("unsupported synthetic content type")


@pytest.fixture
def private_root() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(
        prefix="raos-st1704-evidence-", dir="/var/tmp"
    ) as directory:
        yield Path(directory)


class _ArtifactJournalPort:
    def __init__(
        self,
        *,
        create_fails: bool = False,
        recover_fails: bool = False,
        target_public_post_id: int = 42,
    ) -> None:
        self.create_fails = create_fails
        self.recover_fails = recover_fails
        self.target_public_post_id = target_public_post_id
        self.created: list[ReviewDraftRequest] = []
        self.recovered: list[ReviewDraftRequest] = []
        self.verified: list[ReviewDraftRequest] = []
        self.verified_public_post_ids: list[int] = []

    def preflight(self, request: ReviewDraftRequest, command: str) -> None:
        assert request.article_id in {
            identity.article_id for identity in PILOT_ARTICLE_IDENTITIES
        }
        assert command in {
            "create-review-draft",
            "recover-create-review-draft",
            "verify-carry-on-single-url",
            "verify-public",
        }

    def resolve_public_target(
        self, request: ReviewDraftRequest, command: str
    ) -> int | None:
        assert command in {"create-review-draft", "recover-create-review-draft"}
        return (
            self.target_public_post_id
            if request.article_id == PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID
            else None
        )

    def create(self, request: ReviewDraftRequest) -> ReviewDraftReceipt:
        self.created.append(request)
        if self.create_fails:
            raise EditorialPilotFailure(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
        return self._receipt(request, ReviewDraftDisposition.OWNER_LIVE_CREATED)

    def recover(self, request: ReviewDraftRequest) -> ReviewDraftReceipt:
        self.recovered.append(request)
        if self.recover_fails:
            raise EditorialPilotFailure(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
        return self._receipt(request, ReviewDraftDisposition.OWNER_LIVE_RECOVERED)

    def verify_public(
        self, request: ReviewDraftRequest, expected_public_post_id: int
    ) -> PublicVerification:
        self.verified.append(request)
        self.verified_public_post_ids.append(expected_public_post_id)
        return PublicVerification(
            article_id=request.article_id,
            packet_sha256=request.packet_sha256,
            request_sha256=request.request_sha256,
            response_sha256="e" * 64,
            post_id=expected_public_post_id,
            status="publish",
        )

    def verify_carry_on_single_url(
        self, binding: CarryOnSingleUrlReconciliationBinding
    ) -> CarryOnSingleUrlReconciliationEvidence:
        request = binding.request
        self.verified.append(request)
        self.verified_public_post_ids.append(binding.target_public_post_id)
        surface_hashes = {
            "article_html_sha256": "1" * 64,
            "category_sha256": "2" * 64,
            "core_sitemap_sha256": "3" * 64,
            "homepage_html_sha256": "4" * 64,
            "homepage_targets_sha256": "5" * 64,
            "page_sitemap_sha256": "6" * 64,
            "post_sitemap_sha256": "7" * 64,
            "related_target_sha256": "8" * 64,
            "review_draft_rest_evidence_sha256": "9" * 64,
            "review_public_rest_evidence_sha256": "a" * 64,
            "review_url_html_evidence_sha256": "b" * 64,
            "robots_sha256": "c" * 64,
            "sitemap_index_sha256": "d" * 64,
        }
        strict_verification = PublicVerification(
            article_id=request.article_id,
            packet_sha256=request.packet_sha256,
            request_sha256=request.request_sha256,
            response_sha256="e" * 64,
            post_id=binding.target_public_post_id,
            status="publish",
            expected_public_post_id=binding.target_public_post_id,
            target_public_post_id=binding.target_public_post_id,
            review_draft_post_id=binding.expected_review_draft_post_id,
            public_surface_sha256=canonical_sha256(surface_hashes),
            verified_checks=PILOT_PUBLIC_VERIFICATION_CHECKS,
            public_surface_verified=True,
            recorded_evidence_only=False,
            live_read=True,
            **surface_hashes,
        )
        return CarryOnSingleUrlReconciliationEvidence.from_strict_verification(
            binding, strict_verification
        )

    def _receipt(
        self, request: ReviewDraftRequest, disposition: ReviewDraftDisposition
    ) -> ReviewDraftReceipt:
        return ReviewDraftReceipt(
            article_id=request.article_id,
            packet_sha256=request.packet_sha256,
            request_sha256=request.request_sha256,
            response_sha256="d" * 64,
            draft_id=1704,
            disposition=disposition,
            target_public_post_id=(
                self.target_public_post_id
                if request.article_id == PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID
                else None
            ),
            recorded_evidence_only=False,
            live_authority=True,
        )


def _install_overlay(root: Path, evidence: RakutenProductEvidence) -> Path:
    directory = root / ".secrets" / OWNER_DIRECTORY / RAKUTEN_DIRECTORY
    directory.mkdir(parents=True, mode=0o700)
    (root / ".secrets").chmod(0o700)
    (root / ".secrets" / OWNER_DIRECTORY).chmod(0o700)
    directory.chmod(0o700)
    document = {
        "affiliate_request_fingerprint": evidence.affiliate_request_fingerprint,
        "affiliate_ref": evidence.affiliate_ref,
        "affiliate_response_sha256": evidence.affiliate_response_sha256,
        "affiliate_selected_result_sha256": (evidence.affiliate_selected_result_sha256),
        "destination_url": evidence.destination_url,
        "height": evidence.height,
        "image_sha256": evidence.image_sha256,
        "image_url": evidence.image_url,
        "item_code": evidence.item_code,
        "item_name": evidence.item_name,
        "jan": evidence.jan,
        "media_asset_ref": evidence.media_asset_ref,
        "no_modification_policy": dict(evidence.no_modification_policy),
        "product_id": evidence.product_id,
        "request_fingerprint": evidence.request_fingerprint,
        "response_sha256": evidence.response_sha256,
        "retrieved_at": evidence.retrieved_at,
        "schema": evidence.schema,
        "selected_result_sha256": evidence.selected_result_sha256,
        "source_url": evidence.source_url,
        "variant": evidence.variant,
        "width": evidence.width,
    }
    path = directory / f"{evidence.product_id}.v1.json"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        payload = canonical_json_bytes(document) + b"\n"
        assert os.write(descriptor, payload) == len(payload)
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    response_path = root / rakuten_response_relative_path(evidence.product_id)
    response_payload = _synthetic_response_bytes(evidence)
    assert bytes_sha256(response_payload) == evidence.response_sha256
    response_descriptor = os.open(
        response_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    try:
        assert os.write(response_descriptor, response_payload) == len(response_payload)
        os.fchmod(response_descriptor, 0o600)
    finally:
        os.close(response_descriptor)
    affiliate_response_path = root / rakuten_affiliate_response_relative_path(
        evidence.product_id
    )
    affiliate_response_payload = _synthetic_affiliate_response_bytes(evidence)
    assert (
        bytes_sha256(affiliate_response_payload) == evidence.affiliate_response_sha256
    )
    affiliate_response_descriptor = os.open(
        affiliate_response_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    try:
        assert os.write(
            affiliate_response_descriptor, affiliate_response_payload
        ) == len(affiliate_response_payload)
        os.fchmod(affiliate_response_descriptor, 0o600)
    finally:
        os.close(affiliate_response_descriptor)
    image_path = root / rakuten_image_relative_path(evidence.product_id)
    image_payload = _synthetic_image_bytes()
    assert bytes_sha256(image_payload) == evidence.image_sha256
    image_descriptor = os.open(image_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        assert os.write(image_descriptor, image_payload) == len(image_payload)
        os.fchmod(image_descriptor, 0o600)
    finally:
        os.close(image_descriptor)
    return path


def _install_source_overlay(
    root: Path, evidence: OfficialSourceCaptureEvidence
) -> tuple[Path, Path]:
    directory = root / ".secrets" / OWNER_DIRECTORY / SOURCE_DIRECTORY
    directory.mkdir(parents=True, mode=0o700)
    (root / ".secrets").chmod(0o700)
    (root / ".secrets" / OWNER_DIRECTORY).chmod(0o700)
    directory.chmod(0o700)
    metadata_path = root / source_evidence_relative_path(evidence.source_ref)
    body_path = root / source_body_relative_path(evidence.source_ref)
    metadata = canonical_json_bytes(evidence.value()) + b"\n"
    body = _source_body_bytes(evidence.content_type, evidence.locators)
    assert bytes_sha256(body) == evidence.body_sha256
    for path, payload in ((metadata_path, metadata), (body_path, body)):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            assert os.write(descriptor, payload) == len(payload)
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)
    return metadata_path, body_path


def test_all_five_packets_render_deterministically_with_closed_draft_payload() -> None:
    total_cards = 0
    for identity in PILOT_ARTICLE_IDENTITIES:
        is_replacement_article = (
            identity.article_id
            == "st1704-countertop-dishwasher-for-small-households"
        )
        clock = (
            (lambda: datetime(2026, 8, 26, 11, 0, tzinfo=timezone.utc))
            if is_replacement_article
            else _fixed_clock
        )
        evidence_reader = (
            (
                lambda repository_root, *, product_id: replace(
                    _reader(repository_root, product_id=product_id),
                    retrieved_at="2026-08-26T11:00:00Z",
                )
            )
            if is_replacement_article
            else _reader
        )
        first = prepare_editorial_article(
            REPOSITORY_ROOT,
            identity.article_id,
            evidence_reader=evidence_reader,
            source_evidence_reader=_source_reader,
            clock=clock,
        )
        second = prepare_editorial_article(
            REPOSITORY_ROOT,
            identity.article_id,
            evidence_reader=evidence_reader,
            source_evidence_reader=_source_reader,
            clock=clock,
        )
        assert first.packet_sha256 == second.packet_sha256
        assert first.request.request_sha256 == second.request.request_sha256
        assert first.request.content == second.request.content
        assert set(first.request.wordpress_body()) == {
            "content",
            "excerpt",
            "meta",
            "slug",
            "status",
            "title",
        }
        assert first.request.wordpress_body()["status"] == "draft"
        assert set(cast(dict[str, object], first.request.wordpress_body()["meta"])) == {
            PILOT_SNAPSHOT_META_KEY
        }
        content = first.request.content
        assert content.startswith(
            '<div class="raos-editorial-v2">\n<dl class="raos-article-facts'
        )
        assert content.endswith("</div>\n")
        assert content.index('<dl class="raos-article-facts') < content.index(
            '<aside class="raos-disclosure disclosure"'
        )
        assert "<h1" not in content.lower()
        assert content.count('class="raos-product-card product-profile ') == (
            first.product_count
        )
        assert content.count('class="raos-product-card__media"') == first.product_count
        assert content.count('class="raos-comparison__table-view"') == 1
        assert content.count('data-raos-placement="comparison_table"') == 1
        assert content.count('class="raos-comparison__cards"') == 1
        assert content.count('class="raos-comparison-card"') == first.product_count
        assert "<dl><div><dt>商品</dt><dd>" in content
        assert content.count('width="128" height="128"') == first.product_count
        assert content.count('class="raos-cta rakuten-cta"') == (
            first.product_count * 2
        )
        assert content.count(PILOT_CTA_LABEL) == first.product_count * 2
        assert 'data-raos-evidence-level="A"' in content
        assert "A：公式仕様" in content
        if identity.article_id == "st1703-first-suitcase-comparison":
            assert "UNKNOWN：未確認" in content
        assert content.count('class="raos-comparison__product-image"') == (
            first.product_count * 2
        )
        assert content.count("Supported by Rakuten Developers") == 1
        assert 'rel="sponsored nofollow"' in content
        assert content.count('data-raos-placement="product_card"') == (
            first.product_count
        )
        assert content.count('data-raos-placement="final_summary"') == (
            first.product_count
        )
        assert "公式サイトで仕様を確認する" in content
        assert 'class="raos-decision-summary__link"' in content
        if identity.article_id == "st1703-first-suitcase-comparison":
            assert 'class="raos-article-facts article-meta"' in content
            assert "エース系3モデル" in content
            assert "市場全体のおすすめ順位ではなく" in content
            assert "<dt>実機確認</dt><dd>未実施" in content
            assert content.index("<dt>対象読者</dt>") < content.index("広告を含みます。")
            assert content.index("広告を含みます。") < content.index("比較範囲：")
            assert "D：編集部の判断" in content
        assert first.request.snapshot.payload.seo_title
        assert first.request.snapshot.payload.seo_title != ""
        assert first.request.snapshot.payload.packet_sha256 == first.packet_sha256
        assert "raos-related-guides" not in content
        assert all(
            f'href="/{other.slug}/"' not in content
            for other in PILOT_ARTICLE_IDENTITIES
        )
        assert not first.publication_authority
        assert not first.production_evidence
        assert first.network_requests == first.external_writes == 0
        total_cards += first.product_count
    assert total_cards == 19


def test_rendered_content_parser_accepts_strict_official_cta_arrow() -> None:
    parser = https_module._RenderedContentParser()  # type: ignore[attr-defined]
    parser.feed(
        '<a class="official-product-link raos-cta" '
        'href="https://www.ankerjapan.com/products/a1722" '
        'rel="noopener noreferrer" '
        'data-raos-article-id="st1704-portable-power-station-guide" '
        'data-raos-product-id="PRD-ANKER-SOLIX-C300" '
        'data-raos-placement="final_summary">'
        'メーカー公式で仕様を確認する '
        '<span aria-hidden="true">→</span></a>'
    )
    parser.close()

    assert parser.cta_active is None
    assert parser.cta_span_open is False
    assert parser.rakuten_hrefs == []
    assert parser.cta_records == [
        (
            "https://www.ankerjapan.com/products/a1722",
            "noopener noreferrer",
            "st1704-portable-power-station-guide",
            "PRD-ANKER-SOLIX-C300",
            "final_summary",
            "メーカー公式で仕様を確認する →",
        )
    ]


@pytest.mark.parametrize(
    "nested_markup",
    [
        '<span aria-hidden="false">→</span>',
        "<strong>→</strong>",
        (
            '<span aria-hidden="true"><span aria-hidden="true">'
            "→</span></span>"
        ),
        '<span aria-hidden="true">→</a>',
    ],
)
def test_rendered_content_parser_rejects_noncanonical_cta_arrow(
    nested_markup: str,
) -> None:
    parser = https_module._RenderedContentParser()  # type: ignore[attr-defined]
    markup = (
        '<a class="official-product-link raos-cta" '
        'href="https://www.ankerjapan.com/products/a1722" '
        'rel="noopener noreferrer" '
        'data-raos-article-id="st1704-portable-power-station-guide" '
        'data-raos-product-id="PRD-ANKER-SOLIX-C300" '
        'data-raos-placement="final_summary">'
        f"メーカー公式で仕様を確認する {nested_markup}</a>"
    )

    with pytest.raises(EditorialPilotFailure) as failure:
        parser.feed(markup)

    assert failure.value.code is EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH


def test_committed_request_survives_three_day_freshness_and_shared_c300_refresh(
    private_root: Path,
) -> None:
    article_id = "st1704-portable-power-station-guide"
    original = prepare_editorial_article(
        REPOSITORY_ROOT,
        article_id,
        evidence_reader=_reader,
        source_evidence_reader=_source_reader,
        clock=_fixed_clock,
    )
    port = _ArtifactJournalPort()
    journal = OwnerPrivateLiveReviewDraftJournal(private_root, port)
    journal.create(original.request)
    day_seven = datetime(2026, 8, 29, 11, 30, tzinfo=timezone.utc)

    with pytest.raises(EditorialPilotFailure) as stale_current_evidence:
        prepare_editorial_article(
            REPOSITORY_ROOT,
            article_id,
            evidence_reader=_reader,
            source_evidence_reader=_source_reader,
            clock=lambda: day_seven,
        )
    assert (
        stale_current_evidence.value.code
        is EditorialPilotFailureCode.RESOURCE_NOT_READY
    )

    def refreshed_reader(root: Path, *, product_id: str) -> RakutenProductEvidence:
        del root
        return replace(
            _synthetic_evidence(product_id),
            retrieved_at="2026-08-29T11:00:00Z",
        )

    refreshed = prepare_editorial_article(
        REPOSITORY_ROOT,
        article_id,
        evidence_reader=refreshed_reader,
        source_evidence_reader=_source_reader,
        clock=lambda: day_seven,
    )
    assert refreshed.request.packet_sha256 != original.request.packet_sha256
    assert refreshed.request.request_sha256 != original.request.request_sha256

    persisted, expected_public_post_id = journal.committed_request(article_id)
    assert persisted == original.request
    assert persisted != refreshed.request
    assert expected_public_post_id == 1704


@pytest.mark.parametrize(
    ("hidden_block_index", "expected_type"),
    [(1, "lead"), (8, "product_card")],
    ids=["standalone-admin-only", "adjacent-product-card-admin-only"],
)
def test_prepare_and_renderer_reject_every_admin_only_block(
    monkeypatch: pytest.MonkeyPatch,
    hidden_block_index: int,
    expected_type: str,
) -> None:
    articles, _sources, _media = _documents()
    article = next(
        value
        for value in cast(list[dict[str, object]], articles["articles"])
        if value["article_id"] == "st1704-portable-power-station-guide"
    )
    ast_model = application_module.load_content_ast(  # type: ignore[attr-defined]
        canonical_json_bytes(article["content_ast"])
    )
    ast = cast(
        dict[str, object],
        ast_model.model_dump(mode="json", by_alias=True, warnings=False),
    )
    blocks = cast(list[dict[str, object]], ast["blocks"])
    assert blocks[hidden_block_index]["type"] == expected_type
    if expected_type == "product_card":
        assert blocks[hidden_block_index - 1]["type"] == "product_card"
    blocks[hidden_block_index]["visibility"] = "admin_only"
    model = SimpleNamespace(model_dump=lambda **_kwargs: ast)
    monkeypatch.setattr(
        application_module,
        "load_content_ast",
        lambda _raw: model,
    )

    with pytest.raises(EditorialPilotFailure) as prepared:
        prepare_editorial_article(
            REPOSITORY_ROOT,
            "st1704-portable-power-station-guide",
            evidence_reader=_reader,
            source_evidence_reader=_source_reader,
            clock=_fixed_clock,
        )
    assert prepared.value.code is EditorialPilotFailureCode.CONTENT_AST_INVALID

    renderer = application_module._Renderer.__new__(  # type: ignore[attr-defined]
        application_module._Renderer  # type: ignore[attr-defined]
    )
    with pytest.raises(EditorialPilotFailure) as rendered:
        renderer.render(ast)
    assert rendered.value.code is EditorialPilotFailureCode.CONTENT_AST_INVALID


def test_renderer_output_is_bound_into_packet_snapshot_and_review_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = prepare_editorial_article(
        REPOSITORY_ROOT,
        "st1704-portable-power-station-guide",
        evidence_reader=_reader,
        source_evidence_reader=_source_reader,
        clock=_fixed_clock,
    )
    original = application_module._Renderer.render  # type: ignore[attr-defined]

    def changed(renderer: object, ast: object) -> str:
        return (
            original(renderer, ast) + '<p class="renderer-contract-mutation">差分</p>'
        )

    monkeypatch.setattr(application_module._Renderer, "render", changed)  # type: ignore[attr-defined]
    mutated = prepare_editorial_article(
        REPOSITORY_ROOT,
        "st1704-portable-power-station-guide",
        evidence_reader=_reader,
        source_evidence_reader=_source_reader,
        clock=_fixed_clock,
    )
    assert mutated.packet_sha256 != baseline.packet_sha256
    assert mutated.request.request_sha256 != baseline.request.request_sha256
    assert (
        mutated.request.snapshot.payload_sha256
        != baseline.request.snapshot.payload_sha256
    )
    assert mutated.request.slug != baseline.request.slug


def test_freshness_boundaries_reject_stale_future_and_non_utc_clock() -> None:
    application_module._require_observed_date_not_future(  # type: ignore[attr-defined]
        "2020-01-01", now=datetime(2026, 8, 23, tzinfo=timezone.utc)
    )
    with pytest.raises(EditorialPilotFailure) as future_date:
        application_module._require_observed_date_not_future(  # type: ignore[attr-defined]
            "2026-08-24", now=datetime(2026, 8, 23, tzinfo=timezone.utc)
        )
    assert future_date.value.code is EditorialPilotFailureCode.RESOURCE_NOT_READY

    application_module._require_fresh_rakuten_timestamp(  # type: ignore[attr-defined]
        "2026-08-22T11:30:00Z",
        now=datetime(2026, 8, 23, 11, 30, tzinfo=timezone.utc),
    )
    with pytest.raises(EditorialPilotFailure) as stale_rakuten:
        application_module._require_fresh_rakuten_timestamp(  # type: ignore[attr-defined]
            "2026-08-22T11:29:59Z",
            now=datetime(2026, 8, 23, 11, 30, tzinfo=timezone.utc),
        )
    assert stale_rakuten.value.code is EditorialPilotFailureCode.RESOURCE_NOT_READY
    with pytest.raises(EditorialPilotFailure) as future_rakuten:
        application_module._require_fresh_rakuten_timestamp(  # type: ignore[attr-defined]
            "2026-08-23T11:30:01Z",
            now=datetime(2026, 8, 23, 11, 30, tzinfo=timezone.utc),
        )
    assert future_rakuten.value.code is EditorialPilotFailureCode.RESOURCE_NOT_READY

    with pytest.raises(EditorialPilotFailure) as non_utc:
        prepare_editorial_article(
            REPOSITORY_ROOT,
            "st1704-portable-power-station-guide",
            evidence_reader=_reader,
            source_evidence_reader=_source_reader,
            clock=lambda: datetime(
                2026, 8, 23, 20, 30, tzinfo=timezone(timedelta(hours=9))
            ),
        )
    assert non_utc.value.code is EditorialPilotFailureCode.RESOURCE_NOT_READY


def test_source_capture_time_is_truthful_monotonic_and_independently_fresh() -> None:
    def reader_at(retrieved_at: str):
        def read(root: Path, *, source_ref: str) -> OfficialSourceCaptureEvidence:
            original = _source_reader(root, source_ref=source_ref)
            material = original.response_material()
            material["retrieved_at"] = retrieved_at
            return replace(
                original,
                retrieved_at=retrieved_at,
                response_sha256=canonical_sha256(material),
            )

        return read

    current = prepare_editorial_article(
        REPOSITORY_ROOT,
        "st1704-portable-power-station-guide",
        evidence_reader=_reader,
        source_evidence_reader=reader_at("2026-08-23T10:00:00Z"),
        clock=_fixed_clock,
    )
    assert current.request.packet_sha256

    delayed_now = datetime(2026, 9, 15, 11, 30, tzinfo=timezone.utc)

    def current_products(root: Path, *, product_id: str) -> RakutenProductEvidence:
        del root
        return replace(
            _synthetic_evidence(product_id),
            retrieved_at="2026-09-15T11:00:00Z",
        )

    delayed = prepare_editorial_article(
        REPOSITORY_ROOT,
        "st1704-portable-power-station-guide",
        evidence_reader=current_products,
        source_evidence_reader=reader_at("2026-09-15T10:00:00Z"),
        clock=lambda: delayed_now,
    )
    assert delayed.request.packet_sha256 != current.request.packet_sha256

    with pytest.raises(EditorialPilotFailure) as backdated:
        prepare_editorial_article(
            REPOSITORY_ROOT,
            "st1704-portable-power-station-guide",
            evidence_reader=_reader,
            source_evidence_reader=reader_at("2026-08-11T23:59:59Z"),
            clock=_fixed_clock,
        )
    assert backdated.value.code is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID


def test_missing_or_cross_bound_product_evidence_fails_closed() -> None:
    def missing(root: Path, *, product_id: str) -> RakutenProductEvidence:
        del root, product_id
        raise EditorialPilotFailure(EditorialPilotFailureCode.RESOURCE_NOT_READY)

    with pytest.raises(EditorialPilotFailure) as absent:
        prepare_editorial_article(
            REPOSITORY_ROOT,
            "st1704-portable-power-station-guide",
            evidence_reader=missing,
            source_evidence_reader=_source_reader,
            clock=_fixed_clock,
        )
    assert absent.value.code is EditorialPilotFailureCode.RESOURCE_NOT_READY

    def mismatched(root: Path, *, product_id: str) -> RakutenProductEvidence:
        del root
        value = _synthetic_evidence(product_id)
        return RakutenProductEvidence(
            product_id=value.product_id,
            affiliate_ref=value.affiliate_ref,
            media_asset_ref="MEDIA-WRONG-BOUNDARY",
            item_code=value.item_code,
            item_name=value.item_name,
            jan=value.jan,
            variant=value.variant,
            source_url=value.source_url,
            destination_url=value.destination_url,
            image_url=value.image_url,
            width=value.width,
            height=value.height,
            retrieved_at=value.retrieved_at,
            request_fingerprint=value.request_fingerprint,
            response_sha256=value.response_sha256,
            selected_result_sha256=value.selected_result_sha256,
            affiliate_request_fingerprint=value.affiliate_request_fingerprint,
            affiliate_response_sha256=value.affiliate_response_sha256,
            affiliate_selected_result_sha256=(value.affiliate_selected_result_sha256),
            image_sha256=value.image_sha256,
            no_modification_policy=value.no_modification_policy,
        )

    with pytest.raises(EditorialPilotFailure) as mismatch:
        prepare_editorial_article(
            REPOSITORY_ROOT,
            "st1704-portable-power-station-guide",
            evidence_reader=mismatched,
            source_evidence_reader=_source_reader,
            clock=_fixed_clock,
        )
    assert mismatch.value.code is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_url", "https://example.invalid/item/"),
        (
            "image_url",
            "https://thumbnail.image.rakuten.co.jp/@0_mall/test/item.jpg?_ex=256x256",
        ),
        ("width", 256),
    ],
)
def test_rakuten_evidence_rejects_unbound_hosts_or_non_128_image(
    field: str, value: object
) -> None:
    evidence = _synthetic_evidence("PRD-ANKER-SOLIX-C300")
    with pytest.raises(EditorialPilotFailure) as failure:
        replace(evidence, **{field: value})
    assert failure.value.code is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID


def test_rakuten_evidence_binds_item_url_shop_to_item_code() -> None:
    evidence = _synthetic_evidence("PRD-ANKER-SOLIX-C300")
    wrong_source = evidence.source_url.replace("/test-shop/", "/different-shop/")
    destination = urlsplit(evidence.destination_url)
    query = parse_qs(destination.query)
    wrong_destination = destination._replace(
        query=urlencode(
            {
                "m": "https://m.rakuten.co.jp/different-shop/i/item/",
                "pc": wrong_source,
                "rafcid": query["rafcid"][0],
            }
        )
    ).geturl()
    with pytest.raises(EditorialPilotFailure) as failure:
        replace(
            evidence,
            source_url=wrong_source,
            destination_url=wrong_destination,
        )
    assert failure.value.code is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID


def test_owner_private_rakuten_overlay_is_fixed_schema_and_mode_bound(
    private_root: Path,
) -> None:
    evidence = _synthetic_evidence("PRD-ANKER-SOLIX-C300")
    path = _install_overlay(private_root, evidence)

    loaded = read_rakuten_product_evidence(private_root, product_id=evidence.product_id)
    assert loaded == evidence
    assert path.stat().st_mode & 0o777 == 0o600

    document = json.loads(path.read_text(encoding="utf-8"))
    document["arbitrary_url"] = "https://example.invalid/"
    path.write_bytes(canonical_json_bytes(document) + b"\n")
    path.chmod(0o600)
    with pytest.raises(EditorialPilotFailure) as extra:
        read_rakuten_product_evidence(private_root, product_id=evidence.product_id)
    assert extra.value.code is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID


def test_rakuten_overlay_requires_second_affiliate_capture_and_image_bytes(
    private_root: Path,
) -> None:
    evidence = _synthetic_evidence("PRD-ANKER-SOLIX-C300")
    _install_overlay(private_root, evidence)
    affiliate_path = private_root / rakuten_affiliate_response_relative_path(
        evidence.product_id
    )
    held_path = affiliate_path.with_suffix(".held")
    affiliate_path.rename(held_path)
    with pytest.raises(EditorialPilotFailure) as missing:
        read_rakuten_product_evidence(private_root, product_id=evidence.product_id)
    assert missing.value.code is EditorialPilotFailureCode.RESOURCE_NOT_READY
    held_path.rename(affiliate_path)

    affiliate_path.write_bytes(
        _synthetic_affiliate_response_bytes(evidence).replace(
            evidence.destination_url.encode(), evidence.source_url.encode()
        )
    )
    affiliate_path.chmod(0o600)
    with pytest.raises(EditorialPilotFailure) as wrong_affiliate:
        read_rakuten_product_evidence(private_root, product_id=evidence.product_id)
    assert (
        wrong_affiliate.value.code
        is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID
    )


def test_product_identity_rejects_accessory_title_and_synthetic_or_variant() -> None:
    original = _synthetic_evidence("PRD-ANKER-SOLIX-C300")

    def accessory(root: Path, *, product_id: str) -> RakutenProductEvidence:
        del root
        value = _synthetic_evidence(product_id)
        item_name = "Anker Solix C300 ポータブル電源用収納ケース"
        return replace(
            value,
            item_name=item_name,
            selected_result_sha256=canonical_sha256(
                {**value.identity_material(), "item_name": item_name}
            ),
            affiliate_selected_result_sha256=canonical_sha256(
                {**value.affiliate_identity_material(), "item_name": item_name}
            ),
        )

    with pytest.raises(EditorialPilotFailure) as accessory_failure:
        prepare_editorial_article(
            REPOSITORY_ROOT,
            "st1704-portable-power-station-guide",
            evidence_reader=accessory,
            source_evidence_reader=_source_reader,
            clock=_fixed_clock,
        )
    assert (
        accessory_failure.value.code
        is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID
    )

    def or_variant(root: Path, *, product_id: str) -> RakutenProductEvidence:
        del root
        return replace(
            _synthetic_evidence(product_id),
            variant=(
                "A17225Z1_OR_A1722511"
                if product_id == original.product_id
                else _synthetic_evidence(product_id).variant
            ),
        )

    with pytest.raises(EditorialPilotFailure) as synthetic_or:
        prepare_editorial_article(
            REPOSITORY_ROOT,
            "st1704-portable-power-station-guide",
            evidence_reader=or_variant,
            source_evidence_reader=_source_reader,
            clock=_fixed_clock,
        )
    assert (
        synthetic_or.value.code is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID
    )


@pytest.mark.parametrize(
    ("target_product", "item_name"),
    [
        (
            "PRD-ANKER-SOLIX-C300",
            "Anker Solix C3000 Portable Power Station",
        ),
        (
            "PRD-ANKER-SOLIX-C300",
            "Anker Solix C300 DC Portable Power Station",
        ),
        ("PRD-BLUETTI-AC70", "BLUETTI AC70P Portable Power Station"),
    ],
    ids=[
        "alphanumeric-model-prefix",
        "known-c300-dc-sibling",
        "known-ac70p-sibling",
    ],
)
def test_product_identity_rejects_model_prefix_and_known_sibling(
    target_product: str,
    item_name: str,
) -> None:
    def confused(root: Path, *, product_id: str) -> RakutenProductEvidence:
        del root
        evidence = _synthetic_evidence(product_id)
        if product_id != target_product:
            return evidence
        return replace(
            evidence,
            item_name=item_name,
            selected_result_sha256=canonical_sha256(
                {**evidence.identity_material(), "item_name": item_name}
            ),
            affiliate_selected_result_sha256=canonical_sha256(
                {**evidence.affiliate_identity_material(), "item_name": item_name}
            ),
        )

    with pytest.raises(EditorialPilotFailure) as failure:
        prepare_editorial_article(
            REPOSITORY_ROOT,
            "st1704-portable-power-station-guide",
            evidence_reader=confused,
            source_evidence_reader=_source_reader,
            clock=_fixed_clock,
        )
    assert failure.value.code is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID


def test_base_c1000_rejects_gen2_provider_title() -> None:
    base_product = "PRD-ANKER-SOLIX-C1000"

    def confused(root: Path, *, product_id: str) -> RakutenProductEvidence:
        del root
        evidence = _synthetic_evidence(product_id)
        if product_id != base_product:
            return evidence
        item_name = evidence.item_name + " Gen 2"
        return replace(
            evidence,
            item_name=item_name,
            selected_result_sha256=canonical_sha256(
                {**evidence.identity_material(), "item_name": item_name}
            ),
            affiliate_selected_result_sha256=canonical_sha256(
                {**evidence.affiliate_identity_material(), "item_name": item_name}
            ),
        )

    with pytest.raises(EditorialPilotFailure) as failure:
        prepare_editorial_article(
            REPOSITORY_ROOT,
            "st1704-anker-solix-c300-c800-c1000-differences",
            evidence_reader=confused,
            source_evidence_reader=_source_reader,
            clock=_fixed_clock,
        )
    assert failure.value.code is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID


def test_owner_private_source_capture_binds_raw_body_url_claims_and_modes(
    private_root: Path,
) -> None:
    evidence = _source_reader(REPOSITORY_ROOT, source_ref="SRC-ANKER-SOLIX-C300")
    metadata_path, body_path = _install_source_overlay(private_root, evidence)

    loaded = read_official_source_capture_evidence(
        private_root, source_ref=evidence.source_ref
    )
    assert loaded == evidence
    assert metadata_path.stat().st_mode & 0o777 == 0o600
    assert body_path.stat().st_mode & 0o777 == 0o600

    body_path.write_bytes(b"wrong official body")
    body_path.chmod(0o600)
    with pytest.raises(EditorialPilotFailure) as mismatch:
        read_official_source_capture_evidence(
            private_root, source_ref=evidence.source_ref
        )
    assert mismatch.value.code is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID


def test_source_capture_rejects_same_claim_duplicate_statement_drift_and_fake_formats() -> (
    None
):
    evidence = _source_reader(REPOSITORY_ROOT, source_ref="SRC-ANKER-SOLIX-C300")
    assert len(evidence.locators) > 1
    first = evidence.locators[0]
    with pytest.raises(EditorialPilotFailure) as reused:
        replace(
            evidence,
            locators=(
                (first[0], first[1], (first[2][0], first[2][0])),
                *evidence.locators[1:],
            ),
        )
    assert reused.value.code is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID

    def statement_drift(
        root: Path, *, source_ref: str
    ) -> OfficialSourceCaptureEvidence:
        original = _source_reader(root, source_ref=source_ref)
        locator = original.locators[0]
        return replace(
            original,
            locators=((locator[0], "f" * 64, locator[2]),) + original.locators[1:],
        )

    with pytest.raises(EditorialPilotFailure) as statement_failure:
        prepare_editorial_article(
            REPOSITORY_ROOT,
            "st1704-portable-power-station-guide",
            evidence_reader=_reader,
            source_evidence_reader=statement_drift,
            clock=_fixed_clock,
        )
    assert (
        statement_failure.value.code
        is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID
    )
    for body, content_type in (
        (b"not an html document", "text/html"),
        (b"%PDF-1.7\nmissing terminal marker", "application/pdf"),
    ):
        with pytest.raises(EditorialPilotFailure) as format_failure:
            json_module._validate_source_capture_body(  # type: ignore[attr-defined]
                body, content_type=content_type
            )
        assert (
            format_failure.value.code
            is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID
        )


def test_product_image_parser_rejects_truncated_or_corrupt_128_headers() -> None:
    valid = _synthetic_image_bytes()
    assert json_module._image_dimensions(valid) == (128, 128)  # type: ignore[attr-defined]
    valid_indexed = _synthetic_image_bytes(color_type=3, include_palette=True)
    assert json_module._image_dimensions(valid_indexed) == (  # type: ignore[attr-defined]
        128,
        128,
    )
    valid_gif = _synthetic_gif_bytes(valid_lzw=True)
    assert json_module._image_dimensions(valid_gif) == (128, 128)  # type: ignore[attr-defined]
    valid_jpeg = _synthetic_jpeg_bytes(valid_entropy=True)
    assert json_module._image_dimensions(valid_jpeg) == (  # type: ignore[attr-defined]
        128,
        128,
    )
    truncated = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    corrupt = bytearray(valid)
    idat = valid.index(b"IDAT") + 4
    corrupt[idat] ^= 0x01
    invalid_compressed = _synthetic_image_bytes(compressed_payload=b"not-zlib-data")
    indexed_without_palette = _synthetic_image_bytes(color_type=3)
    palette_after_zero_idat = _synthetic_image_bytes(zero_idat_before_palette=True)
    non_target_png = _synthetic_image_bytes(width=96)
    indexed_outside_palette = _synthetic_image_bytes(
        color_type=3, include_palette=True, indexed_sample=1
    )
    invalid_gif = _synthetic_gif_bytes(valid_lzw=False)
    non_target_gif = _synthetic_gif_bytes(valid_lzw=True, width=96)
    invalid_jpeg = _synthetic_jpeg_bytes(valid_entropy=False)
    non_target_jpeg = _synthetic_jpeg_bytes(valid_entropy=True, width=129, height=128)
    for raw in (
        truncated,
        bytes(corrupt),
        invalid_compressed,
        indexed_without_palette,
        palette_after_zero_idat,
        non_target_png,
        indexed_outside_palette,
        invalid_gif,
        non_target_gif,
        invalid_jpeg,
        non_target_jpeg,
    ):
        with pytest.raises(EditorialPilotFailure) as failure:
            json_module._image_dimensions(raw)  # type: ignore[attr-defined]
        assert (
            failure.value.code is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID
        )


def test_evidence_reader_rejects_unrequested_provider_item_fields() -> None:
    evidence = _synthetic_evidence("PRD-ANKER-SOLIX-C300")
    raw = (
        canonical_json_bytes(
            {
                "Items": [
                    {
                        "itemCode": evidence.item_code,
                        "itemName": evidence.item_name,
                        "itemUrl": evidence.source_url,
                        "mediumImageUrls": [evidence.image_url],
                        "reviewAverage": 4.5,
                    }
                ]
            }
        )
        + b"\n"
    )
    bound = replace(evidence, response_sha256=bytes_sha256(raw))
    with pytest.raises(EditorialPilotFailure) as failure:
        json_module._validate_rakuten_response(  # type: ignore[attr-defined]
            raw,
            evidence=bound,
            affiliate_id_supplied=False,
        )
    assert failure.value.code is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID


def test_evidence_reader_rejects_compact_response_with_extra_rows() -> None:
    evidence = _synthetic_evidence("PRD-ANKER-SOLIX-C300")
    raw = (
        canonical_json_bytes(
            {
                "Items": [
                    {
                        "itemCode": evidence.item_code,
                        "itemName": evidence.item_name,
                        "itemUrl": evidence.source_url,
                        "mediumImageUrls": [evidence.image_url],
                    },
                    {
                        "itemCode": "test-shop:unrelated-item",
                        "itemName": "Unrelated product",
                        "itemUrl": "https://item.rakuten.co.jp/test-shop/unrelated-item/",
                        "mediumImageUrls": [evidence.image_url],
                    },
                ]
            }
        )
        + b"\n"
    )
    bound = replace(evidence, response_sha256=bytes_sha256(raw))
    with pytest.raises(EditorialPilotFailure) as failure:
        json_module._validate_rakuten_response(  # type: ignore[attr-defined]
            raw,
            evidence=bound,
            affiliate_id_supplied=False,
        )
    assert failure.value.code is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID


def test_owner_live_gate_is_bound_to_article_packet_request_and_command(
    private_root: Path,
) -> None:
    candidate = request()
    gate_directory = private_root / OWNER_GATE_DIRECTORY
    gate_directory.mkdir(parents=True, mode=0o700)
    (private_root / ".secrets").chmod(0o700)
    (private_root / ".secrets" / OWNER_DIRECTORY).chmod(0o700)
    gate_directory.chmod(0o700)
    document = {
        "article_id": candidate.article_id,
        "authority": OWNER_GATE_AUTHORITY,
        "command": "create-review-draft",
        "origin": candidate.origin,
        "packet_sha256": candidate.packet_sha256,
        "request_sha256": candidate.request_sha256,
        "schema": OWNER_GATE_SCHEMA,
    }
    path = private_root / owner_gate_relative_path(candidate, "create-review-draft")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        payload = canonical_json_bytes(document) + b"\n"
        assert os.write(descriptor, payload) == len(payload)
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)

    require_owner_live_gate(private_root, candidate, "create-review-draft")
    with pytest.raises(EditorialPilotFailure) as wrong_command:
        require_owner_live_gate(private_root, candidate, "recover-create-review-draft")
    assert wrong_command.value.code is EditorialPilotFailureCode.OWNER_GATE_REQUIRED


class _Credentials:
    def authorization_header(self) -> str:
        return "Basic synthetic"


class _CredentialStore:
    def __init__(self, root: Path) -> None:
        assert root.is_absolute()

    def metadata_status(self) -> str:
        return "METADATA_READY"

    def read(self) -> _Credentials:
        return _Credentials()


class _Response:
    def __init__(
        self,
        body: bytes,
        *,
        status: int,
        total: str | None = None,
        pages: str | None = None,
        content_type: str = "application/json; charset=UTF-8",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.body = body
        self.total = total
        self.pages = pages
        self.content_type = content_type
        self.headers = headers or {}

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return {
            **self.headers,
            "Content-Type": self.content_type,
            "Content-Length": str(len(self.body)),
            "X-WP-Total": self.total,
            "X-WP-TotalPages": self.pages,
        }.get(name, default)

    def read(self, amount: int = -1) -> bytes:
        assert amount > len(self.body)
        return self.body


class _Connection:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.observed: tuple[str, str, bytes, dict[str, str]] | None = None
        self.connected = 0
        self.closed = 0

    def connect(self) -> None:
        self.connected += 1

    def set_read_timeout(self, seconds: int) -> None:
        assert seconds > 0

    def request(
        self, method: str, path: str, body: bytes, headers: dict[str, str]
    ) -> None:
        self.observed = (method, path, body, headers)

    def getresponse(self) -> _Response:
        return self.response

    def close(self) -> None:
        self.closed += 1


class _Factory:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: object,
    ) -> _Connection:
        assert host == SELF_HOSTED_WORDPRESS_HOST
        assert port == SELF_HOSTED_WORDPRESS_PORT == 443
        assert connect_timeout_seconds > 0
        assert tls_context is not None
        return self.connection


class _QueueFactory:
    def __init__(self, *connections: _Connection) -> None:
        self.connections = list(connections)
        self.opened: list[_Connection] = []

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: object,
    ) -> _Connection:
        assert host == SELF_HOSTED_WORDPRESS_HOST
        assert port == SELF_HOSTED_WORDPRESS_PORT == 443
        assert connect_timeout_seconds > 0
        assert tls_context is not None
        connection = self.connections.pop(0)
        self.opened.append(connection)
        return connection


def _wp_post(
    status: str = "draft",
    candidate: object | None = None,
    *,
    post_id: int = 1704,
) -> dict[str, object]:
    candidate = request() if candidate is None else candidate
    post: dict[str, object] = {
        "content": {"raw": candidate.content},
        "excerpt": {"raw": candidate.excerpt},
        "id": post_id,
        "meta": {PILOT_SNAPSHOT_META_KEY: candidate.snapshot.json_string()},
        "slug": candidate.slug if status == "draft" else candidate.public_slug,
        "status": status,
        "title": {"raw": candidate.title},
        "type": "post",
    }
    if status == "publish":
        post.update(
            {
                "categories": [42],
                "date_gmt": "2026-08-23T01:00:00",
                "modified_gmt": "2026-08-23T02:00:00",
            }
        )
    return post


def _theme_article_values(identity: object) -> tuple[str, str, str, str]:
    row = cast(SimpleNamespace, identity)
    values = (row.article_id, row.slug, row.section, row.title)
    assert all(type(value) is str for value in values)
    return cast(tuple[str, str, str, str], values)


def _theme_article_rows() -> tuple[tuple[str, str, str, str], ...]:
    homepage = https_module._load_theme_homepage_clusters(  # type: ignore[attr-defined]
        REPOSITORY_ROOT
    )
    clusters = cast(dict[str, dict[str, object]], homepage["clusters"])
    return tuple(
        _theme_article_values(identity)
        for cluster_id in cast(tuple[str, ...], homepage["display_order"])
        for identity in cast(tuple[object, ...], clusters[cluster_id]["posts"])
    )


def _v3_fallback_post(
    identity: tuple[str, str, str, str],
    *,
    post_id: int,
) -> dict[str, object]:
    article_id, slug, _section, title = identity
    return {
        "categories": [42],
        "content": {
            "raw": (
                '<div class="raos-editorial-v2">\n'
                f'<span data-raos-article-id="{article_id}"></span>\n'
                "</div>\n"
            )
        },
        "date_gmt": "2026-08-23T01:00:00",
        "excerpt": {"raw": title},
        "id": post_id,
        "meta": {PILOT_SNAPSHOT_META_KEY: ""},
        "modified_gmt": "2026-08-23T02:00:00",
        "slug": slug,
        "status": "publish",
        "title": {"raw": title},
        "type": "post",
    }


def _v3_public_posts(
    candidate: object,
    *,
    public_post_id: int,
) -> list[dict[str, object]]:
    posts: list[dict[str, object]] = []
    for position, identity in enumerate(_theme_article_rows(), start=1):
        if identity[0] == candidate.article_id:
            posts.append(_wp_post("publish", candidate, post_id=public_post_id))
        else:
            posts.append(_v3_fallback_post(identity, post_id=20_000 + position))
    assert len(posts) == 10
    return posts


def _v3_related_posts(
    candidate: object,
    *,
    public_post_id: int,
) -> list[dict[str, object]]:
    navigation = https_module._load_theme_related_navigation(  # type: ignore[attr-defined]
        REPOSITORY_ROOT
    )
    targets = cast(tuple[object, ...], navigation[candidate.article_id]["targets"])
    target_slugs = {_theme_article_values(target)[1] for target in targets}
    return [
        post
        for post in _v3_public_posts(candidate, public_post_id=public_post_id)
        if cast(str, post["slug"]) in target_slugs
    ]


def _prepared_request(
    article_id: str = "st1704-portable-power-station-guide",
) -> object:
    return prepare_editorial_article(
        REPOSITORY_ROOT,
        article_id,
        evidence_reader=_reader,
        source_evidence_reader=_source_reader,
        clock=_fixed_clock,
    ).request


def _public_article_html(candidate: object) -> bytes:
    payload = candidate.snapshot.payload
    published = "2026-08-23T01:00:00Z"
    modified = "2026-08-23T02:00:00Z"
    json_ld = canonical_json_bytes(
        https_module._expected_json_ld(  # type: ignore[attr-defined]
            candidate, published=published, modified=modified
        )
    ).decode("utf-8")
    metadata = {
        "description": payload.description,
        "robots": (
            "index, follow, max-image-preview:large, max-snippet:-1, "
            "max-video-preview:-1"
        ),
        "twitter:card": "summary_large_image",
        "twitter:description": payload.og_description,
        "twitter:image": https_module._SOCIAL_IMAGE_URL,  # type: ignore[attr-defined]
        "twitter:title": payload.og_title,
    }
    properties = {
        "og:description": payload.og_description,
        "og:image": https_module._SOCIAL_IMAGE_URL,  # type: ignore[attr-defined]
        "og:image:height": "900",
        "og:image:type": "image/webp",
        "og:image:width": "1600",
        "og:title": payload.og_title,
        "og:type": "article",
        "og:url": payload.canonical_url,
    }
    meta_html = "".join(
        f'<meta name="{name}" content="{value}">' for name, value in metadata.items()
    ) + "".join(
        f'<meta property="{name}" content="{value}">'
        for name, value in properties.items()
    )
    navigation = https_module._load_theme_related_navigation(  # type: ignore[attr-defined]
        REPOSITORY_ROOT
    )
    home_url, home_label = cast(
        tuple[str, str], navigation[candidate.article_id]["home"]
    )
    targets = cast(
        tuple[object, ...], navigation[candidate.article_id]["targets"]
    )
    target_links = "".join(
        f'<li><a href="https://kurashinoshirube.com/{slug}/">{title}</a></li>'
        for _article_id, slug, _section, title in (
            _theme_article_values(target) for target in targets
        )
    )
    related = (
        '<aside class="raos-related-guides" aria-labelledby="raos-related-title">'
        '<h2 id="raos-related-title">関連記事</h2><ul>'
        f'{target_links}<li><a href="{home_url}">{home_label}</a></li></ul></aside>'
    )
    return (
        "<!doctype html><html><head>"
        f"<title>{payload.seo_title}</title>{meta_html}"
        f'<link rel="canonical" href="{payload.canonical_url}">'
        '<script id="raos-structured-data" type="application/ld+json">'
        f"{json_ld}</script></head><body><article>"
        f"<h1>{payload.title}</h1>"
        '<div class="wp-block-post-content">'
        f"{candidate.content}</div>{related}</article></body></html>"
    ).encode("utf-8")


def _public_homepage_html(candidate: object) -> bytes:
    homepage = https_module._load_theme_homepage_clusters(  # type: ignore[attr-defined]
        REPOSITORY_ROOT
    )
    clusters = cast(dict[str, dict[str, object]], homepage["clusters"])
    sections: list[str] = []
    for cluster_id in cast(tuple[str, ...], homepage["display_order"]):
        posts = cast(tuple[object, ...], clusters[cluster_id]["posts"])
        links = "".join(
            f'<li><a href="https://kurashinoshirube.com/{slug}/">{title}</a></li>'
            for _article_id, slug, _section, title in (
                _theme_article_values(post) for post in posts
            )
        )
        sections.append(
            f'<section id="{cluster_id}" class="raos-cluster">'
            f"<h3>{clusters[cluster_id]['heading']}</h3><ul>"
            f"{links}</ul></section>"
        )
    return (
        "<!doctype html><html><head><title>暮らしのしるべ</title></head><body>"
        '<section class="raos-cluster-nav alignwide">'
        + "".join(sections)
        + "</section></body></html>"
    ).encode()


def _sitemap_index() -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<sitemap><loc>https://kurashinoshirube.com/post-sitemap.xml</loc></sitemap>"
        "<sitemap><loc>https://kurashinoshirube.com/page-sitemap.xml</loc></sitemap>"
        "</sitemapindex>"
    ).encode()


def _url_sitemap(*urls: str) -> bytes:
    records = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{records}</urlset>"
    ).encode()


def _public_connections(
    candidate: object, *, public_post_id: int = 1704
) -> list[_Connection]:
    return [
        _Connection(
            _Response(
                canonical_json_bytes(
                    [_wp_post("publish", candidate, post_id=public_post_id)]
                ),
                status=200,
                total="1",
                pages="1",
            )
        ),
        _Connection(
            _Response(
                canonical_json_bytes(
                    [{"id": 42, "name": "暮らしの道具", "slug": "kurashi-tools"}]
                ),
                status=200,
                total="1",
                pages="1",
            )
        ),
        _Connection(
            _Response(
                canonical_json_bytes(
                    _v3_related_posts(
                        candidate,
                        public_post_id=public_post_id,
                    )
                ),
                status=200,
                total="2",
                pages="1",
            )
        ),
        _Connection(
            _Response(
                canonical_json_bytes(
                    _v3_public_posts(
                        candidate,
                        public_post_id=public_post_id,
                    )
                ),
                status=200,
                total="10",
                pages="1",
            )
        ),
        _Connection(
            _Response(
                _public_article_html(candidate),
                status=200,
                content_type="text/html; charset=UTF-8",
            )
        ),
        _Connection(
            _Response(
                _public_homepage_html(candidate),
                status=200,
                content_type="text/html; charset=UTF-8",
            )
        ),
        _Connection(
            _Response(
                b"User-agent: *\nDisallow:\nSitemap: https://kurashinoshirube.com/sitemap_index.xml\n",
                status=200,
                content_type="text/plain; charset=UTF-8",
            )
        ),
        _Connection(
            _Response(_sitemap_index(), status=200, content_type="application/xml")
        ),
        _Connection(
            _Response(
                _url_sitemap(candidate.snapshot.payload.canonical_url),
                status=200,
                content_type="application/xml",
            )
        ),
        _Connection(
            _Response(
                _url_sitemap("https://kurashinoshirube.com/"),
                status=200,
                content_type="application/xml",
            )
        ),
        _Connection(
            _Response(
                b"",
                status=301,
                content_type="text/html; charset=UTF-8",
                headers={
                    "Location": "https://kurashinoshirube.com/sitemap_index.xml",
                    "X-Redirect-By": "Yoast SEO",
                },
            )
        ),
        _Connection(
            _Response(
                (
                    canonical_json_bytes(
                        [
                            _wp_post(
                                "draft",
                                candidate,
                                post_id=(
                                    PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID
                                ),
                            )
                        ]
                    )
                    if candidate.article_id == "st1703-first-suitcase-comparison"
                    else b"[]"
                ),
                status=200,
                total=(
                    "1"
                    if candidate.article_id == "st1703-first-suitcase-comparison"
                    else "0"
                ),
                pages=(
                    "1"
                    if candidate.article_id == "st1703-first-suitcase-comparison"
                    else "0"
                ),
            )
        ),
        _Connection(_Response(b"[]", status=200, total="0", pages="0")),
        _Connection(
            _Response(
                b"<html><body>review not found</body></html>",
                status=404,
                content_type="text/html; charset=UTF-8",
            )
        ),
    ]


def _review_surface_evidence_sha256(kind: str, path: str, response: _Response) -> str:
    return canonical_sha256(
        {
            "body_sha256": bytes_sha256(response.body),
            "content_type": response.content_type,
            "http_status": response.status,
            "kind": kind,
            "location_header": response.getheader("Location"),
            "method": "GET",
            "path": path,
            "schema": "RAOS_ST1704_REVIEW_SURFACE_EVIDENCE_V1",
            "x_wp_total": response.getheader("X-WP-Total"),
            "x_wp_total_pages": response.getheader("X-WP-TotalPages"),
        }
    )


def _synthetic_carry_on_reconciliation_binding(
    candidate: ReviewDraftRequest, monkeypatch: pytest.MonkeyPatch
) -> CarryOnSingleUrlReconciliationBinding:
    artifact_sha256 = "a" * 64
    monkeypatch.setattr(
        domain_module,
        "PILOT_CARRY_ON_RECONCILIATION_PACKET_SHA256",
        candidate.packet_sha256,
    )
    monkeypatch.setattr(
        domain_module,
        "PILOT_CARRY_ON_RECONCILIATION_REQUEST_SHA256",
        candidate.request_sha256,
    )
    monkeypatch.setattr(
        domain_module,
        "PILOT_CARRY_ON_RECONCILIATION_PAYLOAD_SHA256",
        candidate.snapshot.payload_sha256,
    )
    monkeypatch.setattr(
        domain_module,
        "PILOT_CARRY_ON_RECONCILIATION_ARTIFACT_SHA256",
        artifact_sha256,
    )
    return CarryOnSingleUrlReconciliationBinding(
        request=candidate,
        request_artifact_sha256=artifact_sha256,
        journal_state="RECOVERY_ATTEMPTED",
        target_public_post_id=PILOT_CARRY_ON_RECONCILIATION_TARGET_PUBLIC_POST_ID,
        expected_review_draft_post_id=(
            PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID
        ),
    )


def _install_fake_live_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    related_navigation = https_module._load_theme_related_navigation(  # type: ignore[attr-defined]
        REPOSITORY_ROOT
    )
    monkeypatch.setattr(
        https_module,
        "_load_theme_related_navigation",
        lambda _root: related_navigation,
    )
    homepage_clusters = https_module._load_theme_homepage_clusters(  # type: ignore[attr-defined]
        REPOSITORY_ROOT
    )
    monkeypatch.setattr(
        https_module,
        "_load_theme_homepage_clusters",
        lambda _root: homepage_clusters,
    )
    monkeypatch.setattr(https_module, "require_owner_live_gate", lambda *args: None)
    monkeypatch.setattr(
        https_module, "OwnerPrivateSelfHostedWordPressCredentialStore", _CredentialStore
    )
    monkeypatch.setattr(
        https_module,
        "require_clean_self_hosted_wordpress_environment",
        lambda: None,
    )


def test_public_verifier_projects_ten_articles_and_two_relations_from_v3() -> None:
    related = https_module._load_theme_related_navigation(  # type: ignore[attr-defined]
        REPOSITORY_ROOT
    )
    assert set(related) == {row[0] for row in _theme_article_rows()}
    assert all(
        len(cast(tuple[object, ...], relation["targets"])) >= 2
        for relation in related.values()
    )
    assert related["st1704-portable-power-station-guide"]["home"] == (
        "https://kurashinoshirube.com/#cluster-ready",
        "暮らしの道具「備え」の一覧へ",
    )
    power_targets = cast(
        tuple[object, ...],
        related["st1704-portable-power-station-guide"]["targets"],
    )
    assert _theme_article_values(power_targets[0]) == (
        "st1704-anker-solix-c300-c800-c1000-differences",
        "anker-solix-c300-c800-c1000-differences",
        "備え",
        "Anker Solix C300・C800 Plus・C1000・C1000 Gen 2の違い",
    )
    homepage = https_module._load_theme_homepage_clusters(  # type: ignore[attr-defined]
        REPOSITORY_ROOT
    )
    assert homepage["display_order"] == (
        "cluster-mobility",
        "cluster-home",
        "cluster-ready",
    )
    assert (
        sum(
            len(cast(tuple[tuple[str, str], ...], cluster["posts"]))
            for cluster in cast(
                dict[str, dict[str, object]], homepage["clusters"]
            ).values()
        )
        == 10
    )
    clusters = cast(dict[str, dict[str, object]], homepage["clusters"])
    assert tuple(
        len(cast(tuple[object, ...], clusters[key]["posts"]))
        for key in homepage["display_order"]
    ) == (4, 4, 2)


def test_owner_https_create_posts_only_the_exact_draft_payload(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_live_boundary(monkeypatch)
    candidate = request()
    body = canonical_json_bytes(_wp_post())
    target_connection = _Connection(
        _Response(
            b"[]",
            status=200,
            total="0",
            pages="0",
            headers={"Link": _WORDPRESS_API_DISCOVERY_LINK},
        )
    )
    inventory_connection = _Connection(
        _Response(
            b"[]",
            status=200,
            total="0",
            pages="0",
            headers={"Link": _WORDPRESS_API_DISCOVERY_LINK},
        )
    )
    connection = _Connection(_Response(body, status=201))
    factory = _QueueFactory(target_connection, inventory_connection, connection)
    adapter = OfficialSelfHostedEditorialPilotWordPressAdapter(
        private_root, connection_factory=factory
    )

    assert adapter.resolve_public_target(candidate, "create-review-draft") is None
    receipt = adapter.create(candidate)

    assert receipt.draft_id == 1704
    assert receipt.live_authority
    assert not receipt.publication_authority
    assert connection.observed is not None
    method, path, sent, headers = connection.observed
    assert method == "POST"
    assert path == PILOT_CREATE_PATH
    assert json.loads(sent) == candidate.wordpress_body()
    assert set(json.loads(sent)) == {
        "content",
        "excerpt",
        "meta",
        "slug",
        "status",
        "title",
    }
    assert json.loads(sent)["status"] == "draft"
    assert headers["Host"] == "kurashinoshirube.com"
    assert connection.connected == connection.closed == 1


def test_public_target_rejects_pagination_or_unbound_link_header(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_live_boundary(monkeypatch)
    target_connection = _Connection(
        _Response(
            b"[]",
            status=200,
            total="0",
            pages="0",
            headers={
                "Link": (
                    "<https://kurashinoshirube.com/wp-json/wp/v2/posts?page=2>; "
                    'rel="next"'
                )
            },
        )
    )
    adapter = OfficialSelfHostedEditorialPilotWordPressAdapter(
        private_root,
        connection_factory=_QueueFactory(target_connection),
    )

    with pytest.raises(EditorialPilotFailure) as failure:
        adapter.resolve_public_target(request(), "create-review-draft")

    assert failure.value.code is EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH
    assert target_connection.observed is not None
    assert target_connection.observed[0] == "GET"


@pytest.mark.parametrize("orphaned_meta", [False, True])
def test_create_preexisting_review_slug_family_leaves_no_journal_and_never_posts(
    private_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    orphaned_meta: bool,
) -> None:
    _install_fake_live_boundary(monkeypatch)
    candidate = request()
    existing = _wp_post(candidate=candidate)
    if orphaned_meta:
        existing["slug"] = candidate.slug + "-2"
        existing["meta"] = {}
    target_connection = _Connection(_Response(b"[]", status=200, total="0", pages="0"))
    inventory_connection = _Connection(
        _Response(
            canonical_json_bytes([existing]),
            status=200,
            total="1",
            pages="1",
        )
    )
    factory = _QueueFactory(target_connection, inventory_connection)
    adapter = OfficialSelfHostedEditorialPilotWordPressAdapter(
        private_root, connection_factory=factory
    )
    journal = OwnerPrivateLiveReviewDraftJournal(private_root, adapter)

    with pytest.raises(EditorialPilotFailure) as failure:
        journal.create(candidate)

    assert failure.value.code is EditorialPilotFailureCode.JOURNAL_AMBIGUOUS
    journal_path = (
        private_root
        / ".secrets"
        / OWNER_DIRECTORY
        / JOURNAL_DIRECTORY
        / f"{candidate.article_id}.{candidate.packet_sha256}.live.v1.json"
    )
    assert not journal_path.exists()
    assert len(factory.opened) == 2
    assert all(
        connection.observed is not None and connection.observed[0] == "GET"
        for connection in factory.opened
    )


@pytest.mark.parametrize(
    ("posts", "total"),
    [([], "0"), ([_wp_post(), _wp_post()], "2")],
)
def test_owner_https_recovery_rejects_zero_or_multiple_without_post(
    private_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    posts: list[object],
    total: str,
) -> None:
    _install_fake_live_boundary(monkeypatch)
    target_connection = _Connection(_Response(b"[]", status=200, total="0", pages="0"))
    connection = _Connection(
        _Response(
            canonical_json_bytes(posts),
            status=200,
            total=total,
            pages="0" if total == "0" else "1",
        )
    )
    factory = _QueueFactory(target_connection, connection)
    adapter = OfficialSelfHostedEditorialPilotWordPressAdapter(
        private_root, connection_factory=factory
    )

    assert (
        adapter.resolve_public_target(request(), "recover-create-review-draft") is None
    )
    with pytest.raises(EditorialPilotFailure) as failure:
        adapter.recover(request())
    assert failure.value.code is EditorialPilotFailureCode.OUTCOME_AMBIGUOUS
    assert connection.observed is not None
    method, path, sent, _headers = connection.observed
    assert method == "GET"
    assert path.startswith("/wp-json/wp/v2/posts?context=edit&status=draft")
    assert "status=draft" in path
    assert "slug=" not in path
    assert "_raos_publication_snapshot_v1" in path
    assert sent == b""


@pytest.mark.parametrize(
    "mutation",
    ["malformed-description", "wrong-excerpt", "wrong-title"],
)
def test_related_targets_require_complete_bound_snapshot_and_theme_title(
    mutation: str,
) -> None:
    request_candidate = _prepared_request()
    target_candidate = _prepared_request(
        "st1704-anker-solix-c300-c800-c1000-differences"
    )
    post = _wp_post("publish", target_candidate)
    if mutation == "wrong-excerpt":
        cast(dict[str, object], post["excerpt"])["raw"] = "異なる要約"
    elif mutation == "wrong-title":
        cast(dict[str, object], post["title"])["raw"] = "異なる記事タイトル"
    elif mutation == "malformed-description":
        wrapper = json.loads(
            cast(dict[str, object], post["meta"])[PILOT_SNAPSHOT_META_KEY]
        )
        wrapper["payload"]["description"] = 42
        wrapper["payload_sha256"] = canonical_sha256(wrapper["payload"])
        cast(dict[str, object], post["meta"])[PILOT_SNAPSHOT_META_KEY] = (
            canonical_json_bytes(wrapper).decode()
        )
    else:
        raise AssertionError("unknown mutation")
    related = https_module._load_theme_related_navigation(  # type: ignore[attr-defined]
        REPOSITORY_ROOT
    )
    with pytest.raises(EditorialPilotFailure) as failure:
        https_module._related_targets_bound(  # type: ignore[attr-defined]
            canonical_json_bytes([post]), request_candidate, related
        )
    assert failure.value.code is EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH


def test_verify_public_checks_exact_anonymous_surface_and_bound_post_id(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_live_boundary(monkeypatch)
    candidate = _prepared_request()
    connections = _public_connections(candidate)
    factory = _QueueFactory(*connections)
    adapter = OfficialSelfHostedEditorialPilotWordPressAdapter(
        private_root, connection_factory=factory
    )

    verification = adapter.verify_public(candidate, 1704)

    assert verification.public_surface_verified
    assert verification.expected_public_post_id == verification.post_id == 1704
    assert verification.category_sha256
    assert verification.related_target_sha256
    assert verification.homepage_html_sha256
    assert verification.homepage_targets_sha256
    assert verification.core_sitemap_sha256
    assert verification.review_draft_post_id is None
    assert verification.review_draft_rest_evidence_sha256
    assert verification.review_public_rest_evidence_sha256
    assert verification.review_url_html_evidence_sha256
    assert verification.verified_checks == PILOT_PUBLIC_VERIFICATION_CHECKS
    assert verification.public_surface_sha256 == canonical_sha256(
        {
            "article_html_sha256": verification.article_html_sha256,
            "category_sha256": verification.category_sha256,
            "core_sitemap_sha256": verification.core_sitemap_sha256,
            "homepage_html_sha256": verification.homepage_html_sha256,
            "homepage_targets_sha256": verification.homepage_targets_sha256,
            "page_sitemap_sha256": verification.page_sitemap_sha256,
            "post_sitemap_sha256": verification.post_sitemap_sha256,
            "related_target_sha256": verification.related_target_sha256,
            "review_draft_rest_evidence_sha256": (
                verification.review_draft_rest_evidence_sha256
            ),
            "review_public_rest_evidence_sha256": (
                verification.review_public_rest_evidence_sha256
            ),
            "review_url_html_evidence_sha256": (
                verification.review_url_html_evidence_sha256
            ),
            "robots_sha256": verification.robots_sha256,
            "sitemap_index_sha256": verification.sitemap_index_sha256,
        }
    )
    assert not factory.connections
    observed = [connection.observed for connection in connections]
    assert all(value is not None for value in observed)
    paths = [
        cast(tuple[str, str, bytes, dict[str, str]], value)[1] for value in observed
    ]
    assert paths[0].startswith("/wp-json/wp/v2/posts?context=edit&slug=portable")
    assert paths[1].startswith("/wp-json/wp/v2/categories?search=")
    assert "slug=anker-solix-c300-c800-c1000-differences" in paths[2]
    assert paths[3].startswith("/wp-json/wp/v2/posts?context=edit&status=publish&slug=")
    review_draft_path = (
        f"/wp-json/wp/v2/posts?context=edit&slug={candidate.slug}&status=draft"
        f"&_fields={https_module._RECOVERY_FIELDS}&page=1&per_page=100"  # type: ignore[attr-defined]
    )
    review_public_path = (
        f"/wp-json/wp/v2/posts?slug={candidate.slug}&status=publish"
        "&_fields=id%2Ctype%2Cslug%2Cstatus&page=1&per_page=100"
    )
    review_url_path = f"/{candidate.slug}/"
    assert paths[4:] == [
        "/portable-power-station-guide/",
        "/",
        "/robots.txt",
        "/sitemap_index.xml",
        "/post-sitemap.xml",
        "/page-sitemap.xml",
        "/wp-sitemap.xml",
        review_draft_path,
        review_public_path,
        review_url_path,
    ]
    assert verification.review_draft_rest_evidence_sha256 == (
        _review_surface_evidence_sha256(
            "review-draft-rest", review_draft_path, connections[11].response
        )
    )
    assert verification.review_public_rest_evidence_sha256 == (
        _review_surface_evidence_sha256(
            "review-public-rest", review_public_path, connections[12].response
        )
    )
    assert verification.review_url_html_evidence_sha256 == (
        _review_surface_evidence_sha256(
            "review-url-html", review_url_path, connections[13].response
        )
    )
    headers = [
        cast(tuple[str, str, bytes, dict[str, str]], value)[3] for value in observed
    ]
    assert "Authorization" in headers[0]
    assert "Authorization" in headers[2]
    assert "Authorization" in headers[3]
    assert "Authorization" in headers[11]
    assert all(
        "Authorization" not in value
        for index, value in enumerate(headers)
        if index not in {0, 2, 3, 11}
    )


def test_verify_public_binds_exact_yoast_core_sitemap_redirect(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_live_boundary(monkeypatch)
    candidate = _prepared_request()
    connections = _public_connections(candidate)
    adapter = OfficialSelfHostedEditorialPilotWordPressAdapter(
        private_root, connection_factory=_QueueFactory(*connections)
    )

    verification = adapter.verify_public(candidate, 1704)

    assert verification.public_surface_verified
    assert verification.core_sitemap_sha256 == bytes_sha256(b"")


def test_verify_public_binds_the_retained_at003_review_draft(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_live_boundary(monkeypatch)
    candidate = _prepared_request("st1703-first-suitcase-comparison")
    connections = _public_connections(candidate)
    adapter = OfficialSelfHostedEditorialPilotWordPressAdapter(
        private_root, connection_factory=_QueueFactory(*connections)
    )

    verification = adapter.verify_public(candidate, 1704)

    assert (
        verification.review_draft_post_id
        == PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID
    )
    with pytest.raises(EditorialPilotFailure) as cloned_id:
        replace(verification, review_draft_post_id=27)
    assert cloned_id.value.code is EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH
    draft_observation = cast(
        tuple[str, str, bytes, dict[str, str]], connections[-3].observed
    )
    assert draft_observation[1].startswith(
        f"/wp-json/wp/v2/posts?context=edit&slug={candidate.slug}&status=draft"
    )
    assert "Authorization" in draft_observation[3]
    assert verification.review_draft_rest_evidence_sha256 == (
        _review_surface_evidence_sha256(
            "review-draft-rest",
            draft_observation[1],
            connections[-3].response,
        )
    )


def test_carry_on_reconciliation_uses_its_distinct_owner_gate_and_fixed_ids(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_live_boundary(monkeypatch)
    candidate = cast(
        ReviewDraftRequest,
        _prepared_request(PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID),
    )
    binding = _synthetic_carry_on_reconciliation_binding(candidate, monkeypatch)
    connections = _public_connections(
        candidate,
        public_post_id=PILOT_CARRY_ON_RECONCILIATION_TARGET_PUBLIC_POST_ID,
    )
    observed_commands: list[str] = []

    def capture_gate(_root: Path, _request: ReviewDraftRequest, command: str) -> None:
        observed_commands.append(command)

    monkeypatch.setattr(https_module, "require_owner_live_gate", capture_gate)
    adapter = OfficialSelfHostedEditorialPilotWordPressAdapter(
        private_root, connection_factory=_QueueFactory(*connections)
    )

    evidence = adapter.verify_carry_on_single_url(binding)

    assert observed_commands == ["verify-carry-on-single-url"]
    assert type(evidence) is CarryOnSingleUrlReconciliationEvidence
    assert (
        evidence.post_id
        == evidence.target_public_post_id
        == PILOT_CARRY_ON_RECONCILIATION_TARGET_PUBLIC_POST_ID
    )
    assert (
        evidence.review_draft_post_id
        == PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID
    )
    assert evidence.formal_gate_eligible is False
    assert evidence.public_surface_verified is False
    assert evidence.strict_public_checks_passed is True
    assert evidence.reconciliation_status == "PENDING_HUMAN_EXCEPTION"
    assert evidence.status == "READ_ONLY_RECONCILIATION_EVIDENCE"
    assert evidence.public_post_status == "publish"
    assert evidence.production_evidence is False
    assert evidence.publication_authority is False
    with pytest.raises(EditorialPilotFailure) as promoted:
        replace(evidence, public_surface_verified=True)
    assert promoted.value.code is EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing", EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH),
        ("wrong-retained-id", EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH),
        ("wrong-title", EditorialPilotFailureCode.OUTCOME_AMBIGUOUS),
    ],
)
def test_verify_public_rejects_missing_or_mismatched_at003_review_draft(
    private_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_code: EditorialPilotFailureCode,
) -> None:
    _install_fake_live_boundary(monkeypatch)
    candidate = _prepared_request("st1703-first-suitcase-comparison")
    connections = _public_connections(candidate)
    response = connections[-3].response
    if mutation == "missing":
        response.body = b"[]"
        response.total = "0"
        response.pages = "0"
    elif mutation == "wrong-title":
        post = _wp_post(
            "draft",
            candidate,
            post_id=PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID,
        )
        cast(dict[str, object], post["title"])["raw"] = "異なるレビュー題名"
        response.body = canonical_json_bytes([post])
    elif mutation == "wrong-retained-id":
        response.body = canonical_json_bytes(
            [
                _wp_post(
                    "draft",
                    candidate,
                    post_id=(PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID + 1),
                )
            ]
        )
    else:
        raise AssertionError("unknown mutation")
    adapter = OfficialSelfHostedEditorialPilotWordPressAdapter(
        private_root, connection_factory=_QueueFactory(*connections)
    )

    with pytest.raises(EditorialPilotFailure) as failure:
        adapter.verify_public(candidate, 1704)

    assert failure.value.code is expected_code


@pytest.mark.parametrize(
    ("mutation", "connection_index"),
    [
        ("uppercase-description", 4),
        ("extra-json-ld", 4),
        ("extra-json-ld-head-parameter", 4),
        ("extra-json-ld-body-parameter", 4),
        ("extra-affiliate-outside", 4),
        ("forbidden-microdata", 4),
        ("forbidden-rdfa", 4),
        ("body-text-change", 4),
        ("bot-noindex", 4),
        ("missing-related", 4),
        ("homepage-unbound-link", 5),
        ("homepage-review-link", 5),
        ("homepage-review-percent-encoded", 5),
        ("homepage-review-percent-encoded-authority", 5),
        ("homepage-review-malformed-percent", 5),
        ("target-robots-disallow", 6),
        ("malformed-sitemap-port", 7),
        ("duplicate-clean-canonical", 8),
        ("post-sitemap-review-url", 8),
        ("post-sitemap-review-url-double-encoded", 8),
        ("page-sitemap-clean-canonical", 9),
        ("page-sitemap-review-url", 9),
        ("page-sitemap-review-url-percent-encoded", 9),
        ("wrong-category", 1),
        ("core-sitemap-enabled", 10),
        ("core-sitemap-legacy-404", 10),
        ("core-sitemap-temporary-redirect", 10),
        ("core-sitemap-missing-redirect-target", 10),
        ("core-sitemap-wrong-redirect-target", 10),
        ("core-sitemap-query-redirect-target", 10),
        ("core-sitemap-wrong-redirect-owner", 10),
        ("core-sitemap-pagination-header", 10),
        ("core-sitemap-nonempty-body", 10),
        ("promoted-review-draft-still-present", 11),
        ("review-public-rest-nonempty", 12),
        ("review-url-redirect", 13),
        ("review-url-public", 13),
        ("review-url-body-leak", 13),
        ("review-url-partial-content-leak", 13),
        ("review-url-entity-title-leak", 13),
        ("review-url-snapshot-payload-sha-leak", 13),
        ("review-url-snapshot-interior-leak", 13),
        ("review-url-shortened-cta-leak", 13),
    ],
)
def test_verify_public_rejects_duplicate_or_unindexable_public_surfaces(
    private_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    connection_index: int,
) -> None:
    _install_fake_live_boundary(monkeypatch)
    candidate = _prepared_request()
    connections = _public_connections(candidate)
    response = connections[connection_index].response
    if mutation == "uppercase-description":
        response.body = response.body.replace(
            b"</head>", b'<meta name="DESCRIPTION" content="duplicate"></head>'
        )
    elif mutation == "extra-json-ld":
        response.body = response.body.replace(
            b"</body>",
            b'<script type=" application/ld+json ">{}</script></body>',
        )
    elif mutation == "extra-json-ld-head-parameter":
        response.body = response.body.replace(
            b"</head>",
            b'<script type="application/ld+json; charset=utf-8">{}</script></head>',
        )
    elif mutation == "extra-json-ld-body-parameter":
        response.body = response.body.replace(
            b"</body>",
            b'<script type="application/ld+json; charset=utf-8">{}</script></body>',
        )
    elif mutation == "extra-affiliate-outside":
        response.body = response.body.replace(
            b"</body>",
            '<a href="https://hb.afl.rakuten.co.jp/hgc/extra/">広告</a></body>'.encode(),
        )
    elif mutation == "forbidden-microdata":
        response.body = response.body.replace(
            b"<article>",
            b'<article itemscope itemtype="https://schema.org/Product">',
        )
    elif mutation == "forbidden-rdfa":
        response.body = response.body.replace(
            b"<article>",
            b'<article vocab="https://schema.org/" typeof="Product">',
        )
    elif mutation == "body-text-change":
        assert "比較のしかた".encode() in response.body
        response.body = response.body.replace(
            "比較のしかた".encode(), "比較手順".encode(), 1
        )
    elif mutation == "bot-noindex":
        response.body = response.body.replace(
            b"</head>", b'<meta name="GoogleBot" content="noindex"></head>'
        )
    elif mutation == "missing-related":
        start = response.body.index(b'<aside class="raos-related-guides"')
        end = response.body.index(b"</aside>", start) + len(b"</aside>")
        response.body = response.body[:start] + response.body[end:]
    elif mutation == "homepage-unbound-link":
        response.body = response.body.replace(
            b"</ul></section></section>",
            (
                b'<li><a href="https://kurashinoshirube.com/'
                b'anker-solix-c300-c800-c1000-differences/">'
                + "Anker Solix 4モデルの違い".encode()
                + b"</a></li></ul></section></section>"
            ),
            1,
        )
    elif mutation == "homepage-review-link":
        response.body = response.body.replace(
            b"</body>",
            (f'<a href="/?next={candidate.slug}">Review</a></body>'.encode()),
        )
    elif mutation == "homepage-review-percent-encoded":
        response.body = response.body.replace(
            b"</body>",
            (
                f'<a href="/%72aos%2Dreview-{candidate.request_sha256}/">'
                "Review</a></body>"
            ).encode(),
        )
    elif mutation == "homepage-review-percent-encoded-authority":
        response.body = response.body.replace(
            b"</body>",
            (
                f'<a href="https://%72aos%2Dreview-{candidate.request_sha256}.example/">'
                "Review</a></body>"
            ).encode(),
        )
    elif mutation == "homepage-review-malformed-percent":
        response.body = response.body.replace(
            b"</body>",
            (
                f'<a href="/raos%2review-{candidate.request_sha256}/">Review</a></body>'
            ).encode(),
        )
    elif mutation == "target-robots-disallow":
        response.body = response.body.replace(
            b"Disallow:\n",
            b"Disallow: /portable-power-station-guide/\n",
        )
    elif mutation == "malformed-sitemap-port":
        response.body = response.body.replace(
            b"https://kurashinoshirube.com/post-sitemap.xml",
            b"https://kurashinoshirube.com:invalid/post-sitemap.xml",
        )
    elif mutation == "duplicate-clean-canonical":
        response.body = response.body.replace(
            b"</urlset>",
            (
                f"<url><loc>{candidate.snapshot.payload.canonical_url}</loc>"
                "</url></urlset>"
            ).encode(),
        )
    elif mutation == "post-sitemap-review-url":
        response.body = response.body.replace(
            b"</urlset>",
            (
                f"<url><loc>https://kurashinoshirube.com/{candidate.slug}/</loc>"
                "</url></urlset>"
            ).encode(),
        )
    elif mutation == "post-sitemap-review-url-double-encoded":
        response.body = response.body.replace(
            b"</urlset>",
            (
                "<url><loc>https://kurashinoshirube.com/"
                f"%2572aos%252Dreview-{candidate.request_sha256}/</loc>"
                "</url></urlset>"
            ).encode(),
        )
    elif mutation == "page-sitemap-clean-canonical":
        response.body = response.body.replace(
            b"</urlset>",
            (
                f"<url><loc>{candidate.snapshot.payload.canonical_url}</loc>"
                "</url></urlset>"
            ).encode(),
        )
    elif mutation == "page-sitemap-review-url":
        response.body = response.body.replace(
            b"</urlset>",
            (
                f"<url><loc>https://kurashinoshirube.com/{candidate.slug}/</loc>"
                "</url></urlset>"
            ).encode(),
        )
    elif mutation == "page-sitemap-review-url-percent-encoded":
        response.body = response.body.replace(
            b"</urlset>",
            (
                "<url><loc>https://kurashinoshirube.com/"
                f"%72aos%2Dreview-{candidate.request_sha256}/</loc>"
                "</url></urlset>"
            ).encode(),
        )
    elif mutation == "wrong-category":
        response.body = canonical_json_bytes(
            [{"id": 42, "name": "未分類", "slug": "uncategorized"}]
        )
    elif mutation == "core-sitemap-enabled":
        response.status = 200
        response.content_type = "application/xml"
        response.body = _sitemap_index()
    elif mutation == "core-sitemap-legacy-404":
        response.status = 404
        response.headers = {}
        response.body = b"<html><body>not found</body></html>"
    elif mutation == "core-sitemap-temporary-redirect":
        response.status = 302
    elif mutation == "core-sitemap-missing-redirect-target":
        response.headers.pop("Location")
    elif mutation == "core-sitemap-wrong-redirect-target":
        response.headers["Location"] = (
            "https://kurashinoshirube.com/page-sitemap.xml"
        )
    elif mutation == "core-sitemap-query-redirect-target":
        response.headers["Location"] = (
            "https://kurashinoshirube.com/sitemap_index.xml?unexpected=1"
        )
    elif mutation == "core-sitemap-wrong-redirect-owner":
        response.headers["X-Redirect-By"] = "Unexpected Redirector"
    elif mutation == "core-sitemap-pagination-header":
        response.total = "0"
    elif mutation == "core-sitemap-nonempty-body":
        response.body = b"redirecting"
    elif mutation == "promoted-review-draft-still-present":
        response.body = canonical_json_bytes([_wp_post("draft", candidate, post_id=26)])
        response.total = "1"
        response.pages = "1"
    elif mutation == "review-public-rest-nonempty":
        response.body = canonical_json_bytes([_wp_post("publish", candidate)])
        response.total = "1"
        response.pages = "1"
    elif mutation == "review-url-redirect":
        response.headers["Location"] = candidate.snapshot.payload.canonical_url
    elif mutation == "review-url-public":
        response.status = 200
    elif mutation == "review-url-body-leak":
        response.body = _public_article_html(candidate)
    elif mutation == "review-url-partial-content-leak":
        fragment = (
            "停電への備えは、容量が大きいほど合うとは限りません。"
            "使いたい機器の消費電力"
        )
        assert fragment in candidate.content
        response.body = f"<html><body>{fragment}</body></html>".encode()
    elif mutation == "review-url-entity-title-leak":
        fragment = candidate.title[2:32]
        encoded = "".join(f"&#x{ord(character):x};" for character in fragment)
        response.body = f"<html><body>{encoded}</body></html>".encode()
    elif mutation == "review-url-snapshot-payload-sha-leak":
        response.body = (
            f"<html><body>{candidate.snapshot.payload_sha256}</body></html>".encode()
        )
    elif mutation == "review-url-snapshot-interior-leak":
        snapshot = candidate.snapshot.json_string()
        start = snapshot.index('"canonical_url"')
        fragment = snapshot[start : start + 70]
        assert len(fragment) == 70
        response.body = f"<html><body>{fragment}</body></html>".encode()
    elif mutation == "review-url-shortened-cta-leak":
        response.body = (
            "<html><body>楽天市場で写真・価格・在庫を確認する</body></html>".encode()
        )
    else:
        raise AssertionError("unknown mutation")

    adapter = OfficialSelfHostedEditorialPilotWordPressAdapter(
        private_root, connection_factory=_QueueFactory(*connections)
    )
    with pytest.raises(EditorialPilotFailure) as failure:
        adapter.verify_public(candidate, 1704)
    assert failure.value.code is EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH


def test_review_404_leak_guard_allows_clean_canonical_navigation_only(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_live_boundary(monkeypatch)
    candidate = _prepared_request()
    connections = _public_connections(candidate)
    connections[13].response.body = (
        '<html><body><a href="'
        f"{candidate.snapshot.payload.canonical_url}"
        '">公開記事へ戻る</a></body></html>'
    ).encode()
    adapter = OfficialSelfHostedEditorialPilotWordPressAdapter(
        private_root, connection_factory=_QueueFactory(*connections)
    )

    verification = adapter.verify_public(candidate, 1704)

    assert verification.public_surface_verified is True


def test_review_404_leak_guard_allows_expected_review_route_metadata(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_live_boundary(monkeypatch)
    candidate = _prepared_request()
    connections = _public_connections(candidate)
    review_url = f"https://kurashinoshirube.com/{candidate.slug}/"
    connections[13].response.body = (
        '<html><head><meta property="og:url" content="'
        f'{review_url}"><link rel="canonical" href="{review_url}">'
        "</head><body>ページが見つかりません。</body></html>"
    ).encode()
    adapter = OfficialSelfHostedEditorialPilotWordPressAdapter(
        private_root, connection_factory=_QueueFactory(*connections)
    )

    verification = adapter.verify_public(candidate, 1704)

    assert verification.public_surface_verified is True


def test_verify_public_rejects_x_robots_none_and_wrong_post_identity(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_live_boundary(monkeypatch)
    candidate = _prepared_request()
    connections = _public_connections(candidate)
    connections[4].response.headers["X-Robots-Tag"] = "none"
    adapter = OfficialSelfHostedEditorialPilotWordPressAdapter(
        private_root, connection_factory=_QueueFactory(*connections)
    )
    with pytest.raises(EditorialPilotFailure):
        adapter.verify_public(candidate, 1704)

    connections = _public_connections(candidate)
    adapter = OfficialSelfHostedEditorialPilotWordPressAdapter(
        private_root, connection_factory=_QueueFactory(*connections)
    )
    with pytest.raises(EditorialPilotFailure) as wrong_id:
        adapter.verify_public(candidate, 9999)
    assert wrong_id.value.code is EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH


def test_cli_verify_uses_committed_artifact_without_reprepare(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    article_id = "st1704-portable-power-station-guide"
    original = prepare_editorial_article(
        REPOSITORY_ROOT,
        article_id,
        evidence_reader=_reader,
        source_evidence_reader=_source_reader,
        clock=_fixed_clock,
    )
    journal = OwnerPrivateLiveReviewDraftJournal(private_root, _ArtifactJournalPort())
    journal.create(original.request)
    cli_port = _ArtifactJournalPort()

    def reprepare_forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("verify-public attempted current-evidence prepare")

    monkeypatch.setattr(
        application_module, "prepare_editorial_article", reprepare_forbidden
    )
    monkeypatch.setattr(
        https_module,
        "OfficialSelfHostedEditorialPilotWordPressAdapter",
        lambda _root: cli_port,
    )
    namespace = runpy.run_path(str(SCRIPT))
    run = namespace["_run"]
    run.__globals__["REPOSITORY_ROOT"] = private_root

    result = run("verify-public", article_id)

    assert result["packet_sha256"] == original.request.packet_sha256
    assert result["request_sha256"] == original.request.request_sha256
    assert "review_draft_post_id" in result
    assert "review_draft_rest_evidence_sha256" in result
    assert "review_public_rest_evidence_sha256" in result
    assert "review_url_html_evidence_sha256" in result
    assert cli_port.verified == [original.request]
    assert cli_port.verified_public_post_ids == [1704]
    with pytest.raises(AssertionError, match="current-evidence prepare"):
        run("create-review-draft", article_id)


def test_cli_carry_on_reconciliation_is_non_formal_and_never_reprepares(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = cast(
        ReviewDraftRequest,
        _prepared_request(PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID),
    )
    binding = _synthetic_carry_on_reconciliation_binding(candidate, monkeypatch)
    cli_port = _ArtifactJournalPort(
        target_public_post_id=PILOT_CARRY_ON_RECONCILIATION_TARGET_PUBLIC_POST_ID
    )

    class _ReadOnlyReconciliationJournal:
        def __init__(self, root: Path, port: object) -> None:
            assert root == private_root
            assert port is cli_port

        def carry_on_single_url_reconciliation_binding(
            self, article_id: str
        ) -> CarryOnSingleUrlReconciliationBinding:
            if article_id != PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID:
                raise EditorialPilotFailure(
                    EditorialPilotFailureCode.OPERATION_NOT_ALLOWED
                )
            return binding

    def reprepare_forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("reconciliation attempted current-evidence prepare")

    monkeypatch.setattr(
        application_module, "prepare_editorial_article", reprepare_forbidden
    )
    monkeypatch.setattr(
        https_module,
        "OfficialSelfHostedEditorialPilotWordPressAdapter",
        lambda _root: cli_port,
    )
    monkeypatch.setattr(
        json_module,
        "OwnerPrivateLiveReviewDraftJournal",
        _ReadOnlyReconciliationJournal,
    )
    namespace = runpy.run_path(str(SCRIPT))
    run = namespace["_run"]
    run.__globals__["REPOSITORY_ROOT"] = private_root

    result = run(
        "verify-carry-on-single-url",
        PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID,
    )

    assert result["command"] == "verify-carry-on-single-url"
    assert result["authority"] == "OWNER_GATED_READ_ONLY_RECONCILIATION"
    assert result["journal_state"] == "RECOVERY_ATTEMPTED"
    assert result["reconciliation_status"] == "PENDING_HUMAN_EXCEPTION"
    assert result["formal_gate_eligible"] is False
    assert result["journal_mutated"] is False
    assert result["production_evidence"] is False
    assert result["publication_authority"] is False
    assert result["strict_public_checks_passed"] is True
    assert result["public_surface_verified"] is False
    assert result["expected_public_post_id"] == 19
    assert result["expected_review_draft_post_id"] == 26
    assert result["review_draft_post_id"] == 26
    assert result["payload_sha256"] == candidate.snapshot.payload_sha256
    assert result["request_artifact_sha256"] == binding.request_artifact_sha256
    assert cli_port.verified == [candidate]
    assert cli_port.verified_public_post_ids == [19]
    with pytest.raises(Exception) as other_article:
        run("verify-carry-on-single-url", "st1704-portable-power-station-guide")
    assert getattr(other_article.value, "code", None) == "OPERATION_NOT_ALLOWED"


def test_terminal_carry_on_reconciliation_load_is_exact_and_journal_read_only(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = cast(
        ReviewDraftRequest,
        _prepared_request(PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID),
    )
    initial = OwnerPrivateLiveReviewDraftJournal(
        private_root,
        _ArtifactJournalPort(
            create_fails=True,
            target_public_post_id=(PILOT_CARRY_ON_RECONCILIATION_TARGET_PUBLIC_POST_ID),
        ),
    )
    with pytest.raises(EditorialPilotFailure):
        initial.create(candidate)
    terminal = OwnerPrivateLiveReviewDraftJournal(
        private_root,
        _ArtifactJournalPort(
            recover_fails=True,
            target_public_post_id=(PILOT_CARRY_ON_RECONCILIATION_TARGET_PUBLIC_POST_ID),
        ),
    )
    with pytest.raises(EditorialPilotFailure):
        terminal.recover(candidate)

    artifact_path = private_root / request_artifact_relative_path(candidate)
    artifact_sha256 = bytes_sha256(artifact_path.read_bytes())
    monkeypatch.setattr(
        domain_module,
        "PILOT_CARRY_ON_RECONCILIATION_PACKET_SHA256",
        candidate.packet_sha256,
    )
    monkeypatch.setattr(
        domain_module,
        "PILOT_CARRY_ON_RECONCILIATION_REQUEST_SHA256",
        candidate.request_sha256,
    )
    monkeypatch.setattr(
        domain_module,
        "PILOT_CARRY_ON_RECONCILIATION_PAYLOAD_SHA256",
        candidate.snapshot.payload_sha256,
    )
    monkeypatch.setattr(
        domain_module,
        "PILOT_CARRY_ON_RECONCILIATION_ARTIFACT_SHA256",
        artifact_sha256,
    )
    journal_directory = private_root / ".secrets" / OWNER_DIRECTORY / JOURNAL_DIRECTORY
    journal_path = next(
        journal_directory.glob(f"{candidate.article_id}.*.live.v1.json")
    )
    before_entries = tuple(sorted(path.name for path in journal_directory.iterdir()))
    before_journal = journal_path.read_bytes()
    before_artifact = artifact_path.read_bytes()
    before_journal_stat = journal_path.stat()
    before_artifact_stat = artifact_path.stat()

    binding = terminal.carry_on_single_url_reconciliation_binding(candidate.article_id)

    assert binding.request == candidate
    assert binding.request_artifact_sha256 == artifact_sha256
    assert binding.journal_state == "RECOVERY_ATTEMPTED"
    assert binding.target_public_post_id == 19
    assert binding.expected_review_draft_post_id == 26
    assert not binding.formal_gate_eligible
    assert not binding.journal_mutated
    assert before_entries == tuple(
        sorted(path.name for path in journal_directory.iterdir())
    )
    assert journal_path.read_bytes() == before_journal
    assert artifact_path.read_bytes() == before_artifact
    assert journal_path.stat().st_mtime_ns == before_journal_stat.st_mtime_ns
    assert journal_path.stat().st_ctime_ns == before_journal_stat.st_ctime_ns
    assert artifact_path.stat().st_mtime_ns == before_artifact_stat.st_mtime_ns
    assert artifact_path.stat().st_ctime_ns == before_artifact_stat.st_ctime_ns
    with pytest.raises(EditorialPilotFailure) as other_article:
        terminal.carry_on_single_url_reconciliation_binding(
            "st1704-portable-power-station-guide"
        )
    assert other_article.value.code is EditorialPilotFailureCode.OPERATION_NOT_ALLOWED


def test_cli_recover_uses_intent_artifact_without_reprepare(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    article_id = "st1704-portable-power-station-guide"
    original = prepare_editorial_article(
        REPOSITORY_ROOT,
        article_id,
        evidence_reader=_reader,
        source_evidence_reader=_source_reader,
        clock=_fixed_clock,
    )
    initial_port = _ArtifactJournalPort(create_fails=True)
    journal = OwnerPrivateLiveReviewDraftJournal(private_root, initial_port)
    with pytest.raises(EditorialPilotFailure):
        journal.create(original.request)
    recovery_port = _ArtifactJournalPort()

    def reprepare_forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("recovery attempted current-evidence prepare")

    monkeypatch.setattr(
        application_module, "prepare_editorial_article", reprepare_forbidden
    )
    monkeypatch.setattr(
        https_module,
        "OfficialSelfHostedEditorialPilotWordPressAdapter",
        lambda _root: recovery_port,
    )
    namespace = runpy.run_path(str(SCRIPT))
    run = namespace["_run"]
    run.__globals__["REPOSITORY_ROOT"] = private_root

    result = run("recover-create-review-draft", article_id)

    assert result["packet_sha256"] == original.request.packet_sha256
    assert result["request_sha256"] == original.request.request_sha256
    assert recovery_port.created == []
    assert recovery_port.recovered == [original.request]


def test_cli_exposes_only_five_commands_and_no_caller_selected_path() -> None:
    environment = {
        **os.environ,
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "TZ": "UTC",
    }
    help_result = subprocess.run(
        [
            str(REPOSITORY_ROOT / ".venv/bin/python"),
            "-B",
            "-I",
            "-S",
            str(SCRIPT),
            "--help",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    for command in (
        "prepare",
        "create-review-draft",
        "recover-create-review-draft",
        "verify-carry-on-single-url",
        "verify-public",
    ):
        assert command in help_result.stdout
    rejected = subprocess.run(
        [
            str(REPOSITORY_ROOT / ".venv/bin/python"),
            str(SCRIPT),
            "prepare",
            "--article-id",
            "st1704-portable-power-station-guide",
            "--path",
            "/arbitrary",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 2
    assert "unrecognized arguments" in rejected.stderr
    rejected_article = subprocess.run(
        [
            str(REPOSITORY_ROOT / ".venv/bin/python"),
            str(SCRIPT),
            "verify-carry-on-single-url",
            "--article-id",
            "st1704-portable-power-station-guide",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected_article.returncode == 2
    assert "invalid choice" in rejected_article.stderr


def test_at003_receipt_emits_complete_fixed_tools_assertion_url() -> None:
    namespace = runpy.run_path(str(SCRIPT))
    payload_sha256 = "1" * 64
    packet_sha256 = "2" * 64
    request_sha256 = "3" * 64
    receipt = SimpleNamespace(
        article_id="st1703-first-suitcase-comparison",
        disposition=SimpleNamespace(value="OWNER_LIVE_CREATED"),
        draft_id=1704,
        live_authority=True,
        packet_sha256=packet_sha256,
        publication_authority=False,
        request_sha256=request_sha256,
        response_sha256="4" * 64,
        status="draft",
        target_public_post_id=42,
    )
    candidate = SimpleNamespace(snapshot=SimpleNamespace(payload_sha256=payload_sha256))
    result = namespace["_receipt_result"]("create-review-draft", receipt, candidate)
    path = cast(str, result["owner_apply_path"])
    parts = urlsplit(path)
    assert parts.path == "/wp-admin/tools.php"
    assert list(parse_qs(parts.query)) == [
        "page",
        "payload_sha256",
        "packet_sha256",
        "request_sha256",
        "review_draft_id",
        "target_public_post_id",
    ]
    assert parse_qs(parts.query) == {
        "page": ["kurashinoshirube-at003-update-v1"],
        "payload_sha256": [payload_sha256],
        "packet_sha256": [packet_sha256],
        "request_sha256": [request_sha256],
        "review_draft_id": ["1704"],
        "target_public_post_id": ["42"],
    }
    assert "nonce" not in parts.query
    assert "authority" not in parts.query


def test_at003_artifact_preserves_target_and_owner_apply_hashes(
    private_root: Path,
) -> None:
    article_id = "st1703-first-suitcase-comparison"
    original = prepare_editorial_article(
        REPOSITORY_ROOT,
        article_id,
        evidence_reader=_reader,
        source_evidence_reader=_source_reader,
        clock=_fixed_clock,
    )
    journal = OwnerPrivateLiveReviewDraftJournal(private_root, _ArtifactJournalPort())
    receipt = journal.create(original.request)
    persisted, expected_public_post_id = journal.committed_request(article_id)
    namespace = runpy.run_path(str(SCRIPT))

    result = namespace["_receipt_result"]("create-review-draft", receipt, persisted)
    query = parse_qs(urlsplit(cast(str, result["owner_apply_path"])).query)

    assert persisted == original.request
    assert receipt.target_public_post_id == expected_public_post_id == 42
    assert query["payload_sha256"] == [original.request.snapshot.payload_sha256]
    assert query["packet_sha256"] == [original.request.packet_sha256]
    assert query["request_sha256"] == [original.request.request_sha256]
    assert query["review_draft_id"] == [str(receipt.draft_id)]
    assert query["target_public_post_id"] == ["42"]
