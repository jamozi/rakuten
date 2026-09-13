"""Home media remains a six-product, exact-source projection, never a CMS bypass."""

from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import pytest

from raos.application.editorial.home_product_media import (
    GROUPS,
    MINI,
    MINI_LINK,
    MINI_NAME,
    MODELS,
    SCHEMA,
    bind_home_product_media,
    build_home_product_media,
    slot,
)
from raos.application.editorial.purchase_support import canonical
from raos.application.editorial.reader_html import fragment

ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)


def inputs():
    # Keep the retired feature's integrity tests independent of current article
    # media reviews. The live homepage uses anonymous lifestyle imagery.
    fixture = json.loads(
        (ROOT / "tests/purchase_support/fixtures/legacy-home-media.v1.json").read_text()
    )
    return (
        fixture["catalog"],
        {
            "schema": SCHEMA,
            "post_id": 15,
            "post_type": "page",
            "slug": "home",
            "groups": {k: list(v) for k, v in GROUPS.items()},
        },
        fixture["records"],
        (THEME / "assets/images/roomba-mini-official.jpg").read_bytes(),
    )


def test_six_linked_products_preserve_rakuten_sources_and_mini_credit():
    args = inputs()
    before = deepcopy(args)
    p = build_home_product_media(*args)
    assert args == before
    assert set(p["products"]) == set(MODELS)
    assert set(p["slots"]) == {41, 83, 30}
    assert sum(row["html"].count("<img") for row in p["products"].values()) == 6
    for pid, row in p["products"].items():
        dom = fragment(row["html"])
        images = [n for n in dom.walk() if n.tag == "img"]
        assert len(images) == 1 and images[0].parent.tag == "a"
        assert not any(
            key.startswith("data-raos-") for n in dom.walk() for key in n.attrs
        )
        assert row["sha256"] == sha256(row["html"].encode()).hexdigest()
        if pid != MINI:
            record = next(r for r in args[2] if r["product_id"] == pid)
            assert row["html"].count(record["sources"]["240"]) == 1
            assert record["sources"]["300"] not in row["html"]
            assert "（楽天市場）" in row["html"]
        else:
            assert images[0].parent.attrs["href"] == MINI_LINK
            assert MINI_NAME in row["html"]
            assert (
                'href="https://irobotjp.mediaroom.com/media-kits?item=28"'
                in row["html"]
            )
            article = (
                ROOT
                / "changes/wordpress-direct-publish-v1/articles/compact-robot-vacuum-shortlist.html"
            ).read_text()
            assert 'id="' + MINI_LINK.split("#")[1] + '"' in article
    body = "<main>" + "".join(p["slots"].values()) + "</main>"
    bound = bind_home_product_media(p, body)
    assert bound["body_sha256"] == sha256(body.encode()).hexdigest()
    assert "slots" not in bound
    assert "slots" in p


@pytest.mark.parametrize(
    "case",
    [
        "home_id",
        "home_slug",
        "extra_product",
        "wrong_model",
        "missing_product",
        "duplicate_product",
        "excluded",
        "unverified",
        "no_orderable_offer",
        "offer_model",
        "source_scope",
        "review_evidence",
        "record",
        "snippet",
        "official_bytes",
    ],
)
def test_unapproved_or_changed_source_rejected(case):
    cat, config, records, image = inputs()
    pid = GROUPS["41"][0]
    product = next(p for p in cat["products"] if p["product_id"] == pid)
    record = next(r for r in records if r["product_id"] == pid)
    article = next(a for a in cat["articles"] if a["post_id"] == 41)
    if case == "home_id":
        config["post_id"] = 16
    elif case == "home_slug":
        config["slug"] = "arbitrary-page"
    elif case == "extra_product":
        config["groups"]["41"].append("PRD-ANKER-SOLIX-C300")
    elif case == "wrong_model":
        product["exact_model"] = "NP-TML1-W"
    elif case == "missing_product":
        cat["products"].remove(product)
    elif case == "duplicate_product":
        cat["products"].append(deepcopy(product))
    elif case == "excluded":
        article["media_exclusions"] = {pid: "Unverified reuse scope"}
    elif case == "unverified":
        product["image_review"]["state"] = "UNVERIFIED"
    elif case == "no_orderable_offer":
        for o in cat["offers"]:
            if o["product_id"] == pid:
                o["identity_verified"] = False
    elif case == "offer_model":
        for o in cat["offers"]:
            if o["product_id"] == pid:
                o["product_model"] = "wrong-model"
    elif case == "source_scope":
        article["product_ids"].remove(pid)
    elif case == "review_evidence":
        product["image_review"]["evidence"] = "guessed-rights"
    elif case == "record":
        record["shop_name"] = "different-seller"
    elif case == "snippet":
        record["sources"]["240"] += "<img src='extra'>"
    elif case == "official_bytes":
        image += b"changed"
    with pytest.raises(ValueError):
        build_home_product_media(cat, config, records, image)


def test_image_only_guard_rejects_price_even_if_source_digests_are_rebound():
    cat, config, records, image = inputs()
    pid = GROUPS["41"][0]
    product = next(p for p in cat["products"] if p["product_id"] == pid)
    record = next(r for r in records if r["product_id"] == pid)
    record["sources"]["240"] = record["sources"]["240"].replace("</a>", "1,000円</a>")
    product["image_review"]["source_sha256"]["240"] = sha256(
        record["sources"]["240"].encode()
    ).hexdigest()
    product["image_review"]["record_sha256"] = sha256(
        canonical(record).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="IMAGE_ONLY"):
        build_home_product_media(cat, config, records, image)


@pytest.mark.parametrize("case", ["missing", "duplicate", "unknown"])
def test_home_slots_are_exact_and_unique(case):
    p = build_home_product_media(*inputs())
    body = "".join(p["slots"].values())
    first = slot(GROUPS["41"][0])
    if case == "missing":
        body = body.replace(first, "")
    elif case == "duplicate":
        body += first
    else:
        body += '<div class="ks-home-product-slot" data-ks-home-product="PRD-UNKNOWN"></div>'
    with pytest.raises(ValueError, match="SLOT"):
        bind_home_product_media(p, body)


def test_php_home_projection_preserves_public_snapshot_and_payload_boundaries():
    projection = build_home_product_media(*inputs())
    body = "".join(projection["slots"].values())
    bound = bind_home_product_media(projection, body)
    php = (THEME / "inc/purchase-support.php").read_text()
    function = (
        "function kurashinoshirube_home_product_media"
        + php.split("function kurashinoshirube_home_product_media", 1)[1].split(
            "add_filter('the_content', 'kurashinoshirube_home_product_media'", 1
        )[0]
    )
    cases = [
        "valid",
        "local_valid",
        "local_wrong_current",
        "local_wrong_query",
        "local_wrong_snapshot",
        "local_wrong_slug",
        "local_wrong_front",
        "wrong_page",
        "wrong_current_post",
        "not_front",
        "draft",
        "password",
        "missing_snapshot",
        "stored_body",
        "runtime_digest",
        "body_digest",
        "product_digest",
        "product_model",
        "extra_product",
        "source_digest",
        "duplicate_slot",
    ]
    for case in cases:
        document = {
            "schema": "RAOS_SITE_EDITORIAL_METADATA_V1",
            "articles": {},
            "home_product_media": deepcopy(bound),
        }
        data = document["home_product_media"]
        pid = GROUPS["41"][0]
        if case == "body_digest":
            data["body_sha256"] = "0" * 64
        elif case == "product_digest":
            data["products"][pid]["html"] += "changed"
        elif case == "product_model":
            data["products"][pid]["exact_model"] = "wrong"
        elif case == "extra_product":
            data["products"]["PRD-ANKER-SOLIX-C300"] = deepcopy(data["products"][pid])
        elif case == "source_digest":
            data["products"][pid]["source_sha256"]["240"] = "not-hash"
        payload = json.dumps(document, ensure_ascii=False).encode()
        digest = "0" * 64 if case == "runtime_digest" else sha256(payload).hexdigest()
        request = {
            "body": body,
            "content": body + (slot(pid) if case == "duplicate_slot" else ""),
            "case": case,
            "payload": base64.b64encode(payload).decode(),
        }
        encoded = base64.b64encode(json.dumps(request).encode()).decode()
        program = (
            "const KURASHINOSHIRUBE_SITE_EDITORIAL_METADATA_SHA256 = '"
            + digest
            + "';\n"
            + r"""
$GLOBALS['input'] = json_decode(base64_decode('ENCODED'), true);
$GLOBALS['root'] = sys_get_temp_dir() . '/raos-home-media-' . bin2hex(random_bytes(8));
mkdir($GLOBALS['root'] . '/assets', 0700, true);
file_put_contents($GLOBALS['root'] . '/assets/site-editorial-metadata.v1.json', base64_decode($GLOBALS['input']['payload']));
function is_admin() { return false; }
function is_feed() { return false; }
function is_front_page() { return $GLOBALS['input']['case'] !== 'not_front'; }
function local_case() { return str_starts_with($GLOBALS['input']['case'], 'local_'); }
function get_option($key) { return $GLOBALS['input']['case'] === 'local_wrong_front' ? 6 : 5; }
function get_queried_object_id() { return local_case() ? ($GLOBALS['input']['case'] === 'local_wrong_query' ? 6 : 5) : ($GLOBALS['input']['case'] === 'wrong_page' ? 41 : 15); }
function get_the_ID() { return local_case() ? ($GLOBALS['input']['case'] === 'local_wrong_current' ? 6 : 5) : ($GLOBALS['input']['case'] === 'wrong_current_post' ? 41 : 15); }
function kurashinoshirube_is_local_preview() { return local_case(); }
function get_post_meta($id, $key, $single) {
 return array('id'=>$GLOBALS['input']['case']==='local_wrong_snapshot'?6:5,'post_type'=>'page','slug'=>$GLOBALS['input']['case']==='local_wrong_slug'?'other':'home','title'=>'Home','excerpt'=>'Excerpt','block_markup'=>$GLOBALS['input']['body']);
}
function get_stylesheet_directory() { return $GLOBALS['root']; }
function get_post_status($id) { return $GLOBALS['input']['case'] === 'draft' ? 'draft' : 'publish'; }
function get_post_field($field, $id, $context) {
    $values = array('post_name'=>'home','post_type'=>'page','post_title'=>'Home','post_excerpt'=>'Excerpt',
        'post_password'=>$GLOBALS['input']['case']==='password'?'secret':'',
        'post_content'=>$GLOBALS['input']['body'] . ($GLOBALS['input']['case']==='stored_body'?'changed':''));
    return $values[$field];
}
if (!local_case()) {
class RAOS_Codex_MCP_Owner_Direct {
    public static function public_article_snapshot($id) {
        if ($GLOBALS['input']['case'] === 'missing_snapshot') return null;
        return array('id'=>15,'post_type'=>'page','slug'=>'home','title'=>'Home','excerpt'=>'Excerpt','block_markup'=>$GLOBALS['input']['body']);
    }
}
}
""".replace("ENCODED", encoded)
            + function
            + r"""
$result = kurashinoshirube_home_product_media($GLOBALS['input']['content']);
echo json_encode(array('html'=>$result));
unlink($GLOBALS['root'] . '/assets/site-editorial-metadata.v1.json');
rmdir($GLOBALS['root'] . '/assets'); rmdir($GLOBALS['root']);
"""
        )
        run = subprocess.run(
            ["php", "-r", program], capture_output=True, text=True, check=False
        )
        assert run.returncode == 0, run.stderr
        result = json.loads(run.stdout)["html"]
        if case in {"valid", "local_valid"}:
            assert result.count('<figure class="ks-home-product-image"') == 6
            assert 'class="ks-home-product-slot"' not in result
        else:
            assert result == request["content"], case


def test_home_media_clicks_never_enter_article_analytics_even_with_consent():
    """No article attribution is inherited; denied consent also sends nothing."""
    projection = build_home_product_media(*inputs())
    for row in projection["products"].values():
        assert "data-raos-cta-type" not in row["html"]
        assert "data-raos-purchase-support" not in row["html"]
    program = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
for (const consent of [false, true]) {
  const events = {}, sent = [];
  const gtag = (...args) => sent.push(args); gtag.raosConsentGate = true;
  const window = {gtag, getCkyConsent: () => ({isUserActionCompleted:true,categories:{analytics:consent}}),
    wp_has_consent:()=>consent, _googlesitekitConsents:{analytics_storage:consent?'granted':'denied'},
    localStorage:{getItem:()=>null}};
  const document = {addEventListener:(name,fn)=>events[name]=fn,
    getElementById:()=>({type:'application/json',textContent:JSON.stringify({profile:'purchase-support-v1',enabled:true,debug_mode:true,bindings:[]})})};
  vm.runInNewContext(source,{window,document});
  for(let image=0;image<6;image++) for(const type of ['click','auxclick']) {
    const anchor = {closest:()=>null}; // Actual home markup has no article CTA ancestors.
    events[type]({type,button:type==='click'?0:1,isTrusted:true,target:{closest:()=>anchor}});
  }
  if(sent.length) throw new Error('Home media inherited article analytics');
}
"""
    run = subprocess.run(
        ["node", "-e", program, str(THEME / "assets/purchase-analytics.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
