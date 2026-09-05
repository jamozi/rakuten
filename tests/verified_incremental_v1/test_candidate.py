"""Synthetic documents and typed source receipts only; no private or MCP I/O."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path, PurePosixPath
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from raos.application.editorial.editorial_portfolio_v3 import (
    ArticleBindingV3,
    CtaBindingV3,
    EditorialPortfolioV3,
    ProductBindingV3,
)
from raos.application.editorial.verified_incremental_sources_v1 import (
    SelectedOfficialSourceReceiptV1,
    SelectedOfficialSourcesFailure,
    SelectedOfficialSourcesV1,
    SelectedSourceIssueV1,
)
from scripts import raos_wordpress_incremental_candidate as owner


NOW = datetime(2026, 9, 5, 2, 0, tzinfo=UTC)
PAGES = ("home", "about-ad-policy", "comparison-policy", "privacy-policy")


def _portfolio() -> EditorialPortfolioV3:
    articles = []
    products = []
    for number in range(1, 11):
        article_id = f"article-{number}"
        product_id = f"PRD-MODEL-{number}"
        ctas = tuple(
            CtaBindingV3(
                article_id,
                f"a{number:02}",
                product_id,
                f"p{number:02}",
                f"snapshot-{number}",
                f"offer-{number}",
                f"icta_a{number:02}_p{number:02}_{code}",
                placement,
                code,
                f"slot-{number}-{code}",
                "NOT_CONFIGURED",
            )
            for placement, code in (
                ("product_card", "card"),
                ("final_summary", "final"),
            )
        )
        articles.append(
            ArticleBindingV3(
                article_id=article_id,
                article_code=f"a{number:02}",
                production_slug=f"guide-{number}",
                cluster_id="synthetic-cluster",
                intent_group_id=f"intent-{number}",
                category_label="比較",
                content_role="SPECIFICATION_COMPARISON",
                content_role_label="公式仕様比較",
                primary_query_intent="条件から比較対象を絞る",
                comparison_scope="合成商品",
                broader_article_id=None,
                home_order=number,
                snapshot_id=f"snapshot-{number}",
                related_article_ids=(),
                product_ids=(product_id,),
                cta_bindings=ctas,
            )
        )
        products.append(ProductBindingV3(product_id, f"p{number:02}"))
    return EditorialPortfolioV3(
        "synthetic-v1",
        owner.publication.ORIGIN,
        "a" * 64,
        tuple(articles),
        tuple(products),
        (),
    )


def _document(slug: str, number: int, *, post_type: str) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": "ContentDocumentV1",
        "id": 100 + number,
        "status": "publish",
        "post_type": post_type,
        "slug": slug,
        "title": f"既存の合成ページ {number}",
        "excerpt": "既存の合成抜粋",
        "block_markup": f"<p>既存の合成本文 {number}</p>",
        "taxonomies": {"category": [3, 8], "post_tag": [], "post_format": []},
        "media_ids": [1000 + number],
        "revision_id": 2 + number,
        "modified_gmt": "2026-09-05T01:59:00Z",
    }
    document["content_sha256"] = owner.publication._content_after_sha256(
        document, document["id"]
    )
    return document


def _markup(binding: ArticleBindingV3) -> str:
    product_id = binding.product_ids[0]
    return (
        '<div class="raos-editorial-v2">'
        '<dl class="raos-article-facts"><dt>実機</dt><dd>未使用</dd></dl>'
        f'<a href="#model-{product_id}-purchase">条件を見る</a>'
        f'<article id="model-{product_id}" class="product-profile" data-raos-product-id="{product_id}">'
        f"<h3>公式モデル {product_id}</h3><p>用途に合う条件と妥協点。</p>"
        '<a href="https://example.com/official-specifications">公式仕様の出典</a>'
        '<div class="raos-product-card__media">'
        f'<img data-raos-product-image-id="{product_id}" src="https://example.com/unverified.jpg"></div>'
        f'<div id="model-{product_id}-purchase" data-raos-purchase-action>'
        f'<p>未検証の購入注意書き</p><a data-raos-article-id="{binding.article_id}" '
        f'data-raos-product-id="{product_id}" data-raos-placement="product_card" '
        'href="https://example.com/unverified-offer">購入先</a></div></article>'
        '<div class="final-summary-action">'
        f'<a data-raos-article-id="{binding.article_id}" data-raos-product-id="{product_id}" '
        'data-raos-placement="final_summary" href="https://example.com/unverified-offer">購入先</a>'
        "</div></div>"
    )


def sample(selected: tuple[int, ...] = (1, 8)) -> dict[str, Any]:
    portfolio = _portfolio()
    bindings = tuple(portfolio.articles[index - 1] for index in selected)
    documents = [
        _document(binding.production_slug, index, post_type="post")
        for index, binding in enumerate(portfolio.articles, 1)
    ] + [
        _document(slug, 11 + index, post_type="page")
        for index, slug in enumerate(PAGES)
    ]
    articles = tuple(
        owner.publication.Article(
            f"local-preview-{binding.production_slug}",
            binding.production_slug,
            f"更新する合成記事 {binding.article_id}",
            "更新する合成抜粋",
            _markup(binding),
            {"category": [99], "post_tag": [], "post_format": []},
        )
        for binding in bindings
    )
    receipts = {
        f"source-{binding.article_id}": SelectedOfficialSourceReceiptV1(
            f"source-{binding.article_id}",
            "2026-09-05T01:00:00Z",
            "2026-09-06T01:00:00Z",
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "d" * 64,
            {"source_registry": "e" * 64, "locator_contract": "f" * 64},
            {f"claim-{binding.article_id}": "1" * 64},
        )
        for binding in bindings
    }
    sources = SelectedOfficialSourcesV1(
        tuple(binding.article_id for binding in bindings),
        {
            binding.article_id: {
                f"claim-{binding.article_id}": (f"source-{binding.article_id}",)
            }
            for binding in bindings
        },
        {binding.article_id: (f"source-{binding.article_id}",) for binding in bindings},
        receipts,
        (),
        {"source_registry": "e" * 64, "locator_contract": "f" * 64},
        "2026-09-05T02:00:00Z",
    )
    return {
        "portfolio": portfolio,
        "snapshot": {
            "schema": "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1",
            "publication_profile": owner.PROFILE,
            "origin": owner.publication.ORIGIN,
            "publication_authority": False,
            "source": "BOUNDED_WORDPRESS_EDITOR_MCP",
            "documents": documents,
        },
        "sources": sources,
        "articles": articles,
        "now": NOW,
    }


def test_selected_articles_only_preserve_live_identity_taxonomies_and_media() -> None:
    inputs = sample()
    snapshot_before = deepcopy(inputs["snapshot"])
    manifest, artifacts, preparation = owner.prepare_noncommercial_candidate(**inputs)
    assert inputs["snapshot"] == snapshot_before
    selected = {"guide-1", "guide-8"}
    assert set(preparation["production_documents"]) == selected
    assert set(manifest["rendered_document_slugs"]) == selected
    original = {doc["slug"]: doc for doc in snapshot_before["documents"]}
    assert manifest["unchanged_documents"] == {
        slug: doc["content_sha256"]
        for slug, doc in original.items()
        if slug not in selected
    }
    assert len(manifest["unchanged_documents"]) == 12
    assert set(PAGES) <= set(manifest["unchanged_documents"])
    assert manifest["shared_artifacts"] == {}
    assert len(artifacts) == 4
    for slug, row in preparation["production_documents"].items():
        assert row["post_id"] == original[slug]["id"]
        assert row["baseline_precondition"] == owner.publication.precondition(
            original[slug]
        )
        document = row["document"]
        assert document["post_type"] == original[slug]["post_type"] == "post"
        assert document["slug"] == slug
        assert document["taxonomies"] == original[slug]["taxonomies"]
        assert document["media_ids"] == original[slug]["media_ids"]
        assert row["after_sha256"] == owner.publication._content_after_sha256(
            document, row["post_id"]
        )
        assert (
            artifacts[f"local-{slug}"]
            == artifacts[f"production-{slug}"]
            == document["block_markup"].encode()
        )


def test_candidate_has_no_commerce_or_approval_but_keeps_products_and_sources() -> None:
    inputs = sample()
    manifest, artifacts, preparation = owner.prepare_noncommercial_candidate(**inputs)
    assert manifest["link_mode"] == preparation["link_mode"] == "standard-api"
    assert (
        manifest["publication_authority"]
        is preparation["publication_authority"]
        is False
    )
    assert manifest["measurement_collection_enabled"] is False
    assert preparation["status"] == "SOURCE_VERIFIED_AUDIT_NOT_EXECUTED"
    assert preparation["monetization_state"] == "NOT_INCLUDED"
    assert preparation["counts"] == {
        "articles": 2,
        "editorial_products": 2,
        "images": 0,
        "ctas": 0,
        "monetized_articles": 0,
    }
    assert "TWO_INDEPENDENT_CODEX_AUDITS" in preparation["required_next_gates"]
    assert "CONCRETE_OWNER_WP_ADMIN_APPROVAL" in preparation["required_next_gates"]
    assert "POST_APPLY_READBACK" in preparation["required_next_gates"]
    assert preparation["manifest_sha256"] == owner.digest(owner.canonical(manifest))
    assert preparation["snapshot_sha256"] == owner.digest(
        owner.publication.canonical_json_bytes(inputs["snapshot"])
    )
    for row in manifest["articles"]:
        assert row["images"] == row["ctas"] == {}
        assert len(row["excluded_commerce"]) == 3
        assert row["source_receipts"]
        assert row["claim_ids"]
        raw = artifacts[row["production_artifact"]["key"]].decode()
        assert "公式モデル" in raw and "用途に合う条件と妥協点" in raw
        assert "https://example.com/official-specifications" in raw
        assert "実機" in raw and "未使用" in raw
        for forbidden in (
            "unverified",
            "<img",
            "data-raos-placement",
            "購入注意書き",
            "購入先",
            "#model-" + row["editorial_product_ids"][0] + "-purchase",
        ):
            assert forbidden not in raw


@pytest.mark.parametrize("selected", ((), (1, 1)))
def test_empty_or_duplicate_article_selection_is_rejected(
    selected: tuple[int, ...],
) -> None:
    with pytest.raises(owner.IncrementalPublicationFailure):
        owner.prepare_noncommercial_candidate(**sample(selected))


def test_source_receipts_must_cover_exactly_the_selected_articles() -> None:
    inputs = sample()
    inputs["sources"] = sample((1,))["sources"]
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="SOURCE_SET_MISMATCH"
    ):
        owner.prepare_noncommercial_candidate(**inputs)


def test_incomplete_source_replay_cannot_prepare_a_candidate() -> None:
    inputs = sample()
    inputs["sources"] = replace(
        inputs["sources"],
        issues=(
            SelectedSourceIssueV1(
                "source-article-1", ("article-1",), "CAPTURE_MISSING"
            ),
        ),
    )
    with pytest.raises(SelectedOfficialSourcesFailure, match="SELECTED_SET_INCOMPLETE"):
        owner.prepare_noncommercial_candidate(**inputs)


@pytest.mark.parametrize(
    "expiry,expected",
    (
        ("2026-09-06T01:00:00Z", "2026-09-06T01:00:00Z"),
        ("2026-09-07T01:00:00Z", "2026-09-06T02:00:00Z"),
        ("2026-09-05T02:05:00Z", "2026-09-05T02:05:00Z"),
    ),
)
def test_audit_subject_expiry_never_outlives_sources_or_twenty_four_hours(
    expiry: str, expected: str
) -> None:
    inputs = sample()
    inputs["sources"] = replace(
        inputs["sources"],
        sources={
            key: replace(receipt, expires_at=expiry)
            for key, receipt in inputs["sources"].sources.items()
        },
    )
    manifest, _, _ = owner.prepare_noncommercial_candidate(**inputs)
    assert manifest["expires_at"] == expected


def test_expired_sources_fail_closed() -> None:
    inputs = sample()
    inputs["sources"] = replace(
        inputs["sources"],
        sources={
            key: replace(receipt, expires_at="2026-09-05T02:00:00Z")
            for key, receipt in inputs["sources"].sources.items()
        },
    )
    with pytest.raises(owner.IncrementalPublicationFailure, match="EXPIRED"):
        owner.prepare_noncommercial_candidate(**inputs)


@pytest.mark.parametrize(
    "field,value",
    (
        ("schema", "unknown"),
        ("origin", "https://example.com"),
        ("source", "UI_GUESS"),
        ("publication_authority", True),
    ),
)
def test_untrusted_or_authorized_snapshot_envelope_is_rejected(
    field: str, value: object
) -> None:
    inputs = sample()
    inputs["snapshot"][field] = value
    with pytest.raises(owner.IncrementalPublicationFailure, match="SNAPSHOT_INVALID"):
        owner.prepare_noncommercial_candidate(**inputs)


@pytest.mark.parametrize(
    "mutation",
    ("missing_policy", "extra_document", "duplicate_id", "draft", "modified_markup"),
)
def test_incomplete_or_altered_snapshot_cannot_supply_a_baseline(mutation: str) -> None:
    inputs = sample()
    documents = inputs["snapshot"]["documents"]
    if mutation == "missing_policy":
        documents.pop()
    elif mutation == "extra_document":
        documents.append(_document("unplanned", 20, post_type="post"))
    elif mutation == "duplicate_id":
        documents[1]["id"] = documents[0]["id"]
        documents[1]["content_sha256"] = owner.publication._content_after_sha256(
            documents[1], documents[1]["id"]
        )
    elif mutation == "draft":
        documents[0]["status"] = "draft"
    else:
        documents[0]["block_markup"] = "<p>改変された本文</p>"
    with pytest.raises(owner.IncrementalPublicationFailure):
        owner.prepare_noncommercial_candidate(**inputs)


def test_article_update_cannot_change_an_existing_post_into_a_page() -> None:
    inputs = sample()
    inputs["articles"] = (
        replace(inputs["articles"][0], post_type="page"),
        inputs["articles"][1],
    )
    with pytest.raises(owner.IncrementalPublicationFailure):
        owner.prepare_noncommercial_candidate(**inputs)


def test_production_candidate_rejects_local_preview_links() -> None:
    inputs = sample()
    first = inputs["articles"][0]
    inputs["articles"] = (
        replace(
            first,
            block_markup=first.block_markup.replace(
                "https://example.com/official-specifications",
                "http://127.0.0.1:39330/local-preview-guide-2/",
            ),
        ),
        inputs["articles"][1],
    )
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="PRODUCTION_ARTIFACT_INVALID"
    ):
        owner.prepare_noncommercial_candidate(**inputs)


def _theme_projection() -> bytes:
    return owner.publication.canonical_json_bytes(
        [{"path": "style.css", "size": 20, "sha256": "c" * 64}]
    )


def _deployment_baseline() -> dict[str, object]:
    return {
        "schema": "RAOS_WORDPRESS_DEPLOYMENT_BASELINE_SNAPSHOT_V1",
        "source": "BOUNDED_WORDPRESS_DEPLOYMENT_MCP",
        "status": "CAPTURED_READ_ONLY",
        "theme": {
            "tree_sha256": "d" * 64,
            "slug": "kurashinoshirube-child",
            "active": True,
        },
    }


def _policies() -> tuple[owner.publication.Article, ...]:
    return tuple(
        owner.publication.Article(
            slug,
            slug,
            "合成方針ページ",
            "合成方針の抜粋",
            "<div><h2>公開方針</h2><p>追加計測は無効。問い合わせはcontact@example.com。</p></div>",
            {},
            post_type="page",
        )
        for slug in PAGES[1:]
    )


def test_shared_theme_and_policy_opt_in_requires_full_mixed_preview_scope() -> None:
    inputs = sample()
    inputs["snapshot"]["deployment_status"] = _deployment_baseline()
    inputs.update(theme_projection=_theme_projection(), policy_articles=_policies())
    before = deepcopy(inputs["snapshot"])
    manifest, artifacts, preparation = owner.prepare_noncommercial_candidate(**inputs)
    assert inputs["snapshot"] == before
    originals = {document["slug"]: document for document in before["documents"]}
    assert set(manifest["shared_artifacts"]) == {"theme", *PAGES[1:]}
    assert set(manifest["rendered_document_slugs"]) == set(originals)
    assert len(manifest["rendered_document_slugs"]) == 14
    assert set(preparation["production_documents"]) == {
        "guide-1",
        "guide-8",
        *PAGES[1:],
    }
    assert set(manifest["unchanged_documents"]) == set(originals) - {
        "guide-1",
        "guide-8",
        *PAGES[1:],
    }
    assert "home" in manifest["unchanged_documents"]
    assert manifest["shared_artifacts"]["theme"] == {
        "key": "theme-tree",
        "sha256": owner.digest(_theme_projection()),
        "baseline_sha256": "d" * 64,
        "post_id": None,
    }
    assert preparation["expected_shared_readback_sha256"] == {
        "theme": owner.digest(_theme_projection())
    }
    for slug in PAGES[1:]:
        target = preparation["production_documents"][slug]
        assert target["post_id"] == originals[slug]["id"]
        assert target["document"]["slug"] == slug
        assert target["document"]["post_type"] == "page"
        assert target["document"]["taxonomies"] == originals[slug]["taxonomies"]
        assert target["document"]["media_ids"] == originals[slug]["media_ids"]
        assert target["after_sha256"] == owner.publication._content_after_sha256(
            target["document"], target["post_id"]
        )
        assert (
            artifacts[f"production-{slug}"]
            == target["document"]["block_markup"].encode()
        )
    assert preparation["counts"]["ctas"] == preparation["counts"]["images"] == 0
    assert preparation["publication_authority"] is False


def test_one_policy_opt_in_does_not_update_other_policies_or_the_home() -> None:
    inputs = sample()
    inputs["policy_articles"] = _policies()[:1]
    manifest, artifacts, preparation = owner.prepare_noncommercial_candidate(**inputs)
    assert set(manifest["shared_artifacts"]) == {"about-ad-policy"}
    assert {"home", "comparison-policy", "privacy-policy"} <= set(
        manifest["unchanged_documents"]
    )
    assert "theme-tree" not in artifacts
    assert preparation["expected_shared_readback_sha256"] == {}
    assert len(manifest["rendered_document_slugs"]) == 14


@pytest.mark.parametrize(
    "policy",
    [
        replace(_policies()[0], post_type="post"),
        replace(_policies()[0], production_slug="home"),
        replace(_policies()[0], production_slug="new-policy"),
    ],
)
def test_shared_policies_cannot_create_retype_or_change_home(
    policy: owner.publication.Article,
) -> None:
    inputs = sample()
    inputs["policy_articles"] = (policy,)
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="SHARED_TARGET_INVALID"
    ):
        owner.prepare_noncommercial_candidate(**inputs)


def test_duplicate_policy_selection_is_rejected() -> None:
    inputs = sample()
    inputs["policy_articles"] = (_policies()[0], _policies()[0])
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="SHARED_TARGET_INVALID"
    ):
        owner.prepare_noncommercial_candidate(**inputs)


@pytest.mark.parametrize(
    "deployment", [None, {}, {"theme": {}}, {"theme": {"tree_sha256": "not-a-hash"}}]
)
def test_theme_requires_exact_readback_baseline(deployment: object) -> None:
    inputs = sample()
    inputs.update(theme_projection=_theme_projection())
    inputs["snapshot"]["deployment_status"] = deployment
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="THEME_BASELINE_UNVERIFIED"
    ):
        owner.prepare_noncommercial_candidate(**inputs)


@pytest.mark.parametrize(
    "projection",
    [
        b"not-json",
        b"[]",
        b"{}",
        b'[ {"path":"style.css","size":20,"sha256":"' + b"c" * 64 + b'"} ]',
        owner.publication.canonical_json_bytes([{"unexpected": True}]),
        owner.publication.canonical_json_bytes(
            [{"path": "../style.css", "size": 20, "sha256": "c" * 64}]
        ),
        owner.publication.canonical_json_bytes(
            [{"path": "style.css", "size": -1, "sha256": "c" * 64}]
        ),
        owner.publication.canonical_json_bytes(
            [{"path": "style.css", "size": 20, "sha256": "wrong"}]
        ),
        owner.publication.canonical_json_bytes(
            [{"path": "style.css", "size": 20, "sha256": "c" * 64}] * 2
        ),
    ],
)
def test_theme_rejects_noncanonical_or_unsafe_manifest_rows(projection: bytes) -> None:
    inputs = sample()
    inputs.update(theme_projection=projection)
    inputs["snapshot"]["deployment_status"] = _deployment_baseline()
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="THEME_ARTIFACT_INVALID"
    ):
        owner.prepare_noncommercial_candidate(**inputs)


@pytest.mark.parametrize(
    "markup",
    [
        '<div><a href="http://127.0.0.1:39330/local-preview-guide-1/">ローカル</a></div>',
        '<div><a href="https://hb.afl.rakuten.co.jp/hgc/unverified/">未検証の購入先</a></div>',
        "<div><script>alert(1)</script></div>",
        "<div><p>閉じていない文書</div>",
    ],
)
def test_zero_commerce_policy_cannot_contain_local_unsafe_or_affiliate_markup(
    markup: str,
) -> None:
    inputs = sample()
    inputs["policy_articles"] = (replace(_policies()[0], block_markup=markup),)
    with pytest.raises(owner.IncrementalPublicationFailure):
        owner.prepare_noncommercial_candidate(**inputs)


def test_snapshot_and_artifact_filenames_are_complete_hash_bound_leaf_names() -> None:
    inputs = sample()
    inputs.update(theme_projection=_theme_projection(), policy_articles=_policies())
    inputs["snapshot"]["deployment_status"] = _deployment_baseline()
    _, artifacts, preparation = owner.prepare_noncommercial_candidate(**inputs)
    assert (
        preparation["snapshot_name"] == f"live-{preparation['snapshot_sha256']}.v1.json"
    )
    assert preparation["snapshot_sha256"] == owner.digest(
        owner.publication.canonical_json_bytes(inputs["snapshot"])
    )
    assert preparation["artifact_files"] == {
        key: f"{key}.v1.json" if key == "theme-tree" else f"{key}.html"
        for key in artifacts
    }
    assert len(set(preparation["artifact_files"].values())) == len(artifacts)
    for name in (preparation["snapshot_name"], *preparation["artifact_files"].values()):
        assert PurePosixPath(name).name == name
        assert ".." not in name


def _stub_cli(
    monkeypatch: pytest.MonkeyPatch,
    *,
    snapshot_name: str | None = None,
    flags: tuple[str, ...] = (),
) -> tuple[dict[str, Any], list[tuple[Path, str, bytes]], list[object]]:
    inputs = sample()
    inputs["snapshot"]["deployment_status"] = _deployment_baseline()
    canonical_name = f"live-{owner.digest(owner.publication.canonical_json_bytes(inputs['snapshot']))}.v1.json"
    reads: list[object] = []
    writes: list[tuple[Path, str, bytes]] = []

    def read(root: Path, name: str) -> dict[str, Any]:
        reads.append((root, name))
        return inputs["snapshot"]

    def write(root: Path, name: str, raw: bytes) -> Path:
        writes.append((root, name, raw))
        return root / name

    monkeypatch.setattr(owner, "read_private_json", read)
    monkeypatch.setattr(owner, "write_private_bytes", write)
    monkeypatch.setattr(owner, "ensure_private_root", lambda root: root)
    monkeypatch.setattr(
        owner, "load_editorial_portfolio_v3", lambda _: inputs["portfolio"]
    )
    monkeypatch.setattr(
        owner.publication, "load_articles", lambda _: inputs["articles"]
    )
    monkeypatch.setattr(
        owner, "validate_selected_official_sources", lambda **_: inputs["sources"]
    )
    monkeypatch.setattr(
        owner,
        "datetime",
        SimpleNamespace(now=lambda _: NOW, strptime=datetime.strptime),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "candidate",
            "--snapshot-name",
            snapshot_name or canonical_name,
            "--articles",
            "guide-1,guide-8",
            *flags,
        ],
    )
    return inputs, writes, reads


def test_cli_defaults_do_not_include_theme_or_policy_and_write_declared_artifact_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, writes, reads = _stub_cli(monkeypatch)

    def forbidden(*_: object, **__: object) -> None:
        pytest.fail("Optional theme/policy route invoked without an explicit flag")

    monkeypatch.setattr(owner, "current_theme_projection", forbidden)
    monkeypatch.setattr(owner.publication, "load_policy_pages", forbidden)
    assert owner.main() == 0
    assert len(reads) == 1
    preparation = json.loads(
        next(raw for _, name, raw in writes if name == "candidate-preparation.v1.json")
    )
    names = {name for path, name, _ in writes if path.name == "artifacts"}
    assert names == set(preparation["artifact_files"].values())
    assert not any("policy" in name or "theme" in name for name in names)
    assert preparation["snapshot_name"] == reads[0][1]
    assert all(
        "/home/minami/rakuten/.secrets/wordpress-mcp/incremental-candidates/"
        in str(path)
        for path, _, _ in writes
    )


def test_cli_explicit_shared_flags_load_production_policies_and_exact_theme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, writes, _ = _stub_cli(
        monkeypatch, flags=("--include-theme", "--update-policies", "all")
    )
    calls = []
    monkeypatch.setattr(owner, "current_theme_projection", lambda: _theme_projection())

    def policies(*, profile: str) -> tuple[owner.publication.Article, ...]:
        calls.append(profile)
        return _policies()

    monkeypatch.setattr(owner.publication, "load_policy_pages", policies)
    assert owner.main() == 0
    assert calls == ["production"]
    names = {name for path, name, _ in writes if path.name == "artifacts"}
    assert "theme-tree.v1.json" in names
    assert {f"production-{slug}.html" for slug in PAGES[1:]} <= names


def test_cli_refuses_noncanonical_snapshot_name_before_writing_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, writes, _ = _stub_cli(monkeypatch, snapshot_name="renamed-snapshot.v1.json")
    assert owner.main() == 69
    assert writes == []


@pytest.mark.parametrize("mutation", ("none", "package_descriptor", "tracked_tree"))
def test_current_theme_projection_is_bound_to_fixed_package_and_tracked_tree(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    raw = _theme_projection()
    expected = owner.digest(raw)
    calls: list[str] = []

    def package() -> tuple[bytes, dict[str, object]]:
        calls.append("fixed-theme-package")
        return b"synthetic-package-only", {
            "file_manifest": json.loads(raw),
            "file_manifest_sha256": "f" * 64
            if mutation == "package_descriptor"
            else expected,
        }

    monkeypatch.setitem(
        sys.modules,
        "raos_wordpress_deployment_operator",
        SimpleNamespace(theme_package=package),
    )
    monkeypatch.setattr(
        owner.publication,
        "tracked_theme_tree_sha256",
        lambda: "e" * 64 if mutation == "tracked_tree" else expected,
    )
    if mutation == "none":
        assert owner.current_theme_projection() == raw
    else:
        with pytest.raises(
            owner.IncrementalPublicationFailure, match="THEME_ARTIFACT_INVALID"
        ):
            owner.current_theme_projection()
    assert calls == ["fixed-theme-package"]
