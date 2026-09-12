"""Price ageing and cross-article identity regressions from the September audit."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

from raos.application.editorial.purchase_support import offer_panel, condition_summary
from raos.application.editorial.reader_html import fragment

ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)


def inputs():
    catalog = json.loads(
        (
            ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
        ).read_text()
    )
    product = catalog["products"][0]
    article = next(
        a
        for a in catalog["articles"]
        if product["product_id"] in a.get("product_ids", [])
    )
    offer = deepcopy(
        next(o for o in catalog["offers"] if o["product_id"] == product["product_id"])
    )
    offer.update(
        price_yen=123456,
        shipping_yen=None,
        required_items_yen=None,
        checked_at="2026-09-13T00:00:00Z",
        valid_until="2026-09-14T00:00:00Z",
        identity_verified=True,
        state="AVAILABLE",
        condition="new",
    )
    catalog["offers"] = [offer]
    return catalog, product, article


def test_cached_static_body_never_contains_price_numbers_even_before_expiry():
    catalog, product, article = inputs()
    for day in (13, 14):
        now = datetime(2026, 9, day, 1, tzinfo=timezone.utc)
        panel, _ = offer_panel(
            product, catalog, article, "ps-test", "final_summary", now=now
        )
        text = fragment(panel).text()
        assert "123,456" not in text and "123456" not in text
        assert 'data-ps-price-yen="123456"' in panel  # inert public observation
        assert 'class="ps-price-status"' in panel
        assert (
            "123,456"
            not in fragment(condition_summary(product, article, catalog, now)).text()
        )


def test_expired_unknown_or_wrong_identity_never_reappears_as_historical_subtotal():
    node = shutil.which("node")
    assert node
    script = r"""
const assert = require('node:assert/strict');
const context = {module:{exports:{}}};
require('node:vm').runInNewContext(require('node:fs').readFileSync(process.argv[1],'utf8'),context);
const {pricePresentation} = context.module.exports;
const checked = Date.parse('2026-09-13T00:00:00Z');
const offer = {checked_at:'2026-09-13T00:00:00Z',valid_until:'2026-09-14T00:00:00Z',
  identity_verified:true,state:'AVAILABLE',condition:'new',price_yen:123456,
  shipping_yen:null,required_items_yen:null,total_scope_complete:false};
let result = pricePresentation(offer,checked+1);
assert.equal(result.state,'INCOMPLETE');
assert.match(result.text,/123,456/); assert.match(result.text,/小計/);
assert.match(result.text,/送料：未確認/);
for (const [value,now] of [[offer,checked+86400000],[offer,checked-1],
  [{...offer,identity_verified:false},checked+1],[{...offer,state:'SOLD_OUT'},checked+1]]) {
  assert.doesNotMatch(pricePresentation(value,now).text,/123,456|123456/);
}
const total={...offer,shipping_yen:0,required_items_yen:0,total_scope_complete:true};
assert.equal(pricePresentation(total,checked+1).state,'CURRENT');
assert.match(pricePresentation(total,checked+1).text,/購入総額：123,456/);
const shorter={...total,valid_until:'2026-09-13T00:01:00Z'};
assert.equal(pricePresentation(shorter,checked+60000).state,'EXPIRED');
"""
    result = subprocess.run(
        [node, "-e", script, str(THEME / "assets/purchase-support.js")],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_disclosure_matches_admitted_links_and_all_editorial_tables_are_contained():
    runtime = json.loads((THEME / "assets/purchase-support.v1.json").read_text())
    for article in runtime["articles"]:
        if not article.get("bindings"):
            continue
        body = fragment(
            (
                ROOT
                / "changes/wordpress-direct-publish-v1/articles"
                / (article["slug"] + ".html")
            ).read_text()
        )
        ads = any(b.get("affiliate") == "true" for b in article["bindings"])
        notice = body.find(cls="ps-disclosure")
        assert len(notice) == 1
        assert ("リンクはありません" not in notice[0].text()) == ads
        for table in body.find(tag="table"):
            parent = table.parent
            contained = False
            while parent:
                contained |= any(
                    parent.has(name)
                    for name in (
                        "ps-table-scroll",
                        "comparison-table-wrap",
                        "table-scroll",
                    )
                )
                parent = parent.parent
            assert contained, article["slug"]
