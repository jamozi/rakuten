#!/usr/bin/env python3
"""Offline checks of anonymous public responses; no network or CMS writes.

Input is a RAOSAnonymousPageBatchV1 JSON export, not owner-private snapshots.
PASS means only the listed checks passed. It is not proof of indexing, legal
compliance, product accuracy, merchant availability, conversions or revenue.
No outbound URLs, article prose or account identifiers appear in the report.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from raos.domain.editorial.purchase_support import (
    offer_states,
    resolve_offer,
)  # noqa: E402

ORIGIN = "https://kurashinoshirube.com"
HOST = "kurashinoshirube.com"
MAX_BYTES = 24 * 1024 * 1024
AFFILIATE_HOSTS = frozenset(
    {
        "hb.afl.rakuten.co.jp",
        "af.moshimo.com",
        "px.a8.net",
        "ck.jp.ap.valuecommerce.com",
        "click.linksynergy.com",
        "h.accesstrade.net",
        "t.afi-b.com",
    }
)
VOID = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()
)
DISCLOSURE = re.compile(r"広告[・をが]|アフィリエイトリンク[をが]|広告を含|広告が含")


def _path(value):
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value.startswith("//")
    ):
        raise ValueError("PATH_INVALID")
    decoded = unquote(value)
    if any(c in decoded for c in ("\\", "\r", "\n", "\x00")):
        raise ValueError("PATH_INVALID")
    parsed = urlsplit(decoded)
    if (
        parsed.netloc
        or parsed.scheme
        or parsed.query
        or parsed.fragment
        or ".." in parsed.path.split("/")
    ):
        raise ValueError("PATH_INVALID")
    return value


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.position = 0
        self.ids = []
        self.robots = []
        self.canonicals = []
        self.h1_count = 0
        self.title = []
        self.description = []
        self.links = []
        self.disclosures = []
        self.visible_text = []
        self.cost_container = False
        self.cost_script = False
        self.elements = []
        self.element_stack = []
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        if len(self.elements) >= 100000 or len(self.stack) >= 256:
            raise ValueError("HTML_COMPLEXITY_LIMIT")
        self.position += 1
        attributes = dict(attrs)
        hidden = (
            any(x[1] for x in self.stack)
            or "hidden" in attributes
            or attributes.get("aria-hidden") == "true"
            or bool(
                re.search(
                    r"display\s*:\s*none|visibility\s*:\s*hidden",
                    attributes.get("style") or "",
                    re.I,
                )
            )
            or tag in {"script", "style", "template", "noscript"}
        )
        if "id" in attributes:
            self.ids.append(attributes["id"])
        node = {
            "tag": tag,
            "attrs": attributes,
            "hidden": hidden,
            "text": "",
            "parent": self.element_stack[-1] if self.element_stack else None,
        }
        self.elements.append(node)
        if tag == "h1":
            self.h1_count += 1
        if tag == "meta":
            name = (attributes.get("name") or "").lower()
            if name in {"robots", "googlebot"}:
                self.robots.append(attributes.get("content") or "")
            if name == "description":
                self.description.append(attributes.get("content") or "")
        if (
            tag == "link"
            and "canonical" in (attributes.get("rel") or "").lower().split()
        ):
            self.canonicals.append(attributes.get("href") or "")
        if tag == "a" and attributes.get("href") and not hidden:
            self.links.append(
                (
                    attributes["href"],
                    set((attributes.get("rel") or "").lower().split()),
                    self.position,
                )
            )
        if attributes.get("data-raos-cost-calculator") == "v1":
            self.cost_container = True
        if tag == "script":
            parsed = urlsplit(urljoin(ORIGIN, attributes.get("src") or ""))
            if (
                parsed.scheme == "https"
                and parsed.hostname == HOST
                and parsed.path.endswith("/local-running-cost.js")
            ):
                self.cost_script = True
        if tag not in VOID:
            self.stack.append((tag, hidden))
            self.element_stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                del self.element_stack[index:]
                break

    def handle_data(self, data):
        self.position += 1
        for node in self.element_stack:
            node["text"] += data
        if any(tag == "title" for tag, _ in self.stack):
            self.title.append(data)
        if not any(hidden for _, hidden in self.stack):
            self.visible_text.append(data)
            if DISCLOSURE.search(data):
                self.disclosures.append(self.position)


def purchase_inventory(doc, *, article_id, post_id=None, offers=(), now=None):
    """Observed links plus explicit UNKNOWNs, never evidence inferred from a URL."""
    rows = []
    by_offer = {o["offer_id"]: o for o in offers}
    names = {}
    for node in doc.elements:
        if node["tag"] not in {"h2", "h3"}:
            continue
        parent = node["parent"]
        while parent:
            product = parent["attrs"].get("data-ps-product") or parent["attrs"].get(
                "data-raos-product-id"
            )
            if product:
                names.setdefault(product, node["text"].strip())
                break
            parent = parent["parent"]
    for node in doc.elements:
        a = node["attrs"]
        if node["tag"] != "a" or not a.get("href"):
            continue
        parents, parent = [node], node["parent"]
        while parent:
            parents.append(parent)
            parent = parent["parent"]
        context = next(
            (p["attrs"] for p in parents if p["attrs"].get("data-raos-cta-id")), a
        )
        product = next(
            (
                p["attrs"].get("data-raos-product-id")
                or p["attrs"].get("data-ps-product")
                for p in parents
                if p["attrs"].get("data-raos-product-id")
                or p["attrs"].get("data-ps-product")
            ),
            None,
        )
        href = a["href"]
        target = urlsplit(href)
        purchase_anchor = target.fragment and (
            "購入" in node["text"] or target.fragment.startswith("ps-seller-")
        )
        if (
            not product
            and not purchase_anchor
            and not context.get("data-raos-placement")
        ):
            continue
        offer_id = context.get("data-raos-offer-id")
        offer = by_offer.get(offer_id, {})
        purpose = context.get("data-raos-link-purpose")
        affiliate = target.hostname in AFFILIATE_HOSTS or (
            purpose == "affiliate_purchase"
            or (
                resolve_offer(offer)["affiliate_ready"]
                and resolve_offer(offer)["href"] == href
            )
        )
        kind = (
            "internal"
            if not target.netloc and target.fragment
            else (
                "affiliate"
                if affiliate
                else (
                    "merchant_direct"
                    if purpose == "merchant_purchase"
                    or "ps-offer-link" in (a.get("class") or "").split()
                    else "official_spec"
                )
            )
        )
        rows.append(
            {
                "article_id": article_id,
                "post_id": post_id,
                "product_id": product,
                "product_name": names.get(product),
                "variant": offer.get("variant"),
                "seller_id": context.get("data-raos-seller-id"),
                "offer_id": offer_id,
                "merchant_url": offer.get("merchant_url")
                or (offer.get("url") if not offer.get("affiliate") else None),
                "affiliate_url": offer.get("affiliate_url")
                or (offer.get("url") if offer.get("affiliate") else None),
                "rendered_href": href,
                "link_type": kind,
                "offer_state": offer.get("state", "UNKNOWN"),
                "affiliate_ready": (
                    resolve_offer(offer)["affiliate_ready"] if offer else "UNKNOWN"
                ),
                "price_state": (
                    offer_states(offer, now or datetime.now(timezone.utc))[
                        "price_state"
                    ]
                    if offer
                    else "UNKNOWN"
                ),
                "placement": context.get("data-raos-placement"),
                "target_anchor": target.fragment or None,
            }
        )
    for node in doc.elements:
        if "ps-product-offers" not in (node["attrs"].get("class") or "").split():
            continue
        product = node["attrs"].get("data-ps-product")
        if not any(o.get("product_id") == product for o in offers) and not any(
            r["product_id"] == product
            and r["link_type"] in {"merchant_direct", "affiliate"}
            for r in rows
        ):
            rows.append(
                dict.fromkeys(
                    (
                        "variant",
                        "seller_id",
                        "offer_id",
                        "merchant_url",
                        "affiliate_url",
                        "rendered_href",
                        "placement",
                        "target_anchor",
                    )
                )
                | {
                    "article_id": article_id,
                    "post_id": post_id,
                    "product_id": product,
                    "product_name": names.get(product),
                    "link_type": "unavailable",
                    "offer_state": "UNKNOWN",
                    "affiliate_ready": "UNKNOWN",
                    "price_state": "UNKNOWN",
                }
            )
    if not any(row["product_id"] for row in rows):
        # Older two-product articles can contain only a comparison table. Keep
        # observed names while leaving machine identities and seller evidence unknown.
        columns = [
            n["text"].strip()
            for n in doc.elements
            if n["tag"] == "th" and n["attrs"].get("scope") == "col"
        ]
        if len(columns) == 3:
            for name in columns[1:]:
                rows.append(
                    dict.fromkeys(
                        (
                            "product_id",
                            "variant",
                            "seller_id",
                            "offer_id",
                            "merchant_url",
                            "affiliate_url",
                            "rendered_href",
                            "placement",
                            "target_anchor",
                        )
                    )
                    | {
                        "article_id": article_id,
                        "post_id": post_id,
                        "product_name": name,
                        "link_type": "unavailable",
                        "offer_state": "UNKNOWN",
                        "affiliate_ready": "UNKNOWN",
                        "price_state": "UNKNOWN",
                    }
                )
    return rows


def purchase_findings(doc, expected_bindings=None):
    """Validate semantic purchase targets and exact frozen purchase link bindings."""
    findings = set()
    by_id = {n["attrs"]["id"]: n for n in doc.elements if n["attrs"].get("id")}
    observed = []
    first_card = next(
        (
            i
            for i, n in enumerate(doc.elements)
            if {"ps-product", "raos-product-card"}
            & set((n["attrs"].get("class") or "").split())
        ),
        len(doc.elements),
    )
    for node_index, node in enumerate(doc.elements):
        if node["tag"] != "a":
            continue
        a = node["attrs"]
        href = a.get("href", "")
        chain, parent = [node], node["parent"]
        while parent:
            chain.append(parent)
            parent = parent["parent"]
        context = next(
            (p["attrs"] for p in chain if p["attrs"].get("data-raos-cta-id")), a
        )
        product = next(
            (
                p["attrs"].get("data-ps-product")
                or p["attrs"].get("data-raos-product-id")
                for p in chain
                if p["attrs"].get("data-ps-product")
                or p["attrs"].get("data-raos-product-id")
            ),
            None,
        )
        if href.startswith("#") and (
            href.startswith("#ps-seller-") or href.endswith("-purchase")
        ):
            target = by_id.get(unquote(href[1:]))
            if (
                target is not None
                and target["attrs"].get("data-ps-purchase-alias") == "true"
            ):
                target = target["parent"]
            if (
                not target
                or target["tag"] != "section"
                or "ps-product-offers"
                not in (target["attrs"].get("class") or "").split()
                or not target["text"].strip()
                or target["hidden"]
            ):
                findings.add("PURCHASE_ANCHOR_NOT_OFFER_SECTION")
            elif not product or target["attrs"].get("data-ps-product") != product:
                findings.add("PURCHASE_ANCHOR_PRODUCT_MISMATCH")
        if context.get("data-raos-cta-type") != "offer":
            if (
                context.get("data-raos-placement") == "final_summary"
                and node_index < first_card
                and any(
                    {"raos-decision-summary", "decision-section"}
                    & set((p["attrs"].get("class") or "").split())
                    for p in chain
                )
            ):
                findings.add("PURCHASE_PLACEMENT_MISMATCH")
            continue
        observed.append((context, a))
        owner = next(
            (
                p["attrs"].get("data-ps-product")
                for p in chain[1:]
                if p["attrs"].get("data-ps-product")
            ),
            None,
        )
        if owner and owner != context.get("data-raos-product-id"):
            findings.add("PURCHASE_CTA_PRODUCT_MISMATCH")
        placement = next(
            ("top_summary" for p in chain if p["attrs"].get("id") == "ps-choose"), None
        )
        if (
            not placement
            and node_index < first_card
            and any(
                {"raos-decision-summary", "decision-section"}
                & set((p["attrs"].get("class") or "").split())
                for p in chain
            )
        ):
            placement = "top_summary"
        if placement and context.get("data-raos-placement") != placement:
            findings.add("PURCHASE_PLACEMENT_MISMATCH")
        if expected_bindings is not None:
            matches = [
                b
                for b in expected_bindings
                if b["cta_id"] == context.get("data-raos-cta-id")
            ]
            if len(matches) != 1:
                findings.add("PURCHASE_UNREGISTERED_CTA")
                continue
            b = matches[0]
            if href != b["href"]:
                findings.add("PURCHASE_HREF_MISMATCH")
            for key, value in b.items():
                if key != "href" and context.get(
                    "data-raos-" + key.replace("_", "-")
                ) != str(value):
                    findings.add("PURCHASE_BINDING_MISMATCH")
            if b.get("affiliate") == "true" and not {"sponsored", "nofollow"} <= set(
                (a.get("rel") or "").split()
            ):
                findings.add("PURCHASE_AFFILIATE_REL_MISSING")
            if (
                b.get("affiliate") == "false"
                and "sponsored" in (a.get("rel") or "").split()
            ):
                findings.add("PURCHASE_DIRECT_LINK_LABELLED_AD")
    if expected_bindings is not None:
        counts = Counter(c.get("data-raos-cta-id") for c, _ in observed)
        if any(counts[b["cta_id"]] != 1 for b in expected_bindings):
            findings.add("PURCHASE_CTA_MISSING_OR_DUPLICATE")
    return sorted(findings)


def assess(observations, expected_paths, *, sitemap_paths=None):
    """Assess full HTML observations without trusting HTTP 200 as completion."""
    if not isinstance(observations, list) or not isinstance(expected_paths, list):
        raise ValueError("BATCH_INVALID")
    if not 1 <= len(expected_paths) <= 64 or len(observations) > 64:
        raise ValueError("BATCH_SIZE_INVALID")
    expected = [_path(path) for path in expected_paths]
    if len(expected) != len(set(expected)):
        raise ValueError("EXPECTED_PATH_DUPLICATE")
    observed = {}
    for row in observations:
        if not isinstance(row, dict):
            raise ValueError("OBSERVATION_INVALID")
        path = _path(row.get("path"))
        if path not in expected or path in observed:
            raise ValueError("OBSERVATION_TARGET_INVALID")
        observed[path] = row
    sitemap = None if sitemap_paths is None else {_path(path) for path in sitemap_paths}
    findings = []
    pages = {}
    details = {}

    def note(path, code, level="failure"):
        item = {"path": path, "code": code, "level": level}
        if item not in findings:
            findings.append(item)

    for path in expected:
        row = observed.get(path)
        if row is None or row.get("status") is None:
            note(path, "RESPONSE_UNAVAILABLE", "unknown")
            continue
        if type(row["status"]) is not int or row["status"] != 200:
            note(path, "HTTP_NOT_200")
            continue
        text = row.get("html")
        if (
            row.get("full_html") is not True
            or not isinstance(text, str)
            or not text.strip()
        ):
            note(path, "FULL_HTML_UNAVAILABLE", "unknown")
            continue
        if len(text.encode("utf-8")) > 4 * 1024 * 1024:
            raise ValueError("HTML_TOO_LARGE")
        lower = text.lower()
        if not all(
            token in lower
            for token in ("<html", "</html>", "<head", "</head>", "<body", "</body>")
        ):
            note(path, "FULL_HTML_UNAVAILABLE", "unknown")
            continue
        if row.get("final_url") != ORIGIN + path:
            note(path, "FINAL_URL_NOT_SELF")
        doc = Page(text)
        for code in purchase_findings(doc, row.get("purchase_bindings")):
            note(path, code)
        baseline = row.get("seo_baseline")
        if baseline is not None:
            if baseline != {
                "canonical": doc.canonicals,
                "robots": doc.robots,
                "x_robots_tag": {
                    k.lower(): v
                    for k, v in row.get("headers", {}).items()
                    if k.lower() == "x-robots-tag"
                },
            }:
                note(path, "SEO_BASELINE_CHANGED")
        pages[path] = doc
        headers = row.get("headers", {})
        if not isinstance(headers, dict):
            raise ValueError("HEADERS_INVALID")
        robots = list(doc.robots)
        robots.extend(
            str(value)
            for key, value in headers.items()
            if str(key).lower() == "x-robots-tag"
        )
        directives = set(re.findall(r"[a-z-]+", ",".join(robots).lower()))
        if {"noindex", "none"} & directives:
            note(path, "NOINDEX")
        if {"nofollow", "none"} & directives:
            note(path, "PAGE_NOFOLLOW")
        if len(doc.canonicals) != 1:
            note(path, "CANONICAL_MISSING_OR_DUPLICATE")
        elif doc.canonicals[0] != ORIGIN + path:
            note(path, "CANONICAL_NOT_SELF")
        if doc.h1_count != 1:
            note(path, "H1_COUNT")
        if any(count > 1 for count in Counter(doc.ids).values()):
            note(path, "DUPLICATE_ID")
        if not "".join(doc.title).strip():
            note(path, "TITLE_MISSING")
        if len(doc.description) != 1 or not doc.description[0].strip():
            note(path, "DESCRIPTION_MISSING_OR_DUPLICATE")
        if "現在、条件に合う公開記事はありません" in "".join(doc.visible_text):
            note(path, "EMPTY_LISTING")
        approved_ad_hrefs = {
            b["href"]
            for b in row.get("purchase_bindings", [])
            if b.get("affiliate") == "true"
        }
        paid = [
            (rel, pos)
            for href, rel, pos in doc.links
            if (urlsplit(urljoin(ORIGIN + path, href)).hostname or "").lower()
            in AFFILIATE_HOSTS
            or href in approved_ad_hrefs
        ]
        if any(not ({"sponsored", "nofollow"} & rel) for rel, _ in paid):
            note(path, "AFFILIATE_REL_MISSING")
        if paid and not any(pos < min(p for _, p in paid) for pos in doc.disclosures):
            note(path, "DISCLOSURE_NOT_BEFORE_LINK")
        if doc.cost_container:
            if not doc.cost_script:
                note(path, "COST_SCRIPT_MISSING")
            elif (
                row.get("browser_checks", {}).get("cost_calculation_verified")
                is not True
            ):
                note(path, "COST_INTERACTION_UNVERIFIED", "unknown")
        if sitemap is not None and path not in sitemap:
            note(path, "SITEMAP_MISSING")
        details[path] = {
            "affiliate_links": len(paid),
            "h1_count": doc.h1_count,
            "cost_container": doc.cost_container,
            "cost_script": doc.cost_script,
        }

    for path, doc in pages.items():
        for href, _, _ in doc.links:
            target = urlsplit(urljoin(ORIGIN + path, href))
            if (
                target.hostname != HOST
                or target.scheme not in {"http", "https"}
                or target.query
                or not target.fragment
            ):
                continue
            target_path = target.path or "/"
            if target_path not in pages:
                note(path, "ANCHOR_TARGET_UNCHECKED", "unknown")
            elif unquote(target.fragment) not in pages[target_path].ids:
                note(path, "ANCHOR_MISSING")
    levels = {finding["level"] for finding in findings}
    return {
        "schema": "RAOSPublicAcceptanceV1",
        "publication_authority": False,
        "status": (
            "FAIL"
            if "failure" in levels
            else "INCOMPLETE" if "unknown" in levels else "PASS"
        ),
        "expected_pages": len(expected),
        "parsed_pages": len(pages),
        "findings": findings,
        "page_checks": details,
        "not_verified": [
            "actual_search_indexing",
            "merchant_stock_and_prices",
            "product_accuracy",
            "legal_compliance",
            "conversion_and_profit",
            "visual_layout",
            "consent_runtime",
        ],
        "sitemap_checked": sitemap is not None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, help="Anonymous response export; omit to read stdin"
    )
    parser.add_argument(
        "--purchase-runtime",
        type=Path,
        help="Frozen expected purchase runtime for this rollout",
    )
    parser.add_argument(
        "--inventory-output",
        type=Path,
        help="Write observed public links to a new local file; never stdout",
    )
    parser.add_argument(
        "--purchase-catalog",
        type=Path,
        help="Reviewed offer catalog used only to annotate inventory",
    )
    args = parser.parse_args(argv)
    try:
        if args.input:
            if (
                args.input.is_symlink()
                or not args.input.is_file()
                or args.input.stat().st_size > MAX_BYTES
            ):
                raise ValueError("INPUT_INVALID")
            raw = args.input.read_bytes()
        else:
            raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("INPUT_TOO_LARGE")
        batch = json.loads(raw)
        if (
            not isinstance(batch, dict)
            or batch.get("schema") != "RAOSAnonymousPageBatchV1"
        ):
            raise ValueError("INPUT_SCHEMA_INVALID")
        if args.purchase_runtime:
            runtime = json.loads(args.purchase_runtime.read_text())
            if runtime.get("schema") != "RAOS_PURCHASE_ARTICLE_RUNTIME_V1":
                raise ValueError("PURCHASE_RUNTIME_INVALID")
            matched = 0
            for observation in batch["observations"]:
                matches = [
                    a
                    for a in runtime["articles"]
                    if "/" + a["slug"] + "/" == observation["path"]
                ]
                # Supporting pages (for example the home navigation's anchors)
                # still receive the original SEO/anchor checks, without a purchase contract.
                if not matches:
                    if any(
                        n["attrs"].get("data-raos-purchase-support") == "v1"
                        for n in Page(observation.get("html", "")).elements
                    ):
                        raise ValueError("PURCHASE_EXPECTED_ARTICLE_MISSING")
                    continue
                if len(matches) != 1:
                    raise ValueError("PURCHASE_EXPECTED_ARTICLE_MISSING")
                observation["purchase_bindings"] = matches[0]["bindings"]
                matched += 1
            if not matched:
                raise ValueError("PURCHASE_EXPECTED_ARTICLE_MISSING")
        if args.inventory_output:
            catalog = (
                json.loads(args.purchase_catalog.read_text())
                if args.purchase_catalog
                else {}
            )
            rows = [
                item
                for observation in batch["observations"]
                for item in purchase_inventory(
                    Page(observation.get("html", "")),
                    article_id=observation["path"].strip("/"),
                    post_id=observation.get("post_id"),
                    offers=catalog.get("offers", []),
                )
            ]
            with args.inventory_output.open("x") as stream:
                json.dump(rows, stream, ensure_ascii=False, indent=2)
        report = assess(
            batch["observations"],
            batch["expected_paths"],
            sitemap_paths=batch.get("sitemap_paths"),
        )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[report["status"]]
    except ValueError, OSError, KeyError, TypeError, RecursionError:
        print(
            '{"status":"INCOMPLETE","error":"INPUT_INVALID","publication_authority":false}'
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
