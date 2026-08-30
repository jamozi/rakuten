from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/raos_wordpress_publication_request.py"
SPEC = importlib.util.spec_from_file_location("wordpress_publication_request", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
publication = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = publication
SPEC.loader.exec_module(publication)
ORIGINAL_VERIFY_PUBLIC_PAGES = publication.verify_public_pages
ORIGINAL_TRACKED_THEME_TREE_SHA256 = publication.tracked_theme_tree_sha256
TEST_THEME_TREE_SHA256 = "1" * 64


@pytest.fixture(autouse=True)
def no_live_public_readback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        publication,
        "verify_public_pages",
        lambda articles, **_kwargs: {
            article.production_slug: {
                "url": f"{publication.ORIGIN}/{article.production_slug}/",
                "status": 200,
            }
            for article in articles
        },
    )
    # The shared integration worktree intentionally contains the candidate
    # 1.3.10 theme. Workflow unit tests use a stable reviewed tree while the
    # production function continues to refuse dirty theme sources.
    monkeypatch.setattr(
        publication,
        "tracked_theme_tree_sha256",
        lambda: TEST_THEME_TREE_SHA256,
    )


class _PublicResponse:
    def __init__(
        self,
        url: str,
        payload: str | bytes,
        *,
        headers: dict[str, str] | None = None,
        status: int = 200,
        final_url: str | None = None,
    ) -> None:
        self._url = url
        self._final_url = final_url or url
        self._payload = payload.encode("utf-8") if isinstance(payload, str) else payload
        self._status = status
        self.headers = {
            "Content-Type": "text/html; charset=UTF-8",
            **(headers or {}),
        }

    def __enter__(self) -> _PublicResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def getcode(self) -> int:
        return self._status

    def geturl(self) -> str:
        return self._final_url

    def read(self, maximum: int) -> bytes:
        return self._payload[:maximum]


class _PublicOpener:
    def __init__(
        self,
        response: _PublicResponse,
        *,
        stylesheet_responses: dict[str, _PublicResponse] | None = None,
    ) -> None:
        self.response = response
        self.stylesheet_responses = stylesheet_responses or {}
        self.requests: list[object] = []

    def open(self, request: object, timeout: int) -> _PublicResponse:
        assert timeout == 30
        self.requests.append(request)
        url = request.full_url
        if url == self.response._url:
            return self.response
        explicit = self.stylesheet_responses.get(url)
        if explicit is not None:
            return explicit
        parsed = publication.urlsplit(url)
        if parsed.path.endswith("/assets/theme.css"):
            asset = "assets/theme.css"
        elif parsed.path.endswith("/assets/editorial-v2.css"):
            asset = "assets/editorial-v2.css"
        elif parsed.path.startswith(publication.AUTOPTIMIZE_SINGLE_STYLESHEET_PREFIX):
            asset = (
                "assets/theme.css"
                if f"_{'a' * 32}.php" in parsed.path
                else "assets/editorial-v2.css"
            )
        else:
            raise AssertionError(f"unexpected public request: {url}")
        property_name = publication.THEME_RUNTIME_SENTINEL_PROPERTIES[asset]
        return _PublicResponse(
            url,
            ":root{" + property_name + ":"
            + publication.EXPECTED_THEME_RUNTIME_REVISION
            + ";}",
            headers={"Content-Type": "text/css; charset=UTF-8"},
        )


def _public_markup(
    article: Any,
    *,
    head_extra: str = "",
    block_markup: str | None = None,
    stylesheets: str | None = None,
    footer_markup: str = "<footer><h2>暮らしのしるべ</h2></footer>",
) -> str:
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    stylesheet_markup = stylesheets
    if stylesheet_markup is None:
        stylesheet_markup = (
            '<link rel="stylesheet" href="/wp-content/themes/'
            'kurashinoshirube-child/assets/theme.css?ver=1.3.10">'
            '<link rel="stylesheet" href="/wp-content/themes/'
            'kurashinoshirube-child/assets/editorial-v2.css?ver=1.3.10">'
        )
    return (
        "<!doctype html><html><head><title>"
        + article.title
        + " | 暮らしのしるべ</title>"
        + stylesheet_markup
        + '<link rel="canonical" href="'
        + url
        + '">'
        + head_extra
        + "</head><body><main><h1>"
        + article.title
        + "</h1>"
        + (article.block_markup if block_markup is None else block_markup)
        + "</main>"
        + footer_markup
        + "</body></html>"
    )


def _stylesheet_links(*hrefs: str) -> str:
    return "".join(
        f'<link rel="stylesheet" href="{href.replace("&", "&amp;")}">' for href in hrefs
    )


def test_anonymous_public_readback_requires_exact_canonical_title_and_headings() -> (
    None
):
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    markup = _public_markup(article)
    opener = _PublicOpener(_PublicResponse(url, markup))

    evidence = ORIGINAL_VERIFY_PUBLIC_PAGES(
        [article],
        attempts=1,
        sleeper=lambda seconds: None,
        opener=opener,
    )

    assert evidence[article.production_slug]["canonical_url"] == url
    assert evidence[article.production_slug]["heading_count"] >= 1
    request = opener.requests[0]
    assert request.full_url == url
    assert request.get_header("Authorization") is None


@pytest.mark.parametrize(
    "stylesheets",
    [
        _stylesheet_links(
            "https://example.invalid/unrelated.css?build=42",
            f"{publication.ORIGIN}/wp-content/themes/kurashinoshirube-child/"
            "assets/theme.css?ver=1.3.10",
            f"{publication.ORIGIN}/wp-content/themes/kurashinoshirube-child/"
            "assets/editorial-v2.css?ver=1.3.10",
        ),
        _stylesheet_links(
            "https://example.invalid/unrelated.css?build=42",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver=1.3.10",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver=1.3.10",
        ),
        _stylesheet_links(
            "https://example.invalid/unrelated.css?build=42",
            "/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver=1.3.10",
            "/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver=1.3.10",
        ),
    ],
    ids=(
        "absolute-direct-theme-assets",
        "autoptimize-single-assets",
        "root-relative-autoptimize-single-assets",
    ),
)
def test_public_readback_accepts_exact_theme_stylesheet_materializations(
    stylesheets: str,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"

    evidence = ORIGINAL_VERIFY_PUBLIC_PAGES(
        [article],
        attempts=1,
        sleeper=lambda seconds: None,
        opener=_PublicOpener(
            _PublicResponse(url, _public_markup(article, stylesheets=stylesheets))
        ),
    )

    page = evidence[article.production_slug]
    assert page["theme_version"] == "1.3.10"
    assert page["theme_runtime_revision"] == (
        publication.EXPECTED_THEME_RUNTIME_REVISION
    )
    stylesheet_evidence = page["theme_stylesheets"]
    assert [row["asset"] for row in stylesheet_evidence] == [
        "assets/editorial-v2.css",
        "assets/theme.css",
    ]
    assert all(
        publication.SHA256_RE.fullmatch(row["content_sha256"])
        and row["bytes"] > 0
        and row["runtime_revision"]
        == publication.EXPECTED_THEME_RUNTIME_REVISION
        for row in stylesheet_evidence
    )


def _runtime_css(asset: str, *, revision: str | None = None) -> str:
    return (
        ":root{"
        + publication.THEME_RUNTIME_SENTINEL_PROPERTIES[asset]
        + ":"
        + (revision or publication.EXPECTED_THEME_RUNTIME_REVISION)
        + ";}"
    )


@pytest.mark.parametrize(
    ("payload", "headers", "status", "final_url"),
    [
        (_runtime_css("assets/theme.css"), {"Content-Type": "text/css"}, 503, None),
        (
            _runtime_css("assets/theme.css"),
            {"Content-Type": "application/javascript"},
            200,
            None,
        ),
        (_runtime_css("assets/theme.css"), {"Content-Type": "text/css"}, 200, "redirect"),
        (b"", {"Content-Type": "text/css"}, 200, None),
        (b"\xff", {"Content-Type": "text/css"}, 200, None),
        (
            b"a" * (publication.MAX_PUBLIC_STYLESHEET_BYTES + 1),
            {"Content-Type": "text/css"},
            200,
            None,
        ),
        (
            _runtime_css("assets/theme.css", revision="0" * 64),
            {"Content-Type": "text/css"},
            200,
            None,
        ),
        (
            _runtime_css("assets/theme.css") * 2,
            {"Content-Type": "text/css"},
            200,
            None,
        ),
        (
            _runtime_css("assets/theme.css")
            + _runtime_css("assets/editorial-v2.css"),
            {"Content-Type": "text/css"},
            200,
            None,
        ),
        (
            _runtime_css("assets/editorial-v2.css"),
            {"Content-Type": "text/css"},
            200,
            None,
        ),
    ],
    ids=(
        "wrong-status",
        "wrong-content-type",
        "redirected",
        "empty",
        "invalid-utf8",
        "oversize",
        "stale-revision",
        "duplicate-sentinel",
        "combined-sentinels",
        "wrong-direct-asset",
    ),
)
def test_public_readback_rejects_invalid_fetched_stylesheet_evidence(
    payload: str | bytes,
    headers: dict[str, str],
    status: int,
    final_url: str | None,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    page_url = f"{publication.ORIGIN}/{article.production_slug}/"
    stylesheet_url = (
        f"{publication.ORIGIN}/wp-content/themes/kurashinoshirube-child/"
        "assets/theme.css?ver=1.3.10"
    )
    response_final_url = (
        f"{publication.ORIGIN}/redirected.css"
        if final_url == "redirect"
        else stylesheet_url
    )
    opener = _PublicOpener(
        _PublicResponse(page_url, _public_markup(article)),
        stylesheet_responses={
            stylesheet_url: _PublicResponse(
                stylesheet_url,
                payload,
                headers=headers,
                status=status,
                final_url=response_final_url,
            )
        },
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=opener,
        )


def test_public_stylesheet_fetch_is_cached_once_per_url_per_readback() -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    page_url = f"{publication.ORIGIN}/{article.production_slug}/"
    opener = _PublicOpener(_PublicResponse(page_url, _public_markup(article)))

    ORIGINAL_VERIFY_PUBLIC_PAGES(
        [article, article],
        attempts=1,
        sleeper=lambda seconds: None,
        opener=opener,
    )

    requested_urls = [request.full_url for request in opener.requests]
    assert requested_urls.count(page_url) == 2
    assert len(requested_urls) == 4
    assert len(set(requested_urls) - {page_url}) == 2


@pytest.mark.parametrize(
    "footer_markup",
    [
        "",
        "<footer><h3>暮らしのしるべ</h3></footer>",
        "<footer><h2>別のサイト名</h2></footer>",
        "<footer><h2>暮らしのしるべ</h2><h2>暮らしのしるべ</h2></footer>",
        "<footer><h2>暮らしのしるべ</h2><h3>追加見出し</h3></footer>",
        "<footer><h3>追加見出し</h3><h2>暮らしのしるべ</h2></footer>",
    ],
    ids=(
        "missing",
        "wrong-level",
        "wrong-copy",
        "duplicate",
        "not-trailing",
        "extra-before-footer",
    ),
)
def test_public_readback_requires_one_exact_trailing_site_footer_heading(
    footer_markup: str,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(
                _PublicResponse(
                    url,
                    _public_markup(article, footer_markup=footer_markup),
                )
            ),
        )


@pytest.mark.parametrize(
    "stylesheets",
    [
        _stylesheet_links(
            "/wp-content/themes/kurashinoshirube-child/assets/theme.css?ver=1.3.10",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver=1.3.10",
        ),
        _stylesheet_links(
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver=1.3.10",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver=1.3.10",
        ),
        _stylesheet_links(
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'A' * 32}.php?ver=1.3.10",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver=1.3.10",
        ),
        _stylesheet_links(
            "http://kurashinoshirube.com/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver=1.3.10",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver=1.3.10",
        ),
        _stylesheet_links(
            "https://user@kurashinoshirube.com/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver=1.3.10",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver=1.3.10",
        ),
        _stylesheet_links(
            "https://kurashinoshirube.com:443/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver=1.3.10",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver=1.3.10",
        ),
        _stylesheet_links(
            "https://example.invalid/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver=1.3.10",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver=1.3.10",
        ),
        _stylesheet_links(
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver=1.3.10#fragment",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver=1.3.10",
        ),
        _stylesheet_links(
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver=1.3.10&extra=1",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver=1.3.10",
        ),
        _stylesheet_links(
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver=1.3.10",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver=1.3.10",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'c' * 32}.php?ver=1.3.10",
        ),
        _stylesheet_links(
            "/wp-content/themes/kurashinoshirube-child/assets/theme.css?ver=1.3.10&extra=1",
            "/wp-content/themes/kurashinoshirube-child/assets/editorial-v2.css?ver=1.3.10",
        ),
    ],
    ids=(
        "mixed-direct-and-autoptimize",
        "duplicate-autoptimize-hash",
        "uppercase-autoptimize-hash",
        "http-autoptimize-url",
        "userinfo-autoptimize-url",
        "port-autoptimize-url",
        "cross-origin-autoptimize-url",
        "fragment-autoptimize-url",
        "extra-query-autoptimize-url",
        "third-autoptimize-url",
        "extra-query-direct-url",
    ),
)
def test_public_readback_rejects_invalid_theme_stylesheet_materialization(
    stylesheets: str,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(
                _PublicResponse(url, _public_markup(article, stylesheets=stylesheets))
            ),
        )


def test_anonymous_public_readback_rejects_noindex() -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    markup = _public_markup(
        article,
        head_extra='<meta name="robots" content="noindex, follow">',
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(_PublicResponse(url, markup)),
        )


@pytest.mark.parametrize(
    ("meta_content", "response_headers"),
    [
        ("follow noindex noarchive", {}),
        ("follow; NONE", {}),
        (None, {"x-robots-tag": "googlebot: noindex, follow"}),
        (None, {"X-Robots-Tag": "none"}),
    ],
)
def test_anonymous_public_readback_rejects_all_noindex_marker_forms(
    meta_content: str | None,
    response_headers: dict[str, str],
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    meta = f'<meta name="robots" content="{meta_content}">' if meta_content else ""
    markup = _public_markup(article, head_extra=meta)
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(
                _PublicResponse(url, markup, headers=response_headers)
            ),
        )


def test_anonymous_public_readback_rejects_googlebot_noindex_meta() -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    markup = _public_markup(
        article,
        head_extra='<meta name="googlebot" content="follow noindex">',
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(_PublicResponse(url, markup)),
        )


def test_anonymous_public_readback_rejects_cta_identity_or_theme_drift() -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    tampered_cta, replacements = re.subn(
        r'(<a\b[^>]*href=")[^"]+("[^>]*data-raos-placement=)',
        r"\1https://example.invalid/wrong-product\2",
        article.block_markup,
        count=1,
    )
    assert replacements == 1
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_(CTA_INVALID|READBACK_FAILED)",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(
                _PublicResponse(url, _public_markup(article, block_markup=tampered_cta))
            ),
        )

    wrong_theme = _public_markup(article).replace("?ver=1.3.10", "?ver=1.3.8")
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(_PublicResponse(url, wrong_theme)),
        )


def test_authenticated_public_readback_sends_only_the_supplied_basic_header() -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    opener = _PublicOpener(_PublicResponse(url, _public_markup(article)))

    ORIGINAL_VERIFY_PUBLIC_PAGES(
        [article],
        attempts=1,
        sleeper=lambda seconds: None,
        opener=opener,
        authorization="Basic dXNlcjpwYXNz",
    )

    request = opener.requests[0]
    assert request.get_header("Authorization") == "Basic dXNlcjpwYXNz"


@pytest.mark.parametrize(
    "tamper",
    [
        lambda article: article.block_markup.replace(
            "<h2", "<h3", 1
        ).replace("</h2>", "</h3>", 1),
        lambda article: f"<h1>{article.title}</h1>{article.block_markup}",
        lambda article: article.block_markup
        + '<a href="https://hb.afl.rakuten.co.jp/ichiba/00000000.00000000.00000000/">hidden affiliate</a>',
        lambda article: article.block_markup.replace(
            "広告を含みます", "広告リンクがあります", 1
        ),
        lambda article: article.block_markup.replace(
            "/wp-content/themes/kurashinoshirube-child/assets/images/home-hero.webp",
            "https://example.invalid/product-image-drift.webp",
        ),
    ],
    ids=(
        "heading-level-demotion",
        "duplicate-h1",
        "unattributed-affiliate-link",
        "disclosure-copy-drift",
        "product-image-drift",
    ),
)
def test_public_readback_rejects_semantic_or_commercial_drift(
    tamper: Any,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_(CTA_INVALID|READBACK_FAILED)",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(
                _PublicResponse(
                    url,
                    _public_markup(article, block_markup=tamper(article)),
                )
            ),
        )


def test_mapping_is_closed_numeric_and_exact_slug_conversion() -> None:
    mapping = json.loads(
        (
            ROOT / "changes/wordpress-local-preview-v1/production-mapping.v1.json"
        ).read_text(encoding="utf-8")
    )
    articles = publication.load_articles("all")

    assert mapping["origin"] == publication.ORIGIN
    assert mapping["editor_endpoint"] == publication.EDITOR_ENDPOINT
    assert mapping["review_url"] == publication.REVIEW_URL
    assert len(articles) == 10
    for row in mapping["articles"]:
        assert row["production_slug"] == row["local_slug"].removeprefix(
            "local-preview-"
        )
        assert row["taxonomies"] == {
            "category": [5],
            "post_format": [],
            "post_tag": [],
        }
        assert all(type(term_id) is int for term_id in row["taxonomies"]["category"])


def test_tracked_theme_hash_matches_the_bounded_operator_manifest() -> None:
    relative_theme = publication.THEME_ROOT.relative_to(ROOT).as_posix()
    if subprocess.run(
        ("git", "status", "--porcelain=v1", "--", relative_theme),
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout:
        pytest.skip(
            "candidate theme is intentionally dirty in the integration worktree"
        )
    operator_path = ROOT / "scripts/raos_wordpress_deployment_operator.py"
    specification = importlib.util.spec_from_file_location(
        "wordpress_deployment_operator_for_publication_test", operator_path
    )
    assert specification is not None and specification.loader is not None
    operator = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = operator
    specification.loader.exec_module(operator)
    _, descriptor = operator.theme_package()
    assert ORIGINAL_TRACKED_THEME_TREE_SHA256() == descriptor["file_manifest_sha256"]


def test_article_selection_is_exact_production_slug_csv() -> None:
    selected = publication.load_articles(
        "roomba-mini-vs-switchbot-k11-pro,solota-vs-rakua-mini-plus"
    )
    assert [article.production_slug for article in selected] == [
        "roomba-mini-vs-switchbot-k11-pro",
        "solota-vs-rakua-mini-plus",
    ]
    for invalid in (
        "",
        "local-preview-roomba-mini-vs-switchbot-k11-pro",
        "unknown-slug",
        "roomba-mini-vs-switchbot-k11-pro,roomba-mini-vs-switchbot-k11-pro",
        "roomba-mini-vs-switchbot-k11-pro, solota-vs-rakua-mini-plus",
    ):
        with pytest.raises(
            publication.PublicationFailure,
            match="RAOS_WORDPRESS_REQUEST_ARTICLE_SELECTION_INVALID",
        ):
            publication.load_articles(invalid)


def _document(
    article: Any, post_id: int = 82, *, status: str = "draft"
) -> dict[str, Any]:
    value = article.document() | {
        "schema": "ContentDocumentV1",
        "id": post_id,
        "status": status,
        "revision_id": post_id,
        "modified_gmt": "2026-08-29T00:00:00Z",
        "content_sha256": f"{post_id:064x}",
    }
    return value


class ReconcileClient:
    def __init__(self, readback: dict[str, Any]) -> None:
        self.readback = readback
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call(self, name: str, arguments: dict[str, object]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        if name == "raos-codex-content-get":
            return self.readback
        if name == "raos-codex-content-update-draft":
            return self.readback
        raise AssertionError(name)


class MultiReconcileClient:
    def __init__(self, readbacks: list[dict[str, Any]]) -> None:
        self.readbacks = {document["id"]: document for document in readbacks}
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call(self, name: str, arguments: dict[str, object]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        assert name == "raos-codex-content-get"
        post_id = arguments["id"]
        assert isinstance(post_id, int)
        return self.readbacks[post_id]


def _private_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    os.chmod(tmp_path, 0o700)
    directory = tmp_path / "publication-requests"
    monkeypatch.setattr(publication, "PRIVATE_REQUEST_DIRECTORY", directory)
    publication._ensure_private_directory()
    return directory / "request.json"


def test_exact_draft_is_reused_and_read_back_without_update(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    document = _document(article)
    client = ReconcileClient(document)
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)

    result = publication.reconcile_drafts(client, [article], [document], receipt, path)

    assert result[article.production_slug] == document
    assert [name for name, _ in client.calls] == ["raos-codex-content-get"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_known_draft_is_cas_replaced_but_unknown_drift_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    drifted = _document(article)
    drifted["title"] = "prior workflow title"
    updated = _document(article)
    client = ReconcileClient(updated)
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_UNKNOWN_DRAFT_DRIFT",
    ):
        publication.reconcile_drafts(client, [article], [drifted], receipt, path)

    receipt["drafts"] = {
        article.production_slug: {
            "id": drifted["id"],
            "content_sha256": drifted["content_sha256"],
        }
    }
    client.calls.clear()
    publication.reconcile_drafts(client, [article], [drifted], receipt, path)
    update = next(arguments for name, arguments in client.calls if "update" in name)
    assert update["mode"] == "replace"
    assert update["precondition"]["content_sha256"] == drifted["content_sha256"]


def test_existing_published_target_is_bound_to_private_baseline_before_reuse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    published = _document(article, status="publish")
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)
    client = ReconcileClient(published)

    authoritative = publication.capture_existing_baselines(
        client,
        [article],
        [published],
        receipt,
        path,
    )
    result = publication.reconcile_drafts(
        client,
        [article],
        authoritative,
        receipt,
        path,
    )

    assert result[article.production_slug] == published
    assert receipt["baselines"][article.production_slug] == {
        "id": published["id"],
        "slug": article.production_slug,
        "status": "publish",
        "revision_id": published["revision_id"],
        "modified_gmt": published["modified_gmt"],
        "content_sha256": published["content_sha256"],
    }
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["baselines"] == receipt["baselines"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_known_draft_does_not_authorize_a_published_target_in_normal_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    published = _document(article, status="publish")
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)
    receipt["drafts"] = {
        article.production_slug: {
            "id": published["id"],
            "content_sha256": published["content_sha256"],
        }
    }

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLISHED_CONFLICT",
    ):
        publication.reconcile_drafts(
            ReconcileClient(published),
            [article],
            [published],
            receipt,
            path,
        )


def test_unknown_post_drift_after_baseline_is_refused_before_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    original = _document(article, status="publish")
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)
    publication.capture_existing_baselines(
        ReconcileClient(original), [article], [original], receipt, path
    )
    drifted = dict(original)
    drifted["content_sha256"] = "f" * 64
    drifted["revision_id"] += 1
    drifted["modified_gmt"] = "2026-08-29T00:01:00Z"

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_UNKNOWN_BASELINE_DRIFT",
    ):
        publication.capture_existing_baselines(
            ReconcileClient(drifted), [article], [drifted], receipt, path
        )


@pytest.mark.parametrize("listed_state", [None, "draft"])
def test_all_mode_refuses_a_missing_or_unpublished_existing_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    listed_state: str | None,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)
    documents = (
        [] if listed_state is None else [_document(article, status=listed_state)]
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_UNKNOWN_BASELINE_DRIFT",
    ):
        publication.capture_existing_baselines(
            ReconcileClient(documents[0] if documents else _document(article)),
            [article],
            documents,
            receipt,
            path,
            require_existing_published=True,
        )


def test_published_target_revision_only_race_is_refused_on_second_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    original = _document(article, status="publish")
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)
    receipt["baselines"][article.production_slug] = publication._baseline_record(
        original
    )
    revised = dict(original)
    revised["revision_id"] += 1
    revised["modified_gmt"] = "2026-08-29T00:01:00Z"

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_DRAFT_READBACK_FAILED",
    ):
        publication.reconcile_drafts(
            ReconcileClient(revised),
            [article],
            [original],
            receipt,
            path,
        )


@pytest.mark.parametrize(
    "replacement_state",
    ["APPLIED_ATTEMPT_REPLACED", "EXPIRED_ATTEMPT_REPLACED"],
)
def test_replaced_attempt_reconciles_multiple_known_published_targets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, replacement_state: str
) -> None:
    articles = publication.load_articles(
        "roomba-mini-vs-switchbot-k11-pro,solota-vs-rakua-mini-plus"
    )
    published = [
        _document(article, post_id=85 + index, status="publish")
        for index, article in enumerate(articles)
    ]
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt(articles, path)
    receipt["state"] = replacement_state
    receipt["drafts"] = {
        article.production_slug: {
            "id": document["id"],
            "content_sha256": document["content_sha256"],
        }
        for article, document in zip(articles, published, strict=True)
    }
    client = MultiReconcileClient(published)

    result = publication.reconcile_drafts(client, articles, published, receipt, path)

    assert result == {
        article.production_slug: document
        for article, document in zip(articles, published, strict=True)
    }
    assert [name for name, _ in client.calls] == [
        "raos-codex-content-get",
        "raos-codex-content-get",
    ]
    assert receipt["state"] == "DRAFTS_READY"


class PaginatedClient:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents
        self.pages: list[int] = []

    def call(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        assert name == "raos-codex-content-list"
        page = arguments["page"]
        assert isinstance(page, int)
        self.pages.append(page)
        start = (page - 1) * publication.LIST_PER_PAGE
        return {
            "schema": "ContentDocumentListV1",
            "page": page,
            "per_page": publication.LIST_PER_PAGE,
            "total": len(self.documents),
            "documents": self.documents[start : start + publication.LIST_PER_PAGE],
        }


def test_content_list_fetches_every_page() -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    documents = [_document(article, post_id=index) for index in range(1, 24)]
    client = PaginatedClient(documents)
    assert publication.list_all_documents(client) == documents
    assert client.pages == [1, 2, 3]


def _tools() -> dict[str, dict[str, object]]:
    result = {name: {} for name in publication.EXPECTED_TOOLS}
    result["raos-codex-content-propose-release"] = {
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "precondition", "document"],
            "properties": {
                "idempotency_key": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                }
            },
        }
    }
    result["raos-codex-publication-batch-register"] = {
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["proposal_ids", "expected_theme_tree_sha256"],
            "properties": {
                "proposal_ids": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 20,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                    },
                },
                "expected_theme_tree_sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
            },
        }
    }
    return result


def _deployment_tools() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for name in sorted(publication.EXPECTED_DEPLOYMENT_TOOLS):
        schema: dict[str, object] = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
        if name == "theme-propose-release":
            schema["properties"] = {
                "idempotency_key": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                }
            }
        if name in {"publication-batch-status", "release-wait-and-apply"}:
            schema["required"] = [
                "batch_token",
                "batch_manifest_sha256",
                "proposal_ids",
            ]
            schema["properties"] = {
                "batch_token": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "batch_manifest_sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "proposal_ids": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 20,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                    },
                },
            }
        result.append(
            {
                "name": name,
                "inputSchema": schema,
                "annotations": {
                    "readOnlyHint": name
                    in {"deployment-status", "publication-batch-status"},
                    "destructiveHint": name
                    in {
                        "release-wait-and-apply",
                        "plugin-apply-change",
                        "operation-recover",
                    },
                    "idempotentHint": name
                    not in {"theme-propose-release", "plugin-propose-change"},
                    "openWorldHint": name == "plugin-propose-change",
                },
            }
        )
    return result


class WorkflowClient:
    def __init__(self, article: Any, events: list[str]) -> None:
        self.article = article
        self.events = events
        self.document = _document(article)
        self.published = False
        self.batch_registration_state = "REGISTERED"
        self.runtime_version = publication.theme_version()
        self.runtime_revision = publication.EXPECTED_THEME_RUNTIME_REVISION

    def initialize(self) -> None:
        self.events.append("remote-initialize")

    def public_authorization(self) -> str:
        return "Basic dGVzdDp0ZXN0"

    def tools(self) -> dict[str, dict[str, object]]:
        return _tools()

    def current_document(self) -> dict[str, object]:
        document = self.document | {"status": "publish" if self.published else "draft"}
        if self.published:
            document["content_sha256"] = publication._content_after_sha256(
                self.article.document(), self.document["id"]
            )
        return document

    def status(self) -> dict[str, object]:
        return {
            "schema": "RAOSWordPressSiteStatusV1",
            "origin": publication.ORIGIN,
            "wordpress_version_compatible": True,
            "mcp_adapter_version": "0.6.1",
            "mcp_adapter_version_compatible": True,
            "plugin_version": publication.EXPECTED_PLUGIN_VERSION,
            "plugin_runtime_revision": publication.EXPECTED_PLUGIN_RUNTIME_REVISION,
            "writes_enabled": {
                "global": True,
                "draft": True,
                "content_apply": True,
                "theme_apply": True,
            },
            "theme": {
                "slug": "kurashinoshirube-child",
                "exists": True,
                "active": True,
                "version": publication.theme_version(),
                "runtime_version": self.runtime_version,
                "runtime_revision": self.runtime_revision,
            },
            "apply_authorization": {
                "mode": "approval_scoped_lease",
                "default": False,
                "single_use": True,
                "ttl_seconds": 900,
            },
            "server": {
                "endpoint": publication.EDITOR_ENDPOINT,
                "publish_tool_exposed": False,
                "delete_tool_exposed": False,
                "media_write_tool_exposed": False,
                "proposal_ttl_seconds": 900,
            },
        }

    def call(self, name: str, arguments: dict[str, object]) -> dict[str, Any]:
        self.events.append(name)
        if name == "raos-codex-site-status":
            return self.status()
        if name == "raos-codex-content-list":
            return {
                "schema": "ContentDocumentListV1",
                "page": 1,
                "per_page": publication.LIST_PER_PAGE,
                "total": 1,
                "documents": [self.current_document()],
            }
        if name == "raos-codex-content-get":
            return self.current_document()
        if name == "raos-codex-operation-get":
            assert arguments == {"operation_id": "a" * 64}
            return {
                "schema": "OperationReceiptV1",
                "proposal_id": "a" * 64,
                "operation_id": "a" * 64,
                "state": "APPLIED" if self.published else "MANUAL_REQUIRED",
                "result_code": (
                    "CONTENT_RELEASE_APPLIED"
                    if self.published
                    else "HUMAN_APPROVAL_REQUIRED"
                ),
                "before_sha256": self.document["content_sha256"],
                "after_sha256": publication._content_after_sha256(
                    self.article.document(), self.document["id"]
                ),
                "audit_id": "3" * 64,
            }
        if name == "raos-codex-content-propose-release":
            assert publication.SHA256_RE.fullmatch(str(arguments["idempotency_key"]))
            return {
                "schema": "ContentReleaseProposalV1",
                "proposal_id": "a" * 64,
                "after_sha256": publication._content_after_sha256(
                    self.article.document(), self.document["id"]
                ),
                "expires_at_gmt": "2099-08-29T00:15:00Z",
            }
        if name == "raos-codex-publication-batch-register":
            proposal_ids = arguments["proposal_ids"]
            assert isinstance(proposal_ids, list)
            assert proposal_ids == sorted(proposal_ids)
            expected_theme = arguments["expected_theme_tree_sha256"]
            assert publication.SHA256_RE.fullmatch(str(expected_theme))
            return {
                "schema": "RAOSWordPressPublicationBatchV1",
                "batch_token": "c" * 64,
                "batch_manifest_sha256": "d" * 64,
                "expected_theme_tree_sha256": expected_theme,
                "proposal_count": len(proposal_ids),
                "proposal_ids": proposal_ids,
                "state": self.batch_registration_state,
                "expires_at_gmt": "2099-08-29T00:15:00Z",
                "review_url": publication.REVIEW_URL,
            }
        raise AssertionError(name)


class DeploymentRunner:
    def __init__(
        self,
        client: WorkflowClient,
        events: list[str],
        *,
        fail_first_wait: bool = False,
        batch_status_state: str = "APPROVED",
    ) -> None:
        self.client = client
        self.events = events
        self.fail_first_wait = fail_first_wait
        self.batch_status_state = batch_status_state
        self.watcher_calls = 0
        self.theme_proposed = False
        self.local_tree = publication.tracked_theme_tree_sha256()
        self.live_tree = "9" * 64
        self.runtime_version = publication.theme_version()
        self.runtime_revision = publication.EXPECTED_THEME_RUNTIME_REVISION

    def status(self) -> dict[str, object]:
        return {
            "schema": "RAOSWordPressDeploymentStatusV1",
            "origin": publication.ORIGIN,
            "plugin_runtime_revision": publication.EXPECTED_PLUGIN_RUNTIME_REVISION,
            "php_version": "8.3.0",
            "wordpress_version": "7.1.0",
            "theme": {
                "slug": "kurashinoshirube-child",
                "version": publication.theme_version(),
                "runtime_version": self.runtime_version,
                "runtime_revision": self.runtime_revision,
                "active": True,
                "tree_sha256": self.live_tree,
            },
            "gates": {
                "global": True,
                "content_apply": True,
                "theme_apply": True,
                "plugin_apply": True,
            },
            "apply_authorization": {
                "mode": "approval_scoped_lease",
                "default": False,
                "single_use": True,
                "ttl_seconds": 900,
            },
            "private_directory_ready": True,
        }

    def __call__(
        self, arguments: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        assert arguments == (
            publication.NODE_BIN.as_posix(),
            "--experimental-strip-types",
            publication.DEPLOYMENT_BRIDGE.as_posix(),
        )
        messages = [
            json.loads(line)
            for line in bytes(kwargs["input"]).decode("utf-8").splitlines()
        ]
        assert [message["method"] for message in messages] == [
            "initialize",
            "notifications/initialized",
            "tools/list",
            "tools/call",
        ]
        call = messages[3]["params"]
        name = call["name"]
        tool_arguments = call["arguments"]
        self.events.append(f"deployment:{name}")
        if name == "deployment-status":
            value = self.status()
        elif name == "publication-batch-status":
            expected_ids = ["a" * 64]
            if self.theme_proposed:
                expected_ids.append("b" * 64)
            assert tool_arguments == {
                "batch_token": "c" * 64,
                "batch_manifest_sha256": "d" * 64,
                "proposal_ids": sorted(expected_ids),
            }
            value = {
                "schema": "RAOSWordPressPublicationBatchStatusV1",
                "batch_token": "c" * 64,
                "batch_manifest_sha256": "d" * 64,
                "proposal_count": len(expected_ids),
                "proposal_ids": sorted(expected_ids),
                "state": self.batch_status_state,
                "expires_at_gmt": "2099-08-29T00:15:00Z",
                "preconditions_ready": self.batch_status_state
                in {"APPROVED", "APPLIED"},
            }
        elif name == "theme-propose-release":
            self.theme_proposed = True
            assert publication.SHA256_RE.fullmatch(tool_arguments["idempotency_key"])
            value = {
                "proposal": {
                    "proposal_id": "b" * 64,
                    "after_tree_sha256": self.local_tree,
                    "expires_at_gmt": "2099-08-29T00:15:00Z",
                }
            }
        elif name == "release-wait-and-apply":
            self.watcher_calls += 1
            expected_ids = ["a" * 64]
            if self.theme_proposed:
                expected_ids.append("b" * 64)
            assert tool_arguments == {
                "batch_token": "c" * 64,
                "batch_manifest_sha256": "d" * 64,
                "proposal_ids": sorted(expected_ids),
            }
            if self.fail_first_wait and self.watcher_calls == 1:
                value = {"code": "WORDPRESS_MCP_RELEASE_WAIT_TIMEOUT"}
                return self._response(arguments, value, is_error=True)
            self.client.published = True
            if self.theme_proposed:
                self.live_tree = self.local_tree
                self.runtime_version = publication.theme_version()
                self.client.runtime_version = publication.theme_version()
                self.runtime_revision = publication.EXPECTED_THEME_RUNTIME_REVISION
                self.client.runtime_revision = (
                    publication.EXPECTED_THEME_RUNTIME_REVISION
                )
            receipts: list[dict[str, object]] = []
            if self.theme_proposed:
                receipts.append(
                    {
                        "schema": "OperationReceiptV1",
                        "proposal_id": "b" * 64,
                        "operation_id": "b" * 64,
                        "state": "APPLIED",
                        "result_code": "THEME_RELEASE_APPLIED",
                        "before_sha256": "9" * 64,
                        "after_sha256": self.local_tree,
                        "audit_id": "2" * 64,
                    }
                )
            receipts.append(
                {
                    "schema": "OperationReceiptV1",
                    "proposal_id": "a" * 64,
                    "operation_id": "a" * 64,
                    "state": "APPLIED",
                    "result_code": "CONTENT_RELEASE_APPLIED",
                    "before_sha256": "0" * 64,
                    "after_sha256": publication._content_after_sha256(
                        self.client.article.document(), self.client.document["id"]
                    ),
                    "audit_id": "3" * 64,
                }
            )
            value = {
                "schema": "ReleaseWaitApplyReceiptV1",
                "batch_token": "c" * 64,
                "batch_manifest_sha256": "d" * 64,
                "proposal_count": len(expected_ids),
                "proposal_ids": sorted(expected_ids),
                "state": "APPLIED",
                "receipts": receipts,
            }
        else:
            raise AssertionError(name)
        return self._response(arguments, value)

    @staticmethod
    def _response(
        arguments: tuple[str, ...], value: dict[str, object], *, is_error: bool = False
    ) -> subprocess.CompletedProcess[bytes]:
        responses = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": publication.PROTOCOL_VERSION,
                    "serverInfo": {
                        "name": "raos-wordpress-bridge",
                        "version": "1.1.0",
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"tools": _deployment_tools()},
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(value)}],
                    "structuredContent": value,
                    **({"isError": True} if is_error else {}),
                },
            },
        ]
        output = b"".join(
            json.dumps(response).encode("utf-8") + b"\n" for response in responses
        )
        return subprocess.CompletedProcess(arguments, 0, output, b"")


def test_full_workflow_checks_local_before_remote_and_runs_foreground_watcher(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    _private_path(monkeypatch, tmp_path)
    deployment = DeploymentRunner(client, events)

    def preview() -> None:
        events.append("local-preview")

    path = publication.execute(
        article.production_slug,
        preview=preview,
        client_factory=lambda: client,
        deployment_runner=deployment,
    )

    assert events[0:2] == ["local-preview", "remote-initialize"]
    assert "deployment:theme-propose-release" in events
    assert "deployment:release-wait-and-apply" in events
    assert events.count("deployment:deployment-status") == 2
    receipt = json.loads(path.read_text(encoding="utf-8"))
    assert receipt["state"] == "APPLIED"
    assert receipt["desired_theme_tree_sha256"] == deployment.local_tree
    assert receipt["batch_registration"]["proposal_ids"] == ["a" * 64, "b" * 64]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    output = capsys.readouterr().out
    assert "承認対象バッチtoken末尾12文字: cccccccccccc" in output
    assert "入力するbatch manifest hash末尾8文字: dddddddd" in output
    assert publication.REVIEW_URL in output


def test_stale_theme_runtime_forces_a_theme_proposal_even_when_tree_matches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    _private_path(monkeypatch, tmp_path)
    deployment = DeploymentRunner(client, events)
    deployment.live_tree = deployment.local_tree
    deployment.runtime_version = "1.3.8"

    path = publication.execute(
        article.production_slug,
        preview=lambda: events.append("local-preview"),
        client_factory=lambda: client,
        deployment_runner=deployment,
    )

    assert "deployment:theme-propose-release" in events
    assert deployment.runtime_version == publication.EXPECTED_THEME_VERSION
    receipt = json.loads(path.read_text(encoding="utf-8"))
    assert receipt["authenticated_readback"]["theme"]["runtime_version"] == "1.3.10"
    assert receipt["authenticated_readback"]["theme"]["runtime_revision"] == (
        publication.EXPECTED_THEME_RUNTIME_REVISION
    )


def test_missing_editor_theme_runtime_revision_forces_theme_proposal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    _private_path(monkeypatch, tmp_path)
    deployment = DeploymentRunner(client, events)
    deployment.live_tree = deployment.local_tree
    client.runtime_revision = None

    path = publication.execute(
        article.production_slug,
        preview=lambda: events.append("local-preview"),
        client_factory=lambda: client,
        deployment_runner=deployment,
    )

    assert "deployment:theme-propose-release" in events
    receipt = json.loads(path.read_text(encoding="utf-8"))
    assert receipt["desired_theme_runtime_revision"] == (
        publication.EXPECTED_THEME_RUNTIME_REVISION
    )
    assert receipt["authenticated_readback"]["theme"]["runtime_revision"] == (
        publication.EXPECTED_THEME_RUNTIME_REVISION
    )


def test_legacy_local_receipt_without_proposals_adopts_reviewed_runtime_revision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    path = _private_path(monkeypatch, tmp_path)
    monkeypatch.setattr(publication, "_receipt_path", lambda _articles: path)
    legacy = publication._fresh_receipt(
        [article],
        path,
        TEST_THEME_TREE_SHA256,
    )
    legacy["desired_theme_runtime_revision"] = None
    publication._atomic_receipt(path, legacy)
    deployment = DeploymentRunner(client, events)
    deployment.live_tree = deployment.local_tree

    result = publication.execute(
        article.production_slug,
        preview=lambda: events.append("local-preview"),
        client_factory=lambda: client,
        deployment_runner=deployment,
    )

    assert result == path
    receipt = json.loads(path.read_text(encoding="utf-8"))
    assert receipt["state"] == "APPLIED"
    assert receipt["desired_theme_runtime_revision"] == (
        publication.EXPECTED_THEME_RUNTIME_REVISION
    )


def test_article_change_during_preview_stops_before_remote_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    changed = publication.Article(
        local_slug=original.local_slug,
        production_slug=original.production_slug,
        title=original.title,
        excerpt=original.excerpt,
        block_markup=original.block_markup + "\n<!-- changed -->",
        taxonomies=original.taxonomies,
    )
    loads = iter(([original], [original], [changed]))
    monkeypatch.setattr(
        publication,
        "load_articles",
        lambda selection, **kwargs: next(loads),
    )
    _private_path(monkeypatch, tmp_path)
    remote_called = False

    def client_factory() -> object:
        nonlocal remote_called
        remote_called = True
        raise AssertionError("remote client must not be initialized")

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_ARTICLE_CHANGED_DURING_PREVIEW",
    ):
        publication.execute(
            original.production_slug,
            preview=lambda: None,
            client_factory=client_factory,
        )
    assert remote_called is False


def test_rerun_resumes_the_same_proposal_after_wait_response_loss(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    _private_path(monkeypatch, tmp_path)
    deployment = DeploymentRunner(client, events, fail_first_wait=True)

    with pytest.raises(
        publication.PublicationFailure,
        match="WORDPRESS_MCP_RELEASE_WAIT_TIMEOUT",
    ):
        publication.execute(
            article.production_slug,
            preview=lambda: events.append("local-preview"),
            client_factory=lambda: client,
            deployment_runner=deployment,
        )

    receipt_path = next(publication.PRIVATE_REQUEST_DIRECTORY.glob("request-*.json"))
    interrupted = json.loads(receipt_path.read_text(encoding="utf-8"))
    interrupted["proposals"][0]["expires_at_gmt"] = "2026-08-29T00:00:00Z"
    publication._atomic_receipt(receipt_path, interrupted)

    path = publication.execute(
        article.production_slug,
        preview=lambda: events.append("local-preview"),
        client_factory=lambda: client,
        deployment_runner=deployment,
    )
    assert deployment.watcher_calls == 2
    assert events.count("raos-codex-content-propose-release") == 1
    assert events.count("raos-codex-content-list") == 2
    assert events.count("raos-codex-operation-get") >= 2
    assert json.loads(path.read_text(encoding="utf-8"))["state"] == "APPLIED"


def test_changed_desired_never_discards_an_active_server_batch_from_local_ttl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    _private_path(monkeypatch, tmp_path)
    deployment = DeploymentRunner(client, events, fail_first_wait=True)

    with pytest.raises(
        publication.PublicationFailure,
        match="WORDPRESS_MCP_RELEASE_WAIT_TIMEOUT",
    ):
        publication.execute(
            article.production_slug,
            preview=lambda: events.append("local-preview"),
            client_factory=lambda: client,
            deployment_runner=deployment,
        )

    receipt_path = next(publication.PRIVATE_REQUEST_DIRECTORY.glob("request-*.json"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["desired_sha256"][article.production_slug] = "f" * 64
    for proposal in receipt["proposals"]:
        proposal["expires_at_gmt"] = "2026-08-29T00:00:00Z"
    publication._atomic_receipt(receipt_path, receipt)

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PENDING_REQUEST_CONFLICT",
    ):
        publication.execute(
            article.production_slug,
            preview=lambda: events.append("local-preview"),
            client_factory=lambda: client,
            deployment_runner=deployment,
        )

    preserved = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert preserved["proposals"] == receipt["proposals"]
    assert events.count("deployment:publication-batch-status") == 1
    assert deployment.watcher_calls == 1


def test_changed_desired_replaces_only_server_confirmed_expired_batch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    _private_path(monkeypatch, tmp_path)
    deployment = DeploymentRunner(client, events, fail_first_wait=True)

    with pytest.raises(publication.PublicationFailure):
        publication.execute(
            article.production_slug,
            preview=lambda: events.append("local-preview"),
            client_factory=lambda: client,
            deployment_runner=deployment,
        )
    receipt_path = next(publication.PRIVATE_REQUEST_DIRECTORY.glob("request-*.json"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["desired_sha256"][article.production_slug] = "f" * 64
    publication._atomic_receipt(receipt_path, receipt)
    deployment.batch_status_state = "EXPIRED"

    path = publication.execute(
        article.production_slug,
        preview=lambda: events.append("local-preview"),
        client_factory=lambda: client,
        deployment_runner=deployment,
    )

    completed = json.loads(path.read_text(encoding="utf-8"))
    assert completed["state"] == "APPLIED"
    assert (
        completed["desired_sha256"][article.production_slug] == article.desired_sha256()
    )
    assert events.count("deployment:publication-batch-status") == 1
    assert deployment.watcher_calls == 2


def test_changed_content_replaces_exact_server_confirmed_applied_batch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    _private_path(monkeypatch, tmp_path)
    deployment = DeploymentRunner(client, events)
    deployment.live_tree = deployment.local_tree

    first_path = publication.execute(
        article.production_slug,
        preview=lambda: events.append("local-preview"),
        client_factory=lambda: client,
        deployment_runner=deployment,
    )
    first = json.loads(first_path.read_text(encoding="utf-8"))
    first["desired_sha256"][article.production_slug] = "f" * 64
    publication._atomic_receipt(first_path, first)
    deployment.batch_status_state = "APPLIED"

    path = publication.execute(
        article.production_slug,
        preview=lambda: events.append("local-preview"),
        client_factory=lambda: client,
        deployment_runner=deployment,
    )
    completed = json.loads(path.read_text(encoding="utf-8"))
    assert completed["state"] == "APPLIED"
    assert (
        completed["desired_sha256"][article.production_slug] == article.desired_sha256()
    )
    assert events.count("deployment:publication-batch-status") == 1
    assert events.count("raos-codex-content-propose-release") == 2
    assert deployment.watcher_calls == 2


def test_changed_theme_replaces_exact_server_confirmed_applied_batch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    current_tree = ["1" * 64]
    monkeypatch.setattr(
        publication,
        "tracked_theme_tree_sha256",
        lambda: current_tree[0],
    )
    events: list[str] = []
    client = WorkflowClient(article, events)
    _private_path(monkeypatch, tmp_path)
    deployment = DeploymentRunner(client, events)

    publication.execute(
        article.production_slug,
        preview=lambda: events.append("local-preview"),
        client_factory=lambda: client,
        deployment_runner=deployment,
    )
    current_tree[0] = "2" * 64
    deployment.local_tree = current_tree[0]
    deployment.batch_status_state = "APPLIED"

    path = publication.execute(
        article.production_slug,
        preview=lambda: events.append("local-preview"),
        client_factory=lambda: client,
        deployment_runner=deployment,
    )
    completed = json.loads(path.read_text(encoding="utf-8"))
    assert completed["state"] == "APPLIED"
    assert completed["desired_theme_tree_sha256"] == current_tree[0]
    assert deployment.live_tree == current_tree[0]
    assert events.count("deployment:publication-batch-status") == 1
    assert events.count("deployment:theme-propose-release") == 2


def test_registration_response_loss_with_local_edit_reconciles_expired_batch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    _private_path(monkeypatch, tmp_path)
    deployment = DeploymentRunner(client, events, fail_first_wait=True)
    deployment.live_tree = deployment.local_tree

    with pytest.raises(publication.PublicationFailure):
        publication.execute(
            article.production_slug,
            preview=lambda: events.append("local-preview"),
            client_factory=lambda: client,
            deployment_runner=deployment,
        )
    receipt_path = next(publication.PRIVATE_REQUEST_DIRECTORY.glob("request-*.json"))
    interrupted = json.loads(receipt_path.read_text(encoding="utf-8"))
    interrupted["batch_registration"] = None
    interrupted["state"] = "PROPOSALS_READY"
    interrupted["desired_sha256"][article.production_slug] = "f" * 64
    publication._atomic_receipt(receipt_path, interrupted)
    client.batch_registration_state = "EXPIRED"
    deployment.batch_status_state = "EXPIRED"

    path = publication.execute(
        article.production_slug,
        preview=lambda: events.append("local-preview"),
        client_factory=lambda: client,
        deployment_runner=deployment,
    )
    completed = json.loads(path.read_text(encoding="utf-8"))
    assert completed["state"] == "APPLIED"
    assert events.count("raos-codex-publication-batch-register") == 3
    assert events.count("deployment:publication-batch-status") == 1


def test_registration_response_loss_after_human_approval_resumes_exact_batch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []

    class RegistrationResponseLossClient(WorkflowClient):
        def __init__(self) -> None:
            super().__init__(article, events)
            self.registration_calls = 0

        def call(self, name: str, arguments: dict[str, object]) -> dict[str, Any]:
            if name == "raos-codex-publication-batch-register":
                self.registration_calls += 1
                response = super().call(name, arguments)
                if self.registration_calls == 1:
                    raise publication.PublicationFailure(
                        "RAOS_WORDPRESS_REQUEST_MCP_RESPONSE_MISSING"
                    )
                return response
            return super().call(name, arguments)

    client = RegistrationResponseLossClient()
    _private_path(monkeypatch, tmp_path)
    deployment = DeploymentRunner(client, events)

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_MCP_RESPONSE_MISSING",
    ):
        publication.execute(
            article.production_slug,
            preview=lambda: events.append("local-preview"),
            client_factory=lambda: client,
            deployment_runner=deployment,
        )

    receipt_path = next(publication.PRIVATE_REQUEST_DIRECTORY.glob("request-*.json"))
    interrupted = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert interrupted["state"] == "PROPOSALS_READY"
    assert interrupted["batch_registration"] is None

    # Human approval may complete after the server committed registration but
    # before the caller receives that response. The idempotent retry must retain
    # the authoritative APPROVED state and continue with the exact batch.
    client.batch_registration_state = "APPROVED"
    path = publication.execute(
        article.production_slug,
        preview=lambda: events.append("local-preview"),
        client_factory=lambda: client,
        deployment_runner=deployment,
    )

    completed = json.loads(path.read_text(encoding="utf-8"))
    assert completed["state"] == "APPLIED"
    assert completed["batch_registration"]["state"] == "APPROVED"
    assert client.registration_calls == 2
    assert events.count("raos-codex-content-propose-release") == 1
    assert events.count("deployment:release-wait-and-apply") == 1


def test_partial_proposal_checkpoint_is_never_ready_for_batch_registration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles = publication.load_articles("all")
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt(articles, path)
    receipt["state"] = "PROPOSALS_IN_PROGRESS"
    receipt["proposals"] = [
        {
            "kind": "CONTENT_RELEASE",
            "slug": articles[0].production_slug,
            "proposal_id": "a" * 64,
            "after_sha256": "b" * 64,
            "expires_at_gmt": "2099-08-29T00:15:00Z",
            "idempotency_key": "c" * 64,
        }
    ]

    assert publication._unregistered_proposal_set_ready(receipt, len(articles)) is False
    receipt["state"] = "PROPOSALS_READY"
    assert publication._unregistered_proposal_set_ready(receipt, len(articles)) is False
    receipt["proposals"] = [
        {
            "kind": "CONTENT_RELEASE",
            "slug": article.production_slug,
            "proposal_id": f"{index + 1:064x}",
            "after_sha256": f"{index + 20:064x}",
            "expires_at_gmt": "2099-08-29T00:15:00Z",
            "idempotency_key": f"{index + 40:064x}",
        }
        for index, article in enumerate(articles)
    ]
    assert publication._unregistered_proposal_set_ready(receipt, len(articles)) is True
    receipt["proposals"].insert(
        0,
        {
            "kind": "THEME_RELEASE",
            "slug": None,
            "proposal_id": "e" * 64,
            "after_sha256": receipt["desired_theme_tree_sha256"],
            "expires_at_gmt": "2099-08-29T00:15:00Z",
            "idempotency_key": "f" * 64,
        },
    )
    assert publication._unregistered_proposal_set_ready(receipt, len(articles)) is True


def test_all_selection_builds_one_theme_and_ten_content_proposals(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles = publication.load_articles("all")
    assert len(articles) == publication.EXPECTED_ALL_ARTICLE_COUNT == 10
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt(articles, path, TEST_THEME_TREE_SHA256)
    drafts = {
        article.production_slug: _document(article, post_id=200 + index)
        for index, article in enumerate(articles)
    }
    proposal_ids = {
        article.production_slug: f"{index + 10:064x}"
        for index, article in enumerate(articles)
    }

    class ProposalClient:
        def call(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
            if name == "raos-codex-content-propose-release":
                document = arguments["document"]
                assert isinstance(document, dict)
                slug = document["slug"]
                assert isinstance(slug, str)
                return {
                    "schema": "ContentReleaseProposalV1",
                    "proposal_id": proposal_ids[slug],
                    "after_sha256": publication._content_after_sha256(
                        document, int(arguments["id"])
                    ),
                    "expires_at_gmt": "2099-08-29T00:15:00Z",
                }
            if name == "raos-codex-publication-batch-register":
                ids = arguments["proposal_ids"]
                assert isinstance(ids, list)
                return {
                    "schema": "RAOSWordPressPublicationBatchV1",
                    "batch_token": "c" * 64,
                    "batch_manifest_sha256": "d" * 64,
                    "expected_theme_tree_sha256": TEST_THEME_TREE_SHA256,
                    "proposal_count": 11,
                    "proposal_ids": ids,
                    "state": "REGISTERED",
                    "expires_at_gmt": "2099-08-29T00:15:00Z",
                    "review_url": publication.REVIEW_URL,
                }
            raise AssertionError(name)

    def deployment_call(
        command: str,
        value: dict[str, object],
        **kwargs: object,
    ) -> dict[str, object]:
        assert command == "theme-propose-release"
        return {
            "proposal": {
                "proposal_id": "f" * 64,
                "after_tree_sha256": TEST_THEME_TREE_SHA256,
                "expires_at_gmt": "2099-08-29T00:15:00Z",
            }
        }

    monkeypatch.setattr(publication, "_deployment_mcp_call", deployment_call)
    client = ProposalClient()
    proposals = publication.create_proposals(
        client,
        articles,
        drafts,
        True,
        receipt,
        path,
    )
    registration = publication.register_publication_batch(client, receipt, path)

    assert [proposal["kind"] for proposal in proposals] == ["THEME_RELEASE"] + [
        "CONTENT_RELEASE"
    ] * 10
    assert [proposal["slug"] for proposal in proposals[1:]] == [
        article.production_slug for article in articles
    ]
    assert registration["proposal_count"] == 11
    assert set(receipt["operation_ids"]) == {
        proposal["proposal_id"] for proposal in proposals
    }


def test_content_only_resume_stops_before_apply_if_exact_live_theme_drifted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    _private_path(monkeypatch, tmp_path)
    deployment = DeploymentRunner(client, events, fail_first_wait=True)
    deployment.live_tree = deployment.local_tree

    with pytest.raises(
        publication.PublicationFailure,
        match="WORDPRESS_MCP_RELEASE_WAIT_TIMEOUT",
    ):
        publication.execute(
            article.production_slug,
            preview=lambda: events.append("local-preview"),
            client_factory=lambda: client,
            deployment_runner=deployment,
        )

    deployment.live_tree = "9" * 64
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PENDING_THEME_DRIFT",
    ):
        publication.execute(
            article.production_slug,
            preview=lambda: events.append("local-preview"),
            client_factory=lambda: client,
            deployment_runner=deployment,
        )

    assert deployment.watcher_calls == 1
    assert client.published is False
    assert events.count("raos-codex-content-propose-release") == 1


def test_missing_idempotency_schema_stops_before_mutation() -> None:
    tools = _tools()
    del tools["raos-codex-content-propose-release"]["inputSchema"]["properties"]
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_IDEMPOTENCY_BOOTSTRAP_REQUIRED",
    ):
        publication.validate_tool_contract(tools)


def test_site_status_requires_plugin_1_2_1_runtime_and_scoped_approval_lease() -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    client = WorkflowClient(article, [])
    status = client.status()
    status["plugin_version"] = "1.1.0"
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)
    for invalid_runtime in (None, "0" * 64, "not-a-sha256"):
        status = client.status()
        status["plugin_runtime_revision"] = invalid_runtime
        with pytest.raises(
            publication.PublicationFailure,
            match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
        ):
            publication.validate_site_status(status)
    status = client.status()
    del status["plugin_runtime_revision"]
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)
    status = client.status()
    status["theme"]["runtime_version"] = None
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)
    status = client.status()
    status["theme"]["runtime_revision"] = "not-a-sha256"
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)
    status = client.status()
    del status["theme"]["runtime_revision"]
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)
    status = client.status()
    status["theme"]["runtime_revision"] = None
    publication.validate_site_status(status)
    status = client.status()
    status["apply_authorization"] = {
        "mode": "approval_scoped_lease",
        "default": True,
        "single_use": True,
        "ttl_seconds": 900,
    }
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)


def test_deployment_status_requires_runtime_revision_key_but_accepts_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    deployment = DeploymentRunner(client, events)
    status = deployment.status()
    del status["theme"]["runtime_revision"]
    monkeypatch.setattr(
        publication,
        "_deployment_mcp_call",
        lambda *_args, **_kwargs: status,
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_DEPLOYMENT_STATUS_INVALID",
    ):
        publication.deployment_status()

    status = deployment.status()
    status["theme"]["runtime_revision"] = None
    assert publication.deployment_status()["theme"]["runtime_revision"] is None


@pytest.mark.parametrize(
    "invalid_runtime",
    [None, "0" * 64, "not-a-sha256"],
)
def test_deployment_status_requires_exact_plugin_runtime_revision(
    monkeypatch: pytest.MonkeyPatch,
    invalid_runtime: object,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    deployment = DeploymentRunner(client, events)
    status = deployment.status()
    status["plugin_runtime_revision"] = invalid_runtime
    monkeypatch.setattr(
        publication,
        "_deployment_mcp_call",
        lambda *_args, **_kwargs: status,
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_DEPLOYMENT_STATUS_INVALID",
    ):
        publication.deployment_status()


def test_deployment_status_rejects_missing_plugin_runtime_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    deployment = DeploymentRunner(client, events)
    status = deployment.status()
    del status["plugin_runtime_revision"]
    monkeypatch.setattr(
        publication,
        "_deployment_mcp_call",
        lambda *_args, **_kwargs: status,
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_DEPLOYMENT_STATUS_INVALID",
    ):
        publication.deployment_status()


def test_portfolio_refresh_runs_capture_then_both_materializations_in_foreground() -> (
    None
):
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def runner(
        command: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, b"", b"")

    publication.run_editorial_portfolio_refresh(runner)

    assert [command[2:] for command, _ in calls] == [
        ("capture",),
        (
            "materialize-local",
            "--output-root",
            publication.PREVIEW_PRIVATE_ROOT.as_posix(),
        ),
        (
            "materialize-production",
            "--output-root",
            publication.PORTFOLIO_PRIVATE_ROOT.as_posix(),
        ),
    ]
    assert all(
        command[1] == publication.PORTFOLIO_SCRIPT.as_posix() for command, _ in calls
    )
    assert all(
        kwargs["stdout"] is None and kwargs["stderr"] is None for _, kwargs in calls
    )
    assert all(
        kwargs["env"] == publication.PORTFOLIO_SUBPROCESS_ENVIRONMENT
        for _, kwargs in calls
    )
    assert publication.PORTFOLIO_SUBPROCESS_ENVIRONMENT == {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "TMPDIR": "/tmp",
        "TEMP": "/tmp",
        "TMP": "/tmp",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _write_materialization_pair(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[list[Any], Path, Path]:
    articles = publication.load_articles("all")
    local_root = tmp_path / "local" / "materialized-fixtures-v2"
    production_root = tmp_path / "production" / "production-materialized-fixtures-v2"
    local_articles = local_root / "articles"
    local_articles.mkdir(parents=True)
    production_root.mkdir(parents=True)
    monkeypatch.setattr(publication, "LOCAL_MATERIALIZED_FIXTURE_ROOT", local_root)
    monkeypatch.setattr(
        publication,
        "LOCAL_MATERIALIZATION_RECEIPT",
        local_root / "materialization-receipt.v2.json",
    )
    monkeypatch.setattr(
        publication,
        "PRODUCTION_MATERIALIZATION_RECEIPT",
        production_root / "materialization-receipt.v2.json",
    )
    product_ids: set[str] = set()
    article_rows: list[dict[str, str]] = []
    for article in articles:
        parser = publication._PublicPageEvidenceParser()
        parser.feed(article.block_markup)
        parser.close()
        product_ids.update(
            str(cta["product_id"])
            for cta in publication._validated_ctas(parser)
        )
        payload = article.block_markup.encode("utf-8")
        (local_articles / f"{article.production_slug}.html").write_bytes(payload)
        article_rows.append(
            {
                "article_id": article.production_slug,
                "production_slug": article.production_slug,
                "content_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    products = [
        {
            "product_id": product_id,
            "state": "not_found",
            "provider_binding_sha256": hashlib.sha256(
                product_id.encode("ascii")
            ).hexdigest(),
        }
        for product_id in sorted(product_ids)
    ]
    generated_at = publication.datetime.now(publication.UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    common = {
        "schema": "RAOS_EDITORIAL_PORTFOLIO_MATERIALIZATION_RECEIPT_V2",
        "generated_at": generated_at,
        "portfolio_sha256": "a" * 64,
        "evidence_status_sha256": "e" * 64,
        "articles": article_rows,
        "products": products,
    }
    local_receipt = publication.LOCAL_MATERIALIZATION_RECEIPT
    production_receipt = publication.PRODUCTION_MATERIALIZATION_RECEIPT
    local_receipt.write_text(
        json.dumps({**common, "mode": "local"}), encoding="utf-8"
    )
    production_receipt.write_text(
        json.dumps({**common, "mode": "production"}), encoding="utf-8"
    )
    local_receipt.chmod(0o600)
    production_receipt.chmod(0o600)
    return articles, local_articles, local_receipt


def test_production_materialization_is_bound_to_the_exact_local_preview_variant(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, local_articles, _ = _write_materialization_pair(monkeypatch, tmp_path)

    binding = publication.production_materialization_binding(articles)

    assert binding["portfolio_sha256"] == "a" * 64
    assert len(binding["articles"]) == 10
    target = local_articles / f"{articles[0].production_slug}.html"
    target.write_text(target.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID",
    ):
        publication.production_materialization_binding(articles)


def test_materialization_pair_refuses_evidence_set_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, _, local_receipt = _write_materialization_pair(monkeypatch, tmp_path)
    local = json.loads(local_receipt.read_text(encoding="utf-8"))
    local["evidence_status_sha256"] = "f" * 64
    local_receipt.write_text(json.dumps(local), encoding="utf-8")
    local_receipt.chmod(0o600)

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID",
    ):
        publication.production_materialization_binding(articles)


def test_all_mode_recovers_registered_batch_before_provider_refresh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles = publication.load_articles("all")
    path = tmp_path / "existing.json"
    loaded = {"state": "WAITING_FOR_APPROVAL"}
    calls: list[str] = []

    class NoopLock:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(publication, "request_lock", lambda: NoopLock())
    monkeypatch.setattr(publication, "load_articles", lambda *_args, **_kwargs: articles)
    monkeypatch.setattr(publication, "_receipt_path", lambda _articles: path)
    monkeypatch.setattr(publication, "_read_receipt", lambda _path: loaded)

    def resume(
        source_articles: list[Any],
        receipt: dict[str, object],
        receipt_path: Path,
        **_kwargs: object,
    ) -> bool:
        assert source_articles == articles
        assert receipt is loaded
        assert receipt_path == path
        calls.append("resume")
        return True

    monkeypatch.setattr(publication, "_resume_existing_all_attempt", resume)

    result = publication.execute(
        "all",
        portfolio_refresh=lambda: calls.append("refresh"),
    )

    assert result == path
    assert calls == ["resume"]


def test_all_mode_applied_receipt_cannot_short_circuit_fresh_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles = publication.load_articles("all")
    path = tmp_path / "applied.json"
    receipt = publication._fresh_receipt(
        articles,
        path,
        TEST_THEME_TREE_SHA256,
    )
    receipt["state"] = "APPLIED"
    remote_status_called = False

    def remote_status(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal remote_status_called
        remote_status_called = True
        raise AssertionError("terminal receipt must not be resumed before refresh")

    monkeypatch.setattr(publication, "publication_batch_status", remote_status)

    assert publication._resume_existing_all_attempt(
        articles,
        receipt,
        path,
        client_factory=lambda: (_ for _ in ()).throw(AssertionError()),
        deployment_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError()
        ),
    ) is False
    assert remote_status_called is False


def test_all_mode_exact_nonterminal_receipt_remains_recoverable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles = publication.load_articles("all")
    path = tmp_path / "waiting.json"
    receipt = publication._fresh_receipt(
        articles,
        path,
        TEST_THEME_TREE_SHA256,
    )
    receipt["state"] = "WAITING_FOR_APPROVAL"
    receipt["proposals"] = [
        {"proposal_id": f"{index + 1:064x}"}
        for index in range(len(articles))
    ]
    receipt["batch_registration"] = {}
    calls: list[str] = []

    class ResumeClient:
        def initialize(self) -> None:
            calls.append("initialize")

        def tools(self) -> list[dict[str, object]]:
            return []

        def call(self, name: str, _arguments: dict[str, object]) -> dict[str, object]:
            assert name == "raos-codex-site-status"
            calls.append("site-status")
            return {}

    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {"state": "APPROVED"},
    )
    monkeypatch.setattr(
        publication,
        "load_articles",
        lambda *_args, **_kwargs: articles,
    )
    monkeypatch.setattr(
        publication,
        "production_materialization_binding",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(publication, "validate_tool_contract", lambda _value: None)
    monkeypatch.setattr(publication, "validate_site_status", lambda _value: None)
    monkeypatch.setattr(
        publication,
        "read_content_operations",
        lambda *_args: calls.append("operations") or {"a" * 64: {"state": "APPLIED"}},
    )
    monkeypatch.setattr(
        publication,
        "wait_and_apply",
        lambda *_args, **kwargs: calls.append(
            f"apply:{kwargs.get('finalize_applied')}"
        ),
    )
    monkeypatch.setattr(publication, "_published_document_evidence", lambda *_args: {})
    monkeypatch.setattr(publication, "_touch_receipt", lambda *_args: calls.append("touch"))

    assert publication._resume_existing_all_attempt(
        articles,
        receipt,
        path,
        client_factory=ResumeClient,
        deployment_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 0, b"", b""
        ),
    ) is False
    assert calls == [
        "initialize",
        "site-status",
        "operations",
        "apply:False",
        "operations",
        "touch",
    ]


def _write_remote_applied_legacy_all_attempt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[
    list[Any],
    Path,
    str,
    dict[str, dict[str, object]],
    dict[str, dict[str, object]],
    dict[str, dict[str, object]],
]:
    articles = publication.load_articles("all")
    path = _private_path(monkeypatch, tmp_path)
    old_tree = "0" * 64
    receipt = publication._fresh_receipt(articles, path, old_tree)
    receipt["desired_theme_runtime_revision"] = None
    receipt["state"] = "APPLY_RETURNED"
    content_proposals: list[dict[str, object]] = []
    operations: dict[str, dict[str, object]] = {}
    documents: dict[str, dict[str, object]] = {}
    drafts: dict[str, dict[str, object]] = {}
    for index, article in enumerate(articles, start=1):
        proposal_id = f"{index:064x}"
        post_id = 1000 + index
        after_sha256 = publication._content_after_sha256(article.document(), post_id)
        content_proposals.append(
            {
                "kind": "CONTENT_RELEASE",
                "slug": article.production_slug,
                "proposal_id": proposal_id,
                "after_sha256": after_sha256,
                "expires_at_gmt": "2099-08-29T00:15:00Z",
                "idempotency_key": f"{index + 20:064x}",
            }
        )
        drafts[article.production_slug] = {
            "id": post_id,
            "content_sha256": after_sha256,
        }
        documents[article.production_slug] = {
            "id": post_id,
            "slug": article.production_slug,
            "status": "publish",
            "content_sha256": after_sha256,
            "revision_id": post_id,
            "modified_gmt": "2026-08-29T00:00:00Z",
        }
        operations[proposal_id] = {
            "schema": "OperationReceiptV1",
            "proposal_id": proposal_id,
            "operation_id": proposal_id,
            "state": "APPLIED",
            "result_code": "CONTENT_RELEASE_APPLIED",
            "before_sha256": after_sha256,
            "after_sha256": after_sha256,
            "audit_id": f"{index + 40:064x}",
        }
    theme_proposal_id = "f" * 64
    receipt["proposals"] = [
        *content_proposals,
        {
            "kind": "THEME_RELEASE",
            "slug": None,
            "proposal_id": theme_proposal_id,
            "after_sha256": old_tree,
            "expires_at_gmt": "2099-08-29T00:15:00Z",
            "idempotency_key": "e" * 64,
        },
    ]
    receipt["operation_ids"] = {
        str(proposal["proposal_id"]): str(proposal["proposal_id"])
        for proposal in receipt["proposals"]
    }
    receipt["batch_registration"] = {}
    receipt["drafts"] = drafts
    publication._atomic_receipt(path, receipt)
    return articles, path, old_tree, operations, documents, drafts


def test_all_mode_remote_applied_reconciliation_ignores_stale_materialization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, path, _old_tree, operations, documents, _drafts = (
        _write_remote_applied_legacy_all_attempt(monkeypatch, tmp_path)
    )
    live_documents = {
        article.production_slug: article.document()
        | {"schema": "ContentDocumentV1"}
        | documents[article.production_slug]
        for article in articles
    }
    lifecycle: list[str] = []

    class Client:
        def initialize(self) -> None:
            lifecycle.append("initialize")

        def tools(self) -> dict[str, object]:
            return {}

        def call(
            self,
            name: str,
            arguments: dict[str, object],
        ) -> dict[str, object]:
            if name == "raos-codex-site-status":
                lifecycle.append("site-status")
                return {}
            assert name == "raos-codex-content-get"
            post_id = arguments.get("id")
            return next(
                document
                for document in live_documents.values()
                if document["id"] == post_id
            )

    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {
            "state": "APPLIED",
            "preconditions_ready": True,
        },
    )
    monkeypatch.setattr(publication, "validate_tool_contract", lambda _tools: None)
    monkeypatch.setattr(publication, "validate_site_status", lambda _status: None)

    def operation_readback(*_args: object) -> dict[str, dict[str, object]]:
        lifecycle.append("operations")
        return operations

    monkeypatch.setattr(publication, "read_content_operations", operation_readback)

    def finalize(*_args: object, **kwargs: object) -> None:
        assert kwargs == {"finalize_applied": True}
        lifecycle.append("finalize")

    monkeypatch.setattr(publication, "wait_and_apply", finalize)
    monkeypatch.setattr(
        publication,
        "load_articles",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("applied reconciliation must not load stale materialization")
        ),
    )
    monkeypatch.setattr(
        publication,
        "production_materialization_binding",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("applied reconciliation must not bind stale materialization")
        ),
    )
    receipt = json.loads(path.read_text(encoding="utf-8"))

    assert publication._resume_existing_all_attempt(
        articles,
        receipt,
        path,
        client_factory=Client,
        deployment_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 0, b"", b""
        ),
    ) is False

    assert lifecycle == [
        "initialize",
        "site-status",
        "operations",
        "finalize",
        "operations",
    ]
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["state"] == "APPLIED"
    assert stored["prior_applied_reconciliation"] == {
        "schema": "RAOS_WORDPRESS_PRIOR_APPLIED_RECONCILIATION_V1",
        "captured_at_gmt": stored["prior_applied_reconciliation"][
            "captured_at_gmt"
        ],
        "documents": documents,
        "operations": operations,
    }


def test_all_mode_remote_applied_reconciliation_requires_ready_preconditions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, path, _old_tree, _operations, _documents, _drafts = (
        _write_remote_applied_legacy_all_attempt(monkeypatch, tmp_path)
    )

    class Client:
        def __init__(self) -> None:
            raise AssertionError("MCP client must not initialize after precondition drift")

    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {
            "state": "APPLIED",
            "preconditions_ready": False,
        },
    )
    receipt = json.loads(path.read_text(encoding="utf-8"))

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_BATCH_STATUS_INVALID",
    ):
        publication._resume_existing_all_attempt(
            articles,
            receipt,
            path,
            client_factory=Client,
            deployment_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                [], 0, b"", b""
            ),
        )

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["state"] == "APPLY_RETURNED"
    assert stored["prior_applied_reconciliation"] is None


def test_all_mode_remote_applied_reconciliation_rechecks_preconditions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, path, _old_tree, operations, documents, _drafts = (
        _write_remote_applied_legacy_all_attempt(monkeypatch, tmp_path)
    )
    statuses = iter(
        (
            {"state": "APPLIED", "preconditions_ready": True},
            {"state": "APPLIED", "preconditions_ready": False},
        )
    )

    class Client:
        def initialize(self) -> None:
            return None

        def tools(self) -> dict[str, object]:
            return {}

        def call(self, name: str, _arguments: dict[str, object]) -> dict[str, object]:
            assert name == "raos-codex-site-status"
            return {}

    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: next(statuses),
    )
    monkeypatch.setattr(publication, "validate_tool_contract", lambda _tools: None)
    monkeypatch.setattr(publication, "validate_site_status", lambda _status: None)
    monkeypatch.setattr(
        publication,
        "read_content_operations",
        lambda *_args: operations,
    )
    monkeypatch.setattr(publication, "wait_and_apply", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        publication,
        "_published_receipt_document_evidence",
        lambda *_args: documents,
    )
    receipt = json.loads(path.read_text(encoding="utf-8"))

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_BATCH_STATUS_INVALID",
    ):
        publication._resume_existing_all_attempt(
            articles,
            receipt,
            path,
            client_factory=Client,
            deployment_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                [], 0, b"", b""
            ),
        )

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["state"] == "APPLY_RETURNED"
    assert stored["prior_applied_reconciliation"] is None


def test_all_mode_remote_applied_reconciliation_refuses_live_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, path, _old_tree, operations, documents, _drafts = (
        _write_remote_applied_legacy_all_attempt(monkeypatch, tmp_path)
    )
    live_documents = {
        article.production_slug: article.document()
        | {"schema": "ContentDocumentV1"}
        | documents[article.production_slug]
        for article in articles
    }
    changed_slug = articles[0].production_slug
    live_documents[changed_slug]["block_markup"] += "<!-- production drift -->"
    finalized = False

    class Client:
        def initialize(self) -> None:
            return None

        def tools(self) -> dict[str, object]:
            return {}

        def call(
            self,
            name: str,
            arguments: dict[str, object],
        ) -> dict[str, object]:
            if name == "raos-codex-site-status":
                return {}
            assert name == "raos-codex-content-get"
            post_id = arguments.get("id")
            return next(
                document
                for document in live_documents.values()
                if document["id"] == post_id
            )

    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {
            "state": "APPLIED",
            "preconditions_ready": True,
        },
    )
    monkeypatch.setattr(publication, "validate_tool_contract", lambda _tools: None)
    monkeypatch.setattr(publication, "validate_site_status", lambda _status: None)
    monkeypatch.setattr(
        publication,
        "read_content_operations",
        lambda *_args: operations,
    )

    def finalize(*_args: object, **kwargs: object) -> None:
        nonlocal finalized
        assert kwargs == {"finalize_applied": True}
        finalized = True

    monkeypatch.setattr(publication, "wait_and_apply", finalize)
    monkeypatch.setattr(
        publication,
        "load_articles",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()),
    )
    monkeypatch.setattr(
        publication,
        "production_materialization_binding",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()),
    )
    receipt = json.loads(path.read_text(encoding="utf-8"))

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLISH_READBACK_FAILED",
    ):
        publication._resume_existing_all_attempt(
            articles,
            receipt,
            path,
            client_factory=Client,
            deployment_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                [], 0, b"", b""
            ),
        )

    assert finalized is True
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["state"] == "APPLY_RETURNED"
    assert stored["prior_applied_reconciliation"] is None


@pytest.mark.parametrize("replacement_preconditions_ready", [True, False])
def test_all_mode_remote_applied_legacy_attempt_checks_replacement_preconditions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    replacement_preconditions_ready: bool,
) -> None:
    articles, path, old_tree, operations, documents, drafts = (
        _write_remote_applied_legacy_all_attempt(monkeypatch, tmp_path)
    )

    class Client:
        def initialize(self) -> None:
            return None

        def tools(self) -> dict[str, object]:
            return {}

        def call(self, name: str, _arguments: dict[str, object]) -> dict[str, object]:
            assert name == "raos-codex-site-status"
            return {"theme": {}}

    calls: list[str] = []
    status_calls = 0
    replacement_count = 0
    replacement_includes_theme = False

    class NoopLock:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(publication, "request_lock", lambda: NoopLock())
    monkeypatch.setattr(publication, "_receipt_path", lambda _articles: path)
    monkeypatch.setattr(publication, "load_articles", lambda *_args, **_kwargs: articles)
    monkeypatch.setattr(
        publication,
        "production_materialization_binding",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(publication, "validate_tool_contract", lambda _tools: None)
    monkeypatch.setattr(publication, "validate_site_status", lambda _status: None)
    def batch_status(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal status_calls
        status_calls += 1
        return {
            "state": "APPLIED",
            "preconditions_ready": (
                replacement_preconditions_ready if status_calls == 3 else True
            ),
        }

    monkeypatch.setattr(publication, "publication_batch_status", batch_status)
    monkeypatch.setattr(
        publication,
        "read_content_operations",
        lambda *_args: operations,
    )
    monkeypatch.setattr(
        publication,
        "_published_receipt_document_evidence",
        lambda *_args: documents,
    )
    monkeypatch.setattr(publication, "list_all_documents", lambda _client: [])
    monkeypatch.setattr(
        publication,
        "capture_existing_baselines",
        lambda _client, _articles, listed, *_args, **_kwargs: listed,
    )
    monkeypatch.setattr(
        publication,
        "deployment_status",
        lambda *_args, **_kwargs: {
            "theme": {
                "tree_sha256": old_tree,
                "version": "1.3.9",
                "runtime_version": "1.3.9",
                "runtime_revision": None,
            }
        },
    )
    monkeypatch.setattr(
        publication,
        "reconcile_drafts",
        lambda *_args, **_kwargs: drafts,
    )

    def create_proposals(
        _client: object,
        selected: list[Any],
        _drafts: dict[str, object],
        include_theme: bool,
        stored: dict[str, object],
        *_args: object,
    ) -> list[dict[str, object]]:
        nonlocal replacement_count, replacement_includes_theme
        replacement_count = len(selected) + (1 if include_theme else 0)
        replacement_includes_theme = include_theme
        assert stored["state"] == "APPLIED_ATTEMPT_REPLACED"
        assert stored["prior_applied_reconciliation"] is not None
        return [{} for _ in range(replacement_count)]

    monkeypatch.setattr(publication, "create_proposals", create_proposals)
    monkeypatch.setattr(
        publication,
        "register_publication_batch",
        lambda *_args: calls.append("registered"),
    )
    def wait_for_batch(*_args: object, **kwargs: object) -> None:
        if kwargs.get("finalize_applied") is True:
            calls.append("finalized-old")
            return
        raise publication.PublicationFailure("WORDPRESS_MCP_RELEASE_WAIT_TIMEOUT")

    monkeypatch.setattr(publication, "wait_and_apply", wait_for_batch)

    with pytest.raises(
        publication.PublicationFailure,
        match=(
            "WORDPRESS_MCP_RELEASE_WAIT_TIMEOUT"
            if replacement_preconditions_ready
            else "RAOS_WORDPRESS_REQUEST_BATCH_STATUS_INVALID"
        ),
    ):
        publication.execute(
            "all",
            portfolio_refresh=lambda: calls.append("refresh"),
            preview=lambda: calls.append("preview"),
            client_factory=Client,
        )

    assert status_calls == 3
    if replacement_preconditions_ready:
        assert calls == ["finalized-old", "refresh", "preview", "registered"]
        assert replacement_includes_theme is True
        assert replacement_count == 11
    else:
        assert calls == ["finalized-old", "refresh", "preview"]
        assert replacement_includes_theme is False
        assert replacement_count == 0


def test_all_mode_applied_recovery_failure_stops_before_fresh_cycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, path, _old_tree, operations, _documents, _drafts = (
        _write_remote_applied_legacy_all_attempt(monkeypatch, tmp_path)
    )
    lifecycle: list[str] = []

    class Client:
        def initialize(self) -> None:
            return None

        def tools(self) -> dict[str, object]:
            return {}

        def call(self, name: str, _arguments: dict[str, object]) -> dict[str, object]:
            assert name == "raos-codex-site-status"
            return {"theme": {}}

    monkeypatch.setattr(publication, "_receipt_path", lambda _articles: path)
    monkeypatch.setattr(publication, "load_articles", lambda *_args, **_kwargs: articles)
    monkeypatch.setattr(
        publication,
        "production_materialization_binding",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(publication, "validate_tool_contract", lambda _tools: None)
    monkeypatch.setattr(publication, "validate_site_status", lambda _status: None)
    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {
            "state": "APPLIED",
            "preconditions_ready": True,
        },
    )
    monkeypatch.setattr(
        publication,
        "read_content_operations",
        lambda *_args: operations,
    )

    def recovery_failure(
        stored: dict[str, object],
        receipt_path: Path,
        *_args: object,
        **kwargs: object,
    ) -> None:
        assert kwargs == {"finalize_applied": True}
        publication._touch_receipt(receipt_path, stored, "FINALIZING_APPLIED")
        lifecycle.append("recover")
        raise publication.PublicationFailure(
            "RAOS_CODEX_RECOVERY_CLEANUP_INDETERMINATE"
        )

    monkeypatch.setattr(publication, "wait_and_apply", recovery_failure)
    monkeypatch.setattr(
        publication,
        "_published_receipt_document_evidence",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("readback must follow successful recovery")
        ),
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_CODEX_RECOVERY_CLEANUP_INDETERMINATE",
    ):
        publication.execute(
            "all",
            portfolio_refresh=lambda: lifecycle.append("refresh"),
            preview=lambda: lifecycle.append("preview"),
            client_factory=Client,
        )

    assert lifecycle == ["recover"]
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["state"] == "FINALIZING_APPLIED"
    assert publication._resume_ready(stored, len(articles)) is True


def test_all_mode_refuses_revision_only_drift_after_applied_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, path, _old_tree, operations, documents, _drafts = (
        _write_remote_applied_legacy_all_attempt(monkeypatch, tmp_path)
    )
    current_documents = {
        article.production_slug: article.document()
        | {"schema": "ContentDocumentV1"}
        | documents[article.production_slug]
        for article in articles
    }
    lifecycle: list[str] = []
    remote_calls: list[str] = []

    class Client:
        def initialize(self) -> None:
            remote_calls.append("initialize")

        def tools(self) -> dict[str, object]:
            return {}

        def call(
            self,
            name: str,
            arguments: dict[str, object],
        ) -> dict[str, object]:
            remote_calls.append(name)
            if name == "raos-codex-site-status":
                return {"theme": {}}
            if name == "raos-codex-content-list":
                assert arguments == {
                    "post_type": "post",
                    "status": "any",
                    "page": 1,
                    "per_page": publication.LIST_PER_PAGE,
                }
                return {
                    "schema": "ContentDocumentListV1",
                    "page": 1,
                    "per_page": publication.LIST_PER_PAGE,
                    "total": len(current_documents),
                    "documents": list(current_documents.values()),
                }
            if name == "raos-codex-content-get":
                post_id = arguments.get("id")
                return next(
                    document
                    for document in current_documents.values()
                    if document["id"] == post_id
                )
            raise AssertionError(f"unexpected mutation/proposal call: {name}")

    client = Client()
    monkeypatch.setattr(publication, "_receipt_path", lambda _articles: path)
    monkeypatch.setattr(publication, "load_articles", lambda *_args, **_kwargs: articles)
    monkeypatch.setattr(
        publication,
        "production_materialization_binding",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(publication, "validate_tool_contract", lambda _tools: None)
    monkeypatch.setattr(publication, "validate_site_status", lambda _status: None)
    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {
            "state": "APPLIED",
            "preconditions_ready": True,
        },
    )
    monkeypatch.setattr(
        publication,
        "read_content_operations",
        lambda *_args: operations,
    )
    monkeypatch.setattr(
        publication,
        "wait_and_apply",
        lambda *_args, **kwargs: lifecycle.append(
            f"finalize:{kwargs.get('finalize_applied')}"
        ),
    )

    def reconciled_documents(*_args: object) -> dict[str, dict[str, object]]:
        lifecycle.append("resume-readback")
        return documents

    monkeypatch.setattr(
        publication,
        "_published_receipt_document_evidence",
        reconciled_documents,
    )
    monkeypatch.setattr(
        publication,
        "deployment_status",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("deployment status must follow exact baseline verification")
        ),
    )
    monkeypatch.setattr(
        publication,
        "reconcile_drafts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("draft reconciliation must not run after unknown drift")
        ),
    )
    monkeypatch.setattr(
        publication,
        "create_proposals",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("proposal creation must not run after unknown drift")
        ),
    )

    def preview() -> None:
        assert lifecycle == ["finalize:True", "resume-readback", "refresh"]
        lifecycle.append("preview")
        slug = articles[0].production_slug
        revised = dict(current_documents[slug])
        revised["revision_id"] = int(revised["revision_id"]) + 1
        revised["modified_gmt"] = "2026-08-29T00:01:00Z"
        assert revised["content_sha256"] == documents[slug]["content_sha256"]
        current_documents[slug] = revised

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_UNKNOWN_BASELINE_DRIFT",
    ):
        publication.execute(
            "all",
            portfolio_refresh=lambda: lifecycle.append("refresh"),
            preview=preview,
            client_factory=lambda: client,
        )

    assert lifecycle == [
        "finalize:True",
        "resume-readback",
        "refresh",
        "preview",
    ]
    assert "raos-codex-content-update-draft" not in remote_calls
    assert "raos-codex-content-propose-release" not in remote_calls
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["state"] == "APPLIED"
    assert stored["prior_applied_reconciliation"]["documents"] == documents


def test_stale_docker_group_uses_only_fixed_sg_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(publication, "_docker_group_membership_is_stale", lambda: True)
    commands: list[tuple[str, ...]] = []
    fixture_roots: list[str] = []

    def runner(
        command: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        fixture_roots.append(environment["RAOS_WORDPRESS_PREVIEW_FIXTURE_ROOT"])
        return subprocess.CompletedProcess(command, 0, b"", b"")

    publication.run_preview_checks(runner)
    assert commands == [
        (
            "/usr/bin/sg",
            "docker",
            "-c",
            f"/usr/bin/make {target}",
        )
        for target in (
            "wordpress-preview-up",
            "wordpress-preview-sync",
            "wordpress-preview-check",
        )
    ]
    assert all("ARTICLES" not in part for command in commands for part in command)
    assert fixture_roots == [publication.LOCAL_MATERIALIZED_FIXTURE_ROOT.as_posix()] * 3


def test_make_target_passes_articles_via_environment_without_shell_expansion() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "wordpress-production-request:" in makefile
    recipe = makefile[makefile.index("wordpress-production-request:") :]
    assert "$(ARTICLES)" not in recipe
    assert 'os.environ.get("ARTICLES", "all")' in SCRIPT.read_text(encoding="utf-8")


def test_seed_uses_the_production_markup_sanitizers() -> None:
    seed = (ROOT / "changes/wordpress-local-preview-v1/seed.php").read_text(
        encoding="utf-8"
    )
    assert "wp_strip_all_tags($post['title']) !== $post['title']" in seed
    assert "wp_kses_post($post['excerpt']) !== $post['excerpt']" in seed
    assert "wp_kses_post($content) !== $content" in seed
