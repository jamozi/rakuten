#!/usr/bin/env python3
"""Project Editorial V3 into the public-safe WordPress navigation contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import TYPE_CHECKING, Final, NoReturn

ROOT: Final = Path(__file__).resolve().parents[1]
if TYPE_CHECKING:
    # Static owner edge for the affected-generator dependency graph. Importing
    # only for type checking keeps this projection runnable under Python -S.
    from scripts import build_editorial_portfolio_v3 as editorial_v3_owner  # noqa: F401


PORTFOLIO: Final = ROOT / "changes/editorial-portfolio-v3/editorial-portfolio.v3.json"
NAVIGATION: Final = ROOT / "changes/editorial-portfolio-v3/generated/navigation.v3.json"
OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/editorial-navigation.v3.json"
)
OUTPUT_AUDIT_INVENTORY_PATH: Final = (
    ROOT / "changes/editorial-portfolio-v3/generated/wordpress-audit-inventory.v3.json"
)
OUTPUT_PATHS: Final = (OUTPUT, OUTPUT_AUDIT_INVENTORY_PATH)
TEST_PATHS: Final = (
    Path("tests/st1704"),
    Path("tests/wordpress_local_preview"),
)
MAX_INPUT_BYTES: Final = 2 * 1024 * 1024
MAX_OUTPUT_BYTES: Final = 256 * 1024
SLUG_RE: Final = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CODE_RE: Final = re.compile(r"^a[0-9]{2}$")
CONTENT_ROLE_LABELS: Final = {
    "brand_family_comparison": "ブランド内比較",
    "category_guide": "選び方",
    "constraint_shortlist": "条件別比較",
    "feature_shortlist": "機能別比較",
    "head_to_head_comparison": "2製品比較",
    "head_to_head_with_reference": "2製品比較＋参考機種",
    "lifecycle_status_route": "旧製品の販売状態確認＋現行比較への案内",
    "model_family_comparison": "ブランド内比較",
}
AUDIT_VIEWPORTS: Final = (360, 390, 768, 1440)
AUDIT_POLICY_SLUGS: Final = (
    "about-ad-policy",
    "comparison-policy",
    "privacy-policy",
)
AUDIT_LOCAL_SURFACES: Final = (
    {
        "expected_canonical": "ABSENT",
        "expected_http_status": 200,
        "expected_page_number": None,
        "expected_search_query": "",
        "expected_state": "EMPTY_QUERY",
        "expected_ui_text": [
            "検索結果",
            "商品名や条件を入力して、比較ガイドを検索できます。",
            "検索語を入力してください",
        ],
        "kind": "search",
        "local_path": "/?s=",
        "route_class": "SEARCH_EMPTY_QUERY",
        "surface_id": "search-empty-query",
    },
    {
        "expected_canonical": "ABSENT",
        "expected_http_status": 200,
        "expected_page_number": None,
        "expected_search_query": "",
        "expected_state": "WHITESPACE_QUERY",
        "expected_ui_text": [
            "検索結果",
            "商品名や条件を入力して、比較ガイドを検索できます。",
            "検索語を入力してください",
        ],
        "kind": "search",
        "local_path": "/?s=%20%20%20",
        "route_class": "SEARCH_WHITESPACE_QUERY",
        "surface_id": "search-whitespace-query",
    },
    {
        "expected_canonical": "ABSENT",
        "expected_http_status": 200,
        "expected_page_number": None,
        "expected_search_query": "ロボット",
        "expected_state": "RESULTS_PRESENT",
        "expected_ui_text": ["検索結果", "「ロボット」に一致する記事："],
        "kind": "search",
        "local_path": "/?s=%E3%83%AD%E3%83%9C%E3%83%83%E3%83%88",
        "route_class": "SEARCH_RESULTS",
        "surface_id": "search-results",
    },
    {
        "expected_canonical": "ABSENT",
        "expected_http_status": 200,
        "expected_page_number": None,
        "expected_search_query": "raos-no-result-20260831",
        "expected_state": "NO_RESULTS",
        "expected_ui_text": [
            "検索結果",
            "「raos-no-result-20260831」に一致する記事：0件",
            "一致する記事はありません",
        ],
        "kind": "search",
        "local_path": "/?s=raos-no-result-20260831",
        "route_class": "SEARCH_NO_RESULTS",
        "surface_id": "search-no-results",
    },
    {
        "expected_canonical": "ABSENT",
        "expected_http_status": 200,
        "expected_page_number": None,
        "expected_search_query": "<script>alert(1)</script>",
        "expected_state": "HOSTILE_QUERY_ESCAPED",
        "expected_ui_text": [
            "「<script>alert(1)</script>」に一致する記事：0件",
            "一致する記事はありません",
        ],
        "kind": "search",
        "local_path": "/?s=%3Cscript%3Ealert%281%29%3C%2Fscript%3E",
        "route_class": "SEARCH_HOSTILE_QUERY",
        "surface_id": "search-hostile-query",
    },
    {
        "expected_canonical": "ABSENT",
        "expected_http_status": 200,
        "expected_page_number": 2,
        "expected_search_query": "比較",
        "expected_state": "PAGED_RESULTS",
        "expected_ui_text": ["検索結果", "「比較」に一致する記事：", "前のページ"],
        "kind": "search",
        "local_path": "/?s=%E6%AF%94%E8%BC%83&paged=2",
        "route_class": "SEARCH_PAGED_RESULTS",
        "surface_id": "search-results-page-2",
    },
    {
        "archive_type": "category",
        "expected_canonical": "ABSENT",
        "expected_http_status": 200,
        "expected_state": "EXCERPT_LIST",
        "expected_ui_text": ["移動の記事", "比較ガイド一覧"],
        "kind": "archive",
        "local_path": "/category/mobility/",
        "route_class": "ARCHIVE_CATEGORY",
        "surface_id": "archive-category-mobility",
    },
    {
        "archive_type": "category",
        "expected_canonical": "ABSENT",
        "expected_http_status": 200,
        "expected_state": "EXCERPT_LIST",
        "expected_ui_text": ["家事の記事", "比較ガイド一覧"],
        "kind": "archive",
        "local_path": "/category/household/",
        "route_class": "ARCHIVE_CATEGORY",
        "surface_id": "archive-category-household",
    },
    {
        "archive_type": "category",
        "expected_canonical": "ABSENT",
        "expected_http_status": 200,
        "expected_state": "EXCERPT_LIST",
        "expected_ui_text": ["備えの記事", "比較ガイド一覧"],
        "kind": "archive",
        "local_path": "/category/preparedness/",
        "route_class": "ARCHIVE_CATEGORY",
        "surface_id": "archive-category-preparedness",
    },
    {
        "archive_type": "date",
        "expected_canonical": "ABSENT",
        "expected_http_status": 200,
        "expected_state": "EXCERPT_LIST",
        "expected_ui_text": ["2026年8月", "比較ガイド一覧"],
        "kind": "archive",
        "local_path": "/2026/08/",
        "route_class": "ARCHIVE_DATE",
        "surface_id": "archive-date-2026-08",
    },
    {
        "archive_type": "author",
        "expected_canonical": "ABSENT",
        "expected_http_status": 200,
        "expected_state": "EXCERPT_LIST",
        "expected_ui_text": ["執筆者別の記事", "比較ガイド一覧"],
        "kind": "archive",
        "local_path": "/author/raos-local-admin/",
        "route_class": "ARCHIVE_AUTHOR",
        "surface_id": "archive-author-local-admin",
    },
    {
        "expected_canonical": "ABSENT",
        "expected_http_status": 404,
        "expected_state": "NOT_FOUND",
        "expected_ui_text": ["ページが見つかりませんでした", "ホームへ戻る"],
        "kind": "not_found",
        "local_path": "/local-preview-page-not-found/",
        "route_class": "NOT_FOUND",
        "surface_id": "not-found",
    },
)
AUDIT_ROUTE_COVERAGE: Final = {
    "archive_types": [
        {
            "archive_type": "category",
            "reason": None,
            "reason_code": None,
            "status": "APPLICABLE",
            "surface_ids": [
                "archive-category-mobility",
                "archive-category-household",
                "archive-category-preparedness",
            ],
        },
        {
            "archive_type": "date",
            "reason": None,
            "reason_code": None,
            "status": "APPLICABLE",
            "surface_ids": ["archive-date-2026-08"],
        },
        {
            "archive_type": "author",
            "reason": None,
            "reason_code": None,
            "status": "APPLICABLE",
            "surface_ids": ["archive-author-local-admin"],
        },
        {
            "archive_type": "tag",
            "reason": "The closed ten-post fixture assigns no tag terms.",
            "reason_code": "NO_SEEDED_TAG_TERMS",
            "status": "NOT_APPLICABLE",
            "surface_ids": [],
        },
        {
            "archive_type": "post_type",
            "reason": "The seed exposes no public custom post type with has_archive enabled.",
            "reason_code": "NO_PUBLIC_HAS_ARCHIVE_POST_TYPE",
            "status": "NOT_APPLICABLE",
            "surface_ids": [],
        },
    ],
    "robots_profile": {
        "local_observed_policy": "FORCED_ALL_NOINDEX_NOFOLLOW_NOARCHIVE_NOSNIPPET",
        "local_profile_id": "LOCAL_PREVIEW",
        "production_expected_not_found": "noindex, nofollow",
        "production_expected_search_archive": "noindex, follow",
        "production_robots_evidence": False,
    },
}
PRESENTATION: Final = {
    "household": {
        "anchor": "cluster-home",
        "description": "置き場所と手間から、無理のない一台を選ぶ。",
        "heading": "置き場所と日々の手間を整える",
        "label": "家事",
    },
    "mobility": {
        "anchor": "cluster-mobility",
        "description": "軽さ、容量、持ち運び方の違いをほどく。",
        "heading": "持ち運ぶ負担を小さくする",
        "label": "移動",
    },
    "preparedness": {
        "anchor": "cluster-ready",
        "description": "必要な容量と出力を、使う場面から逆算する。",
        "heading": "必要な電力を過不足なく備える",
        "label": "備え",
    },
}


class NavigationBuildFailure(RuntimeError):
    """Stable projection refusal."""


def _fail() -> NoReturn:
    raise NavigationBuildFailure("EDITORIAL_V3_THEME_NAVIGATION_INVALID") from None


def _read_json(path: Path) -> tuple[dict[str, object], bytes]:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        _fail()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or metadata.st_size > MAX_INPUT_BYTES
        or len(payload) != metadata.st_size
    ):
        _fail()
    try:
        decoded = json.loads(payload)
    except UnicodeDecodeError, json.JSONDecodeError:
        _fail()
    if type(decoded) is not dict:
        _fail()
    return decoded, payload


def _canonical(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except TypeError, ValueError:
        _fail()


def build_documents() -> tuple[bytes, bytes]:
    portfolio, portfolio_bytes = _read_json(PORTFOLIO)
    navigation, navigation_bytes = _read_json(NAVIGATION)
    if (
        portfolio.get("schema") != "RAOS_EDITORIAL_PORTFOLIO_V3"
        or navigation.get("schema") != "RAOS_EDITORIAL_NAVIGATION_V3"
        or portfolio.get("target_origin") != "https://kurashinoshirube.com"
        or navigation.get("target_origin") != "https://kurashinoshirube.com"
        or type(portfolio.get("articles")) is not list
        or type(navigation.get("articles")) is not list
        or type(navigation.get("clusters")) is not list
        or len(portfolio["articles"]) != 10
        or len(navigation["articles"]) != 10
        or len(navigation["clusters"]) != 3
    ):
        _fail()

    portfolio_by_id: dict[str, dict[str, object]] = {}
    for raw in portfolio["articles"]:
        if type(raw) is not dict:
            _fail()
        article_id = raw.get("article_id")
        local_slug = raw.get("local_slug")
        production_slug = raw.get("production_slug")
        article_code = raw.get("article_code")
        intent_group_id = raw.get("intent_group_id")
        content_role = raw.get("content_role")
        content_role_label = raw.get("content_role_label")
        primary_query_intent = raw.get("primary_query_intent")
        comparison_scope = raw.get("comparison_scope")
        broader_article_id = raw.get("broader_article_id")
        if (
            type(article_id) is not str
            or article_id in portfolio_by_id
            or type(local_slug) is not str
            or not local_slug.startswith("local-preview-")
            or type(production_slug) is not str
            or SLUG_RE.fullmatch(production_slug) is None
            or local_slug != f"local-preview-{production_slug}"
            or type(article_code) is not str
            or CODE_RE.fullmatch(article_code) is None
            or type(intent_group_id) is not str
            or SLUG_RE.fullmatch(intent_group_id) is None
            or type(content_role) is not str
            or CONTENT_ROLE_LABELS.get(content_role) != content_role_label
            or type(primary_query_intent) is not str
            or primary_query_intent.strip() != primary_query_intent
            or not primary_query_intent
            or len(primary_query_intent) > 180
            or type(comparison_scope) is not str
            or not comparison_scope.strip()
            or len(comparison_scope) > 120
            or (broader_article_id is not None and type(broader_article_id) is not str)
        ):
            _fail()
        portfolio_by_id[article_id] = raw
    for intent_group_id in {
        str(row["intent_group_id"]) for row in portfolio_by_id.values()
    }:
        query_intents = [
            str(row["primary_query_intent"])
            for row in portfolio_by_id.values()
            if row["intent_group_id"] == intent_group_id
        ]
        if len(query_intents) != len(set(query_intents)):
            _fail()
    for article_id, raw in portfolio_by_id.items():
        broader_article_id = raw.get("broader_article_id")
        if broader_article_id is None:
            continue
        broader = portfolio_by_id.get(broader_article_id)
        if (
            broader is None
            or broader_article_id == article_id
            or broader.get("intent_group_id") != raw.get("intent_group_id")
            or broader.get("content_role")
            not in {"category_guide", "constraint_shortlist"}
        ):
            _fail()

    projected_articles: list[dict[str, object]] = []
    seen_codes: set[str] = set()
    seen_slugs: set[str] = set()
    for raw in navigation["articles"]:
        if type(raw) is not dict:
            _fail()
        article_id = raw.get("article_id")
        source = portfolio_by_id.get(article_id) if type(article_id) is str else None
        related = raw.get("related_articles")
        if (
            source is None
            or type(related) is not list
            or len(related) < 1
            or raw.get("article_code") != source.get("article_code")
            or raw.get("production_slug") != source.get("production_slug")
            or raw.get("cluster_id") != source.get("cluster_id")
            or raw.get("intent_group_id") != source.get("intent_group_id")
            or raw.get("content_role") != source.get("content_role")
            or raw.get("content_role_label") != source.get("content_role_label")
            or raw.get("primary_query_intent") != source.get("primary_query_intent")
            or raw.get("comparison_scope") != source.get("comparison_scope")
            or raw.get("broader_article_id") != source.get("broader_article_id")
            or raw.get("category_label") != source.get("category_label")
            or type(raw.get("home_order")) is not int
            or type(raw.get("title")) is not str
        ):
            _fail()
        code = source["article_code"]
        slug = source["production_slug"]
        if code in seen_codes or slug in seen_slugs:
            _fail()
        seen_codes.add(code)
        seen_slugs.add(slug)
        related_ids: set[str] = set()
        projected_related: list[dict[str, str]] = []
        for relation in related:
            if type(relation) is not dict:
                _fail()
            related_id = relation.get("article_id")
            related_source = (
                portfolio_by_id.get(related_id) if type(related_id) is str else None
            )
            relationship = relation.get("relationship")
            expected_relationship = (
                "broader_guide"
                if source.get("broader_article_id") == related_id
                else (
                    "narrower_comparison"
                    if related_source is not None
                    and related_source.get("broader_article_id") == article_id
                    else "adjacent_condition"
                )
            )
            expected_context = {
                "adjacent_condition": "近い条件を別の軸で比べる",
                "broader_guide": "候補を広げて選び直す",
                "narrower_comparison": "条件を絞った比較へ進む",
            }[expected_relationship]
            if (
                related_source is None
                or related_id == article_id
                or related_id in related_ids
                or relationship != expected_relationship
                or relation.get("context") != expected_context
                or related_source.get("intent_group_id")
                != source.get("intent_group_id")
            ):
                _fail()
            related_ids.add(related_id)
            projected_related.append(
                {
                    "article_id": related_id,
                    "relationship": relationship,
                }
            )
        if not 1 <= len(projected_related) <= 2:
            _fail()
        projected_articles.append(
            {
                "article_code": code,
                "article_id": article_id,
                "category_label": source["category_label"],
                "cluster_id": source["cluster_id"],
                "intent_group_id": source["intent_group_id"],
                "content_role": source["content_role"],
                "content_role_label": source["content_role_label"],
                "primary_query_intent": source["primary_query_intent"],
                "comparison_scope": source["comparison_scope"],
                "broader_article_id": source["broader_article_id"],
                "home_order": raw["home_order"],
                "local_slug": source["local_slug"],
                "production_slug": slug,
                "related_articles": projected_related,
                "snapshot_id": source["snapshot_id"],
                "title": raw["title"],
            }
        )

    projected_by_id = {
        str(article["article_id"]): article for article in projected_articles
    }
    for article_id, article in projected_by_id.items():
        broader_article_id = article["broader_article_id"]
        if broader_article_id is None:
            continue
        relations = article["related_articles"]
        broader = projected_by_id.get(str(broader_article_id))
        if type(relations) is not list or type(broader) is not dict:
            _fail()
        reciprocal = broader["related_articles"]
        if (
            type(reciprocal) is not list
            or not any(
                type(row) is dict
                and row.get("article_id") == broader_article_id
                and row.get("relationship") == "broader_guide"
                for row in relations
            )
            or not any(
                type(row) is dict
                and row.get("article_id") == article_id
                and row.get("relationship") == "narrower_comparison"
                for row in reciprocal
            )
        ):
            _fail()

    clusters: list[dict[str, object]] = []
    membership: list[str] = []
    for raw in navigation["clusters"]:
        if type(raw) is not dict:
            _fail()
        cluster_id = raw.get("cluster_id")
        article_ids = raw.get("article_ids")
        presentation = PRESENTATION.get(cluster_id) if type(cluster_id) is str else None
        if (
            presentation is None
            or type(article_ids) is not list
            or not article_ids
            or any(type(value) is not str for value in article_ids)
            or len(set(article_ids)) != len(article_ids)
            or raw.get("category_label") != presentation["label"]
            or type(raw.get("home_order")) is not int
        ):
            _fail()
        for article_id in article_ids:
            source = portfolio_by_id.get(article_id)
            if source is None or source.get("cluster_id") != cluster_id:
                _fail()
        membership.extend(article_ids)
        clusters.append(
            {
                "article_ids": article_ids,
                "cluster_id": cluster_id,
                "home_order": raw["home_order"],
                **presentation,
            }
        )
    if sorted(membership) != sorted(portfolio_by_id):
        _fail()
    projected_articles.sort(key=lambda row: str(row["article_code"]))
    clusters.sort(key=lambda row: int(row["home_order"]))
    output: dict[str, object] = {
        "articles": projected_articles,
        "clusters": clusters,
        "schema": "RAOS_EDITORIAL_THEME_NAVIGATION_V3",
        "source_navigation_sha256": hashlib.sha256(navigation_bytes).hexdigest(),
        "source_portfolio_sha256": hashlib.sha256(portfolio_bytes).hexdigest(),
        "target_origin": "https://kurashinoshirube.com",
        "version": "3.0.0",
    }
    article_by_id = {
        str(article["article_id"]): article for article in projected_articles
    }
    cluster_by_id = {str(cluster["cluster_id"]): cluster for cluster in clusters}
    audit_surfaces: list[dict[str, object]] = [
        {
            "kind": "home",
            "local_path": "/",
            "production_path": "/",
            "surface_id": "home",
        }
    ]
    for article in projected_articles:
        related = article["related_articles"]
        if type(related) is not list:
            _fail()
        contextual = next(
            (relation["article_id"] for relation in related if type(relation) is dict),
            None,
        )
        if type(contextual) is not str:
            _fail()
        terminal_related = [
            relation["article_id"]
            for relation in related
            if type(relation) is dict and relation.get("article_id") != contextual
        ]
        cluster = cluster_by_id.get(str(article["cluster_id"]))
        if len(terminal_related) > 1 or type(cluster) is not dict:
            _fail()
        audit_surfaces.append(
            {
                "article_id": article["article_id"],
                "cluster_anchor": cluster["anchor"],
                "cluster_id": article["cluster_id"],
                "intent_group_id": article["intent_group_id"],
                "content_role": article["content_role"],
                "content_role_label": article["content_role_label"],
                "primary_query_intent": article["primary_query_intent"],
                "comparison_scope": article["comparison_scope"],
                "broader_article_id": article["broader_article_id"],
                "contextual_article_id": contextual,
                "kind": "article",
                "local_path": f"/{article['local_slug']}/",
                "production_path": f"/{article['production_slug']}/",
                "related_article_ids": terminal_related,
                "surface_id": f"article-{article['article_code']}",
            }
        )
    audit_surfaces.extend(
        {
            "kind": "policy",
            "local_path": f"/{slug}/",
            "production_path": f"/{slug}/",
            "surface_id": f"policy-{slug}",
        }
        for slug in AUDIT_POLICY_SLUGS
    )
    audit_clusters = []
    for cluster in clusters:
        article_ids = cluster["article_ids"]
        if type(article_ids) is not list or any(
            article_id not in article_by_id for article_id in article_ids
        ):
            _fail()
        audit_clusters.append(
            {
                "anchor": cluster["anchor"],
                "article_ids": article_ids,
                "cluster_id": cluster["cluster_id"],
            }
        )
    audit_inventory = {
        "clusters": audit_clusters,
        "local_surfaces": list(AUDIT_LOCAL_SURFACES),
        "route_coverage": AUDIT_ROUTE_COVERAGE,
        "schema": "RAOS_WORDPRESS_AUDIT_INVENTORY_V3",
        "source_navigation_sha256": hashlib.sha256(navigation_bytes).hexdigest(),
        "source_portfolio_sha256": hashlib.sha256(portfolio_bytes).hexdigest(),
        "surfaces": audit_surfaces,
        "target_origin": "https://kurashinoshirube.com",
        "version": "3.0.0",
        "viewports": list(AUDIT_VIEWPORTS),
    }
    payload = _canonical(output)
    audit_payload = _canonical(audit_inventory)
    if len(payload) > MAX_OUTPUT_BYTES or len(audit_payload) > MAX_OUTPUT_BYTES:
        _fail()
    return payload, audit_payload


def build() -> bytes:
    """Retain the historical single-navigation builder API for consumers."""

    return build_documents()[0]


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        payloads = build_documents()
        if arguments.check:
            for path, payload in zip(OUTPUT_PATHS, payloads, strict=True):
                if path.read_bytes() != payload or path.is_symlink():
                    _fail()
        else:
            for path, payload in zip(OUTPUT_PATHS, payloads, strict=True):
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
                descriptor = os.open(
                    temporary,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                    0o644,
                )
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
    except NavigationBuildFailure, OSError:
        print("EDITORIAL_V3_THEME_NAVIGATION_INVALID", file=os.sys.stderr)
        return 1
    print(
        "EDITORIAL_V3_THEME_NAVIGATION_OK sha256="
        + hashlib.sha256(payloads[0]).hexdigest()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
