#!/usr/bin/env python3
"""Validate the closed reader-unit to source-claim ledger for ten articles.

The ledger is an authored review artifact, not generated output.  This owner
extracts every reader-visible text/accessibility unit from the final WordPress
fixtures and refuses any addition, removal, relocation, or reclassification
that has not been reviewed in the ledger.  ``--skeleton`` only prints an
unclassified proposal to stdout; it never writes or updates the tracked ledger.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import stat
import sys
from typing import Final, NoReturn, cast
import unicodedata
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.application.editorial.product_safety_manufacturer_capture import (  # noqa: E402
    EMPTY_EVIDENCE_RELATIVE_PATH as PRODUCT_SAFETY_MANUFACTURER_EMPTY_RELATIVE,
    PLAN_RELATIVE_PATH as PRODUCT_SAFETY_MANUFACTURER_PLAN_RELATIVE,
)
from raos.application.editorial.product_safety_query_capture import (  # noqa: E402
    QUERY_PLAN_RELATIVE_PATH as PRODUCT_SAFETY_ADMIN_PLAN_RELATIVE,
)
from raos.application.editorial.product_safety_receipts import (  # noqa: E402
    ProductSafetyOfficialSource,
    ProductSafetyReceiptFailure,
    ProductSafetyRequirement,
    ProductSafetySourceRegistryContext,
    evaluate_product_safety_receipts,
    load_product_safety_receipt_audit,
)

UTC: Final = timezone.utc
SLICE_PATH: Final = Path("changes/st-1704/self-hosted-editorial-pilot-v1")
LEDGER_RELATIVE: Final = SLICE_PATH / "sources/reader-claim-bindings.v1.json"
PORTFOLIO_RELATIVE: Final = Path(
    "changes/editorial-portfolio-v2/editorial-portfolio.v2.json"
)
REGISTRY_RELATIVE: Final = SLICE_PATH / "sources/source-registry.v1.json"
LOCATOR_RELATIVE: Final = SLICE_PATH / "sources/source-locator-contract.v1.json"
SALES_STATE_RELATIVE: Final = Path(
    "changes/editorial-portfolio-v2/manufacturer-sales-state.v1.json"
)
MARKET_AUDIT_RELATIVE: Final = Path(
    "changes/editorial-portfolio-v3/market-candidate-audit.v1.json"
)
PRODUCT_SAFETY_RECEIPT_RELATIVE: Final = (
    SLICE_PATH / "sources/product-safety-query-receipts.v1.json"
)
PRODUCT_SAFETY_RECEIPT_SCHEMA: Final = "RAOS_PRODUCT_SAFETY_QUERY_RECEIPTS_V1"
PRODUCT_SAFETY_REQUIRED_AUTHORITIES: Final = [
    "MANUFACTURER_OFFICIAL",
    "JAPAN_ADMINISTRATIVE_OFFICIAL",
]
PRODUCT_SAFETY_RECEIPT_VERSION: Final = "1.0.0"
PRODUCT_SAFETY_MAX_AGE: Final = timedelta(days=30)
PRODUCT_SAFETY_MAX_FUTURE_SKEW: Final = timedelta(minutes=5)
PRODUCT_SAFETY_RECEIPT_HASH_FIELDS: Final = (
    "product_id",
    "authority_kind",
    "model_tokens",
    "query_terms",
    "official_source_ref",
    "official_source_url",
    "checked_at_utc",
    "result",
    "matched_notice_ids",
    "capture_sha256",
    "coverage_caveat",
)
PRODUCT_SAFETY_REQUIRED_CAVEAT: Final = (
    "この結果は、記録した公式source・型番token・query・確認日時の範囲だけを示し、"
    "安全情報が存在しないことを一般に証明しません。"
)
MARKET_AUDIT_SCHEMA: Final = "RAOS_EDITORIAL_MARKET_CANDIDATE_AUDIT_V1"
MARKET_AUDIT_VERSION: Final = "1.0.0"
MARKET_REQUIRED_AXES: Final = (
    "use_case_fit",
    "safety",
    "dimensions",
    "performance",
    "warranty_and_support",
    "maintainability",
    "primary_source_confidence",
)
DECISION_GATE_SCHEMA: Final = "RAOS_READER_DECISION_GATE_V1"
DECISION_GATE_AXES: Final = (
    "safety",
    "warranty_and_support",
    "maintainability",
)
DECISION_GATE_STATES: Final = frozenset({"ELIGIBLE", "BLOCKED"})
PRODUCT_SAFETY_STATUSES: Final = frozenset(
    {
        "COMPLETE_NONE_FOUND",
        "BLOCKED_MATCH_FOUND",
        "BLOCKED_AMBIGUOUS_RESULT",
        "BLOCKED_STALE_RECEIPT",
        "BLOCKED_MISSING_RECEIPT",
    }
)
LEGACY_CONTENT_RELATIVE: Final = SLICE_PATH / "content/articles.v1.json"
POSTS_RELATIVE: Final = Path("changes/wordpress-local-preview-v1/fixtures/posts.json")

ARTICLE_IDS: Final = (
    "st1703-first-suitcase-comparison",
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
    "carry-on-suitcase-under-100-seats",
    "lightweight-carry-on-suitcase-under-3kg",
    "front-open-carry-on-suitcase-with-stopper",
    "roomba-mini-vs-switchbot-k11-pro",
    "solota-vs-rakua-mini-plus",
)
ARTICLE_DISPLAY_ALIASES: Final = {
    "st1703-first-suitcase-comparison": {
        # The primary source and reader copy both use the Romanized short
        # family name after the exact product identity is introduced.  Keep it
        # article-local so the comparison winner in phrases such as
        # ``Tri-Airが3モデルで最軽量`` is attributed to 01541 rather than to
        # the nearest unrelated model name earlier in the same sentence.
        "PRD-PROTECA-TRI-AIR-01541": ("Tri-Air",),
    },
    "st1704-compact-robot-vacuum-shortlist": {
        # Introductory comparison prose shortens the exact AutoEmpty product
        # identity after it has been introduced.  Without this local alias,
        # the Mini station's 17.8 cm depth could be misattributed to the next
        # named product in the coordinated sentence.
        "PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY": ("Roomba Mini",),
    },
    "lightweight-carry-on-suitcase-under-3kg": {
        # The FAQ and running copy deliberately shorten the full display name
        # to APPLITE after the comparison set has been declared.
        "PRD-PROTECA-TRI-AIR-01541": ("Tri-Air",),
        "PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002": ("APPLITE",),
        "PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549": ("C-Lite",),
    },
}
ARTICLE_EXTERNAL_DISPLAY_ALIASES: Final = {
    "st1704-compact-robot-vacuum-shortlist": {
        "EXT-SWITCHBOT-K10-PRO-COMBO": ("K10+ Pro Combo",),
    },
    "st1704-countertop-dishwasher-for-small-households": {
        "EXT-PANASONIC-NP-TMLK1": ("SOLOTA", "NP-TMLK1"),
    },
    "roomba-mini-vs-switchbot-k11-pro": {
        "EXT-IROBOT-ROOMBA-MINI-AUTOEMPTY-F155260": ("F155260",),
    },
    "solota-vs-rakua-mini-plus": {
        "EXT-PANASONIC-SOLOTA-NP-TMLK1-K": (
            "SOLOTA",
            "NP-TMLK1",
            "NP-TMLK1-K",
        ),
        "EXT-THANKO-RAKUA-MINI-PLUS": ("ラクアmini Plus",),
    },
}
ARTICLE_LOCAL_SUBJECT_SCOPE_ADDITIONS: Final[dict[str, tuple[str, ...]]] = {}
METADATA_SUBJECT_OVERRIDES: Final[dict[tuple[str, str], tuple[str, ...]]] = {}
MIXED_DISH_SELECTION_REFERENCE_TEXTS: Final = frozenset(
    {
        "比較範囲:タンク給水対応の4モデル。 公式仕様を比較する4候補を、"
        "本体・扉開放寸法、標準収納容量、使用水量、給水・乾燥方式で比較し、"
        "販売状態未確認のSOLOTAは仕様参考に限定しています。",
        "公式仕様を比較する4候補を設置寸法と食器点数で選び、SOLOTAは仕様参考に限定する",
    }
)
DISH_SELECTED_SUBJECTS: Final = (
    "PRD-SIROCA-SS-M171",
    "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
    "PRD-SIROCA-SS-MA251",
    "PRD-TOSHIBA-DWS-33B-W",
)

READER_UNIT_SUBJECT_OVERRIDES: Final = {
    **{
        ("st1704-countertop-dishwasher-for-small-households", text): (
            *DISH_SELECTED_SUBJECTS,
            "EXT-PANASONIC-NP-TMLK1",
        )
        for text in MIXED_DISH_SELECTION_REFERENCE_TEXTS
    },
    (
        "st1704-compact-robot-vacuum-shortlist",
        "K10+ Pro Comboはコードレス掃除機統合という別用途で、ステーション寸法の軸も"
        "未確認のため現行4候補から除外",
    ): (
        "PRD-EUFY-AUTOEMPTY-C10-T2292",
        "PRD-SWITCHBOT-K11-PRO",
        "PRD-ECOVACS-DEEBOT-MINI2",
        "PRD-IROBOT-ROOMBA-PLUS-515-COMBO",
    ),
    (
        "st1704-countertop-dishwasher-for-small-households",
        "Panasonic NP-TMLK1 仕様・詳細情報",
    ): ("EXT-PANASONIC-NP-TMLK1",),
    (
        "st1704-anker-solix-c300-c800-c1000-differences",
        "停電時の正確な切り替え時間は、公式ページ内に約0.01秒と"
        "約0.02秒の記載が併存するため比較軸から外しています",
    ): (
        "PRD-ANKER-SOLIX-C1000",
        "PRD-ANKER-SOLIX-C1000-GEN2",
    ),
    (
        "front-open-carry-on-suitcase-with-stopper",
        "Q 60570のPC収納なら、13インチ端末は必ず入りますか。",
    ): ("PRD-BERMAS-INTER-CITY-III-60570",),
}

# A small number of coordinated headings put the governing identity after a
# value (or explicitly contrast a named baseline before the value).  These
# exact, article-local overrides are safer than a broad nearest-name heuristic
# that could lend a neighbouring product's fact to the wrong model.
LOCAL_ASSERTION_SUBJECT_OVERRIDES: Final = {
    **{
        (text, token, 0): DISH_SELECTED_SUBJECTS
        for text in MIXED_DISH_SELECTION_REFERENCE_TEXTS
        for token in ("4候補", "4モデル")
    },
    (
        "比較表に含めなかった理由:2026年9月1日に公式画面を再取得すると、"
        "青TDWS25SBLと赤TDWS25SRDの各選択肢は、いずれも『再入荷(予約開始)通知』"
        "と表示されました。比較表にはTK-MDW22Wを残し、色展開、ダブルノズル、"
        "24か月保証、ポンプ対応を優先する場合は再入荷後に型番・JANを改めて"
        "照合します。乾燥方式が熱風から温風へ変わるため、後継・上位・性能向上とは"
        "扱いません。",
        "再入荷(予約開始)通知",
        0,
    ): ("EXT-THANKO-RAKUA-MINI-COLOR",),
    (
        "K10+ Pro Comboはコードレス掃除機統合という別用途で、ステーション寸法の軸も"
        "未確認のため現行4候補から除外",
        "4候補",
        0,
    ): (
        "PRD-EUFY-AUTOEMPTY-C10-T2292",
        "PRD-SWITCHBOT-K11-PRO",
        "PRD-ECOVACS-DEEBOT-MINI2",
        "PRD-IROBOT-ROOMBA-PLUS-515-COMBO",
    ),
    (
        "工事不要のタンク式食洗機4候補を公式仕様で比較。標準食器11〜18点の"
        "現行モデルを、設置寸法、使用水量、給水・乾燥方式で選び分けます。"
        "SOLOTA NP-TMLK1は販売状態未確認の仕様参考にとどめます。",
        "11〜18点",
        0,
    ): (
        "PRD-SIROCA-SS-M171",
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-MA251",
        "PRD-TOSHIBA-DWS-33B-W",
    ),
    (
        "工事不要のタンク式食洗機4候補を公式仕様で比較。標準食器11〜18点の"
        "現行モデルを、設置寸法、使用水量、給水・乾燥方式で選び分けます。"
        "SOLOTA NP-TMLK1は販売状態未確認の仕様参考にとどめます。",
        "現行モデル",
        0,
    ): (
        "PRD-SIROCA-SS-M171",
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-MA251",
        "PRD-TOSHIBA-DWS-33B-W",
    ),
    (
        "標準食器点数は各社の想定した食器構成による参考値で、自宅の皿や調理器具が"
        "必ず収まる保証ではありません。現行4候補は、幅を抑えつつ11〜12点を想定するラクアmini、"
        "SS-M171を16点と2WAY給水、通常商品SS-MA251を16点とオートオープン、"
        "DWS-33Bを18点まとめ洗いの条件に分け、一度に洗う実物と開扉時を含む設置寸法で"
        "絞ります。SOLOTA NP-TMLK1-Kは販売状態未確認のため、仕様参考にとどめます。",
        "現行",
        0,
    ): (
        "PRD-SIROCA-SS-M171",
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-MA251",
        "PRD-TOSHIBA-DWS-33B-W",
    ),
    (
        "標準食器点数は各社の想定した食器構成による参考値で、自宅の皿や調理器具が"
        "必ず収まる保証ではありません。現行4候補は、幅を抑えつつ11〜12点を想定するラクアmini、"
        "16点と2WAY給水のSS-M171、16点とオートオープンの通常商品SS-MA251、"
        "18点まとめ洗いのDWS-33Bに分け、一度に洗う実物と開扉時を含む設置寸法で絞ります。"
        "SOLOTA NP-TMLK1-Kは販売状態未確認のため、仕様参考にとどめます。",
        "16点",
        0,
    ): ("PRD-SIROCA-SS-M171",),
    (
        "標準食器点数は各社の想定した食器構成による参考値で、自宅の皿や調理器具が"
        "必ず収まる保証ではありません。現行4候補は、幅を抑えつつ11〜12点を想定するラクアmini、"
        "16点と2WAY給水のSS-M171、16点とオートオープンの通常商品SS-MA251、"
        "18点まとめ洗いのDWS-33Bに分け、一度に洗う実物と開扉時を含む設置寸法で絞ります。"
        "SOLOTA NP-TMLK1-Kは販売状態未確認のため、仕様参考にとどめます。",
        "16点",
        1,
    ): ("PRD-SIROCA-SS-MA251",),
    (
        "標準食器点数は各社の想定した食器構成による参考値で、自宅の皿や調理器具が"
        "必ず収まる保証ではありません。現行4候補は、幅を抑えつつ11〜12点を想定するラクアmini、"
        "16点と2WAY給水のSS-M171、16点とオートオープンの通常商品SS-MA251、"
        "18点まとめ洗いのDWS-33Bに分け、一度に洗う実物と開扉時を含む設置寸法で絞ります。"
        "SOLOTA NP-TMLK1-Kは販売状態未確認のため、仕様参考にとどめます。",
        "18点",
        0,
    ): ("PRD-TOSHIBA-DWS-33B-W",),
    (
        "SOLOTA・ラクアmini Plusの仕様参考と、ラクアmini・SS-M171・"
        "通常商品SS-MA251の現行3候補",
        "現行",
        0,
    ): (
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-M171",
        "PRD-SIROCA-SS-MA251",
    ),
    (
        "標準食器6点と16点のどちらが日常の量に近いか",
        "6点",
        0,
    ): ("EXT-PANASONIC-SOLOTA-NP-TML1-W",),
    (
        "標準食器6点と16点のどちらが日常の量に近いか",
        "16点",
        0,
    ): ("PRD-SIROCA-SS-M171",),
    (
        "SS-M171はSOLOTAより幅が110mm、奥行が210mm大きい一方、標準食器点数は"
        "10点多くなります。数字の大きい方を一律に勧める比較ではありません。SOLOTAの"
        "数値は短い奥行の仕様参考であり、現行販売を確認できないため購入候補にはしません。",
        "幅が110mm",
        0,
    ): ("PRD-SIROCA-SS-M171",),
    (
        "SS-M171はSOLOTAより幅が110mm、奥行が210mm大きい一方、標準食器点数は"
        "10点多くなります。数字の大きい方を一律に勧める比較ではありません。SOLOTAの"
        "数値は短い奥行の仕様参考であり、現行販売を確認できないため購入候補にはしません。",
        "奥行が210mm",
        0,
    ): ("PRD-SIROCA-SS-M171",),
    (
        "SS-M171はSOLOTAより幅が110mm、奥行が210mm大きい一方、標準食器点数は"
        "10点多くなります。数字の大きい方を一律に勧める比較ではありません。SOLOTAの"
        "数値は短い奥行の仕様参考であり、現行販売を確認できないため購入候補にはしません。",
        "10点",
        0,
    ): ("PRD-SIROCA-SS-M171",),
    (
        "約2.5Lと約5Lは1回あたりの公表値です。1日の運転回数が違えば、"
        "単純な大小だけでは使用量を決められません。",
        "2.5L",
        0,
    ): ("EXT-PANASONIC-SOLOTA-NP-TML1-W",),
    (
        "約2.5Lと約5Lは1回あたりの公表値です。1日の運転回数が違えば、"
        "単純な大小だけでは使用量を決められません。",
        "5L",
        0,
    ): ("PRD-SIROCA-SS-M171",),
    (
        "標準食器点数は各社の想定した食器構成による参考値で、自宅の皿や調理器具が必ず収まる"
        "保証ではありません。SOLOTAは現行販売を公式確認できていないため、小容量と短い奥行の仕様参考に"
        "とどめます。現行候補は、幅を抑えつつ11〜12点を想定するラクアmini、SS-MA251を16点とオートオープン、"
        "DWS-33Bを18点まとめ洗いの条件に分け、一度に洗う実物と開扉時を含む設置寸法で絞ります。",
        "現行",
        0,
    ): (
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-MA251",
        "PRD-TOSHIBA-DWS-33B-W",
    ),
    (
        "この記事では、Panasonic SOLOTA NP-TML1-Wとsiroca 食器洗い乾燥機 SS-M171の設置寸法、"
        "標準食器点数、使用水量、給水方式を比較します。SOLOTAは少量と短い奥行を示す"
        "仕様参考ですが、現行販売は未確認です。SS-M171は、設置面を広げて16点と2通りの"
        "給水方法を選ぶ現行候補です。自動でドアが開くことを条件にする場合は、siroca 食器洗い乾燥機 "
        "SS-MA251を容量参考として別に扱います。",
        "現行",
        0,
    ): ("PRD-SIROCA-SS-M171",),
    (
        "比較範囲:置き場所優先のEufy C10・K11+ Proと、モップ自動手入れ優先の"
        "DEEBOT mini 2・Roomba Plus 515 Combo。 置き場所優先の2モデルと"
        "モップ自動手入れ優先の2モデルを、本体・ステーション寸法と"
        "水拭き・自動手入れの公式仕様で比べ、清掃性能の順位は付けていません。",
        "2モデル",
        0,
    ): (
        "PRD-EUFY-AUTOEMPTY-C10-T2292",
        "PRD-SWITCHBOT-K11-PRO",
    ),
    (
        "比較範囲:置き場所優先のEufy C10・K11+ Proと、モップ自動手入れ優先の"
        "DEEBOT mini 2・Roomba Plus 515 Combo。 置き場所優先の2モデルと"
        "モップ自動手入れ優先の2モデルを、本体・ステーション寸法と"
        "水拭き・自動手入れの公式仕様で比べ、清掃性能の順位は付けていません。",
        "2モデル",
        1,
    ): (
        "PRD-ECOVACS-DEEBOT-MINI2",
        "PRD-IROBOT-ROOMBA-PLUS-515-COMBO",
    ),
    (
        "SOLOTAの仕様差を参考にしながら、現行候補SS-M171が自宅に合うか判断する",
        "現行",
        0,
    ): ("PRD-SIROCA-SS-M171",),
    (
        "工事不要のタンク式食洗機を公式仕様で比較。現行販売を確認できた3候補を、"
        "食器点数、設置寸法、使用水量、乾燥方式で選び分けます。"
        "SOLOTA NP-TMLK1は販売状態未確認の仕様参考です。",
        "現行販売",
        0,
    ): (
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-MA251",
        "PRD-TOSHIBA-DWS-33B-W",
    ),
    (
        "工事不要のタンク式食洗機を公式仕様で比較。現行販売を確認できた3候補を、"
        "食器点数、設置寸法、使用水量、乾燥方式で選び分けます。"
        "SOLOTA NP-TMLK1は販売状態未確認の仕様参考です。",
        "3候補",
        0,
    ): (
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-MA251",
        "PRD-TOSHIBA-DWS-33B-W",
    ),
    (
        "比較範囲:タンク給水対応の4モデル。 現行販売を確認できた3候補と、"
        "販売状態未確認のSOLOTA 1モデルを仕様参考として、本体・扉開放寸法、"
        "標準収納容量、使用水量、乾燥方式で比較しています。",
        "現行販売",
        0,
    ): (
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-MA251",
        "PRD-TOSHIBA-DWS-33B-W",
    ),
    (
        "比較範囲:タンク給水対応の4モデル。 現行販売を確認できた3候補と、"
        "販売状態未確認のSOLOTA 1モデルを仕様参考として、本体・扉開放寸法、"
        "標準収納容量、使用水量、乾燥方式で比較しています。",
        "3候補",
        0,
    ): (
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-MA251",
        "PRD-TOSHIBA-DWS-33B-W",
    ),
    (
        "タンク給水に対応し、メーカー公式情報で主要仕様を確認できた4モデルを比較しています。"
        "このうち現行販売を確認できた3モデルを購入候補、SOLOTAを販売状態未確認の仕様参考とします。"
        "設置条件と一度に洗う量が異なるため、同じ総合順位には並べず、条件別に整理しました。",
        "現行販売",
        0,
    ): (
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-MA251",
        "PRD-TOSHIBA-DWS-33B-W",
    ),
    (
        "タンク給水に対応し、メーカー公式情報で主要仕様を確認できた4モデルを比較しています。"
        "このうち現行販売を確認できた3モデルを購入候補、SOLOTAを販売状態未確認の仕様参考とします。"
        "設置条件と一度に洗う量が異なるため、同じ総合順位には並べず、条件別に整理しました。",
        "3モデル",
        0,
    ): (
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-MA251",
        "PRD-TOSHIBA-DWS-33B-W",
    ),
    (
        "工事不要の食洗機3候補+1仕様参考|1〜2人暮らしの設置条件で選ぶ",
        "3候補",
        0,
    ): (
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-MA251",
        "PRD-TOSHIBA-DWS-33B-W",
    ),
    (
        "ロボット掃除機4モデルを、本体・ステーションの設置寸法、帰還余白、"
        "水拭きと自動手入れの範囲で比較。置き場所優先の2モデルと、"
        "モップ自動手入れ優先の2モデルを条件別に整理します。",
        "2モデル",
        0,
    ): (
        "PRD-EUFY-AUTOEMPTY-C10-T2292",
        "PRD-SWITCHBOT-K11-PRO",
    ),
    (
        "ロボット掃除機4モデルを、本体・ステーションの設置寸法、帰還余白、"
        "水拭きと自動手入れの範囲で比較。置き場所優先の2モデルと、"
        "モップ自動手入れ優先の2モデルを条件別に整理します。",
        "2モデル",
        1,
    ): (
        "PRD-ECOVACS-DEEBOT-MINI2",
        "PRD-IROBOT-ROOMBA-PLUS-515-COMBO",
    ),
    (
        "現行候補と仕様参考を混ぜない。",
        "現行",
        0,
    ): ("PRD-SIROCA-SS-M171",),
    (
        "現行候補と販売状態未確認モデルを分けて読む。",
        "現行",
        0,
    ): ("PRD-SIROCA-SS-M171",),
    (
        "現行候補と販売状態未確認モデルを分けて読む。",
        "販売状態未確認",
        0,
    ): ("EXT-PANASONIC-SOLOTA-NP-TML1-W",),
    (
        "現行候補(ラクアmini・SS-M171・通常商品SS-MA251)と販売状態未確認の"
        "SOLOTAを分けて読む。",
        "現行",
        0,
    ): (
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-M171",
        "PRD-SIROCA-SS-MA251",
    ),
    (
        "現行候補(ラクアmini・SS-M171・通常商品SS-MA251)と販売状態未確認の"
        "SOLOTAを分けて読む。",
        "販売状態未確認",
        0,
    ): ("EXT-PANASONIC-SOLOTA-NP-TML1-W",),
    (
        "仕様参考として掲載する白いSOLOTAです。現行販売は未確認です。"
        "ブラックはNP-TMLK1-Kで、別の型番として公式情報を確認します。",
        "現行販売",
        0,
    ): ("EXT-PANASONIC-SOLOTA-NP-TML1-W",),
    (
        "「新しい世代」を理由にC1000 Gen 2を選ぶと、C1000より約1.6kg軽く、"
        "USB-Cが2口から3口へ増える一方で、C1000が備える容量拡張を"
        "手放すという重要な差を見落とします。",
        "2口",
        0,
    ): ("PRD-ANKER-SOLIX-C1000",),
    (
        "「新しい世代」を理由にC1000 Gen 2を選ぶと、C1000より約1.6kg軽く、"
        "USB-Cが2口から3口へ増える一方で、C1000が備える容量拡張を"
        "手放すという重要な差を見落とします。",
        "3口",
        0,
    ): ("PRD-ANKER-SOLIX-C1000-GEN2",),
    (
        "短い奥行ならSOLOTA、16点と2WAY給水ならSS-M171。",
        "16点",
        0,
    ): ("PRD-SIROCA-SS-M171",),
    (
        "アドバンスシリーズの容量参考型番です。SS-M171の仕様を読み替えず、"
        "オートオープンと収納条件を個別に確認します。",
        "オートオープン",
        0,
    ): ("PRD-SIROCA-SS-MA251",),
    (
        "2製品比較+参考機種",
        "2製品",
        0,
    ): (
        "EXT-PANASONIC-SOLOTA-NP-TML1-W",
        "EXT-THANKO-RAKUA-MINI-PLUS",
    ),
    (
        "5モデル最軽量 / 日本製",
        "5モデル",
        0,
    ): (
        "PRD-PROTECA-AEROFLEX-DX2-01521",
        "PRD-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
        "PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002",
        "PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549",
        "PRD-PROTECA-TRI-AIR-01541",
    ),
    (
        "外寸は幅37×奥行23×高さ55cm、3辺合計115cm。35L、1.8kgの日本製で、"
        "5モデルのうち本体が最も軽い候補です。公式商品ページで拡張機能は"
        "確認できません。キャスターストッパーは公式商品ページと公式サイト内の"
        "分類情報が一致しないため、有無を未確認として扱います。",
        "5モデル",
        0,
    ): (
        "PRD-PROTECA-AEROFLEX-DX2-01521",
        "PRD-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
        "PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002",
        "PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549",
        "PRD-PROTECA-TRI-AIR-01541",
    ),
    (
        "狭い家具間を優先するなら、幅24.8cmのK11+ Proか幅24.5cmの"
        "Roomba Mini Slimを確認します。高さはいずれも9.2cmです。",
        "幅24.8cm",
        0,
    ): ("PRD-SWITCHBOT-K11-PRO",),
    (
        "狭い家具間を優先するなら、幅24.8cmのK11+ Proか幅24.5cmの"
        "Roomba Mini Slimを確認します。高さはいずれも9.2cmです。",
        "幅24.5cm",
        0,
    ): ("PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",),
    (
        "狭い家具間を優先するなら、幅24.8cmのK11+ Proか幅24.5cmの"
        "Roomba Mini Slimを確認します。高さはいずれも9.2cmです。",
        "9.2cm",
        0,
    ): (
        "PRD-SWITCHBOT-K11-PRO",
        "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",
    ),
    (
        "比較した5モデルの公表値はC300が288Wh・定格300W・約4.1kg、"
        "Jackery 500 Newが512Wh・定格500W・約5.7kg、Anker Solix C800が"
        "768Wh・定格1200W・約10.5kg、Jackery 1000 New V3が1024Wh・"
        "AC定格1500W・約10.6kg、DJI Power 1000 V2が1024Wh・最大連続2600W・"
        "約14.2kgである。この閉じた5モデル比較ではC300が最小容量かつ最軽量で、"
        "C800は1024Whの1000 New V3より約0.1kg、Power 1000 V2より約3.7kg軽い。"
        "各社公表の連続供給目安は呼称・試験条件が異なるため、定格出力と最大連続出力を"
        "同一指標として大小比較しない。接続機器の通常時・起動時電力と同時使用の合計を"
        "各製品の条件へ個別に照合し、必要容量、安全に運べる重量、保管条件、"
        "保証・サポートでも候補を変える。",
        "3.7kg",
        0,
    ): ("PRD-ANKER-SOLIX-C800",),
}

SCHEMA: Final = "RAOS_READER_CLAIM_BINDINGS_V1"
VERSION: Final = "1.1.0"
MAX_JSON_BYTES: Final = 4 * 1024 * 1024
MAX_HTML_BYTES: Final = 2 * 1024 * 1024
MAX_UNITS_PER_ARTICLE: Final = 2_000
SALES_STATE_MAX_AGE_SECONDS: Final = 24 * 60 * 60
SALES_STATE_MAX_FUTURE_SKEW_SECONDS: Final = 5 * 60
# Independent review anchor for the owner-private manufacturer availability
# capture.  Row hashes alone are self-describing and can be recomputed after a
# state edit; this document digest makes any replacement an explicit code and
# ledger review rather than silently trusting a newly self-hashed JSON row.
REVIEWED_SALES_STATE_DOCUMENT_SHA256: Final = (
    "54a424b01070e0b6a362f799c5463c74a8a032469ece1e83b8729f81eab0c80f"
)
# The ledger itself is an independently reviewed allow-list.  Regex extraction
# is useful for numbers, comparisons, dimensions, availability, and a closed
# feature vocabulary, but it cannot prove that arbitrary natural-language
# prose is non-factual.  This canonical document anchor therefore makes every
# newly added unit, text change, claim mapping, and NON_CLAIM exemption require
# an explicit code-review update.  It is filled only after the complete ledger
# has passed the semantic validator and an independent review.
REVIEWED_READER_LEDGER_SHA256: Final = (
    "af0890d3492e36e2e5e0ad1b5d00e69e669ac3a303d07b35e5c2184a5a23758a"
)
# Reconciled development ledger, not an independent review attestation. Keep
# the reviewed anchor above unchanged until the separate review is completed.
DEVELOPMENT_READER_LEDGER_SHA256: Final = (
    "7581aedcbeae7c4aa3500a7ff5193869140851c2d35775b09d8f97f2f5ac60ab"
)
ADDITIONAL_OFFICIAL_SALES_HOSTS: Final = {
    # siroca separates product information and its first-party store across
    # siroca.co.jp / siroca.jp.  This is an explicit origin registration, not
    # a suffix or arbitrary-HTTPS allowance.
    "PRD-SIROCA-SS-MA251": frozenset({"store.siroca.jp"}),
    "PRD-SIROCA-SS-M171": frozenset({"store.siroca.jp"}),
    # PROTECA is an ACE brand and uses the ACE first-party shop for sales.
    "PRD-PROTECA-AEROFLEX-DX2-01521": frozenset({"store.ace.jp"}),
}
SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")

UNIT_TAGS: Final = frozenset(
    {
        "a",
        "blockquote",
        "button",
        "caption",
        "dd",
        "dt",
        "figcaption",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "label",
        "legend",
        "li",
        "option",
        "p",
        "summary",
        "td",
        "th",
    }
)
VOID_TAGS: Final = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
IGNORED_TAGS: Final = frozenset({"script", "style", "template", "noscript"})
ACCESSIBILITY_ATTRIBUTES: Final = ("alt", "aria-label", "title", "placeholder")
READER_TEXT_CHANNELS: Final = frozenset(
    {"VISIBLE_TEXT", "WORDPRESS_TITLE", "WORDPRESS_EXCERPT"}
)
KINDS: Final = frozenset(
    {
        "VERIFIABLE",
        "EDITORIAL_INFERENCE",
        "RECHECK_REQUIRED",
        "UNKNOWN",
        "NON_CLAIM",
    }
)
CONTEXTS: Final = frozenset({"GENERAL", "COMPARISON", "DECISION"})
EXEMPTION_CODES: Final = frozenset(
    {
        "ACCESSIBILITY_OR_DECORATION",
        "DISCLOSURE_POLICY",
        "EDITORIAL_METADATA",
        "EDITORIAL_METHOD",
        "NAVIGATION_OR_UI",
        "READER_SCOPE_OR_GUIDANCE",
        "SOURCE_CITATION_LABEL",
        "TABLE_OR_DEFINITION_LABEL",
    }
)

UNKNOWN_RE: Final = re.compile(
    r"(?:未確認|確認できず|確認できなかった|確認できない|確認できません|比較できない|"
    r"確定できず|確定できない|確定できません|不明|"
    r"公表(?:なし|されていない)|比較できる公式[^。]*値なし|"
    r"推奨根拠から除外|該当なし)"
)
UNKNOWN_STATUS_RE: Final = re.compile(
    r"(?:"
    r"公式確認範囲では未確認|"
    r"(?:(?:メーカー公式情報では確認できず|公式の現行製品ページ本文で|"
    r"アクセサリ互換性は)\s*)?未確認"
    r"(?:\((?:推奨根拠に不使用|推奨根拠外)\))?(?:\s+未確認)?"
    r"(?:\s+推奨根拠に使用しない)?|"
    r"比較できる公式(?:容量|吸引力|運転音|電力量)値なし|"
    r"公式商品ページでは確認できず\s+未確認|"
    r"公式容量値は未確認|"
    r"公式商品ページと公式サイト内の分類情報が一致せず、"
    r"キャスターストッパーの有無は未確認(?:\s+未確認)?|"
    r"該当なし"
    r")"
)
# An external market candidate may remain visible when its decision-critical
# fact could not be established, but the uncertainty must be unmistakable and
# must not enter the recommendation graph.  This phrase is deliberately exact
# enough that a generic "未確認" cannot be presented as a completed review.
RECHECK_REQUIRED_DISCLOSURE_RE: Final = re.compile(
    r"未確認[（(]推奨根拠に使用しない[）)]"
)
AFFILIATE_FALLBACK_STATUS_RE: Final = re.compile(
    r"(?:一致する楽天商品を確認できなかったため、"
    r"楽天購入リンクは掲載していません|"
    r"商品画像未確認・購入導線停止)"
)
CLOSED_UNKNOWN_SALES_PHRASE_RE: Final = re.compile(
    r"(?:販売状態(?:は|を)?(?:未確認|確認できな(?:い|かった|く|せん))|"
    r"現行販売(?:は|を|が)?[^ 。、！？]{0,24}"
    r"(?:未確認|確認できな(?:い|かった|く)|"
    r"確認できません|確認できていない|確認していない))"
)
RELATIVE_ASSERTION_RE: Final = re.compile(
    r"(?:最軽量|最大|最小|"
    r"最も(?:軽(?:い|く)?|重(?:い|く)?|大き(?:い|く)?|小さ(?:い|く)?|"
    r"多(?:い|く)?|少な(?:い|く)?|高(?:い|く)?|低(?:い|く)?)|"
    r"より(?:軽(?:い|く)?|重(?:い|く)?|大き(?:い|く)?|小さ(?:い|く)?|"
    r"多(?:い|く)?|少な(?:い|く)?|高(?:い|く)?|低(?:い|く)?)|"
    r"上回る|下回る|同率)"
)
DECISION_MARKERS: Final = (
    "decision",
    "recommend",
    "conclusion",
    "product-card",
    "product_card",
    "product-profile",
    "products-section",
    "shortlist",
    "final-summary",
    "final_summary",
)
COMPARISON_MARKERS: Final = (
    "comparison",
    "matrix",
    "difference",
    "spec-table",
    "spec_table",
)

# The automatic portion is intentionally conservative.  It forces authors to
# declare values/models and a small set of decision-critical feature phrases;
# it does not attempt to infer a source claim from prose.
NUMERIC_ASSERTION_RE: Final = re.compile(
    r"(?<![A-Za-z0-9_.])(?:"
    r"[A-Za-z][A-Za-z0-9+*._-]*\d[A-Za-z0-9+*._/-]*"
    r"|\d+(?:[.,]\d+)?\s*(?:"
    r"cm|mm|m|kg|GHz|Hz|kWh|Wh|W|Pa|L|V|口|点|個|席|人|台|回|"
    r"時間|分|秒|年|月|日"
    r")"
    r")(?![A-Za-z0-9_.])",
    re.IGNORECASE,
)
RANGE_ASSERTION_RE: Final = re.compile(
    r"\d+(?:[.,]\d+)?\s*[〜～]\s*\d+(?:[.,]\d+)?\s*"
    r"(?:cm|mm|m|kg|kWh|Wh|W|Pa|L|口|点|個|席|人|台|回|時間|分|秒|年|月|日)",
    re.IGNORECASE,
)
COUNT_ASSERTION_RE: Final = re.compile(
    r"(?<![A-Za-z0-9])\d+\s*(?:モデル|製品|構成|機種|候補)"
)
BAND_ASSERTION_RE: Final = re.compile(r"\d+(?:[.,]\d+)?\s*kg台", re.IGNORECASE)
COMPARATOR_PATTERN: Final = (
    r"では(?:ない|ありません)|未満|以下|以内|以上|"
    r"を(?:超え(?:る|ます)?|上回(?:る|ります)?)|"
    r"より(?:大きい|小さい|多い|少ない)"
)
NAMED_DIMENSION_ASSERTION_RE: Final = re.compile(
    r"(?:(?P<dimension_subject>"
    r"本体(?:寸法)?|(?:充電|ゴミ収集|デュアル集塵)?ステーション|"
    r"充電台|充電スタンド|ドア開閉時最大外形|ドア開放時|扉開放時|開扉時|"
    r"通常時(?:外寸)?|拡張時(?:外寸)?"
    r")\s*(?:[）)]\s*)?(?:は|が|の|[:：])?\s*)?"
    r"幅(?:約)?(?P<width>\d+(?:[.,]\d+)?)(?P<width_unit>cm|mm)?\s*[×x]\s*"
    r"奥行(?:約)?(?P<depth>\d+(?:[.,]\d+)?)(?P<depth_unit>cm|mm)?\s*[×x]\s*"
    r"高さ(?:約)?(?P<height>\d+(?:[.,]\d+)?)(?P<height_unit>cm|mm)",
    re.IGNORECASE,
)
ORDERED_DIMENSION_ASSERTION_RE: Final = re.compile(
    r"(?<![.\d])(?:約)?(?P<width>\d+(?:[.,]\d+)?)(?P<width_unit>cm|mm)?"
    r"\s*[×x]\s*(?:約)?(?P<depth>\d+(?:[.,]\d+)?)(?P<depth_unit>cm|mm)?"
    r"\s*[×x]\s*(?:約)?(?P<height>\d+(?:[.,]\d+)?)(?P<height_unit>cm|mm)"
    r"(?![A-Za-z\d])",
    re.IGNORECASE,
)
AXIS_SCALAR_ASSERTION_RE: Final = re.compile(
    r"(?:(?P<dimension_subject>"
    r"本体(?:寸法)?|(?:充電|ゴミ収集|デュアル集塵)?ステーション|"
    r"充電台|充電スタンド|台の筐体|ドア開閉時最大外形|"
    r"ドア開放時|扉開放時|開扉時|扉を開いたときの|"
    r"通常時(?:外寸)?|拡張時(?:外寸)?"
    r")\s*(?:[）)]\s*)?(?:は|が|の|[:：])?\s*(?:最大)?\s*)?"
    r"(?P<axis>幅|奥行|高さ|直径)\s*"
    r"(?:は|が|の|[:：])?\s*(?:約)?"
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>cm|mm)"
    rf"(?P<suffix>{COMPARATOR_PATTERN})?",
    re.IGNORECASE,
)
OPEN_DEPTH_ASSERTION_RE: Final = re.compile(
    r"(?P<dimension_subject>ドア開閉時最大|ドア開放時|扉開放時|開扉時)"
    r"(?:奥行)?\s*(?:約)?(?P<value>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>cm|mm)"
    rf"(?P<suffix>{COMPARATOR_PATTERN})?",
    re.IGNORECASE,
)
THREE_SIDE_SUM_ASSERTION_RE: Final = re.compile(
    r"(?:3辺(?:の)?(?:合計|和)|合計)\s*(?:は|が|[:：])?\s*(?:約)?"
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>cm|mm)"
    rf"(?P<suffix>{COMPARATOR_PATTERN})?",
    re.IGNORECASE,
)
EFFECTIVE_DATE_ASSERTION_RE: Final = re.compile(
    r"20\d{2}(?:年|[./-])\d{1,2}(?:(?:月|[./-])\d{1,2}日?)?"
)
FEATURE_ASSERTION_RE: Final = re.compile(
    r"(?:自動ゴミ収集|自動給水|温水洗浄|温風乾燥|熱風乾燥|送風乾燥|"
    r"自動ドア開放|オートオープン|リフトアップ(?:オープン)?ドア|"
    r"キャスターストッパー|ストッパー|ブレーキ機能|"
    r"フロントオープン|センターオープン|前開き|中央開き|"
    r"フロントポケット|メイン収納(?:全体)?へ(?:アクセス|届く)|"
    r"前(?:側|面)?から(?:メイン収納)?全体へ(?:アクセス|届く)|メインへアクセス|"
    r"2WAY(?:オープン)?|3ROOM|ワイドオープン|"
    r"(?:独立)?PC(?:収納|ポケット)|USB(?:\s*Type)?-[AC]|USB(?:ポート|端子)|"
    r"日本製|ハード(?:タイプ)?|ソフト(?:タイプ)?|"
    r"拡張機能(?:あり|なし)|拡張(?:時|後|すると|できる|対応)|"
    r"交換用静音タイヤキット|交換可能車輪|車輪を交換|"
    r"使い捨てシート式|お掃除シート式|共用ステーション|"
    r"手動(?:で)?(?:の)?ごみ捨て|手動で空に|"
    r"拡張バッテリー|SlimCharge|AutoEmpty|AutoWash|DualClean|"
    r"ビデオマネージャー|"
    r"Wi-Fi(?=(?:に|は)?(?:対応|非対応))|機内持ち込み|機内持込み)",
    re.IGNORECASE,
)
SALES_STATE_ASSERTION_RE: Final = re.compile(
    r"(?:販売状態(?:は|を)?(?:未確認|確認できな(?:い|かった|く|せん))|"
    r"購入UIを確認できな(?:い|かった|く|せん)|"
    r"購入UIを確認でき(?:る|た|ました)|"
    r"再入荷(?:\(予約開始\))?通知(?:のみ|だけ)?|"
    r"在庫切れ|売り切れ|売切れ|欠品中|品切れ|完売|再入荷待ち|"
    r"在庫なし|購入不可|"
    r"現行(?:販売|表示|品|モデル|製品)|現行(?=$|[\s、。！？])|"
    r"在庫あり|販売中|購入可能|現在購入できます|"
    r"購入できます|注文できます|予約受付中|残りわずか|"
    r"販売再開(?:中|済み|しました)|"
    r"生産終了|販売終了|終売|取扱終了|販売休止|販売停止)"
)
SALES_AFFIRMATIVE_SUFFIX_RE: Final = re.compile(
    r"(?:です|でした|で|(?:の)?ため|[をと]確認(?:済み|できた)?|しました|しています|"
    r"を(?:、|,)?|現行候補(?:です|で|と|として|は|を|の|。|、|$)|"
    r"状態を満たすため|[』」]?と表示されました|"
    r"中です|の\d+台|(?:の)?(?:新)?仕様|\d+構成|\d+モデル|"
    r"(?:の)?(?:購入)?(?:\d+\s*)?候補(?:です|で|と|として|は|を|の|(?=[A-Za-z0-9])|。|、|$)|"
    r"・|。|、|「|$)"
)
SALES_NEGATED_OR_UNCERTAIN_RE: Final = re.compile(
    r"(?:では(?:ありません|ない|なかった)|じゃ(?:ありません|ない)|でない|"
    r"というわけではない|わけではない|とは限らない|かは不明|"
    r"とは確認できな(?:い|かった)|を確認できな(?:い|かった|ません)|"
    r"確認できません|未確認|不明|のためではない|"
    r"確認して(?:い|おり)ません|していない)"
)
# Whether an availability word is asserted is occurrence-local.  For example,
# ``販売中とは判定しません`` must not be extracted as an AVAILABLE
# assertion merely because the literal word ``販売中`` is present.
SALES_LOCAL_NEGATION_SUFFIX_RE: Final = re.compile(
    r"^\s*(?:"
    r"では(?:ありません|ない|なかった)|"
    r"じゃ(?:ありません|ない)|"
    r"とは(?:限らない|いえない|判定|判断|確認)"
    r"(?:しない|しません|できない|できません)|"
    r"と(?:は)?推測(?:しない|しません|せず)|"
    r"か(?:どうか)?(?:は)?(?:不明|未確認|確定できない)|"
    r"を確認できな(?:い|かった|く)|"
    r"型番(?:は|を)[^。！？]{0,20}(?:推奨せず|推奨対象にしない)|"
    r"を示さない|を意味し(?:ない|ません)|"
    r"(?:です|なの)?か(?:[。！？]|$)|"
    r"というわけではない|わけではない|"
    r"(?:の)?(?:購入)?(?:\d+\s*)?(?:候補|比較表|構成)[^。、]{0,12}"
    r"(?:から|へ)?(?:除外|外し|戻さない|戻しません)"
    r")"
)
# A completed external exclusion may report a closed OUT_OF_STOCK observation
# and, in the same sentence, the narrower fact that no purchase UI could be
# confirmed.  This is not an unresolved sales-state recommendation, but the
# exception is intentionally exact and later also requires an independently
# validated embedded OUT_OF_STOCK gate on the same ``-EXCLUDED`` claim.
EXTERNAL_OUT_OF_STOCK_UI_GAP_RE: Final = re.compile(
    r"(?:在庫切れ|売り切れ|売切れ)[^。！？]{0,20}"
    r"(?:購入UI|カート(?:導線)?|注文ボタン)[^。！？]{0,20}"
    r"(?:確認できな(?:い|かった|く)|表示されない)"
)
EXTERNAL_RESTOCK_ONLY_RE: Final = re.compile(
    r"再入荷(?:\(予約開始\))?通知(?:のみ|だけ)"
)
EXTERNAL_EXCLUSION_ACTION_RE: Final = re.compile(
    r"(?:現行(?:の)?(?:購入)?候補から除外|"
    r"購入候補[^。！？]{0,24}(?:から)?外し|"
    r"購入候補へ戻しません|仕様参考に限定|"
    r"商品カード[^。！？]{0,24}(?:から)?外し|"
    r"比較表に含めなかった)"
)
A10_SOLOTA_UNKNOWN_EXCLUSION_CLAIM_ID: Final = (
    "CLM-PORTFOLIO-DISH-SOLOTA-NP-TMLK1-EXCLUDED"
)
A10_RAKUA_RESTOCK_EXCLUSION_CLAIM_ID: Final = (
    "CLM-PORTFOLIO-DISH-RAKUA-MINI-PLUS-EXCLUDED"
)
A10_LIFECYCLE_ROUTE_CLAIM_ID: Final = "CLM-PORTFOLIO-DISH-LIFECYCLE-REFERENCE"
EXTERNAL_UNKNOWN_PURCHASE_UI_RE: Final = re.compile(
    r"(?:購入UI|カート(?:導線)?)[^。！？]{0,24}"
    r"確認でき(?:ない|なかった|なく|ません|ず)"
)
EXTERNAL_UNKNOWN_EXCLUSION_ACTION_RE: Final = re.compile(
    r"(?:仕様参考に(?:限定|とどめ)|"
    r"商品カード・購入導線から除外|"
    r"購入候補には戻しません|"
    r"現行販売を確認できるまで推奨しません|"
    r"(?:現行|いま購入できる)[^。！？]{0,48}で選び直してください)"
)
# A terse table value can be a decision-critical assertion even when it has no
# useful lexical overlap with its evidence (for example, an "自動ゴミ収集"
# column whose cells contain only "あり" / "なし").  Such units must still be
# claim-bearing in the authored ledger; table/definition headers remain exempt.
TERSE_FACT_STATUS_RE: Final = re.compile(
    r"^(?:あり|なし|自動|手動|送風|公表あり|該当なし)(?:\s.*)?$|"
    r"(?:公式確認済み|編集部による計算値|公式ストア(?:で)?売り切れ)"
)
FEATURE_FACT_PREDICATE_RE: Final = re.compile(
    r"(?:備え|対応(?:し|する|して|でき)|案内|公表|搭載|用意|設計|"
    r"機能(?:あり|なし)|あります|ありません|できます|できる|"
    r"(?:式|タイプ)(?:です|である)|異なります|"
    r"非搭載|未搭載|非対応|備えてい(?:ない|ません)|"
    r"行わない|ではない|対応し(?:ない|ません))"
)
FEATURE_POLARITY_SUFFIX_RE: Final = re.compile(
    r"^(?:"
    r"(?:は|には|に|が)?(?:なし|ない|ありません|対応しない|対応しません|非対応|廃止)|"
    r"(?:を|は|には|が)?(?:搭載|装備|対応)(?:されて|して)?い(?:ない|ません)|"
    r"(?:を|は|には|が)?備えてい(?:ない|ません)|"
    r"(?:を|は)?行わない|(?:は|が)?できない|"
    r"(?:では|とは|が|は)?ない|(?:が|は)?なく|"
    r"非搭載|未搭載|非対応"
    r")"
)
# These predicates are deliberately a closed, high-risk vocabulary rather
# than a catch-all ``...仕様`` suffix.  A broad suffix matcher incorrectly
# treats editorial labels such as ``公式仕様`` and ``製品仕様`` as product
# claims, while still failing to understand their polarity.  New fact-bearing
# feature families belong in FEATURE_ASSERTION_RE (with explicit polarity);
# this last line catches common unsupported marketing predicates that must not
# be laundered through a NON_CLAIM exemption.
GENERIC_QUALITATIVE_ASSERTION_RE: Final = re.compile(
    r"(?:静音(?:設計|です|である)|防水(?:仕様|です|である)|"
    r"防滴(?:仕様|です|である)|防塵(?:仕様|です|である)|"
    r"医療機器(?:です|である)|抗菌加工済み|"
    r"TSAロック搭載|Travel\s*Sentryロック搭載)",
    re.IGNORECASE,
)
# A closed predicate extractor catches a reader-visible capability that carries
# no number or feature keyword.  Without it, a product identity alone could be
# bound to an unrelated claim while arbitrary prose such as ``宇宙空間で使用
# できます`` escaped semantic review.
CAPABILITY_ASSERTION_RE: Final = re.compile(
    r"[^。、；;]{1,36}?(?:で|を|に)(?:使用|利用|設置|収納|接続|充電|給電|"
    r"洗浄|乾燥|運転|持ち込み|持込)(?:できます|できる|可能(?:です)?)"
)
GENERIC_QUALITATIVE_POLARITY_SUFFIX_RE: Final = re.compile(
    r"^(?:では(?:ない|ありません)|でない|とは限らない|とはいえない)"
)
RECOMMENDATION_CONCLUSION_RE: Final = re.compile(
    r"(?:おすすめ(?:する|の)?理由|選ぶ理由|選定理由|推奨する理由)"
)
# Reader-visible selection conclusions need the same sales/safety/due-diligence
# gate even when the editor did not literally label the sentence as an
# ``おすすめする理由``.  Keep this vocabulary closed: a broad match on
# ``条件`` or ``場合`` would incorrectly turn ordinary installation cautions into
# recommendations.
SELECTION_DECISION_RE: Final = re.compile(
    r"(?:購入候補|第一候補|候補(?:です|として|にする|に向く|"
    r"に合う|から選ぶ|を選ぶ|を絞る)|"
    r"選び方|選び分け|選ぶなら|選びたい|選定理由|"
    r"向く条件|向いています|場合に向きます|"
    r"場合に合います|比較の軸です|買わない条件)"
)
# Closed high-risk prose families checked before any NON_CLAIM exemption.  An
# exemption may explain method, metadata, navigation, or disclosure; it cannot
# make a sales observation, product recommendation, or capability assertion
# non-factual merely because one exempt-looking substring occurs elsewhere in
# the same reader unit.
CLAIM_REVIEW_REQUIRED_RE: Final = re.compile(
    r"(?:仕様(?:を|が)?(?:確認|公表|掲載)|"
    r"メーカー公式[^。！？]{0,40}(?:確認|公表|表示)|"
    r"保証(?:期間|年|か月|ヶ月)|補修用性能部品|"
    r"リコール|安全情報)"
)
NUMERIC_COMPARATOR_SUFFIX_RE: Final = re.compile(
    r"^(?:では(?:ない|ありません)|未満|以下|以内|以上|"
    r"を(?:超え(?:る|ます)?|上回(?:る|ります)?)|"
    r"より(?:大きい|小さい|多い|少ない))"
)
NESTED_COMPARATOR_NEGATION_RE: Final = re.compile(
    r"(?:未満|以下|以内|以上|を(?:超え(?:る|ます)?|上回(?:る|ります)?))"
    r"では(?:ない|ありません)"
)
RELATIVE_POLARITY_SUFFIX_RE: Final = re.compile(
    r"^(?:(?:では|とは|わけでは)(?:ない|ありません|限らない|いえない)|"
    r"とは限らない|とはいえない)"
)
RELATIVE_GUIDANCE_RE: Final = re.compile(
    r"(?:探(?:す|している)|求める|したい|抑えたい|選びたい|優先したい|"
    r"選ぶ|決め(?:る|たい)|最小に(?:し|する))"
)
SALES_STATE_HASH_FIELDS: Final = (
    "checked_at_utc",
    "product_id",
    "state",
    "availability_scope",
    "official_url",
    "status_evidence_urls",
    "locator",
    "basis",
    "variant_caveat",
    "alternative",
)
DISCLOSURE_EXEMPTION_RE: Final = re.compile(
    r"(?:広告|アフィリエイト|成果報酬|報酬率|購入リンク|掲載順|"
    r"楽天ウェブサービス)"
)
METADATA_EXEMPTION_RE: Final = re.compile(
    r"(?:確認日|最終確認|取得期間|更新履歴|執筆担当|事実確認担当|"
    r"実機(?:確認|未使用|未実施)|実機で未確認|対象読者|比較範囲|"
    r"確認範囲|一次情報確認)"
)
METHOD_EXEMPTION_RE: Final = re.compile(
    r"(?:比較方法|比較軸|比較対象|実機(?:試験|確認)|公表値|公式情報|"
    r"公称値|順にそろえ|"
    r"実機を使用したレビューではありません|"
    r"順位(?:付け)?|評価(?:しない|できない)|"
    r"確認(?:する|します|し|して|してください)|"
    r"目安|計算|概算|条件をそろえ|モデルに限定|保証(?:では|しない)|対象外)"
)
METHOD_UNKNOWN_EXEMPTION_RE: Final = re.compile(
    r"(?:"
    r"実機を使用していないため、[^。]+は比較対象外です(?:。価格、在庫、"
    r"報酬率による順位付けも行っていません)?|"
    r"各数値の軸を確認できない寸法は、最大底面辺や設置面積の計算と"
    r"推奨根拠に使いません|"
    r"[^。]+確認できないため、[^。]+(?:推奨根拠に使いません|比較には使いません)|"
    r"1回消費電力量の公式値がある場合だけ、[^。]+。値がそろわなければ、"
    r"費用差は未確認のままにします。"
    r")"
)
METADATA_UNKNOWN_EXEMPTION_RE: Final = re.compile(
    r"(?:実機で未確認|更新履歴[^。]+実機未確認の境界[^。]+(?:。[^。]+)?)"
)
COMPARISON_SCOPE_LIMIT_RE: Final = re.compile(
    r"(?:"
    r"20\d{2}年\d{1,2}月\d{1,2}日に確認した\d+モデルの公式仕様整理。"
    r"価格・在庫・搭乗可否は比較表から確定できません。|"
    r"このページからは確定できません。"
    r"利用する運航会社、便、機材、運賃種別の最新条件と、"
    r"荷物を入れた状態の外寸・総重量を照合してください。"
    r")"
)
NAVIGATION_EXEMPTION_RE: Final = re.compile(
    r"(?:目次|戻る|一覧|公式(?:サイト)?で仕様を確認|"
    r"メーカー公式で(?:仕様と型番|販売状況(?:と仕様)?)を確認|"
    r"楽天市場|Supported by Rakuten Developers|編集・比較方針|"
    r"よくある質問|編集部まとめ|条件ごとの結論|公表仕様を比べる|"
    r"詳しい理由と注意点を読む|詳しい仕様を見る|仕様差を読む|"
    r"合いやすい条件|合いにくい条件|"
    r"別の候補も検討したい条件|容量の参考|"
    r"商品画像未確認・購入導線停止|"
    r"^(?:はじめに|結論|比較方法|こんな人向け|1泊の確認項目|"
    r"4つの使用場面|設置|手入れ|アプリ・Wi-Fi|まとめ|確認結果|確認方法)$|"
    r"注記・出典|^候補\d+$|^\d{1,2}$|^\d{2}\s|^[A-D](?:\s.*)?$)"
)
SOURCE_LABEL_EXEMPTION_RE: Final = re.compile(
    r"(?:公式(?:サイト|オンラインストア|通販|製品情報|サポート|仕様|ページ)|"
    r"出典|情報源|参照元|メーカー公式)"
)
ACCESSIBILITY_FIXED_TEXTS: Final = frozenset(
    {
        "比較の要点",
        "広告表示",
        "この記事の確認状況",
        "この記事の確認範囲",
        "比較方法と外部リンクについて",
        "収益化の対象外",
        "機内持ち込み用スーツケースの選び方を表現した旅支度のイメージ",
        "軽量な機内持ち込み用スーツケースを比較するイメージ",
        "フロントオープン型スーツケースの選び方を表現した旅支度のイメージ",
        "ロボット掃除機本体、充電ステーション、走行スペースの採寸を表した中立イメージ。比較対象の商品写真ではありません",
        "卓上食洗機、開いた扉、シンク周辺の採寸を表した中立イメージ。比較対象の商品写真ではありません",
        "モバイル用食洗機2製品比較",
    }
)
METADATA_FIXED_TEXTS: Final = frozenset(
    {
        "2製品比較+参考機種",
        "外寸などを確認し、前開きとキャスターストッパーを必須とする本記事の"
        "範囲外として整理。確認日:2026年8月31日。",
    }
)
METHOD_FIXED_TEXTS: Final = frozenset(
    {
        "清掃力・段差・障害物回避は実機で比べていません。",
        "軽さ、前開き、PC収納のどれが必要かを考える前に、利用便と機材を確認してください。"
        "公称寸法だけでは持ち込み可否を確定できません。",
        "容量、定格出力、重量をメーカー公式情報で確認できるモデルに限定",
        "販売状態は変わるため、購入前にメーカー公式ページで同じ型番を再確認します。",
        "A. いいえ。正確な型番の購入画面または再入荷通知を確認します。"
        "購入画面を確認できなければ、販売状態を再確認できるまで購入を見送ります。",
        "購入UIを確認できない型番を推奨対象にしないこと",
        "実機レビューではありません",
        "メーカー公式の製品情報、仕様表、設置案内を確認しています。"
        "同じ床での清掃率、動作音、障害物回避、アプリの操作性は測定していないため、"
        "使い勝手や清掃力の順位は示しません。",
        "メーカー公式ページで型番と販売表示を確認しています。"
        "洗浄・乾燥性能や操作性は試しておらず、このページでは性能順位を示しません。",
    }
)
LOCAL_MIXED_UNKNOWN_FIXED_TEXTS: Final = frozenset(
    {
        "ビデオマネージャー対応 対応Wi-Fi周波数帯は未確認",
        "ビデオマネージャーは遠隔見守り・声かけ・スクリーンショットに対応します。"
        "この記事で対応Wi-Fi周波数帯は確認できていないため、購入時に公式サポートで確認します。",
    }
)
TABLE_OR_DEFINITION_LABELS: Final = frozenset(
    {
        "商品",
        "比較軸",
        "外寸",
        "外寸(幅×奥行×高さ)",
        "寸法(幅×奥行×高さ)",
        "非拡張時の外寸(幅×奥行×高さ)",
        "通常時外寸(幅×奥行×高さ)",
        "通常時寸法(幅×奥行×高さ)",
        "本体",
        "本体(幅×奥行×高さ)",
        "本体寸法",
        "本体寸法(幅×奥行×高さ)",
        "台(幅×奥行×高さ)",
        "台の筐体(幅×奥行×高さ)",
        "ステーション",
        "ステーション寸法(公式表記)",
        "ステーション寸法(幅×奥行×高さ)",
        "開扉",
        "開扉時奥行",
        "3辺合計",
        "基本容量",
        "容量",
        "通常時容量",
        "標準収納容量",
        "標準食器点数",
        "標準使用水量",
        "使用水量",
        "重量",
        "本体重量",
        "質量",
        "定格出力",
        "アクセス方法",
        "前開きの整理",
        "前面",
        "構造",
        "特徴",
        "現行仕様",
        "使い分け",
        "選ぶ理由",
        "固有の検討軸",
        "向く人",
        "向く条件",
        "別の候補が向く条件",
        "別の情報が必要な条件",
        "購入前の確認",
        "再入荷後に向く条件",
        "再確認すること",
        "注意",
        "注意点",
        "拡張",
        "拡張時",
        "型番",
        "世代固有機能・拡張性",
        "水拭き",
        "自動手入れ",
        "手入れ",
        "自動ゴミ収集",
        "収集",
        "紙パック容量",
        "ステーション機能",
        "アプリ / Wi-Fi",
        "連携",
        "接続",
        "乾燥",
        "乾燥方式",
        "乾燥の案内",
        "乾燥・扉",
        "端子",
        "家庭内設定",
        "共通の確認",
        "鍋やフライパン",
        "仕様だけでは分からないこと",
    }
)
PRODUCT_NEUTRAL_ALT_SUFFIX: Final = (
    "を比較検討するための中立イメージ。商品写真ではありません"
)


class CoverageFailure(RuntimeError):
    """Closed-world reader coverage or evidence binding is invalid."""


def _fail(detail: str) -> NoReturn:
    raise CoverageFailure(f"READER_CLAIM_COVERAGE_INVALID: {detail}") from None


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def _literal_occurrence_starts(value: str, token: str) -> list[int]:
    """Find literal occurrences without matching inside another numeric/model token."""

    normalized = _normalize_text(value).casefold()
    needle = _normalize_text(token).casefold()
    prefix = r"(?<![A-Za-z0-9_.])" if needle and needle[0].isascii() else ""
    suffix = r"(?![A-Za-z0-9_.])" if needle and needle[-1].isascii() else ""
    return [
        match.start()
        for match in re.finditer(prefix + re.escape(needle) + suffix, normalized)
    ]


def _site_domain(hostname: str) -> str:
    labels = hostname.casefold().rstrip(".").split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in {
        "co.jp",
        "ne.jp",
        "or.jp",
        "com.au",
        "co.uk",
    }:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _support_key(value: str) -> str:
    normalized = _normalize_text(value).casefold()
    normalized = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", normalized)
    normalized = normalized.replace("機内持込み", "機内持ち込み")
    normalized = normalized.replace("～", "〜")
    normalized = re.sub(r"最も軽(?:い|く)?", "最軽量", normalized)
    normalized = re.sub(r"最も重(?:い|く)?", "最重量", normalized)
    normalized = re.sub(r"最も大き(?:い|く)?", "最大", normalized)
    normalized = re.sub(r"最も小さ(?:い|く)?", "最小", normalized)
    normalized = re.sub(
        r"(?:2way(?:オープン)?|2通り(?:の開き方)?)", "2通り", normalized
    )
    normalized = re.sub(r"(?:フロントオープン|前開き)", "frontopen", normalized)
    normalized = re.sub(r"(?:センターオープン|中央開き)", "centeropen", normalized)
    normalized = re.sub(
        r"usb\s*(?:type)?-?a\s*[/／・]\s*type-?c", "usba/usbc", normalized
    )
    normalized = re.sub(r"usb\s*(?:type)?-?a", "usba", normalized)
    normalized = re.sub(r"usb\s*(?:type)?-?c", "usbc", normalized)
    normalized = re.sub(r"usb\s*(?:ポート|端子)", "usb", normalized)
    normalized = re.sub(r"(?:独立)?pc\s*(?:収納|ポケット)", "pcstorage", normalized)
    normalized = re.sub(
        r"(?:メイン収納(?:全体)?へ(?:アクセス(?:できる)?|届く)|"
        r"メイン収納へのアクセス|前(?:側|面)?から(?:メイン収納)?全体へ"
        r"(?:アクセス|届く)|メインへアクセス)",
        "mainstorageaccess",
        normalized,
    )
    normalized = re.sub(
        r"(?:手動(?:で)?(?:の)?ごみ捨て|手動で空に(?:する|します)?)",
        "自動ゴミ収集なし",
        normalized,
    )
    normalized = re.sub(r"(?:自動ドア開放|オートオープン)", "autoopen", normalized)
    normalized = re.sub(
        r"(?:市販の)?(?:使い捨て)?お?掃除シート(?:式)?|使い捨てシート式",
        "disposablesheet",
        normalized,
    )
    normalized = re.sub(
        r"(?:交換用静音タイヤキット|交換可能車輪|車輪を交換)",
        "replaceablewheel",
        normalized,
    )
    normalized = re.sub(
        r"拡張(?:機能(?:あり)?|対応|できる|すると|時|後)",
        "expansion",
        normalized,
    )
    normalized = re.sub(r"リフトアップ(?:オープン)?ドア", "liftupdoor", normalized)
    normalized = re.sub(
        r"(?:(?:を|は|には|が)?(?:搭載|装備|対応)(?:されて|して)?"
        r"い(?:ない|ません)|(?:を|は|には|が)?備えていません|"
        r"(?:を|は|には|が)?備えていない|(?:を|は)?行わない|"
        r"(?:は|が)?できない|"
        r"(?:が|は|では|とは)(?:なく|ない)|非搭載|未搭載|非対応)",
        "negative",
        normalized,
    )
    normalized = re.sub(
        r"(?:(?:は|には|に)?(?:なし|ない|ありません|対応しない|対応しません|非対応|廃止))",
        "negative",
        normalized,
    )
    normalized = re.sub(
        r"(?:在庫切れ|売り切れ|売切れ|欠品中|品切れ|完売|再入荷待ち|"
        r"out_of_stock)",
        "outofstock",
        normalized,
    )
    normalized = re.sub(r"(?:販売終了|終売)", "discontinued", normalized)
    normalized = re.sub(
        r"(?:在庫あり|販売中|購入可能|現在購入できます|購入できます|注文できます)",
        "available",
        normalized,
    )
    normalized = re.sub(r"(?<![a-z])no\.(?=\d)", "", normalized)
    return normalized


def _is_feature_assertion_token(value: str) -> bool:
    match = FEATURE_ASSERTION_RE.match(value)
    return match is not None and (
        match.end() == len(value)
        or FEATURE_POLARITY_SUFFIX_RE.fullmatch(value[match.end() :]) is not None
    )


def _predicate_is_negative(value: str) -> bool:
    return bool(
        re.search(
            r"(?:negative|非搭載|未搭載|非対応|ではない|ではありません|"
            r"でない|対応しない|対応しません|備えていない|"
            r"備えていません|行わない|なし|ない|ありません)",
            value,
        )
    )


def _feature_supported(token: str, support: str) -> bool:
    token_match = FEATURE_ASSERTION_RE.match(token)
    if token_match is None:
        return False
    token_key = _support_key(token)
    raw_feature_key = _support_key(token_match.group(0))
    feature_key = raw_feature_key.replace("negative", "")
    support_key = _support_key(support)
    token_negative = _predicate_is_negative(token_key)
    feature_keys = {
        _support_key(candidate.group(0)).replace("negative", "")
        for candidate in FEATURE_ASSERTION_RE.finditer(_normalize_text(support))
    }
    feature_starts = sorted(
        candidate.start()
        for candidate_key in feature_keys
        for candidate in re.finditer(re.escape(candidate_key), support_key)
    )
    for match in re.finditer(re.escape(feature_key), support_key):
        start = max(
            support_key.rfind(marker, 0, match.start())
            for marker in ("。", "；", ";", "、")
        )
        ends = [
            index
            for marker in ("。", "；", ";", "、")
            if (index := support_key.find(marker, match.end())) >= 0
        ]
        ends.extend(start for start in feature_starts if start > match.start())
        end = min(ends) if ends else len(support_key)
        clause = support_key[start + 1 : end]
        if _predicate_is_negative(clause) == token_negative:
            return True
    return False


def _generic_qualitative_supported(token: str, support: str) -> bool:
    token_match = GENERIC_QUALITATIVE_ASSERTION_RE.match(token)
    if token_match is None:
        return False
    predicate = _support_key(token_match.group(0))
    token_negative = _predicate_is_negative(_support_key(token)[len(predicate) :])
    support_key = _support_key(support)
    for match in re.finditer(re.escape(predicate), support_key):
        ends = [
            index
            for marker in ("。", "；", ";", "、")
            if (index := support_key.find(marker, match.end())) >= 0
        ]
        end = min(ends) if ends else len(support_key)
        if _predicate_is_negative(support_key[match.end() : end]) == token_negative:
            return True
    return False


def _closed_wifi_band_boundary_supported(
    token: str, reader_text: str, support: str
) -> bool:
    """Bind the closed 5GHz exclusion implied by official 2.4GHz-only text."""

    return bool(
        _support_key(token) == "5ghz"
        and re.search(
            r"5\s*ghz(?:のみのssidでは設定できません|対応を優先する)",
            _normalize_text(reader_text),
            re.IGNORECASE,
        )
        and re.search(
            r"2[.]4\s*ghz(?:\s*wi-fi)?(?:だけ|のみ)に?対応",
            _normalize_text(support),
            re.IGNORECASE,
        )
    )


def _named_dimensions_cm(
    value: str,
) -> list[tuple[str, Decimal, Decimal, Decimal]]:
    """Parse closed width/depth/height expressions with axis semantics.

    A final unit may be shared by the preceding values, as in normal Japanese
    product copy (``幅35×奥行25×高さ55cm``).  Axis order is mandatory so a
    width/height swap cannot be accepted merely because the three values are
    present somewhere in a source statement.
    """

    result: list[tuple[str, Decimal, Decimal, Decimal]] = []
    for match in NAMED_DIMENSION_ASSERTION_RE.finditer(_normalize_text(value)):
        trailing_unit = match.group("height_unit").casefold()
        values: list[Decimal] = []
        try:
            for value_group, unit_group in (
                ("width", "width_unit"),
                ("depth", "depth_unit"),
                ("height", "height_unit"),
            ):
                raw = Decimal(match.group(value_group).replace(",", ""))
                unit = (match.group(unit_group) or trailing_unit).casefold()
                values.append(raw / 10 if unit == "mm" else raw)
        except InvalidOperation, AttributeError:
            continue
        subject = _dimension_subject_role(match.group("dimension_subject") or "")
        result.append((subject, values[0], values[1], values[2]))
    return result


def _dimension_subject_role(value: str) -> str:
    return (
        "OPEN"
        if re.search(r"(?:開扉|開放|開閉|扉を開いた)", value)
        else "STATION"
        if re.search(r"(?:ステーション|充電台|充電スタンド|台の筐体)", value)
        else "EXPANDED"
        if "拡張時" in value
        else "NORMAL"
        if "通常時" in value
        else "BODY"
        if "本体" in value
        else "UNSPECIFIED"
    )


def _dimension_roles_compatible(expected: str, actual: str) -> bool:
    """Return whether two explicit dimension roles describe the same object.

    ``BODY`` and ``NORMAL`` are compatible descriptions of an unexpanded
    product body, and a source with one unqualified dimension set is allowed
    to support either.  Station/open/expanded measurements remain strictly
    isolated because swapping those values is decision-critical.
    """

    if expected == "UNSPECIFIED":
        return True
    if expected in {"BODY", "NORMAL"}:
        return actual in {"UNSPECIFIED", "BODY", "NORMAL"}
    return actual == expected


def _local_dimension_role(
    text: str, token: str, fallback: str | None, occurrence_index: int = 0
) -> str | None:
    """Resolve a dimension role at the assertion occurrence, not unit-wide.

    Reader units often contain both a normal and expanded size or both a body
    and station size.  Applying one unit-level role to all numbers would make
    an axis-correct value semantically wrong.  Explicit wording in the token
    wins; otherwise a bounded clause prefix is used.  The common compact form
    ``normal-size / 拡張時 expanded-size`` assigns NORMAL to the first
    otherwise-unlabelled triplet.
    """

    # A plate/wheel diameter is an object measurement, not a door-clearance
    # measurement.  Nearby wording such as ``自動ドア開放`` must not turn it
    # into an OPEN dimension merely because both occur in one paragraph.
    scalar = _axis_scalar_dimensions_cm(token)
    if scalar and scalar[0][1] == "DIAMETER":
        return None
    direct = _dimension_subject_role(token)
    if direct != "UNSPECIFIED":
        return direct
    normalized = _normalize_text(text)
    normalized_token = _normalize_text(token)
    starts = _literal_occurrence_starts(normalized, normalized_token)
    if occurrence_index >= len(starts):
        return fallback
    start = starts[occurrence_index]
    boundary = max(
        normalized.rfind(marker, 0, start)
        for marker in ("。", "；", ";", "、", "・", "/", "／")
    )
    prefix = normalized[boundary + 1 : start]
    prefix = prefix[-48:]
    roles: set[str] = set()
    if re.search(r"(?:開扉|扉開放|ドア開放|ドア開閉|扉を開いた)", prefix):
        roles.add("OPEN")
    if re.search(r"(?:ステーション|充電台|充電スタンド|台の筐体)", prefix):
        roles.add("STATION")
    without_normal = re.sub(r"非拡張時", "", prefix)
    if "非拡張時" in prefix or "通常時" in prefix:
        roles.add("NORMAL")
    if re.search(r"拡張(?:時|後|すると|した状態)", without_normal):
        roles.add("EXPANDED")
    if "本体" in prefix:
        roles.add("BODY")
    if len(roles) == 1:
        return next(iter(roles))
    if fallback == "OPEN" and re.search(
        r"(?:開扉|扉開放|ドア開放|ドア開閉|扉を開いた)",
        normalized[start + len(normalized_token) :],
    ):
        # A unit can state the body dimensions first and its opened depth
        # later.  The unit-wide fallback is OPEN, but only values after the
        # explicit open marker inherit that role.
        return "BODY"
    dimension_occurrences = sorted(
        (
            match.start(),
            match.group(0),
        )
        for pattern in (NAMED_DIMENSION_ASSERTION_RE, ORDERED_DIMENSION_ASSERTION_RE)
        for match in pattern.finditer(normalized)
    )
    if (
        dimension_occurrences
        and start == dimension_occurrences[0][0]
        and any(
            "拡張時" in normalized[first_start:start_after]
            for (first_start, _), (start_after, _) in zip(
                dimension_occurrences, dimension_occurrences[1:]
            )
        )
    ):
        return "NORMAL"
    return fallback


def _local_dimension_axis(
    text: str, token: str, fallback: str | None, occurrence_index: int = 0
) -> str | None:
    if THREE_SIDE_SUM_ASSERTION_RE.fullmatch(_normalize_text(token)) is not None:
        return "TOTAL"
    scalar = _axis_scalar_dimensions_cm(token)
    if scalar:
        return scalar[0][1]
    normalized = _normalize_text(text)
    normalized_token = _normalize_text(token)
    starts = _literal_occurrence_starts(normalized, normalized_token)
    if occurrence_index >= len(starts):
        return fallback
    start = starts[occurrence_index]
    if "最大底面辺" in normalized[max(0, start - 32) : start]:
        return fallback
    shared_axis = re.search(
        r"それぞれ[^。；;]{0,24}(幅|奥行|高さ|直径)"
        r"\s*\d+(?:[.,]\d+)?\s*(?:cm|mm)\s*[、,]\s*$",
        normalized[max(0, start - 64) : start],
    )
    if shared_axis is not None:
        return {
            "幅": "WIDTH",
            "奥行": "DEPTH",
            "高さ": "HEIGHT",
            "直径": "DIAMETER",
        }[shared_axis.group(1)]
    boundary = max(
        normalized.rfind(marker, 0, start) for marker in ("。", "；", ";", "、", ",")
    )
    prefix = normalized[max(boundary + 1, start - 24) : start]
    axes = {
        axis
        for marker, axis in (
            ("幅", "WIDTH"),
            ("横", "WIDTH"),
            ("奥行", "DEPTH"),
            ("前後", "DEPTH"),
            ("高さ", "HEIGHT"),
            ("縦", "HEIGHT"),
            ("直径", "DIAMETER"),
        )
        if marker in prefix
    }
    return next(iter(axes)) if len(axes) == 1 else fallback


def _axis_scalar_dimensions_cm(
    value: str,
) -> list[tuple[str, str, Decimal, str]]:
    result: list[tuple[str, str, Decimal, str]] = []
    normalized = _normalize_text(value)
    # A named triplet is parsed atomically by ``_named_dimensions_cm``.  Do not
    # parse its three inner axes a second time as unqualified scalars: doing so
    # would erase the BODY/OPEN/STATION role carried by the triplet and allow,
    # for example, an OPEN depth to satisfy a BODY-depth assertion.
    compound_spans = tuple(
        (match.start(), match.end())
        for pattern in (NAMED_DIMENSION_ASSERTION_RE, ORDERED_DIMENSION_ASSERTION_RE)
        for match in pattern.finditer(normalized)
    )
    previous_end: int | None = None
    previous_role = "UNSPECIFIED"
    for match in AXIS_SCALAR_ASSERTION_RE.finditer(normalized):
        if any(
            match.start() >= start and match.end() <= end
            for start, end in compound_spans
        ):
            continue
        raw = Decimal(match.group("value").replace(",", ""))
        if match.group("unit").casefold() == "mm":
            raw /= 10
        axis = {
            "幅": "WIDTH",
            "奥行": "DEPTH",
            "高さ": "HEIGHT",
            "直径": "DIAMETER",
        }[match.group("axis")]
        role = _dimension_subject_role(match.group("dimension_subject") or "")
        if (
            role == "UNSPECIFIED"
            and previous_end is not None
            and previous_role != "UNSPECIFIED"
            and match.start() - previous_end <= 24
            and not re.search(r"[。；;／/]", normalized[previous_end : match.start()])
        ):
            # Japanese specifications commonly state the object once and then
            # coordinate its remaining axes: ``開扉時 幅… 奥行… 高さ…``.
            # Preserve that role across the coordinated scalar sequence.
            role = previous_role
        result.append(
            (
                role,
                axis,
                raw,
                _numeric_operator(match.group("suffix") or ""),
            )
        )
        previous_end = match.end()
        previous_role = role
    for match in OPEN_DEPTH_ASSERTION_RE.finditer(normalized):
        raw = Decimal(match.group("value").replace(",", ""))
        if match.group("unit").casefold() == "mm":
            raw /= 10
        candidate = (
            "OPEN",
            "DEPTH",
            raw,
            _numeric_operator(match.group("suffix") or ""),
        )
        if candidate not in result:
            result.append(candidate)
    return result


def _three_side_sums_cm(value: str) -> list[tuple[Decimal, str]]:
    result: list[tuple[Decimal, str]] = []
    for match in THREE_SIDE_SUM_ASSERTION_RE.finditer(_normalize_text(value)):
        amount = Decimal(match.group("value").replace(",", ""))
        if match.group("unit").casefold() == "mm":
            amount /= 10
        result.append((amount, _numeric_operator(match.group("suffix") or "")))
    return result


def _ordered_dimensions_cm(
    value: str,
) -> list[tuple[Decimal, Decimal, Decimal]]:
    result: list[tuple[Decimal, Decimal, Decimal]] = []
    for match in ORDERED_DIMENSION_ASSERTION_RE.finditer(_normalize_text(value)):
        trailing_unit = match.group("height_unit").casefold()
        values: list[Decimal] = []
        try:
            for value_group, unit_group in (
                ("width", "width_unit"),
                ("depth", "depth_unit"),
                ("height", "height_unit"),
            ):
                raw = Decimal(match.group(value_group).replace(",", ""))
                unit = (match.group(unit_group) or trailing_unit).casefold()
                values.append(raw / 10 if unit == "mm" else raw)
        except InvalidOperation, AttributeError:
            continue
        result.append((values[0], values[1], values[2]))
    return result


MEASURED_ASSERTION_RE: Final = re.compile(
    r"(?P<number>\d+(?:[.,]\d+)?)"
    r"(?P<unit>cm|mm|m|kg|ghz|hz|kwh|wh|w|pa|l|v|口|点|個|席|人|台|回|時間|分|秒|インチ)"
    r"(?P<suffix>では(?:ない|ありません)|未満|以下|以内|以上|"
    r"を(?:超え(?:る|ます)?|上回(?:る|ります)?)|"
    r"より(?:大きい|小さい|多い|少ない))?",
    re.IGNORECASE,
)


def _numeric_operator(suffix: str) -> str:
    if not suffix:
        return "EQ"
    if suffix.startswith("では"):
        return "NE"
    if suffix == "未満" or suffix.endswith("小さい") or suffix.endswith("少ない"):
        return "LT"
    if suffix in {"以下", "以内"}:
        return "LE"
    if suffix == "以上":
        return "GE"
    return "GT"


def _exact_value_satisfies(
    source_value: Decimal, threshold: Decimal, operator: str
) -> bool:
    """Evaluate a reader comparator against one exact source value."""

    return (
        (operator == "EQ" and source_value == threshold)
        or (operator == "NE" and source_value != threshold)
        or (operator == "LT" and source_value < threshold)
        or (operator == "LE" and source_value <= threshold)
        or (operator == "GE" and source_value >= threshold)
        or (operator == "GT" and source_value > threshold)
    )


def _measured_assertion(value: str) -> tuple[str, str, str] | None:
    match = MEASURED_ASSERTION_RE.fullmatch(_support_key(value))
    if match is None:
        return None
    return (
        match.group("number").replace(",", ""),
        match.group("unit").casefold(),
        _numeric_operator(match.group("suffix") or ""),
    )


def _measured_supported(number: str, unit: str, operator: str, support: str) -> bool:
    support_key = _support_key(support)
    # Decimal spelling is not semantic: ``24.0cm`` and ``24cm`` describe the
    # same exact measurement.  Compare parsed values before the legacy
    # spelling-preserving scan so a harmless trailing zero cannot orphan a
    # reader claim.  Unit conversion remains deliberately limited to cm/mm;
    # no approximate conversion or tolerance is introduced.
    requested_value = Decimal(number)
    for match in MEASURED_ASSERTION_RE.finditer(support_key):
        support_value = Decimal(match.group("number").replace(",", ""))
        support_unit = match.group("unit").casefold()
        if unit == support_unit:
            same_value = requested_value == support_value
        elif unit == "cm" and support_unit == "mm":
            same_value = requested_value * 10 == support_value
        elif unit == "mm" and support_unit == "cm":
            same_value = requested_value == support_value * 10
        else:
            same_value = False
        support_operator = _numeric_operator(match.group("suffix") or "")
        if same_value and support_operator == operator:
            return True
        # An exact official value can prove a reader-facing threshold without
        # requiring the source sentence to repeat that editorial comparator.
        # This is ordinary decimal arithmetic, not fuzzy matching: 24.8cm can
        # establish ``25cm以下`` while 25cm cannot establish ``25cm未満``.
        if support_operator == "EQ":
            if unit == support_unit:
                comparable_value = support_value
            elif unit == "cm" and support_unit == "mm":
                comparable_value = support_value / 10
            elif unit == "mm" and support_unit == "cm":
                comparable_value = support_value * 10
            else:
                comparable_value = None
            if comparable_value is not None and _exact_value_satisfies(
                comparable_value, requested_value, operator
            ):
                return True
    candidates = [(number, unit)]
    numeric_value = Decimal(number)
    if unit == "cm":
        candidates.append((f"{numeric_value * 10:g}", "mm"))
    elif unit == "mm":
        candidates.append((f"{numeric_value / 10:g}", "cm"))
    for candidate_number, candidate_unit in candidates:
        pattern = re.compile(
            rf"(?<![.\d]){re.escape(candidate_number)}(?![.\d])\s*"
            rf"{re.escape(candidate_unit)}(?![a-z])"
            rf"(?P<suffix>では(?:ない|ありません)|未満|以下|以内|以上|"
            rf"を(?:超え(?:る|ます)?|上回(?:る|ります)?)|"
            rf"より(?:大きい|小さい|多い|少ない))?",
            re.IGNORECASE,
        )
        if any(
            _numeric_operator(match.group("suffix") or "") == operator
            for match in pattern.finditer(support_key)
        ):
            return True
    return False


def _token_supported(
    token: str,
    support: str,
    *,
    dimension_role: str | None = None,
    dimension_axis: str | None = None,
) -> bool:
    token_key = _support_key(token)
    support_key = _support_key(support)
    band_match = BAND_ASSERTION_RE.fullmatch(token_key)
    if band_match is not None:
        lower = Decimal(re.match(r"\d+(?:[.,]\d+)?", token_key).group(0))
        return any(
            match.group("unit").casefold() == "kg"
            and lower <= Decimal(match.group("number").replace(",", "")) < lower + 1
            and _numeric_operator(match.group("suffix") or "") == "EQ"
            for match in MEASURED_ASSERTION_RE.finditer(support_key)
        )
    if RANGE_ASSERTION_RE.fullmatch(token_key) is not None:
        if token_key in support_key:
            return True
        range_match = re.fullmatch(
            r"(?P<lower>\d+(?:[.,]\d+)?)\s*[〜～]\s*"
            r"(?P<upper>\d+(?:[.,]\d+)?)\s*"
            r"(?P<unit>cm|mm|m|kg|kWh|Wh|W|Pa|L|口|点|個|席|人|台|回|"
            r"時間|分|秒|年|月|日)",
            token_key,
            re.IGNORECASE,
        )
        assert range_match is not None
        unit = range_match.group("unit").casefold()
        endpoints = {
            Decimal(range_match.group("lower").replace(",", "")),
            Decimal(range_match.group("upper").replace(",", "")),
        }
        supported_values = {
            Decimal(match.group("number").replace(",", ""))
            for match in MEASURED_ASSERTION_RE.finditer(support_key)
            if match.group("unit").casefold() == unit
            and _numeric_operator(match.group("suffix") or "") == "EQ"
        }
        # A compact range may summarize an explicitly closed comparison claim
        # whose statement lists both exact endpoints separately.  Requiring
        # both endpoints (and later the complete claim-subject coverage) avoids
        # treating an isolated minimum or maximum as proof of the range.
        return endpoints <= supported_values
    count_match = COUNT_ASSERTION_RE.fullmatch(token_key)
    if count_match is not None:
        number_match = re.match(r"\d+", token_key)
        assert number_match is not None
        number = number_match.group(0)
        category = (
            r"(?:モデル|機種|候補)"
            if re.search(r"(?:モデル|機種|候補)\Z", token_key)
            else "製品"
            if token_key.endswith("製品")
            else "構成"
        )
        return bool(re.search(rf"(?<!\d){number}\s*{category}", support_key))
    token_sums = _three_side_sums_cm(token)
    if token_sums:
        token_value, token_operator = token_sums[0]
        return any(
            support_value == token_value and support_operator == token_operator
            for support_value, support_operator in _three_side_sums_cm(support)
        )
    token_dimensions = _named_dimensions_cm(token)
    if token_dimensions:
        token_subject, *token_values = token_dimensions[0]
        expected_subject = (
            dimension_role
            if token_subject == "UNSPECIFIED" and dimension_role is not None
            else token_subject
        )
        return any(
            token_values == support_values
            and _dimension_roles_compatible(expected_subject, support_subject)
            for support_subject, *support_values in _named_dimensions_cm(support)
        )
    ordered_dimensions = _ordered_dimensions_cm(token)
    if ordered_dimensions:
        expected = ordered_dimensions[0]
        named_support = _named_dimensions_cm(support)
        # An official unlabelled three-value string can support only that same
        # ordered string.  It does not acquire width/depth/height semantics,
        # but it remains a valid claim about the literal manufacturer text.
        if expected in _ordered_dimensions_cm(support):
            return True
        if dimension_role is not None:
            return any(
                tuple(values) == expected
                and _dimension_roles_compatible(dimension_role, subject)
                for subject, *values in named_support
            )
        return any(tuple(values) == expected for _, *values in named_support)
    scalar_dimensions = _axis_scalar_dimensions_cm(token)
    if scalar_dimensions:
        token_subject, token_axis, token_value, token_operator = scalar_dimensions[0]
        if dimension_axis is not None and token_axis != dimension_axis:
            return False
        if (
            dimension_role is not None
            and token_subject != "UNSPECIFIED"
            and not _dimension_roles_compatible(dimension_role, token_subject)
        ):
            return False
        expected_subject = (
            dimension_role
            if token_subject == "UNSPECIFIED" and dimension_role is not None
            else token_subject
        )
        scalar_supports = any(
            support_axis == token_axis
            and (
                (support_value == token_value and support_operator == token_operator)
                or (
                    support_operator == "EQ"
                    and _exact_value_satisfies(
                        support_value, token_value, token_operator
                    )
                )
            )
            and _dimension_roles_compatible(expected_subject, support_subject)
            for support_subject, support_axis, support_value, support_operator in _axis_scalar_dimensions_cm(
                support
            )
        )
        if scalar_supports:
            return True
        # The source contract prefers a semantically named triplet over three
        # duplicated scalar claims.  Project the requested axis from that
        # exact triplet while preserving its BODY/STATION/OPEN subject role.
        # This also lets an exact official value prove a true editorial
        # threshold (24.8cm <= 25cm) without fuzzy tolerance.
        axis_index = {"WIDTH": 0, "DEPTH": 1, "HEIGHT": 2}.get(token_axis)
        if axis_index is None:
            return False
        return any(
            _exact_value_satisfies(values[axis_index], token_value, token_operator)
            and _dimension_roles_compatible(expected_subject, support_subject)
            for support_subject, *values in _named_dimensions_cm(support)
        )
    measured_assertion = _measured_assertion(token)
    if measured_assertion is not None:
        number, unit, operator = measured_assertion
        # A reader-facing ``最大底面辺`` is intentionally stored as one bare
        # measurement token: the surrounding unit metadata carries the
        # product role, while the source packet retains the authoritative
        # width/depth/height triplet.  A compact triplet shares ``cm`` only at
        # its final value, so the generic measured-value scan below cannot see
        # the width or depth.  Derive only the exact maximum of width/depth for
        # the requested role; height must never satisfy this footprint token.
        if (
            unit in {"cm", "mm"}
            and dimension_role is not None
            and dimension_axis is None
        ):
            value_cm = Decimal(number) / 10 if unit == "mm" else Decimal(number)
            if any(
                _exact_value_satisfies(max(width, depth), value_cm, operator)
                and _dimension_roles_compatible(dimension_role, support_subject)
                for support_subject, width, depth, _height in _named_dimensions_cm(
                    support
                )
            ):
                return True
        if unit in {"cm", "mm"} and dimension_axis is not None:
            value_cm = Decimal(number) / 10 if unit == "mm" else Decimal(number)
            if any(
                support_axis == dimension_axis
                and (
                    (support_value == value_cm and support_operator == operator)
                    or (
                        support_operator == "EQ"
                        and _exact_value_satisfies(support_value, value_cm, operator)
                    )
                )
                and (
                    dimension_role is None
                    or _dimension_roles_compatible(dimension_role, support_subject)
                )
                for support_subject, support_axis, support_value, support_operator in _axis_scalar_dimensions_cm(
                    support
                )
            ):
                return True
            return False
        if _measured_supported(number, unit, operator, support):
            return True
        if operator != "EQ":
            return False
    measured = re.fullmatch(
        r"(\d+(?:[.,]\d+)?)(cm|mm|m|kg|ghz|hz|kwh|wh|w|pa|l|v|口|点|個|席|人|台|回|時間|分|秒|インチ)",
        token_key,
        re.IGNORECASE,
    )
    if measured is not None:
        number, unit = measured.groups()
        number_pattern = rf"(?<![.\d]){re.escape(number)}(?![.\d])"
        unit_pattern = rf"{re.escape(unit)}(?![a-z])"
        if re.search(rf"{number_pattern}\s*{unit_pattern}", support_key, re.IGNORECASE):
            return True
        # Exact cm/mm conversion is a semantic identity, not an approximate
        # numeric match.  It is deliberately limited to these two units.
        numeric_value = float(number.replace(",", ""))
        converted: tuple[float, str] | None = None
        if unit.casefold() == "cm":
            converted = (numeric_value * 10, "mm")
        elif unit.casefold() == "mm":
            converted = (numeric_value / 10, "cm")
        if converted is not None:
            converted_number, converted_unit = converted
            converted_display = f"{converted_number:g}"
            if re.search(
                rf"(?<![.\d]){re.escape(converted_display)}(?![.\d])\s*"
                rf"{converted_unit}(?![a-z])",
                support_key,
                re.IGNORECASE,
            ):
                return True
        # Official specifications sometimes share one unit across a compact
        # normal/expanded pair (``36/42L`` or ``36（拡張時42）L``).  Accept only
        # those two closed syntaxes.  Arbitrary intervening quantities/units
        # must never lend their trailing unit to the first number.
        paired = (
            rf"{number_pattern}\s*[/／]\s*\d+(?:[.,]\d+)?\s*{unit_pattern}",
            rf"{number_pattern}\s*[（(]\s*(?:拡張時|通常時)?\s*"
            rf"\d+(?:[.,]\d+)?\s*[）)]\s*{unit_pattern}",
        )
        return any(re.search(pattern, support_key, re.IGNORECASE) for pattern in paired)
    if re.fullmatch(r"\d+(?:[.,]\d+)?", token_key):
        return bool(
            re.search(
                rf"(?<![a-z0-9.]){re.escape(token_key)}(?![.\d])",
                support_key,
            )
        )
    if re.search(r"\d", token_key):
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(token_key)}(?![a-z0-9])",
                support_key,
            )
        )
    if _is_feature_assertion_token(token):
        return _feature_supported(token, support)
    generic_match = GENERIC_QUALITATIVE_ASSERTION_RE.match(token)
    if generic_match is not None and (
        generic_match.end() == len(token)
        or GENERIC_QUALITATIVE_POLARITY_SUFFIX_RE.fullmatch(
            token[generic_match.end() :]
        )
        is not None
    ):
        return _generic_qualitative_supported(token, support)
    return token_key in support_key


def _sales_variant_scope_is_explicit(
    reader_text: str, caveat: dict[str, object]
) -> bool:
    """Require the exact observed variant before a caveated row can support prose."""

    normalized = _normalize_text(reader_text).casefold()
    code = caveat.get("code")
    required_markers = {
        "OTHER_COLOR_NOT_ATTESTED": ("ブラック", "t2292511"),
        "IVORY_VARIANT_ONLY": ("アイボリー",),
        "STANDARD_PRODUCT_ONLY": ("ss-ma251", "通常商品"),
        "OFFICIAL_MODEL_VARIANTS_ONLY": (
            "ブルーグレー",
            "シルバー",
            "ブラックヘアライン",
            "60570",
        ),
    }.get(code)
    return required_markers is not None and any(
        marker.casefold() in normalized for marker in required_markers
    )


def _sales_token_supported(
    token: str,
    state: dict[str, object],
    reader_text: str | None = None,
    occurrence_index: int = 0,
) -> bool:
    """Match availability language only against structured state polarity.

    Locator/basis prose is deliberately excluded: negated phrases such as
    "販売終了の明記はない" and mixed-variant caveats must never prove the
    opposite reader-facing assertion.
    """

    if state.get("availability_scope") not in {"MODEL", "VARIANT"}:
        return False
    raw_caveat = state.get("variant_caveat")
    if raw_caveat is not None:
        if type(raw_caveat) is not dict or reader_text is None:
            return False
        if not _sales_variant_scope_is_explicit(
            reader_text, cast(dict[str, object], raw_caveat)
        ):
            return False
    normalized = _normalize_text(token)
    expected = (
        "UNKNOWN"
        if (
            re.fullmatch(
                r"販売状態(?:は|を)?(?:未確認|確認できな(?:い|かった|く|せん))",
                normalized,
            )
            or (
                reader_text is not None
                and _sales_occurrence_is_unknown(
                    normalized, reader_text, occurrence_index
                )
            )
        )
        else "OUT_OF_STOCK"
        if re.fullmatch(
            r"(?:購入UIを確認できな(?:い|かった|く|せん)|"
            r"再入荷(?:\(予約開始\))?通知(?:のみ|だけ)?|"
            r"在庫切れ|売り切れ|売切れ|欠品中|品切れ|完売|再入荷待ち|"
            r"在庫なし|購入不可)",
            normalized,
        )
        else "AVAILABLE"
        if re.fullmatch(
            r"(?:購入UIを確認でき(?:る|た|ました)|"
            r"現行(?:販売|表示|品|モデル|製品)?|"
            r"在庫あり|販売中|購入可能|現在購入できます|購入できます|"
            r"注文できます|予約受付中|残りわずか|"
            r"販売再開(?:中|済み|しました))",
            normalized,
        )
        else "DISCONTINUED"
        if normalized in {"生産終了", "販売終了", "終売", "取扱終了"}
        else None
    )
    return expected is not None and state.get("state") == expected


def _sales_occurrence_is_unknown(
    token: str, reader_text: str, occurrence_index: int
) -> bool:
    normalized_text = _normalize_text(reader_text)
    normalized_token = _normalize_text(token)
    if normalized_token == "現行":
        return False
    starts = _literal_occurrence_starts(normalized_text, normalized_token)
    if not 0 <= occurrence_index < len(starts):
        return False
    start = starts[occurrence_index]
    if (
        re.fullmatch(
            r"(?:在庫切れ|売り切れ|売切れ|欠品中|品切れ|完売|"
            r"再入荷待ち|在庫なし|購入不可)",
            normalized_token,
        )
        and EXTERNAL_OUT_OF_STOCK_UI_GAP_RE.search(normalized_text) is not None
    ):
        return False
    suffix = normalized_text[start + len(normalized_token) :]
    return bool(
        re.match(
            r"^(?:は|を|が|[:：])?[^ 。、！？]{0,24}"
            r"(?:未確認|確認できな(?:い|かった|く)|"
            r"確認できません|確認できていない|"
            r"確認していない|状態を確認できるまで)",
            suffix,
        )
    )


def _sales_match_is_unknown(match: re.Match[str], text: str) -> bool:
    token = match.group(0)
    if re.fullmatch(
        r"販売状態(?:は|を)?(?:未確認|確認できな(?:い|かった|く|せん))",
        _normalize_text(token),
    ):
        return True
    preceding = text[: match.start()]
    occurrence_index = len(_literal_occurrence_starts(preceding, token))
    return _sales_occurrence_is_unknown(token, text, occurrence_index)


def _affirmed_sales_matches(text: str) -> tuple[re.Match[str], ...]:
    """Return availability lexemes that are asserted, not locally negated."""

    normalized = _normalize_text(text)
    return tuple(
        match
        for match in SALES_STATE_ASSERTION_RE.finditer(normalized)
        if SALES_LOCAL_NEGATION_SUFFIX_RE.match(normalized[match.end() :]) is None
    )


def _sales_unknown_overlap(text: str) -> bool:
    """Detect uncertainty governing an asserted sales state, sentence-locally."""

    normalized = _normalize_text(text)
    sentences = [
        (match.start(), match.end(), match.group(0))
        for match in re.finditer(r"[^。！？]+(?:[。！？]|$)", normalized)
    ]
    for sales_match in _affirmed_sales_matches(normalized):
        if _sales_match_is_unknown(sales_match, normalized):
            continue
        sentence_index = next(
            (
                index
                for index, (start, end, _) in enumerate(sentences)
                if start <= sales_match.start() < end
            ),
            None,
        )
        if sentence_index is None:
            return True
        if UNKNOWN_RE.search(sentences[sentence_index][2]):
            return True
        # A following qualification introduced by 「ただし」or「なお」
        # still governs the preceding availability assertion.  Unrelated
        # provenance/history sentences (for example, a later ``実機未確認``
        # note) remain independently claim-bound instead of poisoning it.
        if sentence_index + 1 < len(sentences):
            following = sentences[sentence_index + 1][2].lstrip()
            if re.match(r"(?:ただし|なお)", following) and UNKNOWN_RE.search(following):
                return True
    return False


def _sales_observation_date_supported(token: str, state: dict[str, object]) -> bool:
    normalized = _normalize_text(token)
    match = re.fullmatch(
        r"(20\d{2})(?:年|[./-])(\d{1,2})(?:(?:月|[./-])(\d{1,2})日?)?",
        normalized,
    )
    checked_at = state.get("checked_at_utc")
    if match is None or match.group(3) is None or type(checked_at) is not str:
        return False
    try:
        observed = datetime.fromisoformat(checked_at.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    local_date = observed.astimezone(ZoneInfo("Asia/Tokyo")).date()
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
    ) == (local_date.year, local_date.month, local_date.day)


def _sales_count_evidence_ids(
    token: str,
    reader_text: str,
    states_by_binding_id: dict[str, dict[str, object]],
) -> frozenset[str] | None:
    """Bind an explicit product count to the observed sales-state rows.

    Copy such as ``在庫切れの1台`` is a cardinality claim about the same
    external observation, not a stable source-packet product fact.  It is
    accepted only when every supplied evidence row has the asserted polarity
    and their exact count matches the reader token.
    """

    count_match = re.fullmatch(r"(?P<count>\d+)\s*台", _normalize_text(token))
    sales_tokens = [match.group(0) for match in _affirmed_sales_matches(reader_text)]
    if count_match is None or not sales_tokens or not states_by_binding_id:
        return None
    supported = frozenset(
        binding_id
        for binding_id, state in states_by_binding_id.items()
        if any(
            _sales_token_supported(sales_token, state, reader_text)
            for sales_token in sales_tokens
        )
    )
    if supported != states_by_binding_id.keys() or len(supported) != int(
        count_match.group("count")
    ):
        return None
    return supported


def _sales_lexemes_are_affirmative(text: str) -> bool:
    normalized = _normalize_text(text)
    matches = list(SALES_STATE_ASSERTION_RE.finditer(normalized))
    if not matches:
        return False
    sentence_spans = [
        (match.start(), match.end(), match.group(0))
        for match in re.finditer(r"[^。！？]+(?:[。！？]|$)", normalized)
    ]
    for match in matches:
        if _sales_match_is_unknown(match, normalized):
            continue
        suffix = normalized[match.end() :]
        if SALES_LOCAL_NEGATION_SUFFIX_RE.match(suffix) is not None:
            continue
        if (
            SALES_AFFIRMATIVE_SUFFIX_RE.match(suffix) is None
            and re.match(r"[^。！？]{0,12}" + SALES_STATE_ASSERTION_RE.pattern, suffix)
            is None
        ):
            return False
        sentence_index = next(
            (
                index
                for index, (start, end, _) in enumerate(sentence_spans)
                if start <= match.start() < end
            ),
            None,
        )
        if sentence_index is None:
            return False
        sentence = sentence_spans[sentence_index][2]
        semantic_sentence = CLOSED_UNKNOWN_SALES_PHRASE_RE.sub("", sentence)
        semantic_sentence = EXTERNAL_OUT_OF_STOCK_UI_GAP_RE.sub("", semantic_sentence)
        if SALES_NEGATED_OR_UNCERTAIN_RE.search(semantic_sentence):
            return False
        # Do not permit uncertainty to be separated by punctuation and then
        # reversed with "ただし"/"なお".  This catches both
        # ``未確認。ただし在庫切れ`` and
        # ``在庫切れ。なお未確認`` without rejecting unrelated
        # evidence prose elsewhere in a long reader unit.
        neighbors: list[str] = []
        if sentence_index > 0:
            previous = sentence_spans[sentence_index - 1][2]
            if (
                re.match(r"\s*(?:ただし|なお)", sentence.lstrip())
                or len(_normalize_text(previous)) <= 32
            ):
                neighbors.append(previous)
        if sentence_index + 1 < len(sentence_spans) and re.match(
            r"\s*(?:ただし|なお)",
            sentence_spans[sentence_index + 1][2].lstrip(),
        ):
            neighbors.append(sentence_spans[sentence_index + 1][2])
        if any(SALES_NEGATED_OR_UNCERTAIN_RE.search(value) for value in neighbors):
            return False
    return True


def _read_regular(root: Path, relative: Path, maximum: int) -> bytes:
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        _fail(f"unsafe path: {relative.as_posix()}")
    path = root / relative
    try:
        metadata = path.lstat()
    except OSError:
        _fail(f"missing input: {relative.as_posix()}")
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        _fail(f"input is not a regular non-symlink: {relative.as_posix()}")
    if metadata.st_size <= 0 or metadata.st_size > maximum:
        _fail(f"input size is invalid: {relative.as_posix()}")
    try:
        payload = path.read_bytes()
    except OSError:
        _fail(f"input is unreadable: {relative.as_posix()}")
    if len(payload) != metadata.st_size:
        _fail(f"short read: {relative.as_posix()}")
    return payload


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(root: Path, relative: Path) -> dict[str, object]:
    payload = _read_regular(root, relative, MAX_JSON_BYTES)
    try:
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except UnicodeDecodeError, json.JSONDecodeError:
        _fail(f"invalid JSON: {relative.as_posix()}")
    if type(value) is not dict:
        _fail(f"JSON root must be an object: {relative.as_posix()}")
    return cast(dict[str, object], value)


@dataclass
class _Element:
    tag: str
    path: str
    attributes: dict[str, str | None]
    parent: _Element | None
    sequence: int
    hidden: bool
    ignored: bool
    assigned_text: list[str] = field(default_factory=list)
    descendant_text: list[str] = field(default_factory=list)
    first_text_sequence: int | None = None
    child_tag_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ReaderUnit:
    unit_id: str
    locator: str
    channel: str
    text: str
    text_sha256: str
    context: str
    subject_product_ids: tuple[str, ...]
    owner_product_id: str | None
    dimension_role: str | None
    dimension_axis: str | None
    sequence: int


def _is_structural_fact_value(unit: ReaderUnit) -> bool:
    table_value = re.search(r"/td\[\d+\](?:/[^@:]*)?(?:::text|@)", unit.locator)
    definition_value = re.search(r"/dd\[\d+\](?:/[^@:]*)?(?:::text|@)", unit.locator)
    return bool(
        table_value
        or (
            definition_value
            and (unit.context == "COMPARISON" or bool(unit.subject_product_ids))
        )
    )


class _ReaderUnitParser(HTMLParser):
    def __init__(
        self,
        article_id: str,
        product_aliases: dict[str, tuple[str, ...]] | None = None,
        selected_product_ids: tuple[str, ...] | None = None,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.article_id = article_id
        self.stack: list[_Element] = []
        self.roots: list[_Element] = []
        self.elements: list[_Element] = []
        self._sequence = 0
        self._top_counts: dict[str, int] = defaultdict(int)
        self.product_aliases = product_aliases or {}
        self.selected_product_ids = (
            tuple(self.product_aliases)
            if selected_product_ids is None
            else selected_product_ids
        )
        if not set(self.selected_product_ids) <= set(self.product_aliases):
            _fail(f"selected reader products escape aliases: {article_id}")
        self.reference_product_ids = tuple(
            product_id
            for product_id in self.product_aliases
            if product_id not in self.selected_product_ids
        )
        self.outside_reader_content: list[str] = []

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    @staticmethod
    def _is_editorial_root(attributes: dict[str, str | None]) -> bool:
        classes = (attributes.get("class") or "").split()
        return "raos-editorial-v2" in classes

    def _start(self, tag: str, raw_attributes: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        attributes: dict[str, str | None] = {}
        for key, value in raw_attributes:
            key = key.casefold()
            if key in attributes:
                _fail(f"duplicate HTML attribute {key} in {self.article_id}")
            attributes[key] = value

        parent = self.stack[-1] if self.stack else None
        if parent is None:
            self._top_counts[tag] += 1
            sibling_index = self._top_counts[tag]
            path = f"{tag}[{sibling_index}]"
        else:
            parent.child_tag_counts[tag] = parent.child_tag_counts.get(tag, 0) + 1
            sibling_index = parent.child_tag_counts[tag]
            path = f"{parent.path}/{tag}[{sibling_index}]"
        hidden = bool(
            (parent and parent.hidden)
            or "hidden" in attributes
            or (attributes.get("aria-hidden") or "").casefold() == "true"
        )
        ignored = bool((parent and parent.ignored) or tag in IGNORED_TAGS)
        element = _Element(
            tag=tag,
            path=path,
            attributes=attributes,
            parent=parent,
            sequence=self._next_sequence(),
            hidden=hidden,
            ignored=ignored,
        )
        self.elements.append(element)
        if self._is_editorial_root(attributes):
            self.roots.append(element)
        if not hidden and not ignored and not self._inside_root(element):
            self.outside_reader_content.extend(
                _normalize_text(value)
                for attribute in ACCESSIBILITY_ATTRIBUTES
                if (value := attributes.get(attribute)) is not None
                and _normalize_text(value)
            )
        if tag not in VOID_TAGS:
            self.stack.append(element)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs)
        if tag.casefold() not in VOID_TAGS and self.stack:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        normalized = _normalize_text(data)
        if not normalized:
            return
        if not self.stack:
            self.outside_reader_content.append(normalized)
            return
        current = self.stack[-1]
        if current.hidden or current.ignored:
            return
        if not self._inside_root(current):
            self.outside_reader_content.append(normalized)
            return
        for candidate in self.stack:
            if not candidate.hidden and not candidate.ignored:
                candidate.descendant_text.append(data)
        anchor = current
        for candidate in reversed(self.stack):
            if candidate.tag in UNIT_TAGS:
                anchor = candidate
                break
        anchor.assigned_text.append(data)
        if anchor.first_text_sequence is None:
            anchor.first_text_sequence = self._next_sequence()

    def _inside_root(self, element: _Element) -> bool:
        candidate: _Element | None = element
        while candidate is not None:
            if candidate in self.roots:
                return True
            candidate = candidate.parent
        return False

    @staticmethod
    def _context(element: _Element) -> str:
        comparison = element.tag == "table"
        candidate: _Element | None = element
        while candidate is not None:
            marker = " ".join(
                filter(
                    None,
                    (
                        candidate.attributes.get("class") or "",
                        candidate.attributes.get("id") or "",
                        candidate.attributes.get("role") or "",
                    ),
                )
            ).casefold()
            if any(value in marker for value in DECISION_MARKERS):
                return "DECISION"
            if candidate.tag == "table" or any(
                value in marker for value in COMPARISON_MARKERS
            ):
                comparison = True
            candidate = candidate.parent
        return "COMPARISON" if comparison else "GENERAL"

    def _matching_products(self, value: str) -> tuple[str, ...]:
        return _matching_product_ids(value, self.product_aliases)

    @staticmethod
    def _dimension_role_from_text(value: str) -> str | None:
        normalized = _normalize_text(value)
        roles: set[str] = set()
        if re.search(r"(?:開扉|扉開放|ドア開放|ドア開閉)", normalized):
            roles.add("OPEN")
        if re.search(
            r"(?:ステーション|充電台|充電スタンド|台の筐体|^台(?:\s|[（(]))",
            normalized,
        ):
            roles.add("STATION")
        # ``非拡張時`` is the normal state.  Test it before the
        # shorter substring ``拡張時`` so the negating prefix cannot be lost.
        without_normal = re.sub(r"非拡張時", "", normalized)
        if "非拡張時" in normalized or "通常時" in normalized:
            roles.add("NORMAL")
        if "拡張時" in without_normal:
            roles.add("EXPANDED")
        if "本体" in normalized:
            roles.add("BODY")
        # A reader unit can describe two dimension subjects (body/station or
        # normal/expanded).  Returning one by priority would silently apply it
        # to every assertion in the unit; ambiguous units therefore carry no
        # unit-wide fallback and are resolved from each token's local text.
        return next(iter(roles)) if len(roles) == 1 else None

    @staticmethod
    def _dimension_axis_from_text(value: str) -> str | None:
        normalized = _normalize_text(value)
        axes = [
            axis
            for marker, axis in (
                ("幅", "WIDTH"),
                ("横", "WIDTH"),
                ("奥行", "DEPTH"),
                ("前後", "DEPTH"),
                ("高さ", "HEIGHT"),
                ("縦", "HEIGHT"),
                ("直径", "DIAMETER"),
            )
            if marker in normalized
        ]
        return axes[0] if len(set(axes)) == 1 else None

    def _dimension_role(
        self, element: _Element, text: str, root: _Element
    ) -> str | None:
        direct = self._dimension_role_from_text(text)
        if direct is not None:
            return direct
        cell: _Element | None = element
        while (
            cell is not None and cell is not root and cell.tag not in {"td", "th", "dd"}
        ):
            cell = cell.parent
        if cell is None or cell is root:
            return None
        if cell.tag == "dd" and cell.parent is not None:
            label = " ".join(
                candidate.descendant_text
                and " ".join(candidate.descendant_text)
                or " ".join(candidate.assigned_text)
                for candidate in self.elements
                if candidate.parent is cell.parent and candidate.tag == "dt"
            )
            return self._dimension_role_from_text(label)
        if cell.tag not in {"td", "th"}:
            return None
        table: _Element | None = cell.parent
        while table is not None and table is not root and table.tag != "table":
            table = table.parent
        if table is None or table.tag != "table":
            return None
        related: list[str] = []
        if cell.parent is not None:
            related.extend(
                " ".join(candidate.descendant_text or candidate.assigned_text)
                for candidate in self.elements
                if candidate.parent is cell.parent and candidate.tag == "th"
            )
        column = re.search(r"/(?:td|th)\[(\d+)\]\Z", cell.path)
        if column is not None:
            column_index = int(column.group(1))
            if (
                cell.tag == "td"
                and cell.parent is not None
                and any(
                    candidate.parent is cell.parent
                    and candidate.tag == "th"
                    and (candidate.attributes.get("scope") or "").casefold() == "row"
                    for candidate in self.elements
                )
            ):
                column_index += 1
            related.extend(
                " ".join(candidate.descendant_text or candidate.assigned_text)
                for candidate in self.elements
                if candidate.tag == "th"
                and candidate.path.startswith(f"{table.path}/")
                and (candidate_column := re.search(r"/th\[(\d+)\]\Z", candidate.path))
                is not None
                and int(candidate_column.group(1)) == column_index
            )
        for label in related:
            role = self._dimension_role_from_text(label)
            if role is not None:
                return role
        return None

    def _dimension_axis(
        self, element: _Element, text: str, root: _Element
    ) -> str | None:
        direct = self._dimension_axis_from_text(text)
        if direct is not None:
            return direct
        cell: _Element | None = element
        while (
            cell is not None and cell is not root and cell.tag not in {"td", "th", "dd"}
        ):
            cell = cell.parent
        if cell is None or cell is root:
            return None
        labels: list[str] = []
        if cell.tag == "dd" and cell.parent is not None:
            labels.extend(
                " ".join(candidate.descendant_text or candidate.assigned_text)
                for candidate in self.elements
                if candidate.parent is cell.parent and candidate.tag == "dt"
            )
        elif cell.tag in {"td", "th"}:
            table: _Element | None = cell.parent
            while table is not None and table is not root and table.tag != "table":
                table = table.parent
            if cell.parent is not None:
                labels.extend(
                    " ".join(candidate.descendant_text or candidate.assigned_text)
                    for candidate in self.elements
                    if candidate.parent is cell.parent and candidate.tag == "th"
                )
            if table is not None and table.tag == "table":
                column = re.search(r"/(?:td|th)\[(\d+)\]\Z", cell.path)
                if column is not None:
                    column_index = int(column.group(1))
                    if (
                        cell.tag == "td"
                        and cell.parent is not None
                        and any(
                            candidate.parent is cell.parent
                            and candidate.tag == "th"
                            and (candidate.attributes.get("scope") or "").casefold()
                            == "row"
                            for candidate in self.elements
                        )
                    ):
                        column_index += 1
                    labels.extend(
                        " ".join(candidate.descendant_text or candidate.assigned_text)
                        for candidate in self.elements
                        if candidate.tag == "th"
                        and candidate.path.startswith(f"{table.path}/")
                        and (
                            candidate_column := re.search(
                                r"/th\[(\d+)\]\Z", candidate.path
                            )
                        )
                        is not None
                        and int(candidate_column.group(1)) == column_index
                    )
        for label in labels:
            axis = self._dimension_axis_from_text(label)
            if axis is not None:
                return axis
        return None

    def _owner_product_id(self, element: _Element, root: _Element) -> str | None:
        # These exact mixed-scope summaries describe four selected products
        # and one excluded reference. The latter cannot own the sales claim.
        if (
            self.article_id == "st1704-countertop-dishwasher-for-small-households"
            and _normalize_text(" ".join(element.assigned_text))
            in MIXED_DISH_SELECTION_REFERENCE_TEXTS
        ):
            return None
        # A non-selected portfolio reference or article-local ``EXT-*``
        # market-candidate identity may be named directly in this unit.  It
        # is an ownership boundary, not a selected product subject.
        direct_nonselected = tuple(
            product_id
            for product_id in self._matching_products(
                " ".join(element.assigned_text or element.descendant_text)
            )
            if product_id in self.reference_product_ids
        )
        if len(direct_nonselected) == 1:
            return direct_nonselected[0]
        inside_table = False
        table_ancestor: _Element | None = element
        while table_ancestor is not None and table_ancestor is not root:
            if table_ancestor.tag == "table":
                inside_table = True
                break
            table_ancestor = table_ancestor.parent
        candidate: _Element | None = element
        while candidate is not None and candidate is not root:
            product_id = candidate.attributes.get("data-raos-product-id")
            if product_id in self.product_aliases:
                return cast(str, product_id)
            # Cross-article recommendations intentionally have no product
            # card identity: they live in a small nested ``section`` headed
            # by the referenced product.  Scope its later prose to that
            # heading, rather than to every selected product named elsewhere
            # in the enclosing market-candidate section.  Only products that
            # are source-packet REFERENCE_ONLY aliases may take this path, so
            # an ordinary heading can never manufacture a selected-product
            # owner.
            if (
                candidate.tag == "section"
                and self.reference_product_ids
                and not inside_table
            ):
                preceding_headings = sorted(
                    (
                        descendant
                        for descendant in self.elements
                        if descendant.tag in {"h2", "h3", "h4", "h5", "h6"}
                        and descendant.path.startswith(f"{candidate.path}/")
                        and descendant.sequence < element.sequence
                        and descendant.descendant_text
                    ),
                    key=lambda descendant: descendant.sequence,
                    reverse=True,
                )
                for heading in preceding_headings:
                    heading_matches = self._matching_products(
                        " ".join(heading.descendant_text)
                    )
                    if not heading_matches:
                        continue
                    reference_matches = tuple(
                        product_id
                        for product_id in heading_matches
                        if product_id in self.reference_product_ids
                    )
                    if len(reference_matches) == 1:
                        return reference_matches[0]
                    # The closest product-bearing heading controls the
                    # subsection.  Do not fall through to an older heading
                    # when the closest heading is ambiguous or selected.
                    break
            if candidate.tag in {"li", "article", "aside"}:
                preceding_parts = [" ".join(candidate.assigned_text)]
                preceding_parts.extend(
                    " ".join(descendant.assigned_text)
                    for descendant in self.elements
                    if descendant is not candidate
                    and descendant.path.startswith(f"{candidate.path}/")
                    and descendant.sequence < element.sequence
                    and descendant.assigned_text
                )
                preceding_matches = self._matching_products(" ".join(preceding_parts))
                if preceding_matches:
                    return preceding_matches[-1]
            candidate = candidate.parent
        return None

    def _subjects(
        self, element: _Element, text: str, root: _Element
    ) -> tuple[str, ...]:
        # A product card/decision item owns its later prose.  Prefer an
        # explicit data identity, then a product heading that precedes the
        # current unit, before considering comparison mentions inside the
        # current sentence (for example a C800 paragraph saying "C300より").
        override = READER_UNIT_SUBJECT_OVERRIDES.get((self.article_id, text))
        if override is not None:
            if not set(override) <= set(self.product_aliases):
                _fail(
                    f"reader-unit subject override escaped article scope: {self.article_id}"
                )
            return override
        direct = [
            product_id
            for product_id in self._matching_products(text)
            if not product_id.startswith("EXT-")
        ]
        groups = list(
            _matching_product_group_ids(
                text, self.product_aliases, self.selected_product_ids
            )
        )
        owner = self._owner_product_id(element, root)
        owned = [owner] if owner is not None and not owner.startswith("EXT-") else []
        if owned or direct:
            subjects = tuple(dict.fromkeys((*owned, *direct, *groups)))
            if re.search(r"\d+\s*候補より", text):
                return tuple(dict.fromkeys((*subjects, *self.selected_product_ids)))
            return subjects
        if owner is not None and owner.startswith("EXT-"):
            # The market-candidate identity is carried by the owner boundary,
            # while its manufacturer claim intentionally remains subjectless.
            # Do not turn a model number in the heading into a fallback claim
            # about every selected product in the article.
            return ()
        # A FAQ answer inherits identity from its paired question, not from an
        # unrelated product mentioned elsewhere in the enclosing section.
        # The common markup is ``dl > div > dt + dd``; nested answer elements
        # first walk up to their owning ``dd``.
        definition: _Element | None = element
        while (
            definition is not None and definition is not root and definition.tag != "dd"
        ):
            definition = definition.parent
        if definition is not None and definition is not root and definition.parent:
            questions = [
                candidate
                for candidate in self.elements
                if candidate.tag == "dt"
                and candidate.parent is definition.parent
                and candidate.sequence < definition.sequence
            ]
            if questions:
                question_text = " ".join(questions[-1].descendant_text)
                if METADATA_EXEMPTION_RE.search(question_text):
                    if required_assertion_tokens(text):
                        return self.selected_product_ids
                    return ()
                question_subjects = self._matching_products(question_text)
                if question_subjects:
                    return question_subjects
        cell: _Element | None = element
        while cell is not None and cell is not root and cell.tag not in {"td", "th"}:
            cell = cell.parent
        if cell is not None and cell.tag in {"td", "th"}:
            table: _Element | None = cell.parent
            while table is not None and table is not root and table.tag != "table":
                table = table.parent
            column = re.search(r"/(?:td|th)\[(\d+)\]\Z", cell.path)
            if table is not None and table.tag == "table" and column is not None:
                column_index = int(column.group(1))
                if (
                    cell.tag == "td"
                    and cell.parent is not None
                    and any(
                        candidate.parent is cell.parent
                        and candidate.tag == "th"
                        and (candidate.attributes.get("scope") or "").casefold()
                        == "row"
                        for candidate in self.elements
                    )
                ):
                    column_index += 1
                column_subjects: list[str] = []
                for candidate in self.elements:
                    if candidate.tag != "th" or not candidate.path.startswith(
                        f"{table.path}/"
                    ):
                        continue
                    candidate_column = re.search(r"/th\[(\d+)\]\Z", candidate.path)
                    if (
                        candidate_column is not None
                        and int(candidate_column.group(1)) == column_index
                    ):
                        column_subjects.extend(
                            self._matching_products(" ".join(candidate.descendant_text))
                        )
                if column_subjects:
                    return tuple(dict.fromkeys(column_subjects))
        candidate = element
        while candidate is not None and candidate is not root:
            if candidate.tag in {"li", "tr", "article", "aside"}:
                matches = self._matching_products(" ".join(candidate.descendant_text))
                if matches:
                    return (matches[0],)
            candidate = candidate.parent
        if groups:
            return tuple(groups)
        # Headings, captions, FAQ prompts, and summary sentences often name a
        # comparison group only in neighboring content.  Use the closest
        # enclosing section's closed descendant product set rather than
        # leaving the unit subjectless (which would allow a product claim to
        # bind without an identity boundary).
        candidate = element.parent
        while candidate is not None and candidate is not root:
            if candidate.tag == "section":
                matches = self._matching_products(" ".join(candidate.descendant_text))
                # A singleton here is commonly an incidental earlier mention
                # (notably a neighboring FAQ). Product-specific prose must use
                # a direct/owner/paired-question identity instead.
                if len(matches) >= 2:
                    return matches
            candidate = candidate.parent
        # A fact-bearing article-level prompt or scope sentence may not repeat
        # product names (for example, ``1〜2人`` or a dimension-only FAQ).
        # Keep it inside the closed article product set; claim-level and
        # occurrence-level subject checks still decide which evidence can
        # support each assertion.
        if required_assertion_tokens(text):
            return self.selected_product_ids
        return ()

    def units(self) -> list[ReaderUnit]:
        if len(self.roots) != 1:
            _fail(f"{self.article_id} must contain exactly one editorial root")
        if self.outside_reader_content:
            _fail(
                f"reader-visible content exists outside editorial root: "
                f"{self.article_id}"
            )
        root = self.roots[0]
        candidates: list[tuple[int, str, str, str, _Element]] = []
        for element in self.elements:
            if element.hidden or element.ignored or not self._inside_root(element):
                continue
            for offset, attribute in enumerate(ACCESSIBILITY_ATTRIBUTES):
                value = element.attributes.get(attribute)
                if value is not None and _normalize_text(value):
                    candidates.append(
                        (
                            element.sequence * 10 + offset,
                            f"{element.path}@{attribute}",
                            f"ATTRIBUTE_{attribute.upper().replace('-', '_')}",
                            _normalize_text(value),
                            element,
                        )
                    )
            if element.assigned_text:
                text = _normalize_text(
                    " ".join(
                        _normalize_text(segment)
                        for segment in element.assigned_text
                        if _normalize_text(segment)
                    )
                )
                if text:
                    candidates.append(
                        (
                            cast(int, element.first_text_sequence) * 10 + 9,
                            f"{element.path}::text",
                            "VISIBLE_TEXT",
                            text,
                            element,
                        )
                    )
        candidates.sort(key=lambda value: (value[0], value[1]))
        units: list[ReaderUnit] = []
        for sequence, locator, channel, text, element in candidates:
            relative_locator = locator.removeprefix(f"{root.path}/")
            identity = hashlib.sha256(
                f"{self.article_id}\0{channel}\0{relative_locator}".encode("utf-8")
            ).hexdigest()[:20]
            units.append(
                ReaderUnit(
                    unit_id=f"RU-{identity}",
                    locator=relative_locator,
                    channel=channel,
                    text=text,
                    text_sha256=_text_sha256(text),
                    context=self._context(element),
                    subject_product_ids=self._subjects(element, text, root),
                    owner_product_id=self._owner_product_id(element, root),
                    dimension_role=self._dimension_role(element, text, root),
                    dimension_axis=self._dimension_axis(element, text, root),
                    sequence=sequence,
                )
            )
        if not units or len(units) > MAX_UNITS_PER_ARTICLE:
            _fail(f"invalid reader-unit count for {self.article_id}: {len(units)}")
        identities = [unit.unit_id for unit in units]
        locators = [unit.locator for unit in units]
        if len(set(identities)) != len(identities) or len(set(locators)) != len(
            locators
        ):
            _fail(f"duplicate reader-unit identity in {self.article_id}")
        return units


def extract_reader_units(
    article_id: str,
    payload: bytes,
    product_aliases: dict[str, tuple[str, ...]] | None = None,
    selected_product_ids: tuple[str, ...] | None = None,
) -> list[ReaderUnit]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        _fail(f"article fixture is not UTF-8: {article_id}")
    parser = _ReaderUnitParser(article_id, product_aliases, selected_product_ids)
    try:
        parser.feed(text)
        parser.close()
    except CoverageFailure:
        raise
    except Exception:
        _fail(f"article fixture could not be parsed: {article_id}")
    return parser.units()


def _wordpress_metadata_units(
    article_id: str,
    article: dict[str, object],
    product_aliases: dict[str, tuple[str, ...]],
    selected_product_ids: tuple[str, ...],
) -> list[ReaderUnit]:
    units: list[ReaderUnit] = []
    for sequence, (channel, locator, field_name) in enumerate(
        (
            ("WORDPRESS_TITLE", "@wordpress-title", "title"),
            ("WORDPRESS_EXCERPT", "@wordpress-excerpt", "excerpt"),
        ),
        start=-2,
    ):
        text = _normalize_text(
            _strict_string(article.get(field_name), f"{field_name} {article_id}")
        )
        subjects = METADATA_SUBJECT_OVERRIDES.get((article_id, channel))
        owner_product_id: str | None = None
        if subjects is None:
            direct = _matching_product_ids(text, product_aliases)
            external_direct = tuple(
                product_id for product_id in direct if product_id.startswith("EXT-")
            )
            if len(external_direct) == 1:
                owner_product_id = external_direct[0]
            groups = _matching_product_group_ids(
                text, product_aliases, selected_product_ids
            )
            subjects = tuple(
                dict.fromkeys(
                    (
                        *(
                            product_id
                            for product_id in direct
                            if not product_id.startswith("EXT-")
                        ),
                        *groups,
                    )
                )
            )
            if (
                not subjects
                and owner_product_id is None
                and required_assertion_tokens(text)
            ):
                subjects = selected_product_ids
        if not set(subjects) <= set(product_aliases):
            _fail(f"WordPress metadata subject is outside article scope: {article_id}")
        identity = hashlib.sha256(
            f"{article_id}\0{channel}\0{locator}".encode("utf-8")
        ).hexdigest()[:20]
        units.append(
            ReaderUnit(
                unit_id=f"RU-{identity}",
                locator=locator,
                channel=channel,
                text=text,
                text_sha256=_text_sha256(text),
                context="DECISION",
                subject_product_ids=tuple(subjects),
                owner_product_id=owner_product_id,
                dimension_role=_ReaderUnitParser._dimension_role_from_text(text),
                dimension_axis=_ReaderUnitParser._dimension_axis_from_text(text),
                sequence=sequence,
            )
        )
    return units


def _final_reader_units(
    article_id: str,
    article: dict[str, object],
    payload: bytes,
    product_aliases: dict[str, tuple[str, ...]],
) -> list[ReaderUnit]:
    selected_product_ids = tuple(
        _strict_string_list(
            article.get("product_ids"), f"article product_ids {article_id}"
        )
    )
    return [
        *_wordpress_metadata_units(
            article_id, article, product_aliases, selected_product_ids
        ),
        *extract_reader_units(
            article_id, payload, product_aliases, selected_product_ids
        ),
    ]


def _unit_digest(units: list[ReaderUnit]) -> str:
    return _canonical_sha256(
        [
            {
                "unit_id": unit.unit_id,
                "locator": unit.locator,
                "channel": unit.channel,
                "text_sha256": unit.text_sha256,
                "context": unit.context,
                "subject_product_ids": list(unit.subject_product_ids),
                "owner_product_id": unit.owner_product_id,
                "dimension_role": unit.dimension_role,
                "dimension_axis": unit.dimension_axis,
            }
            for unit in units
        ]
    )


def _authoring_input(
    root: Path,
    model: _RepositoryModel,
    article_id: str,
    content_ref: str,
) -> dict[str, str]:
    """Bind the final fixture to its actual authoring owner.

    The first five bodies are generated from the legacy structured AST; the
    later five tracked HTML files are their own authoring inputs.  Recording
    both prevents an AST edit from being hidden behind a stale generated HTML
    file while retaining the no-new-post, ten-fixture boundary.
    """

    if article_id in model.legacy_articles:
        return {
            "kind": "LEGACY_AST_ARTICLE",
            "ref": f"{LEGACY_CONTENT_RELATIVE.as_posix()}#article_id={article_id}",
            "sha256": _canonical_sha256(model.legacy_articles[article_id]),
        }
    payload = _read_regular(root, Path(content_ref), MAX_HTML_BYTES)
    return {
        "kind": "STATIC_HTML_FIXTURE",
        "ref": content_ref,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def required_assertion_tokens(
    text: str, *, structural_fact: bool = False
) -> tuple[str, ...]:
    """Return closed syntactic tokens that an authored binding must cover."""

    normalized = _normalize_text(text)
    if normalized in METADATA_FIXED_TEXTS:
        return ()
    # A terse comparison cell whose complete value is an explicit unknown is
    # a status, not an affirmative feature assertion.  The UNKNOWN validator
    # below still requires this exact closed vocabulary and comparison
    # context, so this cannot hide a mixed factual sentence.
    if UNKNOWN_STATUS_RE.fullmatch(normalized) is not None:
        return ()
    if re.fullmatch(r"\d{1,2}", normalized):
        return ()
    scan_text = normalized
    # Editorial observation dates and visual list/model ordinals are provenance
    # or navigation, not product assertions.  Effective dates remain visible to
    # the gate and are captured as one full-date assertion below.
    if not _affirmed_sales_matches(normalized) and not re.search(
        r"(?:搭乗分より|適用|施行|発効|改定日|(?:から|より)[^。]{0,30}明確化)",
        normalized,
    ):
        # A provenance range such as ``2026年8月31日から9月1日`` is one
        # editorial observation window.  Removing only its fully qualified
        # first date leaves ``1日`` behind, which the numeric scanner would
        # incorrectly promote to a product-duration assertion.  Strip the
        # complete Japanese range before the broader single-date form.  This
        # branch is deliberately bypassed for sales observations and effective
        # dates, whose complete dates remain evidence-bound assertions.
        scan_text = re.sub(
            r"20\d{2}年\d{1,2}月\d{1,2}日"
            r"(?:\s*(?:から|[〜～–—-])\s*(?:20\d{2}年)?\d{1,2}月\d{1,2}日)?",
            " ",
            scan_text,
        )
        scan_text = re.sub(
            r"20\d{2}(?:年|[./-])\d{1,2}(?:(?:月|[./-])\d{1,2}日?)?",
            " ",
            scan_text,
        )
    scan_text = re.sub(r"^(?:モデル\s*)?\d{1,2}\s*(?:/|\s)", " ", scan_text)
    scan_text = re.sub(r"^(?:Q|A)\d+[.．:：)\s]\s*", " ", scan_text)
    scan_text = re.sub(r"第\d+(?:世代|位|版)", " ", scan_text)
    # Slash-separated model identities are two independently reviewable
    # identities, not one synthetic model token.  Splitting only an
    # alphanumeric/model-like boundary keeps unit labels such as ``Wh/kWh``
    # untouched while requiring every visible model on either side to have
    # its own packet support.
    scan_text = re.sub(r"(?<=[A-Za-z0-9-])/(?=[A-Za-z])", " ", scan_text)
    matches: list[tuple[int, int, str]] = []
    if structural_fact and re.fullmatch(r"\d+(?:[.,]\d+)?", scan_text):
        matches.append((0, len(scan_text), scan_text))
    patterns = [
        NAMED_DIMENSION_ASSERTION_RE,
        ORDERED_DIMENSION_ASSERTION_RE,
        THREE_SIDE_SUM_ASSERTION_RE,
        AXIS_SCALAR_ASSERTION_RE,
        OPEN_DEPTH_ASSERTION_RE,
        EFFECTIVE_DATE_ASSERTION_RE,
        RANGE_ASSERTION_RE,
        BAND_ASSERTION_RE,
        COUNT_ASSERTION_RE,
        NUMERIC_ASSERTION_RE,
        SALES_STATE_ASSERTION_RE,
    ]
    if not RELATIVE_GUIDANCE_RE.search(normalized):
        patterns.append(RELATIVE_ASSERTION_RE)
    for pattern in patterns:
        for match in pattern.finditer(scan_text):
            end = match.end()
            token = match.group(0)
            if (
                pattern is SALES_STATE_ASSERTION_RE
                and SALES_LOCAL_NEGATION_SUFFIX_RE.match(scan_text[end:]) is not None
            ):
                continue
            if pattern is SALES_STATE_ASSERTION_RE:
                clause_start, clause_end = _clause_bounds(scan_text, match.start())
                clause = scan_text[clause_start:clause_end]
                if re.search(
                    r"(?:探しており|知りたい|確認先|"
                    r"(?:購入画面|再入荷通知)[^。]{0,20}(?:を|へ)?確認します|"
                    r"購入UIを確認できない型番)",
                    clause,
                ):
                    # Reader intent and a future verification instruction are
                    # not observations that a particular variant is currently
                    # available or out of stock.
                    continue
                if re.fullmatch(
                    r"[^。；;]{0,24}(?:販売中|在庫あり)の[^。；;]{0,48}"
                    r"(?:選ぶ場合|探す|選びたい|候補にする)",
                    clause,
                ):
                    # This is a reader-supplied eligibility condition, not an
                    # observation that an unnamed product is available.
                    continue
            if pattern is FEATURE_ASSERTION_RE:
                suffix = FEATURE_POLARITY_SUFFIX_RE.match(scan_text[end:])
                if suffix is not None:
                    end += suffix.end()
                    token += suffix.group(0)
            elif pattern is RELATIVE_ASSERTION_RE:
                if token == "最大" and re.match(
                    r"\s*(?:\d|連続|底面辺|外形|奥行|寸法)", scan_text[end:]
                ):
                    continue
                suffix = RELATIVE_POLARITY_SUFFIX_RE.match(scan_text[end:])
                if suffix is not None:
                    end += suffix.end()
                    token += suffix.group(0)
            elif pattern is NUMERIC_ASSERTION_RE:
                suffix = NUMERIC_COMPARATOR_SUFFIX_RE.match(scan_text[end:])
                if suffix is not None:
                    clause_start, clause_end = _clause_bounds(scan_text, match.start())
                    clause = scan_text[clause_start:clause_end]
                    if not (
                        suffix.group(0).startswith(("を超え", "を上回"))
                        and re.search(
                            r"(?:接続|使用)[^。；;]{0,16}(?:せず|しない|しません|避け)",
                            clause,
                        )
                    ):
                        end += suffix.end()
                        token += suffix.group(0)
            matches.append((match.start(), end, token))
    # Feature assertions are clause-local. A word such as ``前開き`` in a
    # comparison-scope sentence must not become factual merely because a
    # different sentence elsewhere in the same paragraph says ``案内``.
    for match in FEATURE_ASSERTION_RE.finditer(scan_text):
        clause_start = (
            max(
                scan_text.rfind(marker, 0, match.start())
                for marker in ("。", "；", ";")
            )
            + 1
        )
        clause_ends = [
            end
            for marker in ("。", "；", ";")
            if (end := scan_text.find(marker, match.end())) >= 0
        ]
        clause_end = min(clause_ends) if clause_ends else len(scan_text)
        clause = scan_text[clause_start:clause_end]
        if RELATIVE_GUIDANCE_RE.search(clause):
            # A preference such as ``ストッパーを優先したい`` is a
            # reader-supplied condition, not a claim that the surrounding
            # product has that feature. Terse table/definition facts remain
            # covered because they contain no guidance predicate.
            continue
        if not structural_fact and FEATURE_FACT_PREDICATE_RE.search(clause) is None:
            continue
        end = match.end()
        token = match.group(0)
        suffix = FEATURE_POLARITY_SUFFIX_RE.match(scan_text[end:])
        if suffix is not None:
            end += suffix.end()
            token += suffix.group(0)
        matches.append((match.start(), end, token))
    feature_spans = [
        (start, end)
        for start, end, token in matches
        if _is_feature_assertion_token(token)
    ]
    for match in GENERIC_QUALITATIVE_ASSERTION_RE.finditer(scan_text):
        if any(
            match.start() < end and match.end() > start for start, end in feature_spans
        ):
            continue
        end = match.end()
        token = match.group(0)
        suffix = GENERIC_QUALITATIVE_POLARITY_SUFFIX_RE.match(scan_text[end:])
        if suffix is not None:
            end += suffix.end()
            token += suffix.group(0)
        matches.append((match.start(), end, token))
    for match in CAPABILITY_ASSERTION_RE.finditer(scan_text):
        # Known feature phrases have their own polarity-aware contract.  Only
        # add the broader capability proposition when it is not wholly
        # contained by one of those tokens.
        if any(
            match.start() >= start and match.end() <= end
            for start, end in feature_spans
        ):
            continue
        matches.append((match.start(), match.end(), match.group(0)))
    matches.sort(key=lambda value: (value[0], -(value[1] - value[0]), value[2]))
    selected: list[tuple[int, int, str]] = []
    for candidate in matches:
        start, end, token = candidate
        if any(
            start >= prior_start and end <= prior_end
            for prior_start, prior_end, _ in selected
        ):
            continue
        selected.append((start, end, token))
    # Keep repeated occurrences. The ledger binds each occurrence separately
    # so the same value cannot be attributed to two products while only one
    # source-supported occurrence is reviewed.
    tokens = [token for _, _, token in selected]
    if re.search(r"(?:料金|月額|契約単価|自宅の|概算|計算する)", normalized):
        tokens = [
            token
            for token in tokens
            if not re.fullmatch(r"(?:1回|1,?000|\d+日)", token)
        ]
    if "1回消費電力量" in normalized:
        # ``1回`` is part of the metric's proper label here, not an asserted
        # event count.  Any accompanying Wh/kWh value remains independently
        # extracted and source-bound.
        tokens = [token for token in tokens if token != "1回"]
    # ``1000Wh帯`` is a reader-facing capacity-band label, not an assertion
    # that the exact product capacity is 1000Wh.  Exact capacities in the same
    # unit remain extracted independently.
    tokens = [
        token
        for token in tokens
        if not re.search(rf"{re.escape(token)}\s*帯", scan_text, re.IGNORECASE)
    ]
    if re.search(r"1回(?:あたり|の(?:電気代|電力量))", normalized):
        # ``1回`` qualifies the metric or billing calculation; it does not
        # assert that a product ran exactly once.  Any adjacent L/Wh/kWh value
        # remains independently source-bound.
        tokens = [token for token in tokens if token != "1回"]
    if "1日の運転回数" in normalized:
        # This is a hypothetical frequency variable in editorial guidance,
        # not a claim that the reader operates the appliance once per day.
        tokens = [token for token in tokens if token != "1日"]
    # "the two compared products" is structural scope, not a product
    # capability.  Exact dimensional differences in the same sentence remain
    # assertions and therefore cannot be hidden by this exception.
    if re.search(r"(?:幅差|開扉時奥行|横幅).*(?:2台|2製品)", normalized):
        tokens = [token for token in tokens if token not in {"2台", "2"}]
    if normalized.startswith("更新履歴"):
        # The leading date timestamps the editorial change log; it is not the
        # observation date of every product fact summarized in that row.
        tokens = [
            token
            for token in tokens
            if EFFECTIVE_DATE_ASSERTION_RE.fullmatch(token) is None
        ]
    return tuple(tokens)


def _claim_support_text(claim: dict[str, object]) -> str:
    parts = [str(claim["statement"])]
    if claim.get("market_candidate_id") is not None:
        exact_model = str(claim["exact_model"])
        exact_variant_scope = str(claim["exact_variant_scope"])
        evaluated_at = str(claim["evaluated_at"])
        evaluated_date = datetime.fromisoformat(evaluated_at)
        parts.extend(
            (
                exact_model,
                exact_variant_scope,
                evaluated_at,
                f"{evaluated_date.year}年{evaluated_date.month}月{evaluated_date.day}日",
            )
        )
        lifecycle_terms = {
            "AVAILABLE": "現行 現行販売 現行表示 販売中 購入可能",
            "PREORDER": "予約受付中",
            "PRODUCTION_ENDED": "生産終了",
            "RESTOCK_NOTIFICATION_ONLY": "再入荷通知のみ 購入UIを確認できない",
            "SOLD_OUT": "在庫切れ 購入UIを確認できない",
            "UNKNOWN": "販売状態未確認",
        }
        effective_lifecycle = claim.get("effective_lifecycle")
        if effective_lifecycle in lifecycle_terms:
            parts.append(lifecycle_terms[cast(str, effective_lifecycle)])
    embedded_sales = claim.get("manufacturer_sales_state")
    if type(embedded_sales) is dict:
        sales = cast(dict[str, object], embedded_sales)
        checked_at = str(sales["checked_at"])
        observed = datetime.fromisoformat(
            checked_at.removesuffix("Z") + "+00:00"
        ).astimezone(ZoneInfo("Asia/Tokyo"))
        parts.extend(
            (
                str(sales["exact_variant"]),
                str(sales["reader_visible_label"]),
                checked_at,
                f"{observed.year}年{observed.month}月{observed.day}日",
            )
        )
    dimensions = claim.get("dimensions", [])
    if type(dimensions) is list:
        for raw in dimensions:
            if type(raw) is not dict:
                continue
            dimension = cast(dict[str, object], raw)
            if set(dimension) != {"subject", "width_cm", "depth_cm", "height_cm"}:
                continue
            width = dimension["width_cm"]
            depth = dimension["depth_cm"]
            height = dimension["height_cm"]

            def display(value: object) -> str:
                if type(value) is float and cast(float, value).is_integer():
                    return str(int(cast(float, value)))
                return str(value)

            width_display = display(width)
            depth_display = display(depth)
            height_display = display(height)
            subject = str(dimension["subject"])
            total = float(width) + float(depth) + float(height)
            # Every synthetic representation retains its structured subject.
            # Emitting a bare ``594mm``/triplet here would erase OPEN/STATION
            # semantics and let it satisfy a BODY assertion with the same
            # number.
            parts.extend(
                (
                    f"{subject} 幅{width_display}×奥行{depth_display}×高さ{height_display}cm",
                    f"{subject} 幅{width_display}cm 奥行{depth_display}cm 高さ{height_display}cm",
                    f"{subject} 幅{float(width) * 10:g}×奥行{float(depth) * 10:g}×高さ{float(height) * 10:g}mm",
                    f"{subject} 3辺合計{total:g}cm",
                )
            )
    return " ".join(parts)


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


def _exact_keys(value: dict[str, object], expected: set[str], context: str) -> None:
    if set(value) != expected:
        _fail(f"unexpected fields in {context}")


def _strict_string(value: object, context: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail(f"invalid string in {context}")
    return cast(str, value)


def _strict_string_list(value: object, context: str) -> list[str]:
    if type(value) is not list:
        _fail(f"invalid list in {context}")
    result = [_strict_string(item, context) for item in cast(list[object], value)]
    if len(result) != len(set(result)):
        _fail(f"duplicate list item in {context}")
    return result


@dataclass(frozen=True)
class _RepositoryModel:
    articles: dict[str, dict[str, object]]
    legacy_articles: dict[str, dict[str, object]]
    packets: dict[str, dict[str, object]]
    claims: dict[str, dict[str, dict[str, object]]]
    supports: dict[str, dict[str, str]]
    sales_states: dict[str, dict[str, object]]
    product_aliases: dict[str, dict[str, tuple[str, ...]]]
    claim_subjects: dict[str, dict[str, tuple[str, ...]]]
    safety_statuses: dict[str, dict[str, object]]
    market_axis_states: dict[str, dict[str, str]]
    sales_state_document_sha256: str
    safety_receipt_document_sha256: str
    market_audit_document_sha256: str


def _matching_product_spans(
    value: str, product_aliases: dict[str, tuple[str, ...]]
) -> tuple[tuple[str, int, int], ...]:
    """Return non-shadowed product aliases and their normalized-text spans.

    ASCII model aliases are boundary matched so short identifiers cannot be
    hidden inside a different model.  Multi-token title aliases are compacted
    only as a whole; individual title tokens such as ``ACE`` are deliberately
    not aliases because they are shared by unrelated products.
    """

    normalized = _normalize_text(value).casefold()
    candidates: list[tuple[str, int, int, int]] = []
    for product_id, aliases in product_aliases.items():
        for alias in aliases:
            normalized_alias = _normalize_text(alias).casefold()
            if not normalized_alias:
                continue
            body = r"\s*".join(re.escape(part) for part in normalized_alias.split(" "))
            if re.search(r"[a-z0-9]", normalized_alias):
                body = rf"(?<![a-z0-9]){body}(?![a-z0-9])"
            for match in re.finditer(body, normalized):
                candidates.append(
                    (product_id, match.start(), match.end(), len(normalized_alias))
                )
    matches: list[tuple[str, int, int]] = []
    for product_id, start, end, length in sorted(
        candidates, key=lambda value: (value[1], -value[3], value[0])
    ):
        if any(
            other_product != product_id
            and other_start <= start
            and other_end >= end
            and other_length > length
            for other_product, other_start, other_end, other_length in candidates
        ):
            continue
        candidate = (product_id, start, end)
        if candidate not in matches:
            matches.append(candidate)
    return tuple(matches)


def _matching_product_ids(
    value: str, product_aliases: dict[str, tuple[str, ...]]
) -> tuple[str, ...]:
    """Return product identities explicitly named by *value*.

    ASCII model aliases are boundary matched so short identifiers cannot be
    hidden inside a different model. Multi-token aliases shadow their shorter
    siblings at the same text span.
    """

    return tuple(
        dict.fromkeys(
            product_id
            for product_id, _, _ in _matching_product_spans(value, product_aliases)
        )
    )


def _matching_product_group_ids(
    value: str,
    product_aliases: dict[str, tuple[str, ...]],
    eligible_product_ids: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    """Resolve only closed, article-local comparison-group expressions."""

    normalized = _normalize_text(value)
    product_ids = (
        tuple(product_aliases)
        if eligible_product_ids is None
        else tuple(
            product_id
            for product_id in eligible_product_ids
            if product_id in product_aliases
        )
    )
    if re.search(r"全(?:モデル|製品|構成|機種|候補)", normalized):
        return product_ids
    count_matches = [
        int(match.group(1))
        for match in re.finditer(r"(\d+)\s*(?:モデル|製品|構成|機種|候補)", normalized)
    ]
    if len(product_ids) in count_matches:
        return product_ids

    available = set(product_ids)
    special_groups: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
        (
            re.compile(r"2\s*構成"),
            (
                "PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY",
                "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",
            ),
        ),
        (
            re.compile(r"2\s*(?:製品|モデル)"),
            (
                "EXT-PANASONIC-SOLOTA-NP-TML1-W",
                "EXT-THANKO-RAKUA-MINI-PLUS",
            ),
        ),
        (
            re.compile(r"3\s*候補"),
            (
                "PRD-PROTECA-AEROFLEX-DX2-01521",
                "PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549",
                "PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002",
            ),
        ),
        (
            re.compile(r"2\s*モデル"),
            (
                "PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549",
                "PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002",
            ),
        ),
    )
    for pattern, group in special_groups:
        if pattern.search(normalized) and set(group) <= available:
            return group
    # In the Roomba comparison, two commercial product families are represented
    # by three configuration-specific portfolio IDs.
    if (
        re.search(r"2\s*製品", normalized)
        and {
            "PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY",
            "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",
            "PRD-SWITCHBOT-K11-PRO",
        }
        <= available
    ):
        return (
            "PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY",
            "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",
            "PRD-SWITCHBOT-K11-PRO",
        )
    return ()


def _load_product_safety_statuses(
    *,
    root: Path,
    products_by_id: dict[str, dict[str, object]],
    sources: dict[str, dict[str, object]],
    claims: dict[str, dict[str, dict[str, object]]],
    replay_owner_private: bool = True,
) -> tuple[dict[str, dict[str, object]], str]:
    """Derive status only from replayed official evidence, never tracked hashes."""

    payload = _read_regular(root, PRODUCT_SAFETY_RECEIPT_RELATIVE, MAX_JSON_BYTES)
    try:
        raw = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except UnicodeDecodeError, json.JSONDecodeError:
        _fail("product-safety receipt document is invalid JSON")
    if type(raw) is not dict:
        _fail("product-safety receipt document root is not an object")
    document = cast(dict[str, object], raw)

    requirements: list[ProductSafetyRequirement] = []
    for product_id, product in products_by_id.items():
        models = tuple(
            _strict_string_list(
                product.get("official_models"), f"official_models {product_id}"
            )
        )
        requirements.append(
            ProductSafetyRequirement(
                product_id=product_id,
                exact_model_tokens=models,
            )
        )

    source_products: dict[str, set[str]] = defaultdict(set)
    for packet_claims in claims.values():
        for claim in packet_claims.values():
            subjects = _strict_string_list(
                claim.get("subject_product_ids"), "product-safety source subjects"
            )
            for source_ref in _strict_string_list(
                claim.get("evidence_refs"), "product-safety source refs"
            ):
                source_products[source_ref].update(subjects)

    manufacturer_hosts: set[str] = set()
    administrative_hosts: set[str] = set()
    official_sources: dict[str, ProductSafetyOfficialSource] = {}
    for source_ref, source in sources.items():
        authority = source.get("authority")
        url = source.get("url")
        capture_sha256 = source.get("immutable_capture_sha256")
        if type(url) is not str:
            continue
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold()
        if authority == "MANUFACTURER_OFFICIAL":
            if host:
                manufacturer_hosts.add(host)
            covered = frozenset(source_products.get(source_ref, set()))
            if not covered:
                continue
            source_authority = "MANUFACTURER_OFFICIAL"
        elif authority == "GOVERNMENT_OFFICIAL":
            if not host.endswith(".go.jp"):
                continue
            administrative_hosts.add(host)
            covered = frozenset(products_by_id)
            source_authority = "JAPAN_ADMINISTRATIVE_OFFICIAL"
        else:
            continue
        if type(capture_sha256) is not str:
            _fail(f"product-safety source capture is invalid: {source_ref}")
        official_sources[source_ref] = ProductSafetyOfficialSource(
            source_ref=source_ref,
            url=url,
            authority_kind=source_authority,
            capture_sha256=capture_sha256,
            covered_product_ids=covered,
        )

    # Empty host sets are valid only for an evidence-free isolated evaluator.
    # These non-routable sentinels cannot authorize a source because no source
    # row can bind to them.
    if not manufacturer_hosts:
        manufacturer_hosts.add("manufacturer.invalid")
    if not administrative_hosts:
        administrative_hosts.add("administrative.invalid.go.jp")
    registry = ProductSafetySourceRegistryContext(
        sources=official_sources,
        allowed_hosts_by_authority={
            "MANUFACTURER_OFFICIAL": frozenset(manufacturer_hosts),
            "JAPAN_ADMINISTRATIVE_OFFICIAL": frozenset(administrative_hosts),
        },
    )

    try:
        if replay_owner_private and (root / PORTFOLIO_RELATIVE).is_file():
            for relative in (
                PRODUCT_SAFETY_ADMIN_PLAN_RELATIVE,
                PRODUCT_SAFETY_MANUFACTURER_PLAN_RELATIVE,
                PRODUCT_SAFETY_MANUFACTURER_EMPTY_RELATIVE,
            ):
                if not (root / relative).is_file():
                    _fail(
                        "product-safety replay contract is missing: "
                        f"{relative.as_posix()}"
                    )
            audit = load_product_safety_receipt_audit(
                root,
                requirements=tuple(requirements),
                registry_context=registry,
            )
        else:
            # A synthetic/non-portfolio caller can validate the declaration
            # schema, but has no path to acquire either verified authority.
            audit = evaluate_product_safety_receipts(
                document,
                requirements=tuple(requirements),
                registry_context=registry,
            )
    except ProductSafetyReceiptFailure as exc:
        _fail(f"product-safety receipt contract mismatch: {exc}")

    statuses = {
        product.product_id: {
            "product_id": product.product_id,
            "status": product.status,
            "receipt_sha256s": [receipt.receipt_sha256 for receipt in product.receipts],
            "missing_authority_kinds": list(product.missing_authority_kinds),
            "stale_authority_kinds": list(product.stale_authority_kinds),
            "matched_notice_ids": list(product.matched_notice_ids),
        }
        for product in audit.products
    }
    return statuses, hashlib.sha256(payload).hexdigest()


def _load_market_axis_states(
    *, root: Path, articles: dict[str, dict[str, object]]
) -> tuple[dict[str, dict[str, str]], str]:
    """Bind the three selected-product due-diligence axes into reader gates."""

    payload = _read_regular(root, MARKET_AUDIT_RELATIVE, MAX_JSON_BYTES)
    try:
        raw = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except UnicodeDecodeError, json.JSONDecodeError:
        _fail("market candidate audit is invalid JSON")
    if type(raw) is not dict:
        _fail("market candidate audit root is not an object")
    document = cast(dict[str, object], raw)
    _exact_keys(
        document,
        {
            "schema",
            "version",
            "evaluated_at",
            "required_axes",
            "rules",
            "articles",
        },
        "market candidate audit",
    )
    rules = document.get("rules")
    if (
        document.get("schema") != MARKET_AUDIT_SCHEMA
        or document.get("version") != MARKET_AUDIT_VERSION
        or document.get("required_axes") != list(MARKET_REQUIRED_AXES)
        or type(rules) is not dict
        or cast(dict[str, object], rules).get(
            "incomplete_selected_product_axes_block_publication"
        )
        is not True
        or type(document.get("articles")) is not list
    ):
        _fail("market candidate audit contract mismatch")
    axis_states: dict[str, dict[str, str]] = {}
    raw_articles = cast(list[object], document["articles"])
    if len(raw_articles) != len(ARTICLE_IDS):
        _fail("market candidate audit article inventory mismatch")
    allowed_states = {
        "EVALUATED_NOT_DIFFERENTIATING",
        "OFFICIAL_EVIDENCE_USED",
        "SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED",
    }
    for expected_article_id, raw_article in zip(ARTICLE_IDS, raw_articles, strict=True):
        if type(raw_article) is not dict:
            _fail(f"market candidate audit article is invalid: {expected_article_id}")
        article = cast(dict[str, object], raw_article)
        if article.get("article_id") != expected_article_id:
            _fail("market candidate audit article order/identity mismatch")
        if _strict_string_list(
            article.get("selected_product_ids"),
            f"market selected products {expected_article_id}",
        ) != _strict_string_list(
            articles[expected_article_id].get("product_ids"),
            f"portfolio products {expected_article_id}",
        ):
            _fail(f"market selected product drift: {expected_article_id}")
        assessments = article.get("axis_assessments")
        if type(assessments) is not dict or set(
            cast(dict[str, object], assessments)
        ) != set(MARKET_REQUIRED_AXES):
            _fail(f"market axis inventory mismatch: {expected_article_id}")
        article_states: dict[str, str] = {}
        for axis in DECISION_GATE_AXES:
            assessment = cast(dict[str, object], assessments).get(axis)
            if type(assessment) is not dict:
                _fail(
                    f"market axis assessment is invalid: {expected_article_id}/{axis}"
                )
            state = cast(dict[str, object], assessment).get("state")
            if state not in allowed_states:
                _fail(f"market axis state is invalid: {expected_article_id}/{axis}")
            article_states[axis] = cast(str, state)
        axis_states[expected_article_id] = article_states
    return axis_states, hashlib.sha256(payload).hexdigest()


def _load_repository_model(
    root: Path, *, require_fresh_sales_state: bool = True
) -> _RepositoryModel:
    portfolio = _load_json(root, PORTFOLIO_RELATIVE)
    posts_document = _load_json(root, POSTS_RELATIVE)
    legacy_content = _load_json(root, LEGACY_CONTENT_RELATIVE)
    registry = _load_json(root, REGISTRY_RELATIVE)
    locator = _load_json(root, LOCATOR_RELATIVE)
    sales_payload = _read_regular(root, SALES_STATE_RELATIVE, MAX_JSON_BYTES)
    if (
        hashlib.sha256(sales_payload).hexdigest()
        != REVIEWED_SALES_STATE_DOCUMENT_SHA256
    ):
        _fail("manufacturer sales-state document is not the reviewed capture")
    try:
        raw_sales_document = json.loads(
            sales_payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except UnicodeDecodeError, json.JSONDecodeError:
        _fail("manufacturer sales-state document is invalid JSON")
    if type(raw_sales_document) is not dict:
        _fail("manufacturer sales-state document root is not an object")
    sales_document = cast(dict[str, object], raw_sales_document)

    raw_articles = portfolio.get("articles")
    raw_posts = posts_document.get("posts")
    raw_legacy_articles = legacy_content.get("articles")
    raw_packets = registry.get("source_packets")
    raw_sources = registry.get("sources")
    raw_locator_sources = locator.get("sources")
    raw_sales_states = sales_document.get("products")
    if not all(
        type(value) is list
        for value in (
            raw_articles,
            raw_posts,
            raw_legacy_articles,
            raw_packets,
            raw_sources,
            raw_locator_sources,
            raw_sales_states,
        )
    ):
        _fail("portfolio/source documents have invalid collections")

    articles: dict[str, dict[str, object]] = {}
    for raw in cast(list[object], raw_articles):
        if type(raw) is not dict:
            _fail("portfolio article is not an object")
        article = cast(dict[str, object], raw)
        article_id = _strict_string(article.get("article_id"), "portfolio article_id")
        if article_id in articles:
            _fail(f"duplicate portfolio article: {article_id}")
        articles[article_id] = article
    if tuple(articles) != ARTICLE_IDS:
        _fail("portfolio article set/order changed; new posts are forbidden")

    posts = cast(list[object], raw_posts)
    if len(posts) != len(ARTICLE_IDS):
        _fail("WordPress post fixture must contain exactly ten posts")
    for article_id, raw_post in zip(ARTICLE_IDS, posts, strict=True):
        if type(raw_post) is not dict:
            _fail(f"WordPress post fixture is not an object: {article_id}")
        post = cast(dict[str, object], raw_post)
        article = articles[article_id]
        content_ref = _strict_string(
            article.get("content_ref"), f"content_ref {article_id}"
        )
        expected_content_file = f"articles/{Path(content_ref).name}"
        if (
            post.get("content_file") != expected_content_file
            or post.get("title") != article.get("title")
            or post.get("excerpt") != article.get("excerpt")
        ):
            _fail(f"WordPress title/excerpt fixture drift: {article_id}")

    legacy_articles: dict[str, dict[str, object]] = {}
    for raw in cast(list[object], raw_legacy_articles):
        if type(raw) is not dict:
            _fail("legacy content article is not an object")
        article = cast(dict[str, object], raw)
        article_id = _strict_string(
            article.get("article_id"), "legacy content article_id"
        )
        if article_id in legacy_articles:
            _fail(f"duplicate legacy content article: {article_id}")
        legacy_articles[article_id] = article
    if tuple(legacy_articles) != ARTICLE_IDS[:5]:
        _fail("legacy AST article set/order changed")
    for article_id in ARTICLE_IDS:
        article = articles[article_id]
        source_kind = article.get("source_kind")
        source_ref = article.get("source_ref")
        if article_id in legacy_articles:
            if source_kind != "st1704_renderer" or source_ref != article_id:
                _fail(f"legacy AST ownership drift: {article_id}")
        elif source_kind != "html_fixture" or source_ref != (
            f"articles/{Path(str(article['content_ref'])).name}"
        ):
            _fail(f"static HTML ownership drift: {article_id}")

    packets: dict[str, dict[str, object]] = {}
    claims: dict[str, dict[str, dict[str, object]]] = {}
    all_claims: list[dict[str, object]] = []
    for raw in cast(list[object], raw_packets):
        if type(raw) is not dict:
            _fail("source packet is not an object")
        packet = cast(dict[str, object], raw)
        article_id = _strict_string(packet.get("article_id"), "packet article_id")
        if article_id in packets:
            _fail(f"duplicate packet article: {article_id}")
        if packet.get("fact_packet_sha256") != _packet_hash(packet):
            _fail(f"fact packet hash mismatch: {article_id}")
        raw_claims = packet.get("claims")
        if type(raw_claims) is not list or not raw_claims:
            _fail(f"source packet claims invalid: {article_id}")
        packet_claims: dict[str, dict[str, object]] = {}
        for raw_claim in cast(list[object], raw_claims):
            if type(raw_claim) is not dict:
                _fail(f"claim is not an object: {article_id}")
            claim = cast(dict[str, object], raw_claim)
            expected_claim_keys = {
                "claim_id",
                "classification",
                "evidence_level",
                "statement",
                "evidence_refs",
                "status",
                "subject_product_ids",
            }
            if "dimensions" in claim:
                expected_claim_keys.add("dimensions")
            market_fields = {
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
            }
            has_market_contract = bool(market_fields & claim.keys())
            if has_market_contract:
                expected_claim_keys.update(market_fields)
            if "negative_claim_evidence" in claim:
                expected_claim_keys.add("negative_claim_evidence")
            if "product_specific_recall_query_gate" in claim:
                expected_claim_keys.add("product_specific_recall_query_gate")
            if "manufacturer_sales_state" in claim:
                expected_claim_keys.add("manufacturer_sales_state")
            portfolio_candidate_fields = {
                "portfolio_candidate_disposition",
                "portfolio_candidate_reason",
                "route_article_id",
            }
            has_portfolio_candidate_contract = bool(
                portfolio_candidate_fields & claim.keys()
            )
            if has_portfolio_candidate_contract:
                expected_claim_keys.update(portfolio_candidate_fields)
            _exact_keys(claim, expected_claim_keys, f"claim {article_id}")
            claim_id = _strict_string(claim.get("claim_id"), "claim_id")
            if claim_id in packet_claims:
                _fail(f"duplicate claim: {claim_id}")
            classification = claim.get("classification")
            status = claim.get("status")
            if classification not in {
                "MAJOR_VERIFIABLE",
                "EDITORIAL_INFERENCE",
                "DECISION_CRITICAL_UNKNOWN",
            }:
                _fail(f"invalid claim classification: {claim_id}")
            if (
                (
                    classification == "MAJOR_VERIFIABLE"
                    and status != "BOUND_TO_OFFICIAL_SOURCE"
                )
                or (
                    classification == "EDITORIAL_INFERENCE"
                    and status != "INFERENCE_FROM_BOUND_OFFICIAL_FACTS"
                )
                or (
                    classification == "DECISION_CRITICAL_UNKNOWN"
                    and status != "UNCONFIRMED_FROM_BOUND_OFFICIAL_SOURCE"
                )
            ):
                _fail(f"invalid claim status: {claim_id}")
            if classification == "DECISION_CRITICAL_UNKNOWN" and (
                not has_market_contract
                or not claim_id.endswith("-REFERENCE")
                or claim.get("evidence_level") != "UNKNOWN"
            ):
                _fail(f"unknown claim is not an external reference: {claim_id}")
            if has_portfolio_candidate_contract:
                route_article_id = _strict_string(
                    claim.get("route_article_id"),
                    f"portfolio candidate route {claim_id}",
                )
                reason = _strict_string(
                    claim.get("portfolio_candidate_reason"),
                    f"portfolio candidate reason {claim_id}",
                )
                candidate_subjects = _strict_string_list(
                    claim.get("subject_product_ids"),
                    f"portfolio candidate subjects {claim_id}",
                )
                route_article = articles.get(route_article_id)
                current_product_ids = set(
                    _strict_string_list(
                        articles[article_id].get("product_ids"),
                        f"article product_ids {article_id}",
                    )
                )
                route_product_ids = (
                    set(
                        _strict_string_list(
                            route_article.get("product_ids"),
                            f"route product_ids {route_article_id}",
                        )
                    )
                    if route_article is not None
                    else set()
                )
                if (
                    claim.get("portfolio_candidate_disposition") != "REFERENCE_ONLY"
                    or classification != "EDITORIAL_INFERENCE"
                    or status != "INFERENCE_FROM_BOUND_OFFICIAL_FACTS"
                    or not claim_id.endswith("-REFERENCE")
                    or has_market_contract
                    or route_article_id == article_id
                    or len(candidate_subjects) != 1
                    or candidate_subjects[0] in current_product_ids
                    or candidate_subjects[0] not in route_product_ids
                    or reason not in cast(str, claim.get("statement", ""))
                ):
                    _fail(f"invalid portfolio candidate route: {claim_id}")
            if has_market_contract:
                market_candidate_id = _strict_string(
                    claim.get("market_candidate_id"),
                    f"market candidate_id {claim_id}",
                )
                if not market_candidate_id.startswith("EXT-"):
                    _fail(f"invalid market candidate identity: {claim_id}")
                disposition = claim.get("market_disposition")
                if disposition not in {"EXCLUDED", "DEFERRED"}:
                    _fail(f"invalid market candidate disposition: {claim_id}")
                official_url = _strict_string(
                    claim.get("official_url"), f"market official_url {claim_id}"
                )
                if urlsplit(official_url).scheme != "https":
                    _fail(f"market candidate official URL is not HTTPS: {claim_id}")
                _strict_string(
                    claim.get("exact_model"),
                    f"market exact_model {claim_id}",
                )
                _strict_string(
                    claim.get("exact_variant_scope"),
                    f"market exact_variant_scope {claim_id}",
                )
                evaluated_at = _strict_string(
                    claim.get("evaluated_at"), f"market evaluated_at {claim_id}"
                )
                if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", evaluated_at) is None:
                    _fail(f"invalid market candidate evaluation date: {claim_id}")
                try:
                    datetime.fromisoformat(evaluated_at)
                except ValueError:
                    _fail(f"invalid market candidate evaluation date: {claim_id}")
                lifecycle_states = {
                    "AVAILABLE",
                    "PREORDER",
                    "PRODUCTION_ENDED",
                    "RESTOCK_NOTIFICATION_ONLY",
                    "SOLD_OUT",
                    "UNKNOWN",
                }
                model_lifecycle = claim.get("model_lifecycle")
                variant_lifecycle = claim.get("variant_lifecycle")
                reader_lifecycle = claim.get("reader_visible_lifecycle")
                embedded_lifecycle = claim.get("embedded_structured_lifecycle")
                evidence_state = claim.get("lifecycle_evidence_state")
                effective_lifecycle = claim.get("effective_lifecycle")
                if (
                    model_lifecycle not in lifecycle_states
                    or variant_lifecycle not in lifecycle_states
                    or reader_lifecycle not in lifecycle_states
                    or embedded_lifecycle not in {*lifecycle_states, "NOT_PRESENT"}
                    or evidence_state
                    not in {"CONSISTENT", "CONFLICT", "READER_VISIBLE_ONLY"}
                    or effective_lifecycle != reader_lifecycle
                    or (
                        embedded_lifecycle == "NOT_PRESENT"
                        and evidence_state != "READER_VISIBLE_ONLY"
                    )
                    or (
                        embedded_lifecycle != "NOT_PRESENT"
                        and embedded_lifecycle == reader_lifecycle
                        and evidence_state != "CONSISTENT"
                    )
                    or (
                        embedded_lifecycle != "NOT_PRESENT"
                        and embedded_lifecycle != reader_lifecycle
                        and evidence_state != "CONFLICT"
                    )
                    or (
                        disposition == "DEFERRED"
                        and effective_lifecycle not in {"PREORDER", "UNKNOWN"}
                        and evidence_state != "CONFLICT"
                    )
                ):
                    _fail(f"invalid market candidate lifecycle: {claim_id}")
            negative_evidence = claim.get("negative_claim_evidence")
            if negative_evidence is not None:
                if type(negative_evidence) is not dict:
                    _fail(f"invalid negative-claim evidence: {claim_id}")
                negative = cast(dict[str, object], negative_evidence)
                _exact_keys(
                    negative,
                    {"mode", "source_refs", "page_omission_is_not_evidence"},
                    f"negative-claim evidence {claim_id}",
                )
                if negative.get("mode") not in {
                    "EXPLICIT_OFFICIAL_TEXT",
                    "OFFICIAL_COMPARISON_TABLE",
                    "OFFICIAL_PRODUCT_MANUAL",
                }:
                    _fail(f"invalid negative-claim evidence mode: {claim_id}")
                negative_refs = _strict_string_list(
                    negative.get("source_refs"),
                    f"negative-claim evidence refs {claim_id}",
                )
                if (
                    not negative_refs
                    or not set(negative_refs)
                    <= set(
                        _strict_string_list(
                            claim.get("evidence_refs"), f"evidence {claim_id}"
                        )
                    )
                    or negative.get("page_omission_is_not_evidence") is not True
                ):
                    _fail(f"invalid negative-claim evidence binding: {claim_id}")
            recall_gate = claim.get("product_specific_recall_query_gate")
            if recall_gate is not None:
                if type(recall_gate) is not dict:
                    _fail(f"invalid product-specific recall gate: {claim_id}")
                gate = cast(dict[str, object], recall_gate)
                _exact_keys(
                    gate,
                    {
                        "schema",
                        "required_product_ids",
                        "required_authority_kinds",
                        "receipt_document_ref",
                        "receipt_document_schema",
                        "coverage_caveat",
                        "general_safety_guidance_is_not_a_receipt",
                    },
                    f"product-specific recall gate {claim_id}",
                )
                article_product_ids = _strict_string_list(
                    articles[article_id].get("product_ids"),
                    f"article product_ids {article_id}",
                )
                if (
                    gate.get("schema") != "PRODUCT_SPECIFIC_RECALL_QUERY_REQUIREMENT_V2"
                    or _strict_string_list(
                        gate.get("required_product_ids"),
                        f"recall required product_ids {claim_id}",
                    )
                    != article_product_ids
                    or _strict_string_list(
                        gate.get("required_authority_kinds"),
                        f"recall required authority kinds {claim_id}",
                    )
                    != PRODUCT_SAFETY_REQUIRED_AUTHORITIES
                    or gate.get("receipt_document_ref")
                    != PRODUCT_SAFETY_RECEIPT_RELATIVE.as_posix()
                    or gate.get("receipt_document_schema")
                    != PRODUCT_SAFETY_RECEIPT_SCHEMA
                    or gate.get("general_safety_guidance_is_not_a_receipt") is not True
                ):
                    _fail(
                        f"product-specific recall gate is not fail-closed: {claim_id}"
                    )
                _strict_string(
                    gate.get("coverage_caveat"),
                    f"recall coverage caveat {claim_id}",
                )
            embedded_sales = claim.get("manufacturer_sales_state")
            if embedded_sales is not None:
                if type(embedded_sales) is not dict:
                    _fail(f"invalid embedded manufacturer sales state: {claim_id}")
                sales = cast(dict[str, object], embedded_sales)
                common_sales_fields = {
                    "exact_variant",
                    "status",
                    "checked_at",
                    "source_ref",
                    "reader_visible_label",
                }
                blocked_sales_fields = {
                    *common_sales_fields,
                    "recommendation_gate",
                    "cta_gate",
                }
                selected_sales_fields = {
                    *common_sales_fields,
                    "product_id",
                    "selection_gate",
                    "variant_caveat",
                }
                if set(sales) == blocked_sales_fields:
                    if (
                        sales.get("status")
                        not in {"OUT_OF_STOCK", "DISCONTINUED", "UNKNOWN"}
                        or sales.get("recommendation_gate") != "BLOCKED"
                        or sales.get("cta_gate") != "BLOCKED"
                    ):
                        _fail(
                            f"embedded manufacturer sales state is not blocked: "
                            f"{claim_id}"
                        )
                elif set(sales) == selected_sales_fields:
                    if (
                        sales.get("status") != "AVAILABLE"
                        or sales.get("selection_gate") != "ELIGIBLE"
                    ):
                        _fail(
                            f"embedded selected manufacturer sales state is invalid: "
                            f"{claim_id}"
                        )
                    _strict_string(
                        sales.get("product_id"),
                        f"embedded sales product_id {claim_id}",
                    )
                    embedded_variant_caveat = sales.get("variant_caveat")
                    if embedded_variant_caveat is not None:
                        if type(embedded_variant_caveat) is not dict:
                            _fail(f"invalid embedded sales variant caveat: {claim_id}")
                        caveat_value = cast(dict[str, object], embedded_variant_caveat)
                        _exact_keys(
                            caveat_value,
                            {
                                "code",
                                "detail",
                                "establishes_exact_rakuten_variant",
                            },
                            f"embedded sales variant caveat {claim_id}",
                        )
                        _strict_string(
                            caveat_value.get("code"),
                            f"embedded sales variant caveat code {claim_id}",
                        )
                        _strict_string(
                            caveat_value.get("detail"),
                            f"embedded sales variant caveat detail {claim_id}",
                        )
                        if (
                            caveat_value.get("establishes_exact_rakuten_variant")
                            is not False
                        ):
                            _fail(
                                f"embedded sales variant caveat scope is invalid: "
                                f"{claim_id}"
                            )
                else:
                    _fail(f"invalid embedded manufacturer sales fields: {claim_id}")
                for key in (
                    "exact_variant",
                    "checked_at",
                    "source_ref",
                    "reader_visible_label",
                ):
                    _strict_string(
                        sales.get(key),
                        f"embedded manufacturer sales state {key} {claim_id}",
                    )
                embedded_checked = cast(str, sales["checked_at"])
                if not embedded_checked.endswith("Z"):
                    _fail(
                        f"embedded manufacturer sales timestamp is invalid: {claim_id}"
                    )
                try:
                    datetime.fromisoformat(
                        embedded_checked.removesuffix("Z") + "+00:00"
                    )
                except ValueError:
                    _fail(
                        f"embedded manufacturer sales timestamp is invalid: {claim_id}"
                    )
            _strict_string(claim.get("statement"), f"claim statement {claim_id}")
            _strict_string_list(claim.get("evidence_refs"), f"evidence {claim_id}")
            _strict_string_list(
                claim.get("subject_product_ids"), f"claim subjects {claim_id}"
            )
            packet_claims[claim_id] = claim
            all_claims.append(claim)
        recall_gates = [
            claim
            for claim in packet_claims.values()
            if "product_specific_recall_query_gate" in claim
        ]
        selected_product_ids = _strict_string_list(
            articles[article_id].get("product_ids"),
            f"portfolio product_ids {article_id}",
        )
        if len(recall_gates) != (1 if selected_product_ids else 0):
            _fail(f"article recall-query gate inventory invalid: {article_id}")
        packets[article_id] = packet
        claims[article_id] = packet_claims
    if set(packets) != set(ARTICLE_IDS) or len(packets) != len(ARTICLE_IDS):
        _fail("source-packet article set is not the closed ten-article set")

    sources: dict[str, dict[str, object]] = {}
    for raw in cast(list[object], raw_sources):
        if type(raw) is not dict:
            _fail("source is not an object")
        source = cast(dict[str, object], raw)
        source_ref = _strict_string(source.get("source_ref"), "source_ref")
        if source_ref in sources:
            _fail(f"duplicate source: {source_ref}")
        sources[source_ref] = source

    if locator.get("source_registry_sha256") != _canonical_sha256(registry):
        _fail("locator contract is not bound to the current source registry")
    locator_sources: dict[str, dict[str, object]] = {}
    for raw in cast(list[object], raw_locator_sources):
        if type(raw) is not dict:
            _fail("locator source is not an object")
        source = cast(dict[str, object], raw)
        source_ref = _strict_string(source.get("source_ref"), "locator source_ref")
        if source_ref in locator_sources:
            _fail(f"duplicate locator source: {source_ref}")
        locator_sources[source_ref] = source

    referenced_source_claims: dict[str, list[dict[str, object]]] = defaultdict(list)
    for claim in all_claims:
        for source_ref in cast(list[str], claim["evidence_refs"]):
            referenced_source_claims[source_ref].append(claim)
    for article_id, packet_claims in claims.items():
        packet_source_refs = set(
            _strict_string_list(
                packets[article_id].get("source_refs"), "packet sources"
            )
        )
        for claim_id, claim in packet_claims.items():
            evidence_refs = cast(list[str], claim["evidence_refs"])
            if not evidence_refs or not set(evidence_refs) <= packet_source_refs:
                _fail(f"claim evidence is outside packet: {claim_id}")
            market_official_url = claim.get("official_url")
            if market_official_url is not None and not any(
                sources.get(source_ref, {}).get("url") == market_official_url
                for source_ref in evidence_refs
            ):
                _fail(
                    f"market candidate official URL is outside claim evidence: "
                    f"{claim_id}"
                )
            for source_ref in evidence_refs:
                source = sources.get(source_ref)
                located = locator_sources.get(source_ref)
                if source is None or located is None:
                    _fail(f"missing evidence source/locator: {claim_id}/{source_ref}")
                if source.get("immutable_capture_sha256") != _source_capture_hash(
                    source, referenced_source_claims[source_ref]
                ):
                    _fail(f"source capture hash mismatch: {source_ref}")
                if located.get("locator_status") != "READY":
                    _fail(f"source locator is not READY: {source_ref}")
                raw_locators = located.get("locators")
                if type(raw_locators) is not list:
                    _fail(f"source locator list invalid: {source_ref}")
                matching = [
                    item
                    for item in cast(list[object], raw_locators)
                    if type(item) is dict
                    and cast(dict[str, object], item).get("claim_id") == claim_id
                ]
                if not matching:
                    _fail(f"claim has no locator: {claim_id}/{source_ref}")
                for item in matching:
                    fragments = cast(dict[str, object], item).get(
                        "exact_utf8_fragments"
                    )
                    validated_fragments = _strict_string_list(
                        fragments, f"locator fragments {claim_id}"
                    )
                    if not validated_fragments:
                        _fail(f"claim locator has no exact fragments: {claim_id}")

    supports: dict[str, dict[str, str]] = {}
    for article_id, packet_claims in claims.items():
        supports[article_id] = {}
        for claim_id, claim in packet_claims.items():
            supports[article_id][claim_id] = _claim_support_text(claim)

    portfolio_products = portfolio.get("products")
    if type(portfolio_products) is not list:
        _fail("portfolio products must be a list")
    products_by_id: dict[str, dict[str, object]] = {}
    for raw_product in cast(list[object], portfolio_products):
        if type(raw_product) is not dict:
            _fail("portfolio product is not an object")
        product = cast(dict[str, object], raw_product)
        product_id = _strict_string(product.get("product_id"), "portfolio product_id")
        if product_id in products_by_id:
            _fail(f"duplicate portfolio product: {product_id}")
        products_by_id[product_id] = product
    portfolio_product_ids = set(products_by_id)

    _exact_keys(
        sales_document,
        {
            "schema",
            "checked_at_utc",
            "snapshot_kind",
            "hash_contract",
            "availability_scope_policy",
            "publication_policy",
            "evidence_resolution_policy",
            "products",
        },
        "manufacturer sales-state document",
    )
    if (
        sales_document.get("schema") != "RAOS_MANUFACTURER_SALES_STATE_AUDIT_V1"
        or sales_document.get("snapshot_kind")
        != "STRUCTURED_OFFICIAL_SALES_STATE_SNAPSHOT_V1"
        or sales_document.get("hash_contract")
        != {
            "algorithm": "SHA-256",
            "canonicalization": (
                "UTF-8 JSON with recursively sorted object keys, no insignificant "
                "whitespace, and unescaped Unicode"
            ),
            "fields": list(SALES_STATE_HASH_FIELDS),
        }
        or sales_document.get("availability_scope_policy")
        != {
            "MODEL": {
                "establishes_exact_rakuten_variant": False,
                "cta_requires_separate_exact_variant_evidence": True,
            },
            "VARIANT": {
                "establishes_exact_rakuten_variant": False,
                "cta_requires_separate_exact_variant_evidence": True,
            },
        }
        or sales_document.get("publication_policy")
        != {
            "AVAILABLE": {
                "state_gate": "CONDITIONAL",
                "known_state": True,
                "recheck_required": True,
            },
            "OUT_OF_STOCK": {
                "state_gate": "INELIGIBLE",
                "known_state": True,
                "recheck_required": True,
            },
            "UNKNOWN": {
                "state_gate": "INELIGIBLE",
                "known_state": False,
                "recheck_required": True,
            },
            "DISCONTINUED": {
                "state_gate": "INELIGIBLE",
                "known_state": True,
                "recheck_required": True,
            },
        }
        or sales_document.get("evidence_resolution_policy")
        != {
            "exact_variant_reader_visible_purchase_ui_required": True,
            (
                "reader_visible_sold_out_discontinued_or_preorder_"
                "precedes_hidden_structured_availability"
            ): True,
            "structured_data_alone_cannot_establish_available": True,
            "conflict_resolution": "FAIL_CLOSED_TO_UNKNOWN_OR_OUT_OF_STOCK",
            "preorder_resolution": "FAIL_CLOSED_TO_UNKNOWN",
        }
    ):
        _fail("manufacturer sales-state contract mismatch")
    checked_at_value = _strict_string(
        sales_document.get("checked_at_utc"), "sales-state checked_at_utc"
    )
    if not checked_at_value.endswith("Z"):
        _fail("manufacturer sales-state checked_at_utc is not UTC")
    try:
        checked_at = datetime.fromisoformat(
            checked_at_value.removesuffix("Z") + "+00:00"
        )
    except ValueError:
        _fail("manufacturer sales-state checked_at_utc is invalid")
    if checked_at.tzinfo is None or checked_at.utcoffset() != UTC.utcoffset(checked_at):
        _fail("manufacturer sales-state checked_at_utc is not UTC")
    age_seconds = (datetime.now(UTC) - checked_at).total_seconds()
    if require_fresh_sales_state and age_seconds > SALES_STATE_MAX_AGE_SECONDS:
        _fail("manufacturer sales-state snapshot is stale")
    if age_seconds < -SALES_STATE_MAX_FUTURE_SKEW_SECONDS:
        _fail("manufacturer sales-state snapshot is in the future")

    sales_states: dict[str, dict[str, object]] = {}
    row_checked_values: list[str] = []
    expected_row_keys = {
        *SALES_STATE_HASH_FIELDS,
        "snapshot_kind",
        "structured_snapshot_sha256",
    }
    for raw_state in cast(list[object], raw_sales_states):
        if type(raw_state) is not dict:
            _fail("manufacturer sales-state row is not an object")
        state = cast(dict[str, object], raw_state)
        _exact_keys(state, expected_row_keys, "manufacturer sales-state row")
        product_id = _strict_string(state.get("product_id"), "sales-state product_id")
        product = products_by_id.get(product_id)
        if product is None or product_id in sales_states:
            _fail(f"invalid manufacturer sales-state product: {product_id}")
        row_checked_value = _strict_string(
            state.get("checked_at_utc"),
            f"sales-state row checked_at_utc {product_id}",
        )
        if not row_checked_value.endswith("Z"):
            _fail(f"manufacturer sales-state row is not UTC: {product_id}")
        try:
            row_checked_at = datetime.fromisoformat(
                row_checked_value.removesuffix("Z") + "+00:00"
            )
        except ValueError:
            _fail(f"manufacturer sales-state row timestamp is invalid: {product_id}")
        if (
            row_checked_at.tzinfo is None
            or row_checked_at.utcoffset() != UTC.utcoffset(row_checked_at)
            or row_checked_at < checked_at
        ):
            _fail(f"manufacturer sales-state row timestamp is invalid: {product_id}")
        row_age_seconds = (datetime.now(UTC) - row_checked_at).total_seconds()
        if require_fresh_sales_state and row_age_seconds > SALES_STATE_MAX_AGE_SECONDS:
            _fail(f"manufacturer sales-state row is stale: {product_id}")
        if row_age_seconds < -SALES_STATE_MAX_FUTURE_SKEW_SECONDS:
            _fail(f"manufacturer sales-state row is in the future: {product_id}")
        row_checked_values.append(row_checked_value)
        if (
            state.get("availability_scope") not in {"MODEL", "VARIANT"}
            or state.get("snapshot_kind")
            != "STRUCTURED_OFFICIAL_SALES_STATE_SNAPSHOT_V1"
            or state.get("official_url") != product.get("official_url")
            or state.get("state")
            not in {"AVAILABLE", "OUT_OF_STOCK", "DISCONTINUED", "UNKNOWN"}
        ):
            _fail(f"manufacturer sales-state row contract mismatch: {product_id}")
        official_url = _strict_string(
            state.get("official_url"), f"sales-state official_url {product_id}"
        )
        if (
            urlsplit(official_url).scheme != "https"
            or not urlsplit(official_url).hostname
        ):
            _fail(f"manufacturer sales-state official_url is invalid: {product_id}")
        evidence_urls = _strict_string_list(
            state.get("status_evidence_urls"),
            f"sales-state evidence URLs {product_id}",
        )
        if not evidence_urls or any(
            urlsplit(url).scheme != "https" or not urlsplit(url).hostname
            for url in evidence_urls
        ):
            _fail(f"manufacturer sales-state evidence URL is invalid: {product_id}")
        official_host = cast(str, urlsplit(official_url).hostname).casefold()
        official_base = _site_domain(official_host)
        allowed_hosts = {official_host} | set(
            ADDITIONAL_OFFICIAL_SALES_HOSTS.get(product_id, frozenset())
        )
        for evidence_url in evidence_urls:
            evidence_host = cast(str, urlsplit(evidence_url).hostname).casefold()
            evidence_base = _site_domain(evidence_host)
            if evidence_host not in allowed_hosts and evidence_base != official_base:
                _fail(
                    "manufacturer sales-state evidence origin is unregistered: "
                    f"{product_id}"
                )
        locator_value = _strict_string(
            state.get("locator"), f"sales-state locator {product_id}"
        )
        basis_value = _strict_string(
            state.get("basis"), f"sales-state basis {product_id}"
        )
        if not 3 <= len(locator_value) <= 2_000 or not 3 <= len(basis_value) <= 4_000:
            _fail(f"manufacturer sales-state prose length is invalid: {product_id}")
        caveat = state.get("variant_caveat")
        if caveat is not None:
            if type(caveat) is not dict:
                _fail(f"manufacturer sales-state caveat is invalid: {product_id}")
            caveat_value = cast(dict[str, object], caveat)
            _exact_keys(
                caveat_value,
                {"code", "detail", "establishes_exact_rakuten_variant"},
                f"manufacturer sales-state caveat {product_id}",
            )
            _strict_string(caveat_value.get("code"), f"sales caveat code {product_id}")
            _strict_string(
                caveat_value.get("detail"), f"sales caveat detail {product_id}"
            )
            if caveat_value.get("establishes_exact_rakuten_variant") is not False:
                _fail(f"manufacturer sales-state caveat scope is invalid: {product_id}")
        if state.get("alternative") is not None:
            _fail(f"manufacturer sales-state alternative is unsupported: {product_id}")
        try:
            snapshot_payload = {
                field: state[field] for field in SALES_STATE_HASH_FIELDS
            }
        except KeyError:
            _fail(f"incomplete manufacturer sales-state snapshot: {product_id}")
        snapshot_hash = state.get("structured_snapshot_sha256")
        if (
            type(snapshot_hash) is not str
            or SHA256_RE.fullmatch(snapshot_hash) is None
            or snapshot_hash != _canonical_sha256(snapshot_payload)
        ):
            _fail(f"manufacturer sales-state snapshot hash mismatch: {product_id}")
        sales_states[product_id] = state
    if not row_checked_values or min(row_checked_values) != checked_at_value:
        _fail("manufacturer sales-state document timestamp is not the oldest row")
    if set(sales_states) != portfolio_product_ids:
        _fail("manufacturer sales-state coverage differs from portfolio products")
    for article_id, packet_claims in claims.items():
        for claim_id, claim in packet_claims.items():
            raw_embedded = claim.get("manufacturer_sales_state")
            if raw_embedded is None:
                continue
            embedded = cast(dict[str, object], raw_embedded)
            exact_variant = cast(str, embedded["exact_variant"])
            source_ref = cast(str, embedded["source_ref"])
            if source_ref not in claim["evidence_refs"]:
                _fail(f"embedded manufacturer sales source drift: {claim_id}")
            subject_ids = _strict_string_list(
                claim.get("subject_product_ids"), f"claim subjects {claim_id}"
            )
            if "recommendation_gate" in embedded:
                if not _is_external_candidate_claim(
                    claim_id, tuple(subject_ids)
                ) or not _sales_token_supported(
                    cast(str, embedded["reader_visible_label"]),
                    {
                        "availability_scope": "MODEL",
                        "variant_caveat": None,
                        "state": embedded["status"],
                    },
                ):
                    _fail(f"embedded external sales state drift: {claim_id}")
                continue
            matching_products = [
                product_id
                for product_id in subject_ids
                if any(
                    model.casefold() in exact_variant.casefold()
                    for model in _strict_string_list(
                        products_by_id[product_id].get("official_models"),
                        f"official_models {product_id}",
                    )
                )
            ]
            if len(matching_products) != 1:
                _fail(
                    f"embedded manufacturer sales variant is not uniquely scoped: "
                    f"{claim_id}"
                )
            product_id = matching_products[0]
            if embedded.get("product_id") != product_id:
                _fail(f"embedded manufacturer sales product drift: {claim_id}")
            state = sales_states[product_id]
            if (
                embedded["status"] != state["state"]
                or embedded["checked_at"] != state["checked_at_utc"]
                or embedded.get("variant_caveat") != state.get("variant_caveat")
                or _normalize_text(cast(str, embedded["reader_visible_label"]))
                not in _normalize_text(f"{state['locator']} {state['basis']}")
            ):
                _fail(f"embedded manufacturer sales state drift: {claim_id}")
    product_aliases: dict[str, dict[str, tuple[str, ...]]] = {}
    for article_id, article in articles.items():
        selected_product_ids = _strict_string_list(
            article.get("product_ids"), f"article product_ids {article_id}"
        )
        if not set(selected_product_ids) <= products_by_id.keys():
            _fail(f"article product is outside portfolio: {article_id}")
        reference_product_ids = [
            product_id
            for claim in claims[article_id].values()
            if claim.get("portfolio_candidate_disposition") == "REFERENCE_ONLY"
            for product_id in _strict_string_list(
                claim.get("subject_product_ids"),
                f"portfolio reference subjects {claim['claim_id']}",
            )
        ]
        local_subject_product_ids = list(
            ARTICLE_LOCAL_SUBJECT_SCOPE_ADDITIONS.get(article_id, ())
        )
        product_ids = list(
            dict.fromkeys(
                [
                    *selected_product_ids,
                    *reference_product_ids,
                    *local_subject_product_ids,
                ]
            )
        )
        if not set(product_ids) <= products_by_id.keys():
            _fail(f"article reference product is outside portfolio: {article_id}")
        article_aliases_working: dict[str, list[str]] = {}
        title_tokens_by_product: dict[str, list[str]] = {}
        identity_text_by_product: dict[str, str] = {}
        model_tokens_by_product: dict[str, list[str]] = {}
        for product_id in product_ids:
            product = products_by_id[product_id]
            aliases = [
                _strict_string(
                    product.get("official_name"), f"official_name {product_id}"
                ),
                _strict_string(
                    product.get("representative_model"),
                    f"representative_model {product_id}",
                ),
                *_strict_string_list(
                    product.get("official_models"), f"official_models {product_id}"
                ),
            ]
            # A trailing one-letter colour suffix may be omitted in reader
            # copy (NP-TSP2-W -> NP-TSP2).  Do not use required_title_tokens
            # independently: sets such as ["ACE", "06316"] are conjunctive
            # listing identity rules and "ACE" alone collides across products.
            aliases.extend(
                stem
                for alias in tuple(aliases)
                if (stem := re.sub(r"-[A-Z]\Z", "", alias)) != alias
            )
            required_title_tokens = _strict_string_list(
                product.get("required_title_tokens"),
                f"required_title_tokens {product_id}",
            )
            if required_title_tokens:
                # The complete token set is one conjunctive alias.  This
                # recognises shortened display names such as
                # ``ラクアmini color`` without turning a shared token such as
                # ``ACE`` into an identity by itself.
                aliases.append(" ".join(required_title_tokens))
            aliases.extend(
                ARTICLE_DISPLAY_ALIASES.get(article_id, {}).get(product_id, ())
            )
            title_tokens_by_product[product_id] = required_title_tokens
            identity_text_by_product[product_id] = " | ".join(
                (*aliases, *required_title_tokens)
            )
            model_tokens_by_product[product_id] = list(
                dict.fromkeys(
                    re.findall(
                        r"(?<![A-Za-z0-9])"
                        r"[A-Za-z][A-Za-z0-9+*._-]*\d[A-Za-z0-9+*._-]*"
                        r"(?![A-Za-z0-9])",
                        identity_text_by_product[product_id],
                    )
                )
            )
            article_aliases_working[product_id] = list(dict.fromkeys(aliases))

        # A shortened title token is an alias only when it identifies exactly
        # one product in this article's closed product set.  Thus ``C300`` and
        # ``ラクア`` remain useful while shared brand text such as ``ACE`` or
        # ``PROTECA`` cannot cross-bind sibling products.
        for product_id, title_tokens in title_tokens_by_product.items():
            for token in title_tokens:
                owners = [
                    candidate_id
                    for candidate_id, identity_text in identity_text_by_product.items()
                    if _matching_product_ids(identity_text, {candidate_id: (token,)})
                ]
                if owners == [product_id]:
                    article_aliases_working[product_id].append(token)
        # Model-like aliases are allowed to identify every matching product.
        # This preserves a deliberate family reference such as ``C1000`` as
        # both generations while retaining exact, article-local boundaries.
        all_model_tokens = tuple(
            dict.fromkeys(
                token for tokens in model_tokens_by_product.values() for token in tokens
            )
        )
        for token in all_model_tokens:
            owners = [
                product_id
                for product_id, identity_text in identity_text_by_product.items()
                if _matching_product_ids(identity_text, {product_id: (token,)})
            ]
            if len(owners) > 1:
                shortest = min(
                    len(str(products_by_id[product_id]["official_name"]))
                    for product_id in owners
                )
                owners = [
                    product_id
                    for product_id in owners
                    if len(str(products_by_id[product_id]["official_name"])) == shortest
                ]
            for product_id in owners:
                article_aliases_working[product_id].append(token)
        article_aliases = {
            product_id: tuple(dict.fromkeys(aliases))
            for product_id, aliases in article_aliases_working.items()
        }
        # Market candidates deliberately remain outside the selected product
        # inventory and keep subjectless packet claims.  Their reviewed
        # ``EXT-*`` identity is nevertheless needed as a structural owner for
        # prose beneath a named candidate heading; otherwise one exclusion's
        # facts could be rebound to a neighboring subjectless exclusion.  The
        # identity is an alias boundary only and is never sales-state eligible.
        external_aliases: dict[str, list[str]] = defaultdict(list)
        for claim in claims[article_id].values():
            raw_candidate_id = claim.get("market_candidate_id")
            if raw_candidate_id is None:
                continue
            candidate_id = _strict_string(
                raw_candidate_id, f"market candidate identity {article_id}"
            )
            if not candidate_id.startswith("EXT-"):
                _fail(f"invalid market candidate alias identity: {article_id}")
            external_aliases[candidate_id].extend(
                (
                    _strict_string(
                        claim.get("exact_model"),
                        f"market candidate exact model {candidate_id}",
                    ),
                    _strict_string(
                        claim.get("exact_variant_scope"),
                        f"market candidate exact variant {candidate_id}",
                    ),
                )
            )
            external_aliases[candidate_id].extend(
                ARTICLE_EXTERNAL_DISPLAY_ALIASES.get(article_id, {}).get(
                    candidate_id, ()
                )
            )
        if set(external_aliases) & set(article_aliases):
            _fail(f"market candidate alias collides with a product: {article_id}")
        article_aliases.update(
            {
                candidate_id: tuple(dict.fromkeys(aliases))
                for candidate_id, aliases in external_aliases.items()
            }
        )
        product_aliases[article_id] = article_aliases
    claim_subjects: dict[str, dict[str, tuple[str, ...]]] = {}
    for article_id, article_claims in claims.items():
        allowed = set(product_aliases[article_id])
        claim_subjects[article_id] = {}
        for claim_id, claim in article_claims.items():
            subjects = tuple(
                _strict_string_list(
                    claim.get("subject_product_ids"), f"claim subjects {claim_id}"
                )
            )
            if not set(subjects) <= allowed:
                _fail(f"claim subject is outside packet product scope: {claim_id}")
            _validate_manufacturer_claim_subject_boundary(
                claim_id=claim_id,
                claim_subjects=subjects,
                has_manufacturer_evidence=any(
                    sources[source_ref].get("authority") == "MANUFACTURER_OFFICIAL"
                    for source_ref in cast(list[str], claim["evidence_refs"])
                ),
            )
            claim_subjects[article_id][claim_id] = subjects
    safety_statuses, safety_receipt_document_sha256 = _load_product_safety_statuses(
        root=root,
        products_by_id=products_by_id,
        sources=sources,
        claims=claims,
        replay_owner_private=require_fresh_sales_state,
    )
    market_axis_states, market_audit_document_sha256 = _load_market_axis_states(
        root=root, articles=articles
    )
    return _RepositoryModel(
        articles,
        legacy_articles,
        packets,
        claims,
        supports,
        sales_states,
        product_aliases,
        claim_subjects,
        safety_statuses,
        market_axis_states,
        hashlib.sha256(sales_payload).hexdigest(),
        safety_receipt_document_sha256,
        market_audit_document_sha256,
    )


def _local_assertion_subjects(
    text: str,
    token: str,
    product_aliases: dict[str, tuple[str, ...]],
    fallback: tuple[str, ...],
    occurrence_index: int = 0,
    owner_product_id: str | None = None,
) -> tuple[str, ...]:
    """Resolve the product locally governing one assertion occurrence.

    A unit may compare several products, but an individual value normally
    belongs to the nearest product identity in the same sentence.  Keeping
    this boundary prevents a multi-product comparison claim from lending (for
    example) C1000 Gen 2's USB count to the older C1000.
    """

    override = LOCAL_ASSERTION_SUBJECT_OVERRIDES.get(
        (_normalize_text(text), _normalize_text(token), occurrence_index)
    )
    if override is not None:
        if not set(override) <= set(product_aliases):
            _fail("local assertion subject override escaped article scope")
        return override

    normalized = _normalize_text(text).casefold()
    token_key = _normalize_text(token).casefold()
    occurrences = _literal_occurrence_starts(normalized, token_key)
    if 0 <= occurrence_index < len(occurrences):
        position = occurrences[occurrence_index]
        containing_products = tuple(
            dict.fromkeys(
                product_id
                for product_id, start, end in _matching_product_spans(
                    text, product_aliases
                )
                if start <= position and position + len(token_key) <= end
            )
        )
        if containing_products:
            # A model token can be nested inside a longer exact identity
            # (``C1000`` in ``C1000 Gen 2``).  The surrounding identity owns
            # that occurrence; looking up the short token in isolation would
            # incorrectly lend Gen 2 facts to the older C1000.
            return containing_products
    direct = _matching_product_ids(token, product_aliases)
    if direct:
        return direct
    group = _matching_product_group_ids(token, product_aliases, fallback)
    if group:
        return group
    if occurrence_index < 0 or occurrence_index >= len(occurrences):
        return fallback
    position = occurrences[occurrence_index]
    if owner_product_id is not None and owner_product_id.startswith("EXT-"):
        # Facts at the start of a reviewed external-candidate card belong to
        # that structural owner until the prose explicitly introduces a
        # selected comparison baseline.  Otherwise a later selected name can
        # lend its sales row or dimensions backwards to the excluded product.
        non_owner_spans = [
            (start, end)
            for product_id, start, end in _matching_product_spans(text, product_aliases)
            if product_id != owner_product_id
        ]
        first_non_owner = (
            min(start for start, _ in non_owner_spans) if non_owner_spans else None
        )
        forward_gap = (
            normalized[position + len(token_key) : first_non_owner]
            if first_non_owner is not None and position < first_non_owner
            else ""
        )
        tightly_governed_by_following_name = bool(
            first_non_owner is not None
            and len(forward_gap) <= 16
            and re.search(r"(?:を想定する|の|は|が)\s*$", forward_gap)
        )
        if not non_owner_spans or (
            position < cast(int, first_non_owner)
            and not tightly_governed_by_following_name
        ):
            return (owner_product_id,)
    sentence_start = (
        max(normalized.rfind(marker, 0, position) for marker in ("。", "；", ";", "\n"))
        + 1
    )
    sentence_ends = [
        end
        for marker in ("。", "；", ";", "\n")
        if (end := normalized.find(marker, position)) >= 0
    ]
    sentence_end = min(sentence_ends) if sentence_ends else len(normalized)
    sentence = normalized[sentence_start:sentence_end]
    if SALES_STATE_ASSERTION_RE.fullmatch(token) is None and re.search(
        r"(?:したい|向け|優先(?:する|したい)|必須|必要条件|求める|"
        r"絞りたい|使い分けたい|条件の目安|判断軸|"
        r"(?:使|洗|運)う人|場合(?:に|は)?|なら|^q[.．:：\s])",
        sentence,
        re.IGNORECASE,
    ):
        # This is an editorial selection boundary, not a specification owned
        # by a surrounding product card.  Raw token semantics still have to
        # exist on an inference/official claim; only the product subject is
        # deliberately neutral here.
        return ()
    candidates = [
        (product_id, start, end)
        for product_id, start, end in _matching_product_spans(text, product_aliases)
        if start >= sentence_start and end <= sentence_end
    ]
    ordered_sentence_products = tuple(
        dict.fromkeys(
            product_id
            for product_id, _, _ in sorted(candidates, key=lambda value: value[1])
        )
    )
    if len(ordered_sentence_products) == 2 and candidates:
        last_product_end = max(end for _, _, end in candidates)
        between = normalized[last_product_end:position]
        if "同じ" in between:
            return ordered_sentence_products
        parallel_start = normalized.rfind("は", last_product_end, position)
        if parallel_start >= last_product_end:
            parallel = normalized[parallel_start + 1 : sentence_end]
            separators = [
                match.start() + parallel_start + 1
                for match in re.finditer(
                    r"(?:cm|mm)と(?=(?:幅|奥行|高さ|直径))", parallel
                )
            ]
            if len(separators) == 1:
                return (
                    ordered_sentence_products[0]
                    if position < separators[0]
                    else ordered_sentence_products[1],
                )
    if "それぞれ" in sentence and len(fallback) >= 2:
        respective_start = sentence_start + sentence.index("それぞれ")
        values = [
            match.start()
            for match in MEASURED_ASSERTION_RE.finditer(
                normalized, respective_start, sentence_end
            )
        ]
        if position in values:
            value_index = values.index(position)
            if value_index < len(fallback):
                return (fallback[value_index],)
    if owner_product_id is not None and re.match(
        r"の?\d+\s*候補より",
        normalized[position + len(token_key) : sentence_end],
    ):
        return tuple(
            product_id for product_id in fallback if product_id != owner_product_id
        )
    preceding = [candidate for candidate in candidates if candidate[2] <= position]
    following = [candidate for candidate in candidates if candidate[1] >= position]
    if following:
        nearest_start = min(start for _, start, _ in following)
        gap = normalized[position + len(token_key) : nearest_start].strip()
        if gap in {"は", "が"}:
            coordinated_end_candidates = [
                index
                for marker in ("、", ",")
                if (index := normalized.find(marker, nearest_start)) >= 0
            ]
            coordinated_end = (
                min(coordinated_end_candidates)
                if coordinated_end_candidates
                else sentence_end
            )
            return tuple(
                dict.fromkeys(
                    product_id
                    for product_id, start, _ in following
                    if start < coordinated_end
                )
            )
    if SALES_STATE_ASSERTION_RE.fullmatch(token) is not None and following:
        nearest_start = min(start for _, start, _ in following)
        post_predicate = normalized[position + len(token_key) : nearest_start]
        if len(post_predicate) <= 32 and re.search(
            r"(?:を確認した|の|である)", post_predicate
        ):
            return tuple(
                dict.fromkeys(
                    product_id
                    for product_id, start, _ in following
                    if start == nearest_start
                )
            )
    if SALES_STATE_ASSERTION_RE.fullmatch(token) is not None and preceding:
        # Availability predicates commonly govern a coordinated subject such
        # as ``ラクアmini colorとNP-TSP2は…在庫切れ``.  Binding only the
        # nearest name would leave the other stated product unevidenced.  The
        # sentence boundary above keeps separate availability observations
        # isolated while retaining every coordinated subject in this clause.
        return tuple(dict.fromkeys(product_id for product_id, _, _ in preceding))
    if token_key.startswith("より") and owner_product_id is not None:
        return (owner_product_id,)
    if token_key.startswith("より") and len(fallback) == 1:
        # In ``C300より大きい`` the product immediately before ``より`` is
        # the comparison baseline, not the product carrying the assertion.
        # Product-card ownership is the closed subject in that common form.
        return fallback
    if preceding:
        group_start = max(
            normalized.rfind(marker, sentence_start, position) for marker in ("、", ",")
        )
        coordinated = [
            candidate for candidate in preceding if candidate[1] > group_start
        ]
        if len({product_id for product_id, _, _ in coordinated}) >= 2 and re.search(
            r"(?:と|および|/|／)[^,、。]{0,24}は\s*$",
            normalized[min(start for _, start, _ in coordinated) : position],
        ):
            return tuple(dict.fromkeys(product_id for product_id, _, _ in coordinated))
        nearest_end = max(end for _, _, end in preceding)
        nearest_ids = {
            product_id for product_id, _, end in preceding if end == nearest_end
        }
        if (
            owner_product_id is not None
            and owner_product_id not in nearest_ids
            and re.search(
                r"(?:には|では)(?:ない|なく|ありません)",
                normalized[nearest_end:position],
            )
        ):
            # ``baselineにはない…6口`` contrasts the owner with the named
            # baseline; the later value belongs to the product card owner.
            return (owner_product_id,)
        if (
            owner_product_id is not None
            and owner_product_id not in nearest_ids
            and re.search(
                r"(?:でも|一方|対して|比べ)", normalized[nearest_end:position]
            )
        ):
            return (owner_product_id,)
        if (
            fallback
            and fallback[0] not in nearest_ids
            and "より" in normalized[nearest_end:position]
        ):
            # ``targetはotherより1.6kg軽い`` is about target; the name
            # immediately before ``より`` is only its baseline.  Prefer an
            # explicit earlier subject in the same clause (needed when the
            # source claim itself is multi-product), then the product-card
            # owner carried first in the fallback.
            earlier = [
                candidate
                for candidate in preceding
                if candidate[2] < nearest_end and candidate[0] not in nearest_ids
            ]
            if earlier:
                earlier_end = max(end for _, _, end in earlier)
                return tuple(
                    dict.fromkeys(
                        product_id
                        for product_id, _, end in earlier
                        if end == earlier_end
                    )
                )
            return fallback[:1]
        return tuple(
            dict.fromkeys(
                product_id for product_id, _, end in preceding if end == nearest_end
            )
        )
    if following:
        nearest_start = min(start for _, start, _ in following)
        gap = normalized[position + len(token_key) : nearest_start]
        if (
            len(gap) <= 40
            and re.search(r"の\Z", gap)
            and not re.search(r"[。；;、,]", gap)
        ):
            # A compact pre-nominal specification such as
            # ``1024Wh・定格1500WのDELTA`` belongs to the following product.
            return tuple(
                dict.fromkeys(
                    product_id
                    for product_id, start, _ in following
                    if start == nearest_start
                )
            )
    named_products = {product_id for product_id, _, _ in candidates}
    if len(fallback) == 1 or (
        owner_product_id is not None
        and candidates
        and fallback
        and fallback[0] not in named_products
    ):
        # A product card/list owner governs leading values; a later comparison
        # target in the same sentence must not steal those values.
        return fallback[:1]
    if following:
        nearest_start = min(start for _, start, _ in following)
        return tuple(
            dict.fromkeys(
                product_id
                for product_id, start, _ in following
                if start == nearest_start
            )
        )
    # Within a product card/list item the first fallback subject is its owner;
    # later names are comparison baselines.  A product-less assertion in a
    # later sentence therefore remains owned by the card instead of becoming
    # an artificial multi-product assertion.  Article-level comparison prose
    # has no owner and reaches this path only when its closed fallback already
    # reflects source-packet order, so claim subject checks remain fail-closed.
    if owner_product_id is not None:
        return (owner_product_id,)
    return fallback


def _subject_scoped_supports(
    *,
    assertion_text: str,
    support: str,
    assertion_subjects: tuple[str, ...],
    claim_subjects: tuple[str, ...],
    product_aliases: dict[str, tuple[str, ...]],
    dimension_role: str | None,
    dimension_axis: str | None,
) -> bool:
    if (
        claim_subjects
        and assertion_subjects
        and not set(assertion_subjects) <= set(claim_subjects)
    ):
        return False
    if not _token_supported(
        assertion_text,
        support,
        dimension_role=dimension_role,
        dimension_axis=dimension_axis,
    ):
        return False
    if len(claim_subjects) <= 1 or len(assertion_subjects) != 1:
        return True

    target = assertion_subjects[0]
    normalized_support = _normalize_text(support)
    spans = _matching_product_spans(normalized_support, product_aliases)
    target_spans = [
        (start, end) for product_id, start, end in spans if product_id == target
    ]
    if not target_spans:
        return False
    for start, end in target_spans:
        later_other = [
            other_start
            for product_id, other_start, _ in spans
            if product_id != target and other_start >= end
        ]
        sentence_end_candidates = [
            index
            for marker in ("。", "；", ";")
            if (index := normalized_support.find(marker, end)) >= 0
        ]
        segment_end = (
            min(sentence_end_candidates)
            if sentence_end_candidates
            else len(normalized_support)
        )
        if later_other:
            segment_end = min(segment_end, min(later_other))
        segment = normalized_support[start:segment_end]
        if _token_supported(
            assertion_text,
            segment,
            dimension_role=dimension_role,
            dimension_axis=dimension_axis,
        ):
            return True
    # A comparison claim often names the target, then a baseline, then the
    # computed delta (``AC70はDELTAより1.9kg軽い``).  Cutting the support at
    # the baseline name hides the delta from the target segment.  Re-evaluate
    # each source assertion occurrence with the same clause-local subject
    # resolver used for reader text, so the baseline cannot own the value and
    # a value belonging to a sibling product cannot leak across the claim.
    occurrence_counts: dict[str, int] = defaultdict(int)
    for support_token in required_assertion_tokens(support):
        occurrence_index = occurrence_counts[support_token]
        occurrence_counts[support_token] += 1
        if not _token_supported(
            assertion_text,
            support_token,
            dimension_role=dimension_role,
            dimension_axis=dimension_axis,
        ):
            continue
        support_subjects = _local_assertion_subjects(
            support,
            support_token,
            product_aliases,
            claim_subjects,
            occurrence_index,
            None,
        )
        if support_subjects and set(assertion_subjects) <= set(support_subjects):
            return True
    return False


COMPARISON_METRIC_PATTERNS: Final = (
    ("WEIGHT", re.compile(r"重量|本体重量|軽(?:い|く|量)|重(?:い|く|量)|kg", re.I)),
    ("OUTPUT", re.compile(r"定格出力|出力|(?<![kM])W(?!h)", re.I)),
    ("CAPACITY", re.compile(r"容量|Wh|kWh|(?<![A-Za-z])L(?![A-Za-z])", re.I)),
    ("WATER", re.compile(r"使用水量|水量")),
    ("DISH_COUNT", re.compile(r"食器(?:点数)?|\d+点")),
    ("WIDTH", re.compile(r"幅|横幅")),
    ("DEPTH", re.compile(r"奥行|前後")),
    ("HEIGHT", re.compile(r"高さ")),
    ("FOOTPRINT", re.compile(r"設置面積|床面積|底面辺|筐体")),
    ("SIZE", re.compile(r"寸法|外寸|大きさ|cm|mm", re.I)),
    ("COUNT", re.compile(r"端子数|ポート数|\d+口|\d+台|\d+構成")),
)


def _clause_bounds(value: str, position: int) -> tuple[int, int]:
    start = (
        max(
            _normalize_text(value).rfind(marker, 0, position)
            for marker in ("。", "；", ";", "\n")
        )
        + 1
    )
    ends = [
        index
        for marker in ("。", "；", ";", "\n")
        if (index := _normalize_text(value).find(marker, position)) >= 0
    ]
    return start, min(ends) if ends else len(_normalize_text(value))


def _comparison_metrics_at(value: str, position: int) -> frozenset[str]:
    normalized = _normalize_text(value)
    start, end = _clause_bounds(normalized, position)
    candidates: list[tuple[int, str]] = []
    for metric, pattern in COMPARISON_METRIC_PATTERNS:
        for match in pattern.finditer(normalized, start, end):
            distance = (
                match.start() - position
                if match.start() >= position
                else position - match.end()
                if match.end() <= position
                else 0
            )
            candidates.append((max(0, distance), metric))
    if not candidates:
        return frozenset()
    minimum = min(distance for distance, _ in candidates)
    # Coordinated metrics (``容量・定格出力が最小``) are intentionally kept
    # together, while unrelated measurements elsewhere in a long sentence do
    # not lend their meaning to the comparison token.
    return frozenset(
        metric for distance, metric in candidates if distance <= minimum + 8
    )


def _comparison_subjects_at(
    value: str,
    position: int,
    *,
    comparative_baseline: bool,
    product_aliases: dict[str, tuple[str, ...]],
    fallback: tuple[str, ...],
) -> tuple[str, ...]:
    normalized = _normalize_text(value).casefold()
    start, end = _clause_bounds(normalized, position)
    candidates = [
        (product_id, alias_start, alias_end)
        for product_id, alias_start, alias_end in _matching_product_spans(
            normalized, product_aliases
        )
        if alias_start >= start and alias_end <= end and alias_end <= position
    ]
    if comparative_baseline and candidates:
        baseline_end = max(alias_end for _, _, alias_end in candidates)
        baseline_ids = {
            product_id
            for product_id, _, alias_end in candidates
            if alias_end == baseline_end
        }
        candidates = [
            candidate for candidate in candidates if candidate[0] not in baseline_ids
        ]
    if candidates:
        nearest_end = max(alias_end for _, _, alias_end in candidates)
        return tuple(
            dict.fromkeys(
                product_id
                for product_id, _, alias_end in candidates
                if alias_end == nearest_end
            )
        )
    return fallback if len(fallback) == 1 else ()


def _relative_supported(
    *,
    assertion_text: str,
    reader_text: str,
    occurrence_index: int,
    assertion_subjects: tuple[str, ...],
    support: str,
    claim_subjects: tuple[str, ...],
    product_aliases: dict[str, tuple[str, ...]],
) -> bool:
    """Require comparison direction, metric and winning subject to agree."""

    assertion_key = _support_key(assertion_text)
    families = (
        (
            r"(?:最軽量|最も軽(?:い|く)?|より軽(?:い|く)?)",
            r"(?:最軽量|最も軽|より[^。]{0,24}軽)",
        ),
        (
            r"(?:最重量|最も重(?:い|く)?|より重(?:い|く)?)",
            r"(?:最重量|最も重|より[^。]{0,24}重)",
        ),
        (r"最も多(?:い|く)?", r"(?:最も多|最大)"),
        (r"最も少な(?:い|く)?", r"(?:最も少な|最小)"),
        (r"最も大き(?:い|く)?", r"(?:最も大き|最大)"),
        (r"最も小さ(?:い|く)?", r"(?:最も小さ|最小)"),
        (r"最大", r"最大"),
        (r"最小", r"最小"),
        (r"より大き", r"より[^。]{0,24}大き"),
        (r"より小さ", r"より[^。]{0,24}小さ"),
        (r"より多", r"より[^。]{0,24}多"),
        (r"より少な", r"より[^。]{0,24}少な"),
        (r"より高", r"より[^。]{0,24}高"),
        (r"より低", r"より[^。]{0,24}低"),
        (r"上回る", r"上回"),
        (r"下回る", r"下回"),
        (r"同率", r"同率"),
    )
    family: str | None = None
    for token_pattern, support_pattern in families:
        if re.fullmatch(token_pattern + r"(?:negative)?", assertion_key):
            family = support_pattern
            break
    if family is None:
        return assertion_key in _support_key(support)
    reader_normalized = _normalize_text(reader_text)
    reader_occurrences = _literal_occurrence_starts(reader_normalized, assertion_text)
    if occurrence_index >= len(reader_occurrences):
        return False
    reader_position = reader_occurrences[occurrence_index]
    reader_metrics = _comparison_metrics_at(reader_normalized, reader_position)
    if re.search(r"(?:最軽量|より軽|最重量|より重)", assertion_key):
        reader_metrics = reader_metrics | {"WEIGHT"}
    support_normalized = _support_key(support)
    token_negative = _predicate_is_negative(assertion_key)
    for match in re.finditer(family, support_normalized):
        support_metrics = _comparison_metrics_at(support_normalized, match.start())
        if re.search(
            r"(?:最軽量|より[^。]{0,24}軽|最重量|最も重|より[^。]{0,24}重)",
            match.group(0),
        ):
            support_metrics = support_metrics | {"WEIGHT"}
        if reader_metrics and not (reader_metrics & support_metrics):
            continue
        support_subjects = _comparison_subjects_at(
            support_normalized,
            match.start(),
            comparative_baseline=assertion_key.startswith("より"),
            product_aliases=product_aliases,
            fallback=claim_subjects,
        )
        if assertion_subjects and (
            not support_subjects or not set(assertion_subjects) <= set(support_subjects)
        ):
            continue
        support_clause_start, support_clause_end = _clause_bounds(
            support_normalized, match.start()
        )
        if (
            _predicate_is_negative(
                _support_key(
                    support_normalized[support_clause_start:support_clause_end]
                )
            )
            != token_negative
        ):
            continue
        return True
    return False


def _unknown_boundary_supported(reader_text: str, support: str) -> bool:
    """Bind a mixed fact/unknown boundary to the same explicit topic."""

    if UNKNOWN_RE.search(support) is None:
        return False
    topics = (
        "アクセサリ互換性",
        "実効容量",
        "各数値の軸",
        "寸法軸",
        "軸",
        "設置寸法",
        "清掃性能",
        "容量値",
        "運転音",
        "保証",
        "無償保証",
        "乾き具合",
        "洗浄力",
        "耐久性",
        "使い勝手",
        "販売状態",
        "購入導線",
        "購入UI",
        "カート",
        "実機",
        "拡張時",
        "前開き",
        "キャスターストッパー",
    )
    reader_topics = {topic for topic in topics if topic in reader_text}
    if bool(reader_topics) and any(topic in support for topic in reader_topics):
        return True
    # A purchase UI/cart observation and an official sales-state observation
    # describe the same lifecycle boundary with different reader vocabulary.
    # Keep this equivalence closed to those four terms so an unrelated unknown
    # cannot borrow a generic lifecycle claim.
    sales_boundary_terms = ("販売状態", "購入導線", "購入UI", "カート")
    return any(term in reader_text for term in sales_boundary_terms) and any(
        term in support for term in sales_boundary_terms
    )


def _has_reader_decision_unknown(reader_text: str) -> bool:
    """Exclude only the deterministic local affiliate-fallback UI status.

    A missing local Rakuten match is owned by the separate product-evidence
    activation contract; it is not an unknown manufacturer product fact.  The
    rest of the same reader unit remains claim-bound and every other unknown
    phrase continues through the fail-closed topic check below.
    """

    normalized = _normalize_text(reader_text)
    if normalized in LOCAL_MIXED_UNKNOWN_FIXED_TEXTS:
        # The positive capability in this exact comparison cell is still a
        # required assertion; only the explicitly disclosed, non-recommended
        # Wi-Fi-band gap remains a local comparison boundary.
        return False
    if COMPARISON_SCOPE_LIMIT_RE.fullmatch(normalized) is not None:
        return False
    semantic_text = AFFILIATE_FALLBACK_STATUS_RE.sub("", reader_text)
    semantic_text = CLOSED_UNKNOWN_SALES_PHRASE_RE.sub("", semantic_text)
    if METADATA_UNKNOWN_EXEMPTION_RE.fullmatch(semantic_text) is not None:
        return False
    return UNKNOWN_RE.search(semantic_text) is not None


def _is_external_candidate_claim(
    claim_id: str, claim_subjects: tuple[str, ...]
) -> bool:
    """Return whether a claim is a deliberately subjectless market candidate.

    Selected products must always carry an explicit portfolio product subject.
    A named market candidate is outside that closed selected-product inventory,
    so only the two review-only claim suffixes may omit a subject.  Keeping this
    predicate shared by packet loading and assertion validation prevents a
    normal manufacturer claim from borrowing the exception.
    """

    return not claim_subjects and claim_id.endswith(("-EXCLUDED", "-REFERENCE"))


def _external_claim_matches_owner(
    *,
    claim: dict[str, object],
    support: str,
    external_owner: str,
    product_aliases: dict[str, tuple[str, ...]],
) -> bool:
    """Bind a subjectless known-fact claim to one reviewed EXT identity.

    The market audit intentionally owns exactly one lifecycle claim for each
    external candidate. A second, known-specification claim must not duplicate
    that full market contract merely to identify its subject. It can instead
    inherit the article-local alias inventory created by the canonical market
    claim, but only when its own support text names exactly that one external
    identity. Generic or sibling-candidate statements remain unbound.
    """

    market_candidate_id = claim.get("market_candidate_id")
    if market_candidate_id is not None:
        return market_candidate_id == external_owner
    matched_external = tuple(
        product_id
        for product_id in _matching_product_ids(support, product_aliases)
        if product_id.startswith("EXT-")
    )
    return matched_external == (external_owner,)


def _bounded_external_out_of_stock_ui_gap(
    *,
    unit: ReaderUnit,
    claim_ids: list[str],
    packet_claims: dict[str, dict[str, object]],
    support_by_claim: dict[str, str],
    claim_subjects: dict[str, tuple[str, ...]],
) -> bool:
    """Allow only a reviewed OOS observation plus a narrower missing-buy UI.

    A generic ``販売状態は未確認`` remains RECHECK_REQUIRED.  The sole
    completed-kind exception covers an external candidate whose reader text,
    packet statement, lifecycle, and embedded manufacturer gate all agree
    that the exact variant is OUT_OF_STOCK while its purchase control is not
    visible.  It is never eligible on a recommendation surface.
    """

    if (
        unit.context == "DECISION"
        or EXTERNAL_OUT_OF_STOCK_UI_GAP_RE.search(unit.text) is None
        or RECHECK_REQUIRED_DISCLOSURE_RE.search(unit.text) is not None
    ):
        return False
    for claim_id in claim_ids:
        claim = packet_claims[claim_id]
        embedded = claim.get("manufacturer_sales_state")
        if (
            not claim_id.endswith("-EXCLUDED")
            or not _is_external_candidate_claim(claim_id, claim_subjects[claim_id])
            or claim.get("classification") == "DECISION_CRITICAL_UNKNOWN"
            or claim.get("effective_lifecycle") != "SOLD_OUT"
            or type(embedded) is not dict
            or cast(dict[str, object], embedded).get("status") != "OUT_OF_STOCK"
            or cast(dict[str, object], embedded).get("recommendation_gate") != "BLOCKED"
            or cast(dict[str, object], embedded).get("cta_gate") != "BLOCKED"
            or EXTERNAL_OUT_OF_STOCK_UI_GAP_RE.search(support_by_claim[claim_id])
            is None
            or not _unknown_boundary_supported(unit.text, support_by_claim[claim_id])
        ):
            continue
        return True
    return False


def _bounded_external_restock_only_lifecycle(
    *,
    unit: ReaderUnit,
    claim_ids: list[str],
    packet_claims: dict[str, dict[str, object]],
    support_by_claim: dict[str, str],
    claim_subjects: dict[str, tuple[str, ...]],
    product_aliases: dict[str, tuple[str, ...]],
) -> bool:
    """Recognize one closed, excluded RESTOCK_NOTIFICATION_ONLY lifecycle.

    This exception only prevents an uncertainty phrase about a *different*
    explicitly named product in the same reader unit from poisoning the
    completed restock observation.  It cannot make a candidate selectable:
    the exact external identity, source-packet lifecycle and reader-visible
    exclusion action must all agree.
    """

    if (
        EXTERNAL_RESTOCK_ONLY_RE.search(unit.text) is None
        or EXTERNAL_EXCLUSION_ACTION_RE.search(unit.text) is None
    ):
        return False
    visible_external_ids = {
        product_id
        for product_id in _matching_product_ids(unit.text, product_aliases)
        if product_id.startswith("EXT-")
    }
    if unit.owner_product_id is not None and unit.owner_product_id.startswith("EXT-"):
        visible_external_ids.add(unit.owner_product_id)
    for claim_id in claim_ids:
        claim = packet_claims[claim_id]
        market_candidate_id = claim.get("market_candidate_id")
        if (
            not claim_id.endswith("-EXCLUDED")
            or not _is_external_candidate_claim(claim_id, claim_subjects[claim_id])
            or claim.get("classification") == "DECISION_CRITICAL_UNKNOWN"
            or claim.get("market_disposition") != "EXCLUDED"
            or claim.get("effective_lifecycle") != "RESTOCK_NOTIFICATION_ONLY"
            or market_candidate_id not in visible_external_ids
            or EXTERNAL_RESTOCK_ONLY_RE.search(support_by_claim[claim_id]) is None
            or EXTERNAL_EXCLUSION_ACTION_RE.search(support_by_claim[claim_id]) is None
        ):
            continue
        return True
    return False


def _bounded_a10_unknown_purchase_ui_exclusion(
    *,
    unit: ReaderUnit,
    claim_ids: list[str],
    packet_claims: dict[str, dict[str, object]],
    support_by_claim: dict[str, str],
    claim_subjects: dict[str, tuple[str, ...]],
    product_aliases: dict[str, tuple[str, ...]],
) -> bool:
    """Allow only A10's exact UNKNOWN-variant, fail-closed removal boundary.

    A missing purchase UI is not proof that a product is discontinued.  A10
    therefore keeps NP-TMLK1-K at UNKNOWN and permits completed prose only
    when the exact reviewed market candidate remains EXCLUDED and the reader
    is explicitly routed away from purchasing it.  A compound sentence that
    also mentions Rakua's restock-only state must bind both exact exclusions
    and the lifecycle route claim.
    """

    if (
        A10_SOLOTA_UNKNOWN_EXCLUSION_CLAIM_ID not in claim_ids
        or EXTERNAL_UNKNOWN_PURCHASE_UI_RE.search(unit.text) is None
        or EXTERNAL_UNKNOWN_EXCLUSION_ACTION_RE.search(unit.text) is None
    ):
        return False
    claim = packet_claims[A10_SOLOTA_UNKNOWN_EXCLUSION_CLAIM_ID]
    candidate_id = claim.get("market_candidate_id")
    visible_external_ids = {
        product_id
        for product_id in _matching_product_ids(unit.text, product_aliases)
        if product_id.startswith("EXT-")
    }
    if unit.owner_product_id is not None and unit.owner_product_id.startswith("EXT-"):
        visible_external_ids.add(unit.owner_product_id)
    if (
        candidate_id not in visible_external_ids
        or not A10_SOLOTA_UNKNOWN_EXCLUSION_CLAIM_ID.endswith("-EXCLUDED")
        or not _is_external_candidate_claim(
            A10_SOLOTA_UNKNOWN_EXCLUSION_CLAIM_ID,
            claim_subjects[A10_SOLOTA_UNKNOWN_EXCLUSION_CLAIM_ID],
        )
        or claim.get("classification") != "EDITORIAL_INFERENCE"
        or claim.get("status") != "INFERENCE_FROM_BOUND_OFFICIAL_FACTS"
        or claim.get("market_disposition") != "EXCLUDED"
        or claim.get("model_lifecycle") != "UNKNOWN"
        or claim.get("variant_lifecycle") != "UNKNOWN"
        or claim.get("reader_visible_lifecycle") != "UNKNOWN"
        or claim.get("embedded_structured_lifecycle") != "NOT_PRESENT"
        or claim.get("lifecycle_evidence_state") != "READER_VISIBLE_ONLY"
        or claim.get("effective_lifecycle") != "UNKNOWN"
        or EXTERNAL_UNKNOWN_PURCHASE_UI_RE.search(
            support_by_claim[A10_SOLOTA_UNKNOWN_EXCLUSION_CLAIM_ID]
        )
        is None
        or EXTERNAL_UNKNOWN_EXCLUSION_ACTION_RE.search(
            support_by_claim[A10_SOLOTA_UNKNOWN_EXCLUSION_CLAIM_ID]
        )
        is None
        or not _unknown_boundary_supported(
            unit.text, support_by_claim[A10_SOLOTA_UNKNOWN_EXCLUSION_CLAIM_ID]
        )
    ):
        return False

    if EXTERNAL_RESTOCK_ONLY_RE.search(unit.text) is None:
        return True
    if not {
        A10_RAKUA_RESTOCK_EXCLUSION_CLAIM_ID,
        A10_LIFECYCLE_ROUTE_CLAIM_ID,
    } <= set(claim_ids):
        return False
    restock = packet_claims[A10_RAKUA_RESTOCK_EXCLUSION_CLAIM_ID]
    return bool(
        restock.get("market_candidate_id") in visible_external_ids
        and restock.get("market_disposition") == "EXCLUDED"
        and restock.get("effective_lifecycle") == "RESTOCK_NOTIFICATION_ONLY"
        and EXTERNAL_RESTOCK_ONLY_RE.search(
            support_by_claim[A10_RAKUA_RESTOCK_EXCLUSION_CLAIM_ID]
        )
        and EXTERNAL_EXCLUSION_ACTION_RE.search(
            support_by_claim[A10_RAKUA_RESTOCK_EXCLUSION_CLAIM_ID]
        )
    )


def _validate_manufacturer_claim_subject_boundary(
    *,
    claim_id: str,
    claim_subjects: tuple[str, ...],
    has_manufacturer_evidence: bool,
) -> None:
    """Reject subject laundering for ordinary manufacturer product claims."""

    if (
        has_manufacturer_evidence
        and not claim_subjects
        and not _is_external_candidate_claim(claim_id, claim_subjects)
    ):
        _fail(f"manufacturer product claim has no subject: {claim_id}")


def _external_candidate_token_supported(
    *,
    assertion_text: str,
    claim_id: str,
    support: str,
    claim_subjects: tuple[str, ...],
    dimension_role: str | None,
    dimension_axis: str | None,
    reader_text: str | None = None,
    occurrence_index: int = 0,
) -> bool:
    """Match an external-candidate token only to its reviewed packet claim.

    External candidates intentionally have no selected ``product_id`` and are
    therefore absent from the manufacturer sales-state document.  Their facts
    remain publishable only when the article packet contains a specifically
    named ``-EXCLUDED``/``-REFERENCE`` claim whose support carries the exact
    token semantics.  This does not relax selected-product availability, which
    continues to require a structured manufacturer-state binding.
    """

    if not _is_external_candidate_claim(claim_id, claim_subjects):
        return False
    normalized_token = _normalize_text(assertion_text)
    if SALES_STATE_ASSERTION_RE.fullmatch(normalized_token) is not None:
        support_key = _normalize_text(support)
        if normalized_token == "現行販売" and "販売状態未確認" in support_key:
            return bool(
                reader_text is not None
                and occurrence_index == 0
                and re.search(
                    r"現行販売を確認できるまで推奨しません",
                    _normalize_text(reader_text),
                )
            )
        if re.fullmatch(
            r"販売状態(?:は|を)?(?:未確認|確認できな(?:い|かった|く|せん))",
            normalized_token,
        ):
            return bool(
                re.search(
                    r"販売状態(?:は|を)?(?:未確認|確認できない|"
                    r"確定できず|確定できない)",
                    support_key,
                )
            )
        if re.fullmatch(
            r"(?:購入UIを確認できな(?:い|かった|く|せん)|"
            r"再入荷(?:\(予約開始\))?通知(?:のみ|だけ)?|"
            r"在庫切れ|売り切れ|売切れ|欠品中|品切れ|完売|"
            r"再入荷待ち|在庫なし|購入不可)",
            normalized_token,
        ):
            return bool(
                re.search(
                    r"再入荷|在庫切れ|売り切れ|売切れ|完売|"
                    r"カート(?:導線)?を確認できない|購入UIを確認できない",
                    support_key,
                )
            )
        if re.fullmatch(
            r"(?:生産終了|販売終了|終売|取扱終了|販売休止|販売停止)",
            normalized_token,
        ):
            return bool(re.search(r"生産終了|販売終了|終売|取扱終了", support_key))
        return bool(
            re.search(
                r"現行|購入UIを確認できる|購入できる|"
                r"カートに入れる|在庫あり|販売中",
                support_key,
            )
        )
    return _token_supported(
        assertion_text,
        support,
        dimension_role=dimension_role,
        dimension_axis=dimension_axis,
    )


def _validate_assertions(
    *,
    unit: ReaderUnit,
    binding: dict[str, object],
    unit_claim_ids: list[str],
    inference_claim_ids: set[str],
    support_by_claim: dict[str, str],
    claim_subjects: dict[str, tuple[str, ...]],
    product_aliases: dict[str, tuple[str, ...]],
    state_by_evidence_binding: dict[str, dict[str, object]],
    subject_sales_states: dict[str, dict[str, object]],
    allow_unknown_reference: bool,
    gate_evidence_binding_ids: set[str] | None = None,
) -> None:
    raw_assertions = binding.get("assertion_tokens")
    if type(raw_assertions) is not list:
        _fail(f"assertion_tokens must be a list: {unit.unit_id}")
    assertions: list[dict[str, object]] = []
    used_evidence_bindings: set[str] = set()
    for raw in cast(list[object], raw_assertions):
        if type(raw) is not dict:
            _fail(f"assertion token is not an object: {unit.unit_id}")
        assertion = cast(dict[str, object], raw)
        _exact_keys(
            assertion,
            {
                "assertion_text",
                "occurrence_index",
                "claim_ids",
                "evidence_binding_ids",
            },
            f"assertion {unit.unit_id}",
        )
        assertion_text = _strict_string(
            assertion.get("assertion_text"), f"assertion {unit.unit_id}"
        )
        occurrence_index = assertion.get("occurrence_index")
        if type(occurrence_index) is not int or cast(int, occurrence_index) < 0:
            _fail(f"invalid assertion occurrence: {unit.unit_id}/{assertion_text}")
        assertion_claims = _strict_string_list(
            assertion.get("claim_ids"), f"assertion claims {unit.unit_id}"
        )
        assertion_evidence = _strict_string_list(
            assertion.get("evidence_binding_ids"),
            f"assertion evidence {unit.unit_id}",
        )
        if not set(assertion_claims) <= set(unit_claim_ids):
            _fail(
                f"assertion claims escape unit claims: {unit.unit_id}/{assertion_text}"
            )
        if not set(assertion_evidence) <= state_by_evidence_binding.keys():
            _fail(
                f"assertion evidence escapes unit bindings: "
                f"{unit.unit_id}/{assertion_text}"
            )
        if not assertion_claims and not assertion_evidence:
            _fail(
                f"assertion token has no semantic support: "
                f"{unit.unit_id}/{assertion_text}"
            )
        if _support_key(assertion_text) not in _support_key(unit.text):
            _fail(
                f"assertion token is absent from reader text: "
                f"{unit.unit_id}/{assertion_text}"
            )
        structural_dimension = _is_structural_fact_value(unit)
        assertion_dimension_role = _local_dimension_role(
            unit.text,
            assertion_text,
            unit.dimension_role if structural_dimension else None,
            cast(int, occurrence_index),
        )
        assertion_dimension_axis = _local_dimension_axis(
            unit.text,
            assertion_text,
            unit.dimension_axis if structural_dimension else None,
            cast(int, occurrence_index),
        )
        assertion_subjects = _local_assertion_subjects(
            unit.text,
            assertion_text,
            product_aliases,
            unit.subject_product_ids,
            cast(int, occurrence_index),
            unit.owner_product_id,
        )
        claim_supported = any(
            _subject_scoped_supports(
                assertion_text=assertion_text,
                support=support_by_claim[claim_id],
                assertion_subjects=assertion_subjects,
                claim_subjects=claim_subjects[claim_id],
                product_aliases=product_aliases,
                dimension_role=assertion_dimension_role,
                dimension_axis=assertion_dimension_axis,
            )
            for claim_id in assertion_claims
        )
        external_candidate_supported = (
            not assertion_subjects
            or all(subject.startswith("EXT-") for subject in assertion_subjects)
        ) and any(
            _external_candidate_token_supported(
                assertion_text=assertion_text,
                claim_id=claim_id,
                support=support_by_claim[claim_id],
                claim_subjects=claim_subjects[claim_id],
                dimension_role=assertion_dimension_role,
                dimension_axis=assertion_dimension_axis,
                reader_text=unit.text,
                occurrence_index=cast(int, occurrence_index),
            )
            for claim_id in assertion_claims
        )
        claim_supported = claim_supported or external_candidate_supported
        claim_supported = claim_supported or any(
            _closed_wifi_band_boundary_supported(
                assertion_text, unit.text, support_by_claim[claim_id]
            )
            for claim_id in assertion_claims
        )
        if allow_unknown_reference:
            claim_supported = claim_supported or any(
                _support_key(assertion_text).replace("negative", "")
                in _support_key(support_by_claim[claim_id]).replace("negative", "")
                and _unknown_boundary_supported(unit.text, support_by_claim[claim_id])
                for claim_id in assertion_claims
            )
        count_match = COUNT_ASSERTION_RE.fullmatch(_normalize_text(assertion_text))
        if count_match is not None:
            count_number = re.match(r"\d+", _normalize_text(assertion_text))
            assert count_number is not None
            count_value = int(count_number.group(0))
            counted_subjects = tuple(
                subject
                for subject in (
                    assertion_subjects
                    or tuple(
                        value
                        for value in unit.subject_product_ids
                        if not value.startswith("EXT-")
                    )
                )
                if not subject.startswith("EXT-")
            )
            claim_supported = claim_supported or (
                count_value == len(counted_subjects)
                and count_value > 0
                and all(
                    any(
                        subject in claim_subjects[claim_id]
                        for claim_id in assertion_claims
                    )
                    for subject in counted_subjects
                )
            )
        if len(assertion_subjects) > 1:
            # Coordinated equality such as ``両機とも高さ9.2cm`` is supported
            # only when every named subject has its own bound claim carrying
            # that exact value.  No one product may lend a shared-looking
            # number to its sibling.
            claim_supported = claim_supported or all(
                any(
                    subject in claim_subjects[claim_id]
                    and _subject_scoped_supports(
                        assertion_text=assertion_text,
                        support=support_by_claim[claim_id],
                        assertion_subjects=(subject,),
                        claim_subjects=claim_subjects[claim_id],
                        product_aliases=product_aliases,
                        dimension_role=assertion_dimension_role,
                        dimension_axis=assertion_dimension_axis,
                    )
                    for claim_id in assertion_claims
                )
                for subject in assertion_subjects
            )
        if RELATIVE_ASSERTION_RE.fullmatch(assertion_text):
            claim_supported = any(
                claim_id in inference_claim_ids
                and set(assertion_subjects) <= set(claim_subjects[claim_id])
                and _relative_supported(
                    assertion_text=assertion_text,
                    reader_text=unit.text,
                    occurrence_index=cast(int, occurrence_index),
                    assertion_subjects=assertion_subjects,
                    support=support_by_claim[claim_id],
                    claim_subjects=claim_subjects[claim_id],
                    product_aliases=product_aliases,
                )
                for claim_id in assertion_claims
            )
        sales_token = SALES_STATE_ASSERTION_RE.fullmatch(assertion_text) is not None
        sales_observation_date = bool(
            EFFECTIVE_DATE_ASSERTION_RE.fullmatch(assertion_text)
            and _affirmed_sales_matches(unit.text)
        )
        sales_count = bool(
            re.fullmatch(r"\d+\s*台", _normalize_text(assertion_text))
            and _affirmed_sales_matches(unit.text)
        )
        sales_count_evidence = _sales_count_evidence_ids(
            assertion_text, unit.text, state_by_evidence_binding
        )
        external_sales_token = sales_token and external_candidate_supported
        external_sales_observation = (
            sales_observation_date and external_candidate_supported
        )
        external_sales_count = sales_count and external_candidate_supported
        if (
            sales_token
            and not _sales_lexemes_are_affirmative(unit.text)
            and not external_sales_token
        ):
            _fail(
                f"sales-state wording is not closed affirmative prose: {unit.unit_id}"
            )
        if sales_token and not assertion_evidence and not external_sales_token:
            _fail(
                f"sales assertion has no sales-state binding: "
                f"{unit.unit_id}/{assertion_text}"
            )
        if sales_observation_date and (
            not external_sales_observation
            and (
                not assertion_evidence
                or set(assertion_evidence) != set(state_by_evidence_binding)
            )
        ):
            _fail(
                f"sales observation date has incomplete evidence: "
                f"{unit.unit_id}/{assertion_text}"
            )
        if sales_count and (
            not external_sales_count
            and (
                sales_count_evidence is None
                or set(assertion_evidence) != set(sales_count_evidence)
            )
        ):
            _fail(
                f"sales-state count has incomplete evidence: "
                f"{unit.unit_id}/{assertion_text}"
            )
        if sales_token and not external_sales_token:
            if not assertion_subjects:
                _fail(
                    f"sales assertion has no local product subject: "
                    f"{unit.unit_id}/{assertion_text}"
                )
            expected_evidence = {
                f"MSS-{product_id}"
                for product_id in assertion_subjects
                if product_id in subject_sales_states
                and _sales_token_supported(
                    assertion_text,
                    subject_sales_states[product_id],
                    unit.text,
                    cast(int, occurrence_index),
                )
            }
            if not expected_evidence or set(assertion_evidence) != expected_evidence:
                _fail(
                    f"sales assertion subject coverage mismatch: "
                    f"{unit.unit_id}/{assertion_text}"
                )
        evidence_supported = (
            any(
                _sales_token_supported(
                    assertion_text,
                    state_by_evidence_binding[binding_id],
                    unit.text,
                    cast(int, occurrence_index),
                )
                or _sales_observation_date_supported(
                    assertion_text, state_by_evidence_binding[binding_id]
                )
                for binding_id in assertion_evidence
            )
            or sales_count_evidence is not None
        )
        if sales_token or sales_count:
            claim_supported = external_candidate_supported
        if not claim_supported and not evidence_supported:
            _fail(
                f"assertion token is unsupported by claims: "
                f"{unit.unit_id}/{assertion_text}"
            )
        used_evidence_bindings.update(assertion_evidence)
        assertions.append(assertion)
    tokens = [cast(str, assertion["assertion_text"]) for assertion in assertions]
    expected_occurrences: dict[str, list[int]] = defaultdict(list)
    for token, assertion in zip(tokens, assertions, strict=True):
        expected_occurrences[token].append(cast(int, assertion["occurrence_index"]))
    for token, indexes in expected_occurrences.items():
        if sorted(indexes) != list(range(len(indexes))):
            _fail(f"assertion occurrence coverage is invalid: {unit.unit_id}/{token}")
    required = list(
        required_assertion_tokens(
            unit.text, structural_fact=_is_structural_fact_value(unit)
        )
    )
    if sorted(required) != sorted(tokens):
        _fail(f"undeclared assertion token(s) in {unit.unit_id}")
    used_evidence_bindings.update(gate_evidence_binding_ids or set())
    if used_evidence_bindings != set(state_by_evidence_binding):
        _fail(f"unused or missing evidence binding: {unit.unit_id}")


def _validate_evidence_bindings(
    *,
    unit: ReaderUnit,
    raw_bindings: object,
    sales_states: dict[str, dict[str, object]],
    allowed_product_ids: set[str],
    gate_product_ids: set[str] | None = None,
) -> dict[str, dict[str, object]]:
    if type(raw_bindings) is not list:
        _fail(f"evidence_bindings must be a list: {unit.unit_id}")
    supports: dict[str, dict[str, object]] = {}
    for raw in cast(list[object], raw_bindings):
        if type(raw) is not dict:
            _fail(f"evidence binding is not an object: {unit.unit_id}")
        binding = cast(dict[str, object], raw)
        _exact_keys(
            binding,
            {
                "binding_id",
                "evidence_kind",
                "product_id",
                "state",
                "availability_scope",
                "variant_caveat",
                "checked_at_utc",
                "official_url",
                "structured_snapshot_sha256",
                "locator",
            },
            f"evidence binding {unit.unit_id}",
        )
        if binding.get("evidence_kind") != "MANUFACTURER_SALES_STATE":
            _fail(f"unsupported evidence kind: {unit.unit_id}")
        product_id = _strict_string(
            binding.get("product_id"), f"evidence product_id {unit.unit_id}"
        )
        if product_id not in allowed_product_ids:
            _fail(f"sales-state product is outside article scope: {unit.unit_id}")
        if product_id not in unit.subject_product_ids and product_id not in (
            gate_product_ids or set()
        ):
            _fail(
                f"sales-state product does not match reader-unit subject: {unit.unit_id}"
            )
        state = sales_states.get(product_id)
        if state is None:
            _fail(f"sales-state product is absent from contract: {unit.unit_id}")
        binding_id = _strict_string(
            binding.get("binding_id"), f"evidence binding_id {unit.unit_id}"
        )
        if binding_id != f"MSS-{product_id}" or binding_id in supports:
            _fail(f"sales-state binding identity is invalid: {unit.unit_id}")
        for key in (
            "state",
            "availability_scope",
            "variant_caveat",
            "checked_at_utc",
            "official_url",
            "structured_snapshot_sha256",
            "locator",
        ):
            if binding.get(key) != state.get(key):
                _fail(f"sales-state binding {key} drift: {unit.unit_id}")
        supports[binding_id] = state
    return supports


def _accessibility_exemption_matches(
    unit: ReaderUnit, product_aliases: dict[str, tuple[str, ...]]
) -> bool:
    if unit.channel in READER_TEXT_CHANNELS:
        return False
    if unit.text in ACCESSIBILITY_FIXED_TEXTS:
        return True
    if not unit.text.endswith(PRODUCT_NEUTRAL_ALT_SUFFIX):
        return False
    prefix = unit.text[: -len(PRODUCT_NEUTRAL_ALT_SUFFIX)]
    if len(unit.subject_product_ids) != 1:
        return False
    product_id = unit.subject_product_ids[0]
    aliases = product_aliases.get(product_id, ())
    return any(_normalize_text(prefix) == _normalize_text(alias) for alias in aliases)


def _table_or_definition_label_matches(unit: ReaderUnit) -> bool:
    return bool(
        re.search(r"(?:^|/)(?:th|dt)\[\d+\]::text\Z", unit.locator)
        and unit.text in TABLE_OR_DEFINITION_LABELS
        and not required_assertion_tokens(unit.text, structural_fact=False)
    )


def _source_citation_label_matches(unit: ReaderUnit) -> bool:
    return bool(
        unit.channel in READER_TEXT_CHANNELS
        and re.search(r"/(?:a|strong)\[\d+\](?:::text)?\Z", unit.locator)
        and _all_nonempty_clauses_match(SOURCE_LABEL_EXEMPTION_RE, unit.text)
    )


def _unit_requires_claim_review(unit: ReaderUnit) -> bool:
    """Detect factual/recommendation content before considering exemptions."""

    text = unit.text
    if text in METADATA_FIXED_TEXTS or text in METHOD_FIXED_TEXTS:
        return False
    if _source_citation_label_matches(unit):
        return False
    return bool(
        required_assertion_tokens(text, structural_fact=_is_structural_fact_value(unit))
        or _affirmed_sales_matches(text)
        or RECOMMENDATION_CONCLUSION_RE.search(text)
        or CLAIM_REVIEW_REQUIRED_RE.search(text)
        or TERSE_FACT_STATUS_RE.search(text)
        or CAPABILITY_ASSERTION_RE.search(text)
        or GENERIC_QUALITATIVE_ASSERTION_RE.search(text)
    )


def _all_nonempty_clauses_match(pattern: re.Pattern[str], text: str) -> bool:
    clauses = [
        clause.strip()
        for clause in re.split(r"(?<=[。！？])|\n", _normalize_text(text))
        if clause.strip()
    ]
    return bool(clauses) and all(
        pattern.search(clause) is not None for clause in clauses
    )


def _decision_gate_product_ids(
    *,
    unit: ReaderUnit,
    product_aliases: dict[str, tuple[str, ...]],
    allowed_product_ids: set[str],
    sales_states: dict[str, dict[str, object]],
) -> tuple[str, ...]:
    selected = [
        product_id
        for product_id in unit.subject_product_ids
        if product_id in allowed_product_ids
    ]
    selected.extend(
        product_id
        for product_id in _matching_product_ids(unit.text, product_aliases)
        if product_id in allowed_product_ids
    )
    group = _matching_product_group_ids(
        unit.text, product_aliases, tuple(sorted(allowed_product_ids))
    )
    selected.extend(
        product_id for product_id in group if product_id in allowed_product_ids
    )
    product_ids = tuple(dict.fromkeys(selected))
    recommendation = RECOMMENDATION_CONCLUSION_RE.search(unit.text) is not None
    selection = SELECTION_DECISION_RE.search(unit.text) is not None
    if unit.text in MIXED_DISH_SELECTION_REFERENCE_TEXTS:
        selection = True
    if selection and re.search(r"\d+\s*候補.*仕様参考", unit.text):
        product_ids = tuple(sorted(allowed_product_ids))
    if selection and re.search(r"販売状態未確認.*現行販売.*候補", unit.text):
        product_ids = tuple(sorted(allowed_product_ids))
    if SALES_STATE_ASSERTION_RE.search(unit.text) and _matching_product_group_ids(
        unit.text, product_aliases, tuple(sorted(allowed_product_ids))
    ):
        product_ids = tuple(sorted(allowed_product_ids))
    if (recommendation or selection) and not product_ids:
        product_ids = tuple(sorted(allowed_product_ids))
    if recommendation or selection:
        return product_ids
    if unit.context != "DECISION":
        return ()
    # A DECISION-classified unit about an unresolved product must remain
    # fail-closed even when the sentence itself only states a specification.
    # Resolved products do not need a repeated selection gate on every value in
    # a product card; their actual selection conclusions are caught above.
    return tuple(
        product_id
        for product_id in product_ids
        if sales_states.get(product_id, {}).get("state") != "AVAILABLE"
    )


def _expected_decision_gate(
    *,
    article_id: str,
    unit: ReaderUnit,
    product_aliases: dict[str, tuple[str, ...]],
    allowed_product_ids: set[str],
    sales_states: dict[str, dict[str, object]],
    safety_statuses: dict[str, dict[str, object]],
    market_axis_states: dict[str, dict[str, str]],
) -> dict[str, object] | None:
    product_ids = _decision_gate_product_ids(
        unit=unit,
        product_aliases=product_aliases,
        allowed_product_ids=allowed_product_ids,
        sales_states=sales_states,
    )
    if not product_ids:
        return None
    sales_rows: list[dict[str, object]] = []
    safety_rows: list[dict[str, object]] = []
    blocked_reasons: list[str] = []
    for product_id in product_ids:
        sales = sales_states.get(product_id)
        safety = safety_statuses.get(product_id)
        if sales is None or safety is None:
            _fail(
                f"decision gate product is outside evidence contracts: {unit.unit_id}"
            )
        caveat = sales.get("variant_caveat")
        sales_rows.append(
            {
                "product_id": product_id,
                "binding_id": f"MSS-{product_id}",
                "state": sales.get("state"),
                "availability_scope": sales.get("availability_scope"),
                "variant_caveat": caveat,
            }
        )
        safety_rows.append(dict(safety))
        if sales.get("state") != "AVAILABLE":
            blocked_reasons.append(f"SALES_STATE:{product_id}:{sales.get('state')}")
        if caveat is not None and (
            type(caveat) is not dict
            or not _sales_variant_scope_is_explicit(
                unit.text, cast(dict[str, object], caveat)
            )
        ):
            blocked_reasons.append(f"SALES_VARIANT_SCOPE:{product_id}")
        if safety.get("status") != "COMPLETE_NONE_FOUND":
            blocked_reasons.append(
                f"PRODUCT_SAFETY:{product_id}:{safety.get('status')}"
            )
    axes = market_axis_states.get(article_id)
    if axes is None or set(axes) != set(DECISION_GATE_AXES):
        _fail(f"decision gate article axes are incomplete: {unit.unit_id}")
    for axis in DECISION_GATE_AXES:
        if axes[axis] != "OFFICIAL_EVIDENCE_USED":
            blocked_reasons.append(f"ARTICLE_AXIS:{axis}:{axes[axis]}")
    sales_gate = (
        "ELIGIBLE"
        if not any(reason.startswith("SALES_") for reason in blocked_reasons)
        else "BLOCKED"
    )
    safety_gate = (
        "ELIGIBLE"
        if not any(
            reason.startswith(("PRODUCT_SAFETY:", "ARTICLE_AXIS:safety:"))
            for reason in blocked_reasons
        )
        else "BLOCKED"
    )
    selection_gate = "ELIGIBLE" if not blocked_reasons else "BLOCKED"
    return {
        "schema": DECISION_GATE_SCHEMA,
        "product_ids": list(product_ids),
        "sales_binding_ids": [f"MSS-{product_id}" for product_id in product_ids],
        "sales_states": sales_rows,
        "safety_statuses": safety_rows,
        "axis_states": dict(axes),
        "sales_gate": sales_gate,
        "safety_gate": safety_gate,
        "selection_gate": selection_gate,
        "publication_gate": selection_gate,
        "blocked_reasons": blocked_reasons,
    }


def _explicit_product_ids_requiring_support(
    *,
    unit: ReaderUnit,
    product_aliases: dict[str, tuple[str, ...]],
    allowed_product_ids: set[str],
) -> set[str]:
    # An external market-candidate card can contain a selected product's short
    # alias as a substring (C1000 in C1000 Plus, or a shared brand token).  Its
    # closed ``EXT-*`` owner is validated against the exact candidate claim;
    # do not manufacture a second selected-product assertion from that alias.
    if unit.owner_product_id is not None and unit.owner_product_id.startswith("EXT-"):
        return set()
    explicit = {
        product_id
        for product_id in _matching_product_ids(unit.text, product_aliases)
        if product_id in allowed_product_ids
    }
    # Counts and group expressions are checked by their assertion binding and
    # decision gate.  They are not explicit product names: treating a route
    # label such as ``4候補の記事`` as four literal mentions would force A10's
    # subjectless lifecycle link to impersonate four product-detail claims.
    return explicit


def _validate_unit_binding(
    *,
    unit: ReaderUnit,
    raw_binding: object,
    packet_claims: dict[str, dict[str, object]],
    support_by_claim: dict[str, str],
    claim_subjects: dict[str, tuple[str, ...]],
    product_aliases: dict[str, tuple[str, ...]],
    sales_states: dict[str, dict[str, object]],
    allowed_product_ids: set[str],
    article_id: str = "__TEST__",
    safety_statuses: dict[str, dict[str, object]] | None = None,
    market_axis_states: dict[str, dict[str, str]] | None = None,
) -> None:
    if type(raw_binding) is not dict:
        _fail(f"reader-unit binding is not an object: {unit.unit_id}")
    binding = cast(dict[str, object], raw_binding)
    _exact_keys(
        binding,
        {
            "unit_id",
            "locator",
            "channel",
            "text",
            "text_sha256",
            "context",
            "subject_product_ids",
            "owner_product_id",
            "dimension_role",
            "dimension_axis",
            "kind",
            "claim_ids",
            "evidence_bindings",
            "assertion_tokens",
            "exemption_code",
            "decision_gate",
        },
        f"binding {unit.unit_id}",
    )
    for key in (
        "unit_id",
        "locator",
        "channel",
        "text",
        "text_sha256",
        "context",
        "dimension_role",
        "dimension_axis",
    ):
        if binding.get(key) != getattr(unit, key):
            _fail(f"reader-unit {key} drift: {unit.unit_id}")
    if binding.get("subject_product_ids") != list(unit.subject_product_ids):
        _fail(f"reader-unit product subject drift: {unit.unit_id}")
    if binding.get("owner_product_id") != unit.owner_product_id:
        _fail(f"reader-unit product owner drift: {unit.unit_id}")
    if NESTED_COMPARATOR_NEGATION_RE.search(unit.text):
        _fail(f"nested comparator negation is unsupported: {unit.unit_id}")

    kind = binding.get("kind")
    if kind not in KINDS:
        _fail(f"invalid or unclassified reader unit: {unit.unit_id}")
    if unit.context not in CONTEXTS:
        _fail(f"invalid derived reader context: {unit.unit_id}")
    claim_ids = _strict_string_list(
        binding.get("claim_ids"), f"unit claims {unit.unit_id}"
    )
    if not set(claim_ids) <= packet_claims.keys():
        _fail(f"reader unit references a claim outside its packet: {unit.unit_id}")
    unit_subjects = set(unit.subject_product_ids)
    external_owner = (
        unit.owner_product_id
        if unit.owner_product_id is not None
        and unit.owner_product_id.startswith("EXT-")
        else None
    )
    for claim_id in claim_ids:
        bound_subjects = set(claim_subjects[claim_id])
        if bound_subjects and (
            not unit_subjects or unit_subjects.isdisjoint(bound_subjects)
        ):
            generic_selection_inference = bool(
                not unit_subjects
                and SELECTION_DECISION_RE.search(unit.text)
                and packet_claims[claim_id].get("classification")
                == "EDITORIAL_INFERENCE"
                and bound_subjects <= allowed_product_ids
            )
            if not generic_selection_inference:
                _fail(
                    "source claim does not match reader-unit subject: "
                    f"{unit.unit_id}/{claim_id}"
                )
        if (
            external_owner is not None
            and _is_external_candidate_claim(claim_id, claim_subjects[claim_id])
            and not _external_claim_matches_owner(
                claim=packet_claims[claim_id],
                support=support_by_claim[claim_id],
                external_owner=external_owner,
                product_aliases=product_aliases,
            )
            and packet_claims[claim_id].get("market_candidate_id")
            not in _matching_product_ids(unit.text, product_aliases)
        ):
            _fail(
                "external candidate claim does not match reader-unit owner: "
                f"{unit.unit_id}/{claim_id}"
            )
    # Closed UNKNOWN sales prose is validated against its exact MSS row (or an
    # external RECHECK claim) below.  A mixed sold-out/missing-UI statement is
    # accepted only with the dedicated embedded external gate.
    if (
        _sales_unknown_overlap(unit.text)
        and CLOSED_UNKNOWN_SALES_PHRASE_RE.search(unit.text) is None
        and not _bounded_external_out_of_stock_ui_gap(
            unit=unit,
            claim_ids=claim_ids,
            packet_claims=packet_claims,
            support_by_claim=support_by_claim,
            claim_subjects=claim_subjects,
        )
        and not _bounded_external_restock_only_lifecycle(
            unit=unit,
            claim_ids=claim_ids,
            packet_claims=packet_claims,
            support_by_claim=support_by_claim,
            claim_subjects=claim_subjects,
            product_aliases=product_aliases,
        )
        and not _bounded_a10_unknown_purchase_ui_exclusion(
            unit=unit,
            claim_ids=claim_ids,
            packet_claims=packet_claims,
            support_by_claim=support_by_claim,
            claim_subjects=claim_subjects,
            product_aliases=product_aliases,
        )
    ):
        _fail(f"sales-state wording contains an unknown qualifier: {unit.unit_id}")
    exemption = binding.get("exemption_code")
    expected_gate = _expected_decision_gate(
        article_id=article_id,
        unit=unit,
        product_aliases=product_aliases,
        allowed_product_ids=allowed_product_ids,
        sales_states=sales_states,
        safety_statuses=safety_statuses or {},
        market_axis_states=market_axis_states or {},
    )
    raw_gate = binding.get("decision_gate")
    if raw_gate != expected_gate:
        _fail(f"reader decision gate drift or fail-open state: {unit.unit_id}")
    gate_product_ids = (
        set(cast(list[str], expected_gate["product_ids"]))
        if expected_gate is not None
        else set()
    )
    gate_evidence_binding_ids = (
        set(cast(list[str], expected_gate["sales_binding_ids"]))
        if expected_gate is not None
        else set()
    )
    evidence_supports = _validate_evidence_bindings(
        unit=unit,
        raw_bindings=binding.get("evidence_bindings"),
        sales_states=sales_states,
        allowed_product_ids=allowed_product_ids,
        gate_product_ids=gate_product_ids,
    )
    if not gate_evidence_binding_ids <= set(evidence_supports):
        _fail(f"decision gate lacks bound manufacturer sales rows: {unit.unit_id}")

    if kind == "NON_CLAIM":
        if claim_ids or evidence_supports or binding.get("assertion_tokens") != []:
            _fail(f"NON_CLAIM unit cannot carry claims/assertions: {unit.unit_id}")
        if exemption not in EXEMPTION_CODES:
            _fail(f"NON_CLAIM unit requires a closed exemption: {unit.unit_id}")
        affiliate_fallback = bool(AFFILIATE_FALLBACK_STATUS_RE.search(unit.text))
        structural_method = bool(
            exemption == "EDITORIAL_METHOD" and unit.text in METHOD_FIXED_TEXTS
        )
        if (
            _is_structural_fact_value(unit)
            and not affiliate_fallback
            and not structural_method
        ):
            _fail(f"comparison value cannot be NON_CLAIM: {unit.unit_id}")
        risky = required_assertion_tokens(
            unit.text, structural_fact=_is_structural_fact_value(unit)
        )
        accessibility_match = _accessibility_exemption_matches(unit, product_aliases)
        if (
            _unit_requires_claim_review(unit)
            and not accessibility_match
            and not affiliate_fallback
        ):
            _fail(f"fact-like NON_CLAIM unit has no eligible exemption: {unit.unit_id}")
        exemption_matches = {
            "ACCESSIBILITY_OR_DECORATION": accessibility_match,
            "DISCLOSURE_POLICY": bool(
                unit.channel in READER_TEXT_CHANNELS
                and _all_nonempty_clauses_match(DISCLOSURE_EXEMPTION_RE, unit.text)
            ),
            "EDITORIAL_METADATA": bool(
                unit.channel in READER_TEXT_CHANNELS
                and (
                    unit.text in METADATA_FIXED_TEXTS
                    or _all_nonempty_clauses_match(METADATA_EXEMPTION_RE, unit.text)
                )
            ),
            "EDITORIAL_METHOD": bool(
                unit.channel in READER_TEXT_CHANNELS
                and (
                    unit.text in METHOD_FIXED_TEXTS
                    or _all_nonempty_clauses_match(METHOD_EXEMPTION_RE, unit.text)
                )
            ),
            "NAVIGATION_OR_UI": bool(
                unit.channel in READER_TEXT_CHANNELS
                and (
                    _all_nonempty_clauses_match(NAVIGATION_EXEMPTION_RE, unit.text)
                    or affiliate_fallback
                    or (
                        re.search(r"/h[1-6]\[\d+\]::text\Z", unit.locator) and not risky
                    )
                )
            ),
            "READER_SCOPE_OR_GUIDANCE": bool(
                unit.channel in READER_TEXT_CHANNELS
                and (
                    unit.context == "GENERAL"
                    or unit.channel in {"WORDPRESS_TITLE", "WORDPRESS_EXCERPT"}
                )
                and not unit.subject_product_ids
                and not _is_structural_fact_value(unit)
                and not risky
            ),
            "SOURCE_CITATION_LABEL": bool(_source_citation_label_matches(unit)),
            "TABLE_OR_DEFINITION_LABEL": bool(
                unit.channel in READER_TEXT_CHANNELS
                and _table_or_definition_label_matches(unit)
            ),
        }
        if not exemption_matches[cast(str, exemption)]:
            _fail(f"NON_CLAIM exemption does not match reader text: {unit.unit_id}")
        if risky and not (
            (exemption == "ACCESSIBILITY_OR_DECORATION" and accessibility_match)
            or (exemption == "NAVIGATION_OR_UI" and affiliate_fallback)
        ):
            _fail(f"fact-like NON_CLAIM unit has no eligible exemption: {unit.unit_id}")
        if _has_reader_decision_unknown(unit.text):
            eligible_limit = (
                exemption == "EDITORIAL_METHOD"
                and (
                    unit.text in METHOD_FIXED_TEXTS
                    or METHOD_UNKNOWN_EXEMPTION_RE.fullmatch(unit.text) is not None
                )
            ) or (
                exemption == "EDITORIAL_METADATA"
                and METADATA_UNKNOWN_EXEMPTION_RE.fullmatch(unit.text) is not None
            )
            if not eligible_limit:
                _fail(f"unknown-status text cannot be NON_CLAIM: {unit.unit_id}")
        if TERSE_FACT_STATUS_RE.search(unit.text):
            _fail(f"decision-critical assertion cannot be NON_CLAIM: {unit.unit_id}")
        return

    if exemption is not None:
        _fail(f"claim-bearing/UNKNOWN unit cannot have an exemption: {unit.unit_id}")
    if kind == "UNKNOWN":
        if claim_ids or evidence_supports or binding.get("assertion_tokens") != []:
            _fail(f"UNKNOWN unit cannot carry claims/assertions: {unit.unit_id}")
        if (
            unit.context != "COMPARISON"
            or UNKNOWN_STATUS_RE.fullmatch(unit.text) is None
            or required_assertion_tokens(
                unit.text, structural_fact=_is_structural_fact_value(unit)
            )
        ):
            _fail(
                f"UNKNOWN is allowed only as explicit comparison status: {unit.unit_id}"
            )
        return

    if kind == "RECHECK_REQUIRED":
        if unit.context == "DECISION":
            _fail(f"RECHECK_REQUIRED unit reached a decision surface: {unit.unit_id}")
        if evidence_supports:
            _fail(
                f"RECHECK_REQUIRED unit cannot borrow selected sales evidence: "
                f"{unit.unit_id}"
            )
        if not claim_ids:
            _fail(f"RECHECK_REQUIRED unit has no external reference: {unit.unit_id}")
        if RECHECK_REQUIRED_DISCLOSURE_RE.search(unit.text) is None:
            _fail(f"RECHECK_REQUIRED disclosure is not reader-visible: {unit.unit_id}")
        for claim_id in claim_ids:
            claim = packet_claims[claim_id]
            if (
                claim["classification"] != "DECISION_CRITICAL_UNKNOWN"
                or claim["status"] != "UNCONFIRMED_FROM_BOUND_OFFICIAL_SOURCE"
                or not claim_id.endswith("-REFERENCE")
                or not _is_external_candidate_claim(claim_id, claim_subjects[claim_id])
            ):
                _fail(
                    f"RECHECK_REQUIRED unit uses a completed/non-reference claim: "
                    f"{unit.unit_id}/{claim_id}"
                )
        external_closed_unknown = bool(CLOSED_UNKNOWN_SALES_PHRASE_RE.search(unit.text))
        if not (
            _has_reader_decision_unknown(unit.text) or external_closed_unknown
        ) or not any(
            _unknown_boundary_supported(unit.text, support_by_claim[claim_id])
            for claim_id in claim_ids
        ):
            _fail(
                f"RECHECK_REQUIRED unit lacks a matching unknown boundary: "
                f"{unit.unit_id}"
            )
        _validate_assertions(
            unit=unit,
            binding=binding,
            unit_claim_ids=claim_ids,
            inference_claim_ids=set(),
            support_by_claim=support_by_claim,
            claim_subjects=claim_subjects,
            product_aliases=product_aliases,
            state_by_evidence_binding={},
            subject_sales_states=sales_states,
            allow_unknown_reference=True,
            gate_evidence_binding_ids=set(),
        )
        return

    if external_owner is not None and not any(
        _is_external_candidate_claim(claim_id, claim_subjects[claim_id])
        and _external_claim_matches_owner(
            claim=packet_claims[claim_id],
            support=support_by_claim[claim_id],
            external_owner=external_owner,
            product_aliases=product_aliases,
        )
        for claim_id in claim_ids
    ):
        _fail(f"external candidate owner has no matching packet claim: {unit.unit_id}")
    if not claim_ids and not evidence_supports:
        _fail(f"claim-bearing reader unit has no semantic binding: {unit.unit_id}")
    if _has_reader_decision_unknown(unit.text) and not any(
        _unknown_boundary_supported(unit.text, support_by_claim[claim_id])
        for claim_id in claim_ids
    ):
        _fail(f"unknown boundary is not bound to the same claim topic: {unit.unit_id}")
    classifications = {
        packet_claims[claim_id]["classification"] for claim_id in claim_ids
    }
    if "DECISION_CRITICAL_UNKNOWN" in classifications:
        _fail(
            f"unknown external claim was promoted to a completed kind: {unit.unit_id}"
        )
    if kind == "VERIFIABLE" and classifications - {"MAJOR_VERIFIABLE"}:
        _fail(f"VERIFIABLE unit has non-verifiable claim: {unit.unit_id}")
    if kind == "EDITORIAL_INFERENCE" and "EDITORIAL_INFERENCE" not in classifications:
        _fail(f"EDITORIAL_INFERENCE unit has no inference claim: {unit.unit_id}")
    recommendation = RECOMMENDATION_CONCLUSION_RE.search(unit.text) is not None
    if recommendation and (
        kind != "EDITORIAL_INFERENCE"
        or "EDITORIAL_INFERENCE" not in classifications
        or expected_gate is None
    ):
        _fail(
            f"recommendation conclusion lacks inference/selection gate: {unit.unit_id}"
        )
    explicitly_named = _explicit_product_ids_requiring_support(
        unit=unit,
        product_aliases=product_aliases,
        allowed_product_ids=allowed_product_ids,
    )
    semantically_covered = set(gate_product_ids)
    semantically_covered.update(
        product_id
        for claim_id in claim_ids
        for product_id in claim_subjects[claim_id]
        if product_id in allowed_product_ids
    )
    semantically_covered.update(
        cast(str, state["product_id"])
        for state in evidence_supports.values()
        if state.get("product_id") in allowed_product_ids
    )
    if not explicitly_named <= semantically_covered:
        missing = sorted(explicitly_named - semantically_covered)
        _fail(
            f"explicit product lacks semantic coverage: {unit.unit_id}/{','.join(missing)}"
        )
    relative_tokens = {
        token
        for token in required_assertion_tokens(
            unit.text, structural_fact=_is_structural_fact_value(unit)
        )
        if RELATIVE_ASSERTION_RE.fullmatch(token)
    }
    if relative_tokens and "EDITORIAL_INFERENCE" not in classifications:
        _fail(f"relative comparison lacks an inference claim: {unit.unit_id}")
    _validate_assertions(
        unit=unit,
        binding=binding,
        unit_claim_ids=claim_ids,
        inference_claim_ids={
            claim_id
            for claim_id, claim in packet_claims.items()
            if claim["classification"] == "EDITORIAL_INFERENCE"
        },
        support_by_claim=support_by_claim,
        claim_subjects=claim_subjects,
        product_aliases=product_aliases,
        state_by_evidence_binding=evidence_supports,
        subject_sales_states=sales_states,
        allow_unknown_reference=False,
        gate_evidence_binding_ids=gate_evidence_binding_ids,
    )


def validate_source_refresh_inputs(root: Path = ROOT) -> None:
    """Check acquisition inputs, not publication readiness or reader approval.

    Sources must be capturable before the reader ledger can be reviewed against
    them. Like development replay, this allows expired observations; future dates, origin,
    identity, snapshot hashes, and source-contract validation remain mandatory.
    """
    _load_repository_model(root, require_fresh_sales_state=False)


def validate_repository(
    root: Path = ROOT,
    ledger: dict[str, object] | None = None,
    *,
    require_fresh_sales_state: bool = True,
) -> None:
    """Validate all semantic bindings; publication callers require fresh data.

    Development can replay historical captures without changing observations or
    granting publication authority. Only elapsed age is optional, never hashes,
    identity, future timestamps, or the complete reader ledger validation.
    """
    model = _load_repository_model(
        root, require_fresh_sales_state=require_fresh_sales_state
    )
    document = ledger if ledger is not None else _load_json(root, LEDGER_RELATIVE)
    _exact_keys(
        document,
        {"schema", "version", "article_ids", "evidence_contracts", "articles"},
        "ledger",
    )
    if document.get("schema") != SCHEMA or document.get("version") != VERSION:
        _fail("ledger schema/version mismatch")
    if _strict_string_list(document.get("article_ids"), "ledger article_ids") != list(
        ARTICLE_IDS
    ):
        _fail("ledger article set/order changed; new posts are forbidden")
    evidence_contracts = document.get("evidence_contracts")
    if type(evidence_contracts) is not list or len(evidence_contracts) != 3:
        _fail("ledger evidence contract inventory is invalid")
    expected_contracts = [
        {
            "evidence_kind": "MANUFACTURER_SALES_STATE",
            "path": SALES_STATE_RELATIVE.as_posix(),
            "document_sha256": model.sales_state_document_sha256,
        },
        {
            "evidence_kind": "PRODUCT_SAFETY_QUERY_RECEIPTS",
            "path": PRODUCT_SAFETY_RECEIPT_RELATIVE.as_posix(),
            "document_sha256": model.safety_receipt_document_sha256,
        },
        {
            "evidence_kind": "MARKET_CANDIDATE_DUE_DILIGENCE",
            "path": MARKET_AUDIT_RELATIVE.as_posix(),
            "document_sha256": model.market_audit_document_sha256,
        },
    ]
    for raw_contract, expected_contract in zip(
        cast(list[object], evidence_contracts), expected_contracts, strict=True
    ):
        if type(raw_contract) is not dict:
            _fail("ledger evidence contract is not an object")
        contract = cast(dict[str, object], raw_contract)
        _exact_keys(
            contract,
            {"evidence_kind", "path", "document_sha256"},
            "ledger evidence contract",
        )
        if contract != expected_contract:
            _fail("ledger evidence contract drift")
    raw_article_bindings = document.get("articles")
    if type(raw_article_bindings) is not list:
        _fail("ledger articles must be a list")
    article_bindings = cast(list[object], raw_article_bindings)
    if len(article_bindings) != len(ARTICLE_IDS):
        _fail("ledger must bind exactly ten articles")

    for expected_article_id, raw_article_binding in zip(
        ARTICLE_IDS, article_bindings, strict=True
    ):
        if type(raw_article_binding) is not dict:
            _fail(f"ledger article is not an object: {expected_article_id}")
        article_binding = cast(dict[str, object], raw_article_binding)
        _exact_keys(
            article_binding,
            {
                "article_id",
                "content_ref",
                "authoring_input",
                "source_packet_ref",
                "fact_packet_sha256",
                "reader_units_sha256",
                "units",
            },
            f"ledger article {expected_article_id}",
        )
        if article_binding.get("article_id") != expected_article_id:
            _fail("ledger article order/identity mismatch")
        portfolio_article = model.articles[expected_article_id]
        packet = model.packets[expected_article_id]
        content_ref = _strict_string(
            portfolio_article.get("content_ref"), f"content_ref {expected_article_id}"
        )
        if article_binding.get("content_ref") != content_ref:
            _fail(f"content_ref drift: {expected_article_id}")
        if article_binding.get("authoring_input") != _authoring_input(
            root, model, expected_article_id, content_ref
        ):
            _fail(
                f"authoring input changed without ledger review: {expected_article_id}"
            )
        if article_binding.get("source_packet_ref") != packet.get("source_packet_ref"):
            _fail(f"source packet ref drift: {expected_article_id}")
        if article_binding.get("fact_packet_sha256") != packet.get(
            "fact_packet_sha256"
        ):
            _fail(f"source packet changed without ledger review: {expected_article_id}")

        relative_content = Path(content_ref)
        payload = _read_regular(root, relative_content, MAX_HTML_BYTES)
        units = _final_reader_units(
            expected_article_id,
            portfolio_article,
            payload,
            model.product_aliases[expected_article_id],
        )
        if article_binding.get("reader_units_sha256") != _unit_digest(units):
            _fail(f"reader-unit digest drift: {expected_article_id}")
        raw_units = article_binding.get("units")
        if type(raw_units) is not list or len(raw_units) != len(units):
            _fail(f"reader-unit inventory drift: {expected_article_id}")
        selected_product_ids = set(
            _strict_string_list(
                portfolio_article.get("product_ids"),
                f"article product_ids {expected_article_id}",
            )
        )
        reference_product_ids = {
            product_id
            for claim in model.claims[expected_article_id].values()
            if claim.get("portfolio_candidate_disposition") == "REFERENCE_ONLY"
            for product_id in _strict_string_list(
                claim.get("subject_product_ids"),
                f"portfolio reference subjects {claim['claim_id']}",
            )
        }
        # Reader-visible lifecycle routing may name a product without selecting
        # it for an affiliate card.  Such REFERENCE_ONLY products remain outside
        # the selected portfolio, but their claims still need the same exact
        # official sales-state evidence as selected products.
        allowed_product_ids = selected_product_ids | reference_product_ids
        for unit, raw_binding in zip(units, cast(list[object], raw_units), strict=True):
            _validate_unit_binding(
                article_id=expected_article_id,
                unit=unit,
                raw_binding=raw_binding,
                packet_claims=model.claims[expected_article_id],
                support_by_claim=model.supports[expected_article_id],
                claim_subjects=model.claim_subjects[expected_article_id],
                product_aliases=model.product_aliases[expected_article_id],
                sales_states=model.sales_states,
                safety_statuses=model.safety_statuses,
                market_axis_states=model.market_axis_states,
                allowed_product_ids=allowed_product_ids,
            )
    expected_ledger_sha256 = (
        REVIEWED_READER_LEDGER_SHA256
        if require_fresh_sales_state
        else DEVELOPMENT_READER_LEDGER_SHA256
    )
    if _canonical_sha256(document) != expected_ledger_sha256:
        _fail("reader ledger is not the independently reviewed semantic allow-list")


def build_skeleton(root: Path = ROOT) -> bytes:
    """Print-only proposal; every unit remains deliberately unclassified."""

    model = _load_repository_model(root)
    articles: list[dict[str, object]] = []
    for article_id in ARTICLE_IDS:
        content_ref = _strict_string(
            model.articles[article_id].get("content_ref"), f"content_ref {article_id}"
        )
        units = _final_reader_units(
            article_id,
            model.articles[article_id],
            _read_regular(root, Path(content_ref), MAX_HTML_BYTES),
            model.product_aliases[article_id],
        )
        articles.append(
            {
                "article_id": article_id,
                "content_ref": content_ref,
                "authoring_input": _authoring_input(
                    root, model, article_id, content_ref
                ),
                "source_packet_ref": model.packets[article_id]["source_packet_ref"],
                "fact_packet_sha256": model.packets[article_id]["fact_packet_sha256"],
                "reader_units_sha256": _unit_digest(units),
                "units": [
                    {
                        "unit_id": unit.unit_id,
                        "locator": unit.locator,
                        "channel": unit.channel,
                        "text": unit.text,
                        "text_sha256": unit.text_sha256,
                        "context": unit.context,
                        "subject_product_ids": list(unit.subject_product_ids),
                        "owner_product_id": unit.owner_product_id,
                        "dimension_role": unit.dimension_role,
                        "dimension_axis": unit.dimension_axis,
                        "kind": "UNCLASSIFIED",
                        "claim_ids": [],
                        "evidence_bindings": [],
                        "assertion_tokens": [],
                        "exemption_code": None,
                        "decision_gate": None,
                    }
                    for unit in units
                ],
            }
        )
    return (
        json.dumps(
            {
                "schema": SCHEMA,
                "version": VERSION,
                "article_ids": list(ARTICLE_IDS),
                "evidence_contracts": [
                    {
                        "evidence_kind": "MANUFACTURER_SALES_STATE",
                        "path": SALES_STATE_RELATIVE.as_posix(),
                        "document_sha256": model.sales_state_document_sha256,
                    },
                    {
                        "evidence_kind": "PRODUCT_SAFETY_QUERY_RECEIPTS",
                        "path": PRODUCT_SAFETY_RECEIPT_RELATIVE.as_posix(),
                        "document_sha256": model.safety_receipt_document_sha256,
                    },
                    {
                        "evidence_kind": "MARKET_CANDIDATE_DUE_DILIGENCE",
                        "path": MARKET_AUDIT_RELATIVE.as_posix(),
                        "document_sha256": model.market_audit_document_sha256,
                    },
                ],
                "articles": articles,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the authored ten-article reader claim ledger."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="validate the tracked ledger"
    )
    mode.add_argument(
        "--skeleton",
        action="store_true",
        help="print an UNCLASSIFIED proposal to stdout without writing files",
    )
    parser.add_argument(
        "--development",
        action="store_true",
        help="Validate historical repository evidence without publication authority.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.skeleton:
            sys.stdout.buffer.write(build_skeleton())
            return 0
        validate_repository(require_fresh_sales_state=not args.development)
    except CoverageFailure as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"reader claim coverage valid: {LEDGER_RELATIVE.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
