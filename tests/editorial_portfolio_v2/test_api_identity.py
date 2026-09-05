"""Recorded API-only identity resolution; no credentials or live requests."""

from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pytest

from raos.application.editorial import editorial_portfolio_v2 as owner


def binding() -> owner.ProductBindingV2:
    return owner.ProductBindingV2(
        product_id="PRD-TEST-API",
        official_name="Test MODEL-1",
        official_models=("MODEL-1",),
        representative_model="MODEL-1",
        official_jan=None,
        official_url="https://example.com/model-1",
        rakuten_shop_code=None,
        rakuten_item_code=None,
        required_title_tokens=("MODEL-1", "ホワイト"),
        product_kind_tokens=("食洗機",),
        forbidden_title_tokens=("セット", "部品"),
    )


def response(*titles: str, count: int | None = None) -> bytes:
    rows = [
        {
            "itemCode": f"shop:1000000{i}",
            "shopCode": "shop",
            "shopName": "Test shop",
            "itemName": title,
            "itemUrl": f"https://item.rakuten.co.jp/shop/model-{i}/",
            "mediumImageUrls": [
                "https://thumbnail.image.rakuten.co.jp/@0_mall/shop/cabinet/test.jpg?_ex=128x128"
            ],
        }
        for i, title in enumerate(titles)
    ]
    return json.dumps(
        {
            "Items": rows,
            "count": len(rows) if count is None else count,
            "page": 1,
            "hits": 30,
            "first": 1 if rows else 0,
            "last": len(rows),
            "pageCount": ((len(rows) if count is None else count) + 29) // 30,
        }
    ).encode()


def test_unique_model_resolves_without_owner_attestation() -> None:
    result = owner.discover_rakuten_identity_v1(
        binding(), response("MODEL-1 ホワイト 食洗機")
    )
    assert result == replace(
        binding(), rakuten_shop_code="shop", rakuten_item_code="shop:10000000"
    )
    assert binding().rakuten_item_code is None


def test_one_byte_query_token_is_omitted_only_from_search() -> None:
    product = replace(binding(), representative_model="DEEBOT mini 2")
    assert owner.rakuten_identity_query_v1(product) == "DEEBOT mini"
    assert product.representative_model == "DEEBOT mini 2"
    # Widened retrieval cannot make a different model satisfy the identity gate.
    assert (
        owner.discover_rakuten_identity_v1(product, response("DEEBOT mini 1")) is None
    )


@pytest.mark.parametrize(
    "titles",
    [
        (),
        ("MODEL-10 ホワイト 食洗機",),
        ("MODEL-1 ブラック 食洗機",),
        ("MODEL-1 ホワイト 食洗機 中古",),
        ("MODEL-1 ホワイト 食洗機 セット",),
        ("MODEL-1 ホワイト 食洗機", "MODEL-1 ホワイト 食洗機"),
    ],
)
def test_ambiguous_or_different_listing_never_resolves(titles: tuple[str, ...]) -> None:
    assert owner.discover_rakuten_identity_v1(binding(), response(*titles)) is None


def test_unexamined_search_results_cannot_establish_unique_identity() -> None:
    assert (
        owner.discover_rakuten_identity_v1(
            binding(),
            response("MODEL-1 ホワイト 食洗機", count=31),
        )
        is None
    )


def test_short_page_actual_hit_count_is_valid_but_inconsistent_count_is_rejected() -> (
    None
):
    document = json.loads(response("MODEL-1 ホワイト 食洗機"))
    document["hits"] = 1
    assert owner.discover_rakuten_identity_v1(binding(), json.dumps(document).encode())
    document["hits"] = 2
    with pytest.raises(owner.identity_capture.RakutenProductCaptureFailure):
        owner.discover_rakuten_identity_v1(binding(), json.dumps(document).encode())


def test_empty_page_with_zero_hits_is_not_a_provider_failure() -> None:
    document = json.loads(response())
    document["hits"] = 0
    assert (
        owner.discover_rakuten_identity_v1(binding(), json.dumps(document).encode())
        is None
    )
    document.pop("Items")
    assert (
        owner.discover_rakuten_identity_v1(binding(), json.dumps(document).encode())
        is None
    )
    document["count"] = 1
    with pytest.raises(owner.identity_capture.RakutenProductCaptureFailure):
        owner.discover_rakuten_identity_v1(binding(), json.dumps(document).encode())


def test_identity_receipt_replays_snapshot_and_rejects_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(owner, "portfolio_sha256", lambda _: "a" * 64)
    root = tmp_path / owner.STATUS_RELATIVE_PATH.parent / "provider"
    root.mkdir(parents=True, mode=0o700)
    raw = response("MODEL-1 ホワイト 食洗機")
    snapshot = root / "PRD-TEST-API.search-response.v2.json"
    snapshot.write_bytes(raw)
    snapshot.chmod(0o600)
    receipt = {
        "schema": "RAOS_RAKUTEN_API_IDENTITY_V1",
        "provenance": "API_VERIFIED",
        "owner_attested": False,
        "portfolio_sha256": "a" * 64,
        "product_id": binding().product_id,
        "query_model": "MODEL-1",
        "search_keyword": "MODEL-1",
        "retrieved_at": "2026-09-05T00:00:00Z",
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "item_code": "shop:10000000",
        "shop_code": "shop",
    }
    path = root / "PRD-TEST-API.identity.v1.json"

    def save(value: dict[str, object]) -> None:
        path.write_text(json.dumps(value))
        path.chmod(0o600)

    save(receipt)
    now = datetime(2026, 9, 5, 1, tzinfo=UTC)
    assert (
        owner.resolve_rakuten_identity_v1(
            tmp_path, binding(), now=now
        ).rakuten_item_code
        == "shop:10000000"
    )
    for field, value in (
        ("owner_attested", True),
        ("item_code", "shop:10000009"),
        ("query_model", "MODEL-2"),
        ("search_keyword", "unrelated"),
        ("portfolio_sha256", "b" * 64),
        ("retrieved_at", "2026-09-01T00:00:00Z"),
    ):
        save({**receipt, field: value})
        with pytest.raises(owner.EditorialPortfolioV2Failure):
            owner.resolve_rakuten_identity_v1(tmp_path, binding(), now=now)
    save(receipt)
    snapshot.write_bytes(response("MODEL-2 ホワイト 食洗機"))
    with pytest.raises(owner.EditorialPortfolioV2Failure):
        owner.resolve_rakuten_identity_v1(tmp_path, binding(), now=now)
