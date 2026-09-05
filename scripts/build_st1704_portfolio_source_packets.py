#!/usr/bin/env python3
"""Build the ten-article ST-1704 official-source registry and locators.

The first five packets are maintained in the structured pilot.  This builder
adds the five existing portfolio articles without creating WordPress posts,
then refreshes every packet/source hash and the registry-to-locator binding.
Only manufacturer, carrier, or platform primary sources are represented.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Final


ROOT: Final = Path(__file__).resolve().parents[1]
SLICE: Final = ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1"
REGISTRY_PATH: Final = SLICE / "sources/source-registry.v1.json"
LOCATOR_PATH: Final = SLICE / "sources/source-locator-contract.v1.json"
PORTFOLIO_PATH: Final = (
    ROOT / "changes/editorial-portfolio-v2/editorial-portfolio.v2.json"
)
MARKET_AUDIT_PATH: Final = (
    ROOT / "changes/editorial-portfolio-v3/market-candidate-audit.v1.json"
)
MANUFACTURER_SALES_STATE_PATH: Final = (
    ROOT / "changes/editorial-portfolio-v2/manufacturer-sales-state.v1.json"
)
RETRIEVED_ON: Final = "2026-08-31"

# `retrieved_on` is an evidence observation date, not the generator run date.
# Most reused sources retain the date already recorded in the registry.  A
# source is advanced only when a new, source-specific observation was actually
# made and is bound below to a checked-at claim.
SOURCE_RETRIEVED_ON_OVERRIDES: Final[dict[str, str]] = {
    # The originally recorded 05721-04 colour is now sold out.  The selected
    # owner record was deliberately moved to the exact, reader-visible
    # 05721-06 white variant on 2026-08-31 instead of treating availability of
    # a sibling colour as availability of the old URL.
    "SRC-ACE-DIFFERENCE-05721": "2026-08-31",
    # These exact reader-visible model blocks, stock labels, cart controls,
    # and model-code tables were re-observed for the embedded MSS projection
    # on 2026-08-31.  Keeping the older 2026-08-23 dates would make the claim
    # evidence look older than the exact fragments actually captured.
    "SRC-ANKER-SOLIX-C300": "2026-08-31",
    "SRC-ANKER-SOLIX-C800-PLUS": "2026-08-31",
    "SRC-ANKER-SOLIX-C1000": "2026-08-31",
    "SRC-ANKER-SOLIX-C1000-GEN2": "2026-08-31",
    "SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY": "2026-08-31",
    # Re-fetched the exact mini 2 store page on 2026-09-01. Video Manager is
    # a decision-critical connected-camera capability, not a decorative
    # product-page detail, so its observation date advances independently.
    "SRC-ECOVACS-DEEBOT-MINI2": "2026-09-01",
}

SOURCE_METADATA_OVERRIDES: Final[dict[str, dict[str, str]]] = {
    "SRC-ACE-DIFFERENCE-05721": {
        "title": (
            "ace. ディフェレンス 05721 06：ホワイト"
            "（エース公式オンラインストア）"
        ),
        "url": "https://store.ace.jp/shop/g/g05721-06/",
    },
}

PORTFOLIO_ARTICLE_IDS: Final = (
    "carry-on-suitcase-under-100-seats",
    "lightweight-carry-on-suitcase-under-3kg",
    "front-open-carry-on-suitcase-with-stopper",
    "roomba-mini-vs-switchbot-k11-pro",
    "solota-vs-rakua-mini-plus",
)

RETIRED_SOURCE_REFS: Final = frozenset(
    {
        # The current NP-TSP2 market-candidate record is bound to the launch
        # announcement and the official subscription page.  The older spec
        # page is no longer referenced by a reader-visible claim and has no
        # claim locator, so keeping it READY would create an unbounded capture
        # target.
        "SRC-PANASONIC-NP-TSP2",
        # The official installation page covers multiple siroca dishwasher
        # families.  Replace the old SS-MA251-specific identifier so a claim
        # about SS-M171 cannot inherit a misleading source identity.
        "SRC-SIROCA-SS-MA251-INSTALL",
    }
)

# Policy sources are part of the capture contract even though they are not
# referenced by product claims.  Keep explicit seeds so pruning retired
# product sources cannot make a subsequent owner regeneration drop these
# fail-closed compliance locators.
POLICY_SOURCE_LOCATORS: Final[dict[str, dict[str, object]]] = {
    "SRC-RAKUTEN-AFFILIATE-GUIDELINE": {
        "source_ref": "SRC-RAKUTEN-AFFILIATE-GUIDELINE",
        "charset": None,
        "locator_status": "READY",
        "locators": [
            {
                "claim_id": "POLICY-SOURCE-STATEMENT",
                "exact_utf8_fragments": [
                    "サイズ変更・周辺部分への加工は可能です",
                    (
                        "画像の上に直接文字や装飾を入れること、画像の一部を"
                        "切り取って使用することは禁止といたします"
                    ),
                ],
            }
        ],
    },
    "SRC-CAA-STEALTH-MARKETING-QA": {
        "source_ref": "SRC-CAA-STEALTH-MARKETING-QA",
        "charset": None,
        "locator_status": "READY",
        "locators": [
            {
                "claim_id": "POLICY-SOURCE-STATEMENT",
                "exact_utf8_fragments": [
                    (
                        '<span>アフィリエイト広告について、アフィリエイトサイトの'
                        '冒頭に、「このサイトはアフィリエイト広告を利用しています。」'
                    ),
                    (
                        "一般消費者にとって「事業者の表示」であることが明瞭となって"
                        "いるかどうかが重要となります。"
                    ),
                ],
            }
        ],
    },
    "SRC-GOOGLE-QUALIFY-OUTBOUND-LINKS": {
        "source_ref": "SRC-GOOGLE-QUALIFY-OUTBOUND-LINKS",
        "charset": "utf-8",
        "locator_status": "READY",
        "locators": [
            {
                "claim_id": "POLICY-SOURCE-STATEMENT",
                "exact_utf8_fragments": [
                    (
                        "Mark links that are advertisements or paid placements "
                        "(commonly called <i>paid\n              links</i>) with the "
                        '<code translate="no" dir="ltr">sponsored</code> value.'
                    )
                ],
            }
        ],
    },
}

# Explicit claim subjects are part of the source packet contract.  They are
# intentionally not inferred from prose: sibling products routinely share
# values and prefixes (for example C1000/C1000 Gen 2), so lexical matching is
# not a safe authorization boundary for reader-facing claim bindings.
CLAIM_SUBJECT_PRODUCT_IDS: Final[dict[str, tuple[str, ...]]] = {
    "CLM-ST1704-SUITCASE-TRIAIR-01541-SPECS": ("PRD-PROTECA-TRI-AIR-01541",),
    "CLM-ST1704-SUITCASE-CRESTA-06316-EXCLUDED": (),
    "CLM-ST1704-SUITCASE-DIFFERENCE-SPECS": ("PRD-ACE-DIFFERENCE-05721",),
    "CLM-ST1704-SUITCASE-MAXPASS-SPECS": ("PRD-ACE-MAXPASS4-01471",),
    "CLM-ST1704-SUITCASE-CARRYON-LIMITS": (),
    "CLM-ST1704-SUITCASE-CONDITIONAL-CHOICES": (
        "PRD-PROTECA-TRI-AIR-01541",
        "PRD-ACE-DIFFERENCE-05721",
        "PRD-ACE-MAXPASS4-01471",
    ),
    "CLM-ST1704-SUITCASE-AEROFLEX-DX2-REFERENCE": (
        "PRD-PROTECA-AEROFLEX-DX2-01521",
    ),
    "CLM-ST1704-POWER-C300-SPECS": ("PRD-ANKER-SOLIX-C300",),
    "CLM-ST1704-POWER-JACKERY-SPECS": ("PRD-JACKERY-500-NEW",),
    "CLM-ST1704-POWER-JACKERY-STORAGE": ("PRD-JACKERY-500-NEW",),
    "CLM-ST1704-POWER-JACKERY-WARRANTY": ("PRD-JACKERY-500-NEW",),
    "CLM-ST1704-POWER-SAFETY-PRACTICE": (),
    "CLM-ST1704-POWER-ANKER-C800-SPECS": ("PRD-ANKER-SOLIX-C800",),
    "CLM-ST1704-POWER-DJI-1000-V2-SPECS": ("PRD-DJI-POWER-1000-V2",),
    "CLM-ST1704-POWER-AC70-EXCLUDED": (),
    "CLM-ST1704-POWER-JACKERY-1000-NEW-V3-SPECS": (
        "PRD-JACKERY-1000-NEW-V3",
    ),
    "CLM-ST1704-POWER-NESTOUT-700N-EXCLUDED": (),
    "CLM-ST1704-POWER-AORA80-EXCLUDED": (),
    "CLM-ST1704-POWER-AORA30-V2-SPECS": ("PRD-BLUETTI-AORA30-V2",),
    "CLM-ST1704-POWER-AORA100-V2-SPECS": ("PRD-BLUETTI-AORA100-V2",),
    "CLM-ST1704-POWER-RIVER3-PLUS-EXCLUDED": (),
    "CLM-ST1704-POWER-DELTA3-PLUS-EXCLUDED": (),
    "CLM-ST1704-POWER-DELTA3-CLASSIC-EXCLUDED": (),
    "CLM-ST1704-POWER-CONDITIONAL-CHOICES": (
        "PRD-ANKER-SOLIX-C300",
        "PRD-BLUETTI-AORA30-V2",
        "PRD-JACKERY-500-NEW",
        "PRD-ANKER-SOLIX-C800",
        "PRD-JACKERY-1000-NEW-V3",
        "PRD-BLUETTI-AORA100-V2",
        "PRD-DJI-POWER-1000-V2",
    ),
    "CLM-ST1704-POWER-C1000-GEN2-REFERENCE": (
        "PRD-ANKER-SOLIX-C1000-GEN2",
    ),
    "CLM-ST1704-ANKER-C300-SPECS": ("PRD-ANKER-SOLIX-C300",),
    "CLM-ST1704-ANKER-C800-SPECS": ("PRD-ANKER-SOLIX-C800-PLUS",),
    "CLM-ST1704-ANKER-C1000-SPECS": ("PRD-ANKER-SOLIX-C1000",),
    "CLM-ST1704-ANKER-C1000-GEN2-SPECS": ("PRD-ANKER-SOLIX-C1000-GEN2",),
    "CLM-ST1704-ANKER-C1000-FEATURE-DIFF": (
        "PRD-ANKER-SOLIX-C1000",
        "PRD-ANKER-SOLIX-C1000-GEN2",
    ),
    "CLM-ST1704-ANKER-C1000-GENERATION-DIFF": (
        "PRD-ANKER-SOLIX-C1000",
        "PRD-ANKER-SOLIX-C1000-GEN2",
    ),
    "CLM-ST1704-ANKER-C1000-PLUS-EXCLUDED": (),
    "CLM-ST1704-ANKER-SAFETY-PRACTICE": (),
    "CLM-ST1704-ANKER-CONDITIONAL-CHOICES": (
        "PRD-ANKER-SOLIX-C300",
        "PRD-ANKER-SOLIX-C800-PLUS",
        "PRD-ANKER-SOLIX-C1000",
        "PRD-ANKER-SOLIX-C1000-GEN2",
    ),
    "CLM-ST1704-ANKER-C800-A1753-REFERENCE": (
        "PRD-ANKER-SOLIX-C800",
    ),
    "CLM-ST1704-DISH-SS-M171-SPECS": ("PRD-SIROCA-SS-M171",),
    "CLM-ST1704-DISH-RAKUA-SPECS": ("PRD-THANKO-RAKUA-MINI-TK-MDW22W",),
    "CLM-ST1704-DISH-SS-MA251-SPECS": ("PRD-SIROCA-SS-MA251",),
    "CLM-ST1704-DISH-TOSHIBA-DWS-33B-SPECS": ("PRD-TOSHIBA-DWS-33B-W",),
    "CLM-ST1704-DISH-TOSHIBA-DWS-33B-SUPPORT": (
        "PRD-TOSHIBA-DWS-33B-W",
    ),
    "CLM-ST1704-DISH-NP-TSP2-LAUNCH-REFERENCE": (),
    "CLM-ST1704-DISH-NP-TSP2-EXCLUDED": (),
    "CLM-ST1704-DISH-THANKO-RAKUA-MINI-COLOR-EXCLUDED": (),
    "CLM-ST1704-DISH-AQUA-M28B-EXCLUDED": (),
    "CLM-ST1704-DISH-CONDITIONAL-CHOICES": (
        "PRD-SIROCA-SS-M171",
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-MA251",
        "PRD-TOSHIBA-DWS-33B-W",
    ),
    "CLM-ST1704-DISH-NP-TMLK1-EXCLUDED": (),
    "CLM-ST1704-ROBOT-EUFY-C10-SPECS": (
        "PRD-EUFY-AUTOEMPTY-C10-T2292",
    ),
    "CLM-ST1704-ROBOT-K11-PRO-SPECS": ("PRD-SWITCHBOT-K11-PRO",),
    "CLM-ST1704-ROBOT-K11-PRO-WARRANTY-UNRESOLVED": (
        "PRD-SWITCHBOT-K11-PRO",
    ),
    "CLM-ST1704-ROBOT-DEEBOT-MINI2-SPECS": ("PRD-ECOVACS-DEEBOT-MINI2",),
    "CLM-ST1704-ROBOT-K10-COMBO-EXCLUDED": (),
    "CLM-ST1704-ROBOT-ROOMBA-MINI-F155260-EXCLUDED": (),
    "CLM-ST1704-ROBOT-RULO-MINI-REFERENCE": (),
    "CLM-ST1704-ROBOT-E20-EXCLUDED": (),
    "CLM-ST1704-ROBOT-SAROS10-EXCLUDED": (),
    "CLM-ST1704-ROBOT-E25-EXCLUDED": (),
    "CLM-ST1704-ROBOT-X50-EXCLUDED": (),
    "CLM-ST1704-ROBOT-X8-EXCLUDED": (),
    "CLM-ST1704-ROBOT-ROOMBA-515-SPECS": ("PRD-IROBOT-ROOMBA-PLUS-515-COMBO",),
    "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES": (
        "PRD-EUFY-AUTOEMPTY-C10-T2292",
        "PRD-SWITCHBOT-K11-PRO",
        "PRD-ECOVACS-DEEBOT-MINI2",
        "PRD-IROBOT-ROOMBA-PLUS-515-COMBO",
    ),
    "CLM-ST1704-ROBOT-F115060-REFERENCE": (
        "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",
    ),
    "CLM-PORTFOLIO-UNDER100-STARIA-02350": ("PRD-PROTECA-STARIA-CXR-02350",),
    "CLM-PORTFOLIO-UNDER100-FRESTER-01550": ("PRD-PROTECA-FRESTER-EX-01550",),
    "CLM-PORTFOLIO-UNDER100-PALISADES-06910": ("PRD-ACE-PALISADES3-Z-06910",),
    "CLM-PORTFOLIO-UNDER100-BERMAS-60524": ("PRD-BERMAS-INTER-CITY-60524",),
    "CLM-PORTFOLIO-UNDER100-ANA-RULE": (),
    "CLM-PORTFOLIO-UNDER100-JAL-RULE": (),
    "CLM-PORTFOLIO-UNDER100-RIMOWA-CABIN-U-EXCLUDED": (),
    "CLM-PORTFOLIO-UNDER100-AUDRINA-EXCLUDED": (),
    "CLM-PORTFOLIO-UNDER100-MUJI20-EXCLUDED": (),
    "CLM-PORTFOLIO-UNDER100-CONDITIONAL-CHOICES": (
        "PRD-PROTECA-STARIA-CXR-02350",
        "PRD-PROTECA-FRESTER-EX-01550",
        "PRD-ACE-PALISADES3-Z-06910",
        "PRD-BERMAS-INTER-CITY-60524",
    ),
    "CLM-PORTFOLIO-UNDER100-MAXPASS4-REFERENCE": (
        "PRD-ACE-MAXPASS4-01471",
    ),
    "CLM-PORTFOLIO-LIGHT-AEROFLEX-01521": ("PRD-PROTECA-AEROFLEX-DX2-01521",),
    "CLM-PORTFOLIO-LIGHT-RIMOWA-82353171": (
        "PRD-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
    ),
    "CLM-PORTFOLIO-LIGHT-SAMSONITE-C-LITE-134679-1549": (
        "PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549",
    ),
    "CLM-PORTFOLIO-LIGHT-APPLITE-QJ6-68002": (
        "PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002",
    ),
    "CLM-PORTFOLIO-LIGHT-FREQUENTER-REFERENCE": (),
    "CLM-PORTFOLIO-LIGHT-ANA-RULE": (),
    "CLM-PORTFOLIO-LIGHT-JAL-RULE": (),
    "CLM-PORTFOLIO-LIGHT-MUJI36-EXCLUDED": (),
    "CLM-PORTFOLIO-LIGHT-CONDITIONAL-CHOICES": (
        "PRD-PROTECA-AEROFLEX-DX2-01521",
        "PRD-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
        "PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002",
        "PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549",
        "PRD-PROTECA-TRI-AIR-01541",
    ),
    "CLM-PORTFOLIO-LIGHT-TRIAIR-01541": (
        "PRD-PROTECA-TRI-AIR-01541",
    ),
    "CLM-PORTFOLIO-FRONT-INNOVATOR-INV50": ("PRD-INNOVATOR-INV50",),
    "CLM-PORTFOLIO-FRONT-DIFFERENCE-05721": ("PRD-ACE-DIFFERENCE-05721",),
    "CLM-PORTFOLIO-FRONT-FRESTER-01551": ("PRD-PROTECA-FRESTER-EX-01551",),
    "CLM-PORTFOLIO-FRONT-BERMAS-60570": ("PRD-BERMAS-INTER-CITY-III-60570",),
    "CLM-PORTFOLIO-FRONT-ANA-RULE": (),
    "CLM-PORTFOLIO-FRONT-JAL-RULE": (),
    "CLM-PORTFOLIO-FRONT-MUJI32-EXCLUDED": (),
    "CLM-PORTFOLIO-FRONT-BERMAS-60561-EXCLUDED": (),
    "CLM-PORTFOLIO-FRONT-C-LITE-REFERENCE": (),
    "CLM-PORTFOLIO-FRONT-C-LITE-KNOWN-SPECS-REFERENCE": (),
    "CLM-PORTFOLIO-FRONT-CONDITIONAL-CHOICES": (
        "PRD-INNOVATOR-INV50",
        "PRD-ACE-DIFFERENCE-05721",
        "PRD-PROTECA-FRESTER-EX-01551",
        "PRD-BERMAS-INTER-CITY-III-60570",
    ),
    "CLM-PORTFOLIO-FRONT-RIMOWA-REFERENCE": (
        "PRD-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
    ),
    "CLM-PORTFOLIO-ROBOT-K11-PRO": ("PRD-SWITCHBOT-K11-PRO",),
    "CLM-PORTFOLIO-ROBOT-K11-PRO-WARRANTY-UNRESOLVED": (
        "PRD-SWITCHBOT-K11-PRO",
    ),
    "CLM-PORTFOLIO-ROBOT-ROOMBA-SLIM-F115060": ("PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",),
    "CLM-PORTFOLIO-ROBOT-K11-INSTALLATION-SPACE": ("PRD-SWITCHBOT-K11-PRO",),
    "CLM-PORTFOLIO-ROBOT-RULO-MINI-REFERENCE": (),
    "CLM-PORTFOLIO-ROBOT-ROOMBA-MINI-F155260-EXCLUDED": (),
    "CLM-PORTFOLIO-ROBOT-EUFY-C10-BOUNDARY-REFERENCE": (
        "PRD-EUFY-AUTOEMPTY-C10-T2292",
    ),
    "CLM-PORTFOLIO-ROBOT-DEEBOT-MINI2-BOUNDARY-REFERENCE": (
        "PRD-ECOVACS-DEEBOT-MINI2",
    ),
    "CLM-PORTFOLIO-ROBOT-CONDITIONAL-CHOICES": (
        "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",
        "PRD-SWITCHBOT-K11-PRO",
    ),
    "CLM-PORTFOLIO-DISH-SOLOTA-NP-TMLK1-IDENTITY-REFERENCE": (),
    "CLM-PORTFOLIO-DISH-SOLOTA-NP-TMLK1-EXCLUDED": (),
    "CLM-PORTFOLIO-DISH-RAKUA-MINI-PLUS-EXCLUDED": (),
    "CLM-PORTFOLIO-DISH-LIFECYCLE-REFERENCE": (),
}

NON_PRODUCT_CLAIM_IDS: Final = frozenset(
    claim_id
    for claim_id, product_ids in CLAIM_SUBJECT_PRODUCT_IDS.items()
    if not product_ids
)

EXACT_MODEL_PRODUCT_TOKENS: Final[dict[str, frozenset[str]]] = {
    "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060": frozenset({"F115060"}),
}
EXACT_IROBOT_MODEL_RE: Final = re.compile(
    r"(?<![A-Za-z0-9])F\d{6}(?![A-Za-z0-9])"
)

# A reader-visible identity note may intentionally distinguish a model that is
# selected in another article from the selected sibling in this packet.  Keep
# that cross-article scope closed and explicit; never widen it from prose.
ARTICLE_LOCAL_SUBJECT_SCOPE_ADDITIONS: Final = {}


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate_locator_text_fragments(locator: dict[str, object]) -> None:
    """Reject markup accidentally spliced into a reader-visible text fragment."""
    for source in locator["sources"]:
        source_ref = str(source["source_ref"])
        for item in source["locators"]:
            claim_id = str(item["claim_id"])
            for raw_fragment in item["exact_utf8_fragments"]:
                fragment = str(raw_fragment)
                lowered = fragment.lstrip().lower()
                meta_position = lowered.find("<meta")
                if meta_position > 0:
                    raise ValueError(
                        "embedded <meta markup in locator text fragment: "
                        f"{source_ref}/{claim_id}"
                    )


def _source(
    source_ref: str,
    authority: str,
    source_type: str,
    title: str,
    url: str,
    *,
    retrieved_on: str = RETRIEVED_ON,
) -> dict[str, object]:
    return {
        "source_ref": source_ref,
        "authority": authority,
        "source_type": source_type,
        "title": title,
        "url": url,
        "retrieved_on": retrieved_on,
        "capture_status": "STRUCTURED_FACT_SNAPSHOT_CAPTURED",
        "immutable_capture_sha256": "0" * 64,
        "review_body_excluded_from_claim_evidence": True,
    }


NEW_SOURCES: Final = (
    _source(
        "SRC-PROTECA-TRI-AIR-01541",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "PROTECA Tri-Air 01541（エース公式通販）",
        "https://store.ace.jp/shop/g/g01541-10/",
    ),
    _source(
        "SRC-ANKER-SOLIX-C800",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "Anker Solix C800 Portable Power Station",
        "https://www.ankerjapan.com/products/a1753",
    ),
    _source(
        "SRC-DJI-POWER-1000-V2-STORE",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "DJI Power 1000 V2（DJI公式ストア）",
        "https://store.dji.com/jp/product/dji-power-1000-v2",
    ),
    _source(
        "SRC-DJI-POWER-1000-V2-SPECS",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_SPECIFICATION_PAGE",
        "DJI Power 1000 V2 仕様",
        "https://www.dji.com/jp/power-1000-v2/specs",
    ),
    _source(
        "SRC-JACKERY-1000-NEW-V3",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "Jackery ポータブル電源 1000 New V3（JE-1000G / JE-1000G-WH）",
        "https://www.jackery.jp/products/explorer-1000-new-v3",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-JACKERY-1000-NEW-V3-LAUNCH",
        "MANUFACTURER_OFFICIAL",
        "CATEGORY_NEWS_PAGE",
        "Jackery ポータブル電源 1000 New V3 発売案内",
        "https://www.jackery.jp/blogs/news/jackery-news20260724",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-JACKERY-500-NEW-MANUAL",
        "MANUFACTURER_OFFICIAL",
        "OFFICIAL_PRODUCT_MANUAL_PDF",
        "Jackery ポータブル電源 500 New 取扱説明書（JE-500A）",
        "https://cdn.shopify.com/s/files/1/0100/1537/5438/files/Jackery_500_New_20250617.pdf?v=1750410730",
    ),
    _source(
        "SRC-JACKERY-500-NEW-DIMENSION-AXES",
        "MANUFACTURER_OFFICIAL",
        "MANUFACTURER_EDITORIAL_PAGE",
        "Jackery公式 幅・奥行・高さ付き500 New寸法表",
        "https://www.jackery.jp/blogs/daily-use/jackery-portable-power-station-in-living-room",
    ),
    _source(
        "SRC-ANKER-SOLIX-C300-SAFETY-MANUAL",
        "MANUFACTURER_OFFICIAL",
        "OFFICIAL_PRODUCT_MANUAL_PDF",
        "Anker Solix C300 安全マニュアル（A1722）",
        "https://lp.ankerjapan.com/hubfs/aoos/manual/A1722Safety.pdf",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-ANKER-SOLIX-C800-SAFETY-MANUAL",
        "MANUFACTURER_OFFICIAL",
        "OFFICIAL_PRODUCT_MANUAL_PDF",
        "Anker Solix C800 安全マニュアル（A1753）",
        "https://lp.ankerjapan.com/hubfs/aoos/manual/A1753Safety.pdf",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-ANKER-SOLIX-C800-PLUS-SAFETY-MANUAL",
        "MANUFACTURER_OFFICIAL",
        "OFFICIAL_PRODUCT_MANUAL_PDF",
        "Anker Solix C800 Plus 安全マニュアル（A1754）",
        "https://lp.ankerjapan.com/hubfs/aoos/manual/A1754Safety.pdf",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-ANKER-SOLIX-C1000-SAFETY-MANUAL",
        "MANUFACTURER_OFFICIAL",
        "OFFICIAL_PRODUCT_MANUAL_PDF",
        "Anker Solix C1000 安全マニュアル（A1761）",
        "https://lp.ankerjapan.com/hubfs/aoos/manual/A1761Safety.pdf",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-ANKER-SOLIX-C1000-GEN2-SAFETY-MANUAL",
        "MANUFACTURER_OFFICIAL",
        "OFFICIAL_PRODUCT_MANUAL_PDF",
        "Anker Solix C1000 Gen 2 安全マニュアル（A1763）",
        "https://lp.ankerjapan.com/hubfs/aoos/manual/A1763Safety.pdf",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-ANKER-SOLIX-JP-SUPPORT",
        "MANUFACTURER_OFFICIAL",
        "SUPPORT_POLICY_PAGE",
        "Anker Solix 国内修理・問い合わせ・回収サポート",
        "https://www.ankerjapan.com/pages/solix-support",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-JACKERY-JP-REPAIR-SERVICE",
        "MANUFACTURER_OFFICIAL",
        "SUPPORT_POLICY_PAGE",
        "Jackery Japan ポータブル電源修理サービス",
        "https://www.jackery.jp/pages/precautions-for-repairing",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-JACKERY-JP-RECYCLING",
        "MANUFACTURER_OFFICIAL",
        "SUPPORT_POLICY_PAGE",
        "Jackery Japan ポータブル電源回収・リサイクルサービス",
        "https://www.jackery.jp/pages/recycling",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-DJI-POWER-1000-V2-SAFETY-GUIDELINES-JA",
        "MANUFACTURER_OFFICIAL",
        "OFFICIAL_PRODUCT_MANUAL_PDF",
        "DJI Power 1000 V2 安全ガイドライン v1.01（日本語）",
        "https://dl.djicdn.com/downloads/DJI_Power_1000_V2/20251225/"
        "DJI_Power_1000_V2_Safety_Guidelines_v1.01_Multi.pdf",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-DJI-POWER-1000-V2-USER-MANUAL-JA",
        "MANUFACTURER_OFFICIAL",
        "OFFICIAL_PRODUCT_MANUAL_PDF",
        "DJI Power 1000 V2 ユーザーマニュアル v1.0（日本語）",
        "https://dl.djicdn.com/downloads/DJI_Power_1000_V2/20250610/"
        "DJI_Power_1000_V2_User_Manual_v1.0_ja.pdf",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-DJI-JP-AFTERSALES-POLICY",
        "MANUFACTURER_OFFICIAL",
        "SUPPORT_POLICY_PAGE",
        "DJI Japan アフターサービスポリシー",
        "https://www.dji.com/jp/service/policy",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-METI-PORTABLE-POWER-SAFETY",
        "GOVERNMENT_OFFICIAL",
        "SAFETY_GUIDANCE_PAGE",
        "経済産業省 ポータブル電源の安全性要求事項（中間とりまとめ）",
        "https://www.meti.go.jp/product_safety/consumer/system/potaburu-denngenn-youkyuu.html",
    ),
    _source(
        "SRC-METI-ELECTRICAL-RECALLS",
        "GOVERNMENT_OFFICIAL",
        "RECALL_INDEX_PAGE",
        "経済産業省 家庭用電気製品のリコール情報",
        "https://www.meti.go.jp/product_safety/recall/denki.html",
    ),
    _source(
        "SRC-TOSHIBA-DWS-33B",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_SPECIFICATION_PAGE",
        "東芝 食器洗い乾燥機 DWS-33B",
        "https://www.toshiba-lifestyle.com/jp/dish-drye/dws-33b/",
    ),
    _source(
        "SRC-TOSHIBA-DWS-33B-STORE",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "東芝 DWS-33B(W) 公式通販",
        "https://shop.toshiba-lifestyle.com/jp/shop/g/g92012630Z00245-ha/",
    ),
    _source(
        "SRC-TOSHIBA-PARTS-RETENTION",
        "MANUFACTURER_OFFICIAL",
        "SUPPORT_POLICY_PAGE",
        "東芝 補修用性能部品の保有期間",
        "https://www.toshiba-lifestyle.com/jp/support/partslimit/",
    ),
    _source(
        "SRC-PANASONIC-NP-TSP2-LAUNCH",
        "MANUFACTURER_OFFICIAL",
        "CATEGORY_NEWS_PAGE",
        "Panasonic 食器洗い乾燥機カテゴリー（NP-TSP2発売予定）",
        "https://panasonic.jp/dish/",
    ),
    _source(
        "SRC-PANASONIC-NP-TSP2-SUBSCRIPTION",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_SUBSCRIPTION_PAGE",
        "Panasonic NP-TSP2 定額利用サービス",
        "https://panasonic.jp/subscription/products/dish/tsp2.html",
    ),
    _source(
        "SRC-PANASONIC-NP-TMLK1-SUPPORT",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_SUPPORT_PAGE",
        "Panasonic NP-TML1 / NP-TMLK1 サポート",
        "https://panasonic.jp/dish/products/NP-TMLK1/support.html",
    ),
    _source(
        "SRC-PANASONIC-NP-TML1-MANUAL",
        "MANUFACTURER_OFFICIAL",
        "OFFICIAL_PRODUCT_MANUAL_PDF",
        "Panasonic NP-TML1 / NP-TMLK1 取扱説明書",
        "https://panasonic.jp/content/dam/panasonic/jp/ja/pim-assets/support/manual/000/000/000/379/872/000000000379872/np-tml1.pdf",
    ),
    _source(
        "SRC-PANASONIC-DISH-PARTS-RETENTION",
        "MANUFACTURER_OFFICIAL",
        "SUPPORT_POLICY_PAGE",
        "Panasonic 補修用性能部品の保有期間",
        "https://panasonic.jp/support/repair/warranty.html",
    ),
    # These three URLs were already cited by the tracked article bodies.  Keep
    # their recorded source-list check dates instead of substituting build time.
    _source(
        "SRC-ANA-DOMESTIC-CARRY-ON",
        "CARRIER_OFFICIAL",
        "POLICY_PAGE",
        "ANA 機内に持ち込める手荷物のサイズとルール（日本国内線）",
        (
            "https://www.ana.co.jp/ja/jp/guide/boarding-procedures/"
            "baggage/domestic/carry-rule/"
        ),
        retrieved_on="2026-08-29",
    ),
    _source(
        "SRC-PROTECA-STARIA-CXR-02350",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_PAGE",
        "PROTECA スタリアCXR 02350（エース公式オンラインストア）",
        "https://store.ace.jp/shop/g/g02350-12/",
    ),
    _source(
        "SRC-PROTECA-FRESTER-EX-01550",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_PAGE",
        "PROTECA フレスターEX 01550（エース公式オンラインストア）",
        "https://store.ace.jp/shop/g/g01550-11/",
    ),
    _source(
        "SRC-ACE-PALISADES3-Z-06910",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_PAGE",
        "ace. パリセイド3-Z 06910（エース公式オンラインストア）",
        "https://store.ace.jp/shop/g/g06910-03/",
    ),
    _source(
        "SRC-BERMAS-INTER-CITY-60524",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_PAGE",
        "BERMAS INTER CITY 60524（新仕様）",
        "https://www.bermas.co.jp/c/series/businesstravel/intercity/60524-1",
    ),
    _source(
        "SRC-JAL-DOMESTIC-CARRY-ON",
        "CARRIER_OFFICIAL",
        "POLICY_PAGE",
        "JAL 国内線 機内持ち込みお手荷物",
        "https://www.jal.co.jp/jp/ja/dom/baggage/inflight/",
    ),
    _source(
        "SRC-PROTECA-AEROFLEX-DX2-01521",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_PAGE",
        "PROTECA エアロフレックスDX2 01521（エース公式オンラインストア）",
        "https://store.ace.jp/shop/g/g01521-09/",
    ),
    _source(
        "SRC-PROTECA-SUITCASE-WARRANTY",
        "MANUFACTURER_OFFICIAL",
        "WARRANTY_POLICY_PAGE",
        "PROTECA スーツケース製品保証・プレミアムケア",
        "https://store.ace.jp/shop/pages/new_proteca_warranty.aspx?ismodesmartphone=off",
    ),
    _source(
        "SRC-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "RIMOWA Essential Lite キャビン 82353171",
        "https://www.rimowa.com/jp/ja/luggage/colour/grey/%E3%82%AD%E3%83%A3%E3%83%93%E3%83%B3/82353171.html",
    ),
    _source(
        "SRC-RIMOWA-LIFETIME-GUARANTEE",
        "MANUFACTURER_OFFICIAL",
        "WARRANTY_POLICY_PAGE",
        "RIMOWA スーツケースの永久保証",
        "https://www.rimowa.com/jp/ja/lifetime-guarantee",
    ),
    _source(
        "SRC-RIMOWA-WARRANTY-FAQ",
        "MANUFACTURER_OFFICIAL",
        "WARRANTY_POLICY_PAGE",
        "RIMOWA 保証FAQ",
        "https://www.rimowa.com/jp/ja/%E3%82%88%E3%81%8F%E3%81%82%E3%82%8B%E3%81%94%E8%B3%AA%E5%95%8F/%E4%BF%9D%E8%A8%BC",
    ),
    _source(
        "SRC-SAMSONITE-C-LITE-CS2-09007",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_PAGE",
        "Samsonite C-Lite Spinner 55 Expandable CS2*09007",
        "https://www.samsonite.az/en/products/c-lite-spinner-5520-exp",
    ),
    _source(
        "SRC-SAMSONITE-CATALOG-2025",
        "MANUFACTURER_OFFICIAL",
        "OFFICIAL_PRODUCT_CATALOG_PDF",
        "Samsonite Collection 2025 catalog（C-Lite A154 / 134679）",
        "https://www.samsonite.ro/cataloage/catalog-2025.pdf",
    ),
    _source(
        "SRC-AMERICAN-TOURISTER-APPLITE4-QJ6-68002",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_PAGE",
        "American Tourister APPLITE 4.0 QJ6-68002",
        "https://www.americantourister.jp/american-tourister/applite4_0/spinner55exp/grey_red",
    ),
    _source(
        "SRC-FREQUENTER-LIEVE-1-250",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_PAGE",
        "FREQUENTER LIEVE 1-250（エンドー鞄公式）",
        "https://www.bagworld.co.jp/c/brands/frequenter/1-250",
    ),
    _source(
        "SRC-INNOVATOR-INV50",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_DATA_ENDPOINT",
        "innovator INV50 official product data",
        "https://shop.innovator.co.jp/products/inv50-paleblue.js",
    ),
    _source(
        "SRC-PROTECA-FRESTER-EX-01551",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_PAGE",
        "PROTECA フレスターEX 01551（エース公式オンラインストア）",
        "https://store.ace.jp/shop/g/g01551-01/",
    ),
    _source(
        "SRC-BERMAS-INTER-CITY-III-60570",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_PAGE",
        "BERMAS INTER CITY III 60570",
        "https://www.bermas.co.jp/c/series/businesstravel/intercity3/60570",
    ),
    _source(
        "SRC-BERMAS-INTER-CITY-II-60561",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_PAGE",
        "BERMAS INTER CITY II 60561",
        "https://www.bermas.co.jp/c/series/businesstravel/intercity2/60561",
    ),
    _source(
        "SRC-IROBOT-ROOMBA-MINI-SLIM-F115060",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_PAGE",
        "Roomba Mini Slim + SlimCharge F115060",
        "https://store.irobot-jp.com/category/ROOMBA/F115060.html",
    ),
    _source(
        "SRC-ECOVACS-DEEBOT-MINI2",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "ECOVACS DEEBOT mini 2（公式限定セット）",
        "https://www.ecovacs.com/jp/shop/deebot-robotic-vacuum-cleaner/bundle-deebot-mini2",
    ),
    _source(
        "SRC-ECOVACS-WARRANTY",
        "MANUFACTURER_OFFICIAL",
        "WARRANTY_POLICY_PAGE",
        "ECOVACS 保証期間について",
        "https://help.ecovacs.com/jp/support/warranty",
    ),
    _source(
        "SRC-SWITCHBOT-K11-PRO-EXTENDED-WARRANTY",
        "MANUFACTURER_OFFICIAL",
        "WARRANTY_SERVICE_PAGE",
        "SwitchBot公式有料5年延長保証サービス（K11+ Pro）",
        "https://www.switchbot.jp/products/extended-warranty-service",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-SWITCHBOT-AUTOEMPTY-INSTALLATION-SPACE",
        "MANUFACTURER_OFFICIAL",
        "INSTALLATION_GUIDE",
        "SwitchBot Mini Robot Vacuum 自動ゴミ収集ステーション設置空間",
        (
            "https://support.switch-bot.com/hc/en-us/articles/"
            "14956880082967-How-Much-Space-Should-Be-Left-When-Installing-"
            "the-Auto-Empty-Station-for-SwitchBot-Mini-Robot-Vacuum-"
            "K10-K10-Pro-K11-K11-Pro"
        ),
        retrieved_on="2026-08-30",
    ),
    _source(
        "SRC-PANASONIC-NP-TML1",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_SPECIFICATION_PAGE",
        "Panasonic SOLOTA NP-TML1 仕様",
        "https://panasonic.jp/dish/products/NP-TML1/spec.html",
    ),
    _source(
        "SRC-PANASONIC-SOLOTA-IDENTITY",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_IDENTITY_PAGE",
        "Panasonic SOLOTA 製品ページ（NP-TML1）",
        "https://panasonic.jp/dish/SOLOTA.html",
    ),
    _source(
        "SRC-THANKO-RAKUA-MINI-TK-MDW22W",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_PAGE",
        "THANKO ラクアmini TK-MDW22W",
        "https://www.thanko.jp/view/item/000000003922?category_page_id=ct576",
    ),
    _source(
        "SRC-THANKO-RAKUA-MINI-COLOR",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_PAGE",
        "THANKO ラクアmini color（全色再入荷通知）",
        "https://www.thanko.jp/view/item/000000004715?category_page_id=thanko-origin",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-THANKO-RAKUA-MINI-PLUS",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_PAGE",
        "THANKO ラクアmini Plus TK-MDW22B / TK-STTDPSWH",
        "https://www.thanko.jp/view/item/000000004055?category_page_id=thanko-origin",
    ),
    _source(
        "SRC-SIROCA-SS-M171",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_SPECIFICATION_PAGE",
        "siroca 食器洗い乾燥機 ベーシックシリーズ SS-M171",
        "https://www.siroca.co.jp/product/dishwasher_basic/",
    ),
    _source(
        "SRC-SIROCA-SS-M171-MANUAL",
        "MANUFACTURER_OFFICIAL",
        "OFFICIAL_PRODUCT_MANUAL_PDF",
        "siroca SS-M171 取扱説明書・保証書",
        "https://www.siroca.co.jp/im/ss-m171.pdf",
    ),
    _source(
        "SRC-SIROCA-SS-M171-STORE",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "siroca公式ストア SS-M171 通常商品",
        "https://store.siroca.jp/products/ss-m171",
    ),
    _source(
        "SRC-SIROCA-SS-MA251-STORE",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "siroca公式ストア SS-MA251 通常商品",
        "https://store.siroca.jp/products/ss-mu251?variant=41121812643976",
    ),
    _source(
        "SRC-IRISOHYAMA-ISHT-5000-W",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_SPECIFICATION_PAGE",
        "アイリスオーヤマ 食器洗い乾燥機 ISHT-5000-W",
        "https://www.irisohyama.co.jp/products/electrical-appliances/cooking-appliances/other-cooking-appliances/dishwasher/dishwasher",
    ),
    _source(
        "SRC-SIROCA-DISHWASHER-INSTALLATION",
        "MANUFACTURER_OFFICIAL",
        "INSTALLATION_GUIDE",
        "siroca 食器洗い乾燥機 共通据え付け案内",
        "https://www.siroca.co.jp/support/%E9%A3%9F%E5%99%A8%E6%B4%97%E3%81%84%E4%B9%BE%E7%87%A5%E6%A9%9F%EF%BC%9A%E6%8D%AE%E3%81%88%E4%BB%98%E3%81%91%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6-6267995f924c65001d340936",
    ),
    _source(
        "SRC-ELECOM-NESTOUT-700N",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_SPECIFICATION_PAGE",
        "ELECOM NESTOUT ポータブル電源 700N DE-NEPS700NBE",
        "https://www.elecom.co.jp/products/DE-NEPS700NBE.html",
    ),
    _source(
        "SRC-BLUETTI-DISCONTINUED-MODELS",
        "MANUFACTURER_OFFICIAL",
        "LIFECYCLE_INDEX_PAGE",
        "BLUETTI 販売終了製品と代替モデル一覧",
        "https://www.bluetti.jp/pages/bluetti-discontinued-models",
    ),
    _source(
        "SRC-ANKER-SOLIX-C1000-PLUS",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "Anker Solix C1000 Plus Portable Power Station A1765",
        "https://www.ankerjapan.com/products/a1765",
    ),
    _source(
        "SRC-AQUA-ADW-M28B",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_SPECIFICATION_PAGE",
        "AQUA 食器洗い乾燥機 ADW-M28B",
        "https://aqua-has.com/product/m28b/",
    ),
    _source(
        "SRC-PANASONIC-RULO-MINI-MC-RSC10",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_SPECIFICATION_PAGE",
        "Panasonic RULO mini MC-RSC10 仕様",
        "https://panasonic.jp/soji/products/MC-RSC10/spec.html",
    ),
    _source(
        "SRC-EUFY-E20-T2070",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "Eufy Robot Vacuum 3-in-1 E20 T2070",
        "https://www.ankerjapan.com/products/t2070",
    ),
    _source(
        "SRC-EUFY-AUTOEMPTY-C10-T2292",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "Eufy Robot Vacuum Auto-Empty C10 T2292511",
        "https://www.ankerjapan.com/products/t2292",
    ),
    _source(
        "SRC-ROBOROCK-SAROS-10",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_SPECIFICATION_PAGE",
        "Roborock Saros 10",
        "https://jp.roborock.com/pages/roborock-saros-10",
    ),
    _source(
        "SRC-EUFY-OMNI-E25-T2353",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "Eufy Robot Vacuum Omni E25 T2353",
        "https://www.ankerjapan.com/products/t2353",
    ),
    _source(
        "SRC-DREAME-X50-ULTRA",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_SPECIFICATION_PAGE",
        "Dreame X50 Ultra",
        "https://www.dreametech.jp/products/x50-ultra",
    ),
    _source(
        "SRC-ECOVACS-DEEBOT-X8-PRO",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "ECOVACS DEEBOT X8 PRO",
        ("https://www.ecovacs.com/jp/shop/deebot-robotic-vacuum-cleaner/deebot-x8-pro"),
    ),
    _source(
        "SRC-RIMOWA-CABIN-U-82350181",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "RIMOWA Original Cabin U 82350181",
        (
            "https://www.rimowa.com/jp/ja/luggage/colour/green/"
            "%E3%82%AD%E3%83%A3%E3%83%93%E3%83%B3-u/82350181.html"
        ),
    ),
    _source(
        "SRC-SAMSONITE-AUDRINA-SPINNER45",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "Samsonite オードリナ スピナー45",
        "https://www.samsonite.co.jp/luggage/audrina-spinner.html",
    ),
    _source(
        "SRC-MUJI-HARD-CARRY-20L",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "無印良品 バーを自由に調節できる ハードキャリーケース 20L",
        "https://www.muji.com/jp/ja/store/cmdty/detail/4550723184182",
    ),
    _source(
        "SRC-SAMSONITE-C-LITE-SPINNER55EXP-MIDNIGHT",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "Samsonite C-Lite Spinner 55 EXP ミッドナイトブルー",
        (
            "https://www.samsonite.co.jp/samsonite/c-lite/spinner55exp/"
            "midnight_blue/ss-134679-1549.html"
        ),
    ),
    _source(
        "SRC-MUJI-HARD-CARRY-36L-SECTION",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_CATEGORY_PAGE",
        "無印良品 ハードキャリーケース 36L 現行シリーズ",
        "https://www.muji.com/jp/ja/store/cmdty/section/S1000504",
    ),
    _source(
        "SRC-MUJI-FRONT-OPEN-32L",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "無印良品 フロントオープンキャリーケース 32L 黒",
        "https://www.muji.com/jp/ja/store/cmdty/detail/4550584950087",
    ),
    _source(
        "SRC-SAMSONITE-C-LITE-SPINNER55EXP-BLACK",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "Samsonite C-Lite Spinner 55 EXP ブラック",
        (
            "https://www.samsonite.co.jp/samsonite/c-lite/spinner55exp/"
            "black/ss-134679-1041.html"
        ),
    ),
    _source(
        "SRC-SWITCHBOT-K11-WIFI-FUNCTIONS",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_DATA_ENDPOINT",
        "SwitchBot K11+ / K11+ Pro Wi-Fiなしで使える機能",
        (
            "https://support.switch-bot.com/api/v2/help_center/en-us/articles/"
            "14490132658967.json"
        ),
    ),
    _source(
        "SRC-SWITCHBOT-K11-SETUP",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_DATA_ENDPOINT",
        "SwitchBot K11+ / K11+ Pro 初期設定",
        (
            "https://support.switch-bot.com/api/v2/help_center/en-us/articles/"
            "13044997647383.json"
        ),
    ),
    _source(
        "SRC-ECOFLOW-RIVER3-PLUS",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "EcoFlow RIVER 3 Plus",
        "https://jp.ecoflow.com/products/river-3-plus-portable-power-station",
    ),
    _source(
        "SRC-ECOFLOW-DELTA3-PLUS",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "EcoFlow DELTA 3 Plus",
        "https://jp.ecoflow.com/products/delta-3-plus-portable-power-station",
    ),
    _source(
        "SRC-BLUETTI-AORA30-V2",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "BLUETTI AORA 30 V2 グレー",
        "https://www.bluetti.jp/products/bluetti-aora-30-v2-288wh-600w",
    ),
    _source(
        "SRC-BLUETTI-AORA30-V2-DIMENSIONS",
        "MANUFACTURER_OFFICIAL",
        "MANUFACTURER_EDITORIAL_PAGE",
        "BLUETTI公式 AORA 30 V2 重量・寸法",
        "https://www.bluetti.jp/blogs/buying-guide/aora-30-v2-vs-eb3a",
        retrieved_on="2026-09-01",
    ),
    _source(
        "SRC-BLUETTI-AORA100-V2",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_STORE_PAGE",
        "BLUETTI AORA 100 V2 インディゴ",
        (
            "https://www.bluetti.jp/products/"
            "bluetti-aora-100-v2-portable-power-station-blue"
        ),
    ),
    _source(
        "SRC-BLUETTI-AORA-SERIES-COLLECTION",
        "MANUFACTURER_OFFICIAL",
        "PRODUCT_CATEGORY_PAGE",
        "BLUETTI AORAシリーズ ポータブル電源",
        "https://www.bluetti.jp/collections/aora-series-portable-power-stations",
    ),
)


def _claim(
    claim_id: str,
    statement: str,
    evidence_refs: list[str],
    *,
    inference: bool = False,
    dimensions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    claim: dict[str, object] = {
        "claim_id": claim_id,
        "classification": "EDITORIAL_INFERENCE" if inference else "MAJOR_VERIFIABLE",
        "evidence_level": "D" if inference else "A",
        "statement": statement,
        "evidence_refs": evidence_refs,
        "status": (
            "INFERENCE_FROM_BOUND_OFFICIAL_FACTS"
            if inference
            else "BOUND_TO_OFFICIAL_SOURCE"
        ),
    }
    if dimensions:
        claim["dimensions"] = dimensions
    return claim


# Every reader-visible external candidate has one stable claim identity in the
# article's source packet.  The market audit owns the prose and official URL;
# this closed mapping prevents a newly displayed exclusion from bypassing the
# source/locator graph.
MARKET_CANDIDATE_CLAIM_IDS: Final[dict[tuple[str, str], str]] = {
    ("st1703-first-suitcase-comparison", "EXT-ACE-CRESTA-06316"): (
        "CLM-ST1704-SUITCASE-CRESTA-06316-EXCLUDED"
    ),
    ("st1704-portable-power-station-guide", "EXT-ELECOM-NESTOUT-700N"): (
        "CLM-ST1704-POWER-NESTOUT-700N-EXCLUDED"
    ),
    ("st1704-portable-power-station-guide", "EXT-BLUETTI-AC70"): (
        "CLM-ST1704-POWER-AC70-EXCLUDED"
    ),
    ("st1704-portable-power-station-guide", "EXT-BLUETTI-AORA80"): (
        "CLM-ST1704-POWER-AORA80-EXCLUDED"
    ),
    ("st1704-portable-power-station-guide", "EXT-ECOFLOW-RIVER3-PLUS"): (
        "CLM-ST1704-POWER-RIVER3-PLUS-EXCLUDED"
    ),
    ("st1704-portable-power-station-guide", "EXT-ECOFLOW-DELTA3-PLUS"): (
        "CLM-ST1704-POWER-DELTA3-PLUS-EXCLUDED"
    ),
    ("st1704-portable-power-station-guide", "EXT-ECOFLOW-DELTA3-CLASSIC"): (
        "CLM-ST1704-POWER-DELTA3-CLASSIC-EXCLUDED"
    ),
    (
        "st1704-anker-solix-c300-c800-c1000-differences",
        "EXT-ANKER-SOLIX-C1000-PLUS",
    ): "CLM-ST1704-ANKER-C1000-PLUS-EXCLUDED",
    (
        "st1704-countertop-dishwasher-for-small-households",
        "EXT-PANASONIC-NP-TMLK1",
    ): "CLM-ST1704-DISH-NP-TMLK1-EXCLUDED",
    (
        "st1704-countertop-dishwasher-for-small-households",
        "EXT-PANASONIC-NP-TSP2",
    ): "CLM-ST1704-DISH-NP-TSP2-EXCLUDED",
    (
        "st1704-countertop-dishwasher-for-small-households",
        "EXT-THANKO-RAKUA-MINI-COLOR",
    ): "CLM-ST1704-DISH-THANKO-RAKUA-MINI-COLOR-EXCLUDED",
    (
        "st1704-countertop-dishwasher-for-small-households",
        "EXT-AQUA-ADW-M28B",
    ): "CLM-ST1704-DISH-AQUA-M28B-EXCLUDED",
    (
        "st1704-compact-robot-vacuum-shortlist",
        "EXT-PANASONIC-RULO-MINI-MC-RSC10",
    ): "CLM-ST1704-ROBOT-RULO-MINI-REFERENCE",
    ("st1704-compact-robot-vacuum-shortlist", "EXT-EUFY-E20-T2070"): (
        "CLM-ST1704-ROBOT-E20-EXCLUDED"
    ),
    (
        "st1704-compact-robot-vacuum-shortlist",
        "EXT-SWITCHBOT-K10-PRO-COMBO",
    ): "CLM-ST1704-ROBOT-K10-COMBO-EXCLUDED",
    (
        "st1704-compact-robot-vacuum-shortlist",
        "EXT-IROBOT-ROOMBA-MINI-AUTOEMPTY-F155260",
    ): "CLM-ST1704-ROBOT-ROOMBA-MINI-F155260-EXCLUDED",
    ("st1704-compact-robot-vacuum-shortlist", "EXT-ROBOROCK-SAROS-10"): (
        "CLM-ST1704-ROBOT-SAROS10-EXCLUDED"
    ),
    ("st1704-compact-robot-vacuum-shortlist", "EXT-EUFY-OMNI-E25-T2353"): (
        "CLM-ST1704-ROBOT-E25-EXCLUDED"
    ),
    ("st1704-compact-robot-vacuum-shortlist", "EXT-DREAME-X50-ULTRA"): (
        "CLM-ST1704-ROBOT-X50-EXCLUDED"
    ),
    ("st1704-compact-robot-vacuum-shortlist", "EXT-ECOVACS-DEEBOT-X8-PRO"): (
        "CLM-ST1704-ROBOT-X8-EXCLUDED"
    ),
    ("carry-on-suitcase-under-100-seats", "EXT-RIMOWA-CABIN-U"): (
        "CLM-PORTFOLIO-UNDER100-RIMOWA-CABIN-U-EXCLUDED"
    ),
    ("carry-on-suitcase-under-100-seats", "EXT-SAMSONITE-AUDRINA-SPINNER-45"): (
        "CLM-PORTFOLIO-UNDER100-AUDRINA-EXCLUDED"
    ),
    ("carry-on-suitcase-under-100-seats", "EXT-MUJI-HARD-CARRY-20L"): (
        "CLM-PORTFOLIO-UNDER100-MUJI20-EXCLUDED"
    ),
    (
        "lightweight-carry-on-suitcase-under-3kg",
        "EXT-FREQUENTER-LIEVE-1-250-MAINTAINABILITY",
    ): "CLM-PORTFOLIO-LIGHT-FREQUENTER-REFERENCE",
    ("lightweight-carry-on-suitcase-under-3kg", "EXT-MUJI-HARD-CARRY-36L"): (
        "CLM-PORTFOLIO-LIGHT-MUJI36-EXCLUDED"
    ),
    ("front-open-carry-on-suitcase-with-stopper", "EXT-MUJI-FRONT-OPEN-32L"): (
        "CLM-PORTFOLIO-FRONT-MUJI32-EXCLUDED"
    ),
    (
        "front-open-carry-on-suitcase-with-stopper",
        "EXT-BERMAS-INTER-CITY-II-60561",
    ): "CLM-PORTFOLIO-FRONT-BERMAS-60561-EXCLUDED",
    (
        "front-open-carry-on-suitcase-with-stopper",
        "EXT-SAMSONITE-C-LITE-FEATURE",
    ): "CLM-PORTFOLIO-FRONT-C-LITE-REFERENCE",
    ("roomba-mini-vs-switchbot-k11-pro", "EXT-PANASONIC-RULO-MINI-MC-RSC10"): (
        "CLM-PORTFOLIO-ROBOT-RULO-MINI-REFERENCE"
    ),
    (
        "roomba-mini-vs-switchbot-k11-pro",
        "EXT-IROBOT-ROOMBA-MINI-AUTOEMPTY-F155260",
    ): "CLM-PORTFOLIO-ROBOT-ROOMBA-MINI-F155260-EXCLUDED",
    ("solota-vs-rakua-mini-plus", "EXT-THANKO-RAKUA-MINI-PLUS"): (
        "CLM-PORTFOLIO-DISH-RAKUA-MINI-PLUS-EXCLUDED"
    ),
    ("solota-vs-rakua-mini-plus", "EXT-PANASONIC-SOLOTA-NP-TMLK1-K"): (
        "CLM-PORTFOLIO-DISH-SOLOTA-NP-TMLK1-EXCLUDED"
    ),
}

# `considered_portfolio_candidates` are also reader-visible decisions.  They
# are different from the external-market ledger: every referenced product is
# selected in the routed sibling article, but its name and route rationale are
# displayed in the current article.  Keep a closed article/product mapping so
# a new cross-article reference cannot appear without a local claim, official
# product source, and locator.
PORTFOLIO_CANDIDATE_REFERENCE_BINDINGS: Final[
    dict[tuple[str, str], tuple[str, tuple[str, ...]]]
] = {
    (
        "st1703-first-suitcase-comparison",
        "PRD-PROTECA-AEROFLEX-DX2-01521",
    ): (
        "CLM-ST1704-SUITCASE-AEROFLEX-DX2-REFERENCE",
        ("SRC-PROTECA-AEROFLEX-DX2-01521",),
    ),
    (
        "st1704-portable-power-station-guide",
        "PRD-ANKER-SOLIX-C1000-GEN2",
    ): (
        "CLM-ST1704-POWER-C1000-GEN2-REFERENCE",
        ("SRC-ANKER-SOLIX-C1000-GEN2",),
    ),
    (
        "st1704-anker-solix-c300-c800-c1000-differences",
        "PRD-ANKER-SOLIX-C800",
    ): (
        "CLM-ST1704-ANKER-C800-A1753-REFERENCE",
        ("SRC-ANKER-SOLIX-C800",),
    ),
    (
        "st1704-compact-robot-vacuum-shortlist",
        "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",
    ): (
        "CLM-ST1704-ROBOT-F115060-REFERENCE",
        ("SRC-IROBOT-ROOMBA-MINI-SLIM-F115060",),
    ),
    (
        "roomba-mini-vs-switchbot-k11-pro",
        "PRD-EUFY-AUTOEMPTY-C10-T2292",
    ): (
        "CLM-PORTFOLIO-ROBOT-EUFY-C10-BOUNDARY-REFERENCE",
        ("SRC-EUFY-AUTOEMPTY-C10-T2292",),
    ),
    (
        "roomba-mini-vs-switchbot-k11-pro",
        "PRD-ECOVACS-DEEBOT-MINI2",
    ): (
        "CLM-PORTFOLIO-ROBOT-DEEBOT-MINI2-BOUNDARY-REFERENCE",
        ("SRC-ECOVACS-DEEBOT-MINI2",),
    ),
    ("carry-on-suitcase-under-100-seats", "PRD-ACE-MAXPASS4-01471"): (
        "CLM-PORTFOLIO-UNDER100-MAXPASS4-REFERENCE",
        ("SRC-ACE-MAXPASS4-01471",),
    ),
    (
        "front-open-carry-on-suitcase-with-stopper",
        "PRD-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
    ): (
        "CLM-PORTFOLIO-FRONT-RIMOWA-REFERENCE",
        ("SRC-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",),
    ),
}

REALLOCATED_SELECTED_CLAIMS: Final[dict[str, dict[str, object]]] = {
    "CLM-PORTFOLIO-LIGHT-TRIAIR-REFERENCE": {
        "claim_id": "CLM-PORTFOLIO-LIGHT-TRIAIR-01541",
        "statement": (
            "PROTECA Tri-Air 01541は容量35L、本体重量1.8kg、外寸"
            "幅36×奥行23×高さ54cmで、30L以上・3kg以下・100席以上便の"
            "一般的な機内持ち込み目安内という本記事の条件を満たす。"
        ),
        "evidence_refs": ["SRC-PROTECA-TRI-AIR-01541"],
    },
}

# The portfolio owner points Aeroflex DX2 at the PROTECA catalogue while the
# source packet already captures the exact 01521 variant on the same
# manufacturer's official store.  The pair is explicit so a general URL
# mismatch can never be treated as equivalent by inference.
PORTFOLIO_CANDIDATE_SOURCE_URL_ALIASES: Final[
    dict[tuple[str, str], tuple[str, str]]
] = {
    (
        "PRD-PROTECA-AEROFLEX-DX2-01521",
        "SRC-PROTECA-AEROFLEX-DX2-01521",
    ): (
        "https://www.proteca.jp/product/aeroflexDX2/",
        "https://store.ace.jp/shop/g/g01521-09/",
    ),
}

# Selection reasons sometimes compare the external candidate with a selected
# product.  Those selected facts must be in the same claim's evidence graph;
# the candidate page alone is never treated as evidence for a sibling model.
MARKET_CANDIDATE_EXTRA_EVIDENCE_REFS: Final[dict[tuple[str, str], tuple[str, ...]]] = {
    ("st1703-first-suitcase-comparison", "EXT-ACE-CRESTA-06316"): (
        "SRC-PROTECA-TRI-AIR-01541",
    ),
    **{
        ("st1704-compact-robot-vacuum-shortlist", candidate_id): (
            "SRC-EUFY-AUTOEMPTY-C10-T2292",
            "SRC-ECOVACS-DEEBOT-MINI2",
        )
        for candidate_id in (
            "EXT-ROBOROCK-SAROS-10",
            "EXT-EUFY-OMNI-E25-T2353",
            "EXT-DREAME-X50-ULTRA",
            "EXT-ECOVACS-DEEBOT-X8-PRO",
        )
    },
    (
        "st1704-anker-solix-c300-c800-c1000-differences",
        "EXT-ANKER-SOLIX-C1000-PLUS",
    ): (
        "SRC-ANKER-SOLIX-C1000",
        "SRC-ANKER-SOLIX-C1000-GEN2",
    ),
    ("lightweight-carry-on-suitcase-under-3kg", "EXT-MUJI-HARD-CARRY-36L"): (
        "SRC-PROTECA-AEROFLEX-DX2-01521",
        "SRC-SAMSONITE-C-LITE-SPINNER55EXP-MIDNIGHT",
    ),
    (
        "lightweight-carry-on-suitcase-under-3kg",
        "EXT-FREQUENTER-LIEVE-1-250-MAINTAINABILITY",
    ): (
        "SRC-SAMSONITE-C-LITE-SPINNER55EXP-MIDNIGHT",
    ),
    ("front-open-carry-on-suitcase-with-stopper", "EXT-MUJI-FRONT-OPEN-32L"): (
        "SRC-INNOVATOR-INV50",
        "SRC-ACE-DIFFERENCE-05721",
        "SRC-PROTECA-FRESTER-EX-01551",
        "SRC-BERMAS-INTER-CITY-III-60570",
    ),
    (
        "front-open-carry-on-suitcase-with-stopper",
        "EXT-BERMAS-INTER-CITY-II-60561",
    ): (
        "SRC-BERMAS-INTER-CITY-III-60570",
    ),
}

# Reader-visible external dimensions are normalized to named axes just like
# selected-product dimensions.  K10+ Pro Combo is intentionally absent: its
# official station three-tuple has no axis labels, and inferring them is the
# reason that candidate is excluded from the same-dimensions comparison.
MARKET_CANDIDATE_DIMENSIONS: Final[
    dict[tuple[str, str], tuple[dict[str, object], ...]]
] = {
    ("st1704-countertop-dishwasher-for-small-households", "EXT-AQUA-ADW-M28B"): (
        {
            "subject": "AQUA ADW-M28B本体",
            "width_cm": 37.0,
            "depth_cm": 51.0,
            "height_cm": 45.2,
        },
    ),
    ("st1704-compact-robot-vacuum-shortlist", "EXT-ROBOROCK-SAROS-10"): (
        {
            "subject": "Roborock Saros 10本体",
            "width_cm": 35.0,
            "depth_cm": 35.3,
            "height_cm": 7.98,
        },
        {
            "subject": "Roborock Saros 10ドック",
            "width_cm": 40.9,
            "depth_cm": 44.0,
            "height_cm": 47.0,
        },
    ),
    ("st1704-compact-robot-vacuum-shortlist", "EXT-EUFY-OMNI-E25-T2353"): (
        {
            "subject": "Eufy Robot Vacuum Omni E25本体",
            "width_cm": 32.7,
            "depth_cm": 34.6,
            "height_cm": 11.1,
        },
        {
            "subject": "Eufy Robot Vacuum Omni E25ステーション",
            "width_cm": 37.0,
            "depth_cm": 46.2,
            "height_cm": 43.7,
        },
    ),
    ("st1704-compact-robot-vacuum-shortlist", "EXT-DREAME-X50-ULTRA"): (
        {
            "subject": "Dreame X50 Ultra本体（センサー格納時）",
            "width_cm": 35.0,
            "depth_cm": 35.0,
            "height_cm": 8.9,
        },
        {
            "subject": "Dreame X50 Ultraステーション",
            "width_cm": 45.7,
            "depth_cm": 34.0,
            "height_cm": 59.0,
        },
    ),
    ("st1704-compact-robot-vacuum-shortlist", "EXT-ECOVACS-DEEBOT-X8-PRO"): (
        {
            "subject": "ECOVACS DEEBOT X8 PRO本体",
            "width_cm": 35.3,
            "depth_cm": 35.15,
            "height_cm": 9.8,
        },
        {
            "subject": "ECOVACS DEEBOT X8 PROステーション",
            "width_cm": 35.0,
            "depth_cm": 47.7,
            "height_cm": 53.3,
        },
    ),
    ("carry-on-suitcase-under-100-seats", "EXT-RIMOWA-CABIN-U"): (
        {
            "subject": "RIMOWA Original Cabin U 82350181",
            "width_cm": 35.0,
            "depth_cm": 20.0,
            "height_cm": 50.0,
        },
    ),
    (
        "carry-on-suitcase-under-100-seats",
        "EXT-SAMSONITE-AUDRINA-SPINNER-45",
    ): (
        {
            "subject": "Samsonite オードリナ スピナー45",
            "width_cm": 37.5,
            "depth_cm": 24.0,
            "height_cm": 47.5,
        },
    ),
    ("carry-on-suitcase-under-100-seats", "EXT-MUJI-HARD-CARRY-20L"): (
        {
            "subject": "無印良品 ハードキャリーケース 20L 商品番号23184182",
            "width_cm": 32.0,
            "depth_cm": 20.5,
            "height_cm": 47.0,
        },
    ),
    ("front-open-carry-on-suitcase-with-stopper", "EXT-MUJI-FRONT-OPEN-32L"): (
        {
            "subject": "無印良品 フロントオープンキャリーケース 32L 商品番号84950087",
            "width_cm": 37.0,
            "depth_cm": 24.0,
            "height_cm": 54.0,
        },
    ),
    (
        "front-open-carry-on-suitcase-with-stopper",
        "EXT-BERMAS-INTER-CITY-II-60561",
    ): (
        {
            "subject": "BERMAS INTER CITY II 60561",
            "width_cm": 35.0,
            "depth_cm": 25.0,
            "height_cm": 55.0,
        },
    ),
}

IROBOT_F155260_SALES_STATE: Final[dict[str, str]] = {
    "exact_variant": "F155260",
    "status": "OUT_OF_STOCK",
    "checked_at": "2026-08-31T12:39:34Z",
    "source_ref": "SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY",
    "reader_visible_label": "在庫切れ",
    "recommendation_gate": "BLOCKED",
    "cta_gate": "BLOCKED",
}

MARKET_CANDIDATE_FIELD_ADDITIONS: Final[
    dict[tuple[str, str], dict[str, dict[str, str]]]
] = {
    key: {"manufacturer_sales_state": IROBOT_F155260_SALES_STATE}
    for key in (
        (
            "st1704-compact-robot-vacuum-shortlist",
            "EXT-IROBOT-ROOMBA-MINI-AUTOEMPTY-F155260",
        ),
        (
            "roomba-mini-vs-switchbot-k11-pro",
            "EXT-IROBOT-ROOMBA-MINI-AUTOEMPTY-F155260",
        ),
    )
}

NEGATIVE_CLAIM_MARKERS: Final = (
    "なし",
    "非対応",
    "非搭載",
    "未搭載",
    "対象外",
    "対応しない",
)
NEGATIVE_CLAIM_DISCLAIMERS: Final = (
    "非搭載と断定するものではありません",
    "非搭載とは断定しません",
    "未搭載と断定するものではありません",
    "非対応と断定するものではありません",
)
# A closed attestation is required for every affirmative absence statement.
# PRODUCT_PAGE_OMISSION is deliberately not an allowed mode.
NEGATIVE_CLAIM_EVIDENCE: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "CLM-ST1704-POWER-SAFETY-PRACTICE": (
        "EXPLICIT_OFFICIAL_TEXT",
        ("SRC-METI-PORTABLE-POWER-SAFETY",),
    ),
    "CLM-ST1704-ANKER-C1000-FEATURE-DIFF": (
        "OFFICIAL_COMPARISON_TABLE",
        ("SRC-ANKER-SOLIX-C1000-GEN2",),
    ),
    "CLM-ST1704-ANKER-SAFETY-PRACTICE": (
        "EXPLICIT_OFFICIAL_TEXT",
        ("SRC-METI-PORTABLE-POWER-SAFETY",),
    ),
    "CLM-ST1704-ROBOT-EUFY-C10-SPECS": (
        "OFFICIAL_COMPARISON_TABLE",
        ("SRC-EUFY-AUTOEMPTY-C10-T2292",),
    ),
    "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES": (
        "OFFICIAL_COMPARISON_TABLE",
        ("SRC-EUFY-AUTOEMPTY-C10-T2292",),
    ),
    "CLM-PORTFOLIO-LIGHT-RIMOWA-82353171": (
        "EXPLICIT_OFFICIAL_TEXT",
        ("SRC-RIMOWA-WARRANTY-FAQ",),
    ),
    "CLM-PORTFOLIO-ROBOT-ROOMBA-SLIM-F115060": (
        "OFFICIAL_COMPARISON_TABLE",
        ("SRC-IROBOT-ROOMBA-MINI-SLIM-F115060",),
    ),
    "CLM-ST1704-ROBOT-F115060-REFERENCE": (
        "EXPLICIT_OFFICIAL_TEXT",
        ("SRC-IROBOT-ROOMBA-MINI-SLIM-F115060",),
    ),
}

PRODUCT_SAFETY_RECEIPT_DOCUMENT_REF: Final = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/sources/"
    "product-safety-query-receipts.v1.json"
)
PRODUCT_SAFETY_RECEIPT_SCHEMA: Final = "RAOS_PRODUCT_SAFETY_QUERY_RECEIPTS_V1"
PRODUCT_SAFETY_REQUIRED_AUTHORITIES: Final = (
    "MANUFACTURER_OFFICIAL",
    "JAPAN_ADMINISTRATIVE_OFFICIAL",
)


def _dimensions(
    subject: str, width_cm: float, depth_cm: float, height_cm: float
) -> dict[str, object]:
    return {
        "subject": subject,
        "width_cm": width_cm,
        "depth_cm": depth_cm,
        "height_cm": height_cm,
    }


FIRST_FIVE_DIMENSION_CLAIMS: Final[dict[str, tuple[dict[str, object], ...]]] = {
    "CLM-ST1704-SUITCASE-TRIAIR-01541-SPECS": (
        _dimensions("PROTECA Tri-Air 01541", 37, 23, 55),
    ),
    "CLM-ST1704-SUITCASE-DIFFERENCE-SPECS": (
        _dimensions("ディフェレンス 05721（通常時）", 36, 24, 55),
        _dimensions("ディフェレンス 05721（拡張時）", 36, 27, 55),
    ),
    "CLM-ST1704-SUITCASE-MAXPASS-SPECS": (
        _dimensions("PROTECA マックスパス4 01471", 40, 25, 50),
    ),
    "CLM-ST1704-SUITCASE-CARRYON-LIMITS": (
        _dimensions("ANA国内線100席以上機内持ち込み上限", 40, 25, 55),
        _dimensions("ANA国内線100席未満機内持ち込み上限", 35, 20, 45),
    ),
    "CLM-ST1704-POWER-C300-SPECS": (
        _dimensions("Anker Solix C300本体", 16.4, 16.1, 24.0),
    ),
    "CLM-ST1704-POWER-AORA30-V2-SPECS": (
        _dimensions("BLUETTI AORA 30 V2本体", 25.0, 17.8, 16.75),
    ),
    "CLM-ST1704-POWER-JACKERY-SPECS": (
        # The manual gives the raw three values; a separate Jackery-official
        # table labels them 幅×奥行×高さ.  Both are bound before normalization.
        _dimensions("Jackery ポータブル電源 500 New本体", 31.1, 20.5, 15.7),
    ),
    "CLM-ST1704-POWER-ANKER-C800-SPECS": (
        _dimensions("Anker Solix C800本体", 37.1, 20.5, 25.0),
    ),
    "CLM-ST1704-POWER-DJI-1000-V2-SPECS": (
        _dimensions(
            "DJI Power 1000 V2本体（公式L×W×Hを幅・奥行・高さへ正規化）",
            22.5,
            44.8,
            23.0,
        ),
    ),
    "CLM-ST1704-POWER-AORA100-V2-SPECS": (
        _dimensions("BLUETTI AORA 100 V2本体", 32.0, 21.5, 25.0),
    ),
    "CLM-ST1704-ANKER-C300-SPECS": (
        _dimensions("Anker Solix C300本体", 16.4, 16.1, 24.0),
    ),
    "CLM-ST1704-ANKER-C800-SPECS": (
        _dimensions("Anker Solix C800 Plus本体", 37.1, 20.5, 25.0),
    ),
    "CLM-ST1704-ANKER-C1000-SPECS": (
        _dimensions("Anker Solix C1000本体", 37.6, 20.5, 26.7),
    ),
    "CLM-ST1704-ANKER-C1000-GEN2-SPECS": (
        _dimensions("Anker Solix C1000 Gen 2本体", 38.4, 20.8, 24.4),
    ),
    "CLM-ST1704-DISH-SS-M171-SPECS": (
        _dimensions("siroca SS-M171本体", 42.0, 43.5, 43.5),
        _dimensions("siroca SS-M171ドア開放時", 42.0, 76.0, 43.5),
    ),
    "CLM-ST1704-DISH-RAKUA-SPECS": (
        _dimensions("THANKO ラクアmini TK-MDW22W本体", 30.8, 31.5, 41.5),
        _dimensions("THANKO ラクアmini TK-MDW22W扉開放時", 30.8, 59.4, 41.5),
    ),
    "CLM-ST1704-DISH-SS-MA251-SPECS": (
        _dimensions("siroca SS-MA251本体", 42.0, 44.0, 47.0),
    ),
    "CLM-ST1704-DISH-TOSHIBA-DWS-33B-SPECS": (
        _dimensions("東芝 DWS-33B(W)本体", 42.0, 43.5, 46.5),
    ),
    "CLM-ST1704-DISH-CONDITIONAL-CHOICES": (
        _dimensions("siroca SS-M171本体", 42.0, 43.5, 43.5),
        _dimensions("THANKO ラクアmini TK-MDW22W本体", 30.8, 31.5, 41.5),
        _dimensions("siroca SS-MA251本体", 42.0, 44.0, 47.0),
        _dimensions("東芝 DWS-33B(W)本体", 42.0, 43.5, 46.5),
    ),
    "CLM-ST1704-ROBOT-EUFY-C10-SPECS": (
        _dimensions("Eufy Auto-Empty C10本体 T2292511", 32.5, 32.3, 7.2),
        _dimensions("Eufy Auto-Empty C10ステーション", 27.5, 19.1, 21.2),
    ),
    "CLM-ST1704-ROBOT-K11-PRO-SPECS": (
        _dimensions("SwitchBot K11+ Pro本体", 24.8, 24.8, 9.2),
        _dimensions("SwitchBot K11+ Proステーション", 24.0, 18.0, 25.0),
    ),
    "CLM-ST1704-ROBOT-DEEBOT-MINI2-SPECS": (
        _dimensions("ECOVACS DEEBOT mini 2本体", 28.6, 28.6, 9.98),
        _dimensions("ECOVACS DEEBOT mini 2ステーション", 32.0, 40.0, 38.5),
    ),
    "CLM-ST1704-ROBOT-ROOMBA-515-SPECS": (
        _dimensions("ルンバ本体", 29.8, 30.3, 8.4),
        _dimensions("AutoWash充電ステーション", 33.0, 34.0, 48.5),
    ),
    "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES": (
        _dimensions("Eufy Auto-Empty C10本体 T2292511", 32.5, 32.3, 7.2),
        _dimensions("Eufy Auto-Empty C10ステーション", 27.5, 19.1, 21.2),
        _dimensions("SwitchBot K11+ Pro本体", 24.8, 24.8, 9.2),
        _dimensions("SwitchBot K11+ Proステーション", 24.0, 18.0, 25.0),
        _dimensions("ECOVACS DEEBOT mini 2本体", 28.6, 28.6, 9.98),
        _dimensions("ECOVACS DEEBOT mini 2ステーション", 32.0, 40.0, 38.5),
        _dimensions("Roomba Plus 515 Combo本体", 29.8, 30.3, 8.4),
        _dimensions("Roomba Plus 515 AutoWash充電ステーション", 33.0, 34.0, 48.5),
    ),
}

ROBOT_CONDITIONAL_STATEMENT: Final = (
    "比較対象4モデルの公表寸法では、Eufy Auto-Empty C10は本体が幅32.5×"
    "奥行32.3×高さ7.2cm、ステーションが幅27.5×奥行19.1×高さ21.2cmで、"
    "水拭きを選定条件にせず、薄型本体と自動ゴミ収集を優先する候補である。"
    "K11+ Proは本体24.8×24.8×9.2cm・ステーション24.0×18.0×25.0cm、"
    "DEEBOT mini 2は本体28.6×28.6×9.98cm・ステーション32.0×40.0×"
    "38.5cm、Roomba Plus 515 Comboは本体29.8×30.3×8.4cm・ステーション"
    "33.0×34.0×48.5cmである。4候補の役割は、C10が水拭きなしの薄型本体と"
    "自動ゴミ収集、K11+ Proが小型本体・自動ゴミ収集・使い捨てお掃除シート、"
    "DEEBOT mini 2が30cm未満の本体とモップ自動洗浄・熱風乾燥、Roomba Plus "
    "515 Comboが自動給水・モップ温水洗浄・温風乾燥である。K10+ Pro Comboの"
    "ステーション寸法は公式の3値に軸ラベルがないうえ、コードレス掃除機との"
    "共用ステーションという別用途のため、現行4候補から除外する。"
    "自動ゴミ収集、水拭き、モップ自動洗浄・乾燥という方式差でも候補が分かれる。"
)

FIRST_FIVE_STATEMENT_OVERRIDES: Final[dict[str, str]] = {
    "CLM-ST1704-SUITCASE-TRIAIR-01541-SPECS": (
        "PROTECA Tri-Air 01541はキャスターとハンドルを含む外寸H55×W37×D23cm、"
        "3辺合計115cm、35L、1.8kg、ポリプロピレン製、日本製である。"
        "通常製品保証は素材・製造上の不具合を10年間、プレミアムケアは"
        "対象購入品の運送中破損を購入後3年間対象とする。キャスターストッパーと"
        "容量拡張は公式商品ページ内の表示だけでは確定できないため未確認とし、"
        "推奨根拠に使わない。"
    ),
    "CLM-ST1704-SUITCASE-CARRYON-LIMITS": (
        "ANAは国内線の100席以上機で幅40cm以内・奥行25cm以内・高さ55cm以内・"
        "3辺合計115cm以内、100席未満機で幅35cm以内・奥行20cm以内・"
        "高さ45cm以内・3辺合計100cm以内を"
        "案内している。身の回り品は2026年7月1日搭乗分より幅30×奥行20×高さ40cm"
        "以内と明確化される。"
    ),
    "CLM-ST1704-SUITCASE-DIFFERENCE-SPECS": (
        "ディフェレンス 05721は非拡張時H55×W36×D24cm、32L、3.5kg、"
        "拡張時D27cm、38Lで、フロントオープン（前開き）とセンターオープンの"
        "2通り、拡張機能、キャスターストッパーが案内されている。"
    ),
    "CLM-ST1704-SUITCASE-CONDITIONAL-CHOICES": (
        "公表値ではTri-Air 1.8kg、ディフェレンス3.5kg、マックスパス4 3.6kgのため、"
        "Tri-Airが3モデルで最軽量、マックスパス4が最も重い。通常容量は順に"
        "35L、32L、40Lのためマックスパス4が最大で、ディフェレンスはフロント"
        "オープン（前開き）とセンターオープンの2通りとストッパー、マックスパス4は"
        "フロントポケットからメイン収納へのアクセスが条件別候補になる。"
    ),
    "CLM-ST1704-POWER-C300-SPECS": (
        "Anker Solix C300 Portable Power Station（型番A17225Z1）は288Wh、"
        "定格300W、約4.1kg、幅約16.4×奥行約16.1×高さ約24.0cmと案内されている。"
    ),
    "CLM-ST1704-POWER-JACKERY-SPECS": (
        "Jackery ポータブル電源 500 New（JE-500A）は512Wh、定格500W、"
        "約5.7kgである。取扱説明書の約311×205×157mmは、Jackery公式の"
        "幅×奥行×高さ表に基づき幅31.1×奥行20.5×高さ15.7cmへ軸を明示して比較する。"
        "LiFePO4電池を採用し、"
        "6000回の充放電後も容量70%以上を維持すると案内されている。"
    ),
    "CLM-ST1704-POWER-ANKER-C800-SPECS": (
        "Anker Solix C800 Portable Power Station（A17535Z1）は768Wh、"
        "定格1200W、約10.5kg、幅約37.1×奥行約20.5×高さ約25.0cmである。"
        "リン酸鉄リチウムイオン電池を採用し、3000回以上の充放電後も"
        "初期容量80%以上を維持すると案内されている。"
    ),
    "CLM-ST1704-POWER-DJI-1000-V2-SPECS": (
        "DJI Power 1000 V2（DYM1000V2L）は1024Wh、最大連続出力2600W、約14.2kg、"
        "公式L×W×H 448×225×230mmである。比較表では幅22.5×"
        "奥行44.8×高さ23.0cmと軸を明示する。LFP電池を採用し、"
        "公式条件下の4000サイクル後に80%以上の容量維持と案内される。"
    ),
    "CLM-ST1704-POWER-CONDITIONAL-CHOICES": (
        "比較した7モデルの公表値はC300が288Wh・定格300W・約4.1kg、AORA 30 V2が"
        "288Wh・定格600W・約4.3kg、Jackery 500 Newが512Wh・定格500W・約5.7kg、"
        "Anker Solix C800が768Wh・定格1200W・約10.5kg、Jackery 1000 New V3が"
        "1024Wh・AC定格1500W・約10.6kg、AORA 100 V2が1024Wh・定格1800W・"
        "約11.5kg、DJI Power 1000 V2が1024Wh・最大連続2600W・約14.2kgである。"
        "C300の288Whは7モデルで最小容量（AORA 30 V2も同じ288Wh）であり、"
        "C300が7モデルで最軽量、"
        "AORA 30 V2はC300より約0.2kg重い一方、同じ288Whで定格出力を広げる。"
        "接続機器の通常時・起動時電力を確認し、AORA 30 V2の定格600Wを超える機器には使わない。"
        "AORA "
        "100 V2は1024Wh帯でJackeryとDJIの間の重量となる。"
        "C800はDJI Power 1000 V2より約3.7kg軽い。各社公表の"
        "連続供給目安は呼称・試験条件が"
        "異なるため、定格出力と最大連続出力を同一指標として大小比較しない。"
        "接続機器の通常時・起動時電力と同時使用の合計を各製品の条件へ個別に照合し、"
        "必要容量、安全に運べる重量、保管条件、保証・サポートでも候補を変える。"
    ),
    "CLM-ST1704-DISH-SS-M171-SPECS": (
        "siroca SS-M171は標準収納16点、使用水量約5L、幅42×奥行43.5×高さ43.5cmで、"
        "タンク式と分岐水栓式の2WAY給水、送風乾燥に対応する。ドア開放時奥行は76cmである。"
    ),
    "CLM-ST1704-DISH-RAKUA-SPECS": (
        "THANKO ラクアmini（型番TK-MDW22W）は食器11〜12点、3.2L、"
        "幅308×高さ415×奥行315mm、扉開放時奥行594mm、約8kgのタンク式で、"
        "下ノズル噴射式と熱風乾燥に対応すると案内されている。"
    ),
    "CLM-ST1704-DISH-TOSHIBA-DWS-33B-SPECS": (
        "東芝DWS-33B(W)は食器18点、約6L、幅420×奥行435×高さ465mm、"
        "約13kgのタンク式で、回転スプレーアームと天井ノズル、"
        "ヒーターとファンによる強制排気乾燥に対応する。"
    ),
    "CLM-ST1704-DISH-CONDITIONAL-CHOICES": (
        "公表値ではSS-M171が奥行43.5cm・約5L・食器16点、ラクアminiが"
        "奥行31.5cm・3.2L・食器11〜12点、SS-MA251が奥行44cm・約6L・食器16点、"
        "DWS-33Bが奥行43.5cm・約6L・食器18点である。現行4候補ではラクアminiが"
        "幅・奥行・標準使用水量で最小、DWS-33Bが標準食器点数で最大である。"
        "SS-M171はタンク式と分岐水栓式の2WAY給水、SS-MA251はオートオープンに"
        "対応するため、設置寸法、食器点数、水量、給水・乾燥・扉方式で候補が変わる。"
        "この記事は1〜2人暮らしを対象とし、現行4候補の標準食器点数は11〜18点である。"
        "SOLOTA NP-TMLK1-Kは販売状態未確認のため、購入候補ではなく仕様参考に限定する。"
    ),
    "CLM-ST1704-ANKER-C300-SPECS": (
        "Anker Solix C300 Portable Power Station（型番A17225Z1）は288Wh、"
        "定格300W、約4.1kg、幅約16.4×奥行約16.1×高さ約24.0cmである。"
    ),
    "CLM-ST1704-ANKER-C800-SPECS": (
        "Anker Solix C800 Plus Portable Power Station（型番A1754）は768Wh、"
        "定格1200W、約10.9kg、幅約37.1×奥行約20.5×高さ約25.0cmである。"
    ),
    "CLM-ST1704-ANKER-C1000-SPECS": (
        "Anker Solix C1000 Portable Power Station（型番A17615Z1）は1056Wh、"
        "定格1500W、約12.9kg、幅約37.6×奥行約20.5×高さ約26.7cmで、"
        "別売りの専用拡張バッテリーにより2112Whへ拡張できる。"
    ),
    "CLM-ST1704-ANKER-C1000-GEN2-SPECS": (
        "Anker Solix C1000 Gen 2 Portable Power Station（型番A17635Z1）は"
        "1024Wh、定格1550W、約11.3kg、幅約38.4×奥行約20.8×高さ約24.4cmである。"
    ),
    "CLM-ST1704-ROBOT-EUFY-C10-SPECS": (
        "Eufy Robot Vacuum Auto-Empty C10のブラックT2292511は、本体が"
        "幅32.5×奥行32.3×高さ7.2cm・約2.5kg、ステーションが幅27.5×"
        "奥行19.1×高さ21.2cm・約1.8kgで、自動ゴミ収集に対応する。公式比較表の"
        "水拭き欄は「-」であり、水拭き非対応として扱う。2.4GHz Wi-Fiだけに"
        "対応し、パッケージ案内は"
        "18か月保証にAnker会員登録後6か月を加える。2026年8月31日の公式ストア"
        "確認時は在庫わずか表示で、交換用ダストバッグ、サイドブラシ、フィルター、"
        "回転ブラシ、バッテリーへの販売導線を確認できた。"
    ),
    "CLM-ST1704-ROBOT-DEEBOT-MINI2-SPECS": (
        "ECOVACS DEEBOT mini 2は本体が幅28.6×奥行28.6×高さ9.98cm、"
        "ステーションが幅32.0×奥行40.0×高さ38.5cmである。"
        "メーカーは吸引力10000Pa、モップの6mm自動リフト、"
        "自動ゴミ収集・自動給水・モップ自動洗浄・63℃熱風乾燥を"
        "案内している。ビデオマネージャーでは外出先からの見守り、声かけ、"
        "スクリーンショットに対応するため、遠隔見守りを使わない人もカメラ・音声・"
        "アプリ利用を購入条件として確認する。保証は通常1年で、2026年2月20日以降の正規販売店購入品は"
        "購入後30日以内のアプリ連携などの条件を満たす場合に2年保証と案内される。"
    ),
    "CLM-ST1704-ROBOT-ROOMBA-515-SPECS": (
        "Roomba Plus 515 Combo（型番N285060）は本体が幅29.8×奥行30.3×高さ8.4cm、"
        "ステーションが幅33.0×奥行34.0×高さ48.5cmで、DualCleanモップパッドを"
        "備え、ゴミ収集、自動給水、モップパッドの温水洗浄・温風乾燥に対応する。"
    ),
    "CLM-ST1704-ANKER-C1000-FEATURE-DIFF": (
        "Anker公式比較表では、C1000 Gen 2は拡張バッテリー非対応、AC出力5口、"
        "USB-C 3口、電池4,000回サイクルとされ、C1000は拡張バッテリー対応、"
        "AC出力6口、USB-C 2口、SurgePad 2000W、電池3,000回サイクルとされる。"
        "同じ公式ページ内で停電時切り替え時間に約0.01秒と約0.02秒の記載が"
        "併存するため、この値は推奨根拠に含めない。SurgePadには精密機器や"
        "電圧保護機能を持つ機器など対象外がある。"
    ),
    "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES": (
        ROBOT_CONDITIONAL_STATEMENT
        + " C10は4モデルで本体高さが最小である。ステーションの底面はK11+ Proの"
        "幅24.0×奥行18.0cmより大きいため、薄型本体と設置面積を混同しない。"
    ),
}

FIRST_FIVE_ADDITIONAL_CLAIMS: Final[dict[str, tuple[dict[str, object], ...]]] = {
    "SPV-ST1704-SUITCASE-V1": (
        _claim(
            "CLM-ST1704-SUITCASE-CRESTA-06316-EXCLUDED",
            "ACE クレスタ 06316は通常時34L、拡張時39L、3.2kgである一方、最軽量を"
            "選ぶ役割では1.8kgのTri-Air 01541が優れるため商品カードから外した。"
            "クレスタの拡張性を否定せず、耐久性の優劣も判定しない。",
            ["SRC-ACE-CRESTA-06316"],
        ),
    ),
    "SPV-ST1704-PORTABLE-POWER-V1": (
        _claim(
            "CLM-ST1704-POWER-AORA30-V2-SPECS",
            "BLUETTI AORA 30 V2（グレー）は288Wh、定格600W、約4.3kg、"
            "本体寸法幅25.0×奥行17.8×高さ16.75cmの現行モデルである。"
            "リン酸鉄リチウムイオン電池、3,000回以上の公表サイクル、5年保証、"
            "アプリ、国内アフターサポートとリサイクルプログラムが案内される。"
            "商品別のリコール照合、修理条件、交換部品の供給期間は別途確認する。",
            [
                "SRC-BLUETTI-AORA30-V2",
                "SRC-BLUETTI-AORA30-V2-DIMENSIONS",
                "SRC-BLUETTI-AORA-SERIES-COLLECTION",
            ],
            dimensions=[
                _dimensions("BLUETTI AORA 30 V2本体", 25.0, 17.8, 16.75),
            ],
        ),
        _claim(
            "CLM-ST1704-POWER-AORA100-V2-SPECS",
            "BLUETTI AORA 100 V2（インディゴ）は1024Wh、定格1800W、"
            "約11.5kg、本体寸法幅32.0×奥行21.5×高さ25.0cmの現行モデルである。"
            "リン酸鉄リチウムイオン電池、4,000回以上の公表サイクル、5年保証、"
            "アプリ、国内アフターサポートとリサイクルプログラムが案内される。"
            "商品別のリコール照合、修理条件、交換部品の供給期間は別途確認する。",
            [
                "SRC-BLUETTI-AORA100-V2",
                "SRC-BLUETTI-AORA-SERIES-COLLECTION",
            ],
            dimensions=[
                _dimensions("BLUETTI AORA 100 V2本体", 32.0, 21.5, 25.0),
            ],
        ),
        _claim(
            "CLM-ST1704-POWER-JACKERY-1000-NEW-V3-SPECS",
            "Jackery ポータブル電源 1000 New V3（JE-1000G／JE-1000G-WH）は、"
            "容量1024Wh、AC定格出力1500W、重量約10.6kg、本体寸法"
            "幅31.4×奥行20.1×高さ23.4cmの現行モデルである。出力値は各社で"
            "呼称・試験条件が異なるため、DJIの最大連続出力と数値だけで順位付けしない。",
            [
                "SRC-JACKERY-1000-NEW-V3",
                "SRC-JACKERY-1000-NEW-V3-LAUNCH",
            ],
            dimensions=[
                _dimensions("Jackery 1000 New V3本体", 31.4, 20.1, 23.4),
            ],
        ),
        _claim(
            "CLM-ST1704-POWER-AC70-EXCLUDED",
            "BLUETTI AC70は公式ページで終売・売り切れと表示されるため、"
            "現在購入できる候補としては除外した。仕様が劣るとは判定しない。",
            ["SRC-BLUETTI-AC70"],
        ),
        _claim(
            "CLM-ST1704-POWER-DELTA3-CLASSIC-EXCLUDED",
            "EcoFlow DELTA 3 Classicは標準単品の読者向け表示に売り切れが出る"
            "一方、同じページの構造化データはavailable=trueで矛盾していた。"
            "構造化データのみを優先せず売り切れと判定し、現行候補から除外した。",
            ["SRC-ECOFLOW-DELTA3-CLASSIC"],
        ),
        _claim(
            "CLM-ST1704-POWER-JACKERY-STORAGE",
            "Jackery 500 Newの取扱説明書は、電池残量が0%にならないよう長期保管中は"
            "3か月に一度の充電を勧めている。",
            ["SRC-JACKERY-500-NEW-MANUAL"],
        ),
        _claim(
            "CLM-ST1704-POWER-JACKERY-WARRANTY",
            "Jackery 500 Newの取扱説明書は購入日から3年間、延長保証登録でさらに"
            "2年間と案内し、公式オンラインストアまたは正規代理店での購入などを"
            "適用条件としている。",
            ["SRC-JACKERY-500-NEW-MANUAL"],
        ),
        _claim(
            "CLM-ST1704-POWER-SAFETY-PRACTICE",
            "経済産業省は、ポータブル電源が電気用品安全法の規制対象外である一方、"
            "火災・感電等の電気的リスクがあるとして安全性要求事項を公表している。"
            "購入前と保管中は、対象型番のリコール、メーカーのBMS・温度条件、"
            "異常時の修理・回収窓口を確認する。",
            ["SRC-METI-PORTABLE-POWER-SAFETY", "SRC-METI-ELECTRICAL-RECALLS"],
        ),
    ),
    "SPV-ST1704-DISHWASHER-V1": (
        _claim(
            "CLM-ST1704-DISH-SS-M171-SPECS",
            "siroca SS-M171は幅42×奥行43.5×高さ43.5cm、約13kg、標準収納16点、"
            "使用水量約5Lで、タンク式と分岐水栓式の2WAY、送風乾燥に対応する。"
            "ドア開放時奥行は76.0cmである。",
            [
                "SRC-SIROCA-SS-M171",
                "SRC-SIROCA-SS-M171-MANUAL",
                "SRC-SIROCA-DISHWASHER-INSTALLATION",
                "SRC-SIROCA-SS-M171-STORE",
            ],
            dimensions=[
                _dimensions("siroca SS-M171本体", 42, 43.5, 43.5),
                _dimensions("siroca SS-M171ドア開放時", 42, 76.0, 43.5),
            ],
        ),
        _claim(
            "CLM-ST1704-DISH-NP-TSP2-LAUNCH-REFERENCE",
            "Panasonic NP-TSP2は2026年9月発売予定で、9月1日時点の公式申込みは"
            "予約受付中、発送は9月中旬以降と案内されている。これは発売時期と"
            "申込み画面の表示を確認した事実であり、現行販売中とは判定しない。",
            [
                "SRC-PANASONIC-NP-TSP2-LAUNCH",
                "SRC-PANASONIC-NP-TSP2-SUBSCRIPTION",
            ],
        ),
        _claim(
            "CLM-ST1704-DISH-NP-TSP2-EXCLUDED",
            "Panasonic NP-TSP2は2026年9月発売予定で、9月1日時点の公式申込みは"
            "予約受付中、発送は9月中旬以降と案内されている。発売前のため"
            "AVAILABLEとは判定せず、現在の購入候補から除外した。",
            [
                "SRC-PANASONIC-NP-TSP2-LAUNCH",
                "SRC-PANASONIC-NP-TSP2-SUBSCRIPTION",
            ],
        ),
        _claim(
            "CLM-ST1704-DISH-TOSHIBA-DWS-33B-SUPPORT",
            "東芝は食器洗い乾燥機の補修用性能部品を、製造打ち切り後6年保有すると"
            "案内している。DWS-33B(W)の保守性を確認する際は、このカテゴリ別の"
            "保有期間と、購入時点の修理受付・部品供給状況を分けて確認する。",
            ["SRC-TOSHIBA-PARTS-RETENTION"],
        ),
    ),
    "SPV-ST1704-ROBOT-VACUUM-V1": (
        _claim(
            "CLM-ST1704-ROBOT-K10-COMBO-EXCLUDED",
            "SwitchBot K10+ Pro Comboはコードレス掃除機とロボット掃除機を"
            "同じステーションへまとめる別用途で、公式のステーション3値に軸ラベルが"
            "ないため設置寸法を同じ基準で比較できない。自動モップ洗浄・乾燥を含む"
            "小型ロボット掃除機の比較枠から除外し、機能の劣位とは判定しない。",
            ["SRC-SWITCHBOT-K10-PRO-COMBO"],
        ),
        _claim(
            "CLM-ST1704-ROBOT-K11-PRO-WARRANTY-UNRESOLVED",
            "SwitchBot公式の有料5年延長保証ページはK11+ Proを対象型番に含め、"
            "元のメーカー保証期間を『1年または2年』と案内するが、K11+ Proが"
            "どちらに当たるかは同ページだけでは確定できない。無償保証期間を"
            "推奨根拠に使わず、購入経路・対象条件・有料延長の要否を購入時に確認する。",
            ["SRC-SWITCHBOT-K11-PRO-EXTENDED-WARRANTY"],
            inference=True,
        ),
    ),
    "SPV-ST1704-ANKER-DIFFERENCES-V1": (
        _claim(
            "CLM-ST1704-ANKER-CONDITIONAL-CHOICES",
            "公表値ではC300が288Wh・定格300W・約4.1kgで4モデル中最小かつ最軽量、"
            "C800 Plusが768Wh・定格1200W・約10.9kgでC300より容量と出力が大きく、"
            "C1000系2モデルより軽い。C1000は1056Whを2112Whへ拡張でき、C1000 "
            "Gen 2はC1000より約1.6kg軽く定格出力が50W高い一方、容量が32Wh小さい。"
            "必要出力、運べる重量、容量拡張、端子数で候補が変わる。C300は"
            "300W以内、C800 Plusは1200W以内の機器を条件とし、300Wを超える"
            "機器はC800 Plus以上の出力帯を検討する。C1000 Gen 2は"
            "4,000回以上の公表サイクル数を条件にする場合の候補である。",
            [
                "SRC-ANKER-SOLIX-C300",
                "SRC-ANKER-SOLIX-C800-PLUS",
                "SRC-ANKER-SOLIX-C1000",
                "SRC-ANKER-SOLIX-C1000-GEN2",
            ],
            inference=True,
        ),
        _claim(
            "CLM-ST1704-ANKER-SAFETY-PRACTICE",
            "経済産業省は、ポータブル電源が電気用品安全法の規制対象外である一方、"
            "火災・感電等の電気的リスクがあるとして安全性要求事項を公表している。"
            "Anker Solixも容量や出力だけで決めず、購入する型番の安全上の注意、"
            "使用温度、リコール、国内保証の条件、修理・回収窓口を購入前に確認する。",
            ["SRC-METI-PORTABLE-POWER-SAFETY", "SRC-METI-ELECTRICAL-RECALLS"],
        ),
    ),
}


# Reader-facing propositions that combine already captured official facts are
# kept on the existing comparison/inference claims.  This explicit appendix is
# part of the source-packet owner (and therefore its packet/capture hashes); it
# prevents a value that happens to occur elsewhere in a multi-product packet
# from being used as semantic support for the wrong decision or product.
ANKER_POWER_DUE_DILIGENCE_APPENDIX: Final = (
    " 型番一致の安全マニュアルは、分解せず不具合時はカスタマーサポートへ"
    "連絡すること、一般ごみとして廃棄しないこと、0〜40℃の乾燥した環境で"
    "保管し、3か月に一度を目安に残量を確認して100%まで充電することを案内する。"
    "公式商品ページはAnker Japan公式オンラインストア会員を対象に、通常18か月の"
    "保証を最大5年へ延長すると案内する。Anker Solixの国内サポートページでは、"
    "国内修理センターと電話・LINE・メール・チャットの窓口、送料購入者負担の"
    "使用済み・故障品回収を確認できた。一方、型番別リコール照合記録、交換部品の"
    "供給期間、個別の修理料金は確認できていないため、公開判定は停止したままとする。"
)

READER_SEMANTIC_APPENDICES: Final[dict[str, str]] = {
    "CLM-ST1704-POWER-AORA30-V2-SPECS": (
        " AORAシリーズ公式情報はLiFePO4、5年保証、国内アフターサポート、"
        "リサイクルプログラムを案内する。一方、型番別リコール照合記録、"
        "個別修理条件、交換部品の供給期間は確認できていないため、"
        "安全・保証・保守性を優位性の根拠にせず公開判定は停止したままとする。"
    ),
    "CLM-ST1704-POWER-AORA100-V2-SPECS": (
        " AORAシリーズ公式情報はLiFePO4、5年保証、国内アフターサポート、"
        "リサイクルプログラムを案内する。一方、型番別リコール照合記録、"
        "個別修理条件、交換部品の供給期間は確認できていないため、"
        "安全・保証・保守性を優位性の根拠にせず公開判定は停止したままとする。"
    ),
    "CLM-ST1704-POWER-C300-SPECS": ANKER_POWER_DUE_DILIGENCE_APPENDIX,
    "CLM-ST1704-POWER-ANKER-C800-SPECS": ANKER_POWER_DUE_DILIGENCE_APPENDIX,
    "CLM-ST1704-ANKER-C300-SPECS": ANKER_POWER_DUE_DILIGENCE_APPENDIX,
    "CLM-ST1704-ANKER-C800-SPECS": ANKER_POWER_DUE_DILIGENCE_APPENDIX,
    "CLM-ST1704-ANKER-C1000-SPECS": ANKER_POWER_DUE_DILIGENCE_APPENDIX,
    "CLM-ST1704-ANKER-C1000-GEN2-SPECS": ANKER_POWER_DUE_DILIGENCE_APPENDIX,
    "CLM-ST1704-POWER-JACKERY-SPECS": (
        " 公式商品ページは、ChargeShieldテクノロジー2.0に62種類の保護機能と"
        "BMSを搭載すると案内する。これはメーカー公表の安全機能であり、型番別"
        "リコール照合の代替にはしない。"
    ),
    "CLM-ST1704-POWER-JACKERY-WARRANTY": (
        " 現行の商品ページは保証登録不要の3年＋2年自動延長と案内する一方、"
        "固定したJE-500A取扱説明書は延長保証登録で2年追加と案内しており、"
        "保証の手続条件に関する公式文言が一致しない。購入前にJackery Japanへ"
        "確認する。国内修理はカスタマーサポートから申し込み、日本国内販売の"
        "Jackeryポータブル電源本体は無償回収の対象だが、返送送料は利用者負担で"
        "ある。型番別リコール照合記録、交換部品の供給期間、個別の修理料金は"
        "確認できていないため、公開判定は停止したままとする。"
    ),
    "CLM-ST1704-POWER-DJI-1000-V2-SPECS": (
        " 型番DYM1000V2L/DYM1000V2Hの日本語安全ガイドラインは、接地済み"
        "コンセント、非分解、換気、規定温度、損傷時の使用停止と公式サポートへの"
        "連絡を案内する。日本語ユーザーマニュアルは長期保管時60%、涼しく乾燥した"
        "場所、6か月に1回の充放電、乾いた布での清掃、通常の廃棄コンテナに入れず"
        "DJIの回収窓口へ相談することを案内する。DJI Japanのアフターサービス"
        "表ではPower 1000 V2本体が60か月、修理はオンライン受付とされる。"
        "型番別リコール照合記録、交換部品の供給期間、個別の修理料金は確認できて"
        "いないため、公開判定は停止したままとする。"
    ),
    "CLM-ST1704-ANKER-C1000-FEATURE-DIFF": (
        " C1000はC1000 Gen 2にはない容量拡張に対応し、AC出力6口とSurgePad "
        "2000W対応を公表する。"
    ),
    "CLM-ST1704-ANKER-CONDITIONAL-CHOICES": (
        " C800 Plusの容量帯はC300より大きく、C1000系より小さい。必要出力と"
        "持ち運べる重さを満たす最小の容量帯から選ぶ。C300とC800 Plusのアクセサリ"
        "互換性、および4モデルの実効容量は公式情報で確認できないため、推奨根拠に"
        "使わない。"
    ),
    "CLM-ST1704-DISH-CONDITIONAL-CHOICES": (
        " ラクアmini TK-MDW22Wは幅約31cm（308mm）である。DWS-33Bは"
        "標準食器18点とヒーター+ファン強制排気乾燥を条件にする容量候補である。"
    ),
    "CLM-PORTFOLIO-UNDER100-CONDITIONAL-CHOICES": (
        " フレスターEX 01550は前開きである。"
    ),
    "CLM-PORTFOLIO-LIGHT-CONDITIONAL-CHOICES": (
        " 5候補の最小通常容量は35Lで、ハードとソフトがあり、拡張できるモデルは通常時と拡張時を"
        "分ける。通常容量は35L、36L、37L、38Lを含み、40L前後を優先する場合は拡張"
        "容量も確認する。Aeroflexは2.1kg、RIMOWAは2.2kg、APPLITEは2.1kg、"
        "C-Liteは2.1kg、Tri-Airは1.8kgである。"
    ),
    "CLM-PORTFOLIO-LIGHT-ANA-RULE": (
        " 100席未満便は別の小さい寸法上限であり、身の回り品は高さ40cm以内である。"
    ),
    "CLM-PORTFOLIO-FRONT-CONDITIONAL-CHOICES": (
        " 4モデルはフロントオープンとキャスターストッパーを条件に比較する。"
        "通常時はINV50・05721・01551が3辺合計115cm、60570が114cmで、拡張時は別に判断する。前開きと"
        "中央開きの2WAY、独立PCポケット、3ROOM、前から全体へアクセスする構造を"
        "区別する。60570は13インチまでを目安とするPC収納と、前面からメイン収納へ届く"
        "2in1構造を備える。メーカーはキャスターを『ストッパー付き55mm静音キャスター』と表記するが、"
        "編集部は走行音を実測しておらず、静音性を選定根拠に使わない。PCの実寸と保護性は購入前に確認する。"
    ),
    "CLM-PORTFOLIO-FRONT-FRESTER-01551": (
        " 前から全体へアクセスする構造で、中央開きはできない。"
    ),
    "CLM-PORTFOLIO-ROBOT-K11-PRO": (
        " 本体ボタンではWi-Fi接続前でも基本的な清掃を開始できる。スケジュールと"
        "マップなどはSwitchBotアプリとのWi-Fi接続が必要で、初期設定では"
        "アプリへのログインと2.4GHz Wi-Fiへの接続を案内している。"
    ),
}


def _manufacturer_sales_state_row(product_id: str) -> dict[str, object]:
    document = json.loads(
        MANUFACTURER_SALES_STATE_PATH.read_text(encoding="utf-8")
    )
    products = document.get("products")
    if not isinstance(products, list):
        raise ValueError("manufacturer sales-state products must be a list")
    matches = [
        row
        for row in products
        if isinstance(row, dict) and row.get("product_id") == product_id
    ]
    if len(matches) != 1:
        raise ValueError(
            f"manufacturer sales-state row must be unique: {product_id}"
        )
    return matches[0]


_EUFY_T2292511_MSS: Final = _manufacturer_sales_state_row(
    "PRD-EUFY-AUTOEMPTY-C10-T2292"
)
_C_LITE_134679_1549_MSS: Final = _manufacturer_sales_state_row(
    "PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549"
)
_DIFFERENCE_05721_06_MSS: Final = _manufacturer_sales_state_row(
    "PRD-ACE-DIFFERENCE-05721"
)
_ANKER_C300_MSS: Final = _manufacturer_sales_state_row("PRD-ANKER-SOLIX-C300")
_ANKER_C800_PLUS_MSS: Final = _manufacturer_sales_state_row(
    "PRD-ANKER-SOLIX-C800-PLUS"
)
_ANKER_C1000_MSS: Final = _manufacturer_sales_state_row("PRD-ANKER-SOLIX-C1000")
_ANKER_C1000_GEN2_MSS: Final = _manufacturer_sales_state_row(
    "PRD-ANKER-SOLIX-C1000-GEN2"
)
_THANKO_RAKUA_MINI_MSS: Final = _manufacturer_sales_state_row(
    "PRD-THANKO-RAKUA-MINI-TK-MDW22W"
)
_SIROCA_SS_M171_MSS: Final = _manufacturer_sales_state_row("PRD-SIROCA-SS-M171")
_SIROCA_SS_MA251_MSS: Final = _manufacturer_sales_state_row("PRD-SIROCA-SS-MA251")
for _mss_row, _expected_scope, _expected_url in (
    (
        _EUFY_T2292511_MSS,
        "MODEL",
        "https://www.ankerjapan.com/products/t2292",
    ),
    (
        _C_LITE_134679_1549_MSS,
        "MODEL",
        "https://www.samsonite.co.jp/samsonite/c-lite/spinner55exp/"
        "midnight_blue/ss-134679-1549.html",
    ),
    (
        _DIFFERENCE_05721_06_MSS,
        "VARIANT",
        "https://store.ace.jp/shop/g/g05721-06/",
    ),
    (_ANKER_C300_MSS, "MODEL", "https://www.ankerjapan.com/products/a1722"),
    (
        _ANKER_C800_PLUS_MSS,
        "MODEL",
        "https://www.ankerjapan.com/products/a1754",
    ),
    (_ANKER_C1000_MSS, "MODEL", "https://www.ankerjapan.com/products/a1761"),
    (
        _ANKER_C1000_GEN2_MSS,
        "MODEL",
        "https://www.ankerjapan.com/products/a1763",
    ),
    (
        _THANKO_RAKUA_MINI_MSS,
        "MODEL",
        "https://www.thanko.jp/view/item/000000003922?category_page_id=ct576",
    ),
    (_SIROCA_SS_M171_MSS, "MODEL", "https://www.siroca.co.jp/product/dishwasher_basic/"),
    (_SIROCA_SS_MA251_MSS, "MODEL", "https://www.siroca.co.jp/product/dishwasher_advance/"),
):
    if (
        _mss_row.get("state") != "AVAILABLE"
        or _mss_row.get("availability_scope") != _expected_scope
        or _mss_row.get("official_url") != _expected_url
        or not isinstance(_mss_row.get("checked_at_utc"), str)
    ):
        raise ValueError(
            "selected embedded sales state no longer matches the owner MSS row: "
            f"{_mss_row.get('product_id')}"
        )

EUFY_T2292511_SALES_STATE: Final[dict[str, object]] = {
    "product_id": "PRD-EUFY-AUTOEMPTY-C10-T2292",
    "exact_variant": "ブラック・日本向けT2292511",
    "status": "AVAILABLE",
    "checked_at": _EUFY_T2292511_MSS["checked_at_utc"],
    "source_ref": "SRC-EUFY-AUTOEMPTY-C10-T2292",
    "reader_visible_label": "在庫わずか",
    "selection_gate": "ELIGIBLE",
    "variant_caveat": _EUFY_T2292511_MSS["variant_caveat"],
}

C_LITE_134679_1549_SALES_STATE: Final[dict[str, object]] = {
    "product_id": "PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549",
    "exact_variant": "ミッドナイトブルー・日本向け134679-1549（SKU CS2*31007）",
    "status": "AVAILABLE",
    "checked_at": _C_LITE_134679_1549_MSS["checked_at_utc"],
    "source_ref": "SRC-SAMSONITE-C-LITE-SPINNER55EXP-MIDNIGHT",
    "reader_visible_label": "カートに入れる",
    "selection_gate": "ELIGIBLE",
    "variant_caveat": _C_LITE_134679_1549_MSS["variant_caveat"],
}

DIFFERENCE_05721_06_SALES_STATE: Final[dict[str, object]] = {
    "product_id": "PRD-ACE-DIFFERENCE-05721",
    "exact_variant": "ホワイト・05721-06",
    "status": "AVAILABLE",
    "checked_at": _DIFFERENCE_05721_06_MSS["checked_at_utc"],
    "source_ref": "SRC-ACE-DIFFERENCE-05721",
    "reader_visible_label": "在庫あります",
    "selection_gate": "ELIGIBLE",
    "variant_caveat": _DIFFERENCE_05721_06_MSS["variant_caveat"],
}


def _available_model_sales_state(
    *,
    row: dict[str, object],
    exact_variant: str,
    source_ref: str,
) -> dict[str, object]:
    """Project one exact owner MSS row without inferring sibling availability."""

    return {
        "product_id": row["product_id"],
        "exact_variant": exact_variant,
        "status": "AVAILABLE",
        "checked_at": row["checked_at_utc"],
        "source_ref": source_ref,
        # This is an exact reader-visible string.  The separate cart control is
        # still required by the source locator for every projected claim.
        "reader_visible_label": "在庫わずか",
        "selection_gate": "ELIGIBLE",
        "variant_caveat": row["variant_caveat"],
    }


ANKER_C300_SALES_STATE: Final = _available_model_sales_state(
    row=_ANKER_C300_MSS,
    exact_variant="日本向け掲載モデル（A17225Z1 / A1722511）",
    source_ref="SRC-ANKER-SOLIX-C300",
)
ANKER_C800_PLUS_SALES_STATE: Final = _available_model_sales_state(
    row=_ANKER_C800_PLUS_MSS,
    exact_variant="日本向け掲載モデル（A17545Z1 / A1754511）",
    source_ref="SRC-ANKER-SOLIX-C800-PLUS",
)
ANKER_C1000_SALES_STATE: Final = _available_model_sales_state(
    row=_ANKER_C1000_MSS,
    exact_variant="日本向け掲載モデル（A17615Z1 / A1761521 / A1761511）",
    source_ref="SRC-ANKER-SOLIX-C1000",
)
ANKER_C1000_GEN2_SALES_STATE: Final = _available_model_sales_state(
    row=_ANKER_C1000_GEN2_MSS,
    exact_variant="日本向け掲載モデル（A17635Z1 / A1763521）",
    source_ref="SRC-ANKER-SOLIX-C1000-GEN2",
)

THANKO_RAKUA_MINI_SALES_STATE: Final = {
    "product_id": "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
    "exact_variant": "ラクアmini単体 TK-MDW22W（JAN 4580060593095）",
    "status": "AVAILABLE",
    "checked_at": _THANKO_RAKUA_MINI_MSS["checked_at_utc"],
    "source_ref": "SRC-THANKO-RAKUA-MINI-TK-MDW22W",
    "reader_visible_label": "カートに入れる",
    "selection_gate": "ELIGIBLE",
    "variant_caveat": _THANKO_RAKUA_MINI_MSS["variant_caveat"],
}

SIROCA_SS_M171_SALES_STATE: Final = {
    "product_id": "PRD-SIROCA-SS-M171",
    "exact_variant": "SS-M171・メタリックウォームグレー",
    "status": "AVAILABLE",
    "checked_at": _SIROCA_SS_M171_MSS["checked_at_utc"],
    "source_ref": "SRC-SIROCA-SS-M171-STORE",
    "reader_visible_label": "購入する",
    "selection_gate": "ELIGIBLE",
    "variant_caveat": _SIROCA_SS_M171_MSS["variant_caveat"],
}

SIROCA_SS_MA251_SALES_STATE: Final = {
    "product_id": "PRD-SIROCA-SS-MA251",
    "exact_variant": "通常商品・オートオープンタイプ／シルバー（SS-MA251）",
    "status": "AVAILABLE",
    "checked_at": _SIROCA_SS_MA251_MSS["checked_at_utc"],
    "source_ref": "SRC-SIROCA-SS-MA251-STORE",
    "reader_visible_label": "購入する",
    "selection_gate": "ELIGIBLE",
    "variant_caveat": _SIROCA_SS_MA251_MSS["variant_caveat"],
}

READER_SEMANTIC_FIELD_ADDITIONS: Final[
    dict[str, dict[str, dict[str, object]]]
] = {
    **{
        claim_id: {"manufacturer_sales_state": EUFY_T2292511_SALES_STATE}
        for claim_id in (
            "CLM-ST1704-ROBOT-EUFY-C10-SPECS",
            "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES",
        )
    },
    "CLM-PORTFOLIO-LIGHT-SAMSONITE-C-LITE-134679-1549": {
        "manufacturer_sales_state": C_LITE_134679_1549_SALES_STATE
    },
    **{
        claim_id: {
            "manufacturer_sales_state": DIFFERENCE_05721_06_SALES_STATE
        }
        for claim_id in (
            "CLM-ST1704-SUITCASE-DIFFERENCE-SPECS",
            "CLM-PORTFOLIO-FRONT-DIFFERENCE-05721",
        )
    },
    "CLM-ST1704-POWER-C300-SPECS": {
        "manufacturer_sales_state": ANKER_C300_SALES_STATE
    },
    "CLM-ST1704-ANKER-C300-SPECS": {
        "manufacturer_sales_state": ANKER_C300_SALES_STATE
    },
    "CLM-ST1704-ANKER-C800-SPECS": {
        "manufacturer_sales_state": ANKER_C800_PLUS_SALES_STATE
    },
    "CLM-ST1704-ANKER-C1000-SPECS": {
        "manufacturer_sales_state": ANKER_C1000_SALES_STATE
    },
    "CLM-ST1704-ANKER-C1000-GEN2-SPECS": {
        "manufacturer_sales_state": ANKER_C1000_GEN2_SALES_STATE
    },
    "CLM-ST1704-DISH-SS-M171-SPECS": {
        "manufacturer_sales_state": SIROCA_SS_M171_SALES_STATE
    },
    "CLM-ST1704-DISH-RAKUA-SPECS": {
        "manufacturer_sales_state": THANKO_RAKUA_MINI_SALES_STATE
    },
    "CLM-ST1704-DISH-SS-MA251-SPECS": {
        "manufacturer_sales_state": SIROCA_SS_MA251_SALES_STATE
    },
}

READER_SEMANTIC_EVIDENCE_ADDITIONS: Final[dict[str, tuple[str, ...]]] = {
    "CLM-ST1704-POWER-C300-SPECS": (
        "SRC-ANKER-SOLIX-C300-SAFETY-MANUAL",
        "SRC-ANKER-SOLIX-JP-SUPPORT",
    ),
    "CLM-ST1704-POWER-ANKER-C800-SPECS": (
        "SRC-ANKER-SOLIX-C800-SAFETY-MANUAL",
        "SRC-ANKER-SOLIX-JP-SUPPORT",
    ),
    "CLM-ST1704-ANKER-C300-SPECS": (
        "SRC-ANKER-SOLIX-C300-SAFETY-MANUAL",
        "SRC-ANKER-SOLIX-JP-SUPPORT",
    ),
    "CLM-ST1704-ANKER-C800-SPECS": (
        "SRC-ANKER-SOLIX-C800-PLUS-SAFETY-MANUAL",
        "SRC-ANKER-SOLIX-JP-SUPPORT",
    ),
    "CLM-ST1704-ANKER-C1000-SPECS": (
        "SRC-ANKER-SOLIX-C1000-SAFETY-MANUAL",
        "SRC-ANKER-SOLIX-JP-SUPPORT",
    ),
    "CLM-ST1704-ANKER-C1000-GEN2-SPECS": (
        "SRC-ANKER-SOLIX-C1000-GEN2-SAFETY-MANUAL",
        "SRC-ANKER-SOLIX-JP-SUPPORT",
    ),
    "CLM-ST1704-POWER-JACKERY-WARRANTY": (
        "SRC-JACKERY-500-NEW",
        "SRC-JACKERY-JP-REPAIR-SERVICE",
        "SRC-JACKERY-JP-RECYCLING",
    ),
    "CLM-ST1704-POWER-DJI-1000-V2-SPECS": (
        "SRC-DJI-POWER-1000-V2-SAFETY-GUIDELINES-JA",
        "SRC-DJI-POWER-1000-V2-USER-MANUAL-JA",
        "SRC-DJI-JP-AFTERSALES-POLICY",
    ),
    "CLM-PORTFOLIO-ROBOT-K11-PRO": (
        "SRC-SWITCHBOT-K11-WIFI-FUNCTIONS",
        "SRC-SWITCHBOT-K11-SETUP",
    ),
    "CLM-ST1704-DISH-SS-M171-SPECS": ("SRC-SIROCA-SS-M171-STORE",),
    "CLM-ST1704-DISH-SS-MA251-SPECS": ("SRC-SIROCA-SS-MA251-STORE",),
}

# Publication remains blocked until product-specific official recall queries
# are recorded.  This closed matrix ensures the other six due-diligence axes
# for every selected power-station model are nevertheless bound to the exact
# article-local claim group and official sources; a generic safety paragraph
# cannot satisfy it.
POWER_STATION_DUE_DILIGENCE_GROUPS: Final = (
    {
        "article_id": "st1704-portable-power-station-guide",
        "product_id": "PRD-ANKER-SOLIX-C300",
        "claim_ids": ("CLM-ST1704-POWER-C300-SPECS",),
        "required_source_refs": (
            "SRC-ANKER-SOLIX-C300",
            "SRC-ANKER-SOLIX-C300-SAFETY-MANUAL",
            "SRC-ANKER-SOLIX-JP-SUPPORT",
        ),
        "required_statement_fragments": (
            "分解せず",
            "一般ごみとして廃棄しない",
            "3か月に一度",
            "最大5年",
            "国内修理センター",
            "故障品回収",
            "型番別リコール照合記録",
            "公開判定は停止",
        ),
    },
    {
        "article_id": "st1704-portable-power-station-guide",
        "product_id": "PRD-BLUETTI-AORA30-V2",
        "claim_ids": ("CLM-ST1704-POWER-AORA30-V2-SPECS",),
        "required_source_refs": (
            "SRC-BLUETTI-AORA30-V2",
            "SRC-BLUETTI-AORA30-V2-DIMENSIONS",
            "SRC-BLUETTI-AORA-SERIES-COLLECTION",
        ),
        "required_statement_fragments": (
            "LiFePO4",
            "5年保証",
            "国内アフターサポート",
            "リサイクルプログラム",
            "型番別リコール照合記録",
            "個別修理条件",
            "交換部品の供給期間",
            "公開判定は停止",
        ),
    },
    {
        "article_id": "st1704-portable-power-station-guide",
        "product_id": "PRD-JACKERY-500-NEW",
        "claim_ids": (
            "CLM-ST1704-POWER-JACKERY-SPECS",
            "CLM-ST1704-POWER-JACKERY-STORAGE",
            "CLM-ST1704-POWER-JACKERY-WARRANTY",
        ),
        "required_source_refs": (
            "SRC-JACKERY-500-NEW",
            "SRC-JACKERY-500-NEW-MANUAL",
            "SRC-JACKERY-JP-REPAIR-SERVICE",
            "SRC-JACKERY-JP-RECYCLING",
        ),
        "required_statement_fragments": (
            "62種類の保護機能",
            "BMS",
            "3か月に一度",
            "3年＋2年自動延長",
            "公式文言が一致しない",
            "国内修理",
            "無償回収",
            "型番別リコール照合記録",
            "公開判定は停止",
        ),
    },
    {
        "article_id": "st1704-portable-power-station-guide",
        "product_id": "PRD-ANKER-SOLIX-C800",
        "claim_ids": ("CLM-ST1704-POWER-ANKER-C800-SPECS",),
        "required_source_refs": (
            "SRC-ANKER-SOLIX-C800",
            "SRC-ANKER-SOLIX-C800-SAFETY-MANUAL",
            "SRC-ANKER-SOLIX-JP-SUPPORT",
        ),
        "required_statement_fragments": (
            "分解せず",
            "一般ごみとして廃棄しない",
            "3か月に一度",
            "最大5年",
            "国内修理センター",
            "故障品回収",
            "型番別リコール照合記録",
            "公開判定は停止",
        ),
    },
    {
        "article_id": "st1704-portable-power-station-guide",
        "product_id": "PRD-DJI-POWER-1000-V2",
        "claim_ids": ("CLM-ST1704-POWER-DJI-1000-V2-SPECS",),
        "required_source_refs": (
            "SRC-DJI-POWER-1000-V2-STORE",
            "SRC-DJI-POWER-1000-V2-SPECS",
            "SRC-DJI-POWER-1000-V2-SAFETY-GUIDELINES-JA",
            "SRC-DJI-POWER-1000-V2-USER-MANUAL-JA",
            "SRC-DJI-JP-AFTERSALES-POLICY",
        ),
        "required_statement_fragments": (
            "DYM1000V2L/DYM1000V2H",
            "非分解",
            "6か月に1回",
            "通常の廃棄コンテナに入れず",
            "60か月",
            "オンライン受付",
            "型番別リコール照合記録",
            "公開判定は停止",
        ),
    },
    {
        "article_id": "st1704-portable-power-station-guide",
        "product_id": "PRD-BLUETTI-AORA100-V2",
        "claim_ids": ("CLM-ST1704-POWER-AORA100-V2-SPECS",),
        "required_source_refs": (
            "SRC-BLUETTI-AORA100-V2",
            "SRC-BLUETTI-AORA-SERIES-COLLECTION",
        ),
        "required_statement_fragments": (
            "LiFePO4",
            "5年保証",
            "国内アフターサポート",
            "リサイクルプログラム",
            "型番別リコール照合記録",
            "個別修理条件",
            "交換部品の供給期間",
            "公開判定は停止",
        ),
    },
    *(
        {
            "article_id": "st1704-anker-solix-c300-c800-c1000-differences",
            "product_id": product_id,
            "claim_ids": (claim_id,),
            "required_source_refs": (product_source, safety_source, "SRC-ANKER-SOLIX-JP-SUPPORT"),
            "required_statement_fragments": (
                "分解せず",
                "一般ごみとして廃棄しない",
                "3か月に一度",
                "最大5年",
                "国内修理センター",
                "故障品回収",
                "型番別リコール照合記録",
                "公開判定は停止",
            ),
        }
        for product_id, claim_id, product_source, safety_source in (
            (
                "PRD-ANKER-SOLIX-C300",
                "CLM-ST1704-ANKER-C300-SPECS",
                "SRC-ANKER-SOLIX-C300",
                "SRC-ANKER-SOLIX-C300-SAFETY-MANUAL",
            ),
            (
                "PRD-ANKER-SOLIX-C800-PLUS",
                "CLM-ST1704-ANKER-C800-SPECS",
                "SRC-ANKER-SOLIX-C800-PLUS",
                "SRC-ANKER-SOLIX-C800-PLUS-SAFETY-MANUAL",
            ),
            (
                "PRD-ANKER-SOLIX-C1000",
                "CLM-ST1704-ANKER-C1000-SPECS",
                "SRC-ANKER-SOLIX-C1000",
                "SRC-ANKER-SOLIX-C1000-SAFETY-MANUAL",
            ),
            (
                "PRD-ANKER-SOLIX-C1000-GEN2",
                "CLM-ST1704-ANKER-C1000-GEN2-SPECS",
                "SRC-ANKER-SOLIX-C1000-GEN2",
                "SRC-ANKER-SOLIX-C1000-GEN2-SAFETY-MANUAL",
            ),
        )
    ),
)


def _packet(
    source_packet_ref: str,
    article_id: str,
    source_refs: list[str],
    claims: list[dict[str, object]],
) -> dict[str, object]:
    verifiable = sum(claim["classification"] == "MAJOR_VERIFIABLE" for claim in claims)
    return {
        "source_packet_ref": source_packet_ref,
        "article_id": article_id,
        "approval_status": "READY_FOR_HUMAN_PUBLICATION_REVIEW",
        "capture_status": "STRUCTURED_FACT_SNAPSHOT_CAPTURED",
        "fact_packet_sha256": "0" * 64,
        "source_refs": source_refs,
        "claims": claims,
        "draft_claim_coverage": {
            "major_claim_count": len(claims),
            "official_source_bound_major_claim_count": len(claims),
            "verifiable_claim_count": verifiable,
            "official_source_bound_verifiable_claim_count": verifiable,
        },
    }


def _refresh_packet_coverage(packet: dict[str, object]) -> None:
    claims = packet["claims"]
    verifiable = sum(claim["classification"] == "MAJOR_VERIFIABLE" for claim in claims)
    packet["draft_claim_coverage"] = {
        "major_claim_count": len(claims),
        "official_source_bound_major_claim_count": len(claims),
        "verifiable_claim_count": verifiable,
        "official_source_bound_verifiable_claim_count": verifiable,
    }


UNDER100_PRODUCTS: Final = [
    "SRC-PROTECA-STARIA-CXR-02350",
    "SRC-PROTECA-FRESTER-EX-01550",
    "SRC-ACE-PALISADES3-Z-06910",
    "SRC-BERMAS-INTER-CITY-60524",
]
LIGHT_PRODUCTS: Final = [
    "SRC-PROTECA-TRI-AIR-01541",
    "SRC-PROTECA-AEROFLEX-DX2-01521",
    "SRC-PROTECA-SUITCASE-WARRANTY",
    "SRC-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
    "SRC-RIMOWA-LIFETIME-GUARANTEE",
    "SRC-RIMOWA-WARRANTY-FAQ",
    "SRC-SAMSONITE-C-LITE-CS2-09007",
    "SRC-SAMSONITE-CATALOG-2025",
    "SRC-AMERICAN-TOURISTER-APPLITE4-QJ6-68002",
    "SRC-FREQUENTER-LIEVE-1-250",
]
FRONT_PRODUCTS: Final = [
    "SRC-INNOVATOR-INV50",
    "SRC-ACE-DIFFERENCE-05721",
    "SRC-PROTECA-FRESTER-EX-01551",
    "SRC-BERMAS-INTER-CITY-III-60570",
]
ROBOT_PRODUCTS: Final = [
    "SRC-SWITCHBOT-K11-PRO",
    "SRC-SWITCHBOT-K11-PRO-EXTENDED-WARRANTY",
    "SRC-IROBOT-ROOMBA-MINI-SLIM-F115060",
    "SRC-SWITCHBOT-AUTOEMPTY-INSTALLATION-SPACE",
]
DISH_PRODUCTS: Final = [
    "SRC-PANASONIC-NP-TMLK1",
    "SRC-THANKO-RAKUA-MINI-PLUS",
]


NEW_PACKETS: Final = (
    _packet(
        "SPV-PORTFOLIO-UNDER100-SUITCASE-V1",
        "carry-on-suitcase-under-100-seats",
        [
            *UNDER100_PRODUCTS,
            "SRC-ANA-DOMESTIC-CARRY-ON",
            "SRC-JAL-DOMESTIC-CARRY-ON",
        ],
        [
            _claim(
                "CLM-PORTFOLIO-UNDER100-STARIA-02350",
                "PROTECA スタリアCXR 02350は外寸H45×W34×D20cm（幅34×奥行20×高さ45cm）、3辺合計99cm、22L、2.4kgで、キャスターストッパーを備える。",
                ["SRC-PROTECA-STARIA-CXR-02350"],
                dimensions=[_dimensions("スタリアCXR 02350", 34, 20, 45)],
            ),
            _claim(
                "CLM-PORTFOLIO-UNDER100-FRESTER-01550",
                "PROTECA フレスターEX 01550は通常時外寸H45×W34×D20cm、99cm、26L、拡張時は奥行24cm、103cm、33Lで、2.8kg、フロントオープンとキャスターストッパーを備える。",
                ["SRC-PROTECA-FRESTER-EX-01550"],
                dimensions=[
                    _dimensions("フレスターEX 01550（通常時）", 34, 20, 45),
                    _dimensions("フレスターEX 01550（拡張時）", 34, 24, 45),
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-UNDER100-PALISADES-06910",
                "ace. パリセイド3-Z 06910は外寸H45×W34×D20cm（幅34×奥行20×高さ45cm）、3辺合計99cm、21L、2.6kgで、フロントオープンとキャスターストッパーを備える。",
                ["SRC-ACE-PALISADES3-Z-06910"],
                dimensions=[_dimensions("パリセイド3-Z 06910", 34, 20, 45)],
            ),
            _claim(
                "CLM-PORTFOLIO-UNDER100-BERMAS-60524",
                "BERMAS INTER CITY 60524は全体外寸W34×H45×D20cm（幅34×奥行20×高さ45cm）、約22L、約2.8kg（付属物を除く）で、13インチPC収納目安、ストッパーを備える。現行新仕様はUSBポート廃止と案内される。",
                ["SRC-BERMAS-INTER-CITY-60524"],
                dimensions=[_dimensions("INTER CITY 60524", 34, 20, 45)],
            ),
            _claim(
                "CLM-PORTFOLIO-UNDER100-ANA-RULE",
                "ANAは100席未満の国内線について、3辺の和100cm以内かつ幅35cm以内・"
                "奥行20cm以内・高さ45cm以内、"
                "身の回り品は2026年7月1日搭乗分より幅30cm以内・奥行20cm以内・"
                "高さ40cm以内、機内持ち込み手荷物1個と"
                "身の回り品1個の合計2個、総重量10kg以内と案内している。",
                ["SRC-ANA-DOMESTIC-CARRY-ON"],
                dimensions=[
                    _dimensions("ANA国内線100席未満機内持ち込み上限", 35, 20, 45),
                    _dimensions("ANA国内線身の回り品上限", 30, 20, 40),
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-UNDER100-JAL-RULE",
                "JALは100席未満の国内線について、付属品を含め幅35cm以内・奥行20cm以内・"
                "高さ45cm以内かつ3辺合計100cm以内、機内持ち込み品の合計重量10kg以内と案内している。",
                ["SRC-JAL-DOMESTIC-CARRY-ON"],
                dimensions=[
                    _dimensions("JAL国内線100席未満機内持ち込み上限", 35, 20, 45)
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-UNDER100-CONDITIONAL-CHOICES",
                "ANAとJALが案内する100席未満便の上限は、幅35×奥行20×高さ45cm・"
                "3辺合計100cmで、100席以上便の幅40×奥行25×高さ55cm・"
                "3辺合計115cmより小さい。4モデルの通常時外寸はいずれも幅34×奥行20×"
                "高さ45cm、3辺合計99cmである。合計は上限より1cm小さいが、高さと"
                "奥行は各辺の上限と同じため、すべての軸に1cmの差があるわけではない。"
                "公表重量はスタリアCXRが最軽量、通常容量はフレスターEXが最大、"
                "パリセイド3-Zが最小で、前開き、PC収納、ストッパー、拡張時の規定超過を"
                "条件として選び分ける。",
                [
                    *UNDER100_PRODUCTS,
                    "SRC-ANA-DOMESTIC-CARRY-ON",
                    "SRC-JAL-DOMESTIC-CARRY-ON",
                ],
                inference=True,
            ),
        ],
    ),
    _packet(
        "SPV-PORTFOLIO-LIGHTWEIGHT-SUITCASE-V1",
        "lightweight-carry-on-suitcase-under-3kg",
        [
            *LIGHT_PRODUCTS,
            "SRC-ANA-DOMESTIC-CARRY-ON",
            "SRC-JAL-DOMESTIC-CARRY-ON",
        ],
        [
            _claim(
                "CLM-PORTFOLIO-LIGHT-TRIAIR-01541",
                "PROTECA Tri-Air 01541はキャスターとハンドルを含む外寸が"
                "高さ55×幅37×奥行23cm、3辺合計115cm、35L、1.8kgの"
                "ポリプロピレン製・日本製である。通常製品保証は素材・製造上の"
                "不具合を10年間、プレミアムケアは対象購入品の運送中破損を"
                "購入後3年間対象とする。キャスターストッパーと容量拡張は"
                "公式商品ページ内の表示だけでは確定できないため未確認とし、"
                "推奨根拠に使わない。",
                ["SRC-PROTECA-TRI-AIR-01541"],
                dimensions=[
                    _dimensions("PROTECA Tri-Air 01541", 37, 23, 55)
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-LIGHT-RIMOWA-82353171",
                "RIMOWA Essential Lite キャビン 82353171は、ホイールとハンドルを"
                "含む外寸が高さ55×幅37×奥行23cm、37L、2.2kgのポリカーボネート製で、"
                "2026年8月31日に公式ストアで在庫ありとカート追加を確認できた。"
                "2022年7月25日以降に購入した新品スーツケースは機能面の不具合を"
                "対象とする永久保証が適用される。通常使用のキズやへこみ、不適切な"
                "使用、誤用または乱用による損傷は対象外である。",
                [
                    "SRC-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
                    "SRC-RIMOWA-LIFETIME-GUARANTEE",
                    "SRC-RIMOWA-WARRANTY-FAQ",
                ],
                dimensions=[
                    _dimensions("RIMOWA Essential Lite キャビン 82353171", 37, 23, 55)
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-LIGHT-AEROFLEX-01521",
                "PROTECA エアロフレックスDX2 01521は外寸H55×W36×D23cm、"
                "35L、2.1kg、キャスターストッパー付き、日本製である。通常製品保証は"
                "素材・製造上の不具合を10年間、プレミアムケアは対象購入品の運送中破損を"
                "購入後3年間対象とする。耐久性を実機比較したとは扱わない。",
                [
                    "SRC-PROTECA-AEROFLEX-DX2-01521",
                    "SRC-PROTECA-SUITCASE-WARRANTY",
                ],
                dimensions=[
                    _dimensions("PROTECA エアロフレックスDX2 01521", 36, 23, 55)
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-LIGHT-SAMSONITE-C-LITE-134679-1549",
                "Samsonite C-Lite Spinner 55 EXP 134679-1549のミッドナイトブルー"
                "（SKU CS2*31007）は、通常時が幅40×奥行20×高さ55cm・36L、"
                "拡張時が奥行23cm・42L、重量2.1kgで、Curv素材、USBポート、"
                "エキスパンダブル機能を備える。日本公式ページは条件付き10年保証、"
                "電子機器部分は購入後1年と案内し、2026年8月31日の確認時に"
                "「カートに入れる」購入UIを確認した。通常時の3辺合計は115cm、"
                "拡張時は118cmとなるため、機内持ち込み判定は通常時と分ける。",
                [
                    "SRC-SAMSONITE-C-LITE-CS2-09007",
                    "SRC-SAMSONITE-CATALOG-2025",
                    "SRC-SAMSONITE-C-LITE-SPINNER55EXP-MIDNIGHT",
                ],
                dimensions=[
                    _dimensions(
                        "Samsonite C-Lite 134679-1549（通常時）", 40, 20, 55
                    ),
                    _dimensions(
                        "Samsonite C-Lite 134679-1549（拡張時）", 40, 23, 55
                    ),
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-LIGHT-APPLITE-QJ6-68002",
                "American Tourister APPLITE 4.0 QJ6-68002は外寸55×35×25/28cm"
                "（通常時は幅35×奥行25×高さ55cm）、約38/40L、約2.1kgの"
                "リサイクルポリエステル製ソフトケース（ソフトタイプ）と案内される。",
                ["SRC-AMERICAN-TOURISTER-APPLITE4-QJ6-68002"],
                dimensions=[
                    _dimensions("APPLITE 4.0 QJ6-68002（通常時）", 35, 25, 55),
                    _dimensions("APPLITE 4.0 QJ6-68002（拡張時）", 35, 28, 55),
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-LIGHT-ANA-RULE",
                "ANAは100席以上の国内線について、3辺の和115cm以内かつ幅40cm以内・"
                "奥行25cm以内・高さ55cm以内、"
                "身の回り品は2026年7月1日搭乗分より40×30×20cm以内、機内持ち込み手荷物1個と"
                "身の回り品1個の合計2個、総重量10kg以内と案内している。",
                ["SRC-ANA-DOMESTIC-CARRY-ON"],
                dimensions=[
                    _dimensions("ANA国内線100席以上機内持ち込み上限", 40, 25, 55),
                    _dimensions("ANA国内線身の回り品上限", 30, 20, 40),
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-LIGHT-JAL-RULE",
                "JALは100席以上の国内線について、付属品を含め幅40cm以内・奥行25cm以内・"
                "高さ55cm以内かつ3辺合計115cm以内、機内持ち込み品の合計重量10kg以内と案内している。",
                ["SRC-JAL-DOMESTIC-CARRY-ON"],
                dimensions=[
                    _dimensions("JAL国内線100席以上機内持ち込み上限", 40, 25, 55)
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-LIGHT-CONDITIONAL-CHOICES",
                "5候補はメーカー公表の通常時容量が35〜38L、本体重量が1.8〜2.2kgで、"
                "すべて編集上の選定範囲で30L以上・3kg以下に入る。通常時容量は"
                "APPLITE 4.0の38Lが5候補で最大である。公表本体重量はTri-Airが"
                "1.8kgで最軽量、AeroflexとAPPLITE 4.0、C-Liteが2.1kg、"
                "RIMOWAが2.2kgである。C-Liteは"
                "通常時36L・奥行20cmから拡張時42L・奥行23cmとなり、3辺合計も"
                "115cmから118cmへ変わる。通常容量、外装素材、ストッパー、"
                "拡張後の外寸を条件として選び分ける。",
                [
                    "SRC-PROTECA-AEROFLEX-DX2-01521",
                    "SRC-PROTECA-SUITCASE-WARRANTY",
                    "SRC-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
                    "SRC-RIMOWA-LIFETIME-GUARANTEE",
                    "SRC-RIMOWA-WARRANTY-FAQ",
                    "SRC-AMERICAN-TOURISTER-APPLITE4-QJ6-68002",
                    "SRC-SAMSONITE-C-LITE-SPINNER55EXP-MIDNIGHT",
                ],
                inference=True,
            ),
        ],
    ),
    _packet(
        "SPV-PORTFOLIO-FRONT-OPEN-SUITCASE-V1",
        "front-open-carry-on-suitcase-with-stopper",
        [
            *FRONT_PRODUCTS,
            "SRC-ANA-DOMESTIC-CARRY-ON",
            "SRC-JAL-DOMESTIC-CARRY-ON",
        ],
        [
            _claim(
                "CLM-PORTFOLIO-FRONT-INNOVATOR-INV50",
                "innovator INV50は外寸H55×W35×D25cm（幅35×奥行25×高さ55cm）、"
                "38L、3.3kgで、3room収納、フロントとミドル収納の間を開放する"
                "ワイドオープン、ワンタッチのブレーキ機能を備える。",
                ["SRC-INNOVATOR-INV50"],
                dimensions=[_dimensions("innovator INV50", 35, 25, 55)],
            ),
            _claim(
                "CLM-PORTFOLIO-FRONT-DIFFERENCE-05721",
                "ace. ディフェレンス 05721は通常時H55×W36×D24cm、32L、3.5kg、拡張時はD27cm、38Lで、前開きと中央開きの2通り、キャスターストッパーを備える。",
                ["SRC-ACE-DIFFERENCE-05721"],
                dimensions=[
                    _dimensions("ディフェレンス 05721（通常時）", 36, 24, 55),
                    _dimensions("ディフェレンス 05721（拡張時）", 36, 27, 55),
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-FRONT-FRESTER-01551",
                "PROTECA フレスターEX 01551は通常時H55×W37×D23cm、115cm、36L、拡張時はD27cm、119cm、45Lで、3.4kg、日本製、フロントオープンとキャスターストッパーを備える。",
                ["SRC-PROTECA-FRESTER-EX-01551"],
                dimensions=[
                    _dimensions("フレスターEX 01551（通常時）", 37, 23, 55),
                    _dimensions("フレスターEX 01551（拡張時）", 37, 27, 55),
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-FRONT-BERMAS-60570",
                "BERMAS INTER CITY III 60570は本体サイズW34×H47×D24cm、"
                "全体外寸W36×H54×D24cm（幅36×奥行24×高さ54cm）、約36L、"
                "約3.3kg（付属物を除く）で、13インチPC収納目安、前面から"
                "メイン収納へ届く2in1構造を備える。メーカーはキャスターを『ストッパー付き55mm静音キャスター』"
                "と表記するが、編集部は走行音を実測しておらず、静音性を選定根拠に使わない。",
                ["SRC-BERMAS-INTER-CITY-III-60570"],
                dimensions=[_dimensions("INTER CITY III 60570", 36, 24, 54)],
            ),
            _claim(
                "CLM-PORTFOLIO-FRONT-ANA-RULE",
                "ANAは100席以上の国内線について、3辺の和115cm以内かつ幅40cm以内・"
                "奥行25cm以内・高さ55cm以内、機内持ち込み手荷物1個と身の回り品1個の"
                "合計2個、総重量10kg以内と案内している。",
                ["SRC-ANA-DOMESTIC-CARRY-ON"],
                dimensions=[
                    _dimensions("ANA国内線100席以上機内持ち込み上限", 40, 25, 55)
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-FRONT-JAL-RULE",
                "JALは100席以上の国内線について、付属品を含め幅40cm以内・奥行25cm以内・"
                "高さ55cm以内かつ3辺合計115cm以内、合計重量10kg以内と案内している。",
                ["SRC-JAL-DOMESTIC-CARRY-ON"],
                dimensions=[
                    _dimensions("JAL国内線100席以上機内持ち込み上限", 40, 25, 55)
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-FRONT-C-LITE-KNOWN-SPECS-REFERENCE",
                "Samsonite C-Lite Spinner 55 EXPのブラック（134679-1041、SKU "
                "CS2*09007）は、通常時が幅40×奥行20×高さ55cm・36L、拡張時が"
                "奥行23cm・42L、重量2.1kgである。2026年8月31日の公式商品ページで"
                "「在庫あり」と「カートに入れる」を確認した。",
                ["SRC-SAMSONITE-C-LITE-SPINNER55EXP-BLACK"],
                dimensions=[
                    _dimensions(
                        "Samsonite C-Lite 134679-1041（通常時）", 40, 20, 55
                    ),
                    _dimensions(
                        "Samsonite C-Lite 134679-1041（拡張時）", 40, 23, 55
                    ),
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-FRONT-CONDITIONAL-CHOICES",
                "4モデルの通常容量はINV50が38L、05721が32L、01551が36L、60570が約36Lである。"
                "通常時から38L以上を必要条件にするとINV50が該当する。前開きの"
                "アクセス方式、拡張、PC収納、日本製、重量を条件として選び分け、"
                "ブレーキ／ストッパーの操作感や耐久性は順位付けしない。",
                FRONT_PRODUCTS,
                inference=True,
            ),
        ],
    ),
    _packet(
        "SPV-PORTFOLIO-ROOMBA-MINI-K11-V1",
        "roomba-mini-vs-switchbot-k11-pro",
        ROBOT_PRODUCTS,
        [
            _claim(
                "CLM-PORTFOLIO-ROBOT-K11-PRO",
                "SwitchBot K11+ Proは本体248×248×92mm、約2.3kg、ステーション"
                "240×180×250mmで、自動ゴミ収集、4L紙パック、最大12,000Paと"
                "案内される。水拭きは市販のお掃除シートを装着し、使用後に捨てる"
                "方式である。",
                ["SRC-SWITCHBOT-K11-PRO"],
                dimensions=[
                    _dimensions("SwitchBot K11+ Pro本体", 24.8, 24.8, 9.2),
                    _dimensions("SwitchBot K11+ Proステーション", 24, 18, 25),
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-ROBOT-K11-PRO-WARRANTY-UNRESOLVED",
                "SwitchBot公式の有料5年延長保証ページはK11+ Proを対象型番に含め、"
                "元のメーカー保証期間を『1年または2年』と案内するが、K11+ Proが"
                "どちらに当たるかは同ページだけでは確定できない。無償保証期間を"
                "推奨根拠に使わず、購入経路・対象条件・有料延長の要否を購入時に確認する。",
                ["SRC-SWITCHBOT-K11-PRO-EXTENDED-WARRANTY"],
                inference=True,
            ),
            _claim(
                "CLM-PORTFOLIO-ROBOT-ROOMBA-SLIM-F115060",
                "Roomba Mini Slim + SlimCharge F115060は本体が幅24.5×奥行24.5×"
                "高さ9.2cm、約2kg、縦置き充電スタンドが幅22.2×奥行8.6×高さ"
                "12.3cmで、2.4GHz／5GHz Wi-Fiに対応する。水拭きは専用の使い捨て"
                "お掃除シートと市販の床拭きシートに対応し、公式比較表では"
                "「充電スタンドでの自動ゴミ収集なし」と案内される。",
                ["SRC-IROBOT-ROOMBA-MINI-SLIM-F115060"],
                dimensions=[
                    _dimensions("Roomba Mini Slim本体 F115060", 24.5, 24.5, 9.2),
                    _dimensions("SlimCharge充電スタンド（縦置き時）", 22.2, 8.6, 12.3),
                ],
            ),
            _claim(
                "CLM-PORTFOLIO-ROBOT-K11-INSTALLATION-SPACE",
                "SwitchBot公式サポートはK11+ Proを含む対象機種の自動ゴミ収集ステーションについて、左右各1m、前方1.5mの空間を推奨し、不足すると本体の帰還に影響し得ると案内している。これはステーション筐体寸法とは別の設置条件である。",
                ["SRC-SWITCHBOT-AUTOEMPTY-INSTALLATION-SPACE"],
            ),
            _claim(
                "CLM-PORTFOLIO-ROBOT-CONDITIONAL-CHOICES",
                "Roomba Mini Slim F115060とK11+ Proの2製品では、前者は"
                "幅22.2×奥行8.6cmの小さい縦置き充電台、後者は小型本体と"
                "自動ゴミ収集を条件として分ける。K11+ Proは"
                "ステーション筐体とは別に左右各1m・前方1.5mの推奨空間を確保する。"
                "両製品とも使い捨てシート式の水拭きである。モップの自動洗浄・乾燥を"
                "条件にする場合は別記事の4モデル比較へ進む。K11+ Proの最大12,000Paは実機で測定していないため、"
                "吸引力の優劣を断定しない。",
                ROBOT_PRODUCTS,
                inference=True,
            ),
        ],
    ),
    _packet(
        "SPV-PORTFOLIO-SOLOTA-RAKUA-PLUS-V1",
        "solota-vs-rakua-mini-plus",
        DISH_PRODUCTS,
        [
            _claim(
                "CLM-PORTFOLIO-DISH-SOLOTA-NP-TMLK1-IDENTITY-REFERENCE",
                "PanasonicのNP-TMLK1公式ページは、SOLOTAのブラックモデルを"
                "NP-TMLK1-Kとして案内する。本記事ではこの正確な型番だけを対象にし、"
                "購入時も型番別の公式情報を確認する。",
                ["SRC-PANASONIC-NP-TMLK1"],
            ),
            _claim(
                "CLM-PORTFOLIO-DISH-RAKUA-MINI-PLUS-EXCLUDED",
                "THANKO ラクアmini Plus TK-MDW22Bの公式ストア確認時は再入荷通知のみが"
                "表示されていた。当サイトは購入リンクを掲載しないが、他の販売店の在庫や"
                "今後の入荷、商品自体の性能の優劣までは判断しない。",
                ["SRC-THANKO-RAKUA-MINI-PLUS"],
            ),
            _claim(
                "CLM-PORTFOLIO-DISH-LIFECYCLE-REFERENCE",
                "本記事はSOLOTA NP-TMLK1-Kとラクアmini Plus TK-MDW22Bの2機種の型番・販売表示と、"
                "購入前の確認項目を案内する。NP-TMLK1-Kの販売状態は未確認であり、"
                "販売終了や購入不可とは判断しない。購入先の案内がないことは商品の劣位を意味しない。"
                "性能の優劣や後継機・同等品は断定せず、設置条件の選び方は別記事へ案内する。"
                "購入前に型番、色、本体のみかセットか、新品か中古品か、販売元の在庫・納期・保証を"
                "確認し、自宅の幅・奥行・高さと取扱説明書の扉・給排水・電源・アース条件を"
                "照合する。設置条件を満たせない場合は購入を見送る選択もある。",
                DISH_PRODUCTS,
                inference=True,
            ),
        ],
    ),
)


# This overview page is retained only for model identity/reference and an
# explicitly UNKNOWN sales state. Its former specification-table locators no
# longer occur here. The image's exact black-model identity and the description
# must remain bound together; the model-family SKU is not stock evidence.
PANASONIC_NP_TMLK1_IDENTITY_FRAGMENTS: Final = (
    "<title>概要 食器洗い乾燥機 NP-TMLK1 | 食器洗い乾燥機（食洗機） | Panasonic</title>",
    '"sku":"NP-TMLK1"',
    "&#34;altText&#34;:&#34;NP-TMLK1-KserialNumber&#34;",
    '<meta name="description" content="パナソニックの「パーソナルタイプの'
    "食器洗い乾燥機（NP-TMLK1）SOLOTA」の商品サイトです。新登場のブラック色モデル。",
)


NEW_SOURCE_FRAGMENTS: Final[dict[str, tuple[str, ...]]] = {
    "SRC-EUFY-AUTOEMPTY-C10-T2292": (
        '<meta property="og:title" content="Eufy Robot Vacuum Auto-Empty C10 | ロボット掃除機の製品情報">',
        'data-variant-sku="T2292511"',
        '<div id="product-variant-stock" class="product-variant-stock">在庫わずか</div>',
        '<td class="product-specs-heading">\n                    ロボット掃除機<br>本体サイズ\n                  </td>\n                  <td>約32.5 x 32.3 x 7.2cm</td>',
        '<td class="product-specs-heading">\n                    ステーション<br>サイズ\n                  </td>\n                  <td>約27.5 x 19.1 x 21.2cm</td>',
        '<td>ロボット掃除機本体：約2.5kg<br>ステーション：約1.8kg</td>',
        '<th>水拭き</th>\n            <td>\n              \n                -\n              \n            </td>',
        '<th>自動ゴミ収集システム</th>\n            <td>\n              \n                ◯\n              \n            </td>',
        "<h2>吸引は強力、角まで綺麗に</h2>\n<p>最大4000Paの強力な吸引力",
        "ステーションは左右0.5m、前方1.5mの範囲内にある障害物を取り除き設置してください。",
        "Eufy Robot Vacuum Auto-Empty C10、自動ゴミ収集ステーション、ステーションカバー、ダスト容器、ダストバッグ、クイックスタートガイド、安全マニュアル、18ヶ月保証 + 6ヶ月 (Ankerで会員登録後) 、カスタマーサポート",
        '<td>T2292511 (ブラック)',
        "本製品は2.4GHz周波数帯のみに対応しています。5GHz周波数帯には対応していません。",
        '<a href="/products/t291c?variant=44872030814369" class="product-card-default-name-link">Eufy Robot Vacuum  交換用ダストバッグ (Auto-Empty C10対応 / Omni C20対応)</a>',
        '<a href="/products/t291d?variant=44872026587297" class="product-card-default-name-link">Eufy Robot Vacuum  交換用サイドブラシ (Auto-Empty C10対応)</a>',
        '<a href="/products/t290y?variant=44872030683297" class="product-card-default-name-link">Eufy Robot Vacuum  交換用フィルター (Auto-Empty C10対応 / Omni C20対応)</a>',
        '<a href="/products/t291f?variant=44872026226849" class="product-card-default-name-link">Eufy Robot Vacuum 交換用回転ブラシ (Auto-Empty C10対応)</a>',
        '<a href="/products/t29k2?variant=44922334806177" class="product-card-default-name-link">Eufy Robot Vacuum  交換用バッテリー (Auto-Empty C10対応)</a>',
    ),
    "SRC-PROTECA-TRI-AIR-01541": (
        '<h1 class="h1 block-goods-name--text js-enhanced-ecommerce-goods-name">PROTECA／プロテカ トライエアー スーツケース 日本製 軽量 1.8kg 35L 01541</h1>',
        "H55×W37×D23 cm",
        "<dd>115 cm</dd>",
        "<dd>35 L</dd>",
        "<dd>1.8kg</dd>",
        "<dd>MADE IN JAPAN</dd>",
        "＜10年間の製品保証＞",
        "＜最初の3年間は完全保証プレミアムケア＞",
        "在庫あります",
        '<input type="hidden" value=01541-10 name="goods">\r\n\t\t\t\t\t<div class="block-add-cart">\r\n<button class="block-add-cart--btn btn btn-primary js-enhanced-ecommerce-add-cart-detail " type="submit" value="カートに入れる">カートに入れる</button>',
    ),
    "SRC-ANKER-SOLIX-C800": (
        "<title>Anker Solix C800 Portable Power Station | リン酸鉄ポータブル電源の製品情報 | Anker Japan 公式オンラインストア</title>",
        'data-variant-sku="A17535Z1"',
        '<div id="product-variant-stock" class="product-variant-stock">在庫わずか</div>',
        'aria-label="カートに入れる"',
        "<h2>業界最高水準の高出力<sup>※</sup>\n</h2>\n<p>768Whの中容量帯ながら、1200Wを安定して出力できる",
        '<td class="product-specs-heading">サイズ</td>\n                  <td>約37.1 x 20.5 x 25.0cm （ 幅 x 奥行 x 高さ )</td>',
        '<td class="product-specs-heading">重さ</td>\n                <td>約10.5kg</td>',
        "<p><small>※電池容量が初期容量の80%まで劣化するまでのサイクル回数は3,000回以上",
        "※Anker Japan 公式オンラインストア会員を対象に、通常18ヶ月の製品保証を5年へ自動延長致します。",
        "<h3>購入後も安心のアフターサービス</h3>\n<p>専門スタッフのサポートや、ご使用済みポータブル電源の回収サービス",
    ),
    "SRC-JACKERY-1000-NEW-V3": (
        "Jackery ポータブル電源 1000 New V3",
        "ポータブル電源 1000 New V3 白（JE-1000G-WH）",
        "ポータブル電源 1000 New V3（JE-1000G）",
        "カートに追加する",
        "前モデル比19%小型化・約10.6kgの軽量ボディ",
        "約6000回の充放電サイクル",
    ),
    "SRC-JACKERY-1000-NEW-V3-LAUNCH": (
        "2026年7月24日（金）より、Jackery人気モデルの「1000 New」より進化した「Jackery ポータブル電源 1000 New V3」を発売いたします。",
        "AC定格出力1500W（瞬間最大3000W）・容量1024Wh",
        "重さ  | 10.6kg  | 10.8kg",
        "サイズ  | 314x201x234mm  | 327x224x247mm",
        "発売日：2026年7月24日（金）11時～",
    ),
    "SRC-DJI-POWER-1000-V2-STORE": (
        "DJI Power 1000 V2",
        '"ean":"6937224115101"',
        '"status":{"code":"on_sale","text":"今すぐ購入"}',
        "1024Wh",
        "最大2600Wの連続出力",
    ),
    "SRC-DJI-POWER-1000-V2-SPECS": (
        "DYM1000V2L/DYM1000V2H",
        "1024 Wh",
        "約14.2 kg",
        "448×225×230 mm（長さ×幅×高さ）",
        "4000サイクル以降は、80%以上の電池容量を維持",
    ),
    "SRC-JACKERY-500-NEW-MANUAL": (
        "JE-500A",
        "リン酸鉄リチウムイオン電池",
        "約311 x 205 x 157 mm",
        "約5.7 kg",
        "6,000回の充放電サイクル後も70%以上",
    ),
    "SRC-JACKERY-500-NEW-DIMENSION-AXES": (
        "サイズ（幅×奥行×高さ）",
        '<span lang="ja">500 New</span></td>\n'
        '<td style="height: 19.5982px; width: 71.0613%;">'
        '<span lang="ja">311×205×157mm</span>',
    ),
    "SRC-ANKER-SOLIX-C300-SAFETY-MANUAL": (
        "Product Number: A1722",
        "本製品を分解しないでください。",
        "本製品を一般ゴミとして廃棄しないでください。",
        "保管およびお手入れ方法",
        "3 ヶ月に一度を目安に定期的にバッテリー残量を確認し、100% まで充電した状態で保管してください。",
    ),
    "SRC-ANKER-SOLIX-C800-SAFETY-MANUAL": (
        "Product Number: A1753",
        "本製品を分解しないでください。",
        "本製品を一般ゴミとして廃棄しないでください。",
        "保管およびお手入れ方法",
        "3 ヶ月に一度を目安に定期的にバッテリー残量を確認し、100% まで充電した状態で保管してください。",
    ),
    "SRC-ANKER-SOLIX-C800-PLUS-SAFETY-MANUAL": (
        "Product Number: A1754",
        "本製品を分解しないでください。",
        "本製品を一般ゴミとして廃棄しないでください。",
        "保管およびお手入れ方法",
        "3 ヶ月に一度を目安に定期的にバッテリー残量を確認し、100% まで充電した状態で保管してください。",
    ),
    "SRC-ANKER-SOLIX-C1000-SAFETY-MANUAL": (
        "Product Number: A1761",
        "本製品を分解しないでください。",
        "本製品を一般ゴミとして廃棄しないでください。",
        "保管およびお手入れ方法",
        "3 ヶ月に一度を目安に定期的にバッテリー残量を確認し、100% まで充電した状態で保管してください。",
    ),
    "SRC-ANKER-SOLIX-C1000-GEN2-SAFETY-MANUAL": (
        "Product Number: A1763",
        "本製品を分解しないでください。",
        "本製品を一般ゴミとして廃棄しないでください。",
        "保管およびお手入れ方法",
        "3 ヶ月に一度を目安に定期的にバッテリー残量を確認し、100% まで充電した状態で保管してください。",
    ),
    "SRC-ANKER-SOLIX-JP-SUPPORT": (
        "Ankerは国内に修理センターを設けており、万が一製品に不具合が生じた際も、スムーズかつ迅速な対応が可能です。",
        "電話 / LINE / メール / チャットで<br>",
        "Ankerでは、ご使用済み、または故障・破損しているポータブル電源の回収を承っております。",
        "※ 対象製品：Anker のポータブル電源。送料はお客様ご負担となります",
    ),
    "SRC-JACKERY-JP-REPAIR-SERVICE": (
        "STEP1：ポータブル電源修理の申し込みをする",
        "受付窓口は、Jackery Japan カスタマーサポートです。",
    ),
    "SRC-JACKERY-JP-RECYCLING": (
        "日本国内で販売されたJackery ポータブル電源本体のみ",
        "無料、ただし送料はお客様のご負担となります。",
    ),
    "SRC-DJI-POWER-1000-V2-SAFETY-GUIDELINES-JA": (
        "モデル DYM1000V2L/DYM1000V2H",
        "火災、感電、または人身傷害といった危険を避けるため",
        "公式サポートまたは正規販売店に連絡して、指示を受けてください。",
        "規定の動作環境温度で使用してください。",
    ),
    "SRC-DJI-POWER-1000-V2-USER-MANUAL-JA": (
        "5.5 メンテナンス",
        "バッテリー残量を 60%まで放電することをお勧めします。",
        "パワーステーションを6 ヶ月に 1 回充電および放電します。",
        "きれいな乾いた布で拭いてください。",
        "通常の廃棄コンテナにパワーステーションを入れて、廃棄しないでください。",
        "DJI は廃棄時の回収も行っております",
    ),
    "SRC-DJI-JP-AFTERSALES-POLICY": (
        "<strong>DJI Power 1000 Mini / DJI Power 1000 V2 / DJI Power 2000 / DJI Power 1000 / DJI Power 500</strong>",
        "<td>DJI Power 1000 Mini / DJI Power 1000 V2 / DJI Power 2000 / DJI Power 1000 / DJI Power 500</td><td>60ヶ月</td>",
        "修理を希望される場合、オンライン修理受付サービス （https://repair.dji.com）から申請する事ができます。",
        "修理後に製品のメーカー保証期間はリセットされません。",
    ),
    "SRC-METI-PORTABLE-POWER-SAFETY": (
        "ポータブル電源の安全性要求事項",
        "電気用品安全法の規制対象外",
        "火災や感電等の電気的なリスク",
    ),
    "SRC-METI-ELECTRICAL-RECALLS": (
        "家庭用電気製品のリコール情報",
        "ポータブル電源",
    ),
    "SRC-TOSHIBA-DWS-33B": (
        '<h1><div class="text">DWS-33B</div></h1>',
        "<tr><th>外形寸法</th><td>420(幅)×435(奥行)×465(高さ)mm</td></tr>",
        "約13kg",
        "<tr><th>標準収納容量</th><td>18点(大皿3点、中鉢3点、小皿3点、茶わん3点、汁わん3点、コップ3点)<br>+小物(はし、スプーン、フォーク)</td></tr>",
        "<tr><th>使用水量</th><td>約6L</td></tr>",
        "<tr><th>乾燥方式</th><td>ヒーターとファンによる強制排気乾燥</td></tr>",
        "<tr><th>運転音<sup>※8</sup>(50Hz/60Hz)</th><td>約41dB/約43dB</td></tr>",
    ),
    "SRC-TOSHIBA-DWS-33B-STORE": (
        "DWS-33B(W)",
        "2025年07月15日",
        "買い物かごに入れる",
    ),
    "SRC-TOSHIBA-PARTS-RETENTION": (
        "食器洗い乾燥機",
        '<tr><th class="th-2"><big><b>食器洗い乾燥機</b></big></th><th class="th-2"><big><b>６年</b></big></th></tr>',
        "製造打ち切り後",
    ),
    "SRC-PANASONIC-NP-TSP2-LAUNCH": (
        "NP-TSP2",
        "2026年9月",
        "発売予定",
    ),
    "SRC-PANASONIC-NP-TSP2-SUBSCRIPTION": (
        "NP-TSP2",
        "予約受付中",
        "9月中旬以降",
    ),
    "SRC-PANASONIC-NP-TMLK1-SUPPORT": (
        "NP-TMLK1 サポート",
        "取扱説明書[NP-TML1_NP-TMLK1]",
        "修理サービス",
        "部品の保有期間から",
    ),
    "SRC-PANASONIC-NP-TML1-MANUAL": (
        "保証期間：お買い上げ日から本体1年間",
        "一般家庭用以外に使用された場合は除く",
        "補修用性能部品の保有期間 6年",
        "製造打ち切り後6年保有",
    ),
    "SRC-PANASONIC-DISH-PARTS-RETENTION": (
        "補修用性能部品の保有期間",
        "保有期間の始期はその製品の製造を打ち切ったとき",
        "食器洗い乾燥機（食洗機）",
        "6年",
    ),
    "SRC-PROTECA-SUITCASE-WARRANTY": (
        # The current page also lists J5's 10-year premium care and the bags'
        # five-year normal warranty. Bind the general suitcase period and
        # manufacturing coverage to its heading, not those repeated labels.
        '<h3>プロテカ スーツケース製品</h3>\r\n'
        '          <p class="card-subtitle">（ハードタイプ・ソフトタイプ）</p>\r\n'
        '        </div>\r\n'
        '        <div class="warranty-section">\r\n'
        '          <div class="warranty-item">\r\n'
        '            <div class="warranty-label">通常製品保証</div>\r\n'
        '            <div class="period-value">10年</div>\r\n'
        '            <div class="period-desc">\r\n'
        '              素材及び製造上の不具合が認められた場合、無償修理\r\n'
        '            </div>',
        # Keep the three-year transport coverage and its exclusions together;
        # the transport sentence alone also appears under the J5 guarantee.
        '<span class="premium-care-period">購入後 3年間】</span><br />'
        '航空会社による破損、またはその他の運送中に生じた損傷も無償修理<br>'
        '※セール品やアウトレット品、並行輸入品は対象外',
    ),
    "SRC-RIMOWA-ESSENTIAL-LITE-CABIN-82353171": (
        "82353171",
        "在庫あり",
        "カートに追加",
        "高さ55 x 幅37 x 奥行23 cm",
        "重量 2.2 kg",
        "容量 37 L",
    ),
    "SRC-RIMOWA-LIFETIME-GUARANTEE": (
        "2022年7月25日以降",
        "新品のスーツケース",
        "永久保証",
        "機能面の不具合",
    ),
    "SRC-RIMOWA-WARRANTY-FAQ": (
        "外観上の経年劣化",
        "不適切な使用、誤用または乱用",
        "保証の対象外",
    ),
    "SRC-ECOVACS-DEEBOT-MINI2": (
        "DEEBOT mini 2",
        "本体：286mm*286mm*99.8mm ステーション：320mm*400mm*385mm",
        "自動ゴミ収集、モップ自動洗浄、63℃熱風乾燥",
        "6mmの自動リフトモップ",
        "ビデオマネージャー（ペット見守り機能）",
        "外出先からでも様子を見守り、声をかけ",
        "スクリーンショット機能",
        "DEEBOT mini2用アクセサリキット",
        'aria-label="add to cart"',
        "カートに追加",
        "今すぐ購入",
    ),
    "SRC-ECOVACS-WARRANTY": (
        "全商品1年間保証",
        "2026年2月20日以降",
        "ECOVACS HOMEアプリにてご登録",
        "製品の保証期間は2年",
        "正規取扱店舗",
    ),
    "SRC-SWITCHBOT-K11-PRO-EXTENDED-WARRANTY": (
        "SwitchBot公式有料5年延長保証サービス",
        "製品のメーカー保証期間（1年または2年）の終了後も",
        "保証期間は、購入日から最長5年間となります",
        "ロボット掃除機K11+ Pro",
    ),
    "SRC-SIROCA-SS-M171-MANUAL": (
        "保証期間  お買い上げ日より1年間",
        "SS-M171",
    ),
    "SRC-IRISOHYAMA-ISHT-5000-W": (
        "ISHT-5000-W",
        "生産終了",
        "幅420×奥行445×高さ435mm",
        "標準収納容量 15点",
        "約5L",
        "お買い上げ日より1年間",
    ),
    "SRC-ANA-DOMESTIC-CARRY-ON": (
        "「機内持ち込み手荷物」1個と「身の回り品」1個の合計2個、重さは合計10kgまで",
        "3辺（縦・横・高さ）の和が115cm以内かつ3辺それぞれの長さが（55cm × 40cm × 25cm以内）",
        "3辺（縦・横・高さ）の和が100cm以内かつ3辺それぞれの長さが（45cm × 35cm × 20cm以内）",
        "<div>40cm × 30cm × 20cm以内</div>",
        "（機内持ち込み手荷物と身の回り品の総重量）",
    ),
    "SRC-PROTECA-STARIA-CXR-02350": (
        "H45×W34×D20 cm",
        "<dd>99 cm</dd>",
        "<dd>22 L</dd>",
        "<dd>2.4kg</dd>",
        "MAGIC STOP(キャスターストッパー)",
    ),
    "SRC-PROTECA-FRESTER-EX-01550": (
        "H45×W34×D20/24 cm",
        "<dd>99/103 cm</dd>",
        "<dd>26/33 L</dd>",
        "<dd>2.8kg</dd>",
        "国内100席未満・機内持込み対応／／フロントオープン／エキスバンダブル／4輪／TSダイヤルファスナーロック／キャスターストッパー",
    ),
    "SRC-ACE-PALISADES3-Z-06910": (
        "H45×W34×D20 cm",
        "<dd>99 cm</dd>",
        "<dd>21 L</dd>",
        "<dd>2.6kg</dd>",
        "TSAダイヤルファスナーロック／キャスターストッパー／小型コインロッカーサイズ／国内100席未満機内持込み",
    ),
    "SRC-BERMAS-INTER-CITY-60524": (
        '<div class="fs-p-productDescription fs-p-productDescription--full"><div class="detail-cont">\r\n<div class="tit">DETAILS</div>\r\n<table width="100%" border="0" cellspacing="0" cellpadding="0">\r\n<tbody>\r\n<tr>\r\n<th scope="row">サイズ</th>\r\n<td> \r\nW33×H38×D20cm(本体サイズ)<br>\r\nW34×H45×D20cm(全体サイズ)</td>\r\n</tr>\r\n<tr>\r\n<th scope="row">素材</th>\r\n<td>PC+</td>\r\n</tr>\r\n<tr>\r\n<th scope="row">容量/重量</th>\r\n<td>約22L / 約2.8kg（付属物含まず）</tr>\r\n</tbody>\r\n</table>',
        '<meta name="description" content="BERMAS INTER CITY No.60524は、1～2泊の出張や旅行に適した22L容量のコンパクトスーツケース。コインロッカー収納対応の38cmサイズで、13インチPC収納対応のフロントオープン設計やストッパー付き静音キャスターを備えたビジネスキャリーです。">',
        '特徴<span class="detail-data01">：100席未満航空機＆LCC機内持込対応・TSロック装備（ダイヤルロック式）・HINOMOTO製ストッパー付き静音キャスター(SILENT RUN)・伸縮ハンドル2段階調節・トラベルセントリーID付属</span>',
        "<b>[新仕様の変更点]　<br>\r\n・USBポートの廃止<br>\r\n・上記USBポート廃止に伴う内装仕様の変更",
    ),
    "SRC-JAL-DOMESTIC-CARRY-ON": (
        "身の回り品1個＋お手荷物1個の合計2個まで",
        "合計重量　10kg以内まで",
        "ハンドルやキャスター、車輪などもサイズに含みます。",
        "合計：115cm以内",
        "55cm×40cm×25cm以内",
        "合計：100cm以内",
        "45cm×35cm×20cm以内",
    ),
    "SRC-PROTECA-AEROFLEX-DX2-01521": (
        "H55×W36×D23 cm",
        "<dd>114 cm</dd>",
        "<dd>35 L</dd>",
        "<dd>2.1kg</dd>",
        "<dd>MADE IN JAPAN</dd>",
        "キャスターストッパー／国内100席以上・国際機内持込み",
    ),
    "SRC-SAMSONITE-C-LITE-CS2-09007": (
        "<h3>CS2*09007</h3>",
        '<span>Size</span></section><section class="product-params-row__value"><span>55*40*20 / S</span>',
        '<span>Material</span></section><section class="product-params-row__value"><span>Curv</span>',
        '<span>Volume</span></section><section class="product-params-row__value"><span>36(42) L</span>',
        '<span>Weight</span></section><section class="product-params-row__value"><span>2,1 kg</span>',
    ),
    "SRC-SAMSONITE-CATALOG-2025": (
        "A154 C-LITE",
        "134679\nSpinner 55 EXP\n40 x 55 x 20/23\n36/42 l\n2.1 kg",
    ),
    "SRC-AMERICAN-TOURISTER-APPLITE4-QJ6-68002": (
        '<span class="value">QJ6-68002</span>',
        'サイズ（外寸）: <span class="product-dimension-value">55 x 35 x 25/28</span>cm',
        '容量: 約 <span class="product-volume-value">38 /40</span>L',
        '重量: 約 <span class="product-weight-value"> 2.1</span>kg',
        '素材: <span class="product-material-value">リサイクルポリエステル</span>',
        "ソフトケース「APPLITE 4.0（アップライト 4.0）」",
    ),
    "SRC-FREQUENTER-LIEVE-1-250": (
        '<tr><td class="cent">サイズ</td><td> 横33cm×縦48cm×奥行23cm</td></tr>',
        '<tr><td class="cent">総外周</td><td> 横35cm×縦55cm×奥行23m=113cm<br>国内線（100席以上）機内持込みサイズ</td></tr>',
        '<tr><td class="cent">重量</td><td> 約2.7kg</td></tr>',
        '<tr><td class="cent">容量</td><td> 約33L</td></tr>',
        "簡単に静粛タイヤを自分で交換可能！交換用静音タイヤキット【1-623】",
    ),
    "SRC-INNOVATOR-INV50": (
        '"title":"INV50 Pale Blue 38L Cabin"',
        "サイズ : H55 x W35 x D25 cm",
        "容　量 : 38 L",
        "重　量 : 3.3 kg",
        "3room収納",
        "フロントとミドルスペースの間のファスナーをあけるとワイドオープンし",
        "ワンタッチでブレーキのオン・オフが可能です。",
    ),
    "SRC-PROTECA-FRESTER-EX-01551": (
        "H55×W37×D23/27 cm",
        "<dd>115/119 cm</dd>",
        "<dd>36/45 L</dd>",
        "<dd>3.4kg</dd>",
        "<dd>MADE IN JAPAN</dd>",
        "国内100席以上・機内持込み対応／フロントオープン／エキスバンダブル／4輪／TSダイヤルファスナーロック／キャスターストッパー",
    ),
    "SRC-BERMAS-INTER-CITY-III-60570": (
        "W34×H47×D24cm(本体サイズ)",
        "W36×H54×D24cm(全体サイズ)",
        "約36L / 約3.3kg（付属物含まず）",
        "フロントポケット＋メインルーム直結",
        "～13インチPC対応可能",
        "HINOMOTO製ストッパー付き55mm静音キャスター",
    ),
    "SRC-BERMAS-INTER-CITY-II-60561": (
        '<div class="fs-p-productDescription fs-p-productDescription--full"><div class="detail-cont">\r\n<div class="tit">DETAILS</div>\r\n<table width="100%" border="0" cellspacing="0" cellpadding="0">\r\n<tbody>\r\n<tr>\r\n<th scope="row">サイズ</th>\r\n<td> \r\nW33×H47×D25cm(本体サイズ)<br>\r\nW35×H55×D25cm(全体サイズ)</td>\r\n</tr>\r\n<tr>\r\n<th scope="row">素材</th>\r\n<td>ポリカーボネート</td>\r\n</tr>\r\n<tr>\r\n<th scope="row">容量/重量</th>\r\n<td>約36L / 約3.5kg（付属物含まず）</tr>\r\n</tbody>\r\n</table>',
        "モバイル機器クッションポケット：～13インチPC対応可能",
        "USBポート(Type-A 1口・Type-C 1口付き)・HINOMOTO製ストッパー付き60mm大径静音キャスター",
    ),
    "SRC-IROBOT-ROOMBA-MINI-SLIM-F115060": (
        '<meta property="og:url" content="https://store.irobot-jp.com/item/F115060.html"',
        "Wi-Fi 2.4GHz帯 / 5GHz帯",
        "24.5（奥行き）×24.5（幅）×9.2（高さ）",
        "（縦置き時）8.6（奥行き）×22.2（幅）×12.3（高さ）",
        "ロボット本体：約2kg",
        "専用使い捨てお掃除シート",
        "市販の床拭きシートも使用可能",
        "充電スタンドでの自動ゴミ収集なし",
    ),
    "SRC-SWITCHBOT-AUTOEMPTY-INSTALLATION-SPACE": (
        "Related Products: SwitchBot Mini Robot Vacuum K10+/K10+ Pro/K11+/K11+ Pro",
        "We recommend a distance of 1 meter for left and right and 1.5 meters in front (no limit on top).",
        "Insufficient space may affect the vacuum body to return to the charging station.",
    ),
    "SRC-PANASONIC-NP-TMLK1": PANASONIC_NP_TMLK1_IDENTITY_FRAGMENTS,
    "SRC-PANASONIC-NP-TML1": (
        "容量&#xff08;食器点数&#xff09;<sup>★1</sup>",
        '<td colspan="1" rowspan="1">6点',
        "○&#xff08;送風乾燥&#xff09;",
        "約2.5L&#xff08;着脱タンク式&#xff09;",
        "約 幅310×高さ435×奥行225&#xff1c;485&#xff1e;mm",
        '<td colspan="1" rowspan="1">約7.5㎏',
    ),
    "SRC-PANASONIC-SOLOTA-IDENTITY": (
        "<title>食器洗い乾燥機 パーソナルタイプ（SOLOTA） | 食器洗い乾燥機（食洗機） | Panasonic</title>",
        "<strong>NP-TML1</strong><br />-W&#xff08;ホワイト&#xff09;",
    ),
    "SRC-THANKO-RAKUA-MINI-TK-MDW22W": (
        '<div class="item-code">JAN：4580060593095</div>',
        '<a href="#makeshop-item-sku-cart-entry-url:1-1-0" class="btn sku-cart1 add_to_cart">カートに入れる</a>',
        "<tr>\n<th>サイズ</th>\n<td>幅 308× 高さ 415× 奥行 315(mm) 開扉時奥行：594mm</td>\n</tr>",
        "<tr>\n<th>重量</th>\n<td>約 8kg</td>\n</tr>",
        "<tr>\n<th>定格消費電力</th>\n<td>900W</td>\n</tr>",
        "<tr>\n<th>使用水量</th>\n<td>3.2L</td>\n</tr>",
        "<tr>\n<th>洗浄方式</th>\n<td>下ノズル噴射式</td>\n</tr>",
        "<tr>\n<th>すすぎ方式</th>\n<td>ためすすぎ</td>\n</tr>",
        "<tr>\n<th>乾燥方式</th>\n<td>熱風乾燥</td>\n</tr>",
        "<tr>\n<th>標準収納容量</th>\n<td>11～12 点（大皿…2 点　中皿またはコップ…2 点　小皿…2～3 点　小鉢…3 点　茶わん…2 点　小物類（はし、スプーン、フォーク、レンゲなど））</td>\n</tr>",
        "単体:TK-MDW22W <br>",
        "<tr>\n<th>保証期間</th>\n<td>購入日より12ヶ月</td>\n</tr>",
    ),
    "SRC-THANKO-RAKUA-MINI-COLOR": (
        '<h1 class="item-name">タンク式食洗機「ラクアmini color」</h1>',
        '<a href="#makeshop-item-sku-restock-url:1-0" class="btn btn-cart3 test3">再入荷(予約開始)通知</a>',
        '<a href="#makeshop-item-sku-restock-url:2-0" class="btn btn-cart3 test3">再入荷(予約開始)通知</a>',
        "【ミスティーブルー】 TDWS25SBL/4580060603756<br>",
        "【クラシックローズ】 TDWS25SRD/4580060603749<br>",
    ),
    "SRC-THANKO-RAKUA-MINI-PLUS": (
        '<a href="#makeshop-item-restock-url" class="btn btn-cart3 test1">再入荷(予約開始)通知</a>',
        'data-original="//data.thanko.jp/product/img-product/tk-mdw22b-top.jpg"',
    ),
    "SRC-SIROCA-SS-M171": (
        '<p class="title title_detail">SS-M171</p>',
        '<span class="top">分岐水栓にも対応の2WAYだから、キッチンの環境に合わせて使える</span>',
        "家族3人分の食器16点<sup>*4</sup>が一度に",
        "標準、念入り、おいそぎ、ソフト、選べる4つの洗浄コース",
        '<th>給水方式</th>\n<td colspan="2">タンク式（手動給水）/分岐水栓式</td>',
        '<th>使用水量(約)</th>\n<td colspan="2">5L</td>',
        '<th>標準収納容量(約)</th>\n<td colspan="2">16点',
        '<th>対応可能な<br />\n大皿サイズ(約)</th>\n<td colspan="2">直径23cmまで</td>',
        '<th>洗浄方式</th>\n<td colspan="2">回転ノズル噴射式</td>',
        '<th>すすぎ方式</th>\n<td colspan="2">ためすすぎ</td>',
        '<th>乾燥方式</th>\n<td colspan="2">送風乾燥</td>',
        '<th>本体重量(約)</th>\n<td colspan="2">13kg',
        '<th>外形寸法(約)</th>\n<td colspan="2">幅42×奥行43.5×高さ43.5cm</td>',
        '<th>消費電力</th>\n<td colspan="2">512W／526W</td>',
    ),
    "SRC-SIROCA-SS-M171-STORE": (
        "SS-M171",
        "メタリックウォームグレー",
        "出荷予定日 9/1",
        "購入する",
    ),
    "SRC-SIROCA-SS-MA251-STORE": (
        "オートオープンタイプ／シルバー（SS-MA251）",
        "出荷予定日 9/1",
        "購入する",
    ),
    "SRC-SIROCA-DISHWASHER-INSTALLATION": (
        "SS-MA251/SS-MU251</span></strong></span>　（約）A: 横38.8 cm　B: 縦35.0 cm／a: 幅 42 cm　b: 奥行 44 cm　c: 高さ 47 cm　d: ドアを開いたときの奥行き 76.0 cm",
        'SS-MA251/SS-MU251/PDW-M151/SS-M171/SS-M151/PDW-5D</span></strong></span></div><div class="line">上面：70 cm以上</div><div class="line">側面：5 cm以上</div><div class="line">背面：6 cm以上</div>',
    ),
    "SRC-ELECOM-NESTOUT-700N": (
        "NESTOUT ポータブル電源 700N(容量712Wh/AC出力700W)",
        "DE-NEPS700NBE",
        "発売中",
        "712.25Wh",
        "約6.2kg",
        "搭載のリチウムイオン電池は充電式で、約500回繰り返し使用可能。",
    ),
    "SRC-BLUETTI-DISCONTINUED-MODELS": (
        "生産終了製品一覧",
        'alt="BLUETTI AORA 80"',
        "BLUETTI AORA 80",
        "2026年4月20日に販売終了",
        "<span>終売</span>",
    ),
    "SRC-ANKER-SOLIX-C1000-PLUS": (
        "Anker Solix C1000 Plus Portable Power Station",
        "定格は家庭用コンセントを上回る1700Wの高出力を実現",
        "SurgePad™により消費電力2000Wまでの家電に複数同時給電に対応",
        "約38.4 x 20.8 x 24.4cm",
        "約11.3kg",
        "1024Wh",
    ),
    "SRC-AQUA-ADW-M28B": (
        "ADW-M28B",
        "（標準収納容量：28点）",
        '<p class="ProductDetail_Section_Spec_Item_Body">幅370×奥行510×高さ452㎜</p>',
        '<p class="ProductDetail_Section_Spec_Item_Body">約4.5L(タンク式) /約6.0L(分岐水栓)</p>',
    ),
    "SRC-PANASONIC-RULO-MINI-MC-RSC10": (
        "MC-RSC10",
        "幅249mm×奥行249mm×高さ92mm",
        "幅134mm×奥行100mm×高さ99mm",
        "繰り返し充放電 約1100回",
    ),
    "SRC-EUFY-E20-T2070": (
        '"sku":"T2070511"',
        '"title":"ブラック"',
        'soldOut: "Sold Out"',
        "在庫切れ",
    ),
    "SRC-ROBOROCK-SAROS-10": (
        "Roborock Saros 10",
        "本体サイズ：350 × 353 × 79.8 mm",
        "ドックサイズ：409 × 440 × 470 mm",
        "8way全自動ドック搭載。",
    ),
    "SRC-EUFY-OMNI-E25-T2353": (
        "Eufy Robot Vacuum Omni E25",
        "約32.7 x 34.6 x 11.1cm",
        "約37.0 x 46.2 x 43.7cm",
        "水拭きしながらモップ洗浄するHydroJet システムを搭載で常にモップを清潔に保ちます。",
        "全自動クリーニングステーションで、ゴミ収集、モップ洗浄、温風乾燥、洗剤の自動投入まで全て自動で完結。",
    ),
    "SRC-DREAME-X50-ULTRA": (
        "Dreame X50 Ultra",
        "350 × 350 × 89mm",
        "センサー部を格納すると本体高さはわずか89mm",
        "457 × 340 × 590mm",
        "【敷居・レールも静かに走破。最大6cm段差対応の耐久設計】",
        "【6way全自動PowerDock＋汚れ検知。お手入れまでほぼ全自動】",
    ),
    "SRC-ECOVACS-DEEBOT-X8-PRO": (
        "DEEBOT X8 PRO OMNI",
        "サイズ（WxDxH) 本体：353*351.5*98 ステーション：350*477*533",
        "インテリジェントモップ洗浄温度制御で、ローラーモップを完璧に洗浄",
        "最大63℃の熱風乾燥システムで、モップを乾燥し、清潔に保ちます",
    ),
    "SRC-RIMOWA-CABIN-U-82350181": (
        "82350181",
        "高さ 50 x 幅 35 x 奥行 20 cm",
        "重量 2 kg",
        "容量 28 L",
    ),
    "SRC-SAMSONITE-AUDRINA-SPINNER45": (
        "オードリナ スピナー45",
        '<span class="product-dimension-value">47.5 x 37.5 x 24.0</span>',
        '<span class="product-volume-value">25.5</span>',
        '<span class="product-weight-value"> 2.29</span>',
        "UB8*09001",
    ),
    "SRC-MUJI-HARD-CARRY-20L": (
        "バーを自由に調節できる　ハードキャリーケース　（２０Ｌ）",
        "黒・タテ４７×ヨコ３２×マチ２０．５ｃｍ",
        "商品番号23184182",
        "ストッパー機能付きのキャリーケースです。",
    ),
    "SRC-SAMSONITE-C-LITE-SPINNER55EXP-MIDNIGHT": (
        "シーライト スピナー55 エキスパンダブル",
        "カートに入れる",
        "※電子機器部分の保証期間は購入後1年です。",
        "CS2*31007",
        '<span class="product-dimension-value">55 x 40 x 20/23</span>',
        '<span class="product-volume-value">36 /42</span>',
        '<span class="product-weight-value"> 2.1</span>',
        "条件付き10年",
    ),
    "SRC-MUJI-HARD-CARRY-36L-SECTION": (
        "バーを自由に調節できる　ハードキャリーケース（３６Ｌ）",
        "36L",
        "2.9kg",
        "キャスターストッパー",
    ),
    "SRC-MUJI-FRONT-OPEN-32L": (
        "バーを自由に調節できる　フロントオープンキャリーケース（３２Ｌ）",
        "黒・タテ５４×ヨコ３７×マチ２４ｃｍ",
        "商品番号84950087",
        "フロントオープンポケットを搭載しました。",
        "ストラップはアタッチメント仕様になっているためフルオーブンも可能です。",
        "キャリーバーの高さ1cmきざみでお好みの高さに調整できます。",
        "走行音が静かな双輪キャスターを採用",
    ),
    "SRC-SAMSONITE-C-LITE-SPINNER55EXP-BLACK": (
        "シーライト スピナー55 エキスパンダブル",
        "在庫あり",
        "カートに入れる",
        "CS2*09007",
        '<span class="product-dimension-value">55 x 40 x 20/23</span>',
        '<span class="product-volume-value">36 /42</span>',
        '<span class="product-weight-value"> 2.1</span>',
    ),
    "SRC-SWITCHBOT-K11-WIFI-FUNCTIONS": (
        "even without connecting to a Wi-Fi network",
        "connecting to Wi-Fi using SwitchBot App enables more convenient features like Schedule and Map",
        "Please make sure to connect to a 2.4GHz Wi-Fi network",
    ),
    "SRC-SWITCHBOT-K11-SETUP": (
        "SwitchBot App Version: 8.2 or newer",
        "Launch the SwitchBot App and login",
        "Enter your home Wi-Fi SSID and password",
        "2.4GHz Wi-Fi tethering",
    ),
    "SRC-ECOFLOW-RIVER3-PLUS": (
        "<h5>286Whの容量と600Wの定格出力を備えたRIVER 3 Plusは、3Wの"
        "Wi-Fiルーターを最大35時間稼働させることができます。さらに、600Wの"
        "パソコンをはじめ、ほとんどのオフィス機器も動作可能で、少なくとも"
        "21分間の動作が確保できるため、安全に作業を完了しシャットダウンできます。"
        "</h5>",
        "約4.7kg",
        'class="swatch-element  swatch_販売終了-river-3-plus-290 soldout "',
        '<span class="swatch-title">【販売終了】RIVER 3 Plus (290)</span>',
    ),
    "SRC-ECOFLOW-DELTA3-PLUS": (
        '<div class="pdp-grid-section__product-title">DELTA 3 Plus</div>',
        '<div class="pdp-grid-section__product-content"><p>容量<br/>1024Wh</p>'
        "<p>容量拡張<br/>最大5kWh<br/><br/>定格出力<br/>1500W "
        "(サージ3000W)<br/></p><p>X-Boost<br/>2000W<br/><br/>AC充電時間"
        "<br/>最短56分</p><p>ソーラー入力<br/>1000W（500W x2）<br/><br/>"
        "バッテリー寿命<br/>4000回以上<br/><br/>UPS機能<br/>&lt;10ms"
        "(サージ保護/NAS)<br/><br/><br/>重量(kg)<br/>約12.5<br/><br/>"
        "サイズ<br/>39.8x20.2x28.4cm<br/><br/>騷音&lt;30dB<br/>"
        "600W出力以下で30ds<br/><br/></p></div>",
        '<span>売り切れ</span>',
        'class="swatch-element  swatch_delta-3-plus-防災に最適 available "',
        '<span class="swatch-title">DELTA 3 Plus | 防災に最適</span>',
    ),
    "SRC-BLUETTI-AORA30-V2": (
        "<title>\n      AORA 30 V2 | グレー\n      \n      \n      ブルーティ "
        "\n    </title>",
        '"available":true',
    ),
    "SRC-BLUETTI-AORA30-V2-DIMENSIONS": (
        "BLUETTI AORA 30 V2：重量4.3kg、サイズ250×178×167.5mm。",
        "AORA 30 V2：3,000回以上の充放電に対応。8～10年の長寿命を実現。保証期間も5年",
        "容量  | 288Wh",
        "定格出力  | 600W",
    ),
    "SRC-BLUETTI-AORA100-V2": (
        "<title>\n      AORA 100 V2 | インディゴ\n      \n      \n      "
        "ブルーティ \n    </title>",
        '"available":true',
    ),
    "SRC-BLUETTI-AORA-SERIES-COLLECTION": (
        "<span>AORA 30 V2: 288Wh容量、600W出力（リフト1500W）、重量約4.3kg。キャンプや旅行、バックアップに最適。</span>",
        "<span>AORA 100 V2: 1024Wh容量、1800W出力（サージ3600W、リフト2700W）、重量約11.5kg、サイズ320x215x250mm。停電時、キャンプ、RV、CPAP機器などに。</span>",
        '"bluetti-aora-30-v2-288wh-600w" : {',
        '"bluetti-aora-100-v2-portable-power-station-blue" : {',
        "AORA 30 V2: 288Wh、600W、9ポート。",
        "AORA 100 V2 / 100: 1,024Wh/1,152Wh、1,800W、11ポート。",
        "4,000回以上（AORA 100 V2）、3,500回以上（AORA 100）、3,000回以上（AORA 30 V2 / AORA 80）。",
        "5年間保証で長期安心。",
        "国内アフターサポートとリサイクルプログラム。",
        "BLUETTIアプリでリモート操作、バッテリー低下通知（5～20%）、充電カスタマイズ。",
    ),
}

REUSED_FRAGMENT_SOURCE_CLAIMS: Final = {
    "SRC-ACE-DIFFERENCE-05721": "CLM-ST1704-SUITCASE-DIFFERENCE-SPECS",
    "SRC-SWITCHBOT-K11-PRO": "CLM-ST1704-ROBOT-K11-PRO-SPECS",
    "SRC-SIROCA-SS-MA251": "CLM-ST1704-DISH-SS-MA251-SPECS",
}

# Reviewed primary purchase block; the page also repeats its button in a footer.
ANKER_STOCK_BOUND_PURCHASE_FRAGMENT: Final = "<div id=\"product-variant-stock\" class=\"product-variant-stock\">在庫わずか</div>\n      \n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n<div class=\"product-form__controls-group product-form__controls-group--submit\">\n  <div\n    class=\"\n      product-form__item product-form__item--submit\"\n  >\n    \n      <button\n        type=\"submit\"\n        name=\"add\"\n        \n        aria-label=\"カートに入れる\"\n        id=\"cafe-purchase-button\"\n        class=\"btn product-form__cart-submit\"\n        \n        \n          aria-haspopup=\"dialog\"\n        \n        data-add-to-cart\n        \n        \n        \n      >"

LATER_CLAIM_FRAGMENT_ADDITIONS: Final[dict[tuple[str, str], tuple[str, ...]]] = {
    **{
        ("SRC-ANKER-SOLIX-C300", claim_id): (
            '<td class="product-specs-heading">サイズ</td>\n                  <td>約16.4 x 16.1 x 24.0cm （ 幅 x 奥行 x 高さ )</td>',
            '<td class="product-specs-heading">重さ</td>\n                <td>約4.1kg</td>',
            '<td class="product-specs-heading">出力</td>\n                <td>定格300W / 瞬間最大600W</td>',
            '<td class="product-specs-heading">バッテリー容量</td>\n                <td>288Wh</td>',
            '<meta property="og:title" content="Anker Solix C300 Portable Power Station | ポータブル電源の製品情報">',
            '<div id="product-variant-stock" class="product-variant-stock">在庫わずか</div>',
            ANKER_STOCK_BOUND_PURCHASE_FRAGMENT,
            '<td>A17225Z1 (ダークグレー) / A1722511 (ブラック)',
            "※Anker Japan 公式オンラインストア会員を対象に、通常18ヶ月の製品保証を5年へ自動延長致します。",
        )
        for claim_id in (
            "CLM-ST1704-POWER-C300-SPECS",
            "CLM-ST1704-ANKER-C300-SPECS",
        )
    },
    (
        "SRC-ANKER-SOLIX-C800-PLUS",
        "CLM-ST1704-ANKER-C800-SPECS",
    ): (
        '<meta property="og:title" content="Anker Solix C800 Plus Portable Power Station | リン酸鉄ポータブル電源の製品情報">',
        '<div id="product-variant-stock" class="product-variant-stock">在庫わずか</div>',
        ANKER_STOCK_BOUND_PURCHASE_FRAGMENT,
        '<td>A17545Z1 (ダークグレー) / A1754511 (ブラック)',
        "※Anker Japan 公式オンラインストア会員を対象に、通常18ヶ月の製品保証を5年へ自動延長致します。",
    ),
    (
        "SRC-ANKER-SOLIX-C1000",
        "CLM-ST1704-ANKER-C1000-SPECS",
    ): (
        '<meta property="og:title" content="Anker Solix C1000 Portable Power Station | リン酸鉄ポータブル電源の製品情報">',
        '<div id="product-variant-stock" class="product-variant-stock">在庫わずか</div>',
        ANKER_STOCK_BOUND_PURCHASE_FRAGMENT,
        '<td>A17615Z1 (ダークグレー) / A1761521 (ベージュ) / A1761511 (ブラック)',
        "※Anker Japan 公式オンラインストア会員を対象に、通常18ヶ月の製品保証を5年へ自動延長致します。",
    ),
    (
        "SRC-ANKER-SOLIX-C1000-GEN2",
        "CLM-ST1704-ANKER-C1000-GEN2-SPECS",
    ): (
        '<meta property="og:title" content="Anker Solix C1000 Gen 2 Portable Power Station | ポータブル電源の製品情報">',
        '<div id="product-variant-stock" class="product-variant-stock">在庫わずか</div>',
        ANKER_STOCK_BOUND_PURCHASE_FRAGMENT,
        '<td>A17635Z1 (ダークグレー) / A1763521 (オフホワイト)',
        "※Anker Japan 公式オンラインストア会員を対象に、通常18ヶ月の製品保証を5年へ自動延長致します。",
    ),
    (
        "SRC-JACKERY-500-NEW",
        "CLM-ST1704-POWER-JACKERY-SPECS",
    ): (
        "62種類の保護機能を搭載した、最先端の高速充電技術 「ChargeShieldテクノロジー2.0」 は、独自の段階的可変速充電アルゴリズムを用いることで、さらなる安全性能向上を実現しました。また、高性能のBMSを搭載。バッテリーの充放電の安全性を確保します。",
    ),
}


PDF_SOURCE_METADATA: Final[dict[str, tuple[str, int]]] = {
    "SRC-ANKER-SOLIX-C300-SAFETY-MANUAL": (
        "0cb763561ebcc4eaf230bf5a16a850023b36302ea008fb3cabd8becc0e2853a6",
        7,
    ),
    "SRC-ANKER-SOLIX-C800-SAFETY-MANUAL": (
        "d3b6e6e704c7d68e32334489efd9e9b1825ef906baf9fb0d78d190d6dc8e6e6a",
        2,
    ),
    "SRC-ANKER-SOLIX-C800-PLUS-SAFETY-MANUAL": (
        "41499aea5474caa77a62a41c295b853cafa89f3be3de471b1e0fd3ca5b67b3c4",
        2,
    ),
    "SRC-ANKER-SOLIX-C1000-SAFETY-MANUAL": (
        "4b137db82b45db52ccadc27a7724591d788946c47da866088e9812b4712ce474",
        5,
    ),
    "SRC-ANKER-SOLIX-C1000-GEN2-SAFETY-MANUAL": (
        "58ec831d2c6889e997b6f8540265c133f7c70b6a58ca59935acebe9d8a44e39b",
        2,
    ),
    "SRC-DJI-POWER-1000-V2-SAFETY-GUIDELINES-JA": (
        "32aff6629ae6c1ef527b944e04105db246e2cefb253b89469e921773c0c08712",
        7,
    ),
    "SRC-DJI-POWER-1000-V2-USER-MANUAL-JA": (
        "24abd72b764139afec6d9f3a92a68061d7adafc12db6921307ef9583e1e082ed",
        20,
    ),
    "SRC-SAMSONITE-CATALOG-2025": (
        "6d874e47c4999547adc3b6671024405a29f90c3ade1d0ab0f27d22449284b5cd",
        10,
    ),
    "SRC-JACKERY-500-NEW-MANUAL": (
        "9173e08ad1239d5522f7b30f29401ea4d18912de4ff9a91949cfc26fdeb33b45",
        17,
    ),
    "SRC-SIROCA-SS-M171-MANUAL": (
        "8693f01c5fba96c146d4a7d8fa863003e8d67f3465a40d5b56008ac0ae5b974e",
        31,
    ),
    "SRC-PANASONIC-NP-TML1-MANUAL": (
        "09b7499fe6407f193a5203db17df7fb22bd4deee45b8d569f898fa7188adf3c5",
        6,
    ),
}

PDF_CLAIM_REVIEWED_PAGES: Final[dict[tuple[str, str], int]] = {
    ("SRC-JACKERY-500-NEW-MANUAL", "CLM-ST1704-POWER-JACKERY-SPECS"): 17,
    ("SRC-JACKERY-500-NEW-MANUAL", "CLM-ST1704-POWER-JACKERY-STORAGE"): 15,
    ("SRC-JACKERY-500-NEW-MANUAL", "CLM-ST1704-POWER-JACKERY-WARRANTY"): 18,
}

DIFFERENCE_05721_06_FRAGMENTS: Final = (
    "<title>ace.／エース ディフェレンス フロントオープン 機内持ち込み "
    "エキスパンド機能 32/38L 05721(06：ホワイト): ace.｜エース公式通販</title>",
    '<input type="hidden" name="goods" value="05721-06">',
    "<dt>サイズ</dt>\r\n\t\t\t<dd>H55×W36×D24/27 cm <br>"
    "※キャスター・ハンドルを含む外寸表記です。</dd>",
    "<dt>容量</dt>\r\n\t\t\t<dd>32/38 L</dd>",
    "<dt>重量</dt>\r\n\t\t\t<dd>3.5kg</dd>",
    "● エキスパンド機能(容量拡張)",
    "● キャスターストッパー",
    "２通りの開閉が可能",
    '<dd id="spec_stock_msg">在庫あります</dd>',
    # The same cart button appears in the main and sticky-footer forms.
    # Bind this occurrence to the exact white variant instead of dropping the
    # purchase control or allowing ambiguous matches.
    '<input type="hidden" value=05721-06 name="goods">\r\n'
    '\t\t\t\t\t<div class="block-add-cart">\r\n'
    '<button class="block-add-cart--btn btn btn-primary '
    'js-enhanced-ecommerce-add-cart-detail " type="submit" '
    'value="カートに入れる">カートに入れる</button>',
)

ANKER_C1000_FEATURE_DIFF_FRAGMENTS: Final = (
    "<h3>【10年長寿命・4000回サイクル】</h3>\n"
    "<p>リン酸鉄リチウムイオン電池採用で4000回以上の充放電サイクルを実現。",
    "AC x 5 / USB-C x 3 / USB-A x 1 / シガーソケット x 1",
    "AC x 6 / USB-C x 2 / USB-A x 2 / シガーソケット x 1",
    "<th>AC出力 (SurgePad™技術)</th>",
    "<th>拡張バッテリー対応</th>",
    "電池 4,000回 / 電子部品 50,000時間",
    "電池 3,000回/ 電子部品 50,000時間",
    "停電時に約0.01秒で自動切り替えする機能搭載",
    "停電時も約0.02秒で自動切替し",
)

CLAIM_FRAGMENT_OVERRIDES: Final[dict[tuple[str, str], tuple[str, ...]]] = {
    **{
        ("SRC-PANASONIC-NP-TMLK1", claim_id): PANASONIC_NP_TMLK1_IDENTITY_FRAGMENTS
        for claim_id in (
            "CLM-ST1704-DISH-NP-TMLK1-EXCLUDED",
            "CLM-PORTFOLIO-DISH-SOLOTA-NP-TMLK1-IDENTITY-REFERENCE",
            "CLM-PORTFOLIO-DISH-LIFECYCLE-REFERENCE",
            "CLM-PORTFOLIO-DISH-SOLOTA-NP-TMLK1-EXCLUDED",
        )
    },
    (
        "SRC-ANKER-SOLIX-C1000-GEN2",
        "CLM-ST1704-ANKER-C1000-FEATURE-DIFF",
    ): ANKER_C1000_FEATURE_DIFF_FRAGMENTS,
    **{
        ("SRC-ACE-DIFFERENCE-05721", claim_id): DIFFERENCE_05721_06_FRAGMENTS
        for claim_id in (
            "CLM-ST1704-SUITCASE-DIFFERENCE-SPECS",
            "CLM-ST1704-SUITCASE-CONDITIONAL-CHOICES",
            "CLM-PORTFOLIO-FRONT-DIFFERENCE-05721",
            "CLM-PORTFOLIO-FRONT-CONDITIONAL-CHOICES",
            "CLM-PORTFOLIO-FRONT-MUJI32-EXCLUDED",
        )
    },
    **{
        ("SRC-ANKER-SOLIX-C300", claim_id): (
            '<td class="product-specs-heading">サイズ</td>\n                  <td>約16.4 x 16.1 x 24.0cm （ 幅 x 奥行 x 高さ )</td>',
            '<td class="product-specs-heading">重さ</td>\n                <td>約4.1kg</td>',
            '<td class="product-specs-heading">出力</td>\n                <td>定格300W / 瞬間最大600W</td>',
            '<td class="product-specs-heading">バッテリー容量</td>\n                <td>288Wh</td>',
            '<meta property="og:title" content="Anker Solix C300 Portable Power Station | ポータブル電源の製品情報">',
            '<div id="product-variant-stock" class="product-variant-stock">在庫わずか</div>',
            ANKER_STOCK_BOUND_PURCHASE_FRAGMENT,
            '<td>A17225Z1 (ダークグレー) / A1722511 (ブラック)',
            "※Anker Japan 公式オンラインストア会員を対象に、通常18ヶ月の製品保証を5年へ自動延長致します。",
        )
        for claim_id in (
            "CLM-ST1704-POWER-C300-SPECS",
            "CLM-ST1704-POWER-CONDITIONAL-CHOICES",
            "CLM-ST1704-ANKER-C300-SPECS",
            "CLM-ST1704-ANKER-CONDITIONAL-CHOICES",
        )
    },
    (
        "SRC-JACKERY-500-NEW-DIMENSION-AXES",
        "CLM-ST1704-POWER-JACKERY-SPECS",
    ): (
        "サイズ（幅×奥行×高さ）",
        '<span lang="ja">500 New</span></td>'
        '<td style="height: 19.5982px; width: 71.0613%;">'
        '<span lang="ja">311×205×157mm</span>',
        "311×205×157mm</span></td>",
    ),
    **{
        ("SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY", claim_id): (
            '<h1 class="purchase_name">Roomba Mini 掃除機＆床拭きロボット + '
            "AutoEmpty 充電ステーション</h1>",
            '<input type="hidden" name="item_cd" value="F155260" />',
            '<div class="purchase_btn-buy soldout">在庫切れ</div>',
        )
        for claim_id in (
            "CLM-ST1704-ROBOT-ROOMBA-MINI-F155260-EXCLUDED",
            "CLM-PORTFOLIO-ROBOT-ROOMBA-MINI-F155260-EXCLUDED",
        )
    },
    (
        "SRC-ACE-CRESTA-06316",
        "CLM-ST1704-SUITCASE-CRESTA-06316-EXCLUDED",
    ): (
        "<title>【WEB限定】 ACE クレスタ スーツケース 34/39L エキスパンド機能 機内持ち込み 06316(01：ブラックカーボン): ACE｜エース公式通販</title>",
        "<dt>サイズ</dt>\r\n\t\t\t<dd>H55×W35×D25/29 cm <br>※キャスター・ハンドルを含む外寸表記です。</dd>",
        "<dt>容量</dt>\r\n\t\t\t<dd>34/39 L</dd>",
        "<dt>重量</dt>\r\n\t\t\t<dd>3.2kg</dd>",
        '<dd id="spec_stock_msg">申し訳ございません。在庫切れとなっております</dd>',
    ),
    (
        "SRC-JACKERY-500-NEW-MANUAL",
        "CLM-ST1704-POWER-JACKERY-STORAGE",
    ): (
        "長期保管する場合",
        "3ヶ月に一度",
        "充電",
        "電池残量が0%にならない",
    ),
    (
        "SRC-JACKERY-500-NEW-MANUAL",
        "CLM-ST1704-POWER-JACKERY-WARRANTY",
    ): (
        "保証期間：3年間",
        "延長保証登録",
        "2年間",
        "正規代理店",
    ),
    (
        "SRC-JACKERY-500-NEW",
        "CLM-ST1704-POWER-JACKERY-WARRANTY",
    ): (
        '<h2 style="font-size: 1.2em; line-height: 35px;">【5年保証・無償回収リサイクル】</h2>',
        "<p>公式サイトで購入日から3年の保証に加えて、2年の自動延長保証を追加（製品の保証登録が不要です）。5年間の長期保証を実現しました。故障時の修理サービスや製品回収サービスもご用意しているので購入後も安心です。</p>",
    ),
    (
        "SRC-BLUETTI-AC70",
        "CLM-ST1704-POWER-AC70-EXCLUDED",
    ): ("お知らせ", "終売", "売り切れ"),
    (
        "SRC-ECOFLOW-DELTA3-CLASSIC",
        "CLM-ST1704-POWER-DELTA3-CLASSIC-EXCLUDED",
    ): ("売り切れ", '"available":true'),
}


def _source_capture_hash(
    source: dict[str, object], claims: list[dict[str, object]]
) -> str:
    return _canonical_sha256(
        {
            "schema": "STRUCTURED_SOURCE_FACT_PACKET_V1",
            "source_ref": source["source_ref"],
            "authority": source["authority"],
            "source_type": source["source_type"],
            "title": source["title"],
            "url": source["url"],
            "retrieved_on": source["retrieved_on"],
            "claims": [
                {
                    **{
                        key: claim[key]
                        for key in (
                            "claim_id",
                            "classification",
                            "statement",
                            "status",
                            "subject_product_ids",
                        )
                    },
                    **{
                        key: claim[key]
                        for key in (
                            "dimensions",
                            "market_candidate_id",
                            "market_disposition",
                            "official_url",
                            "exact_model",
                            "exact_variant_scope",
                            "evaluated_at",
                            "model_lifecycle",
                            "variant_lifecycle",
                            "reader_visible_lifecycle",
                            "embedded_structured_lifecycle",
                            "lifecycle_evidence_state",
                            "effective_lifecycle",
                            "negative_claim_evidence",
                            "product_specific_recall_query_gate",
                            "manufacturer_sales_state",
                            "portfolio_candidate_disposition",
                            "portfolio_candidate_reason",
                            "route_article_id",
                        )
                        if key in claim
                    },
                }
                for claim in sorted(claims, key=lambda value: str(value["claim_id"]))
            ],
        }
    )


def _packet_hash(packet: dict[str, object]) -> str:
    return _canonical_sha256(
        {
            "schema": "STRUCTURED_ARTICLE_SOURCE_PACKET_V1",
            "source_packet_ref": packet["source_packet_ref"],
            "article_id": packet["article_id"],
            "source_refs": packet["source_refs"],
            "claims": packet["claims"],
            "draft_claim_coverage": packet["draft_claim_coverage"],
        }
    )


def _apply_first_five_product_replacements(registry: dict[str, object]) -> None:
    """Replace unavailable selected products without changing article identities."""

    suitcase_packet = next(
        packet
        for packet in registry["source_packets"]
        if packet["article_id"] == "st1703-first-suitcase-comparison"
    )
    suitcase_packet["source_refs"] = list(
        dict.fromkeys(
            [
                *suitcase_packet["source_refs"],
                "SRC-PROTECA-TRI-AIR-01541",
                "SRC-PROTECA-SUITCASE-WARRANTY",
            ]
        )
    )
    for claim in suitcase_packet["claims"]:
        if claim["claim_id"] == "CLM-ST1704-SUITCASE-CRESTA-SPECS":
            claim.update(
                {
                    "claim_id": "CLM-ST1704-SUITCASE-TRIAIR-01541-SPECS",
                    "evidence_refs": [
                        "SRC-PROTECA-TRI-AIR-01541",
                        "SRC-PROTECA-SUITCASE-WARRANTY",
                    ],
                }
            )
        elif claim["claim_id"] == "CLM-ST1704-SUITCASE-CONDITIONAL-CHOICES":
            claim["evidence_refs"] = list(
                dict.fromkeys(
                    [
                        source_ref
                        for source_ref in claim["evidence_refs"]
                        if source_ref != "SRC-ACE-CRESTA-06316"
                    ]
                    + [
                        "SRC-PROTECA-TRI-AIR-01541",
                        "SRC-PROTECA-SUITCASE-WARRANTY",
                    ]
                )
            )
    for resource in registry["affiliate_resources"]:
        if resource["product_id"] == "PRD-ACE-CRESTA-06316":
            resource.update(
                {
                    "affiliate_ref": "AFF-PROTECA-TRI-AIR-01541",
                    "product_id": "PRD-PROTECA-TRI-AIR-01541",
                    "product_name": "PROTECA Tri-Air 01541",
                    "cta_copy": "楽天市場で現在の価格・在庫・カラーを見る",
                }
            )

    power_packet = next(
        packet
        for packet in registry["source_packets"]
        if packet["article_id"] == "st1704-portable-power-station-guide"
    )
    jackery_v3_affiliates = [
        resource
        for resource in registry["affiliate_resources"]
        if resource["product_id"] == "PRD-JACKERY-1000-NEW-V3"
    ]
    if not jackery_v3_affiliates:
        registry["affiliate_resources"].append(
            {
                "affiliate_ref": "AFF-JACKERY-1000-NEW-V3",
                "product_id": "PRD-JACKERY-1000-NEW-V3",
                "product_name": "Jackery ポータブル電源 1000 New V3",
                "status": "PENDING_OWNER_LOCAL_RAKUTEN_EVIDENCE",
                "destination_policy": "DIRECT_RAKUTEN_AFFILIATE_URL",
                "destination_url": None,
                "required_rel": "sponsored nofollow",
                "cta_copy": "楽天市場で現在の価格・在庫・カラーを見る",
                "evidence": None,
                "publication_blocker": "PENDING_AFFILIATE_EVIDENCE",
            }
        )
    elif len(jackery_v3_affiliates) != 1:
        raise ValueError("duplicate Jackery 1000 New V3 affiliate resources")
    for product_id, affiliate_ref, product_name in (
        (
            "PRD-BLUETTI-AORA30-V2",
            "AFF-BLUETTI-AORA30-V2",
            "BLUETTI AORA 30 V2（グレー）",
        ),
        (
            "PRD-BLUETTI-AORA100-V2",
            "AFF-BLUETTI-AORA100-V2",
            "BLUETTI AORA 100 V2（インディゴ）",
        ),
    ):
        matches = [
            resource
            for resource in registry["affiliate_resources"]
            if resource["product_id"] == product_id
        ]
        if not matches:
            registry["affiliate_resources"].append(
                {
                    "affiliate_ref": affiliate_ref,
                    "product_id": product_id,
                    "product_name": product_name,
                    "status": "PENDING_OWNER_LOCAL_RAKUTEN_EVIDENCE",
                    "destination_policy": "DIRECT_RAKUTEN_AFFILIATE_URL",
                    "destination_url": None,
                    "required_rel": "sponsored nofollow",
                    "cta_copy": "楽天市場で現在の価格・在庫・カラーを見る",
                    "evidence": None,
                    "publication_blocker": "PENDING_AFFILIATE_EVIDENCE",
                }
            )
        elif len(matches) != 1:
            raise ValueError(f"duplicate BLUETTI affiliate resources: {product_id}")
    power_packet["source_refs"] = list(
        dict.fromkeys(
            [
                source_ref
                for source_ref in power_packet["source_refs"]
                if source_ref not in {"SRC-BLUETTI-AC70", "SRC-ECOFLOW-DELTA3-CLASSIC"}
            ]
            + [
                "SRC-BLUETTI-AC70",
                "SRC-ECOFLOW-DELTA3-CLASSIC",
                "SRC-ANKER-SOLIX-C800",
                "SRC-DJI-POWER-1000-V2-STORE",
                "SRC-DJI-POWER-1000-V2-SPECS",
                "SRC-JACKERY-500-NEW-MANUAL",
                "SRC-JACKERY-500-NEW-DIMENSION-AXES",
                "SRC-JACKERY-1000-NEW-V3",
                "SRC-JACKERY-1000-NEW-V3-LAUNCH",
                "SRC-BLUETTI-AORA30-V2",
                "SRC-BLUETTI-AORA30-V2-DIMENSIONS",
                "SRC-BLUETTI-AORA100-V2",
                "SRC-BLUETTI-AORA-SERIES-COLLECTION",
                "SRC-METI-PORTABLE-POWER-SAFETY",
                "SRC-METI-ELECTRICAL-RECALLS",
            ]
        )
    )
    for claim in power_packet["claims"]:
        if claim["claim_id"] == "CLM-ST1704-POWER-AC70-SPECS":
            claim.update(
                {
                    "claim_id": "CLM-ST1704-POWER-ANKER-C800-SPECS",
                    "evidence_refs": ["SRC-ANKER-SOLIX-C800"],
                }
            )
        elif claim["claim_id"] == "CLM-ST1704-POWER-DELTA-SPECS":
            claim.update(
                {
                    "claim_id": "CLM-ST1704-POWER-DJI-1000-V2-SPECS",
                    "evidence_refs": [
                        "SRC-DJI-POWER-1000-V2-STORE",
                        "SRC-DJI-POWER-1000-V2-SPECS",
                    ],
                }
            )
        elif claim["claim_id"] == "CLM-ST1704-POWER-CONDITIONAL-CHOICES":
            claim["evidence_refs"] = list(
                dict.fromkeys(
                    [
                        source_ref
                        for source_ref in claim["evidence_refs"]
                        if source_ref
                        not in {
                            "SRC-BLUETTI-AC70",
                            "SRC-ECOFLOW-DELTA3-CLASSIC",
                        }
                    ]
                    + [
                        "SRC-ANKER-SOLIX-C800",
                        "SRC-JACKERY-1000-NEW-V3",
                        "SRC-JACKERY-1000-NEW-V3-LAUNCH",
                        "SRC-BLUETTI-AORA30-V2",
                        "SRC-BLUETTI-AORA30-V2-DIMENSIONS",
                        "SRC-BLUETTI-AORA100-V2",
                        "SRC-BLUETTI-AORA-SERIES-COLLECTION",
                        "SRC-DJI-POWER-1000-V2-STORE",
                        "SRC-DJI-POWER-1000-V2-SPECS",
                    ]
                )
            )
        elif claim["claim_id"] == "CLM-ST1704-POWER-JACKERY-SPECS":
            claim["evidence_refs"] = list(
                dict.fromkeys(
                    [
                        *claim["evidence_refs"],
                        "SRC-JACKERY-500-NEW-MANUAL",
                        "SRC-JACKERY-500-NEW-DIMENSION-AXES",
                    ]
                )
            )

    power_resource_replacements = {
        "PRD-BLUETTI-AC70": {
            "affiliate_ref": "AFF-ANKER-SOLIX-C800",
            "product_id": "PRD-ANKER-SOLIX-C800",
            "product_name": "Anker Solix C800 Portable Power Station",
        },
        "PRD-ECOFLOW-DELTA3-CLASSIC": {
            "affiliate_ref": "AFF-DJI-POWER-1000-V2",
            "product_id": "PRD-DJI-POWER-1000-V2",
            "product_name": "DJI Power 1000 V2",
        },
    }
    for resource in registry["affiliate_resources"]:
        replacement = power_resource_replacements.get(resource["product_id"])
        if replacement is not None:
            resource.update(replacement)
            resource["cta_copy"] = "楽天市場で現在の価格・在庫・カラーを見る"

    packets = [
        packet
        for packet in registry["source_packets"]
        if packet["article_id"] == "st1704-countertop-dishwasher-for-small-households"
    ]
    if len(packets) != 1:
        raise ValueError("expected exactly one A04 source packet")
    packet = packets[0]
    packet["source_refs"] = [
        "SRC-THANKO-RAKUA-MINI-TK-MDW22W"
        if source_ref == "SRC-THANKO-RAKUA-MINI-COLOR"
        else source_ref
        for source_ref in packet["source_refs"]
    ]
    for claim in packet["claims"]:
        claim["evidence_refs"] = [
            "SRC-THANKO-RAKUA-MINI-TK-MDW22W"
            if source_ref == "SRC-THANKO-RAKUA-MINI-COLOR"
            else source_ref
            for source_ref in claim["evidence_refs"]
        ]

    resources = [
        resource
        for resource in registry["affiliate_resources"]
        if resource["product_id"]
        in {
            "PRD-THANKO-RAKUA-MINI-COLOR",
            "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        }
    ]
    if len(resources) != 1:
        raise ValueError("expected exactly one retired A04 affiliate resource")
    resource = resources[0]
    resource.update(
        {
            "affiliate_ref": "AFF-THANKO-RAKUA-MINI-TK-MDW22W",
            "product_id": "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
            "product_name": "THANKO ラクアmini TK-MDW22W",
            "cta_copy": "楽天市場で現在の価格・在庫・カラーを見る",
        }
    )

    dishwasher_packet = next(
        packet
        for packet in registry["source_packets"]
        if packet["article_id"] == "st1704-countertop-dishwasher-for-small-households"
    )
    dishwasher_packet["claims"] = [
        claim
        for claim in dishwasher_packet["claims"]
        if claim["claim_id"]
        not in {
            "CLM-ST1704-DISH-NP-TMLK1-SPECS",
            "CLM-ST1704-DISH-SS-M171-REFERENCE",
        }
    ]
    dishwasher_packet["source_refs"] = list(
        dict.fromkeys(
            [
                source_ref
                for source_ref in dishwasher_packet["source_refs"]
                if source_ref != "SRC-PANASONIC-NP-TSP2"
            ]
            + [
                "SRC-PANASONIC-NP-TSP2-LAUNCH",
                "SRC-PANASONIC-NP-TSP2-SUBSCRIPTION",
                "SRC-TOSHIBA-DWS-33B",
                "SRC-TOSHIBA-DWS-33B-STORE",
                "SRC-TOSHIBA-PARTS-RETENTION",
                "SRC-SIROCA-SS-M171",
                "SRC-SIROCA-SS-M171-MANUAL",
                "SRC-SIROCA-SS-M171-STORE",
                "SRC-SIROCA-SS-MA251-STORE",
                "SRC-SIROCA-DISHWASHER-INSTALLATION",
            ]
        )
    )
    for claim in dishwasher_packet["claims"]:
        if claim["claim_id"] == "CLM-ST1704-DISH-NP-TSP2-SPECS":
            claim.update(
                {
                    "claim_id": "CLM-ST1704-DISH-TOSHIBA-DWS-33B-SPECS",
                    "evidence_refs": [
                        "SRC-TOSHIBA-DWS-33B",
                        "SRC-TOSHIBA-DWS-33B-STORE",
                        "SRC-TOSHIBA-PARTS-RETENTION",
                    ],
                }
            )
        elif claim["claim_id"] == "CLM-ST1704-DISH-CONDITIONAL-CHOICES":
            claim["evidence_refs"] = list(
                dict.fromkeys(
                    [
                        source_ref
                        for source_ref in claim["evidence_refs"]
                        if source_ref
                        not in {
                            "SRC-PANASONIC-NP-TSP2",
                            "SRC-PANASONIC-NP-TMLK1",
                        }
                    ]
                    + [
                        "SRC-SIROCA-SS-M171",
                        "SRC-SIROCA-SS-M171-MANUAL",
                        "SRC-SIROCA-SS-M171-STORE",
                        "SRC-TOSHIBA-DWS-33B",
                        "SRC-TOSHIBA-PARTS-RETENTION",
                    ]
                )
            )
    resources = [
        resource
        for resource in registry["affiliate_resources"]
        if resource["product_id"] in {"PRD-PANASONIC-NP-TSP2", "PRD-TOSHIBA-DWS-33B-W"}
    ]
    if len(resources) != 1:
        raise ValueError("expected exactly one retired NP-TSP2 affiliate resource")
    resources[0].update(
        {
            "affiliate_ref": "AFF-TOSHIBA-DWS-33B-W",
            "product_id": "PRD-TOSHIBA-DWS-33B-W",
            "product_name": "東芝 DWS-33B(W)",
            "cta_copy": "楽天市場で現在の価格・在庫・カラーを見る",
        }
    )
    resources = [
        resource
        for resource in registry["affiliate_resources"]
        if resource["product_id"] in {"PRD-PANASONIC-NP-TMLK1", "PRD-SIROCA-SS-M171"}
    ]
    if len(resources) != 1:
        raise ValueError("expected exactly one retired NP-TMLK1 affiliate resource")
    resources[0].update(
        {
            "affiliate_ref": "AFF-SIROCA-SS-M171",
            "product_id": "PRD-SIROCA-SS-M171",
            "product_name": "siroca SS-M171",
            "cta_copy": "楽天市場で現在の価格・在庫・カラーを見る",
        }
    )

    robot_packet = next(
        packet
        for packet in registry["source_packets"]
        if packet["article_id"] == "st1704-compact-robot-vacuum-shortlist"
    )
    robot_packet["source_refs"] = list(
        dict.fromkeys(
            [
                *[
                    source_ref
                    for source_ref in robot_packet["source_refs"]
                    if source_ref != "SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY"
                ],
                "SRC-EUFY-AUTOEMPTY-C10-T2292",
                "SRC-ECOVACS-DEEBOT-MINI2",
                "SRC-ECOVACS-WARRANTY",
            ]
        )
    )
    for claim in robot_packet["claims"]:
        if claim["claim_id"] in {
            "CLM-ST1704-ROBOT-ROOMBA-MINI-SPECS",
            "CLM-ST1704-ROBOT-EUFY-C10-SPECS",
        }:
            claim.update(
                {
                    "claim_id": "CLM-ST1704-ROBOT-EUFY-C10-SPECS",
                    "evidence_refs": ["SRC-EUFY-AUTOEMPTY-C10-T2292"],
                }
            )
            claim.pop("manufacturer_sales_state", None)
        elif claim["claim_id"] == "CLM-ST1704-ROBOT-K10-COMBO-SPECS":
            claim.update(
                {
                    "claim_id": "CLM-ST1704-ROBOT-DEEBOT-MINI2-SPECS",
                    "evidence_refs": [
                        "SRC-ECOVACS-DEEBOT-MINI2",
                        "SRC-ECOVACS-WARRANTY",
                    ],
                }
            )
        elif claim["claim_id"] == "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES":
            claim.pop("manufacturer_sales_state", None)
            claim["evidence_refs"] = list(
                dict.fromkeys(
                    [
                        source_ref
                        for source_ref in claim["evidence_refs"]
                        if source_ref
                        not in {
                            "SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY",
                            "SRC-SWITCHBOT-K10-PRO-COMBO",
                        }
                    ]
                    + [
                        "SRC-EUFY-AUTOEMPTY-C10-T2292",
                        "SRC-ECOVACS-DEEBOT-MINI2",
                        "SRC-ECOVACS-WARRANTY",
                    ]
                )
            )
    for resource in registry["affiliate_resources"]:
        if resource["product_id"] == "PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY":
            resource.update(
                {
                    "affiliate_ref": "AFF-EUFY-AUTOEMPTY-C10-T2292",
                    "product_id": "PRD-EUFY-AUTOEMPTY-C10-T2292",
                    "product_name": "Eufy Robot Vacuum Auto-Empty C10 (T2292511)",
                    "cta_copy": "楽天市場で現在の価格・在庫・カラーを見る",
                }
            )
        if resource["product_id"] == "PRD-SWITCHBOT-K10-PRO-COMBO":
            resource.update(
                {
                    "affiliate_ref": "AFF-ECOVACS-DEEBOT-MINI2",
                    "product_id": "PRD-ECOVACS-DEEBOT-MINI2",
                    "product_name": "ECOVACS DEEBOT mini 2",
                    "cta_copy": "楽天市場で現在の価格・在庫・カラーを見る",
                }
            )

    c_lite_resources = [
        resource
        for resource in registry["affiliate_resources"]
        if resource["product_id"] == "PRD-SAMSONITE-C-LITE-CS2-09007"
    ]
    # Later-five HTML fixtures do not use the first-five structured affiliate
    # resource inventory.  Retain compatibility with an older registry that did
    # carry C-Lite, without inventing a nineteenth resource in the current one.
    if len(c_lite_resources) > 1:
        raise ValueError("duplicate retired C-Lite affiliate resource")
    if c_lite_resources:
        c_lite_resources[0].update(
            {
                "affiliate_ref": "AFF-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
                "product_id": "PRD-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
                "product_name": "RIMOWA Essential Lite キャビン 82353171",
                "cta_copy": "楽天市場で現在の価格・在庫・カラーを見る",
            }
        )
    for affiliate_resource in registry["affiliate_resources"]:
        affiliate_resource["cta_copy"] = "楽天市場で現在の価格・在庫・カラーを見る"


def _apply_first_five_dimension_contract(registry: dict[str, object]) -> None:
    packets = {
        str(packet["source_packet_ref"]): packet
        for packet in registry["source_packets"]
    }
    for packet_ref, additions in FIRST_FIVE_ADDITIONAL_CLAIMS.items():
        packet = packets.get(packet_ref)
        if packet is None:
            raise ValueError(f"missing first-five packet: {packet_ref}")
        by_id = {str(claim["claim_id"]): claim for claim in packet["claims"]}
        for addition in additions:
            by_id[str(addition["claim_id"])] = dict(addition)
        packet["claims"] = list(by_id.values())
        packet["source_refs"] = list(
            dict.fromkeys(
                [
                    *packet["source_refs"],
                    *(
                        source_ref
                        for addition in additions
                        for source_ref in addition["evidence_refs"]
                    ),
                ]
            )
        )
        verifiable = sum(
            claim["classification"] == "MAJOR_VERIFIABLE" for claim in packet["claims"]
        )
        packet["draft_claim_coverage"] = {
            "major_claim_count": len(packet["claims"]),
            "official_source_bound_major_claim_count": len(packet["claims"]),
            "verifiable_claim_count": verifiable,
            "official_source_bound_verifiable_claim_count": verifiable,
        }
    claims = {
        str(claim["claim_id"]): claim
        for packet in registry["source_packets"]
        for claim in packet["claims"]
    }
    missing_statements = set(FIRST_FIVE_STATEMENT_OVERRIDES) - claims.keys()
    if missing_statements:
        raise ValueError(
            f"missing decision-critical claims: {sorted(missing_statements)}"
        )
    for claim_id, statement in FIRST_FIVE_STATEMENT_OVERRIDES.items():
        claims[claim_id]["statement"] = statement
    missing = set(FIRST_FIVE_DIMENSION_CLAIMS) - claims.keys()
    if missing:
        raise ValueError(
            f"missing decision-critical dimension claims: {sorted(missing)}"
        )
    for claim_id, dimensions in FIRST_FIVE_DIMENSION_CLAIMS.items():
        claims[claim_id]["dimensions"] = [dict(value) for value in dimensions]


def _validate_dimension_contract(registry: dict[str, object]) -> None:
    claims = {
        str(claim["claim_id"]): claim
        for packet in registry["source_packets"]
        for claim in packet["claims"]
    }
    for claim in claims.values():
        if {"dimension_values", "dimensions_cm"} & claim.keys() or any(
            isinstance(value, list)
            and len(value) == 3
            and all(type(axis) in {int, float} for axis in value)
            for value in claim.values()
        ):
            raise ValueError("unlabeled three-value dimension arrays are forbidden")
        raw_dimensions = claim.get("dimensions")
        if raw_dimensions is None:
            continue
        if not isinstance(raw_dimensions, list) or not raw_dimensions:
            raise ValueError("dimensions must be a non-empty structured list")
        subjects: set[str] = set()
        for dimensions in raw_dimensions:
            if not isinstance(dimensions, dict) or set(dimensions) != {
                "subject",
                "width_cm",
                "depth_cm",
                "height_cm",
            }:
                raise ValueError("dimension records require subject and named axes")
            subject = dimensions["subject"]
            if (
                not isinstance(subject, str)
                or not subject.strip()
                or subject in subjects
            ):
                raise ValueError("dimension subjects must be unique non-empty strings")
            subjects.add(subject)
            for axis in ("width_cm", "depth_cm", "height_cm"):
                value = dimensions[axis]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("dimension axes must be positive numbers")
                if value <= 0:
                    raise ValueError("dimension axes must be positive numbers")

    for claim_id in FIRST_FIVE_DIMENSION_CLAIMS:
        if "dimensions" not in claims[claim_id]:
            raise ValueError(f"missing dimensions for {claim_id}")
    for key, expected_dimensions in MARKET_CANDIDATE_DIMENSIONS.items():
        claim_id = MARKET_CANDIDATE_CLAIM_IDS.get(key)
        if claim_id is None or claim_id not in claims:
            raise ValueError(f"missing market candidate dimension claim: {key}")
        if claims[claim_id].get("dimensions") != [
            dict(value) for value in expected_dimensions
        ]:
            raise ValueError(f"market candidate dimension mismatch: {claim_id}")

    deebot = claims["CLM-ST1704-ROBOT-DEEBOT-MINI2-SPECS"]
    deebot_subjects = {str(value["subject"]) for value in deebot.get("dimensions", [])}
    if deebot_subjects != {
        "ECOVACS DEEBOT mini 2本体",
        "ECOVACS DEEBOT mini 2ステーション",
    }:
        raise ValueError("DEEBOT mini 2 body and station axes must remain explicit")
    robot_decision = claims["CLM-ST1704-ROBOT-CONDITIONAL-CHOICES"]
    decision_statement = str(robot_decision["statement"])
    if (
        "K10+ Pro Combo" not in decision_statement
        or "現行4候補から除外" not in decision_statement
        or re.search(
            r"K10\+ Pro Combo.{0,120}幅\d.{0,80}奥行\d.{0,80}高さ\d",
            decision_statement,
        )
        is not None
        or any(
            "K10+ Pro Combo" in str(value["subject"])
            for value in robot_decision.get("dimensions", [])
        )
    ):
        raise ValueError("excluded K10 station dimensions reached a decision claim")


def _apply_market_candidate_claims(registry: dict[str, object]) -> None:
    """Bind the complete reader-visible external-candidate ledger.

    The audit remains the owner of candidate identity, exact variant, current
    lifecycle observation, and displayed rationale.  This source owner rejects
    an audit inventory change until every candidate has a stable claim id and
    every cited URL has an exact official source record.
    """

    audit = json.loads(MARKET_AUDIT_PATH.read_text(encoding="utf-8"))
    candidates = {
        (str(article["article_id"]), str(candidate["candidate_id"])): candidate
        for article in audit["articles"]
        for candidate in article["considered_external_candidates"]
    }
    if set(candidates) != set(MARKET_CANDIDATE_CLAIM_IDS):
        missing = set(candidates) - set(MARKET_CANDIDATE_CLAIM_IDS)
        obsolete = set(MARKET_CANDIDATE_CLAIM_IDS) - set(candidates)
        raise ValueError(
            "reader-visible market candidate inventory drift: "
            f"missing={sorted(missing)}, obsolete={sorted(obsolete)}"
        )

    packets = {
        str(packet["article_id"]): packet for packet in registry["source_packets"]
    }
    expected_candidate_ids_by_article = {
        article_id: {
            candidate_id
            for candidate_article_id, candidate_id in candidates
            if candidate_article_id == article_id
        }
        for article_id in packets
    }
    for article_id, packet in packets.items():
        packet["claims"] = [
            claim
            for claim in packet["claims"]
            if claim.get("market_candidate_id") is None
            or str(claim["market_candidate_id"])
            in expected_candidate_ids_by_article[article_id]
        ]
    source_refs_by_url: dict[str, str] = {}
    source_urls_by_ref: dict[str, str] = {}
    for source in registry["sources"]:
        source_ref = str(source["source_ref"])
        url = str(source["url"])
        if url in source_refs_by_url:
            raise ValueError(f"duplicate official source URL: {url}")
        source_refs_by_url[url] = source_ref
        source_urls_by_ref[source_ref] = url

    for key, candidate in candidates.items():
        article_id, candidate_id = key
        packet = packets.get(article_id)
        if packet is None:
            raise ValueError(f"market candidate article has no packet: {article_id}")
        evidence_urls = [str(url) for url in candidate["evidence_refs"]]
        official_url = str(candidate["official_url"])
        if official_url not in evidence_urls:
            raise ValueError(
                f"candidate official URL is absent from evidence refs: {candidate_id}"
            )
        missing_urls = [url for url in evidence_urls if url not in source_refs_by_url]
        if missing_urls:
            raise ValueError(
                f"candidate evidence lacks official source records: "
                f"{candidate_id}/{missing_urls}"
            )
        evidence_refs = [source_refs_by_url[url] for url in evidence_urls]
        evidence_refs.extend(MARKET_CANDIDATE_EXTRA_EVIDENCE_REFS.get(key, ()))
        evidence_refs = list(dict.fromkeys(evidence_refs))
        missing_extra_refs = [
            source_ref
            for source_ref in evidence_refs
            if source_ref not in source_urls_by_ref
        ]
        if missing_extra_refs:
            raise ValueError(
                f"candidate extra evidence source is missing: "
                f"{candidate_id}/{missing_extra_refs}"
            )

        claim_id = MARKET_CANDIDATE_CLAIM_IDS[key]
        claims = {str(claim["claim_id"]): claim for claim in packet["claims"]}
        claim = claims.get(claim_id)
        if claim is None:
            claim = {"claim_id": claim_id}
            packet["claims"].append(claim)
        unknown = bool(candidate.get("decision_critical_unknowns")) or (
            candidate["disposition"] == "DEFERRED"
            or candidate["exclusion_axis"] == "primary_source_confidence"
        )
        claim.update(
            {
                "classification": (
                    "DECISION_CRITICAL_UNKNOWN" if unknown else "EDITORIAL_INFERENCE"
                ),
                "evidence_level": "UNKNOWN" if unknown else "D",
                "statement": str(candidate["reason"]),
                "evidence_refs": evidence_refs,
                "status": (
                    "UNCONFIRMED_FROM_BOUND_OFFICIAL_SOURCE"
                    if unknown
                    else "INFERENCE_FROM_BOUND_OFFICIAL_FACTS"
                ),
                "market_candidate_id": candidate_id,
                "market_disposition": str(candidate["disposition"]),
                "official_url": official_url,
                "exact_model": str(candidate["exact_model"]),
                "exact_variant_scope": str(candidate["exact_variant_scope"]),
                "evaluated_at": str(candidate["evaluated_at"]),
                "model_lifecycle": str(candidate["model_lifecycle"]),
                "variant_lifecycle": str(candidate["variant_lifecycle"]),
                "reader_visible_lifecycle": str(candidate["reader_visible_lifecycle"]),
                "embedded_structured_lifecycle": str(
                    candidate["embedded_structured_lifecycle"]
                ),
                "lifecycle_evidence_state": str(candidate["lifecycle_evidence_state"]),
                "effective_lifecycle": str(candidate["effective_lifecycle"]),
            }
        )
        claim.pop("dimensions", None)
        if key in MARKET_CANDIDATE_DIMENSIONS:
            claim["dimensions"] = [
                dict(value) for value in MARKET_CANDIDATE_DIMENSIONS[key]
            ]
        for field, value in MARKET_CANDIDATE_FIELD_ADDITIONS.get(key, {}).items():
            claim[field] = dict(value)
        packet["source_refs"] = list(
            dict.fromkeys([*packet["source_refs"], *evidence_refs])
        )
        _refresh_packet_coverage(packet)

    # Rebuilding from an already generated registry must not rotate candidate
    # evidence to a different position on every run.  Keep the established
    # non-market source order, then append the market ledger in audit order.
    # A source shared with a selected claim remains in its original position.
    for article in audit["articles"]:
        article_id = str(article["article_id"])
        packet = packets[article_id]
        market_claims = [
            claim
            for claim in packet["claims"]
            if claim.get("market_candidate_id") is not None
        ]
        market_refs = {
            str(source_ref)
            for claim in market_claims
            for source_ref in claim["evidence_refs"]
        }
        non_market_refs = {
            str(source_ref)
            for claim in packet["claims"]
            if claim.get("market_candidate_id") is None
            for source_ref in claim["evidence_refs"]
        }
        retained = [
            str(source_ref)
            for source_ref in packet["source_refs"]
            if source_ref not in market_refs or source_ref in non_market_refs
        ]
        ordered_market_refs = [
            source_ref
            for candidate in article["considered_external_candidates"]
            for source_ref in next(
                claim
                for claim in market_claims
                if claim["market_candidate_id"] == candidate["candidate_id"]
            )["evidence_refs"]
        ]
        packet["source_refs"] = list(dict.fromkeys([*retained, *ordered_market_refs]))
        _refresh_packet_coverage(packet)

    bound_candidates = {
        str(claim.get("market_candidate_id"))
        for packet in registry["source_packets"]
        for claim in packet["claims"]
        if claim.get("market_candidate_id") is not None
    }
    expected_candidates = {candidate_id for _article_id, candidate_id in candidates}
    if bound_candidates != expected_candidates:
        raise ValueError("market candidate claims are not exactly and uniquely bound")


def _apply_portfolio_candidate_claims(registry: dict[str, object]) -> None:
    """Bind every reader-visible cross-article candidate in its local packet."""

    for packet in registry["source_packets"]:
        for claim in packet["claims"]:
            replacement = REALLOCATED_SELECTED_CLAIMS.get(str(claim["claim_id"]))
            if replacement is None:
                continue
            claim.clear()
            claim.update(
                {
                    **replacement,
                    "classification": "MAJOR_VERIFIABLE",
                    "evidence_level": "A",
                    "status": "BOUND_TO_OFFICIAL_SOURCE",
                }
            )
        conditional_source = {
            "lightweight-carry-on-suitcase-under-3kg": (
                "CLM-PORTFOLIO-LIGHT-CONDITIONAL-CHOICES",
                "SRC-PROTECA-TRI-AIR-01541",
            ),
        }.get(str(packet["article_id"]))
        if conditional_source is not None:
            claim_id, source_ref = conditional_source
            conditional_claim = next(
                claim
                for claim in packet["claims"]
                if claim["claim_id"] == claim_id
            )
            conditional_claim["evidence_refs"] = list(
                dict.fromkeys([*conditional_claim["evidence_refs"], source_ref])
            )

    audit = json.loads(MARKET_AUDIT_PATH.read_text(encoding="utf-8"))
    portfolio = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    candidates: dict[tuple[str, str], dict[str, object]] = {}
    for article in audit["articles"]:
        article_id = str(article["article_id"])
        for candidate in article["considered_portfolio_candidates"]:
            key = (article_id, str(candidate["product_id"]))
            if key in candidates:
                raise ValueError(f"duplicate portfolio candidate: {key}")
            candidates[key] = candidate
    if set(candidates) != set(PORTFOLIO_CANDIDATE_REFERENCE_BINDINGS):
        missing = set(candidates) - set(PORTFOLIO_CANDIDATE_REFERENCE_BINDINGS)
        obsolete = set(PORTFOLIO_CANDIDATE_REFERENCE_BINDINGS) - set(candidates)
        raise ValueError(
            "reader-visible portfolio candidate inventory drift: "
            f"missing={sorted(missing)}, obsolete={sorted(obsolete)}"
        )

    products = {str(product["product_id"]): product for product in portfolio["products"]}
    selected_by_article = {
        str(article["article_id"]): set(article["selected_product_ids"])
        for article in audit["articles"]
    }
    packets = {
        str(packet["article_id"]): packet for packet in registry["source_packets"]
    }
    sources = {
        str(source["source_ref"]): source for source in registry["sources"]
    }
    bound_claim_ids: set[str] = set()

    for key, candidate in candidates.items():
        article_id, product_id = key
        claim_id, required_source_refs = PORTFOLIO_CANDIDATE_REFERENCE_BINDINGS[key]
        if claim_id in bound_claim_ids:
            raise ValueError(f"duplicate portfolio candidate claim id: {claim_id}")
        bound_claim_ids.add(claim_id)
        packet = packets.get(article_id)
        product = products.get(product_id)
        if packet is None or product is None:
            raise ValueError(f"portfolio candidate lacks packet or product: {key}")
        if candidate["disposition"] != "REFERENCE_ONLY":
            raise ValueError(f"portfolio candidate must be reference-only: {key}")
        route_article_id = str(candidate["route_article_id"])
        if (
            route_article_id == article_id
            or route_article_id not in selected_by_article
            or product_id not in selected_by_article[route_article_id]
            or product_id in selected_by_article[article_id]
        ):
            raise ValueError(f"portfolio candidate route is not cross-article: {key}")
        reason = str(candidate["reason"])
        official_name = str(product["official_name"])
        representative_model = str(product["representative_model"])
        official_url = str(product["official_url"])
        if not reason or not official_name or not representative_model or not official_url:
            raise ValueError(f"portfolio candidate metadata is incomplete: {key}")

        for source_ref in required_source_refs:
            source = sources.get(source_ref)
            if source is None:
                raise ValueError(
                    f"portfolio candidate official source is missing: {key}/{source_ref}"
                )
            source_url = str(source["url"])
            if source_url != official_url:
                alias = PORTFOLIO_CANDIDATE_SOURCE_URL_ALIASES.get(
                    (product_id, source_ref)
                )
                if alias != (official_url, source_url):
                    raise ValueError(
                        "portfolio candidate product/source URL mismatch: "
                        f"{key}/{source_ref}"
                    )

        claims = {str(claim["claim_id"]): claim for claim in packet["claims"]}
        existing = claims.get(claim_id)
        if existing is None:
            claim = _claim(
                claim_id,
                f"{official_name}（代表型番：{representative_model}）。{reason}",
                list(required_source_refs),
                inference=True,
            )
            packet["claims"].append(claim)
        else:
            # A10 already had a product-spec claim for Toshiba.  Retain those
            # verified facts and locators, while binding the exact audit reason
            # and treating the combined route decision as an inference.
            claim = existing
            base_statement = str(claim["statement"])
            if reason not in base_statement:
                base_statement = f"{base_statement}{reason}"
            claim.update(
                {
                    "classification": "EDITORIAL_INFERENCE",
                    "evidence_level": "D",
                    "statement": base_statement,
                    "status": "INFERENCE_FROM_BOUND_OFFICIAL_FACTS",
                }
            )
            claim["evidence_refs"] = list(
                dict.fromkeys([*claim["evidence_refs"], *required_source_refs])
            )
        claim.update(
            {
                "portfolio_candidate_disposition": "REFERENCE_ONLY",
                "portfolio_candidate_reason": reason,
                "route_article_id": route_article_id,
            }
        )
        packet["source_refs"] = list(
            dict.fromkeys([*packet["source_refs"], *claim["evidence_refs"]])
        )
        _refresh_packet_coverage(packet)

    # Stabilize source order independently of whether the tracked registry was
    # produced before or after these claims were introduced.  Evidence shared
    # with a normal/market claim keeps its established position; evidence used
    # only by a portfolio route is appended in audit order.
    for article in audit["articles"]:
        article_id = str(article["article_id"])
        packet = packets[article_id]
        portfolio_claims = [
            claim
            for claim in packet["claims"]
            if claim.get("portfolio_candidate_disposition") is not None
        ]
        portfolio_refs = {
            str(source_ref)
            for claim in portfolio_claims
            for source_ref in claim["evidence_refs"]
        }
        non_portfolio_refs = {
            str(source_ref)
            for claim in packet["claims"]
            if claim.get("portfolio_candidate_disposition") is None
            for source_ref in claim["evidence_refs"]
        }
        retained = [
            str(source_ref)
            for source_ref in packet["source_refs"]
            if source_ref not in portfolio_refs or source_ref in non_portfolio_refs
        ]
        ordered_portfolio_refs = [
            source_ref
            for candidate in article["considered_portfolio_candidates"]
            for source_ref in next(
                claim
                for claim in portfolio_claims
                if claim["claim_id"]
                == PORTFOLIO_CANDIDATE_REFERENCE_BINDINGS[
                    (article_id, str(candidate["product_id"]))
                ][0]
            )["evidence_refs"]
        ]
        packet["source_refs"] = list(
            dict.fromkeys([*retained, *ordered_portfolio_refs])
        )
        _refresh_packet_coverage(packet)

    expected_claim_ids = {
        claim_id
        for claim_id, _source_refs in PORTFOLIO_CANDIDATE_REFERENCE_BINDINGS.values()
    }
    observed = {
        str(claim["claim_id"])
        for packet in registry["source_packets"]
        for claim in packet["claims"]
        if claim.get("portfolio_candidate_disposition") is not None
    }
    if observed != expected_claim_ids:
        raise ValueError("portfolio candidate claims are not exactly and uniquely bound")


def _validate_claim_subject_contract(registry: dict[str, object]) -> None:
    portfolio = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    audit = json.loads(MARKET_AUDIT_PATH.read_text(encoding="utf-8"))
    article_products = {
        str(article["article_id"]): set(article["product_ids"])
        for article in portfolio["articles"]
    }
    for article in audit["articles"]:
        article_id = str(article["article_id"])
        if article_id not in article_products:
            raise ValueError(
                f"claim subject article is outside portfolio: {article_id}"
            )
        article_products[article_id].update(
            str(candidate["product_id"])
            for candidate in article["considered_portfolio_candidates"]
        )
    if not set(ARTICLE_LOCAL_SUBJECT_SCOPE_ADDITIONS) <= set(article_products):
        raise ValueError("claim subject scope addition references an unknown article")
    for article_id, product_ids in ARTICLE_LOCAL_SUBJECT_SCOPE_ADDITIONS.items():
        article_products[article_id].update(product_ids)
    seen_claim_ids: set[str] = set()
    for packet in registry["source_packets"]:
        article_id = str(packet["article_id"])
        if article_id not in article_products:
            raise ValueError(
                f"claim subject article is outside portfolio: {article_id}"
            )
        allowed = article_products[article_id]
        for claim in packet["claims"]:
            claim_id = str(claim["claim_id"])
            if claim_id in seen_claim_ids:
                raise ValueError(f"duplicate claim subject identity: {claim_id}")
            seen_claim_ids.add(claim_id)
            product_ids = claim.get("subject_product_ids")
            if not isinstance(product_ids, list) or any(
                not isinstance(product_id, str) or not product_id
                for product_id in product_ids
            ):
                raise ValueError(f"invalid claim subject list: {claim_id}")
            if len(product_ids) != len(set(product_ids)):
                raise ValueError(f"duplicate claim subject product: {claim_id}")
            if not set(product_ids) <= allowed:
                raise ValueError(
                    f"claim subject is outside packet product scope: {claim_id}"
                )
            expected = CLAIM_SUBJECT_PRODUCT_IDS.get(claim_id)
            if expected is None:
                raise ValueError(f"unregistered claim subject identity: {claim_id}")
            if product_ids != list(expected):
                if not product_ids and claim_id not in NON_PRODUCT_CLAIM_IDS:
                    raise ValueError(
                        f"product claim subject cannot be empty: {claim_id}"
                    )
                raise ValueError(f"claim subject product mismatch: {claim_id}")
    missing = set(CLAIM_SUBJECT_PRODUCT_IDS) - seen_claim_ids
    if missing:
        raise ValueError(f"missing claim subject identities: {sorted(missing)}")


def _validate_exact_model_claim_bindings(registry: dict[str, object]) -> None:
    """Reject sibling SKU facts bound to a selected exact-model product id."""

    sources = {
        str(source["source_ref"]): source for source in registry["sources"]
    }
    for packet in registry["source_packets"]:
        for claim in packet["claims"]:
            subject_product_ids = set(claim.get("subject_product_ids", []))
            for product_id, allowed_tokens in EXACT_MODEL_PRODUCT_TOKENS.items():
                if product_id not in subject_product_ids:
                    continue
                evidence_text = " ".join(
                    f"{sources[source_ref]['source_ref']} "
                    f"{sources[source_ref]['title']} {sources[source_ref]['url']}"
                    for source_ref in claim["evidence_refs"]
                    if source_ref in sources
                )
                observed = set(
                    EXACT_IROBOT_MODEL_RE.findall(
                        f"{claim['statement']} {evidence_text}"
                    )
                )
                if not observed <= allowed_tokens:
                    raise ValueError(
                        "claim exact model is outside subject product scope: "
                        f"{claim['claim_id']}"
                    )


def _apply_claim_subject_contract(registry: dict[str, object]) -> None:
    claims = {
        str(claim["claim_id"]): claim
        for packet in registry["source_packets"]
        for claim in packet["claims"]
    }
    if set(claims) != set(CLAIM_SUBJECT_PRODUCT_IDS):
        missing = set(CLAIM_SUBJECT_PRODUCT_IDS) - claims.keys()
        unexpected = claims.keys() - set(CLAIM_SUBJECT_PRODUCT_IDS)
        raise ValueError(
            "claim subject inventory drift: "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    for claim_id, product_ids in CLAIM_SUBJECT_PRODUCT_IDS.items():
        claims[claim_id]["subject_product_ids"] = list(product_ids)
    _validate_claim_subject_contract(registry)
    _validate_exact_model_claim_bindings(registry)


def _validate_negative_claim_contract(registry: dict[str, object]) -> None:
    claims = {
        str(claim["claim_id"]): claim
        for packet in registry["source_packets"]
        for claim in packet["claims"]
    }
    asserted: set[str] = set()
    for claim_id, claim in claims.items():
        statement = str(claim["statement"])
        for disclaimer in NEGATIVE_CLAIM_DISCLAIMERS:
            statement = statement.replace(disclaimer, "")
        if not any(marker in statement for marker in NEGATIVE_CLAIM_MARKERS):
            if "negative_claim_evidence" in claim:
                raise ValueError(
                    f"stale negative-claim evidence attestation: {claim_id}"
                )
            continue
        asserted.add(claim_id)
        configured = NEGATIVE_CLAIM_EVIDENCE.get(claim_id)
        if configured is None:
            raise ValueError(
                "negative claim lacks explicit official text/table/manual evidence: "
                f"{claim_id}"
            )
        mode, required_refs = configured
        if mode not in {
            "EXPLICIT_OFFICIAL_TEXT",
            "OFFICIAL_COMPARISON_TABLE",
            "OFFICIAL_PRODUCT_MANUAL",
        }:
            raise ValueError(f"invalid negative-claim evidence mode: {claim_id}/{mode}")
        if not set(required_refs) <= set(claim["evidence_refs"]):
            raise ValueError(
                f"negative claim is not bound to attested evidence: {claim_id}"
            )
        # Reinsert the generated attestation after all semantic appendices so
        # rebuilding from a previously generated registry preserves byte order.
        claim.pop("negative_claim_evidence", None)
        claim["negative_claim_evidence"] = {
            "mode": mode,
            "source_refs": list(required_refs),
            "page_omission_is_not_evidence": True,
        }
    if asserted != set(NEGATIVE_CLAIM_EVIDENCE):
        raise ValueError(
            "negative-claim evidence inventory drift: "
            f"asserted={sorted(asserted)}, configured={sorted(NEGATIVE_CLAIM_EVIDENCE)}"
        )


def _apply_product_specific_recall_query_gate(
    registry: dict[str, object],
) -> None:
    """Declare article requirements for the central, product-unique receipts.

    Receipts and completion status never live in article claims: products used
    by more than one article would otherwise duplicate or contradict the same
    observation.  The selection audit loads the central owner document and
    derives each product status.  General safety guidance is not a query receipt.
    """

    audit = json.loads(MARKET_AUDIT_PATH.read_text(encoding="utf-8"))
    selected_by_article = {
        str(article["article_id"]): tuple(
            dict.fromkeys(str(value) for value in article["selected_product_ids"])
        )
        for article in audit["articles"]
    }
    packet_by_article = {
        str(packet["article_id"]): packet for packet in registry["source_packets"]
    }
    if set(selected_by_article) != set(packet_by_article):
        raise ValueError("recall-query article inventory does not match source packets")
    for article_id, product_ids in selected_by_article.items():
        packet = packet_by_article[article_id]
        if not product_ids:
            for claim in packet["claims"]:
                claim.pop("product_specific_recall_query_gate", None)
            continue
        product_claims = [
            claim for claim in packet["claims"] if claim.get("subject_product_ids")
        ]
        covered = {
            str(product_id)
            for claim in product_claims
            for product_id in claim["subject_product_ids"]
        }
        if not set(product_ids) <= covered:
            raise ValueError(
                f"selected product lacks a product-scoped source claim: {article_id}"
            )
        if not product_claims:
            raise ValueError(f"recall-query gate has no owner claim: {article_id}")
        owner_claim = product_claims[0]
        owner_claim["product_specific_recall_query_gate"] = {
            "schema": "PRODUCT_SPECIFIC_RECALL_QUERY_REQUIREMENT_V2",
            "required_product_ids": list(product_ids),
            "required_authority_kinds": list(
                PRODUCT_SAFETY_REQUIRED_AUTHORITIES
            ),
            "receipt_document_ref": PRODUCT_SAFETY_RECEIPT_DOCUMENT_REF,
            "receipt_document_schema": PRODUCT_SAFETY_RECEIPT_SCHEMA,
            "coverage_caveat": (
                "NONE_FOUNDは、receiptに記録した公式source・型番token・query・"
                "確認日時の範囲だけを示し、安全情報が存在しないことを一般に"
                "証明しません。"
            ),
            "general_safety_guidance_is_not_a_receipt": True,
        }


def _validate_power_station_due_diligence_contract(
    registry: dict[str, object],
) -> None:
    sources = {
        str(source["source_ref"]): source for source in registry["sources"]
    }
    packets = {
        str(packet["article_id"]): packet for packet in registry["source_packets"]
    }
    observed_pairs: set[tuple[str, str]] = set()
    observed_products: set[str] = set()
    for group in POWER_STATION_DUE_DILIGENCE_GROUPS:
        article_id = str(group["article_id"])
        product_id = str(group["product_id"])
        key = (article_id, product_id)
        if key in observed_pairs:
            raise ValueError(f"duplicate power-station due-diligence group: {key}")
        observed_pairs.add(key)
        observed_products.add(product_id)

        packet = packets.get(article_id)
        if packet is None:
            raise ValueError(f"missing power-station due-diligence packet: {article_id}")
        claims = {
            str(claim["claim_id"]): claim for claim in packet["claims"]
        }
        claim_ids = tuple(str(value) for value in group["claim_ids"])
        if any(claim_id not in claims for claim_id in claim_ids):
            raise ValueError(
                f"missing power-station due-diligence claim group: {key}"
            )
        group_claims = [claims[claim_id] for claim_id in claim_ids]
        if any(
            product_id not in claim["subject_product_ids"]
            for claim in group_claims
        ):
            raise ValueError(
                f"power-station due-diligence claim subject mismatch: {key}"
            )

        evidence_refs = {
            str(source_ref)
            for claim in group_claims
            for source_ref in claim["evidence_refs"]
        }
        required_refs = {str(value) for value in group["required_source_refs"]}
        if not required_refs <= evidence_refs:
            raise ValueError(
                f"power-station due-diligence evidence is incomplete: {key}"
            )
        if any(
            source_ref not in sources
            or sources[source_ref]["authority"] != "MANUFACTURER_OFFICIAL"
            for source_ref in required_refs
        ):
            raise ValueError(
                f"power-station due-diligence evidence is not manufacturer official: {key}"
            )

        combined_statement = " ".join(
            str(claim["statement"]) for claim in group_claims
        )
        missing_fragments = [
            str(fragment)
            for fragment in group["required_statement_fragments"]
            if str(fragment) not in combined_statement
        ]
        if missing_fragments:
            raise ValueError(
                "power-station due-diligence statement is incomplete: "
                f"{key}/{missing_fragments}"
            )

        recall_gates = [
            claim["product_specific_recall_query_gate"]
            for claim in packet["claims"]
            if "product_specific_recall_query_gate" in claim
        ]
        if len(recall_gates) != 1:
            raise ValueError(
                f"power-station recall gate is not uniquely bound: {article_id}"
            )
        recall_gate = recall_gates[0]
        if (
            set(recall_gate)
            != {
                "schema",
                "required_product_ids",
                "required_authority_kinds",
                "receipt_document_ref",
                "receipt_document_schema",
                "coverage_caveat",
                "general_safety_guidance_is_not_a_receipt",
            }
            or product_id not in recall_gate["required_product_ids"]
            or recall_gate["receipt_document_ref"]
            != PRODUCT_SAFETY_RECEIPT_DOCUMENT_REF
            or recall_gate["receipt_document_schema"]
            != PRODUCT_SAFETY_RECEIPT_SCHEMA
            or tuple(recall_gate["required_authority_kinds"])
            != PRODUCT_SAFETY_REQUIRED_AUTHORITIES
            or recall_gate["general_safety_guidance_is_not_a_receipt"] is not True
        ):
            raise ValueError(
                f"power-station product-specific recall gate is fail-open: {key}"
            )

    expected_products = {
        "PRD-ANKER-SOLIX-C300",
        "PRD-BLUETTI-AORA30-V2",
        "PRD-JACKERY-500-NEW",
        "PRD-ANKER-SOLIX-C800",
        "PRD-DJI-POWER-1000-V2",
        "PRD-BLUETTI-AORA100-V2",
        "PRD-ANKER-SOLIX-C800-PLUS",
        "PRD-ANKER-SOLIX-C1000",
        "PRD-ANKER-SOLIX-C1000-GEN2",
    }
    if observed_products != expected_products or len(observed_pairs) != 10:
        raise ValueError("power-station due-diligence inventory drift")


def _normalize_packet_source_ref_order(registry: dict[str, object]) -> None:
    """Derive packet source order from final claim order, not prior output.

    Semantic evidence is appended after market/portfolio projections.  Keeping
    the prior generated packet order made a first generation append those refs
    at the end while a second generation retained them earlier.  The closed
    packet contract requires every source to own at least one claim, so the
    final claim/evidence traversal is both meaningful and byte-idempotent.
    """

    for packet in registry["source_packets"]:
        ordered_refs = list(
            dict.fromkeys(
                str(source_ref)
                for claim in packet["claims"]
                for source_ref in claim["evidence_refs"]
            )
        )
        if set(ordered_refs) != set(packet["source_refs"]):
            raise ValueError(
                "packet source inventory does not match claim evidence: "
                f"{packet['article_id']}"
            )
        packet["source_refs"] = ordered_refs


def _apply_reader_semantic_appendices(registry: dict[str, object]) -> None:
    claims = {
        str(claim["claim_id"]): claim
        for packet in registry["source_packets"]
        for claim in packet["claims"]
    }
    missing = set(READER_SEMANTIC_APPENDICES) - claims.keys()
    if missing:
        raise ValueError(f"missing reader semantic claims: {sorted(missing)}")
    for claim_id, appendix in READER_SEMANTIC_APPENDICES.items():
        statement = str(claims[claim_id]["statement"])
        claims[claim_id]["statement"] = statement + appendix
    missing_field_claims = set(READER_SEMANTIC_FIELD_ADDITIONS) - claims.keys()
    if missing_field_claims:
        raise ValueError(
            f"missing reader semantic field claims: {sorted(missing_field_claims)}"
        )
    for claim_id, additions in READER_SEMANTIC_FIELD_ADDITIONS.items():
        claim = claims[claim_id]
        for field, value in additions.items():
            claim[field] = dict(value)
    packets_by_claim = {
        str(claim["claim_id"]): packet
        for packet in registry["source_packets"]
        for claim in packet["claims"]
    }
    missing_evidence_claims = set(READER_SEMANTIC_EVIDENCE_ADDITIONS) - claims.keys()
    if missing_evidence_claims:
        raise ValueError(
            f"missing reader semantic evidence claims: {sorted(missing_evidence_claims)}"
        )
    for claim_id, source_refs in READER_SEMANTIC_EVIDENCE_ADDITIONS.items():
        claim = claims[claim_id]
        claim["evidence_refs"] = list(
            dict.fromkeys([*claim["evidence_refs"], *source_refs])
        )
        packet = packets_by_claim[claim_id]
        packet["source_refs"] = list(
            dict.fromkeys([*packet["source_refs"], *source_refs])
        )
        _refresh_packet_coverage(packet)


def _normalize_generated_claim_field_order(registry: dict[str, object]) -> None:
    """Keep generated semantic fields byte-stable across rebuilds.

    First-five claims are upgraded in place while portfolio claims are rebuilt.
    Reinsert the common generated fields once, after every appendix, so a
    previously generated registry cannot rotate JSON member order.
    """

    generated_fields = (
        "subject_product_ids",
        "negative_claim_evidence",
        "product_specific_recall_query_gate",
        "manufacturer_sales_state",
    )
    for packet in registry["source_packets"]:
        for claim in packet["claims"]:
            values = {
                field: claim.pop(field)
                for field in generated_fields
                if field in claim
            }
            for field in generated_fields:
                if field in values:
                    claim[field] = values[field]


def _documents() -> tuple[bytes, bytes]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    locator = json.loads(LOCATOR_PATH.read_text(encoding="utf-8"))

    new_refs = {str(source["source_ref"]) for source in NEW_SOURCES}
    existing_sources = {
        str(source["source_ref"]): source for source in registry["sources"]
    }
    generated_sources: list[dict[str, object]] = []
    for source in NEW_SOURCES:
        generated = dict(source)
        existing = existing_sources.get(str(source["source_ref"]))
        if existing is not None:
            # An owner-recorded observation date is evidence, not build metadata.
            # Rebuilding locators or hashes must never advance or backdate it.
            generated["retrieved_on"] = existing["retrieved_on"]
        generated_sources.append(generated)
    registry["generated_on"] = RETRIEVED_ON
    replaced_source_refs = new_refs | RETIRED_SOURCE_REFS
    registry["sources"] = [
        source
        for source in registry["sources"]
        if source["source_ref"] not in replaced_source_refs
    ] + generated_sources
    overridden_source_refs: set[str] = set()
    for source in registry["sources"]:
        source_ref = str(source["source_ref"])
        metadata = SOURCE_METADATA_OVERRIDES.get(source_ref)
        if metadata is None:
            continue
        source.update(metadata)
        overridden_source_refs.add(source_ref)
    if overridden_source_refs != set(SOURCE_METADATA_OVERRIDES):
        missing = set(SOURCE_METADATA_OVERRIDES) - overridden_source_refs
        raise ValueError(f"missing source metadata override targets: {sorted(missing)}")
    observed_source_refs: set[str] = set()
    for source in registry["sources"]:
        source_ref = str(source["source_ref"])
        if source_ref in SOURCE_RETRIEVED_ON_OVERRIDES:
            source["retrieved_on"] = SOURCE_RETRIEVED_ON_OVERRIDES[source_ref]
            observed_source_refs.add(source_ref)
    if observed_source_refs != set(SOURCE_RETRIEVED_ON_OVERRIDES):
        missing = set(SOURCE_RETRIEVED_ON_OVERRIDES) - observed_source_refs
        raise ValueError(
            f"missing source observation override targets: {sorted(missing)}"
        )
    registry["source_packets"] = [
        packet
        for packet in registry["source_packets"]
        if packet["article_id"] not in PORTFOLIO_ARTICLE_IDS
    ] + deepcopy(list(NEW_PACKETS))

    _apply_first_five_product_replacements(registry)
    _apply_first_five_dimension_contract(registry)
    _apply_market_candidate_claims(registry)
    _validate_dimension_contract(registry)
    _apply_portfolio_candidate_claims(registry)
    _apply_reader_semantic_appendices(registry)
    _validate_negative_claim_contract(registry)
    _apply_claim_subject_contract(registry)
    _apply_product_specific_recall_query_gate(registry)
    _validate_power_station_due_diligence_contract(registry)
    _normalize_packet_source_ref_order(registry)
    _normalize_generated_claim_field_order(registry)

    all_claims = [
        claim for packet in registry["source_packets"] for claim in packet["claims"]
    ]
    for packet in registry["source_packets"]:
        packet["fact_packet_sha256"] = _packet_hash(packet)
    for source in registry["sources"]:
        bound = [
            claim
            for claim in all_claims
            if source["source_ref"] in claim["evidence_refs"]
        ]
        source["immutable_capture_sha256"] = _source_capture_hash(source, bound)
    for source in registry["policy_sources"]:
        source["immutable_capture_sha256"] = _source_capture_hash(source, [])

    existing_locator_refs = {
        str(source["source_ref"]) for source in locator["sources"]
    }
    for source_ref, locator_seed in POLICY_SOURCE_LOCATORS.items():
        if source_ref not in existing_locator_refs:
            locator["sources"].append(locator_seed)

    locator_by_ref = {source["source_ref"]: source for source in locator["sources"]}
    for source_ref, template_claim in REUSED_FRAGMENT_SOURCE_CLAIMS.items():
        entry = locator_by_ref[source_ref]
        template = next(
            item for item in entry["locators"] if item["claim_id"] == template_claim
        )
        NEW_SOURCE_FRAGMENTS.setdefault(
            source_ref, tuple(template["exact_utf8_fragments"])
        )

    claims_by_source: dict[str, list[str]] = {
        str(source["source_ref"]): [] for source in registry["sources"]
    }
    for packet in registry["source_packets"]:
        for claim in packet["claims"]:
            for source_ref in claim["evidence_refs"]:
                claims_by_source[source_ref].append(claim["claim_id"])

    new_claim_ids = {
        claim["claim_id"] for packet in NEW_PACKETS for claim in packet["claims"]
    }
    first_five_additional_ids = {
        str(claim["claim_id"])
        for claims in FIRST_FIVE_ADDITIONAL_CLAIMS.values()
        for claim in claims
    }
    additional_claims_by_source: dict[str, list[str]] = {}
    for claims in FIRST_FIVE_ADDITIONAL_CLAIMS.values():
        for claim in claims:
            for source_ref in claim["evidence_refs"]:
                additional_claims_by_source.setdefault(str(source_ref), []).append(
                    str(claim["claim_id"])
                )
    for source_ref, claim_ids in additional_claims_by_source.items():
        entry = locator_by_ref.get(source_ref)
        # Brand-new sources are materialized below from NEW_SOURCE_FRAGMENTS;
        # only reused sources need a pre-existing locator template here.
        if entry is None and source_ref in NEW_SOURCE_FRAGMENTS:
            continue
        if entry is None:
            raise ValueError(f"missing locator template for {source_ref}")
        existing_locators = list(entry.get("locators", []))
        template_fragments = (
            tuple(existing_locators[0]["exact_utf8_fragments"])
            if existing_locators
            else ()
        )
        if not template_fragments and any(
            (source_ref, claim_id) not in CLAIM_FRAGMENT_OVERRIDES
            for claim_id in claim_ids
        ):
            raise ValueError(f"missing locator template for {source_ref}")
        entry["locators"] = [
            item
            for item in entry["locators"]
            if item["claim_id"] not in first_five_additional_ids
        ] + [
            {
                "claim_id": claim_id,
                "exact_utf8_fragments": list(
                    CLAIM_FRAGMENT_OVERRIDES.get(
                        (source_ref, claim_id),
                        template_fragments,
                    )
                ),
            }
            for claim_id in claim_ids
        ]
    for source_ref in REUSED_FRAGMENT_SOURCE_CLAIMS:
        entry = locator_by_ref[source_ref]
        entry["locators"] = [
            item for item in entry["locators"] if item["claim_id"] not in new_claim_ids
        ]
        fragments = list(NEW_SOURCE_FRAGMENTS[source_ref])
        for claim_id in claims_by_source[source_ref]:
            if claim_id in new_claim_ids:
                entry["locators"].append(
                    {"claim_id": claim_id, "exact_utf8_fragments": fragments}
                )

    # A product replacement may deliberately retain the retired product's
    # official page as exclusion evidence while changing the claim id.  Keep
    # those existing source entries, but reconcile their locators to the
    # current packet graph.  Leaving an obsolete locator behind makes the
    # capture plan ambiguous; silently dropping the new exclusion claim would
    # make the decision rationale unverifiable.
    for source_ref, desired_claim_ids in claims_by_source.items():
        if source_ref in new_refs:
            continue
        entry = locator_by_ref.get(source_ref)
        if entry is None:
            raise ValueError(f"missing locator source for {source_ref}")
        existing_locators = list(entry.get("locators", []))
        templates = {str(item["claim_id"]): item for item in existing_locators}
        if len(templates) != len(existing_locators):
            raise ValueError(f"duplicate locator claim for {source_ref}")
        fallback_fragments = (
            tuple(existing_locators[0]["exact_utf8_fragments"])
            if existing_locators
            else ()
        )
        reconciled: list[dict[str, object]] = []
        for claim_id in desired_claim_ids:
            existing = templates.get(claim_id)
            override_fragments = CLAIM_FRAGMENT_OVERRIDES.get(
                (source_ref, claim_id)
            )
            if existing is not None and override_fragments is None:
                reconciled.append(existing)
                continue
            fragments = override_fragments or fallback_fragments
            if not fragments:
                raise ValueError(
                    f"missing locator fragments for {source_ref}/{claim_id}"
                )
            generated_locator: dict[str, object] = {
                "claim_id": claim_id,
                "exact_utf8_fragments": list(fragments),
            }
            if source_ref in PDF_SOURCE_METADATA:
                generated_locator["reviewed_page_number"] = (
                    PDF_CLAIM_REVIEWED_PAGES.get(
                        (source_ref, claim_id), PDF_SOURCE_METADATA[source_ref][1]
                    )
                )
            reconciled.append(generated_locator)
        entry["locators"] = reconciled
        if desired_claim_ids:
            entry["locator_status"] = "READY"
        else:
            registry_source = next(
                source
                for source in registry["sources"]
                if source["source_ref"] == source_ref
            )
            if registry_source.get("review_body_excluded_from_claim_evidence") is not True:
                raise ValueError(f"unbound source is not explicitly excluded: {source_ref}")
            entry["locator_status"] = "LOCATORS_PENDING"

    locator["sources"] = [
        source
        for source in locator["sources"]
        if source["source_ref"] not in replaced_source_refs
    ]
    for source in NEW_SOURCES:
        source_ref = str(source["source_ref"])
        entry: dict[str, object] = {
            "source_ref": source_ref,
            "charset": None if source_ref in PDF_SOURCE_METADATA else "utf-8",
            "locator_status": "READY",
            "locators": [
                {
                    "claim_id": claim_id,
                    "exact_utf8_fragments": list(
                        CLAIM_FRAGMENT_OVERRIDES.get(
                            (source_ref, claim_id),
                            NEW_SOURCE_FRAGMENTS[source_ref],
                        )
                    ),
                }
                for claim_id in claims_by_source[source_ref]
            ],
        }
        if source_ref in PDF_SOURCE_METADATA:
            entry["locator_mode"] = "PINNED_PDF_BODY_AND_REVIEWED_PAGE_TEXT"
            entry["expected_body_sha256"] = PDF_SOURCE_METADATA[source_ref][0]
            for item in entry["locators"]:
                item["reviewed_page_number"] = PDF_CLAIM_REVIEWED_PAGES.get(
                    (source_ref, str(item["claim_id"])),
                    PDF_SOURCE_METADATA[source_ref][1],
                )
        locator["sources"].append(entry)

    locator_by_ref = {
        str(source["source_ref"]): source for source in locator["sources"]
    }
    for (source_ref, claim_id), additions in LATER_CLAIM_FRAGMENT_ADDITIONS.items():
        entries = [
            item
            for item in locator_by_ref[source_ref]["locators"]
            if item["claim_id"] == claim_id
        ]
        if len(entries) != 1:
            raise ValueError(
                f"expected one later-claim locator for {source_ref}/{claim_id}"
            )
        fragments = entries[0]["exact_utf8_fragments"]
        for fragment in additions:
            if fragment not in fragments:
                fragments.append(fragment)

    # Reused sources retain earlier fragments. Replace only the purchase/title
    # fragments re-reviewed against the 2026-09-05 official captures, including
    # inherited conditional-choice locators, so old markup cannot survive an
    # additive refresh. All specification and warranty fragments stay intact.
    for source_ref in (
        "SRC-ANKER-SOLIX-C300",
        "SRC-ANKER-SOLIX-C800",
        "SRC-ANKER-SOLIX-C800-PLUS",
        "SRC-ANKER-SOLIX-C1000",
        "SRC-ANKER-SOLIX-C1000-GEN2",
    ):
        replacements = {
            '<button type="submit" name="add" aria-label="カートに入れる" id="cafe-purchase-button"': ANKER_STOCK_BOUND_PURCHASE_FRAGMENT,
        }
        if source_ref == "SRC-ANKER-SOLIX-C800":
            replacements['aria-label="カートに入れる"'] = (
                ANKER_STOCK_BOUND_PURCHASE_FRAGMENT
            )
        if source_ref in {"SRC-ANKER-SOLIX-C800-PLUS", "SRC-ANKER-SOLIX-C1000"}:
            name = (
                "Anker Solix C800 Plus Portable Power Station"
                if source_ref == "SRC-ANKER-SOLIX-C800-PLUS"
                else "Anker Solix C1000 Portable Power Station"
            )
            replacements[
                f'<meta property="og:title" content="{name} | ポータブル電源の製品情報">'
            ] = f'<meta property="og:title" content="{name} | リン酸鉄ポータブル電源の製品情報">'
        for item in locator_by_ref[source_ref]["locators"]:
            item["exact_utf8_fragments"] = list(
                dict.fromkeys(
                    replacements.get(fragment, fragment)
                    for fragment in item["exact_utf8_fragments"]
                )
            )

    used_product_source_refs = {
        str(source_ref)
        for packet in registry["source_packets"]
        for source_ref in packet["source_refs"]
    }
    registry["sources"] = [
        source
        for source in registry["sources"]
        if source["source_ref"] in used_product_source_refs
    ]
    used_locator_source_refs = used_product_source_refs | {
        str(source["source_ref"]) for source in registry["policy_sources"]
    }
    locator["sources"] = [
        source
        for source in locator["sources"]
        if source["source_ref"] in used_locator_source_refs
    ]

    locator["generated_on"] = RETRIEVED_ON
    locator["locator_policy"] = {
        **locator["locator_policy"],
        "pdf_fragment_match": "PINNED_BODY_SHA256_PLUS_REVIEWED_EXTRACTED_PAGE_TEXT",
    }
    _validate_locator_text_fragments(locator)
    locator["source_registry_sha256"] = _canonical_sha256(registry)

    return (
        (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode(),
        (json.dumps(locator, ensure_ascii=False, indent=2) + "\n").encode(),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build deterministic ten-article official source packets."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when either tracked output differs from the deterministic build",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    registry_raw, locator_raw = _documents()
    outputs = ((REGISTRY_PATH, registry_raw), (LOCATOR_PATH, locator_raw))
    if args.check:
        if any(path.read_bytes() != payload for path, payload in outputs):
            raise SystemExit("ST-1704 portfolio source packet drift")
        return
    for path, payload in outputs:
        path.write_bytes(payload)


if __name__ == "__main__":
    main()
