"""Authorized media is frozen verbatim and has independent image-link bindings."""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from base64 import b64encode
from zlib import compress
import subprocess
import shutil

import pytest

from raos.application.editorial.purchase_support import resolve_product_media
from raos.application.editorial.reader_html import fragment

ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)


# Explicit editorial acceptance: unknown images cannot reappear merely because a
# matching ID is added to the catalog or a merchant changes its generic picture.
EXPECTED_MEDIA = {
    "countertop-dishwasher-for-small-households": {
        "PRD-PANASONIC-NP-TSP1",
        "PRD-PANASONIC-NP-TMLK1",
        "PRD-THANKO-RAKUA-MINI-COLOR",
        "PRD-SIROCA-SS-MA251",
    },
    "lightweight-carry-on-suitcase-under-3kg": {
        "PRD-SAMSONITE-C-LITE-CS2-09007",
        "PRD-FREQUENTER-LIEVE-1-250",
        "PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002",
        "PRD-PROTECA-AEROFLEX-DX2-01521",
    },
    "compact-robot-vacuum-shortlist": {
        "PRD-IROBOT-ROOMBA-PLUS-515-COMBO",
        "PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY",
        "PRD-SWITCHBOT-K11-PRO",
        "PRD-SWITCHBOT-K10-PRO-COMBO",
    },
    "portable-power-station-guide": {
        "PRD-ECOFLOW-DELTA3-CLASSIC",
        "PRD-JACKERY-500-NEW",
        "PRD-BLUETTI-AC70",
        "PRD-ANKER-SOLIX-C300",
    },
    "carry-on-suitcase-comparison": {
        "PRD-ACE-DIFFERENCE-05721",
        "PRD-ACE-CRESTA-06316",
        "PRD-ACE-MAXPASS4-01471",
    },
    "carry-on-suitcase-under-100-seats": {
        "PRD-BERMAS-INTER-CITY-60524",
        "PRD-ACE-PALISADES3-Z-06910",
        "PRD-PROTECA-STARIA-CXR-02350",
        "PRD-PROTECA-FRESTER-EX-01550",
    },
    "front-open-carry-on-suitcase-with-stopper": {
        "PRD-INNOVATOR-INV50",
        "PRD-ACE-DIFFERENCE-05721",
        "PRD-BERMAS-INTER-CITY-II-60561",
        "PRD-PROTECA-FRESTER-EX-01551",
    },
    "roomba-mini-vs-switchbot-k11-pro": {
        "PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY",
        "PRD-SWITCHBOT-K11-PRO",
        "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",
    },
    "solota-vs-rakua-mini-plus": {
        "PRD-PANASONIC-NP-TMLK1",
        "PRD-THANKO-RAKUA-MINI-PLUS",
    },
    "anker-solix-c300-c800-c1000-differences": {
        "PRD-ANKER-SOLIX-C1000",
        "PRD-ANKER-SOLIX-C1000-GEN2",
        "PRD-ANKER-SOLIX-C800-PLUS",
        "PRD-ANKER-SOLIX-C300",
    },
    "compact-dishwasher-comparison": {
        "PRD-PANASONIC-NP-TMLK1",
        "PRD-THANKO-RAKUA-MINI-PLUS",
        "PRD-THANKO-RAKUA-MINI-COLOR",
        "PRD-THANKO-TK-MDW22W",
    },
    "standard-dishwasher-comparison": {
        "PRD-STANDARD-DISHWASHER-STTDWADW",
        "PRD-PANASONIC-NP-TSP1",
        "PRD-SIROCA-SS-MA251",
        "PRD-STANDARD-DISHWASHER-SS-M171",
        "PRD-STANDARD-DISHWASHER-PDW-M151",
        "PRD-STANDARD-DISHWASHER-SS-MU251",
        "PRD-STANDARD-DISHWASHER-AX-S7",
        "PRD-STANDARD-DISHWASHER-DWS-33B-W",
        "PRD-STANDARD-DISHWASHER-NP-TCR5-W",
        "PRD-STANDARD-DISHWASHER-TKDWSLHWH",
        "PRD-STANDARD-DISHWASHER-NP-TSK2",
        "PRD-STANDARD-DISHWASHER-TKDWWDHWH",
        "PRD-STANDARD-DISHWASHER-ADW-M28B",
    },
    "large-dishwasher-comparison": {
        "PRD-LARGE-DISHWASHER-SS-LH451",
        "PRD-LARGE-DISHWASHER-ADW-L40B",
        "PRD-LARGE-DISHWASHER-NP-TA5",
        "PRD-LARGE-DISHWASHER-NP-TZ500",
        "PRD-LARGE-DISHWASHER-NP-TH5",
        "PRD-LARGE-DISHWASHER-SS-LA451",
    },
    "small-carry-on-suitcase-comparison": {
        "PRD-INNOVATOR-INV50",
        "PRD-SMALL-CARRY-ON-SUITCASE-RIMOWA-82353704",
        "PRD-SAMSONITE-C-LITE-CS2-09007",
        "PRD-FREQUENTER-LIEVE-1-250",
        "PRD-BERMAS-INTER-CITY-II-60561",
        "PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002",
        "PRD-ACE-CRESTA-06316",
        "PRD-PROTECA-AEROFLEX-DX2-01521",
        "PRD-SMALL-CARRY-ON-SUITCASE-MUJI-76431312",
        "PRD-SMALL-CARRY-ON-SUITCASE-LEGEND-WALKER-5208-49",
        "PRD-SMALL-CARRY-ON-SUITCASE-TUMI-0228793DTX",
        "PRD-SMALL-CARRY-ON-SUITCASE-DELSEY-D00167680106",
    },
    # next30 Wave 1: the five dish racks have no approved seller, so their
    # image_review stays UNVERIFIED and no photo is projected for these three.
    "dish-rack-installation-measurement": set(),
    "slim-dish-rack-under-20cm": set(),
    "dish-rack-no-space": set(),
}


def inputs():
    return (
        json.loads(
            (
                ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
            ).read_text()
        ),
        json.loads((THEME / "assets/rakuten-product-media.json").read_text()),
        (THEME / "assets/images/roomba-mini-official.jpg").read_bytes(),
    )


def project_conditions(body, article):
    for entry in article.get("condition_media", {}).values():
        placeholder = (
            '<div class="ps-condition-product-media" data-ps-media-product="'
            + entry["product_id"]
            + '" data-ps-condition="'
            + entry["condition_id"]
            + '"></div>'
        )
        assert body.count(placeholder) == 1
        body = body.replace(placeholder, placeholder[:-6] + entry["html"] + "</div>")
    return body


def test_only_reviewed_in_scope_media_and_unmodified_links_are_snapshot_bound():
    spec = importlib.util.spec_from_file_location(
        "purchase_media_build", ROOT / "scripts/build_reader_purchase_support_v1.py"
    )
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    outputs = build.build()
    catalog, records, _ = inputs()
    runtime = json.loads(outputs[build.RUNTIME_OUTPUT_PATH])
    image_count = 0
    official_count = 0
    for article in runtime["articles"]:
        body = outputs[
            ROOT
            / "changes/wordpress-direct-publish-v1/articles"
            / (article["slug"] + ".html")
        ]
        assert sha256(body.encode()).hexdigest() == article["body_sha256"]
        assert not any(n.has("ps-product-image") for n in fragment(body).walk())
        if article["kind"] in {"comparison", "curated_comparison"}:
            assert set(article["media"]) == EXPECTED_MEDIA[article["slug"]]
        for pid, markup in article["media"].items():
            placeholder = (
                '<div class="ps-product-media" data-ps-media-product="'
                + pid
                + '"></div>'
            )
            assert body.count(placeholder) == 1
            body = body.replace(placeholder, markup)
        body = project_conditions(body, article)
        image_bindings = [
            b for b in article["bindings"] if b["offer_id"].startswith("image-")
        ]
        image_count += len(image_bindings)
        root = fragment(body)
        official_count += len(
            [n for n in root.walk() if n.has("ps-official-product-photo")]
        )
        for photo in (n for n in root.walk() if n.has("ps-official-product-photo")):
            assert photo.find(tag="img")[0].attrs["src"] == (
                "/wp-content/themes/kurashinoshirube-child/assets/images/roomba-mini-official.jpg"
            ), "The same frozen theme image must work on the isolated preview origin."
        for b in image_bindings:
            assert len(b) == 10 and b["placement"] in {"product_card", "top_summary"}
            if len(b) == 10:
                assert (
                    b["link_purpose"] == "affiliate_purchase"
                    and b["affiliate"] == "true"
                )
            wrapper = next(
                n for n in root.walk() if n.attrs.get("data-raos-cta-id") == b["cta_id"]
            )
            assert wrapper.tag == "div"
            link = wrapper.find(tag="a")[0]
            assert not any(k.startswith("data-raos-") for k in link.attrs)
            assert (
                sha256(link.attrs["href"].encode()).hexdigest()
                == sha256(b["href"].encode()).hexdigest()
            )
            record = next(r for r in records if r["product_id"] == b["product_id"])
            size = b["offer_id"].rsplit("-", 1)[1]
            # Hash exact substring boundaries instead of serializing the HTML parser.
            start = body.index('data-raos-cta-id="' + b["cta_id"] + '"')
            start = body.index(">", start) + 1
            end = body.index("</div>", start)
            assert (
                sha256(body[start:end].encode()).hexdigest()
                == sha256(record["sources"][size].encode()).hexdigest()
            )
    # The same reviewed Mini/K11 media is bound to both robot comparisons;
    # recovered exact-model photos now cover every comparison product.
    assert image_count >= 138 and official_count >= 2
    assert all(not o["offer_id"].startswith("image-") for o in catalog["offers"])


def test_source_snippet_or_official_asset_drift_requires_new_review():
    catalog, records, official = inputs()
    altered = deepcopy(records)
    target = next(
        r for r in altered if r["product_id"] == catalog["products"][0]["product_id"]
    )
    target["sources"]["300"] += " "
    with pytest.raises(ValueError, match="PURCHASE_MEDIA_(SOURCE|RECORD)_DRIFT"):
        resolve_product_media(catalog, altered, official)
    with pytest.raises(ValueError, match="PURCHASE_OFFICIAL_MEDIA_DRIFT"):
        resolve_product_media(catalog, records, official + b"drift")


def test_media_click_uses_outer_binding_without_sending_url():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    result = subprocess.run(
        [node, "tests/purchase_support/purchase_media_analytics_harness.mjs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_public_media_projection_requires_exact_runtime_and_applied_body():
    runtime_path = THEME / "assets/purchase-support.v1.json"
    runtime = json.loads(runtime_path.read_text())
    assert runtime_path.stat().st_size <= 1048576
    comparisons = [
        a
        for a in runtime["articles"]
        if a["kind"] in {"comparison", "curated_comparison"}
    ]
    expected_figures = {slug: len(pids) for slug, pids in EXPECTED_MEDIA.items()}
    assert {a["slug"] for a in comparisons} == set(EXPECTED_MEDIA)
    guide = next(
        a for a in runtime["articles"] if a["slug"] == "dishwasher-water-supply-methods"
    )
    assert len(guide["guide_product_scope"]["main"]) == 4
    assert len(guide["guide_product_scope"]["supplementary"]) == 1
    comparisons.append(guide)
    expected_figures[guide["slug"]] = 5
    total_photos = 0
    for article in comparisons:
        body = (
            ROOT
            / "changes/wordpress-direct-publish-v1/articles"
            / (article["slug"] + ".html")
        ).read_text()
        rendered = body
        for pid, markup in article["media"].items():
            rendered = rendered.replace(
                '<div class="ps-product-media" data-ps-media-product="'
                + pid
                + '"></div>',
                markup,
            )
        rendered = project_conditions(rendered, article)
        snapshot = {
            "id": 41,
            "slug": article["slug"],
            "title": "test",
            "excerpt": "test",
            "post_type": "post",
            "block_markup": body,
        }
        for mode in [
            "valid",
            "measurement-off",
            "owner",
            "body-tamper",
            "runtime-tamper",
            "no-snapshot",
        ] + (
            ["missing-guide-scope", "duplicate-guide-scope", "unregistered-guide-media"]
            if article["kind"] == "guide"
            else []
        ):
            result = subprocess.run(
                [
                    "php",
                    "-r",
                    (
                        ROOT
                        / "tests/purchase_support/purchase_media_projection_harness.php"
                    )
                    .read_text()
                    .removeprefix("<?php"),
                    str(THEME / "inc/purchase-support.php"),
                    mode,
                    b64encode(
                        compress(json.dumps({"snapshot": snapshot}).encode())
                    ).decode(),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            assert result.returncode == 0, "PHP projection harness failed"
            value = json.loads(result.stdout)
            assert value["unknown_unchanged"]
            if mode in {"valid", "measurement-off", "owner"}:
                assert value["sha256"] == sha256(rendered.encode()).hexdigest()
                assert value["figures"] == expected_figures[article["slug"]] + len(
                    article.get("condition_media", {})
                )
            else:
                assert value["unchanged"] and value["figures"] == 0
        total_photos += len(article["media"])
    assert total_photos == sum(map(len, EXPECTED_MEDIA.values())) + 5


def test_media_projection_changes_snapshot_even_when_placeholder_body_is_stable():
    from raos.application.editorial.purchase_support import compile_articles

    catalog, records, official = inputs()
    media = resolve_product_media(catalog, records, official)
    templates = {
        p.stem: p.read_text()
        for p in (ROOT / "changes/reader-purchase-support-v1/articles").glob("*.html")
    }
    guides = json.loads(
        (
            ROOT / "changes/editorial-portfolio-v3/local-reader-guides.v1.json"
        ).read_text()
    )
    now = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
    _, before = compile_articles(catalog, templates, guides, media, now=now)
    modified = deepcopy(media)
    modified["PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY"]["sha256"] = "f" * 64
    _, after = compile_articles(catalog, templates, guides, modified, now=now)
    for a, b in zip(before["articles"], after["articles"], strict=True):
        if a["slug"] in {
            "compact-robot-vacuum-shortlist",
            "roomba-mini-vs-switchbot-k11-pro",
        }:
            assert a["snapshot_id"] != b["snapshot_id"]
        else:
            assert a["snapshot_id"] == b["snapshot_id"]


def test_unverified_images_are_withheld_without_deleting_product_facts():
    catalog, records, official = inputs()
    blocked = {
        "PRD-BERMAS-INTER-CITY-60524",
        "PRD-INNOVATOR-INV50",
    }
    products = {p["product_id"]: p for p in catalog["products"]}
    for pid in blocked:
        # Revoke a now-verified image in this fixture: a registry entry alone
        # must never bypass a later failed identity review.
        products[pid]["image_review"] = {
            "state": "UNVERIFIED",
            "reason": "同一型番・構成の画像確認を撤回したテストケース",
        }
        assert products[pid]["image_review"]["reason"]
        assert products[pid]["facts"] and products[pid]["official_url"].startswith(
            "https://"
        )
    media = resolve_product_media(catalog, records, official)
    for pid in blocked:
        assert media[pid] == {
            "withheld": True,
            "reason": products[pid]["image_review"]["reason"],
        }
    # An article-specific scope exclusion does not revoke the approved same-product
    # photo in the original four-model dishwasher comparison.
    pair = next(a for a in catalog["articles"] if a["post_id"] == 86)
    assert "PRD-PANASONIC-NP-TMLK1" not in pair.get("media_exclusions", {})
    assert "solota-vs-rakua-mini-plus" in media["PRD-PANASONIC-NP-TMLK1"]["slugs"]
    assert "PRD-PANASONIC-NP-TMLK1" in media
