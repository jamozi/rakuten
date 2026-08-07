"""Synthetic, contract-derived fixtures for the isolated ST-0801 suite."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

CONTENT_ROOT = REPOSITORY_ROOT / "contracts/raos-v0.4/contracts/content"
VALID_FIXTURE_ROOT = CONTENT_ROOT / "fixtures/valid"
INVALID_FIXTURE_ROOT = CONTENT_ROOT / "fixtures/invalid"
BLOCK_SCHEMA_ROOT = CONTENT_ROOT / "schemas/blocks"
TEST_MATRIX_PATH = CONTENT_ROOT / "RAOS_06_content_test_matrix_v0.1.csv"

JsonObject = dict[str, Any]


def rich_text(text: str = "合成テキスト") -> list[JsonObject]:
    return [{"type": "text", "text": text}]


MINIMAL_BLOCKS: dict[str, JsonObject] = {
    "lead": {"claim_ids": [], "content": rich_text()},
    "decision_summary": {
        "items": [{"condition": "条件", "summary": rich_text(), "claim_ids": []}]
    },
    "intended_reader": {
        "claim_ids": [],
        "fits": [rich_text()],
        "not_fits": [],
        "assumptions": [],
    },
    "methodology": {
        "claim_ids": [],
        "methodology_ref": "METH-CASE-001",
        "candidate_universe_summary": rich_text(),
        "inclusion_rules": [rich_text()],
        "exclusion_rules": [],
        "data_checked_at": "2026-07-30T00:00:00Z",
    },
    "selection_criteria": {
        "criteria": [
            {
                "comparison_axis_ref": "AXIS-CASE-001",
                "label": "軸",
                "explanation": rich_text(),
                "claim_ids": [],
            }
        ]
    },
    "heading": {
        "claim_ids": [],
        "level": 2,
        "content": rich_text(),
        "anchor_id": "case-heading",
    },
    "paragraph": {"claim_ids": [], "content": rich_text()},
    "bullet_list": {"items": [{"content": rich_text(), "claim_ids": []}]},
    "numbered_list": {"items": [{"content": rich_text(), "claim_ids": []}]},
    "comparison_table": {
        "claim_ids": [],
        "comparison_table_ref": "TABLE-CASE-001",
        "comparison_axis_refs": ["AXIS-CASE-001"],
        "product_selection_refs": ["PSEL-CASE-001", "PSEL-CASE-002"],
        "display_mode": "desktop_table_mobile_cards",
        "show_unknown_values": True,
    },
    "product_card": {
        "claim_ids": [],
        "recommendation_ref": "REC-CASE-001",
        "product_selection_ref": "PSEL-CASE-001",
        "display_policy_ref": "DISPLAY-CASE-001",
        "show_price_when_fresh": True,
        "show_availability_when_fresh": True,
    },
    "recommendation_group": {
        "group_id": "GROUP-CASE-001",
        "label": "条件向け",
        "condition": rich_text(),
        "recommendation_refs": ["REC-CASE-001"],
        "rationale_claim_ids": [],
        "strict_order": False,
    },
    "difference_matrix": {
        "claim_ids": [],
        "matrix_ref": "MATRIX-CASE-001",
        "comparison_axis_refs": ["AXIS-CASE-001"],
        "product_selection_refs": ["PSEL-CASE-001", "PSEL-CASE-002"],
        "show_equal_values": True,
        "show_unknown_values": True,
    },
    "pros_cons": {"subject_ref": "SUBJECT-CASE-001", "pros": [], "cons": []},
    "tradeoff": {
        "claim_ids": [],
        "subject_ref": "SUBJECT-CASE-001",
        "benefit": rich_text(),
        "cost_or_limitation": rich_text(),
        "applies_when": rich_text(),
    },
    "caution": {"claim_ids": [], "severity": "info", "content": rich_text()},
    "evidence_note": {
        "claim_ids": [],
        "evidence_refs": ["EVIDENCE-CASE-001"],
        "display_mode": "inline",
    },
    "source_summary": {
        "claim_ids": [],
        "source_packet_version_ref": "SPV-CASE-001",
        "last_checked_at": "2026-07-30T00:00:00Z",
        "editorial_policy_route_ref": "ROUTE-CASE-001",
        "show_source_categories": True,
    },
    "faq": {
        "items": [{"question": "質問", "answer": rich_text(), "claim_ids": []}],
        "emit_faqpage_structured_data": False,
    },
    "media": {
        "claim_ids": [],
        "media_asset_ref": "MEDIA-CASE-001",
        "caption": rich_text(),
        "long_description_ref": None,
        "presentation": "figure",
    },
    "internal_links": {
        "links": [
            {
                "route_ref": "ROUTE-CASE-001",
                "anchor_text": "関連記事",
                "journey_purpose": "次の判断を助ける",
            }
        ]
    },
    "update_notice": {
        "claim_ids": [],
        "substantive_updated_at": "2026-07-30T00:00:00Z",
        "change_summary": rich_text(),
        "previous_publication_ref": None,
    },
    "callout": {
        "claim_ids": [],
        "variant": "info",
        "title": "補足",
        "content": rich_text(),
    },
    "disclosure_slot": {
        "disclosure_policy_version_ref": "DISC-CASE-001",
        "placement": "article_top",
        "editor_removable": False,
    },
}

BLOCK_TYPES = tuple(MINIMAL_BLOCKS)
BLOCK_TEXT_PATHS: dict[str, tuple[str | int, ...]] = {
    "lead": ("content", 0, "text"),
    "decision_summary": ("items", 0, "summary", 0, "text"),
    "intended_reader": ("fits", 0, 0, "text"),
    "methodology": ("candidate_universe_summary", 0, "text"),
    "selection_criteria": ("criteria", 0, "explanation", 0, "text"),
    "heading": ("content", 0, "text"),
    "paragraph": ("content", 0, "text"),
    "bullet_list": ("items", 0, "content", 0, "text"),
    "numbered_list": ("items", 0, "content", 0, "text"),
    "recommendation_group": ("condition", 0, "text"),
    "pros_cons": ("pros", 0, "content", 0, "text"),
    "tradeoff": ("benefit", 0, "text"),
    "caution": ("content", 0, "text"),
    "faq": ("items", 0, "answer", 0, "text"),
    "media": ("caption", 0, "text"),
    "internal_links": ("links", 0, "anchor_text"),
    "update_notice": ("change_summary", 0, "text"),
    "callout": ("content", 0, "text"),
}


def block_payload(block_type: str, index: int = 1) -> JsonObject:
    block = deepcopy(MINIMAL_BLOCKS[block_type])
    block["block_id"] = f"BLK-CASE-{index:03d}"
    block["type"] = block_type
    return block


def block_payload_with_text(
    block_type: str, text: str, index: int = 1
) -> tuple[JsonObject, tuple[str | int, ...]]:
    block = block_payload(block_type, index)
    if block_type == "pros_cons":
        block["pros"] = [{"content": rich_text(), "claim_ids": []}]
    path = BLOCK_TEXT_PATHS[block_type]
    cursor: Any = block
    for component in path[:-1]:
        cursor = cursor[component]
    cursor[path[-1]] = text
    return block, path


def nested_value(value: object, path: tuple[str | int, ...]) -> object:
    cursor: Any = value
    for component in path:
        cursor = cursor[component]
    return cursor


@pytest.fixture(scope="session")
def baseline_payload() -> JsonObject:
    path = VALID_FIXTURE_ROOT / "selection_guide.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def payload_with_block(baseline: JsonObject, block_type: str) -> JsonObject:
    payload = deepcopy(baseline)
    payload["blocks"] = [block_payload(block_type, 999), *payload["blocks"]]
    return payload


def encoded(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False)
