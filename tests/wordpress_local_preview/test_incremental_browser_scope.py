from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
BROWSER = ROOT / "changes/wordpress-local-preview-v1/browser"
AUDIT = BROWSER / "wordpress_local_preview_audit.function.js"
spec = importlib.util.spec_from_file_location(
    "wordpress_incremental_browser_scope", BROWSER / "incremental_scope.py"
)
assert spec and spec.loader
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


def _scope() -> dict:
    return {
        "schema": "RAOS_WORDPRESS_INCREMENTAL_BROWSER_SCOPE_V1",
        "publication_profile": "verified-incremental",
        "link_mode": "standard-api",
        "preparation_binding_sha256": "a" * 64,
        "selected_article_ids": ["article-new"],
        "articles": [
            {
                "article_id": "article-new",
                "editorial_product_ids": ["PRD-NEW"],
                "expected_cta_ids": ["cta-new-card", "cta-new-final"],
                "expected_ctas": [
                    {
                        "cta_id": "cta-new-card",
                        "product_id": "PRD-NEW",
                        "placement": "product_card",
                    },
                    {
                        "cta_id": "cta-new-final",
                        "product_id": "PRD-NEW",
                        "placement": "final_summary",
                    },
                ],
                "expected_image_product_ids": ["PRD-NEW"],
                "expected_article_facts": {
                    "content_role_labels": ["用途別の選び方"],
                    "primary_query_intents": ["設置条件を確認する"],
                },
                "expected_disclosure_policy_link_count": 1,
                "display_projection": {
                    "state": "NOT_APPLICABLE",
                    "contract_sha256": "a" * 64,
                    "input_sha256": "b" * 64,
                    "output_sha256": "b" * 64,
                    "profile": None,
                    "removed_decoration_count": 0,
                    "removed_neutral_media_count": 0,
                },
            },
            {
                "article_id": "article-old",
                "editorial_product_ids": ["PRD-OLD"],
                "expected_cta_ids": [],
                "expected_ctas": [
                    {
                        "cta_id": None,
                        "product_id": "PRD-OLD",
                        "placement": "product_card",
                    },
                    {
                        "cta_id": None,
                        "product_id": "PRD-OLD",
                        "placement": "final_summary",
                    },
                ],
                "expected_image_product_ids": ["PRD-OLD", "PRD-OLD"],
                "expected_article_facts": {
                    "content_role_labels": [],
                    "primary_query_intents": [],
                },
                "expected_disclosure_policy_link_count": 0,
                "display_projection": {
                    "state": "NOT_APPLICABLE",
                    "contract_sha256": "a" * 64,
                    "input_sha256": "c" * 64,
                    "output_sha256": "c" * 64,
                    "profile": None,
                    "removed_decoration_count": 0,
                    "removed_neutral_media_count": 0,
                },
            },
        ],
    }


def _audit(scope: dict, article_id: str = "article-new") -> dict:
    row = next(row for row in scope["articles"] if row["article_id"] == article_id)
    return {
        "productIds": row["editorial_product_ids"],
        "commerceCtas": [
            {
                **cta,
                "article_id": article_id,
                "affiliate_host_valid": True,
                "has_measured_identifier": False,
                "rel_tokens": ["sponsored", "nofollow"],
            }
            for cta in row["expected_ctas"]
        ],
        "commerceImages": [
            {
                "product_id": product,
                "state": "verified",
                "alt_valid": True,
                "dimensions_valid": True,
                "lazy": True,
            }
            for product in row["expected_image_product_ids"]
        ],
        "commercePlaceholderCount": 0,
        "articleFacts": {
            "contentRoleLabels": row["expected_article_facts"]["content_role_labels"],
            "primaryQueryIntents": row["expected_article_facts"][
                "primary_query_intents"
            ],
        },
        "disclosure": {
            "policyLinkCount": row["expected_disclosure_policy_link_count"],
        },
    }


def _node(payload: dict) -> dict:
    node = shutil.which("node")
    assert node is not None
    result = subprocess.run(
        [
            node,
            "-e",
            """
const fs = require('fs');
const factory = eval(fs.readFileSync(process.argv[1], 'utf8'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
try {
  const scope = factory.validateIncrementalScope({
    publicationProfile: input.profile || 'verified-incremental',
    linkMode: input.mode || 'standard-api', incrementalScope: input.scope,
    articleIds: input.article_ids || ['article-new', 'article-old'],
    categorySurfaces: input.category_surfaces || [],
  });
  const article = input.audit ? factory.validateIncrementalArticle({
    scope, articleId: input.article_id || 'article-new', audit: input.audit,
  }) : null;
  const listingFailed = input.listing ? factory.validateListing({
    scope, surface: input.category_surfaces[0], audit: input.listing,
    articleRows: input.article_rows,
  }) : null;
  process.stdout.write(JSON.stringify({ valid: true, article, listingFailed }));
} catch (error) {
  process.stdout.write(JSON.stringify({ valid: false, error: error.message }));
}
""",
            str(AUDIT),
        ],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_incremental_exact_scope_accepts_two_positions_and_single_image() -> None:
    scope = _scope()
    result = _node({"scope": scope, "audit": _audit(scope)})
    assert result["valid"] is True
    assert result["article"] == {
        "failed": False,
        "selected": True,
        "commerceStatus": "EXPECTED_VERIFIED_SET_PRESENT",
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_product",
        "wrong_cta",
        "missing_cta",
        "duplicate_cta",
        "wrong_placement",
        "wrong_image",
        "extra_image",
        "placeholder",
        "unverified_image",
        "wrong_article",
        "wrong_host",
        "measured_identifier",
        "missing_rel",
        "missing_alt",
        "missing_size",
        "not_lazy",
    ],
)
def test_selected_dom_tampering_is_rejected_even_when_counts_match(
    mutation: str,
) -> None:
    scope = _scope()
    audit = _audit(scope)
    if mutation == "wrong_product":
        audit["productIds"] = ["PRD-OTHER"]
    elif mutation == "wrong_cta":
        audit["commerceCtas"][0]["cta_id"] = "cta-wrong-card"
    elif mutation == "missing_cta":
        audit["commerceCtas"].pop()
    elif mutation == "duplicate_cta":
        audit["commerceCtas"][1] = copy.deepcopy(audit["commerceCtas"][0])
    elif mutation == "wrong_placement":
        audit["commerceCtas"][0]["placement"] = "final_summary"
    elif mutation == "wrong_image":
        audit["commerceImages"][0]["product_id"] = "PRD-OTHER"
    elif mutation == "extra_image":
        audit["commerceImages"].append(copy.deepcopy(audit["commerceImages"][0]))
    elif mutation == "placeholder":
        audit["commercePlaceholderCount"] = 1
    elif mutation == "unverified_image":
        audit["commerceImages"][0]["state"] = "neutral"
    elif mutation == "wrong_article":
        audit["commerceCtas"][0]["article_id"] = "article-old"
    elif mutation == "wrong_host":
        audit["commerceCtas"][0]["affiliate_host_valid"] = False
    elif mutation == "measured_identifier":
        audit["commerceCtas"][0]["has_measured_identifier"] = True
    elif mutation == "missing_rel":
        audit["commerceCtas"][0]["rel_tokens"] = ["nofollow"]
    else:
        field = {
            "missing_alt": "alt_valid",
            "missing_size": "dimensions_valid",
            "not_lazy": "lazy",
        }[mutation]
        audit["commerceImages"][0][field] = False
    result = _node({"scope": scope, "audit": audit})
    assert result["valid"] is True
    assert result["article"]["failed"] is True


def test_zero_commerce_is_allowed_without_claiming_revenue_verification() -> None:
    scope = _scope()
    for field in ("expected_cta_ids", "expected_ctas", "expected_image_product_ids"):
        scope["articles"][0][field] = []
    result = _node({"scope": scope, "audit": _audit(scope)})
    assert result["article"] == {
        "failed": False,
        "selected": True,
        "commerceStatus": "NOT_INCLUDED",
    }


def test_legacy_null_cta_ids_and_image_multiset_remain_exact_not_reverified() -> None:
    scope = _scope()
    audit = _audit(scope, "article-old")
    for image in audit["commerceImages"]:
        image["state"] = "unknown"
    result = _node({"scope": scope, "audit": audit, "article_id": "article-old"})
    assert result["article"] == {
        "failed": False,
        "selected": False,
        "commerceStatus": "UNCHANGED_NOT_REVERIFIED",
    }
    audit["commerceCtas"][0]["product_id"] = "PRD-NEW"
    result = _node({"scope": scope, "audit": audit, "article_id": "article-old"})
    assert result["article"]["failed"] is True


@pytest.mark.parametrize("article_id", ["article-new", "article-old"])
@pytest.mark.parametrize("mutation", ["role", "intent", "policy_link", "hidden_fact"])
def test_mixed_editorial_fields_must_match_each_bound_body(
    article_id: str, mutation: str
) -> None:
    scope = _scope()
    audit = copy.deepcopy(_audit(scope, article_id))
    if mutation == "role":
        audit["articleFacts"]["contentRoleLabels"] = ["別の記事分類"]
    elif mutation == "intent":
        audit["articleFacts"]["primaryQueryIntents"] = ["別の記事の目的"]
    elif mutation == "policy_link":
        audit["disclosure"]["policyLinkCount"] += 1
    else:
        scope_row = next(
            row for row in scope["articles"] if row["article_id"] == article_id
        )
        scope_row["expected_article_facts"]["content_role_labels"] = [
            "本文に存在する分類"
        ]
        audit["articleFacts"]["contentRoleLabels"] = []
    result = _node({"scope": scope, "audit": audit, "article_id": article_id})
    assert result["valid"] is True
    assert result["article"]["failed"] is True


def test_editorial_expectations_derive_nested_text_and_only_actual_policy_links() -> (
    None
):
    body = """<div><dl>
      <div><dt>記事分類</dt><dd><span>用途別</span>の選び方</dd></div>
      <div><dt>この記事で答えること</dt><dd>幅 &amp; 奥行を確認する</dd></div>
      <div><dt>記事分類</dt><span>隣の要素はddでない</span><dd>取り違え禁止</dd></div>
    </dl><aside class="raos-disclosure">
      <a href="/comparison-policy/">編集方針</a>
      <a href="https://kurashinoshirube.com/comparison-policy/">編集方針</a>
      <a href="https://example.invalid/comparison-policy/">外部サイト</a>
      <a href="/comparison-policy/?tracked=yes">異なるquery</a>
      <a href="/comparison-policy/#details">異なるfragment</a>
    </aside><a href="/comparison-policy/">開示ブロック外</a></div>"""
    actual = loader.derive_article(body, "article-old")
    assert actual["expected_article_facts"] == {
        "content_role_labels": ["用途別の選び方"],
        "primary_query_intents": ["幅 & 奥行を確認する"],
    }
    assert actual["expected_disclosure_policy_link_count"] == 2
    absent = loader.derive_article("<p>本番の旧稿</p>", "article-old")
    assert absent["expected_article_facts"] == {
        "content_role_labels": [],
        "primary_query_intents": [],
    }
    assert absent["expected_disclosure_policy_link_count"] == 0


def test_a10_current_nonaffiliate_disclosure_matches_the_browser_contract() -> None:
    body = (
        BROWSER.parent / "fixtures/articles/solota-vs-rakua-mini-plus.html"
    ).read_text()
    row = loader.derive_article(body, "solota-vs-rakua-mini-plus")
    assert row["expected_article_facts"]["content_role_labels"] == [
        "型番・販売表示の確認案内"
    ]
    assert row["expected_disclosure_policy_link_count"] == 1
    audit = AUDIT.read_text()
    for phrase in (
        "購入リンクなし",
        "商品カードとアフィリエイトリンクは掲載していません",
        "購入先を案内しないことは、商品の性能が劣るという意味ではありません",
    ):
        assert phrase in body and phrase in audit
    assert "以前の比較対象の販売状態を確認する案内記事" not in audit


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_binding",
        "zero_binding",
        "wrong_profile",
        "wrong_mode",
        "missing_article",
        "duplicate_product",
        "selected_null_cta",
        "duplicate_image",
        "invented_count",
        "missing_facts",
        "invented_fact_field",
        "non_array_facts",
        "selected_missing_facts",
        "invalid_policy_count",
        "selected_missing_policy_link",
    ],
)
def test_scope_contract_tampering_is_rejected(mutation: str) -> None:
    scope = _scope()
    if mutation == "missing_binding":
        scope.pop("preparation_binding_sha256")
    elif mutation == "zero_binding":
        scope["preparation_binding_sha256"] = "0" * 64
    elif mutation == "wrong_profile":
        scope["publication_profile"] = "legacy-full"
    elif mutation == "wrong_mode":
        scope["link_mode"] = "measured-admin"
    elif mutation == "missing_article":
        scope["articles"].pop()
    elif mutation == "duplicate_product":
        scope["articles"][0]["editorial_product_ids"].append("PRD-NEW")
    elif mutation == "selected_null_cta":
        scope["articles"][0]["expected_ctas"][0]["cta_id"] = None
        scope["articles"][0]["expected_cta_ids"].pop(0)
    elif mutation == "duplicate_image":
        scope["articles"][0]["expected_image_product_ids"].append("PRD-NEW")
    elif mutation == "missing_facts":
        scope["articles"][0].pop("expected_article_facts")
    elif mutation == "invented_fact_field":
        scope["articles"][0]["expected_article_facts"]["skip_facts"] = True
    elif mutation == "non_array_facts":
        scope["articles"][0]["expected_article_facts"]["content_role_labels"] = "分類"
    elif mutation == "selected_missing_facts":
        scope["articles"][0]["expected_article_facts"]["content_role_labels"] = []
    elif mutation == "invalid_policy_count":
        scope["articles"][1]["expected_disclosure_policy_link_count"] = -1
    elif mutation == "selected_missing_policy_link":
        scope["articles"][0]["expected_disclosure_policy_link_count"] = 0
    else:
        scope["expected_product_count"] = 33
    assert _node({"scope": scope})["valid"] is False


@pytest.mark.parametrize("mode", ["standard-api", "measured-admin"])
def test_legacy_profile_is_explicitly_unchanged_and_refuses_scope_reuse(
    mode: str,
) -> None:
    assert (
        _node({"profile": "legacy-full", "mode": mode, "scope": None})["valid"] is True
    )
    assert (
        _node({"profile": "legacy-full", "mode": mode, "scope": _scope()})["valid"]
        is False
    )
    if mode == "measured-admin":
        assert _node({"mode": mode, "scope": _scope()})["valid"] is False


def _private_write(path: Path, raw: bytes) -> None:
    path.write_bytes(raw)
    path.chmod(0o600)


def _rebind(root: Path, binding: dict) -> Path:
    raw = (json.dumps(binding, ensure_ascii=False, sort_keys=True) + "\n").encode()
    _private_write(root / "preparation-binding.v1.json", raw)
    target = root.parent / f"incremental-preview-{hashlib.sha256(raw).hexdigest()}"
    if target != root:
        root.rename(target)
    return target


def _overlay(tmp_path: Path) -> tuple[Path, dict, dict]:
    root = tmp_path / "draft"
    root.mkdir(mode=0o700)
    (root / "articles").mkdir(mode=0o700)
    slugs = [f"guide-{index}" for index in range(10)]
    inventory = {
        "surfaces": [
            {
                "kind": "article",
                "production_path": f"/{slug}/",
                "article_id": f"article-{index}",
            }
            for index, slug in enumerate(slugs)
        ]
    }
    posts = {
        "schema": "RAOS_WORDPRESS_LOCAL_PREVIEW_FIXTURE_V1",
        "seed_version": "test",
        "posts": [
            {"slug": f"local-preview-{slug}", "content_file": f"articles/{slug}.html"}
            for slug in slugs
        ],
    }
    posts_raw = json.dumps(posts).encode()
    _private_write(root / "posts.json", posts_raw)
    body_hashes, scope_rows = {}, []
    for index, slug in enumerate(slugs):
        commerce = (
            ""
            if index == 0
            else (
                '<img src="https://example.invalid/recorded.jpg" alt="Recorded fixture" />'
                '<a class="raos-cta" data-raos-placement="product_card" '
                'href="https://hb.afl.rakuten.co.jp/recorded-test">Recorded fixture</a>'
            )
        )
        body = f'<article class="product-profile" data-raos-product-id="PRD-{index}">{commerce}</article>'
        _private_write(root / "articles" / f"{slug}.html", body.encode())
        body_hashes[slug] = hashlib.sha256(body.encode()).hexdigest()
        scope_rows.append(loader.derive_article(body, f"article-{index}"))
    binding = {
        "schema": "RAOS_WORDPRESS_MIXED_PREVIEW_PREPARATION_V1",
        "publication_profile": "verified-incremental",
        "link_mode": "standard-api",
        "publication_authority": False,
        "status": "NOT_VERIFIED_FOR_PUBLICATION",
        "selected_commerce": "OMITTED_NOT_VERIFIED",
        "source_snapshot_sha256": "a" * 64,
        "selected_slugs": [slugs[0]],
        "article_body_sha256": body_hashes,
        "baseline_document_sha256": {slug: "b" * 64 for slug in slugs},
        "article_states": {
            slug: "REVISED_DRAFT_NOT_VERIFIED"
            if index == 0
            else "UNCHANGED_LIVE_CONTENT"
            for index, slug in enumerate(slugs)
        },
        "posts_sha256": hashlib.sha256(posts_raw).hexdigest(),
        "incremental_scope": {
            "schema": "RAOS_WORDPRESS_INCREMENTAL_BROWSER_SCOPE_V1",
            "publication_profile": "verified-incremental",
            "link_mode": "standard-api",
            "selected_article_ids": ["article-0"],
            "articles": scope_rows,
        },
    }
    return _rebind(root, binding), inventory, binding


def test_private_loader_replays_actual_bytes_and_injects_binding_hash(
    tmp_path: Path,
) -> None:
    root, inventory, binding = _overlay(tmp_path)
    result = loader.load_scope(root, inventory)
    assert result == {
        **binding["incremental_scope"],
        "preparation_binding_sha256": root.name.removeprefix("incremental-preview-"),
    }
    serialized = json.dumps(result)
    assert "https://" not in serialized
    assert ".secrets" not in serialized
    assert os.stat(root / "posts.json").st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "mutation",
    [
        "body_hash",
        "posts_hash",
        "same_counts_wrong_product",
        "scope_count",
        "link_mode",
        "selected_commerce",
        "article_state",
        "binding_directory",
        "public_file",
        "symlink",
        "invented_old_classification",
        "invented_old_policy_link",
    ],
)
def test_private_loader_refuses_drift_and_rebound_false_scope(
    tmp_path: Path, mutation: str
) -> None:
    root, inventory, binding = _overlay(tmp_path)
    article_path = root / "articles/guide-0.html"
    if mutation == "body_hash":
        _private_write(article_path, article_path.read_bytes() + b"\n")
    elif mutation == "posts_hash":
        posts = root / "posts.json"
        _private_write(posts, posts.read_bytes() + b"\n")
    elif mutation == "same_counts_wrong_product":
        binding["incremental_scope"]["articles"][0]["editorial_product_ids"] = [
            "PRD-WRONG"
        ]
        root = _rebind(root, binding)
    elif mutation == "scope_count":
        binding["incremental_scope"]["expected_product_count"] = 10
        root = _rebind(root, binding)
    elif mutation == "link_mode":
        binding["link_mode"] = "measured-admin"
        root = _rebind(root, binding)
    elif mutation == "selected_commerce":
        binding["selected_commerce"] = "VERIFIED"
        root = _rebind(root, binding)
    elif mutation == "article_state":
        binding["article_states"]["guide-0"] = "UNCHANGED_LIVE_CONTENT"
        root = _rebind(root, binding)
    elif mutation == "binding_directory":
        target = root.parent / "incremental-preview-wrong"
        root.rename(target)
        root = target
    elif mutation == "public_file":
        article_path.chmod(0o644)
    elif mutation == "invented_old_classification":
        binding["incremental_scope"]["articles"][1]["expected_article_facts"][
            "content_role_labels"
        ] = ["新稿だけの分類"]
        root = _rebind(root, binding)
    elif mutation == "invented_old_policy_link":
        binding["incremental_scope"]["articles"][1][
            "expected_disclosure_policy_link_count"
        ] = 1
        root = _rebind(root, binding)
    else:
        destination = root.parent / "linked-article.html"
        article_path.rename(destination)
        article_path.symlink_to(destination)
    with pytest.raises(loader.ScopeFailure):
        loader.load_scope(root, inventory)


def test_incremental_runner_preserves_full_audit_and_rechecks_prepared_bytes() -> None:
    check = (BROWSER / "check.sh").read_text()
    audit = AUDIT.read_text()
    assert check.count('"$python_bin" "$incremental_scope_loader"') == 2
    assert '"$incremental_scope_file"' in check
    assert "publicationProfile, linkMode, incrementalScope" in check
    assert 'cmp -s "$incremental_scope_file" -' in check
    assert "audit.missingAlt !== 0 || audit.unloadedImages !== 0" in audit
    assert "browserCookieCount !== 0" in audit
    assert "lifecycleProductCtaInvariantFailure" in audit
    assert "results.length !== surfaces.length * widths.length" in audit
    assert "audit.axeViolations.length !== 0" in audit
    assert "Object.values(audit.anchorSecurity).some((count) => count !== 0)" in audit
    assert "!audit.disclosure.opacityVisible || !audit.disclosure.inViewport" in audit
    assert "audit.disclosure.beforeFirstCtaDom" in audit
    assert "disclosureKeyboardFailure || focusFlowFailure" in audit


def _category_surface(slug: str = "mobility") -> dict:
    return {
        "surface_id": f"archive-category-{slug}",
        "local_path": f"/category/{slug}/",
        "kind": "archive",
        "archive_type": "category",
        "expected_state": "EXCERPT_LIST",
    }


def _category_metadata(root: Path, inventory: dict, binding: dict) -> tuple[Path, dict]:
    inventory["local_surfaces"] = [_category_surface()]
    policies = ["policy-one", "policy-two", "policy-three"]
    inventory["surfaces"].extend(
        {"kind": "policy", "production_path": f"/{slug}/"} for slug in policies
    )
    (root / "pages").mkdir(mode=0o700)
    (root / "baseline-pages").mkdir(mode=0o700)
    page_hash = hashlib.sha256(b"<p>Recorded policy</p>").hexdigest()
    for slug in policies + ["home"]:
        _private_write(
            root / "baseline-pages" / f"{slug}.html", b"<p>Recorded policy</p>"
        )
        if slug != "home":
            _private_write(root / "pages" / f"{slug}.html", b"<p>Recorded policy</p>")
    pages = {
        "schema": "RAOS_WORDPRESS_LOCAL_PREVIEW_PAGES_V1",
        "pages": [
            {"slug": slug, "content_file": f"pages/{slug}.html"} for slug in policies
        ],
    }
    pages_raw = json.dumps(pages).encode()
    _private_write(root / "pages.json", pages_raw)
    binding.update(
        {
            "metadata_status": "VERIFIED_FIELDS_ONLY",
            "metadata_blockers": [],
            "policy_states": {slug: "UNCHANGED_LIVE_CONTENT" for slug in policies},
            "home_state": "UNCHANGED_LIVE_CONTENT",
            "pages_sha256": hashlib.sha256(pages_raw).hexdigest(),
            "page_body_sha256": {slug: page_hash for slug in policies},
            "baseline_page_sha256": {slug: page_hash for slug in policies + ["home"]},
        }
    )
    metadata = {
        "schema": "RAOS_WORDPRESS_MIXED_PREVIEW_SEED_METADATA_V1",
        "publication_profile": "verified-incremental",
        "publication_authority": False,
        "status": "VERIFIED_FIELDS_ONLY",
        "policy_states": binding["policy_states"],
        "home_state": binding["home_state"],
        "documents": {
            slug: {
                "production_slug": slug,
                "taxonomies": {
                    "category": [
                        {"id": 5, "name": "暮らしの道具", "slug": "tools", "parent": 0}
                    ]
                },
            }
            for slug in list(binding["article_states"]) + policies + ["home"]
        },
    }
    return _write_metadata(root, binding, metadata), metadata


def _write_metadata(root: Path, binding: dict, metadata: dict) -> Path:
    raw = json.dumps(metadata, ensure_ascii=False).encode()
    _private_write(root / "seed-metadata.v1.json", raw)
    binding["seed_metadata_sha256"] = hashlib.sha256(raw).hexdigest()
    return _rebind(root, binding)


@pytest.mark.parametrize("populated", [False, True])
def test_category_membership_comes_from_bound_saved_taxonomy(
    tmp_path: Path, populated: bool
) -> None:
    root, inventory, binding = _overlay(tmp_path)
    root, metadata = _category_metadata(root, inventory, binding)
    if populated:
        metadata["documents"]["guide-0"]["taxonomies"]["category"] = [
            {"id": 8, "name": "移動", "slug": "mobility", "parent": 0}
        ]
        root = _write_metadata(root, binding, metadata)
    result = loader.load_scope(root, inventory)
    assert result["category_expectations"] == {
        "seed_metadata_sha256": binding["seed_metadata_sha256"],
        "listings": [
            {
                "surface_id": "archive-category-mobility",
                "local_path": "/category/mobility/",
                "page_size": 3,
                "expected_article_ids": ["article-0"] if populated else [],
            }
        ],
    }
    assert "category_expectations" not in binding["incremental_scope"]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_metadata",
        "metadata_hash",
        "forged_binding_scope",
        "unknown_surface",
        "wrong_surface_path",
        "missing_category",
        "hierarchical",
        "unknown_term_fields",
        "conflicting_term",
        "duplicate_term",
        "wrong_document_slug",
    ],
)
def test_category_scope_refuses_missing_or_tampered_metadata(
    tmp_path: Path, mutation: str
) -> None:
    root, inventory, binding = _overlay(tmp_path)
    root, metadata = _category_metadata(root, inventory, binding)
    category = metadata["documents"]["guide-0"]["taxonomies"]["category"]
    if mutation == "missing_metadata":
        del binding["seed_metadata_sha256"]
    elif mutation == "metadata_hash":
        binding["seed_metadata_sha256"] = "f" * 64
    elif mutation == "forged_binding_scope":
        binding["incremental_scope"]["category_expectations"] = {"listings": []}
    elif mutation == "unknown_surface":
        inventory["local_surfaces"] = [_category_surface("invented")]
    elif mutation == "wrong_surface_path":
        inventory["local_surfaces"][0]["local_path"] = "/category/household/"
    elif mutation == "missing_category":
        del metadata["documents"]["guide-0"]["taxonomies"]["category"]
    elif mutation == "hierarchical":
        category[0]["parent"] = 1
    elif mutation == "unknown_term_fields":
        category[0]["invented"] = True
    elif mutation == "conflicting_term":
        category[0]["slug"] = "mobility"
    elif mutation == "duplicate_term":
        category.append(copy.deepcopy(category[0]))
    else:
        metadata["documents"]["guide-0"]["production_slug"] = "guide-1"
    if mutation not in {"missing_metadata", "metadata_hash", "forged_binding_scope"}:
        root = _write_metadata(root, binding, metadata)
    else:
        root = _rebind(root, binding)
    with pytest.raises(loader.ScopeFailure):
        loader.load_scope(root, inventory)


def _category_payload(total: int = 0) -> dict:
    scope = _scope()
    for index in range(2, 6):
        row = copy.deepcopy(scope["articles"][1])
        row["article_id"] = f"article-{index}"
        scope["articles"].append(row)
    article_ids = [row["article_id"] for row in scope["articles"]]
    scope["category_expectations"] = {
        "seed_metadata_sha256": "d" * 64,
        "listings": [
            {
                "surface_id": "archive-category-mobility",
                "local_path": "/category/mobility/",
                "page_size": 3,
                "expected_article_ids": article_ids[:total],
            }
        ],
    }
    return {
        "scope": scope,
        "article_ids": article_ids,
        "category_surfaces": [_category_surface()],
        "article_rows": [
            {"article_id": id_, "local_path": f"/{id_}/"} for id_ in article_ids
        ],
        "listing": {
            "listingBodyClass": True,
            "fullPostContentCount": 0,
            "listingCardCount": min(3, total),
            "listingCards": [
                {
                    "title_link_count": 1,
                    "local_origin": True,
                    "local_path": f"/{id_}/",
                    "search": "",
                    "hash": "",
                }
                for id_ in article_ids[: min(3, total)]
            ],
            "emptyStateCount": 0 if total else 1,
            "emptyStateTexts": []
            if total
            else ["この条件で公開中の記事はありません。"],
            "pagination": {
                "count": 2 if total > 3 else 0,
                "originMismatchCount": 0,
                "categoryPageNumbers": [2, 2] if total > 3 else [],
            },
        },
    }


@pytest.mark.parametrize("total", [0, 1, 2, 3, 4, 6])
def test_category_browser_requires_bound_set_and_correct_pagination(total: int) -> None:
    result = _node(_category_payload(total))
    assert result["valid"] is True
    assert result["listingFailed"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "omitted",
        "unknown_id",
        "duplicate",
        "wrong_path",
        "page_size",
        "extra",
        "no_hash",
    ],
)
def test_browser_rejects_forged_category_expectation(mutation: str) -> None:
    payload = _category_payload(2)
    expected = payload["scope"]["category_expectations"]
    row = expected["listings"][0]
    if mutation == "omitted":
        del payload["scope"]["category_expectations"]
    elif mutation == "unknown_id":
        row["expected_article_ids"] = ["unknown-article"]
    elif mutation == "duplicate":
        row["expected_article_ids"] = ["article-new", "article-new"]
    elif mutation == "wrong_path":
        row["local_path"] = "/category/household/"
    elif mutation == "page_size":
        row["page_size"] = 5
    elif mutation == "extra":
        expected["listings"].append(copy.deepcopy(row))
    else:
        del expected["seed_metadata_sha256"]
    assert _node(payload)["valid"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "empty_nonempty",
        "missing_card",
        "wrong_link",
        "duplicate_card",
        "external",
        "wrong_empty_text",
        "missing_next",
        "wrong_next",
        "extra_next",
        "full_body",
    ],
)
def test_category_browser_rejects_false_empty_wrong_members_and_broken_paging(
    mutation: str,
) -> None:
    payload = _category_payload(0 if mutation == "wrong_empty_text" else 4)
    listing = payload["listing"]
    if mutation == "empty_nonempty":
        listing.update(listingCardCount=0, listingCards=[], emptyStateCount=1)
    elif mutation == "missing_card":
        listing["listingCards"].pop()
        listing["listingCardCount"] -= 1
    elif mutation == "wrong_link":
        listing["listingCards"][0]["local_path"] = "/article-5/"
    elif mutation == "duplicate_card":
        listing["listingCards"][0] = copy.deepcopy(listing["listingCards"][1])
    elif mutation == "external":
        listing["listingCards"][0]["local_origin"] = False
    elif mutation == "wrong_empty_text":
        listing["emptyStateTexts"] = ["Nothing found"]
    elif mutation == "missing_next":
        listing["pagination"]["categoryPageNumbers"] = []
    elif mutation == "wrong_next":
        listing["pagination"]["categoryPageNumbers"] = [None]
    elif mutation == "extra_next":
        listing["pagination"]["categoryPageNumbers"] = [2, 3]
    else:
        listing["fullPostContentCount"] = 1
    assert _node(payload)["listingFailed"] is True


def test_legacy_category_empty_still_fails_and_seed_page_size_is_explicit() -> None:
    payload = _category_payload()
    payload.update(profile="legacy-full", scope=None)
    assert _node(payload)["listingFailed"] is True
    payload = _category_payload(2)
    payload.update(profile="legacy-full", scope=None)
    assert _node(payload)["listingFailed"] is False
    seed = (ROOT / "changes/wordpress-local-preview-v1/seed.php").read_text()
    assert "update_option('posts_per_page', 3);" in seed
    assert "categorySurfaces: localSurfaces.filter(" in AUDIT.read_text()
