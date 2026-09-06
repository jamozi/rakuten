"""Guard the Anker lifecycle table's evidence limits and recommendation boundary."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SLICE = ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1"
ARTICLE_ID = "st1704-anker-solix-c300-c800-c1000-differences"
TABLE_REF = "TABLE-ANKER-LIFECYCLE-V1"


def _inputs():
    content = json.loads(
        (SLICE / "content/articles.v1.json").read_text(encoding="utf-8")
    )
    registry = json.loads(
        (SLICE / "sources/source-registry.v1.json").read_text(encoding="utf-8")
    )
    article = next(a for a in content["articles"] if a["article_id"] == ARTICLE_ID)
    packet = next(
        p for p in registry["source_packets"] if p["article_id"] == ARTICLE_ID
    )
    table = next(
        t
        for t in article["render_model"]["comparison_tables"]
        if t["comparison_table_ref"] == TABLE_REF
    )
    return article, packet, table, registry


@pytest.mark.parametrize(
    ("product_ref", "source_ref", "exact_model", "cycle_text", "threshold_state"),
    [
        ("PSEL-ANKER-C300", "SRC-ANKER-SOLIX-C300", "A17225Z1", "3,000回", "UNKNOWN"),
        ("PSEL-ANKER-C800", "SRC-ANKER-SOLIX-C800-PLUS", "A1754", "3,000回", "UNKNOWN"),
        (
            "PSEL-ANKER-C1000",
            "SRC-ANKER-SOLIX-C1000",
            "A17615Z1",
            "3,000回以上",
            "KNOWN",
        ),
        (
            "PSEL-ANKER-C1000-GEN2",
            "SRC-ANKER-SOLIX-C1000-GEN2",
            "A17635Z1",
            "4,000回以上の充放電サイクル",
            "KNOWN",
        ),
    ],
)
def test_each_lifecycle_row_uses_its_own_official_source_and_observation(
    product_ref,
    source_ref,
    exact_model,
    cycle_text,
    threshold_state,
) -> None:
    article, packet, table, registry = _inputs()
    row = next(r for r in table["rows"] if r["product_selection_ref"] == product_ref)
    cells = {
        c["axis_ref"].removeprefix("AXIS-ANKER-LIFECYCLE-"): c for c in row["cells"]
    }
    card = next(
        c
        for c in article["render_model"]["product_cards"]
        if c["product_selection_ref"] == product_ref
    )
    claim_ids = {claim_id for cell in cells.values() for claim_id in cell["claim_ids"]}
    assert len(claim_ids) == 1
    claim = next(c for c in packet["claims"] if c["claim_id"] in claim_ids)
    assert claim["evidence_refs"] == [source_ref]
    assert claim["subject_product_ids"] == [card["product_id"]]
    assert exact_model in claim["statement"]
    source = next(s for s in registry["sources"] if s["source_ref"] == source_ref)
    assert source["authority"] == "MANUFACTURER_OFFICIAL"
    assert source_ref in card["source_refs"]

    observation = re.search(
        r"寿命条件の限定確認日：(\d{4}-\d{2}-\d{2})", claim["statement"]
    )
    assert observation is not None
    assert observation[1] == table["presentation"]["checked_at"]
    assert observation[1] in cells["SOURCE"]["value"]
    assert exact_model in cells["SOURCE"]["value"]

    assert cells["CYCLES"]["value"] == cycle_text
    assert cells["CYCLES"]["state"] == "KNOWN"
    assert cells["CAPACITY"]["state"] == threshold_state
    if threshold_state == "UNKNOWN":
        assert "未確認" in cells["CAPACITY"]["value"]
        assert "80%" not in cells["CAPACITY"]["value"]
    else:
        assert "初期容量の80%まで低下するまで" in cells["CAPACITY"]["value"]
    assert cells["TEST"]["state"] == "UNKNOWN"
    assert all(
        term in cells["TEST"]["value"]
        for term in ("未確認", "温度", "レート", "放電深度")
    )
    assert "18か月" in cells["WARRANTY"]["value"]
    assert "会員" in cells["WARRANTY"]["value"]
    assert "購入先ごとの適用可否・除外条件は未確認" in cells["WARRANTY"]["value"]


def test_lifecycle_table_is_additive_to_the_existing_four_model_comparison() -> None:
    article, _, table, _ = _inputs()
    blocks = article["content_ast"]["blocks"]
    original = next(
        b for b in blocks if b.get("comparison_table_ref") == "TABLE-ANKER-V1"
    )
    added = next(b for b in blocks if b.get("comparison_table_ref") == TABLE_REF)
    assert added["type"] == "comparison_table"
    assert added["show_unknown_values"] is True
    assert added["comparison_axis_refs"] == table["axis_refs"]
    assert added["product_selection_refs"] == original["product_selection_refs"]
    assert len(table["rows"]) == 4
    assert [r["product_selection_ref"] for r in table["rows"]] == added[
        "product_selection_refs"
    ]
    assert blocks.index(original) < blocks.index(added)
    assert blocks.index(added) < next(
        i for i, b in enumerate(blocks) if b["type"] == "product_card"
    )
    assert table["presentation"]["role"] == "supporting_evidence"
    assert table["presentation"]["source_axis_ref"] in table["axis_refs"]
    assert table["presentation"]["source_axis_ref"] == "AXIS-ANKER-LIFECYCLE-SOURCE"
    method = next(b for b in blocks if b["type"] == "methodology")
    assert "使用年数に換算したり、世代の寿命を順位付けしたりしません" in json.dumps(
        method, ensure_ascii=False
    )


def test_cycle_counts_are_not_recommendation_or_exclusion_criteria() -> None:
    article, packet, _, _ = _inputs()
    model = article["render_model"]
    decisions = [
        model["recommendations"],
        [
            b
            for b in article["content_ast"]["blocks"]
            if b["type"] in {"decision_summary", "tradeoff", "selection_criteria"}
        ],
        [
            {
                "condition": c["condition_label"],
                "fit": c["editorial_fit"],
                "presentation": c["presentation_v2"],
            }
            for c in model["product_cards"]
        ],
    ]
    reader = json.loads(
        (ROOT / "changes/editorial-portfolio-v3/reader-experience.v1.json").read_text()
    )
    overlay = (
        reader["articles"][ARTICLE_ID]
        if isinstance(reader["articles"], dict)
        else next(a for a in reader["articles"] if a["article_id"] == ARTICLE_ID)
    )
    decisions.append(overlay["products"])
    text = json.dumps(decisions, ensure_ascii=False)
    assert not any(term in text for term in ("サイクル", "充放電", "4,000", "4000"))
    rationale = next(
        c["statement"]
        for c in packet["claims"]
        if c["claim_id"] == "CLM-ST1704-ANKER-CONDITIONAL-CHOICES"
    )
    assert "推薦条件に使わない" in rationale
    assert "公表サイクル数を条件にする場合の候補" not in rationale
