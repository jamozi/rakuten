from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "scripts/wordpress_public_ui_audit.function.js"
SHELL = ROOT / "scripts/check_wordpress_public_ui_playwright.sh"
INVENTORY = (
    ROOT / "changes/editorial-portfolio-v3/generated/wordpress-audit-inventory.v3.json"
)
NAVIGATION = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/editorial-navigation.v3.json"
)


def test_generated_audit_inventory_is_public_safe_exact_v3_projection() -> None:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    navigation = json.loads(NAVIGATION.read_text(encoding="utf-8"))
    article_surfaces = {
        row["article_id"]: row
        for row in inventory["surfaces"]
        if row["kind"] == "article"
    }

    assert (
        inventory["source_navigation_sha256"] == navigation["source_navigation_sha256"]
    )
    assert inventory["source_portfolio_sha256"] == navigation["source_portfolio_sha256"]
    assert list(article_surfaces) == [
        row["article_id"] for row in navigation["articles"]
    ]
    for article in navigation["articles"]:
        surface = article_surfaces[article["article_id"]]
        related_ids = [
            row["article_id"]
            for row in article["related_articles"]
            if row["relationship"] == "same_cluster"
        ]
        contextual_id = next(
            row["article_id"]
            for row in article["related_articles"]
            if row["relationship"] == "same_cluster"
        )
        assert surface == {
            "article_id": article["article_id"],
            "cluster_id": article["cluster_id"],
            "contextual_article_id": contextual_id,
            "kind": "article",
            "local_path": f"/{article['local_slug']}/",
            "production_path": f"/{article['production_slug']}/",
            "related_article_ids": related_ids,
            "surface_id": f"article-{article['article_code']}",
        }
    assert inventory["clusters"] == [
        {
            "anchor": row["anchor"],
            "article_ids": row["article_ids"],
            "cluster_id": row["cluster_id"],
        }
        for row in navigation["clusters"]
    ]
    assert [
        row["surface_id"] for row in inventory["surfaces"] if row["kind"] == "policy"
    ] == [
        "policy-about-ad-policy",
        "policy-comparison-policy",
        "policy-privacy-policy",
    ]
    serialized = INVENTORY.read_text(encoding="utf-8").casefold()
    for prohibited in (
        "credential",
        "secret",
        "snapshot_id",
        "product_id",
        "query_text",
    ):
        assert prohibited not in serialized


def test_public_audit_covers_home_ten_articles_and_three_pages_at_four_widths() -> None:
    source = AUDIT.read_text(encoding="utf-8")
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    assert len(inventory["surfaces"]) == 14
    assert len(inventory["viewports"]) == 4
    assert len(inventory["surfaces"]) * len(inventory["viewports"]) == 56
    for surface in inventory["surfaces"]:
        if surface["production_path"] != "/":
            assert surface["production_path"] not in source
    assert "const rawSurfaces = inventory?.surfaces;" in source
    assert "const rawClusters = inventory?.clusters;" in source
    assert "const widths = inventory?.viewports;" in source
    assert "path: surface.production_path" in source
    assert "response.status() !== 200" in source
    assert "response.url() !== expectedUrl" in source
    for marker in (
        "audit.homeClusters.length !== expectedClusters.length",
        "cluster.anchor !== expected.anchor",
        "cluster.links.length !== expected.paths.length",
        "link.pathname !== expected.paths[linkIndex]",
        "audit.internalLinks.length !== expectedInternalLinks.length",
        "surface.contextual_article_id",
        "surface.related_article_ids.map",
        "link.origin !== origin",
        "link.search !== ''",
        "link.hash !== ''",
        "page.request.get(link.href, { maxRedirects: 0 })",
        "linkResponse.status() !== 200",
        "linkResponse.url() !== link.href",
        "results.length !== surfaces.length * widths.length",
    ):
        assert marker in source
    assert "process.cwd()" not in source


def test_public_audit_shell_requires_all_56_artifacts_and_is_portable() -> None:
    source = SHELL.read_text(encoding="utf-8")
    assert 'readonly repository_root="$(CDPATH= cd -- "$script_directory/.."' in source
    assert "wordpress-audit-inventory.v3.json" in source
    assert "inventory.surfaces" in source
    assert "inventory.viewports" in source
    assert "artifact_name in $artifact_names" in source
    assert "for name in" not in source
    assert '[ "$#" -eq "$expected_count" ]' in source
    assert "/home/minami/rakuten" not in source
    subprocess.run(
        ["/usr/bin/bash", "-n", str(SHELL)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
