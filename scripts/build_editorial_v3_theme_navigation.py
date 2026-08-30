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
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/editorial-navigation.v3.json"
)
MAX_INPUT_BYTES: Final = 2 * 1024 * 1024
MAX_OUTPUT_BYTES: Final = 256 * 1024
SLUG_RE: Final = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CODE_RE: Final = re.compile(r"^a[0-9]{2}$")
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
    except (UnicodeDecodeError, json.JSONDecodeError):
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
    except (TypeError, ValueError):
        _fail()


def build() -> bytes:
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
        ):
            _fail()
        portfolio_by_id[article_id] = raw

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
            or len(related) < 2
            or raw.get("article_code") != source.get("article_code")
            or raw.get("production_slug") != source.get("production_slug")
            or raw.get("cluster_id") != source.get("cluster_id")
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
            if relationship is None:
                relationship = (
                    "same_cluster"
                    if related_source is not None
                    and related_source.get("cluster_id") == source.get("cluster_id")
                    else "adjacent_context"
                )
            if (
                related_source is None
                or related_id == article_id
                or related_id in related_ids
                or relationship not in {"same_cluster", "adjacent_context"}
            ):
                _fail()
            related_ids.add(related_id)
            projected_related.append(
                {
                    "article_id": related_id,
                    "relationship": relationship,
                }
            )
        cluster_size = sum(
            1
            for candidate in portfolio_by_id.values()
            if candidate.get("cluster_id") == source.get("cluster_id")
        )
        same_cluster_count = sum(
            item["relationship"] == "same_cluster" for item in projected_related
        )
        if (
            (cluster_size >= 3 and same_cluster_count < 2)
            or (cluster_size == 2 and same_cluster_count != 1)
        ):
            _fail()
        projected_articles.append(
            {
                "article_code": code,
                "article_id": article_id,
                "category_label": source["category_label"],
                "cluster_id": source["cluster_id"],
                "home_order": raw["home_order"],
                "local_slug": source["local_slug"],
                "production_slug": slug,
                "related_articles": projected_related,
                "snapshot_id": source["snapshot_id"],
                "title": raw["title"],
            }
        )

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
    output = {
        "articles": projected_articles,
        "clusters": clusters,
        "schema": "RAOS_EDITORIAL_THEME_NAVIGATION_V3",
        "source_navigation_sha256": hashlib.sha256(navigation_bytes).hexdigest(),
        "source_portfolio_sha256": hashlib.sha256(portfolio_bytes).hexdigest(),
        "target_origin": "https://kurashinoshirube.com",
        "version": "3.0.0",
    }
    payload = _canonical(output)
    if len(payload) > MAX_OUTPUT_BYTES:
        _fail()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        payload = build()
        if arguments.check:
            if OUTPUT.read_bytes() != payload or OUTPUT.is_symlink():
                _fail()
        else:
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            temporary = OUTPUT.with_name(f".{OUTPUT.name}.{os.getpid()}.tmp")
            descriptor = os.open(
                temporary,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o644,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, OUTPUT)
    except (NavigationBuildFailure, OSError):
        print("EDITORIAL_V3_THEME_NAVIGATION_INVALID", file=os.sys.stderr)
        return 1
    print(
        "EDITORIAL_V3_THEME_NAVIGATION_OK sha256="
        + hashlib.sha256(payload).hexdigest()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
