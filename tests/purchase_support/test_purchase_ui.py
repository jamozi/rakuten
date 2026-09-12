"""Client purchase decisions, runtime expiry, and progressive enhancement boundaries."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_purchase_ui_logic_and_browser_contract():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node runtime unavailable")
    root = Path(__file__).resolve().parents[2]
    assets = (
        root
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets"
    )
    result = subprocess.run(
        [
            node,
            "tests/purchase_support/purchase_ui_harness.cjs",
            str(assets / "purchase-support.js"),
            str(assets / "purchase-support.css"),
        ],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_published_controls_are_inert_before_browser_enhancement():
    import json

    from raos.application.editorial.reader_html import fragment
    from raos.application.editorial.purchase_support import render_comparison

    root = Path(__file__).resolve().parents[2]
    catalog = json.loads(
        (
            root / "changes/reader-purchase-support-v1/purchase-support.v1.json"
        ).read_text()
    )
    for article in catalog["articles"]:
        body = (
            root
            / "changes/wordpress-direct-publish-v1/articles"
            / (article["slug"] + ".html")
        ).read_text()
        if article["kind"] == "comparison":
            template = (
                root
                / "changes/reader-purchase-support-v1/articles"
                / (article["slug"] + ".html")
            ).read_text()
            body, _ = render_comparison(
                article, catalog, template, "test-inert-boundary"
            )
        nodes = list(fragment(body).walk())
        assert not any(
            node.tag in {"input", "select", "button", "noscript", "form"}
            for node in nodes
        ), article["slug"]
        if article["kind"] == "comparison":
            configs = [
                n.attrs["data-ps-purpose-options"]
                for n in nodes
                if "data-ps-purpose-options" in n.attrs
            ]
            root_node = next(n for n in nodes if "data-raos-article-id" in n.attrs)
            if article["slug"] == "countertop-dishwasher-for-small-households":
                # The main comparison links the four conditions instead of inputs.
                assert configs == []
                assert root_node.attrs["data-ps-purpose-mode"] == "links"
                assert root_node.attrs["data-ps-budget-mode"] == "off"
            else:
                assert "data-ps-purpose-mode" not in root_node.attrs
                assert json.loads(configs[0]) == [
                    {"id": c["id"], "label": c["label"]} for c in article["conditions"]
                ]
