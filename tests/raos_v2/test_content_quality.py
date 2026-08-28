from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from raos.domain.decision_support_v2.content_quality import (
    ContentPacket,
    correction_rate,
    difference_route_allowed,
    validate_content_packet,
)
from raos.domain.decision_support_v2.freshness import assess_freshness
from raos.domain.decision_support_v2.models import FreshnessState, RiskClass
from raos.domain.decision_support_v2.models import (
    CaptureMode,
    CaptureProvenance,
    Claim,
    ClaimStatus,
    ClaimType,
    SourceClass,
    SourceRecord,
)


ROOT = Path(__file__).resolve().parents[2]
CONTENT = ROOT / "changes/raos-v2/phase-2/content"


def _valid() -> ContentPacket:
    return ContentPacket(
        disclosure="広告リンクを含む場合があります。",
        thirty_second_conclusion="条件は区間ごとに確認します。",
        unknowns=("当日の判断",),
        official_source_urls=("https://www.ana.co.jp/example",),
        fits=("公式条件を確認したい人",),
        non_fits=("搭乗保証を求める人",),
        tradeoffs=("安全側の判定",),
    )


def test_t_v2_033_quality_gate_accepts_complete_packet() -> None:
    assert validate_content_packet(_valid()) == ()


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("disclosure", "MISSING_DISCLOSURE"),
        ("thirty_second_conclusion", "MISSING_30_SECOND_CONCLUSION"),
        ("unknowns", "MISSING_UNKNOWNS"),
        ("official_source_urls", "MISSING_OFFICIAL_SOURCES"),
        ("fits", "MISSING_FIT"),
        ("non_fits", "MISSING_NON_FIT"),
        ("tradeoffs", "MISSING_TRADEOFF"),
    ],
)
def test_quality_gate_rejects_each_required_section(field: str, code: str) -> None:
    packet = _valid()
    values = {name: getattr(packet, name) for name in packet.__dataclass_fields__}
    values[field] = "" if isinstance(values[field], str) else ()
    assert code in validate_content_packet(ContentPacket(**values))


def test_experience_claim_is_blocked_without_real_use() -> None:
    packet = _valid()
    values = {name: getattr(packet, name) for name in packet.__dataclass_fields__}
    values["experience_claims"] = ("使って便利だった",)
    assert "UNVERIFIED_EXPERIENCE_CLAIM" in validate_content_packet(
        ContentPacket(**values)
    )


@pytest.mark.parametrize(
    "text", ["実際に使ってみた結果です", "寸法を実測した", "使用して分かった弱点"]
)
def test_false_hands_on_language_is_linted_in_visible_fields(text: str) -> None:
    packet = _valid()
    values = {name: getattr(packet, name) for name in packet.__dataclass_fields__}
    values["thirty_second_conclusion"] = text
    assert "FALSE_HANDS_ON_LANGUAGE" in validate_content_packet(ContentPacket(**values))


def test_t_v2_027_difference_overlap_guard() -> None:
    assert not difference_route_allowed(
        difference_query="ACE Cresta Difference Maxpass4 comparison",
        comparison_query="ACE Cresta Difference Maxpass4 comparison",
    )
    assert difference_route_allowed(
        difference_query="05721 06316 door opening distinction",
        comparison_query="carry on suitcase weight capacity comparison",
    )
    assert not difference_route_allowed(
        difference_query="機内持ち込みスーツケース三機種の重さと容量を比較",
        comparison_query="機内持ち込みスーツケース3機種の重さ容量比較",
        threshold=0.45,
    )


def test_t_v2_032_correction_rate_is_reproducible() -> None:
    assert correction_rate(2, 100) == "2/100"
    with pytest.raises(ValueError):
        correction_rate(3, 2)


def test_t_v2_034_freshness_exact_boundaries() -> None:
    due = datetime.fromisoformat("2026-09-01T00:00:00+09:00")
    assert (
        assess_freshness(
            now=due - timedelta(microseconds=1),
            next_review_at=due,
            risk_class=RiskClass.HIGH,
        ).state
        is FreshnessState.FRESH
    )
    assert (
        assess_freshness(now=due, next_review_at=due, risk_class=RiskClass.HIGH).state
        is FreshnessState.DUE
    )
    assert (
        assess_freshness(
            now=due + timedelta(days=7),
            next_review_at=due,
            risk_class=RiskClass.HIGH,
        ).state
        is FreshnessState.SOFT_STALE
    )
    assert (
        assess_freshness(
            now=due + timedelta(days=7, microseconds=1),
            next_review_at=due,
            risk_class=RiskClass.HIGH,
        ).state
        is FreshnessState.HARD_STALE
    )


def test_phase_2_content_packets_state_external_actions_not_executed() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in CONTENT.glob("*.yaml")
    )
    assert "publication: NOT_EXECUTED" in text
    assert "human_review: NOT_EXECUTED" in text
    assert "実走行、耐久性、キャスター音" in text


def test_claim_times_must_be_aware_and_review_after_check() -> None:
    checked = datetime.fromisoformat("2026-08-28T00:00:00+09:00")
    with pytest.raises(ValueError):
        Claim(
            "CLM-TEST",
            ClaimType.UNKNOWN,
            "PRD-TEST",
            "unknown",
            None,
            None,
            (),
            checked.replace(tzinfo=None),
            checked + timedelta(days=1),
            RiskClass.LOW,
        )
    with pytest.raises(ValueError):
        Claim(
            "CLM-TEST",
            ClaimType.UNKNOWN,
            "PRD-TEST",
            "unknown",
            None,
            None,
            (),
            checked,
            checked,
            RiskClass.LOW,
        )


def test_competitor_ux_source_cannot_support_product_fact() -> None:
    checked = datetime.fromisoformat("2026-08-28T00:00:00+09:00")
    source = SourceRecord(
        source_id="SRC-COMPETITOR-UX",
        source_class=SourceClass.COMPETITOR_UX_ONLY,
        publisher="UX research only",
        title="Public interface observation",
        canonical_url="https://example.invalid/ux-only",
        published_at=None,
        checked_at=checked,
        effective_from=None,
        effective_to=None,
        content_sha256="a" * 64,
        next_review_at=checked + timedelta(days=30),
        capture_provenance=CaptureProvenance(CaptureMode.RECORDED_FIXTURE, checked),
    )
    claim = Claim(
        "CLM-PRODUCT-WEIGHT",
        ClaimType.A_OFFICIAL_FACT,
        "PRD-ACE-CRESTA-06316",
        "mass_kg",
        "3.2",
        "kg",
        (source.source_id,),
        checked,
        checked + timedelta(days=30),
        RiskClass.MEDIUM,
    )
    with pytest.raises(ValueError):
        claim.validate_sources({source.source_id: source})


@pytest.mark.parametrize(
    "canonical_url",
    [
        "https://user@example.invalid/source",
        "https://:password@example.invalid/source",
        "https://example.invalid:444/source",
        "https://example.invalid:bad/source",
        "https:///missing-authority",
    ],
)
def test_source_url_rejects_credentials_and_nondefault_or_invalid_ports(
    canonical_url: str,
) -> None:
    checked = datetime.fromisoformat("2026-08-28T00:00:00+09:00")
    with pytest.raises(ValueError):
        SourceRecord(
            source_id="SRC-URL-NEGATIVE",
            source_class=SourceClass.GOVERNMENT_PRIMARY,
            publisher="Official publisher",
            title="Official title",
            canonical_url=canonical_url,
            published_at=None,
            checked_at=checked,
            effective_from=None,
            effective_to=None,
            content_sha256="a" * 64,
            next_review_at=checked + timedelta(days=30),
            capture_provenance=CaptureProvenance(CaptureMode.RECORDED_FIXTURE, checked),
        )


def test_source_contract_schema_rejects_credentialed_and_nondefault_port_urls() -> None:
    checked = datetime.fromisoformat("2026-08-28T00:00:00+09:00")
    source = SourceRecord(
        source_id="SRC-URL-SCHEMA",
        source_class=SourceClass.GOVERNMENT_PRIMARY,
        publisher="Official publisher",
        title="Official title",
        canonical_url="https://example.invalid/source",
        published_at=None,
        checked_at=checked,
        effective_from=None,
        effective_to=None,
        content_sha256="a" * 64,
        next_review_at=checked + timedelta(days=30),
        capture_provenance=CaptureProvenance(CaptureMode.RECORDED_FIXTURE, checked),
    )
    schema = json.loads(
        (ROOT / "contracts/raos-v2/v1/source-record.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema)
    for canonical_url in (
        "https://user@example.invalid/source",
        "https://:password@example.invalid/source",
        "https://example.invalid:444/source",
    ):
        record = dict(source.to_contract_record())
        record["canonical_url"] = canonical_url
        assert list(validator.iter_errors(record))


def test_claim_runtime_records_validate_directly_against_phase_1_contract() -> None:
    checked = datetime.fromisoformat("2026-08-28T00:00:00+09:00")
    claims = (
        Claim(
            "CLM-TEST-OFFICIAL",
            ClaimType.A_OFFICIAL_FACT,
            "PRD-ACE-CRESTA-06316",
            "mass_kg",
            "3.2",
            "kg",
            ("SRC-ACE-CRESTA-06316",),
            checked,
            checked + timedelta(days=30),
            RiskClass.MEDIUM,
            status=ClaimStatus.VERIFIED,
        ),
        Claim(
            "CLM-TEST-EDITORIAL",
            ClaimType.D_EDITORIAL_JUDGEMENT,
            "PRD-ACE-CRESTA-06316",
            "fit.outcome",
            "candidate",
            None,
            (),
            checked,
            checked + timedelta(days=30),
            RiskClass.LOW,
            logic_inputs={"COMPATIBILITY": "PRD-ACE-CRESTA-06316"},
            status=ClaimStatus.VERIFIED,
        ),
        Claim(
            "CLM-TEST-UNKNOWN",
            ClaimType.UNKNOWN,
            "PRD-ACE-CRESTA-06316",
            "durability",
            None,
            None,
            (),
            checked,
            checked + timedelta(days=30),
            RiskClass.HIGH,
            status=ClaimStatus.BLOCKED,
        ),
    )
    schema = json.loads(
        (ROOT / "contracts/raos-v2/v1/claim.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    for claim in claims:
        validator.validate(claim.to_contract_record())
