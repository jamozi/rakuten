"""Closed public page authoring for reader releases; never creates WordPress objects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
import hashlib
import json
from pathlib import Path
import re
import sys

from raos.application.editorial.reader_experience_v1 import reader_navigation
from raos.application.editorial.verified_incremental_v1 import canonical

sys.path.insert(0, str(Path(__file__).resolve().parent))
from raos_wordpress_publication_request import Article  # noqa: E402

HUB_SLUGS = frozenset(
    {
        "categories",
        "purposes",
        "guides",
        "comparisons",
        "updates",
        "travel",
        "kitchen",
        "cleaning",
        "preparedness",
        "small-space",
        "save-housework",
        "without-installation",
        "easy-maintenance",
        "comfortable-travel",
        "prepare-outage",
    }
)
THEME = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)
READER_SOURCE = Path("changes/editorial-portfolio-v3/reader-experience.v1.json")
PORTFOLIO_SOURCE = Path("changes/editorial-portfolio-v3/editorial-portfolio.v3.json")
PRIVACY_SOURCE = Path("changes/editorial-portfolio-v3/reader-measurement-privacy.html")


def _read(root: Path, relative: Path) -> bytes:
    path = root / relative
    if not root.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("READER_PAGE_SOURCE_INVALID")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("READER_PAGE_SOURCE_INVALID")
    raw = path.read_bytes()
    if not 1 <= len(raw) <= 2 * 1024 * 1024:
        raise ValueError("READER_PAGE_SOURCE_INVALID")
    return raw


def hub_registry(root: Path) -> dict[str, Any]:
    """Derive memberships from the same authoring input used by the theme owner."""
    reader = json.loads(_read(root, READER_SOURCE))
    portfolio = json.loads(_read(root, PORTFOLIO_SOURCE))
    result = reader_navigation(reader["navigation"], portfolio["articles"])
    hubs = result["hubs"]
    if len(hubs) != 15 or {row["slug"] for row in hubs} != HUB_SLUGS:
        raise ValueError("READER_HUB_REGISTRY_SCOPE_CHANGED")
    known = {row["article_id"] for row in portfolio["articles"]}
    if len(known) != 10 or any(
        not row["article_ids"] or not set(row["article_ids"]) <= known for row in hubs
    ):
        raise ValueError("READER_HUB_ARTICLE_SCOPE_CHANGED")
    return result


def hub_registry_sha256(root: Path) -> str:
    return hashlib.sha256(canonical(hub_registry(root))).hexdigest()


def load_hub_pages(root: Path) -> list[Article]:
    result = []
    for row in hub_registry(root)["hubs"]:
        slug = row["slug"]
        result.append(
            Article(
                local_slug=slug,
                production_slug=slug,
                title=row["label"],
                excerpt=row["description"],
                block_markup='<!-- wp:shortcode -->[kurashinoshirube_reader_hub slug="'
                + slug
                + '"]<!-- /wp:shortcode -->',
                taxonomies={},
                post_type="page",
            )
        )
    return result


def select_hub_pages(root: Path, slugs: Sequence[str]) -> list[Article]:
    if not slugs or len(set(slugs)) != len(slugs) or not set(slugs) <= HUB_SLUGS:
        raise ValueError("READER_HUB_SELECTION_INVALID")
    by_slug = {page.production_slug: page for page in load_hub_pages(root)}
    return [by_slug[slug] for slug in sorted(slugs)]


def load_home_page(root: Path) -> Article:
    """The front-page template owns both the displayed page and editor fragment."""
    template = _read(root, THEME / "templates/front-page.html").decode("utf-8")
    body = re.search(r"<main\b[^>]*>\s*(.*?)\s*</main>", template, flags=re.S)
    if body is None or template.count("<main") != 1:
        raise ValueError("READER_HOME_TEMPLATE_INVALID")
    markup = body[1].strip() + "\n"
    if "wp:template-part" in markup or markup.count("<h1") != 1:
        raise ValueError("READER_HOME_TEMPLATE_INVALID")
    return Article(
        local_slug="home",
        production_slug="home",
        title="ホーム",
        excerpt="サイズ、使い方、手入れの違いを整理し、暮らしに合う生活用品を選ぶためのガイドです。",
        block_markup=markup,
        taxonomies={},
        post_type="page",
    )


def load_reader_privacy_page(root: Path) -> Article:
    markup = _read(root, PRIVACY_SOURCE).decode("utf-8")
    if re.search(r"<(?:script|style|iframe|form|input)\b", markup, re.I):
        raise ValueError("READER_PRIVACY_EXECUTABLE_MARKUP")
    return Article(
        local_slug="privacy-policy",
        production_slug="privacy-policy",
        title="プライバシーポリシー",
        excerpt="任意の読者行動計測の項目、許可・拒否・撤回、保存期間、管理・削除について説明します。",
        block_markup=markup,
        taxonomies={},
        post_type="page",
    )


def selected_page_slugs(root: Path, arguments: object) -> list[str]:
    """Resolve only explicit page flags; never infer a publication target."""
    selected: list[str] = []
    raw = getattr(arguments, "reader_pages", None)
    if raw:
        selected.extend(
            page.production_slug for page in select_hub_pages(root, raw.split(","))
        )
    if getattr(arguments, "reader_privacy", False):
        if getattr(arguments, "update_policies", "none") == "all":
            raise ValueError("READER_PRIVACY_SELECTION_CONFLICT")
        selected.append(load_reader_privacy_page(root).production_slug)
    if getattr(arguments, "include_home", False):
        selected.append(load_home_page(root).production_slug)
    return sorted(selected)


def reader_page_targets(
    root: Path, pages: Sequence[Article], snapshot: Mapping[str, Any]
) -> dict[str, Any]:
    """Bind exact templates to authoritative MCP IDs and baseline states."""
    from raos.application.editorial.verified_incremental_v1 import ReaderPageTarget

    expected = {page.production_slug: page for page in load_hub_pages(root)}
    expected["privacy-policy"] = load_reader_privacy_page(root)
    inventory = {row["slug"]: row for row in snapshot["documents"]}
    targets = {}
    for page in pages:
        slug = page.production_slug
        if (
            slug in targets
            or slug not in expected
            or page.document() != expected[slug].document()
        ):
            raise ValueError("READER_PAGE_SOURCE_MISMATCH")
        baseline = inventory.get(slug)
        if (
            baseline is None
            or baseline.get("post_type") != "page"
            or baseline.get("status") not in {"draft", "publish"}
        ):
            raise ValueError("READER_PAGE_BASELINE_INVALID")
        kind = "reader_privacy" if slug == "privacy-policy" else "hub"
        if kind == "reader_privacy" and baseline["status"] != "publish":
            raise ValueError("READER_PAGE_BASELINE_INVALID")
        targets[slug] = ReaderPageTarget(
            kind,
            baseline["id"],
            baseline["status"],
            hashlib.sha256(page.block_markup.encode()).hexdigest(),
            hashlib.sha256(_read(root, PRIVACY_SOURCE)).hexdigest()
            if kind == "reader_privacy"
            else hub_registry_sha256(root),
        )
    return targets


def reader_measurement_projection(root: Path) -> tuple[dict[str, object], bytes]:
    from raos_wordpress_runtime_audit import reader_measurement_runtime

    base = Path("changes/reader-measurement-v1")
    raw = _read(root, base / "runtime-manifest.v1.json")
    manifest = json.loads(raw)
    policy = _read(root, PRIVACY_SOURCE)
    files = {
        row["path"]: _read(
            root, base / "wordpress-plugin/raos-reader-measurement" / row["path"]
        )
        for row in manifest["plugin_files"]
    }
    # The runtime factory validates the actual package bytes, closed endpoints and assets.
    reader_measurement_runtime(
        raw,
        files,
        policy,
        expected_manifest_sha256=hashlib.sha256(raw).hexdigest(),
        expected_policy_sha256=hashlib.sha256(policy).hexdigest(),
        expected_collection_enabled=False,
    )
    return {
        "schema": "RAOS_READER_MEASUREMENT_RELEASE_V1",
        "profile": "reader-minimal-v1",
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "policy_sha256": hashlib.sha256(policy).hexdigest(),
        "contract_sha256": manifest["contract_sha256"],
        "revision": manifest["revision"],
        "expected_collection_enabled": False,
    }, raw
