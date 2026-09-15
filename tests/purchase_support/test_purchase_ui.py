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
        if article["kind"] == "comparison" and not article.get("authored_comparison"):
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
            if article.get("authored_comparison") and not configs:
                assert configs == []
            elif article["slug"] == "countertop-dishwasher-for-small-households":
                # The main comparison links the four conditions instead of inputs.
                assert configs == []
                assert root_node.attrs["data-ps-purpose-mode"] == "links"
                assert root_node.attrs["data-ps-budget-mode"] == "off"
            else:
                assert "data-ps-purpose-mode" not in root_node.attrs
                assert json.loads(configs[0]) == [
                    {"id": c["id"], "label": c["label"]} for c in article["conditions"]
                ]


DECISION_STEPS_SLUGS = (
    "portable-power-station-guide",
    "compact-robot-vacuum-shortlist",
)


def _placement_inputs():
    import json

    root = Path(__file__).resolve().parents[2]
    catalog = json.loads(
        (
            root / "changes/reader-purchase-support-v1/purchase-support.v1.json"
        ).read_text()
    )
    templates = {
        slug: (
            root / "changes/reader-purchase-support-v1/articles" / (slug + ".html")
        ).read_text()
        for slug in DECISION_STEPS_SLUGS
    }
    return catalog, templates


def _positions(body):
    return (
        body.index('id="ps-decision-steps"'),
        body.index('id="ps-choose"'),
        body.index('id="ps-specs"'),
    )


def test_decision_steps_render_where_declared():
    from copy import deepcopy

    from raos.application.editorial.purchase_support import render_comparison

    catalog, templates = _placement_inputs()
    declared = [a for a in catalog["articles"] if a.get("decision_steps")]
    assert {a["slug"] for a in declared} == set(DECISION_STEPS_SLUGS)
    for article in declared:
        # Every article states where its steps go; there is no implicit default.
        assert "placement" in article["decision_steps"], article["slug"]
        for placement in ("before_conditions", "after_conditions", "after_specs"):
            variant = deepcopy(article)
            variant["decision_steps"]["placement"] = placement
            body, _ = render_comparison(
                variant, catalog, templates[article["slug"]], "test-placement"
            )
            assert body.count('id="ps-decision-steps"') == 1
            i, c, s = _positions(body)
            if placement == "before_conditions":
                assert i < c < s, (article["slug"], placement)
            elif placement == "after_conditions":
                assert c < i < s, (article["slug"], placement)
                assert body.index("</section>", c) < i
            else:
                assert c < s < i, (article["slug"], placement)
                assert body.index("</section>", s) < i
        body, _ = render_comparison(
            article, catalog, templates[article["slug"]], "test-placement"
        )
        i, c, s = _positions(body)
        expected = {
            "before_conditions": i < c,
            "after_conditions": c < i < s,
            "after_specs": s < i,
        }
        assert expected[article["decision_steps"]["placement"]], article["slug"]
        # The generated body (authored templates included) matches the declaration.
        generated = (
            Path(__file__).resolve().parents[2]
            / "changes/wordpress-direct-publish-v1/articles"
            / (article["slug"] + ".html")
        ).read_text()
        assert generated.count('id="ps-decision-steps"') == 1
        i, c, s = _positions(generated)
        expected = {
            "before_conditions": i < c,
            "after_conditions": c < i < s,
            "after_specs": s < i,
        }
        assert expected[article["decision_steps"]["placement"]], article["slug"]


@pytest.mark.parametrize(
    ("placement", "code"),
    [
        (None, "PURCHASE_DECISION_STEPS_PLACEMENT_REQUIRED"),
        ("after_offers", "PURCHASE_DECISION_STEPS_PLACEMENT_INVALID"),
    ],
)
def test_decision_steps_without_a_valid_placement_are_rejected(placement, code):
    from copy import deepcopy

    from raos.application.editorial.purchase_support import render_comparison

    catalog, templates = _placement_inputs()
    slug = DECISION_STEPS_SLUGS[0]
    article = deepcopy(next(a for a in catalog["articles"] if a["slug"] == slug))
    article["decision_steps"].pop("placement", None)
    if placement is not None:
        article["decision_steps"]["placement"] = placement
    with pytest.raises(ValueError, match=code):
        render_comparison(article, catalog, templates[slug], "test-placement")
