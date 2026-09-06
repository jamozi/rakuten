"""Select browser surfaces from validated publication scope, never a screen count."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SHARED_PRESENTATION_INPUTS = (
    "changes/wordpress-local-preview-v1/mu-plugins/",
    "changes/wordpress-local-preview-v1/gateway/",
    "changes/wordpress-local-preview-v1/compose.yaml",
    "changes/editorial-measurement-v1/wordpress-plugin/",
    "changes/reader-measurement-v1/wordpress-plugin/",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/",
)


def presentation_requires_full(changes: Sequence[str]) -> bool:
    release_scripts = {
        "raos_wordpress_release_workflow.py",
        "raos_wordpress_verification.py",
        "raos_wordpress_incremental_publication.py",
        "raos_wordpress_publication_request.py",
        "raos_wordpress_incremental_candidate.py",
        "raos_wordpress_incremental_preview.py",
    }
    for path in changes:
        if path.startswith(SHARED_PRESENTATION_INPUTS):
            return True
        # Known publication-only and non-runtime changes don't alter rendering.
        if path.startswith(
            (
                "tests/",
                "docs/",
                "python/raos/application/editorial/verified_incremental",
            )
        ) or path in {"AGENTS.md", "README.md"}:
            continue
        if path.startswith("scripts/") and path.split("/")[-1] in release_scripts:
            continue
        if path in {
            "changes/build/manifest.v2.json",
            "changes/wordpress-mcp-v1/runtime-manifest.v1.json",
            "changes/wordpress-mcp-v1/contracts/repo-plugin-artifacts.v1.json",
        }:
            continue
        if path.endswith(
            (
                ".py",
                ".js",
                ".php",
                ".ts",
                ".css",
                ".json",
                ".yaml",
                ".yml",
                ".lock",
                ".toml",
                ".sh",
                ".conf",
            )
        ):
            return True
    return False


def browser_plan(
    inventory: Mapping[str, Any],
    manifest: Mapping[str, Any] | None = None,
    *,
    article_markup: Mapping[str, str] | None = None,
    full: bool = False,
    changed_files: Sequence[str] = (),
) -> dict[str, Any]:
    rows = [*inventory["surfaces"], *inventory["local_surfaces"]]
    ids = [row["surface_id"] for row in rows]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError("invalid browser inventory")
    reasons: dict[str, list[str]] = {}

    def include(row: Mapping[str, Any], reason: str) -> None:
        reasons.setdefault(row["surface_id"], []).append(reason)

    if (
        full
        or presentation_requires_full(changed_files)
        or manifest is None
        or manifest.get("shared_artifacts")
    ):
        for row in rows:
            include(row, "full diagnostic or shared presentation changes")
    else:
        selected = {row["article_id"] for row in manifest["articles"]}
        articles = {row["article_id"]: row for row in rows if row["kind"] == "article"}
        if not selected or not selected <= set(articles):
            raise ValueError("unknown or empty article selection")
        paths = {
            path
            for article in selected
            for path in (
                articles[article]["local_path"],
                articles[article]["production_path"],
            )
        }
        related = set(selected)
        for cluster in inventory.get("clusters", []):
            if selected & set(cluster["article_ids"]):
                related.update(cluster["article_ids"])
        # Include incoming links as well as outgoing related-article cards.
        # Without inspectable markup, conservatively cover every article.
        if article_markup is None or not set(articles) <= set(article_markup):
            related.update(articles)
        else:
            for article, markup in article_markup.items():
                if any(path in markup for path in paths):
                    related.add(article)
        for row in rows:
            if row["kind"] == "article" and row["article_id"] in related:
                include(row, "selected article or related/internal-link consumer")
            elif row["kind"] in {"home", "search", "archive"}:
                include(row, "article listing or navigation consumer")
    selected_ids = [identifier for identifier in ids if identifier in reasons]
    performance_ids = {"home"}
    if manifest is None or manifest.get("shared_artifacts"):
        performance_ids.add("article-a04")
    if manifest is not None:
        article_ids = {row["article_id"] for row in manifest["articles"]}
        performance_ids.update(
            row["surface_id"]
            for row in rows
            if row["kind"] == "article" and row["article_id"] in article_ids
        )
    widths = list(inventory["viewports"])
    if not widths or len(widths) != len(set(widths)):
        raise ValueError("invalid viewport selection")
    return {
        "schema": "RAOS_WORDPRESS_BROWSER_PLAN_V2",
        "surface_ids": selected_ids,
        "viewports": widths,
        "zoom_percent": 200,
        "reasons": reasons,
        "performance_targets": [
            {"name": row["surface_id"], "path": row["local_path"]}
            for row in rows
            if row["surface_id"] in performance_ids
        ],
        "screenshots": [
            name
            for identifier in selected_ids
            for name in (
                *(f"local-preview-{identifier}-{width}.png" for width in widths),
                f"local-preview-{identifier}-zoom200.png",
            )
        ],
    }


def validate_selection(plan: Mapping[str, Any], inventory: Mapping[str, Any]) -> None:
    rows = [*inventory["surfaces"], *inventory["local_surfaces"]]
    identifiers = plan.get("surface_ids", [])
    if (
        plan.get("schema") != "RAOS_WORDPRESS_BROWSER_PLAN_V2"
        or not identifiers
        or len(set(identifiers)) != len(identifiers)
        or not set(identifiers) <= {row["surface_id"] for row in rows}
        or plan.get("viewports") != inventory["viewports"]
        or plan.get("zoom_percent") != 200
    ):
        raise ValueError("invalid browser selection")
