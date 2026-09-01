"""Closed transport and owner-store tests for ST-1704 official sources."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
import html
import json
from pathlib import Path
import re
import runpy
import ssl
import stat
import tempfile
from typing import Final, cast
import unicodedata

import pytest

import raos.adapters.self_hosted_editorial_source_capture as capture_module
from raos.adapters.self_hosted_editorial_pilot_json import (
    OWNER_DIRECTORY,
    SOURCE_DIRECTORY,
    read_official_source_capture_evidence,
    source_body_relative_path,
    source_evidence_relative_path,
)
from raos.domain.editorial.self_hosted_editorial_pilot import (
    EditorialPilotFailure,
    EditorialPilotFailureCode,
    bytes_sha256,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CAPTURE_SCRIPT = REPOSITORY_ROOT / "scripts/st1704_official_source_capture.py"
WORDPRESS_SCRIPT = REPOSITORY_ROOT / "scripts/st1704_self_hosted_editorial_pilot.py"
SLICE_ROOT = REPOSITORY_ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1"
SOURCES_ROOT = SLICE_ROOT / "sources"
FIXED_NOW = datetime(2026, 8, 23, 12, 34, 56, tzinfo=timezone.utc)
UNIQUE_FRAGMENT = "定格容量は288Whです。"
SECOND_UNIQUE_FRAGMENT = "定格出力は300Wです。"
HTML_BODY = (
    '<!doctype html><html lang="ja"><head><title>公式仕様</title></head>'
    f"<body><p>{UNIQUE_FRAGMENT}</p></body></html>"
).encode()
POLICY_REFS = frozenset(
    {
        "SRC-CAA-STEALTH-MARKETING-QA",
        "SRC-GOOGLE-QUALIFY-OUTBOUND-LINKS",
        "SRC-RAKUTEN-AFFILIATE-GUIDELINE",
    }
)
NEW_SOURCE_REQUIRED_LOCATOR_TOKENS: Final[dict[str, tuple[str, ...]]] = {
    "SRC-ANKER-SOLIX-C300-SAFETY-MANUAL": (
        "Product Number: A1722",
        "分解しないでください",
        "一般ゴミとして廃棄しないでください",
        "3 ヶ月に一度",
    ),
    "SRC-ANKER-SOLIX-C800-SAFETY-MANUAL": (
        "Product Number: A1753",
        "分解しないでください",
        "3 ヶ月に一度",
    ),
    "SRC-ANKER-SOLIX-C800-PLUS-SAFETY-MANUAL": (
        "Product Number: A1754",
        "分解しないでください",
        "3 ヶ月に一度",
    ),
    "SRC-ANKER-SOLIX-C1000-SAFETY-MANUAL": (
        "Product Number: A1761",
        "分解しないでください",
        "3 ヶ月に一度",
    ),
    "SRC-ANKER-SOLIX-C1000-GEN2-SAFETY-MANUAL": (
        "Product Number: A1763",
        "分解しないでください",
        "3 ヶ月に一度",
    ),
    "SRC-ANKER-SOLIX-JP-SUPPORT": (
        "国内に修理センター",
        "電話 / LINE / メール / チャット",
        "送料はお客様ご負担",
    ),
    "SRC-JACKERY-JP-REPAIR-SERVICE": (
        "ポータブル電源修理の申し込み",
        "Jackery Japan カスタマーサポート",
    ),
    "SRC-JACKERY-JP-RECYCLING": (
        "日本国内で販売されたJackery ポータブル電源本体のみ",
        "送料はお客様のご負担",
    ),
    "SRC-DJI-POWER-1000-V2-SAFETY-GUIDELINES-JA": (
        "DYM1000V2L/DYM1000V2H",
        "公式サポートまたは正規販売店",
    ),
    "SRC-DJI-POWER-1000-V2-USER-MANUAL-JA": (
        "メンテナンス",
        "6 ヶ月に 1 回",
        "通常の廃棄コンテナ",
    ),
    "SRC-DJI-JP-AFTERSALES-POLICY": (
        "DJI Power 1000 V2",
        "60ヶ月",
        "オンライン修理受付サービス",
    ),
    "SRC-PROTECA-STARIA-CXR-02350": ("H45×W34×D20", "22 L", "2.4kg"),
    "SRC-PROTECA-FRESTER-EX-01550": (
        "H45×W34×D20/24",
        "26/33 L",
        "2.8kg",
        "フロントオープン",
    ),
    "SRC-ACE-PALISADES3-Z-06910": (
        "H45×W34×D20",
        "21 L",
        "2.6kg",
        "キャスターストッパー",
    ),
    "SRC-BERMAS-INTER-CITY-60524": (
        "W34×H45×D20",
        "約22L",
        "約2.8kg",
        "USBポートの廃止",
    ),
    "SRC-JAL-DOMESTIC-CARRY-ON": (
        "55cm×40cm×25cm",
        "45cm×35cm×20cm",
        "10kg",
        "ハンドルやキャスター",
    ),
    "SRC-PROTECA-AEROFLEX-DX2-01521": (
        "H55×W36×D23",
        "35 L",
        "2.1kg",
        "MADE IN JAPAN",
    ),
    "SRC-SAMSONITE-C-LITE-CS2-09007": (
        "CS2*09007",
        "55*40*20",
        "Curv",
        "36(42) L",
        "2,1 kg",
    ),
    "SRC-SAMSONITE-CATALOG-2025": (
        "A154 C-LITE",
        "134679",
        "40 x 55 x 20/23",
        "36/42 l",
        "2.1 kg",
    ),
    "SRC-AMERICAN-TOURISTER-APPLITE4-QJ6-68002": (
        "QJ6-68002",
        "55 x 35 x 25/28",
        "38 /40",
        "2.1",
        "リサイクルポリエステル",
        "ソフトケース",
    ),
    "SRC-FREQUENTER-LIEVE-1-250": (
        "横33cm×縦48cm×奥行23cm",
        "横35cm×縦55cm×奥行23m=113cm",
        "約2.7kg",
        "約33L",
        "1-623",
    ),
    "SRC-INNOVATOR-INV50": (
        "INV50 Pale Blue 38L Cabin",
        "H55 x W35 x D25",
        "3.3 kg",
        "3room収納",
        "ワイドオープン",
        "ブレーキ",
    ),
    "SRC-PROTECA-FRESTER-EX-01551": (
        "H55×W37×D23/27",
        "36/45 L",
        "3.4kg",
        "MADE IN JAPAN",
    ),
    "SRC-BERMAS-INTER-CITY-III-60570": (
        "W36×H54×D24",
        "約36L",
        "約3.3kg",
        "13インチPC",
        "55mm",
    ),
    "SRC-BERMAS-INTER-CITY-II-60561": (
        "W35×H55×D25",
        "約36L",
        "約3.5kg",
        "13インチPC",
        "Type-C",
    ),
    "SRC-IROBOT-ROOMBA-MINI-SLIM-F115060": (
        "F115060",
        "24.5（奥行き）×24.5（幅）×9.2（高さ）",
        "8.6（奥行き）×22.2（幅）×12.3（高さ）",
        "約2kg",
        "充電スタンドでの自動ゴミ収集なし",
    ),
    "SRC-PANASONIC-NP-TML1": (
        "6点",
        "送風乾燥",
        "約2.5L",
        "幅310×高さ435×奥行225",
        "約7.5㎏",
    ),
    "SRC-PANASONIC-SOLOTA-IDENTITY": ("SOLOTA", "NP-TML1", "ホワイト"),
    "SRC-THANKO-RAKUA-MINI-PLUS": (
        "tk-mdw22b",
        "再入荷(予約開始)通知",
    ),
    "SRC-SIROCA-DISHWASHER-INSTALLATION": (
        "SS-MA251",
        "幅 42 cm",
        "奥行 44 cm",
        "高さ 47 cm",
        "76.0 cm",
        "上面：70 cm以上",
    ),
    "SRC-ELECOM-NESTOUT-700N": ("DE-NEPS700NBE", "712.25Wh", "700W"),
    "SRC-BLUETTI-DISCONTINUED-MODELS": (
        "BLUETTI AORA 80",
        "2026年4月20日に販売終了",
        "終売",
    ),
    "SRC-ANKER-SOLIX-C1000-PLUS": ("1024Wh", "1700W", "11.3kg"),
    "SRC-AQUA-ADW-M28B": ("28点", "幅370×奥行510×高さ452", "4.5L"),
    "SRC-PANASONIC-RULO-MINI-MC-RSC10": (
        "幅249mm×奥行249mm×高さ92mm",
        "幅134mm×奥行100mm×高さ99mm",
    ),
    "SRC-EUFY-E20-T2070": ("T2070511", "Sold Out", "在庫切れ"),
    "SRC-EUFY-AUTOEMPTY-C10-T2292": (
        "T2292511",
        "在庫わずか",
        "約32.5 x 32.3 x 7.2cm",
        "約27.5 x 19.1 x 21.2cm",
        "水拭き",
        "自動ゴミ収集システム",
        "18ヶ月保証 + 6ヶ月",
        "交換用ダストバッグ",
        "交換用サイドブラシ",
        "交換用フィルター",
        "交換用回転ブラシ",
        "交換用バッテリー",
    ),
    "SRC-ROBOROCK-SAROS-10": (
        "350 × 353 × 79.8",
        "409 × 440 × 470",
        "8way全自動ドック",
    ),
    "SRC-EUFY-OMNI-E25-T2353": (
        "32.7 x 34.6 x 11.1",
        "37.0 x 46.2 x 43.7",
        "HydroJet",
        "全自動クリーニングステーション",
    ),
    "SRC-DREAME-X50-ULTRA": (
        "89mm",
        "457 × 340 × 590",
        "最大6cm段差対応",
        "6way全自動PowerDock",
    ),
    "SRC-ECOVACS-DEEBOT-X8-PRO": (
        "353*351.5*98",
        "350*477*533",
        "ローラーモップを完璧に洗浄",
        "最大63℃の熱風乾燥",
    ),
    "SRC-RIMOWA-CABIN-U-82350181": ("50 x 幅 35 x 奥行 20", "2 kg", "28 L"),
    "SRC-SAMSONITE-AUDRINA-SPINNER45": ("47.5 x 37.5 x 24.0", "UB8*09001"),
    "SRC-MUJI-HARD-CARRY-20L": (
        "商品番号23184182",
        "タテ４７×ヨコ３２×マチ２０．５ｃｍ",
        "ストッパー機能付き",
    ),
    "SRC-SAMSONITE-C-LITE-SPINNER55EXP-MIDNIGHT": (
        "55 x 40 x 20/23",
        "36 /42",
        "2.1",
    ),
    "SRC-MUJI-HARD-CARRY-36L-SECTION": ("36L", "2.9kg", "キャスターストッパー"),
    "SRC-MUJI-FRONT-OPEN-32L": (
        "商品番号84950087",
        "タテ５４×ヨコ３７×マチ２４ｃｍ",
        "フルオーブンも可能",
        "高さ1cmきざみ",
        "静かな双輪キャスター",
    ),
    "SRC-SAMSONITE-C-LITE-SPINNER55EXP-BLACK": ("55 x 40 x 20/23", "36 /42"),
    "SRC-SWITCHBOT-K11-WIFI-FUNCTIONS": ("2.4GHz", "Schedule", "Map"),
    "SRC-SWITCHBOT-K11-SETUP": ("SwitchBot App", "SSID", "2.4GHz"),
    "SRC-ECOFLOW-RIVER3-PLUS": (
        "286Wh",
        "600W",
        "販売終了",
        "RIVER 3 Plus (290)",
    ),
    "SRC-ECOFLOW-DELTA3-PLUS": (
        "1024Wh",
        "1500W",
        "12.5",
        "売り切れ",
        "available",
    ),
    "SRC-BLUETTI-AORA30-V2": ("AORA 30 V2", '"available":true'),
    "SRC-BLUETTI-AORA100-V2": ("AORA 100 V2", '"available":true'),
    "SRC-BLUETTI-AORA-SERIES-COLLECTION": (
        "AORA 30 V2: 288Wh",
        "重量約4.3kg",
        "AORA 100 V2: 1024Wh",
        "重量約11.5kg",
    ),
}
REMOVED_RAKUTEN_ACE_REFS = frozenset(
    {
        "SRC-RAKUTEN-ACE-CRESTA-06316",
        "SRC-RAKUTEN-ACE-DIFFERENCE-05721",
        "SRC-RAKUTEN-ACE-MAXPASS4-01471",
    }
)

# This fixture is intentionally independent of the locator contract.  A URL,
# claim id, and exactly-once fragment are structural evidence; these tokens are
# the separately reviewed semantic minimum for every logical claim-source pair.
EXPECTED_LOCATOR_ATOMIC_FACTS: Final[dict[tuple[str, str], tuple[str, ...]]] = {
    (
        "SRC-ACE-CRESTA-06316",
        "CLM-ST1704-SUITCASE-CRESTA-06316-EXCLUDED",
    ): (
        "ACEクレスタ",
        "06316",
        "ブラックカーボン",
        "H55×W35×D25/29cm",
        "34/39L",
        "3.2kg",
        "在庫切れ",
    ),
    (
        "SRC-ACE-DIFFERENCE-05721",
        "CLM-ST1704-SUITCASE-DIFFERENCE-SPECS",
    ): (
        "05721",
        "06：ホワイト",
        "H55×W36×D24/27cm",
        "32/38L",
        "3.5kg",
        "2通りの開閉",
        "容量拡張",
        "キャスターストッパー",
        "在庫あります",
        "カートに入れる",
    ),
    (
        "SRC-ACE-DIFFERENCE-05721",
        "CLM-ST1704-SUITCASE-CONDITIONAL-CHOICES",
    ): (
        "05721",
        "06：ホワイト",
        "32/38L",
        "3.5kg",
        "容量拡張",
        "2通りの開閉",
        "キャスターストッパー",
        "在庫あります",
        "カートに入れる",
    ),
    (
        "SRC-ACE-DIFFERENCE-05721",
        "CLM-PORTFOLIO-FRONT-DIFFERENCE-05721",
    ): (
        "05721",
        "06：ホワイト",
        "H55×W36×D24/27cm",
        "32/38L",
        "3.5kg",
        "2通りの開閉",
        "容量拡張",
        "キャスターストッパー",
        "在庫あります",
        "カートに入れる",
    ),
    (
        "SRC-ACE-DIFFERENCE-05721",
        "CLM-PORTFOLIO-FRONT-CONDITIONAL-CHOICES",
    ): (
        "05721",
        "06：ホワイト",
        "H55×W36×D24/27cm",
        "32/38L",
        "3.5kg",
        "2通りの開閉",
        "容量拡張",
        "キャスターストッパー",
        "在庫あります",
        "カートに入れる",
    ),
    (
        "SRC-ACE-DIFFERENCE-05721",
        "CLM-PORTFOLIO-FRONT-MUJI32-EXCLUDED",
    ): (
        "05721",
        "06：ホワイト",
        "H55×W36×D24/27cm",
        "32/38L",
        "3.5kg",
        "2通りの開閉",
        "容量拡張",
        "キャスターストッパー",
        "在庫あります",
        "カートに入れる",
    ),
    (
        "SRC-ACE-MAXPASS4-01471",
        "CLM-ST1704-SUITCASE-MAXPASS-SPECS",
    ): (
        "H50×W40×D25cm",
        "40L",
        "3.6kg",
        "フロントポケット",
        "メイン気室へアクセス可能",
        "14.0インチ",
        "キャスターストッパー",
    ),
    (
        "SRC-ACE-MAXPASS4-01471",
        "CLM-ST1704-SUITCASE-CONDITIONAL-CHOICES",
    ): (
        "40L",
        "3.6kg",
        "フロントポケット",
        "メイン気室へアクセス可能",
    ),
    (
        "SRC-ANA-CARRY-ON-BAGGAGE",
        "CLM-ST1704-SUITCASE-CARRYON-LIMITS",
    ): (
        "3辺合計115cm以内",
        "55cm×40cm×25cm以内",
        "3辺合計100cm以内",
        "45cm×35cm×20cm以内",
        "合計10kg以内",
        "手荷物と身の回り品の総重量",
    ),
    (
        "SRC-ANKER-SOLIX-C300",
        "CLM-ST1704-POWER-C300-SPECS",
    ): ("288Wh", "定格300W", "4.1kg", "16.4×16.1×24.0cm"),
    (
        "SRC-ANKER-SOLIX-C300",
        "CLM-ST1704-POWER-CONDITIONAL-CHOICES",
    ): ("288Wh", "定格300W", "4.1kg"),
    (
        "SRC-ANKER-SOLIX-C300",
        "CLM-ST1704-ANKER-C300-SPECS",
    ): ("288Wh", "定格300W", "4.1kg", "16.4×16.1×24.0cm"),
    (
        "SRC-JACKERY-500-NEW",
        "CLM-ST1704-POWER-JACKERY-SPECS",
    ): ("512Wh", "500W", "5.7kg"),
    (
        "SRC-JACKERY-500-NEW",
        "CLM-ST1704-POWER-CONDITIONAL-CHOICES",
    ): ("512Wh", "500W", "5.7kg"),
    (
        "SRC-BLUETTI-AC70",
        "CLM-ST1704-POWER-AC70-EXCLUDED",
    ): ("お知らせ", "終売", "売り切れ"),
    (
        "SRC-ECOFLOW-DELTA3-CLASSIC",
        "CLM-ST1704-POWER-DELTA3-CLASSIC-EXCLUDED",
    ): ("売り切れ", '"available":true'),
    (
        "SRC-SIROCA-SS-M171",
        "CLM-ST1704-DISH-SS-M171-SPECS",
    ): (
        "SS-M171",
        "16点",
        "5L",
        "幅42×奥行43.5×高さ43.5cm",
        "13kg",
        "タンク式（手動給水）/分岐水栓式",
        "送風乾燥",
    ),
    (
        "SRC-SIROCA-SS-M171",
        "CLM-ST1704-DISH-CONDITIONAL-CHOICES",
    ): ("16点", "5L", "幅42×奥行43.5×高さ43.5cm", "送風乾燥"),
    (
        "SRC-THANKO-RAKUA-MINI-TK-MDW22W",
        "CLM-ST1704-DISH-RAKUA-SPECS",
    ): (
        "11〜12点",
        "3.2L",
        "幅 308× 高さ 415× 奥行 315",
        "開扉時奥行:594mm",
        "8kg",
        "下ノズル噴射式",
        "熱風乾燥",
    ),
    (
        "SRC-THANKO-RAKUA-MINI-TK-MDW22W",
        "CLM-ST1704-DISH-CONDITIONAL-CHOICES",
    ): (
        "11〜12点",
        "3.2L",
        "幅 308× 高さ 415× 奥行 315",
        "開扉時奥行:594mm",
    ),
    (
        "SRC-SIROCA-SS-MA251",
        "CLM-ST1704-DISH-SS-MA251-SPECS",
    ): (
        "SS-MA251",
        "16点",
        "6L",
        "幅42×奥行44×高さ47cm",
        "13.5kg",
        "送風",
        "オートオープン",
    ),
    (
        "SRC-SIROCA-SS-MA251",
        "CLM-ST1704-DISH-CONDITIONAL-CHOICES",
    ): ("16点", "6L", "幅42×奥行44×高さ47cm", "送風", "オートオープン"),
    (
        "SRC-ANKER-SOLIX-C800-PLUS",
        "CLM-ST1704-ANKER-C800-SPECS",
    ): ("768Wh", "1200W", "10.9kg", "37.1×20.5×25.0cm"),
    (
        "SRC-ANKER-SOLIX-C1000",
        "CLM-ST1704-ANKER-C1000-SPECS",
    ): ("1056Wh", "1500W", "12.9kg", "37.6×20.5×26.7cm"),
    (
        "SRC-ANKER-SOLIX-C1000",
        "CLM-ST1704-ANKER-C1000-GENERATION-DIFF",
    ): ("1056Wh", "1500W", "12.9kg"),
    (
        "SRC-ANKER-SOLIX-C1000-GEN2",
        "CLM-ST1704-ANKER-C1000-GEN2-SPECS",
    ): ("1024Wh", "1550W", "11.3kg", "38.4×20.8×24.4cm"),
    (
        "SRC-ANKER-SOLIX-C1000-GEN2",
        "CLM-ST1704-ANKER-C1000-FEATURE-DIFF",
    ): (
        "4000回",
        "AC×5/USB-C×3",
        "AC×6/USB-C×2",
        "SurgePad",
        "拡張バッテリー対応",
        "3,000回",
        "0.01秒",
        "0.02秒",
    ),
    (
        "SRC-ANKER-SOLIX-C1000-GEN2",
        "CLM-ST1704-ANKER-C1000-GENERATION-DIFF",
    ): ("1024Wh", "1550W", "11.3kg"),
    (
        "SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY",
        "CLM-ST1704-ROBOT-ROOMBA-MINI-F155260-EXCLUDED",
    ): ("Roomba Mini", "在庫切れ"),
    (
        "SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY",
        "CLM-PORTFOLIO-ROBOT-ROOMBA-MINI-F155260-EXCLUDED",
    ): ("Roomba Mini", "在庫切れ"),
    (
        "SRC-EUFY-AUTOEMPTY-C10-T2292",
        "CLM-ST1704-ROBOT-EUFY-C10-SPECS",
    ): (
        "T2292511",
        "32.5x32.3x7.2cm",
        "27.5x19.1x21.2cm",
        "水拭き-",
        "自動ゴミ収集システム◯",
        "在庫わずか",
    ),
    (
        "SRC-EUFY-AUTOEMPTY-C10-T2292",
        "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES",
    ): (
        "T2292511",
        "32.5x32.3x7.2cm",
        "27.5x19.1x21.2cm",
        "在庫わずか",
    ),
    (
        "SRC-EUFY-AUTOEMPTY-C10-T2292",
        "CLM-PORTFOLIO-ROBOT-EUFY-C10",
    ): (
        "T2292511",
        "32.5x32.3x7.2cm",
        "27.5x19.1x21.2cm",
        "水拭き-",
        "在庫わずか",
    ),
    (
        "SRC-EUFY-AUTOEMPTY-C10-T2292",
        "CLM-PORTFOLIO-ROBOT-CONDITIONAL-CHOICES",
    ): (
        "T2292511",
        "32.5x32.3x7.2cm",
        "27.5x19.1x21.2cm",
        "在庫わずか",
    ),
    (
        "SRC-SWITCHBOT-K11-PRO",
        "CLM-ST1704-ROBOT-K11-PRO-SPECS",
    ): (
        "248×248×92mm",
        "240×180×250mm",
        "ゴミ収集ステーション",
        "90日ごみ捨て不要",
        "市販のお掃除シート",
        "そのまま捨てる",
    ),
    (
        "SRC-SWITCHBOT-K11-PRO",
        "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES",
    ): (
        "248×248×92mm",
        "240×180×250mm",
        "90日ごみ捨て不要",
        "市販のお掃除シート",
        "そのまま捨てる",
    ),
    (
        "SRC-SWITCHBOT-K10-PRO-COMBO",
        "CLM-ST1704-ROBOT-K10-COMBO-EXCLUDED",
    ): (
        "248×248×92mm",
        "195×297×410mm",
        "お掃除シート",
        "デュアル集塵ステーション",
        "ロボット+スティックが1つのステーション",
    ),
    (
        "SRC-IROBOT-ROOMBA-PLUS-515-COMBO",
        "CLM-ST1704-ROBOT-ROOMBA-515-SPECS",
    ): (
        "30.3×29.8×8.4",
        "34.0×33.0×48.5",
        "DualClean™モップパッド",
        "自動ゴミ収集",
        "自動給水",
        "温水洗浄",
        "温風乾燥",
    ),
    (
        "SRC-IROBOT-ROOMBA-PLUS-515-COMBO",
        "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES",
    ): (
        "30.3×29.8×8.4",
        "34.0×33.0×48.5",
        "DualClean™モップパッド",
        "自動ゴミ収集",
        "自動給水",
        "温水洗浄",
        "温風乾燥",
    ),
    (
        "SRC-RAKUTEN-AFFILIATE-GUIDELINE",
        "POLICY-SOURCE-STATEMENT",
    ): ("サイズ変更", "画像の上に直接文字", "切り取って使用することは禁止"),
    (
        "SRC-CAA-STEALTH-MARKETING-QA",
        "POLICY-SOURCE-STATEMENT",
    ): ("アフィリエイト広告を利用しています", "明瞭"),
    (
        "SRC-GOOGLE-QUALIFY-OUTBOUND-LINKS",
        "POLICY-SOURCE-STATEMENT",
    ): ("advertisements or paid placements", "sponsored"),
}


_HTML_TAG = re.compile(r"<[^>]*>")


def _semantic_text(value: str) -> str:
    decoded = html.unescape(_HTML_TAG.sub(" ", value))
    normalized = unicodedata.normalize("NFKC", decoded).casefold()
    normalized = normalized.replace("〜", "~").replace("～", "~")
    normalized = normalized.replace("×", "x")
    for axis_label in ("奥行き", "奥行", "幅", "高さ"):
        normalized = normalized.replace(f"({axis_label})", "")
    return re.sub(r"\s+", "", normalized)


@pytest.fixture
def private_root() -> Iterator[Path]:
    """Use a native filesystem because mounted Windows paths ignore POSIX modes."""

    with tempfile.TemporaryDirectory(
        prefix="raos-st1704-source-capture-", dir="/var/tmp"
    ) as directory:
        yield Path(directory)


class _Response:
    def __init__(
        self,
        body: bytes = HTML_BODY,
        *,
        status: int = 200,
        headers: list[tuple[str, str]] | None = None,
    ) -> None:
        self.status = status
        self._body = body
        self._offset = 0
        self._headers = (
            [("Content-Type", "text/html"), ("Content-Length", str(len(body)))]
            if headers is None
            else headers
        )

    def getheader(self, name: str, default: str | None = None) -> str | None:
        matches = [
            value for key, value in self._headers if key.casefold() == name.casefold()
        ]
        return matches[0] if len(matches) == 1 else default

    def getheaders(self) -> list[tuple[str, str]]:
        return list(self._headers)

    def read(self, amount: int | None = None) -> bytes:
        if amount is None:
            amount = len(self._body) - self._offset
        start = self._offset
        self._offset = min(len(self._body), start + amount)
        return self._body[start : self._offset]


class _Connection:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.connected = False
        self.closed = False
        self.read_timeout: int | None = None
        self.requests: list[tuple[str, str, dict[str, str]]] = []

    def connect(self) -> None:
        self.connected = True

    def set_read_timeout(self, seconds: int) -> None:
        self.read_timeout = seconds

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        self.requests.append((method, path, dict(headers)))

    def getresponse(self) -> _Response:
        return self.response

    def close(self) -> None:
        self.closed = True


class _Factory:
    def __init__(self, response: _Response) -> None:
        self.connection = _Connection(response)
        self.opens: list[dict[str, object]] = []

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> _Connection:
        self.opens.append(
            {
                "connect_timeout_seconds": connect_timeout_seconds,
                "host": host,
                "port": port,
                "tls_context": tls_context,
            }
        )
        return self.connection


class _PeerSocket:
    def __init__(self, address: tuple[str, int] | tuple[str, int, int, int]) -> None:
        self.address = address
        self.read_timeout: int | None = None

    def getpeername(self) -> tuple[str, int] | tuple[str, int, int, int]:
        return self.address

    def settimeout(self, seconds: int) -> None:
        self.read_timeout = seconds


class _SystemHttpsConnection:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        timeout: int,
        context: ssl.SSLContext,
        response: _Response,
        failing_ips: frozenset[str],
        attempts: list[str],
    ) -> None:
        self._create_connection: object | None = None
        self._tunnel_host: str | None = None
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.response = response
        self.failing_ips = failing_ips
        self.attempts = attempts
        self.sock: _PeerSocket | None = None
        self.closed = False
        self.requests: list[tuple[str, str, dict[str, str]]] = []

    def connect(self) -> None:
        connector = cast(capture_module._PinnedConnector, self._create_connection)
        candidate = connector.candidate
        candidate_ip = str(candidate.ip)
        self.attempts.append(candidate_ip)
        if candidate_ip in self.failing_ips:
            raise ConnectionRefusedError(candidate_ip)
        self.sock = _PeerSocket(candidate.socket_address)

    def request(
        self,
        method: str,
        path: str,
        body: object,
        headers: dict[str, str],
    ) -> None:
        assert body is None
        self.requests.append((method, path, dict(headers)))

    def getresponse(self) -> _Response:
        return self.response

    def close(self) -> None:
        self.closed = True


def _system_connection_doubles(
    monkeypatch: pytest.MonkeyPatch,
    *,
    failing_ips: frozenset[str],
) -> tuple[list[_SystemHttpsConnection], list[str]]:
    connections: list[_SystemHttpsConnection] = []
    attempts: list[str] = []

    def open_connection(
        *, host: str, port: int, timeout: int, context: ssl.SSLContext
    ) -> _SystemHttpsConnection:
        connection = _SystemHttpsConnection(
            host=host,
            port=port,
            timeout=timeout,
            context=context,
            response=_Response(),
            failing_ips=failing_ips,
            attempts=attempts,
        )
        connections.append(connection)
        return connection

    monkeypatch.setattr(capture_module.http.client, "HTTPSConnection", open_connection)
    return connections, attempts


def _public_resolved_address(value: str) -> capture_module._ResolvedAddress:
    ip = capture_module._public_ip(value, family=capture_module.socket.AF_INET)
    return capture_module._ResolvedAddress(
        family=capture_module.socket.AF_INET,
        socket_type=capture_module.socket.SOCK_STREAM,
        protocol=capture_module.socket.IPPROTO_TCP,
        socket_address=(str(ip), 443),
        ip=ip,
    )


def _target(
    *,
    locator_status: str = "LOCATORS_PENDING",
    fragment: str = UNIQUE_FRAGMENT,
    charset: str | None = None,
    observed_on: date = date(2026, 8, 23),
    media_type: str = "text/html",
    locator_mode: str = "RAW_BODY_EXACTLY_ONCE",
    expected_body_sha256: str | None = None,
    reviewed_page_number: int | None = None,
    host: str = "official.example",
) -> capture_module.SourceCaptureTarget:
    locators: tuple[capture_module.SourceLocator, ...]
    if locator_status == "READY":
        locators = (
            capture_module.SourceLocator(
                "CLM-ST1704-TEST-OFFICIAL-SPECS",
                "a" * 64,
                (fragment,),
                reviewed_page_number,
            ),
        )
    else:
        locators = ()
    return capture_module.SourceCaptureTarget(
        source_ref="SRC-TEST-OFFICIAL",
        url=f"https://{host}/specifications",
        host=host,
        path="/specifications",
        observed_on=observed_on,
        charset=charset,
        locator_status=locator_status,
        locators=locators,
        media_type=media_type,
        locator_mode=locator_mode,
        expected_body_sha256=expected_body_sha256,
    )


def _fetched(
    *,
    locator_status: str,
    body: bytes = HTML_BODY,
    fragment: str = UNIQUE_FRAGMENT,
) -> capture_module.FetchedSource:
    return capture_module.FetchedSource(
        target=_target(locator_status=locator_status, fragment=fragment),
        retrieved_at="2026-08-23T12:34:56Z",
        content_type="text/html",
        body=body,
    )


def _fetch(
    response: _Response,
    *,
    target: capture_module.SourceCaptureTarget | None = None,
    clock: datetime = FIXED_NOW,
) -> tuple[capture_module.FetchedSource, _Factory]:
    factory = _Factory(response)
    result = capture_module._fetch_source(
        _target() if target is None else target,
        connection_factory=factory,
        clock=lambda: clock,
        environment={},
    )
    return result, factory


def _failure_code(error: pytest.ExceptionInfo[Exception]) -> object:
    return cast(capture_module.OfficialSourceCaptureFailure, error.value).code


def test_tracked_plan_exactly_matches_registry_and_policy_inventory() -> None:
    plan = capture_module.load_source_capture_plan(REPOSITORY_ROOT)
    registry = json.loads(
        (SOURCES_ROOT / "source-registry.v1.json").read_text(encoding="utf-8")
    )
    capture_namespace = runpy.run_path(str(CAPTURE_SCRIPT))
    expected_urls = {
        value["source_ref"]: value["url"]
        for collection in (registry["sources"], registry["policy_sources"])
        for value in collection
    }
    locator_contract = json.loads(
        (SOURCES_ROOT / "source-locator-contract.v1.json").read_text(encoding="utf-8")
    )
    expected_locator_count = sum(
        len(source["locators"]) for source in locator_contract["sources"]
    )

    assert len(plan.targets) == len(expected_urls)
    pending = {
        target.source_ref
        for target in plan.targets
        if target.locator_status == "LOCATORS_PENDING"
    }
    assert pending == set()
    assert all(target.locator_status == "READY" for target in plan.targets)
    assert (
        sum(len(target.locators) for target in plan.targets) == expected_locator_count
    )
    assert set(expected_urls) == set(capture_namespace["SOURCE_REFS"])
    assert sum(target.source_ref not in POLICY_REFS for target in plan.targets) == len(
        registry["sources"]
    )
    assert sum(target.source_ref in POLICY_REFS for target in plan.targets) == len(
        registry["policy_sources"]
    )
    assert {target.source_ref: target.url for target in plan.targets} == expected_urls
    assert not REMOVED_RAKUTEN_ACE_REFS & set(expected_urls)
    assert all(not value.startswith("SRC-RAKUTEN-ACE-") for value in expected_urls)


def test_tracked_contract_uses_grouped_string_fragments_only() -> None:
    contract = json.loads(
        (SOURCES_ROOT / "source-locator-contract.v1.json").read_text(encoding="utf-8")
    )
    locators = [
        locator for source in contract["sources"] for locator in source["locators"]
    ]

    assert len(locators) == sum(
        len(source["locators"]) for source in contract["sources"]
    )
    assert all(
        set(locator)
        in (
            {"claim_id", "exact_utf8_fragments"},
            {"claim_id", "exact_utf8_fragments", "reviewed_page_number"},
        )
        for locator in locators
    )
    assert all(
        type(locator["exact_utf8_fragments"]) is list
        and locator["exact_utf8_fragments"]
        and all(type(fragment) is str for fragment in locator["exact_utf8_fragments"])
        for locator in locators
    )
    assert any(len(locator["exact_utf8_fragments"]) > 1 for locator in locators)
    assert sum(len(locator["exact_utf8_fragments"]) for locator in locators) > 98
    assert all(
        1 <= len(fragment.encode("utf-8")) <= 2_000
        for locator in locators
        for fragment in locator["exact_utf8_fragments"]
    )


def test_reviewed_legacy_and_exclusion_locators_cover_atomic_facts() -> None:
    plan = capture_module.load_source_capture_plan(REPOSITORY_ROOT)
    observed: dict[tuple[str, str], tuple[str, ...]] = {}
    missing: dict[tuple[str, str], tuple[str, ...]] = {}

    for target in plan.targets:
        for locator in target.locators:
            key = (target.source_ref, locator.claim_id)
            material = _semantic_text("\n".join(locator.exact_utf8_fragments))
            expected = EXPECTED_LOCATOR_ATOMIC_FACTS.get(key)
            if expected is None:
                continue
            absent = tuple(
                token for token in expected if _semantic_text(token) not in material
            )
            observed[key] = expected
            if absent:
                missing[key] = absent

    assert set(observed) == set(EXPECTED_LOCATOR_ATOMIC_FACTS)
    assert len(observed) == len(EXPECTED_LOCATOR_ATOMIC_FACTS)
    assert not missing, "claim-source locator semantic gaps: " + "; ".join(
        f"{source_ref}/{claim_id}: {tokens!r}"
        for (source_ref, claim_id), tokens in sorted(missing.items())
    )

    # The exact F155260 SKU is encoded in the official page's hidden item
    # field rather than reader-visible text.  Keep that structural identity
    # bound even though the semantic-text assertions above intentionally
    # discard HTML attributes.
    f155_target = plan.target("SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY")
    f155_locators = {
        locator.claim_id: "\n".join(locator.exact_utf8_fragments)
        for locator in f155_target.locators
    }
    for claim_id in (
        "CLM-ST1704-ROBOT-ROOMBA-MINI-F155260-EXCLUDED",
        "CLM-PORTFOLIO-ROBOT-ROOMBA-MINI-F155260-EXCLUDED",
    ):
        assert '<input type="hidden" name="item_cd" value="F155260" />' in (
            f155_locators[claim_id]
        )

    difference_target = plan.target("SRC-ACE-DIFFERENCE-05721")
    for locator in difference_target.locators:
        material = "\n".join(locator.exact_utf8_fragments)
        assert '<input type="hidden" name="goods" value="05721-06">' in material
        assert '<dd id="spec_stock_msg">在庫あります</dd>' in material
        assert 'value="カートに入れる">カートに入れる</button>' in material


def test_new_primary_source_locators_cover_reviewed_atomic_facts() -> None:
    plan = capture_module.load_source_capture_plan(REPOSITORY_ROOT)
    observed: set[str] = set()
    for source_ref, expected_tokens in NEW_SOURCE_REQUIRED_LOCATOR_TOKENS.items():
        target = plan.target(source_ref)
        material = _semantic_text(
            "\n".join(
                fragment
                for locator in target.locators
                for fragment in locator.exact_utf8_fragments
            )
        )
        assert all(_semantic_text(token) in material for token in expected_tokens), (
            source_ref
        )
        observed.add(source_ref)

    assert observed == set(NEW_SOURCE_REQUIRED_LOCATOR_TOKENS)


def test_each_of_ten_article_plans_has_exact_sources_plus_fixed_policy() -> None:
    plan = capture_module.load_source_capture_plan(REPOSITORY_ROOT)
    namespace = runpy.run_path(str(CAPTURE_SCRIPT))
    article_ids = cast(tuple[str, ...], namespace["ARTICLE_IDS"])

    assert len(article_ids) == 10
    assert {article_id for article_id, _refs in plan.article_sources} == set(
        article_ids
    )
    expected_product_source_counts = {
        "st1703-first-suitcase-comparison": 7,
        "st1704-portable-power-station-guide": 29,
        "st1704-anker-solix-c300-c800-c1000-differences": 13,
        "st1704-countertop-dishwasher-for-small-households": 15,
        "st1704-compact-robot-vacuum-shortlist": 15,
        "carry-on-suitcase-under-100-seats": 10,
        "lightweight-carry-on-suitcase-under-3kg": 14,
        "front-open-carry-on-suitcase-with-stopper": 10,
        "roomba-mini-vs-switchbot-k11-pro": 10,
        "solota-vs-rakua-mini-plus": 8,
    }
    for article_id in article_ids:
        selected = plan.for_article(article_id)
        selected_refs = [target.source_ref for target in selected]
        assert len(selected_refs) == expected_product_source_counts[article_id] + 3
        assert len(selected_refs) == len(set(selected_refs))
        assert POLICY_REFS < set(selected_refs)
        assert (
            sum(source_ref not in POLICY_REFS for source_ref in selected_refs)
            == expected_product_source_counts[article_id]
        )


def test_plan_refuses_unknown_source_and_article_identifiers() -> None:
    plan = capture_module.load_source_capture_plan(REPOSITORY_ROOT)

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as source_error:
        plan.target("SRC-NOT-TRACKED")
    assert _failure_code(source_error) is (
        capture_module.OfficialSourceCaptureFailureCode.SOURCE_NOT_ALLOWLISTED
    )
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as article_error:
        plan.for_article("st1704-not-allowlisted")
    assert _failure_code(article_error) is (
        capture_module.OfficialSourceCaptureFailureCode.ARTICLE_NOT_ALLOWLISTED
    )


def test_registry_change_without_locator_contract_rebind_is_rejected(
    private_root: Path,
) -> None:
    destination = private_root / capture_module.SOURCE_REGISTRY_RELATIVE_PATH.parent
    destination.mkdir(parents=True)
    registry = json.loads(
        (SOURCES_ROOT / "source-registry.v1.json").read_text(encoding="utf-8")
    )
    registry["sources"][0]["url"] = "https://official.example/changed"
    (destination / "source-registry.v1.json").write_text(
        json.dumps(registry, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (destination / "source-locator-contract.v1.json").write_bytes(
        (SOURCES_ROOT / "source-locator-contract.v1.json").read_bytes()
    )

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module.load_source_capture_plan(private_root)
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.CONTRACT_INVALID
    )


def test_rebound_registry_and_locator_cannot_substitute_an_unreviewed_url(
    private_root: Path,
) -> None:
    destination = private_root / capture_module.SOURCE_REGISTRY_RELATIVE_PATH.parent
    destination.mkdir(parents=True)
    registry = json.loads(
        (SOURCES_ROOT / "source-registry.v1.json").read_text(encoding="utf-8")
    )
    contract = json.loads(
        (SOURCES_ROOT / "source-locator-contract.v1.json").read_text(encoding="utf-8")
    )
    registry["sources"][0]["url"] = (
        "https://www.ankerjapan.com/products/unreviewed-substitute"
    )
    contract["source_registry_sha256"] = capture_module.canonical_sha256(registry)
    (destination / "source-registry.v1.json").write_text(
        json.dumps(registry, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (destination / "source-locator-contract.v1.json").write_text(
        json.dumps(contract, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module.load_source_capture_plan(private_root)
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.CONTRACT_INVALID
    )


def _write_source_contract_fixture(
    private_root: Path,
    contract: dict[str, object],
) -> None:
    destination = private_root / capture_module.SOURCE_REGISTRY_RELATIVE_PATH.parent
    destination.mkdir(parents=True)
    (destination / "source-registry.v1.json").write_bytes(
        (SOURCES_ROOT / "source-registry.v1.json").read_bytes()
    )
    (destination / "source-locator-contract.v1.json").write_text(
        json.dumps(contract, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def test_contract_allows_minimal_exact_fragment_reuse_across_claims(
    private_root: Path,
) -> None:
    contract = json.loads(
        (SOURCES_ROOT / "source-locator-contract.v1.json").read_text(encoding="utf-8")
    )
    source = next(value for value in contract["sources"] if len(value["locators"]) > 1)
    first, second = source["locators"][:2]
    shared = first["exact_utf8_fragments"][0]
    second["exact_utf8_fragments"] = [shared]
    _write_source_contract_fixture(private_root, contract)

    plan = capture_module.load_source_capture_plan(private_root)
    target = plan.target(source["source_ref"])

    assert target.locators[0].exact_utf8_fragments[0] == shared
    assert target.locators[1].exact_utf8_fragments == (shared,)


def test_contract_rejects_duplicate_fragment_within_one_claim(
    private_root: Path,
) -> None:
    contract = json.loads(
        (SOURCES_ROOT / "source-locator-contract.v1.json").read_text(encoding="utf-8")
    )
    locator = contract["sources"][0]["locators"][0]
    locator["exact_utf8_fragments"].append(locator["exact_utf8_fragments"][0])
    _write_source_contract_fixture(private_root, contract)

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module.load_source_capture_plan(private_root)
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.CONTRACT_INVALID
    )


def test_exact_get_uses_fixed_tls_timeouts_and_no_credentials() -> None:
    fetched, factory = _fetch(_Response())

    assert fetched.body == HTML_BODY
    assert fetched.content_type == "text/html"
    assert fetched.retrieved_at == "2026-08-23T12:34:56Z"
    assert fetched.target.url == "https://official.example/specifications"
    assert len(factory.opens) == 1
    opened = factory.opens[0]
    assert opened["host"] == "official.example"
    assert opened["port"] == 443
    assert opened["connect_timeout_seconds"] == (capture_module.CONNECT_TIMEOUT_SECONDS)
    context = cast(ssl.SSLContext, opened["tls_context"])
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    connection = factory.connection
    assert connection.connected
    assert connection.closed
    assert connection.read_timeout == capture_module.READ_TIMEOUT_SECONDS
    assert connection.requests == [
        (
            "GET",
            "/specifications",
            {
                "Accept": capture_module.CAPTURE_ACCEPT,
                "Accept-Encoding": "identity",
                "Connection": "close",
                "Host": "official.example",
                "User-Agent": capture_module.CAPTURE_USER_AGENT,
            },
        )
    ]
    headers = connection.requests[0][2]
    assert "Authorization" not in headers
    assert "Cookie" not in headers


def test_machine_readable_product_endpoint_accepts_verified_json_javascript() -> None:
    body = b'{"id":123,"title":"INV50","weight_kg":3.3}'
    target = _target(media_type="text/javascript", charset="utf-8")
    fetched, factory = _fetch(
        _Response(
            body,
            headers=[
                ("Content-Type", "text/javascript; charset=utf-8"),
                ("Content-Length", str(len(body))),
            ],
        ),
        target=target,
    )

    assert fetched.content_type == "text/javascript"
    assert fetched.body == body
    assert factory.connection.requests[0][2]["Accept"] == (
        "application/json, text/javascript"
    )


def test_pdf_capture_requires_pinned_body_but_uses_reviewed_page_text() -> None:
    body = b"%PDF-1.7\nreviewed binary fixture\n%%EOF\n"
    target = _target(
        locator_status="READY",
        fragment="134679\nSpinner 55 EXP\n40 x 55 x 20/23\n36/42 l\n2.1 kg",
        media_type="application/pdf",
        locator_mode="PINNED_PDF_BODY_AND_REVIEWED_PAGE_TEXT",
        expected_body_sha256=bytes_sha256(body),
        reviewed_page_number=10,
    )
    fetched, factory = _fetch(
        _Response(
            body,
            headers=[
                ("Content-Type", "application/pdf"),
                ("Content-Length", str(len(body))),
            ],
        ),
        target=target,
    )
    evidence = capture_module._evidence(fetched)

    assert fetched.content_type == "application/pdf"
    assert evidence.body_sha256 == bytes_sha256(body)
    assert evidence.locators[0][2][0][0].startswith("134679")
    assert factory.connection.requests[0][2]["Accept"] == "application/pdf"


def test_pdf_capture_rejects_body_drift_before_reviewed_locator_binding() -> None:
    expected = b"%PDF-1.7\nexpected\n%%EOF\n"
    changed = b"%PDF-1.7\nchanged\n%%EOF\n"
    target = _target(
        locator_status="READY",
        fragment="reviewed page text",
        media_type="application/pdf",
        locator_mode="PINNED_PDF_BODY_AND_REVIEWED_PAGE_TEXT",
        expected_body_sha256=bytes_sha256(expected),
        reviewed_page_number=10,
    )
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        _fetch(
            _Response(
                changed,
                headers=[
                    ("Content-Type", "application/pdf"),
                    ("Content-Length", str(len(changed))),
                ],
            ),
            target=target,
        )
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.LOCATOR_MISMATCH
    )


def test_american_tourister_uses_official_intermediate_with_system_verification() -> (
    None
):
    der = ssl.PEM_cert_to_DER_cert(capture_module._AMERICAN_TOURISTER_INTERMEDIATE_PEM)
    assert bytes_sha256(der) == (
        capture_module._AMERICAN_TOURISTER_INTERMEDIATE_SHA256_FINGERPRINT
    )
    assert capture_module._AMERICAN_TOURISTER_INTERMEDIATE_SOURCE == (
        "https://secure.globalsign.com/cacert/gsgccr3dvtlsca2020.crt"
    )

    fetched, factory = _fetch(
        _Response(), target=_target(host="www.americantourister.jp")
    )
    context = cast(ssl.SSLContext, factory.opens[0]["tls_context"])
    assert fetched.target.host == "www.americantourister.jp"
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_antibot_or_other_non_200_response_fails_closed_without_capture() -> None:
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        _fetch(_Response(status=403))
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.RESPONSE_INVALID
    )


def test_system_transport_tries_later_verified_endpoint_before_one_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _public_resolved_address("1.1.1.1")
    second = _public_resolved_address("8.8.8.8")
    resolved_hosts: list[str] = []

    def resolve(host: str) -> tuple[capture_module._ResolvedAddress, ...]:
        resolved_hosts.append(host)
        return (first, second)

    monkeypatch.setattr(capture_module, "_resolve_public_addresses", resolve)
    connections, attempts = _system_connection_doubles(
        monkeypatch, failing_ips=frozenset({str(first.ip)})
    )

    fetched = capture_module._fetch_source(
        _target(),
        connection_factory=(
            capture_module._SystemOfficialSourceHttpsConnectionFactory()
        ),
        clock=lambda: FIXED_NOW,
        environment={},
    )

    assert fetched.body == HTML_BODY
    assert resolved_hosts == ["official.example"]
    assert attempts == [str(first.ip), str(second.ip)]
    assert len(connections) == 2
    assert all(connection.host == "official.example" for connection in connections)
    assert all(connection.port == 443 for connection in connections)
    assert all(
        connection.timeout == capture_module.CONNECT_TIMEOUT_SECONDS
        for connection in connections
    )
    assert all(connection.context.check_hostname for connection in connections)
    assert all(
        connection.context.verify_mode == ssl.CERT_REQUIRED
        for connection in connections
    )
    assert connections[0].requests == []
    assert connections[1].requests == [
        (
            "GET",
            "/specifications",
            {
                "Accept": capture_module.CAPTURE_ACCEPT,
                "Accept-Encoding": "identity",
                "Connection": "close",
                "Host": "official.example",
                "User-Agent": capture_module.CAPTURE_USER_AGENT,
            },
        )
    ]
    assert sum(len(connection.requests) for connection in connections) == 1
    assert connections[0].closed and connections[1].closed
    assert connections[1].sock is not None
    assert connections[1].sock.read_timeout == capture_module.READ_TIMEOUT_SECONDS


def test_system_transport_reports_failure_only_after_all_endpoints_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _public_resolved_address("1.1.1.1")
    second = _public_resolved_address("8.8.8.8")
    monkeypatch.setattr(
        capture_module,
        "_resolve_public_addresses",
        lambda _host: (first, second),
    )
    connections, attempts = _system_connection_doubles(
        monkeypatch,
        failing_ips=frozenset({str(first.ip), str(second.ip)}),
    )

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module._fetch_source(
            _target(),
            connection_factory=(
                capture_module._SystemOfficialSourceHttpsConnectionFactory()
            ),
            clock=lambda: FIXED_NOW,
            environment={},
        )

    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.CONNECTION_FAILED
    )
    assert attempts == [str(first.ip), str(second.ip)]
    assert len(connections) == 2
    assert all(connection.closed for connection in connections)
    assert all(connection.requests == [] for connection in connections)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "192.168.1.1",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_dns_rejects_non_public_addresses(address: str) -> None:
    family = (
        capture_module.socket.AF_INET6
        if ":" in address
        else capture_module.socket.AF_INET
    )
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module._public_ip(address, family=family)
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.DNS_ADDRESS_REJECTED
    )


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            _Response(status=301, headers=[("Content-Type", "text/html")]),
            capture_module.OfficialSourceCaptureFailureCode.RESPONSE_INVALID,
        ),
        (
            _Response(
                headers=[
                    ("Content-Type", "text/html"),
                    ("Location", "https://official.example/other"),
                ]
            ),
            capture_module.OfficialSourceCaptureFailureCode.RESPONSE_INVALID,
        ),
        (
            _Response(
                headers=[
                    ("Content-Type", "text/html"),
                    ("Content-Encoding", "gzip"),
                ]
            ),
            capture_module.OfficialSourceCaptureFailureCode.RESPONSE_INVALID,
        ),
        (
            _Response(
                headers=[
                    ("Content-Type", "text/html"),
                    ("content-type", "text/html"),
                ]
            ),
            capture_module.OfficialSourceCaptureFailureCode.RESPONSE_INVALID,
        ),
        (
            _Response(headers=[("Content-Type", "application/json")]),
            capture_module.OfficialSourceCaptureFailureCode.MIME_INVALID,
        ),
        (
            _Response(headers=[]),
            capture_module.OfficialSourceCaptureFailureCode.MIME_INVALID,
        ),
        (
            _Response(headers=[("Content-Type", "text/html; charset=utf-8")]),
            capture_module.OfficialSourceCaptureFailureCode.MIME_INVALID,
        ),
        (
            _Response(
                headers=[("Content-Type", "text/html"), ("Content-Length", "01")]
            ),
            capture_module.OfficialSourceCaptureFailureCode.RESPONSE_INVALID,
        ),
        (
            _Response(
                headers=[
                    ("Content-Type", "text/html"),
                    ("Content-Length", str(len(HTML_BODY) + 1)),
                ]
            ),
            capture_module.OfficialSourceCaptureFailureCode.RESPONSE_INVALID,
        ),
        (
            _Response(
                headers=[
                    ("Content-Type", "text/html"),
                    ("Transfer-Encoding", "gzip"),
                ]
            ),
            capture_module.OfficialSourceCaptureFailureCode.RESPONSE_INVALID,
        ),
        (
            _Response(b"", headers=[("Content-Type", "text/html")]),
            capture_module.OfficialSourceCaptureFailureCode.HTML_INVALID,
        ),
        (
            _Response(
                b"<html><body>truncated", headers=[("Content-Type", "text/html")]
            ),
            capture_module.OfficialSourceCaptureFailureCode.HTML_INVALID,
        ),
        (
            _Response(
                b"<!doctype html><html><body>\xff</body></html>",
                headers=[("Content-Type", "text/html")],
            ),
            capture_module.OfficialSourceCaptureFailureCode.HTML_INVALID,
        ),
    ],
)
def test_http_response_variants_fail_closed(
    response: _Response,
    expected: capture_module.OfficialSourceCaptureFailureCode,
) -> None:
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        _fetch(response)
    assert _failure_code(failure) is expected


def test_declared_oversized_body_is_rejected_before_read() -> None:
    response = _Response(
        headers=[
            ("Content-Type", "text/html"),
            ("Content-Length", str(capture_module.MAX_SOURCE_BODY_BYTES + 1)),
        ]
    )

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        _fetch(response)
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.BODY_TOO_LARGE
    )
    assert response._offset == 0


def test_exact_utf8_and_euc_jp_encoding_contracts() -> None:
    utf8_target = _target(charset="utf-8")
    utf8, _factory = _fetch(
        _Response(headers=[("Content-Type", "text/html; charset=UTF_8")]),
        target=utf8_target,
    )
    assert utf8.body == HTML_BODY

    euc_body = (
        "<!doctype html><html><body><p>公式仕様です。</p></body></html>"
    ).encode("euc_jp")
    euc, _factory = _fetch(
        _Response(
            euc_body,
            headers=[("Content-Type", "text/html; charset=EUC_JP")],
        ),
        target=_target(charset="euc-jp"),
    )
    assert euc.body == euc_body


@pytest.mark.parametrize(
    "environment",
    [
        {"HTTPS_PROXY": "https://proxy.invalid"},
        {"https_proxy": ""},
        {"SSL_CERT_FILE": "/tmp/ca.pem"},
        {"SSLKEYLOGFILE": "/tmp/tls.keys"},
        {"NO_PROXY": "official.example"},
    ],
)
def test_proxy_and_ca_override_environment_is_rejected(
    environment: dict[str, str],
) -> None:
    factory = _Factory(_Response())
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module._fetch_source(
            _target(),
            connection_factory=factory,
            clock=lambda: FIXED_NOW,
            environment=environment,
        )
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.NETWORK_ENVIRONMENT_UNSAFE
    )
    assert factory.opens == []


@pytest.mark.parametrize(
    ("clock", "expected"),
    [
        (
            datetime(2026, 8, 22, tzinfo=timezone.utc),
            capture_module.OfficialSourceCaptureFailureCode.CONTRACT_INVALID,
        ),
        (
            datetime(2026, 8, 23),
            capture_module.OfficialSourceCaptureFailureCode.INVALID_ARGUMENT,
        ),
        (
            datetime(2026, 8, 23, tzinfo=timezone(timedelta(hours=9))),
            capture_module.OfficialSourceCaptureFailureCode.INVALID_ARGUMENT,
        ),
    ],
)
def test_capture_clock_must_be_truthful_utc_and_not_precede_registry_baseline(
    clock: datetime, expected: capture_module.OfficialSourceCaptureFailureCode
) -> None:
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        _fetch(_Response(), clock=clock)
    assert _failure_code(failure) is expected


def test_registry_observed_date_is_not_an_artificial_capture_expiry() -> None:
    later = datetime(2036, 8, 23, 1, 2, 3, tzinfo=timezone.utc)
    fetched, _factory = _fetch(_Response(), clock=later)
    assert fetched.retrieved_at == "2036-08-23T01:02:03Z"


@pytest.mark.parametrize(
    "body",
    [
        b"<!doctype html><html><body>no matching fact</body></html>",
        (
            "<!doctype html><html><body>"
            f"<p>{UNIQUE_FRAGMENT}</p><p>{UNIQUE_FRAGMENT}</p>"
            "</body></html>"
        ).encode(),
    ],
)
def test_final_capture_rejects_zero_or_duplicate_locator_occurrences(
    private_root: Path, body: bytes
) -> None:
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module._persist_capture(
            private_root,
            _fetched(locator_status="READY", body=body),
        )
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.LOCATOR_MISMATCH
    )
    metadata = private_root / source_evidence_relative_path("SRC-TEST-OFFICIAL")
    assert not metadata.exists()


def test_pending_capture_is_private_and_never_reader_accepted_as_final(
    private_root: Path,
) -> None:
    fetched = _fetched(locator_status="LOCATORS_PENDING")
    first = capture_module._persist_capture(private_root, fetched)
    sources = private_root / ".secrets" / OWNER_DIRECTORY / SOURCE_DIRECTORY
    pending_body = sources / "SRC-TEST-OFFICIAL.capture.body"
    pending_metadata = sources / "SRC-TEST-OFFICIAL.capture.v1.json"

    assert first.status == "BODY_CAPTURED_LOCATORS_PENDING"
    assert first.retrieved_at == "2026-08-23T12:34:56Z"
    assert first.body_sha256 == bytes_sha256(HTML_BODY)
    assert pending_body.read_bytes() == HTML_BODY
    assert (
        json.loads(pending_metadata.read_text(encoding="utf-8"))["locator_status"]
        == "LOCATORS_PENDING"
    )
    assert not (sources / "SRC-TEST-OFFICIAL.body").exists()
    assert not (sources / "SRC-TEST-OFFICIAL.v1.json").exists()
    with pytest.raises(EditorialPilotFailure) as not_ready:
        read_official_source_capture_evidence(
            private_root, source_ref="SRC-TEST-OFFICIAL"
        )
    assert not_ready.value.code is EditorialPilotFailureCode.RESOURCE_NOT_READY

    for directory in (
        private_root / ".secrets",
        private_root / ".secrets" / OWNER_DIRECTORY,
        sources,
    ):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for path in (
        pending_body,
        pending_metadata,
        sources / capture_module.CAPTURE_LOCK_FILE,
    ):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_final_capture_is_idempotent_and_accepted_by_existing_reader(
    private_root: Path,
) -> None:
    fetched = _fetched(locator_status="READY")
    first = capture_module._persist_capture(private_root, fetched)
    body_path = private_root / source_body_relative_path("SRC-TEST-OFFICIAL")
    metadata_path = private_root / source_evidence_relative_path("SRC-TEST-OFFICIAL")
    first_inodes = (body_path.stat().st_ino, metadata_path.stat().st_ino)

    second = capture_module._persist_capture(private_root, fetched)
    loaded = read_official_source_capture_evidence(
        private_root, source_ref="SRC-TEST-OFFICIAL"
    )

    assert first == second
    assert first.status == "CAPTURED_WITH_VERIFIED_LOCATORS"
    assert first_inodes == (body_path.stat().st_ino, metadata_path.stat().st_ino)
    assert loaded.source_ref == "SRC-TEST-OFFICIAL"
    assert loaded.final_url == "https://official.example/specifications"
    assert loaded.retrieved_at == "2026-08-23T12:34:56Z"
    assert loaded.body_sha256 == bytes_sha256(HTML_BODY)
    assert loaded.locators[0][0] == "CLM-ST1704-TEST-OFFICIAL-SPECS"
    assert loaded.locators[0][2][0][0] == UNIQUE_FRAGMENT
    assert body_path.read_bytes() == HTML_BODY
    assert stat.S_IMODE(body_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(metadata_path.stat().st_mode) == 0o600


def test_grouped_locator_evidence_round_trips_as_fragment_records(
    private_root: Path,
) -> None:
    target = _target(locator_status="LOCATORS_PENDING")
    grouped_target = capture_module.SourceCaptureTarget(
        source_ref=target.source_ref,
        url=target.url,
        host=target.host,
        path=target.path,
        observed_on=target.observed_on,
        charset=target.charset,
        locator_status="READY",
        locators=(
            capture_module.SourceLocator(
                "CLM-ST1704-TEST-OFFICIAL-SPECS",
                "a" * 64,
                (UNIQUE_FRAGMENT, SECOND_UNIQUE_FRAGMENT),
            ),
        ),
    )
    body = (
        "<!doctype html><html><body>"
        f"<p>{UNIQUE_FRAGMENT}</p><p>{SECOND_UNIQUE_FRAGMENT}</p>"
        "</body></html>"
    ).encode()
    capture_module._persist_capture(
        private_root,
        capture_module.FetchedSource(
            target=grouped_target,
            retrieved_at="2026-08-23T12:34:56Z",
            content_type="text/html",
            body=body,
        ),
    )
    metadata_path = private_root / source_evidence_relative_path("SRC-TEST-OFFICIAL")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    fragment_records = metadata["locators"][0]["exact_utf8_fragments"]
    loaded = read_official_source_capture_evidence(
        private_root, source_ref="SRC-TEST-OFFICIAL"
    )

    assert [record["exact_utf8_fragment"] for record in fragment_records] == [
        UNIQUE_FRAGMENT,
        SECOND_UNIQUE_FRAGMENT,
    ]
    assert all(
        set(record) == {"exact_utf8_fragment", "fragment_sha256"}
        for record in fragment_records
    )
    assert loaded.locators[0][2] == (
        (UNIQUE_FRAGMENT, bytes_sha256(UNIQUE_FRAGMENT.encode())),
        (SECOND_UNIQUE_FRAGMENT, bytes_sha256(SECOND_UNIQUE_FRAGMENT.encode())),
    )


def test_one_body_occurrence_can_support_two_distinct_claims(
    private_root: Path,
) -> None:
    target = _target(locator_status="LOCATORS_PENDING")
    shared_target = capture_module.SourceCaptureTarget(
        source_ref=target.source_ref,
        url=target.url,
        host=target.host,
        path=target.path,
        observed_on=target.observed_on,
        charset=target.charset,
        locator_status="READY",
        locators=(
            capture_module.SourceLocator(
                "CLM-ST1704-TEST-OFFICIAL-SPECS",
                "a" * 64,
                (UNIQUE_FRAGMENT,),
            ),
            capture_module.SourceLocator(
                "CLM-ST1704-TEST-CONDITIONAL-CHOICES",
                "b" * 64,
                (UNIQUE_FRAGMENT,),
            ),
        ),
    )

    result = capture_module._persist_capture(
        private_root,
        capture_module.FetchedSource(
            target=shared_target,
            retrieved_at="2026-08-23T12:34:56Z",
            content_type="text/html",
            body=HTML_BODY,
        ),
    )
    loaded = read_official_source_capture_evidence(
        private_root, source_ref="SRC-TEST-OFFICIAL"
    )

    assert result.status == "CAPTURED_WITH_VERIFIED_LOCATORS"
    assert len(loaded.locators) == 2
    assert loaded.locators[0][2] == loaded.locators[1][2]
    assert loaded.locators[0][0] != loaded.locators[1][0]


def test_grouped_locator_requires_each_fragment_exactly_once(
    private_root: Path,
) -> None:
    target = _target(locator_status="LOCATORS_PENDING")
    grouped_target = capture_module.SourceCaptureTarget(
        source_ref=target.source_ref,
        url=target.url,
        host=target.host,
        path=target.path,
        observed_on=target.observed_on,
        charset=target.charset,
        locator_status="READY",
        locators=(
            capture_module.SourceLocator(
                "CLM-ST1704-TEST-OFFICIAL-SPECS",
                "a" * 64,
                (UNIQUE_FRAGMENT, SECOND_UNIQUE_FRAGMENT),
            ),
        ),
    )
    body = (
        f"<!doctype html><html><body><p>{UNIQUE_FRAGMENT}</p></body></html>"
    ).encode()

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module._persist_capture(
            private_root,
            capture_module.FetchedSource(
                target=grouped_target,
                retrieved_at="2026-08-23T12:34:56Z",
                content_type="text/html",
                body=body,
            ),
        )
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.LOCATOR_MISMATCH
    )


def test_body_is_installed_before_metadata_commit_marker(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed: list[str] = []
    original = capture_module._replace_private

    def recording_install(directory: Path, name: str, payload: bytes) -> None:
        installed.append(name)
        original(directory, name, payload)

    monkeypatch.setattr(capture_module, "_replace_private", recording_install)
    capture_module._persist_capture(
        private_root, _fetched(locator_status="LOCATORS_PENDING")
    )

    assert installed == [
        "SRC-TEST-OFFICIAL.capture.body",
        "SRC-TEST-OFFICIAL.capture.v1.json",
    ]


def test_later_capture_atomically_refreshes_body_and_metadata(
    private_root: Path,
) -> None:
    first = _fetched(locator_status="LOCATORS_PENDING")
    capture_module._persist_capture(private_root, first)
    sources = private_root / ".secrets" / OWNER_DIRECTORY / SOURCE_DIRECTORY
    body_path = sources / "SRC-TEST-OFFICIAL.capture.body"
    metadata_path = sources / "SRC-TEST-OFFICIAL.capture.v1.json"
    original_body = body_path.read_bytes()
    original_metadata = metadata_path.read_bytes()
    changed = _fetched(
        locator_status="LOCATORS_PENDING",
        body=HTML_BODY.replace(b"288", b"289"),
    )

    refreshed = capture_module._persist_capture(private_root, changed)

    assert refreshed.body_sha256 == bytes_sha256(changed.body)
    assert body_path.read_bytes() == changed.body
    assert body_path.read_bytes() != original_body
    assert metadata_path.read_bytes() != original_metadata


def test_interrupted_metadata_refresh_fails_closed_and_rerun_repairs(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = _fetched(locator_status="READY")
    capture_module._persist_capture(private_root, original)
    refreshed = _fetched(
        locator_status="READY",
        body=HTML_BODY.replace("公式仕様".encode(), "公式諸元".encode()),
    )
    replace_private = capture_module._replace_private
    metadata_failed = False

    def fail_first_metadata(directory: Path, name: str, payload: bytes) -> None:
        nonlocal metadata_failed
        if name.endswith(".v1.json") and not metadata_failed:
            metadata_failed = True
            raise capture_module.OfficialSourceCaptureFailure(
                capture_module.OfficialSourceCaptureFailureCode.STORE_UNSAFE
            )
        replace_private(directory, name, payload)

    monkeypatch.setattr(capture_module, "_replace_private", fail_first_metadata)
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as interrupted:
        capture_module._persist_capture(private_root, refreshed)
    assert _failure_code(interrupted) is (
        capture_module.OfficialSourceCaptureFailureCode.STORE_UNSAFE
    )
    with pytest.raises(EditorialPilotFailure) as mismatch:
        read_official_source_capture_evidence(
            private_root, source_ref="SRC-TEST-OFFICIAL"
        )
    assert mismatch.value.code is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID

    capture_module._persist_capture(private_root, refreshed)
    loaded = read_official_source_capture_evidence(
        private_root, source_ref="SRC-TEST-OFFICIAL"
    )
    assert loaded.body_sha256 == bytes_sha256(refreshed.body)


def test_private_store_rejects_symlink_at_every_owner_boundary(
    private_root: Path,
) -> None:
    outside = private_root / "outside"
    outside.mkdir(mode=0o700)
    (private_root / ".secrets").symlink_to(outside, target_is_directory=True)

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module._persist_capture(
            private_root, _fetched(locator_status="LOCATORS_PENDING")
        )
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.STORE_UNSAFE
    )
    assert list(outside.iterdir()) == []


def test_private_store_rejects_symlink_capture_file(private_root: Path) -> None:
    sources = private_root / ".secrets" / OWNER_DIRECTORY / SOURCE_DIRECTORY
    sources.mkdir(parents=True, mode=0o700)
    (private_root / ".secrets").chmod(0o700)
    (private_root / ".secrets" / OWNER_DIRECTORY).chmod(0o700)
    sources.chmod(0o700)
    outside = private_root / "outside-body"
    outside.write_bytes(b"do not overwrite")
    outside.chmod(0o600)
    (sources / "SRC-TEST-OFFICIAL.capture.body").symlink_to(outside)

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module._persist_capture(
            private_root, _fetched(locator_status="LOCATORS_PENDING")
        )
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.STORE_UNSAFE
    )
    assert outside.read_bytes() == b"do not overwrite"


def _option_strings(parser: object) -> set[str]:
    actions = cast(list[object], getattr(parser, "_actions"))
    return {
        option
        for action in actions
        for option in cast(list[str], getattr(action, "option_strings"))
    }


def test_capture_cli_exposes_only_two_closed_commands_and_fixed_selectors() -> None:
    namespace = runpy.run_path(str(CAPTURE_SCRIPT))
    parser = namespace["_parser"]()
    subparsers = next(
        action
        for action in parser._actions
        if getattr(action, "choices", None) is not None
    )
    choices = cast(dict[str, object], subparsers.choices)

    assert set(choices) == {"capture-source", "capture-article"}
    assert _option_strings(choices["capture-source"]) == {
        "-h",
        "--help",
        "--source-ref",
    }
    assert _option_strings(choices["capture-article"]) == {
        "-h",
        "--help",
        "--article-id",
    }
    registry = json.loads(
        (SOURCES_ROOT / "source-registry.v1.json").read_text(encoding="utf-8")
    )
    assert len(cast(tuple[str, ...], namespace["SOURCE_REFS"])) == (
        len(registry["sources"]) + len(registry["policy_sources"])
    )
    assert len(cast(tuple[str, ...], namespace["ARTICLE_IDS"])) == 10
    assert not REMOVED_RAKUTEN_ACE_REFS & set(namespace["SOURCE_REFS"])


def test_module_public_surface_has_no_caller_constructed_target_capture_entry() -> None:
    public = set(capture_module.__all__)
    assert {"capture_source_ref", "capture_article_sources"} <= public
    assert (
        not {
            "FetchedSource",
            "SourceCaptureTarget",
            "capture_sources",
            "fetch_source",
            "persist_capture",
            "OfficialSourceHttpsConnectionFactory",
            "SystemOfficialSourceHttpsConnectionFactory",
        }
        & public
    )


def test_public_capture_entries_rebind_only_tracked_source_and_article_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected: list[tuple[capture_module.SourceCaptureTarget, ...]] = []

    def record_targets(
        repository_root: Path,
        targets: tuple[capture_module.SourceCaptureTarget, ...],
        **_kwargs: object,
    ) -> tuple[capture_module.SourceCaptureResult, ...]:
        assert repository_root == REPOSITORY_ROOT
        selected.append(tuple(targets))
        return ()

    monkeypatch.setattr(capture_module, "_capture_targets", record_targets)
    factory = _Factory(_Response())
    source_result = capture_module.capture_source_ref(
        REPOSITORY_ROOT,
        source_ref="SRC-ANKER-SOLIX-C300",
        connection_factory=factory,
        clock=lambda: FIXED_NOW,
        environment={},
    )
    article_result = capture_module.capture_article_sources(
        REPOSITORY_ROOT,
        article_id="st1704-portable-power-station-guide",
        connection_factory=factory,
        clock=lambda: FIXED_NOW,
        environment={},
    )

    assert source_result == article_result == ()
    assert [target.source_ref for target in selected[0]] == ["SRC-ANKER-SOLIX-C300"]
    assert len(selected[1]) == 32
    assert {target.source_ref for target in selected[1]} >= POLICY_REFS
    assert factory.opens == []


@pytest.mark.parametrize(
    "argv",
    [
        ["capture-source", "--source-ref", "SRC-NOT-TRACKED"],
        [
            "capture-source",
            "--source-ref",
            "SRC-ANKER-SOLIX-C300",
            "--url",
            "https://attacker.invalid/",
        ],
        [
            "capture-source",
            "--source-ref",
            "SRC-ANKER-SOLIX-C300",
            "--output",
            "/tmp/capture",
        ],
        ["capture-article", "--article-id", "st1704-not-allowlisted"],
    ],
)
def test_capture_cli_refuses_arbitrary_identifier_url_and_output(
    argv: list[str],
) -> None:
    parser = runpy.run_path(str(CAPTURE_SCRIPT))["_parser"]()
    with pytest.raises(SystemExit) as rejected:
        parser.parse_args(argv)
    assert rejected.value.code == 2


def test_existing_wordpress_cli_remains_exactly_six_closed_commands() -> None:
    namespace = runpy.run_path(str(WORDPRESS_SCRIPT))
    assert namespace["COMMANDS"] == (
        "prepare",
        "prepare-review-draft-revision",
        "create-review-draft",
        "recover-create-review-draft",
        "verify-carry-on-single-url",
        "verify-public",
    )
    parser = namespace["_parser"]()
    subparsers = next(
        action
        for action in parser._actions
        if getattr(action, "choices", None) is not None
    )
    assert set(subparsers.choices) == set(namespace["COMMANDS"])
    for command in subparsers.choices.values():
        assert _option_strings(command) == {"-h", "--help", "--article-id"}
