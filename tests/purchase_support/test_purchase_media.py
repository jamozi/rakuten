"""Authorized media is frozen verbatim and has independent image-link bindings."""

from base64 import b64encode
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import shutil

import pytest

from raos.application.editorial.purchase_support import resolve_product_media
from raos.application.editorial.reader_html import fragment

ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)


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


def test_all_sixteen_photos_and_thirty_unmodified_image_links_are_snapshot_bound():
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
        for pid, markup in article["media"].items():
            placeholder = (
                '<div class="ps-product-media" data-ps-media-product="'
                + pid
                + '"></div>'
            )
            assert body.count(placeholder) == 1
            body = body.replace(placeholder, markup)
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
            assert len(b) == 8 and b["placement"] == "product_card"
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
    assert image_count == 30 and official_count == 1
    assert len(catalog["offers"]) == 6
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
    assert runtime_path.stat().st_size <= 262144
    comparisons = [a for a in runtime["articles"] if a["kind"] == "comparison"]
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
        ]:
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
                    b64encode(json.dumps({"snapshot": snapshot}).encode()).decode(),
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
                assert value["figures"] == 4
            else:
                assert value["unchanged"] and value["figures"] == 0
        total_photos += len(article["media"])
    assert total_photos == 16


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
    _, before = compile_articles(catalog, templates, guides, media)
    modified = deepcopy(media)
    modified["PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY"]["sha256"] = "f" * 64
    _, after = compile_articles(catalog, templates, guides, modified)
    for a, b in zip(before["articles"], after["articles"], strict=True):
        if a["slug"] == "compact-robot-vacuum-shortlist":
            assert a["snapshot_id"] != b["snapshot_id"]
        else:
            assert a["snapshot_id"] == b["snapshot_id"]
