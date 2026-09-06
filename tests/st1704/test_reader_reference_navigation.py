import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pytest
from scripts import build_st1704_reader_claim_coverage as o

DOC = json.loads((o.ROOT / o.LEDGER_RELATIVE).read_text())
MODEL = o._load_repository_model(o.ROOT, require_fresh_sales_state=False)
CASES = []
for article in DOC["articles"]:
    aid = article["article_id"]
    units = o._final_reader_units(
        aid,
        MODEL.articles[aid],
        (o.ROOT / article["content_ref"]).read_bytes(),
        MODEL.product_aliases[aid],
    )
    for unit, binding in zip(units, article["units"], strict=True):
        if binding["text"].endswith("の型番・販売表示を確認する"):
            CASES.append((aid, unit, binding))


def validate(aid, unit, binding):
    selected = set(MODEL.articles[aid]["product_ids"])
    selected.update(
        p
        for c in MODEL.claims[aid].values()
        if c.get("portfolio_candidate_disposition") == "REFERENCE_ONLY"
        for p in c["subject_product_ids"]
    )
    o._validate_unit_binding(
        article_id=aid,
        unit=unit,
        raw_binding=binding,
        packet_claims=MODEL.claims[aid],
        support_by_claim=MODEL.supports[aid],
        claim_subjects=MODEL.claim_subjects[aid],
        product_aliases=MODEL.product_aliases[aid],
        sales_states=MODEL.sales_states,
        safety_statuses=MODEL.safety_statuses,
        market_axis_states=MODEL.market_axis_states,
        allowed_product_ids=selected,
    )


def rebound(unit, binding, **changes):
    unit = replace(unit, **changes)
    binding = copy.deepcopy(binding)
    for k in ("text", "locator", "channel", "context", "owner_product_id"):
        binding[k] = getattr(unit, k)
    binding["text_sha256"] = hashlib.sha256(unit.text.encode()).hexdigest()
    unit = replace(unit, text_sha256=binding["text_sha256"])
    return unit, binding


@pytest.mark.parametrize("aid,unit,binding", CASES)
def test_exact_candidate_navigation(aid, unit, binding):
    assert o._official_reference_navigation_matches(unit, MODEL.claims[aid])
    validate(aid, unit, binding)


@pytest.mark.parametrize("aid,unit,binding", CASES)
@pytest.mark.parametrize(
    "mutation",
    [
        "added_spec",
        "added_feature",
        "added_sales",
        "wrong_model",
        "wrong_maker",
        "wrong_owner",
        "non_anchor",
        "structural_cell",
        "other_exemption",
    ],
)
def test_navigation_does_not_hide_claims(aid, unit, binding, mutation):
    if mutation == "added_spec":
        changes = dict(text=unit.text + "。容量999Lです。")
    elif mutation == "added_feature":
        changes = dict(text=unit.text.replace("の型番", "・タンク式対応の型番"))
    elif mutation == "added_sales":
        changes = dict(text=unit.text.replace("の型番", "・販売中の型番"))
    elif mutation == "wrong_model":
        changes = dict(text=unit.text.replace("公式で", "公式で別機種999L "))
    elif mutation == "wrong_maker":
        changes = dict(text="Other" + unit.text)
    elif mutation == "wrong_owner":
        changes = dict(owner_product_id="EXT-OTHER-MODEL")
    elif mutation == "non_anchor":
        changes = dict(locator="section[1]/p[1]::text")
    elif mutation == "structural_cell":
        changes = dict(
            locator="section[1]/table[1]/tbody[1]/tr[1]/td[1]::text",
            context="COMPARISON",
        )
    else:
        changes = {}
    changed, raw = rebound(unit, binding, **changes)
    if mutation == "other_exemption":
        raw["exemption_code"] = "SOURCE_CITATION_LABEL"
    else:
        assert not o._official_reference_navigation_matches(changed, MODEL.claims[aid])
    with pytest.raises(o.CoverageFailure):
        validate(aid, changed, raw)


def test_model_capacity_remains_an_assertion_outside_navigation():
    assert "20L" in o.required_assertion_tokens("ハードキャリーケース 20L")
    assert "999L" in o.required_assertion_tokens(
        "無印良品公式でハードキャリーケース 20Lの型番・販売表示を確認する。容量999Lです。"
    )


SUPPLY = []
article = DOC["articles"][3]
aid = article["article_id"]
units = o._final_reader_units(
    aid,
    MODEL.articles[aid],
    (o.ROOT / article["content_ref"]).read_bytes(),
    MODEL.product_aliases[aid],
)
for unit, binding in zip(units, article["units"], strict=True):
    if unit.text in (
        "タンク式/分岐水栓式(2WAY) 公式確認済み",
        "タンク式 公式確認済み",
        "未確認 未確認",
    ) and (
        unit.locator.endswith("/td[3]::text") or "/div[4]/dd[1]::text" in unit.locator
    ):
        SUPPLY.append((aid, unit, binding))


@pytest.mark.parametrize("aid,unit,binding", SUPPLY)
def test_supply_cannot_borrow_another_models_claim(aid, unit, binding):
    validate(aid, unit, binding)
    changed = copy.deepcopy(binding)
    cid = (
        "CLM-ST1704-DISH-RAKUA-SPECS"
        if unit.subject_product_ids == ("PRD-SIROCA-SS-M171",)
        else "CLM-ST1704-DISH-SS-M171-SPECS"
    )
    changed.update(kind="VERIFIABLE", claim_ids=[cid])
    for assertion in changed["assertion_tokens"]:
        assertion["claim_ids"] = [cid]
    with pytest.raises(o.CoverageFailure):
        validate(aid, unit, changed)
