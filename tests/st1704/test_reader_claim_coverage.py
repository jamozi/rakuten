"""Closed-world reader-unit/source-claim coverage contracts."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timedelta, tzinfo
import hashlib
import json
from pathlib import Path
import shutil
from typing import cast

import pytest

from scripts import build_st1704_reader_claim_coverage as owner


ROOT = Path(__file__).resolve().parents[2]
INDEPENDENT_REVIEW_ANCHOR = owner.REVIEWED_READER_LEDGER_SHA256
SAFETY_STATUS_LOADER = owner._load_product_safety_statuses


@pytest.fixture(autouse=True)
def recorded_capture_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Semantic fixture tests replay the capture date, not wall-clock expiry."""

    class RecordedClock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return datetime.fromisoformat("2026-09-01T00:00:00+00:00").astimezone(tz)

    monkeypatch.setattr(owner, "datetime", RecordedClock)
    safety_loader = owner._load_product_safety_statuses
    monkeypatch.setattr(
        owner,
        "_load_product_safety_statuses",
        lambda **kwargs: safety_loader(**{**kwargs, "replay_owner_private": False}),
    )
    # Unit tests exercise semantic validation, not independent attestation.
    monkeypatch.setattr(
        owner, "REVIEWED_READER_LEDGER_SHA256", owner.DEVELOPMENT_READER_LEDGER_SHA256
    )


def test_development_ledger_does_not_claim_independent_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        owner, "REVIEWED_READER_LEDGER_SHA256", INDEPENDENT_REVIEW_ANCHOR
    )
    owner.validate_repository(ROOT, require_fresh_sales_state=False)
    with pytest.raises(owner.CoverageFailure, match="independently reviewed"):
        owner.validate_repository(ROOT)


def test_development_replay_does_not_depend_on_private_capture_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(owner, "_load_product_safety_statuses", SAFETY_STATUS_LOADER)

    def private_capture_must_not_run(*args: object, **kwargs: object) -> object:
        raise AssertionError("private capture replay requested")

    monkeypatch.setattr(
        owner, "load_product_safety_receipt_audit", private_capture_must_not_run
    )
    owner.validate_repository(ROOT, require_fresh_sales_state=False)
    with pytest.raises(AssertionError, match="private capture replay requested"):
        owner.validate_repository(ROOT)


def _ledger() -> dict[str, object]:
    return json.loads((ROOT / owner.LEDGER_RELATIVE).read_text(encoding="utf-8"))


def _articles(document: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], document["articles"])


def _units(article: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], article["units"])


def _copy_repository_inputs(destination: Path) -> Path:
    root = destination / "repository"
    paths = {
        owner.PORTFOLIO_RELATIVE,
        owner.REGISTRY_RELATIVE,
        owner.LOCATOR_RELATIVE,
        owner.LEDGER_RELATIVE,
        owner.SALES_STATE_RELATIVE,
        owner.PRODUCT_SAFETY_RECEIPT_RELATIVE,
        owner.PRODUCT_SAFETY_ADMIN_PLAN_RELATIVE,
        owner.PRODUCT_SAFETY_MANUFACTURER_PLAN_RELATIVE,
        owner.PRODUCT_SAFETY_MANUFACTURER_EMPTY_RELATIVE,
        owner.MARKET_AUDIT_RELATIVE,
        owner.LEGACY_CONTENT_RELATIVE,
        owner.POSTS_RELATIVE,
    }
    portfolio = json.loads(
        (ROOT / owner.PORTFOLIO_RELATIVE).read_text(encoding="utf-8")
    )
    paths.update(Path(article["content_ref"]) for article in portfolio["articles"])
    for relative in paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return root


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _first_unit(
    document: dict[str, object],
    *,
    kind: str | None = None,
    context: str | None = None,
    assertions: bool | None = None,
) -> dict[str, object]:
    for article in _articles(document):
        for unit in _units(article):
            if kind is not None and unit["kind"] != kind:
                continue
            if context is not None and unit["context"] != context:
                continue
            if assertions is not None and bool(unit["assertion_tokens"]) != assertions:
                continue
            return unit
    raise AssertionError("required reader-unit test subject is absent")


def _article(document: dict[str, object], article_id: str) -> dict[str, object]:
    return next(
        article
        for article in _articles(document)
        if article["article_id"] == article_id
    )


def _unit_containing(
    document: dict[str, object],
    article_id: str,
    needle: str,
    *,
    channel: str | None = None,
) -> dict[str, object]:
    return next(
        unit
        for unit in _units(_article(document, article_id))
        if needle in cast(str, unit["text"])
        and (channel is None or unit["channel"] == channel)
    )


def _refresh_article_binding(
    root: Path,
    document: dict[str, object],
    article_id: str,
) -> None:
    """Refresh only extracted identity fields after a deliberate test tamper."""

    model = owner._load_repository_model(root)
    article = model.articles[article_id]
    binding = _article(document, article_id)
    content_ref = cast(str, article["content_ref"])
    extracted = owner._final_reader_units(
        article_id,
        article,
        (root / content_ref).read_bytes(),
        model.product_aliases[article_id],
    )
    existing = {cast(str, unit["unit_id"]): unit for unit in _units(binding)}
    assert set(existing) == {unit.unit_id for unit in extracted}
    for unit in extracted:
        ledger_unit = existing[unit.unit_id]
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
            ledger_unit[key] = getattr(unit, key)
        ledger_unit["subject_product_ids"] = list(unit.subject_product_ids)
        ledger_unit["owner_product_id"] = unit.owner_product_id
    binding["reader_units_sha256"] = owner._unit_digest(extracted)
    binding["authoring_input"] = owner._authoring_input(
        root, model, article_id, content_ref
    )


def _rewrite_static_unit(
    root: Path,
    document: dict[str, object],
    article_id: str,
    unit: dict[str, object],
    replacement: str,
) -> dict[str, object]:
    binding = _article(document, article_id)
    content_path = root / cast(str, binding["content_ref"])
    original = content_path.read_text(encoding="utf-8")
    text = cast(str, unit["text"])
    assert original.count(text) == 1
    content_path.write_text(original.replace(text, replacement, 1), encoding="utf-8")
    _refresh_article_binding(root, document, article_id)
    return next(
        candidate
        for candidate in _units(binding)
        if candidate["unit_id"] == unit["unit_id"]
    )


def _write_sales_document(
    root: Path,
    value: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = root / owner.SALES_STATE_RELATIVE
    _write_json(path, value)
    monkeypatch.setattr(
        owner,
        "REVIEWED_SALES_STATE_DOCUMENT_SHA256",
        hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def test_tracked_ledger_covers_exactly_the_ten_final_article_fixtures() -> None:
    owner.validate_repository(ROOT)
    document = _ledger()
    assert document["article_ids"] == list(owner.ARTICLE_IDS)
    assert [article["article_id"] for article in _articles(document)] == list(
        owner.ARTICLE_IDS
    )
    assert all(
        str(article["content_ref"]).startswith(
            "changes/wordpress-local-preview-v1/fixtures/articles/"
        )
        for article in _articles(document)
    )
    assert all(_units(article) for article in _articles(document))
    assert not any(
        unit["kind"] == "UNCLASSIFIED"
        for article in _articles(document)
        for unit in _units(article)
    )


def test_editorial_rewrite_keeps_product_claims_and_unresolved_warranty_bound() -> None:
    document = _ledger()
    dji = _unit_containing(
        document,
        "st1704-portable-power-station-guide",
        "おすすめする理由: メーカー公表の最大連続出力が接続機器の条件に合い",
    )
    assert dji["kind"] == "EDITORIAL_INFERENCE"
    dji_claims = cast(list[str], dji["claim_ids"])
    assert "CLM-ST1704-POWER-DJI-1000-V2-SPECS" in dji_claims
    assert "CLM-ST1704-POWER-CONDITIONAL-CHOICES" in dji_claims
    assert "保証" not in cast(str, dji["text"])
    assert (
        cast(dict[str, object], dji["decision_gate"])["publication_gate"] == "BLOCKED"
    )
    k11 = _unit_containing(
        document,
        "st1704-compact-robot-vacuum-shortlist",
        "無償保証期間は未確定のため、推奨根拠には使いません。",
    )
    assert k11["kind"] == "EDITORIAL_INFERENCE"
    assert "CLM-ST1704-ROBOT-K11-PRO-WARRANTY-UNRESOLVED" in cast(
        list[str], k11["claim_ids"]
    )
    assert (
        cast(dict[str, object], k11["decision_gate"])["publication_gate"] == "BLOCKED"
    )


def test_short_intro_scope_limit_is_not_a_product_fact_or_permission() -> None:
    unit = _unit_containing(
        _ledger(),
        "carry-on-suitcase-under-100-seats",
        "軽さ、前開き、PC収納のどれが必要かを考える前に",
    )
    assert unit["kind"] == "NON_CLAIM"
    assert unit["exemption_code"] == "EDITORIAL_METHOD"
    assert unit["claim_ids"] == []
    assert unit["decision_gate"] is None
    assert unit["text"] in owner.METHOD_FIXED_TEXTS
    unsafe = cast(str, unit["text"]).replace("確定できません", "確定できます")
    assert unsafe not in owner.METHOD_FIXED_TEXTS
    assert (
        "清掃力・段差・障害物回避は実機で比べていません。" in owner.METHOD_FIXED_TEXTS
    )
    assert (
        "清掃力・段差・障害物回避は実機で比べました。" not in owner.METHOD_FIXED_TEXTS
    )


@pytest.mark.parametrize(
    "label", ("はじめに", "結論", "比較方法", "設置", "手入れ", "確認結果")
)
def test_unnumbered_section_labels_do_not_exempt_appended_assertions(
    label: str,
) -> None:
    assert owner.NAVIGATION_EXEMPTION_RE.fullmatch(label)
    assert not owner.NAVIGATION_EXEMPTION_RE.fullmatch(label + "なら購入可能です")
    assert not owner.NAVIGATION_EXEMPTION_RE.fullmatch(label + "は自動ゴミ収集に対応")


def test_source_refresh_can_acquire_after_expiry_but_normal_checks_still_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import build_st1704_self_hosted_editorial_manifest as manifest

    sales = json.loads((ROOT / owner.SALES_STATE_RELATIVE).read_text())
    observed = datetime.fromisoformat(sales["checked_at_utc"])

    class ExpiredClock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return (observed + timedelta(days=2)).astimezone(tz)

    monkeypatch.setattr(owner, "datetime", ExpiredClock)
    before = (ROOT / owner.SALES_STATE_RELATIVE).read_bytes()
    raw = manifest.build_manifest(for_source_refresh=True)
    document = json.loads(raw)
    assert document["publication_authority"] == "NONE"
    assert document["external_action_authority"] == "NONE"
    assert (ROOT / owner.SALES_STATE_RELATIVE).read_bytes() == before
    with pytest.raises(owner.CoverageFailure, match="snapshot is stale"):
        owner.validate_repository(ROOT)
    with pytest.raises(owner.CoverageFailure, match="snapshot is stale"):
        manifest.build_manifest()
    owner.validate_repository(ROOT, require_fresh_sales_state=False)
    assert manifest.build_manifest(development=True) == raw
    invalid_ledger = _ledger()
    invalid_ledger["article_ids"] = []
    with pytest.raises(owner.CoverageFailure, match="article set/order"):
        owner.validate_repository(ROOT, invalid_ledger, require_fresh_sales_state=False)


def test_source_refresh_still_rejects_tampered_sales_evidence(tmp_path: Path) -> None:
    root = _copy_repository_inputs(tmp_path)
    path = root / owner.SALES_STATE_RELATIVE
    sales = json.loads(path.read_text())
    sales["products"][0]["basis"] += " tampered"
    _write_json(path, sales)
    with pytest.raises(owner.CoverageFailure, match="not the reviewed capture"):
        owner.validate_source_refresh_inputs(root)
    with pytest.raises(owner.CoverageFailure, match="not the reviewed capture"):
        owner.validate_repository(root, require_fresh_sales_state=False)


def test_source_refresh_still_rejects_future_sales_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sales = json.loads((ROOT / owner.SALES_STATE_RELATIVE).read_text())
    observed = datetime.fromisoformat(sales["checked_at_utc"])

    class BeforeCaptureClock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return (observed - timedelta(hours=1)).astimezone(tz)

    monkeypatch.setattr(owner, "datetime", BeforeCaptureClock)
    with pytest.raises(owner.CoverageFailure, match="in the future"):
        owner.validate_source_refresh_inputs(ROOT)
    with pytest.raises(owner.CoverageFailure, match="in the future"):
        owner.validate_repository(ROOT, require_fresh_sales_state=False)


def test_reader_inventory_includes_current_channels_and_extracts_image_alt() -> None:
    document = _ledger()
    channels = {
        unit["channel"] for article in _articles(document) for unit in _units(article)
    }
    assert {
        "VISIBLE_TEXT",
        "ATTRIBUTE_ARIA_LABEL",
        "WORDPRESS_TITLE",
        "WORDPRESS_EXCERPT",
    } <= channels
    # Product images remain fail-closed in the current fixture, so the tracked
    # inventory must not fabricate alt units for images that are not present.
    assert "ATTRIBUTE_ALT" not in channels
    synthetic = owner.extract_reader_units(
        "synthetic-alt",
        '<div class="raos-editorial-v2"><img alt="商品ではない比較図"></div>'.encode(),
    )
    assert any(
        unit.channel == "ATTRIBUTE_ALT" and unit.text == "商品ではない比較図"
        for unit in synthetic
    )
    for article in _articles(document):
        article_id = cast(str, article["article_id"])
        model = owner._load_repository_model(ROOT)
        extracted = owner._final_reader_units(
            article_id,
            model.articles[article_id],
            (ROOT / cast(str, article["content_ref"])).read_bytes(),
            model.product_aliases[article_id],
        )
        assert [unit.unit_id for unit in extracted] == [
            unit["unit_id"] for unit in _units(article)
        ]


def test_skeleton_is_print_only_and_never_auto_accepts_current_units() -> None:
    ledger_path = ROOT / owner.LEDGER_RELATIVE
    before = ledger_path.read_bytes()
    skeleton = json.loads(owner.build_skeleton(ROOT))
    assert ledger_path.read_bytes() == before
    assert all(
        unit["kind"] == "UNCLASSIFIED"
        for article in _articles(skeleton)
        for unit in _units(article)
    )
    assert all(
        unit["claim_ids"] == [] and unit["exemption_code"] is None
        for article in _articles(skeleton)
        for unit in _units(article)
    )


def test_same_count_text_replacement_and_accessibility_tamper_are_detected(
    tmp_path: Path,
) -> None:
    for channel in ("VISIBLE_TEXT", "ATTRIBUTE_ARIA_LABEL"):
        root = _copy_repository_inputs(tmp_path / channel.casefold())
        ledger = json.loads((root / owner.LEDGER_RELATIVE).read_text(encoding="utf-8"))
        subject: tuple[dict[str, object], dict[str, object]] | None = None
        for article in _articles(ledger):
            for unit in _units(article):
                if unit["channel"] == channel:
                    subject = article, unit
                    break
            if subject is not None:
                break
        assert subject is not None
        article, unit = subject
        content_path = root / cast(str, article["content_ref"])
        original = content_path.read_text(encoding="utf-8")
        text = cast(str, unit["text"])
        replacement = ("改" if text[0] != "改" else "変") + text[1:]
        assert len(replacement) == len(text)
        assert text in original
        content_path.write_text(
            original.replace(text, replacement, 1), encoding="utf-8"
        )
        with pytest.raises(owner.CoverageFailure, match="reader-unit digest drift"):
            owner.validate_repository(root)


def test_ledger_cannot_add_a_post_or_reference_another_packet_claim() -> None:
    document = _ledger()
    new_post = deepcopy(document)
    cast(list[str], new_post["article_ids"])[-1] = "new-wordpress-post"
    with pytest.raises(owner.CoverageFailure, match="new posts are forbidden"):
        owner.validate_repository(ROOT, new_post)

    escaped = deepcopy(document)
    source = _first_unit(escaped, kind="VERIFIABLE")
    source["claim_ids"] = ["CLM-PORTFOLIO-DISH-SOLOTA-NP-TML1-REFERENCE"]
    source["assertion_tokens"] = []
    with pytest.raises(owner.CoverageFailure, match="outside its packet"):
        owner.validate_repository(ROOT, escaped)


def test_fact_like_unit_cannot_be_relabelled_non_claim_or_drop_assertions() -> None:
    document = _ledger()
    relabelled = deepcopy(document)
    unit = _first_unit(relabelled, kind="VERIFIABLE", assertions=True)
    unit.update(
        kind="NON_CLAIM",
        claim_ids=[],
        evidence_bindings=[],
        assertion_tokens=[],
        exemption_code="ACCESSIBILITY_OR_DECORATION",
    )
    with pytest.raises(owner.CoverageFailure, match="NON_CLAIM"):
        owner.validate_repository(ROOT, relabelled)

    method_loophole = deepcopy(document)
    unit = _first_unit(method_loophole, kind="VERIFIABLE", assertions=True)
    unit.update(
        kind="NON_CLAIM",
        claim_ids=[],
        evidence_bindings=[],
        assertion_tokens=[],
        exemption_code="EDITORIAL_METHOD",
    )
    with pytest.raises(owner.CoverageFailure, match="NON_CLAIM"):
        owner.validate_repository(ROOT, method_loophole)

    missing = deepcopy(document)
    unit = _first_unit(missing, assertions=True)
    cast(list[object], unit["assertion_tokens"]).pop()
    with pytest.raises(owner.CoverageFailure, match="undeclared assertion token"):
        owner.validate_repository(ROOT, missing)

    terse = deepcopy(document)
    unit = next(
        unit
        for article in _articles(terse)
        for unit in _units(article)
        if owner.TERSE_FACT_STATUS_RE.search(cast(str, unit["text"]))
        and unit["kind"] in {"VERIFIABLE", "EDITORIAL_INFERENCE"}
    )
    unit.update(
        kind="NON_CLAIM",
        claim_ids=[],
        evidence_bindings=[],
        assertion_tokens=[],
        exemption_code="READER_SCOPE_OR_GUIDANCE",
    )
    with pytest.raises(
        owner.CoverageFailure,
        match="comparison value cannot be NON_CLAIM|decision-critical assertion",
    ):
        owner.validate_repository(ROOT, terse)


def test_assertion_token_must_be_in_reader_text_and_registered_claim_semantics() -> (
    None
):
    document = _ledger()
    absent = deepcopy(document)
    unit = _first_unit(absent, kind="VERIFIABLE")
    claim_id = cast(list[str], unit["claim_ids"])[0]
    cast(list[dict[str, object]], unit["assertion_tokens"]).append(
        {
            "assertion_text": "999999Wh",
            "occurrence_index": 0,
            "claim_ids": [claim_id],
            "evidence_binding_ids": [],
        }
    )
    with pytest.raises(owner.CoverageFailure, match="absent from reader text"):
        owner.validate_repository(ROOT, absent)

    unsupported = deepcopy(document)
    unit = _first_unit(unsupported, kind="VERIFIABLE", assertions=True)
    assertion = cast(list[dict[str, object]], unit["assertion_tokens"])[0]
    text = cast(str, unit["text"])
    token = cast(str, assertion["assertion_text"])
    assertion["assertion_text"] = text[: min(12, len(text))]
    if cast(str, assertion["assertion_text"]) == token:
        assertion["assertion_text"] = text
    with pytest.raises(owner.CoverageFailure, match="unsupported by claims"):
        owner.validate_repository(ROOT, unsupported)


def test_relative_comparison_requires_inference_and_unknown_is_comparison_only() -> (
    None
):
    document = _ledger()
    relative = deepcopy(document)
    unit = next(
        unit
        for article in _articles(relative)
        for unit in _units(article)
        if owner.RELATIVE_ASSERTION_RE.search(cast(str, unit["text"]))
        and unit["kind"] == "EDITORIAL_INFERENCE"
        and any(claim_id for claim_id in cast(list[str], unit["claim_ids"]) if claim_id)
    )
    article = next(
        article for article in _articles(relative) if unit in _units(article)
    )
    model = owner._load_repository_model(ROOT)
    verifiable = [
        claim_id
        for claim_id in cast(list[str], unit["claim_ids"])
        if model.claims[cast(str, article["article_id"])][claim_id]["classification"]
        == "MAJOR_VERIFIABLE"
    ]
    assert verifiable
    unit["kind"] = "VERIFIABLE"
    unit["claim_ids"] = verifiable
    for assertion in cast(list[dict[str, object]], unit["assertion_tokens"]):
        assertion["claim_ids"] = [
            claim_id
            for claim_id in cast(list[str], assertion["claim_ids"])
            if claim_id in verifiable
        ] or [verifiable[0]]
    with pytest.raises(owner.CoverageFailure, match="relative comparison lacks"):
        owner.validate_repository(ROOT, relative)

    unknown = deepcopy(document)
    decision = _first_unit(unknown, context="DECISION")
    decision.update(
        kind="UNKNOWN", claim_ids=[], assertion_tokens=[], exemption_code=None
    )
    decision["evidence_bindings"] = []
    with pytest.raises(owner.CoverageFailure, match="UNKNOWN is allowed only"):
        owner.validate_repository(ROOT, unknown)


def test_missing_claim_locator_and_evidence_outside_packet_fail_closed(
    tmp_path: Path,
) -> None:
    root = _copy_repository_inputs(tmp_path / "locator")
    locator_path = root / owner.LOCATOR_RELATIVE
    locator = json.loads(locator_path.read_text(encoding="utf-8"))
    locator["sources"][0]["locators"] = []
    _write_json(locator_path, locator)
    with pytest.raises(owner.CoverageFailure, match="claim has no locator"):
        owner.validate_repository(root)
    root = _copy_repository_inputs(tmp_path / "empty-fragments")
    locator_path = root / owner.LOCATOR_RELATIVE
    locator = json.loads(locator_path.read_text(encoding="utf-8"))
    locator["sources"][0]["locators"][0]["exact_utf8_fragments"] = []
    _write_json(locator_path, locator)
    with pytest.raises(owner.CoverageFailure, match="no exact fragments"):
        owner.validate_repository(root)

    root = _copy_repository_inputs(tmp_path / "evidence")
    registry_path = root / owner.REGISTRY_RELATIVE
    locator_path = root / owner.LOCATOR_RELATIVE
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    packet = registry["source_packets"][0]
    packet["claims"][0]["evidence_refs"] = ["SRC-NOT-IN-PACKET"]
    packet["fact_packet_sha256"] = owner._packet_hash(packet)
    _write_json(registry_path, registry)
    locator = json.loads(locator_path.read_text(encoding="utf-8"))
    locator["source_registry_sha256"] = owner._canonical_sha256(registry)
    _write_json(locator_path, locator)
    with pytest.raises(owner.CoverageFailure, match="outside packet"):
        owner.validate_repository(root)


def test_source_capture_hash_binds_market_lifecycle_and_negative_attestation() -> None:
    source = {
        "source_ref": "SRC-OFFICIAL",
        "authority": "MANUFACTURER",
        "source_type": "PRODUCT_PAGE",
        "title": "Official product page",
        "url": "https://example.test/product",
        "retrieved_on": "2026-08-31",
    }
    claim = {
        "claim_id": "CLM-EXTERNAL-CANDIDATE-EXCLUDED",
        "classification": "EDITORIAL_INFERENCE",
        "statement": "読者向け画面の販売状態を優先して候補から除外した。",
        "status": "INFERENCE_FROM_BOUND_OFFICIAL_FACTS",
        "subject_product_ids": [],
        "dimensions": [
            {
                "subject": "BODY",
                "width_cm": 24.5,
                "depth_cm": 24.5,
                "height_cm": 9.2,
            },
            {
                "subject": "STATION",
                "width_cm": 21.2,
                "depth_cm": 17.8,
                "height_cm": 28.5,
            },
        ],
        "market_candidate_id": "EXT-CANDIDATE",
        "market_disposition": "EXCLUDED",
        "official_url": "https://example.test/product",
        "exact_model": "Candidate 1",
        "exact_variant_scope": "C1-JP",
        "evaluated_at": "2026-08-31",
        "model_lifecycle": "SOLD_OUT",
        "variant_lifecycle": "SOLD_OUT",
        "reader_visible_lifecycle": "SOLD_OUT",
        "embedded_structured_lifecycle": "AVAILABLE",
        "lifecycle_evidence_state": "CONFLICT",
        "effective_lifecycle": "SOLD_OUT",
        "negative_claim_evidence": {
            "mode": "EXPLICIT_OFFICIAL_TEXT",
            "source_refs": ["SRC-OFFICIAL"],
            "page_omission_is_not_evidence": True,
        },
    }
    baseline = owner._source_capture_hash(source, [claim])
    changed_dimension = deepcopy(claim)
    cast(list[dict[str, object]], changed_dimension["dimensions"])[0]["width_cm"] = 24.6
    assert owner._source_capture_hash(source, [changed_dimension]) != baseline

    reordered_dimensions = deepcopy(claim)
    cast(list[dict[str, object]], reordered_dimensions["dimensions"]).reverse()
    assert owner._source_capture_hash(source, [reordered_dimensions]) != baseline

    for field, replacement in {
        "model_lifecycle": "AVAILABLE",
        "variant_lifecycle": "AVAILABLE",
        "reader_visible_lifecycle": "AVAILABLE",
        "embedded_structured_lifecycle": "SOLD_OUT",
        "lifecycle_evidence_state": "CONSISTENT",
        "effective_lifecycle": "AVAILABLE",
        "negative_claim_evidence": {
            "mode": "OFFICIAL_PRODUCT_MANUAL",
            "source_refs": ["SRC-OFFICIAL"],
            "page_omission_is_not_evidence": True,
        },
    }.items():
        tampered = deepcopy(claim)
        tampered[field] = replacement
        assert owner._source_capture_hash(source, [tampered]) != baseline

    reference_claim = {
        "claim_id": "CLM-PORTFOLIO-REFERENCE",
        "classification": "EDITORIAL_INFERENCE",
        "statement": "別記事の比較へ案内する。",
        "status": "INFERENCE_FROM_BOUND_OFFICIAL_FACTS",
        "subject_product_ids": ["PRD-REFERENCE"],
        "portfolio_candidate_disposition": "REFERENCE_ONLY",
        "portfolio_candidate_reason": "別記事の比較へ案内する。",
        "route_article_id": "route-article",
    }
    reference_baseline = owner._source_capture_hash(source, [reference_claim])
    for field, replacement in {
        "portfolio_candidate_disposition": "SELECTED",
        "portfolio_candidate_reason": "異なる理由",
        "route_article_id": "different-route",
    }.items():
        tampered = deepcopy(reference_claim)
        tampered[field] = replacement
        assert owner._source_capture_hash(source, [tampered]) != reference_baseline


def test_central_recall_requirements_and_embedded_sales_state_remain_fail_closed(
    tmp_path: Path,
) -> None:
    model = owner._load_repository_model(ROOT)
    recall_gates = [
        claim["product_specific_recall_query_gate"]
        for packet in model.claims.values()
        for claim in packet.values()
        if "product_specific_recall_query_gate" in claim
    ]
    # A10 is now a lifecycle-only route with no selected product placement;
    # the other nine articles each retain one selected-product recall gate.
    assert len(recall_gates) == sum(
        bool(model.articles[article_id]["product_ids"])
        for article_id in owner.ARTICLE_IDS
    )
    assert model.articles["solota-vs-rakua-mini-plus"]["product_ids"] == []
    assert all(
        gate["schema"] == "PRODUCT_SPECIFIC_RECALL_QUERY_REQUIREMENT_V2"
        and gate["receipt_document_ref"]
        == owner.PRODUCT_SAFETY_RECEIPT_RELATIVE.as_posix()
        and gate["receipt_document_schema"] == owner.PRODUCT_SAFETY_RECEIPT_SCHEMA
        and gate["required_authority_kinds"]
        == owner.PRODUCT_SAFETY_REQUIRED_AUTHORITIES
        for gate in recall_gates
    )
    receipt_document = json.loads(
        (ROOT / owner.PRODUCT_SAFETY_RECEIPT_RELATIVE).read_text(encoding="utf-8")
    )
    assert receipt_document["receipts"] == []

    embedded = [
        claim["manufacturer_sales_state"]
        for packet in model.claims.values()
        for claim in packet.values()
        if "manufacturer_sales_state" in claim
    ]
    assert embedded
    blocked = [value for value in embedded if "recommendation_gate" in value]
    selected = [value for value in embedded if "selection_gate" in value]
    assert blocked and selected
    assert all(value["status"] == "OUT_OF_STOCK" for value in blocked)
    assert all(value["reader_visible_label"] == "在庫切れ" for value in blocked)
    assert all(value["recommendation_gate"] == "BLOCKED" for value in blocked)
    assert all(value["cta_gate"] == "BLOCKED" for value in blocked)
    assert all(value["status"] == "AVAILABLE" for value in selected)
    assert all(value["selection_gate"] == "ELIGIBLE" for value in selected)
    assert all(
        value["variant_caveat"]
        == model.sales_states[cast(str, value["product_id"])]["variant_caveat"]
        for value in selected
    )
    assert any(value["variant_caveat"] is None for value in selected)
    assert any(type(value["variant_caveat"]) is dict for value in selected)

    def rewrite_registry(
        root: Path, mutate: Callable[[dict[str, object]], None]
    ) -> None:
        registry_path = root / owner.REGISTRY_RELATIVE
        locator_path = root / owner.LOCATOR_RELATIVE
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        mutate(registry)
        for packet in registry["source_packets"]:
            packet["fact_packet_sha256"] = owner._packet_hash(packet)
        claims_by_source: dict[str, list[dict[str, object]]] = {}
        for packet in registry["source_packets"]:
            for claim in packet["claims"]:
                for source_ref in claim["evidence_refs"]:
                    claims_by_source.setdefault(source_ref, []).append(claim)
        for source in registry["sources"]:
            source_ref = cast(str, source["source_ref"])
            source["immutable_capture_sha256"] = owner._source_capture_hash(
                source, claims_by_source.get(source_ref, [])
            )
        _write_json(registry_path, registry)
        locator = json.loads(locator_path.read_text(encoding="utf-8"))
        locator["source_registry_sha256"] = owner._canonical_sha256(registry)
        _write_json(locator_path, locator)

    root = _copy_repository_inputs(tmp_path / "fabricated-recall")

    def fabricate_receipt(registry: dict[str, object]) -> None:
        packet = cast(list[dict[str, object]], registry["source_packets"])[0]
        claim = next(
            value
            for value in cast(list[dict[str, object]], packet["claims"])
            if "product_specific_recall_query_gate" in value
        )
        gate = cast(dict[str, object], claim["product_specific_recall_query_gate"])
        gate["receipts"] = [{"result": "NONE_FOUND"}]
        gate["status"] = "COMPLETE"

    rewrite_registry(root, fabricate_receipt)
    with pytest.raises(
        owner.CoverageFailure,
        match="unexpected fields in product-specific recall gate",
    ):
        owner._load_repository_model(root)

    root = _copy_repository_inputs(tmp_path / "sales-polarity")

    def invert_sales(registry: dict[str, object]) -> None:
        claim = next(
            claim
            for packet in cast(list[dict[str, object]], registry["source_packets"])
            for claim in cast(list[dict[str, object]], packet["claims"])
            if "selection_gate"
            in cast(dict[str, object], claim.get("manufacturer_sales_state", {}))
        )
        cast(dict[str, object], claim["manufacturer_sales_state"])["checked_at"] = (
            "2026-08-31T12:50:26Z"
        )

    rewrite_registry(root, invert_sales)
    with pytest.raises(
        owner.CoverageFailure, match="embedded manufacturer sales state drift"
    ):
        owner._load_repository_model(root)


def test_subjectless_manufacturer_claim_is_limited_to_external_candidates(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        owner.CoverageFailure, match="manufacturer product claim has no subject"
    ):
        owner._validate_manufacturer_claim_subject_boundary(
            claim_id="CLM-TAMPER-NORMAL-MANUFACTURER-CLAIM",
            claim_subjects=(),
            has_manufacturer_evidence=True,
        )

    for claim_id in (
        "CLM-TAMPER-NAMED-CANDIDATE-EXCLUDED",
        "CLM-TAMPER-NAMED-CANDIDATE-REFERENCE",
    ):
        owner._validate_manufacturer_claim_subject_boundary(
            claim_id=claim_id,
            claim_subjects=(),
            has_manufacturer_evidence=True,
        )
        assert owner._is_external_candidate_claim(claim_id, ())

    assert not owner._is_external_candidate_claim(
        "CLM-TAMPER-NORMAL-MANUFACTURER-CLAIM", ()
    )
    assert not owner._is_external_candidate_claim(
        "CLM-TAMPER-NAMED-CANDIDATE-EXCLUDED", ("PRD-SELECTED",)
    )
    assert owner._external_candidate_token_supported(
        assertion_text="売り切れ",
        claim_id="CLM-TAMPER-NAMED-CANDIDATE-EXCLUDED",
        support="候補製品はメーカー公式ストアで売り切れと表示された。",
        claim_subjects=(),
        dimension_role=None,
        dimension_axis=None,
    )
    assert not owner._external_candidate_token_supported(
        assertion_text="売り切れ",
        claim_id="CLM-TAMPER-NORMAL-MANUFACTURER-CLAIM",
        support="選定製品はメーカー公式ストアで売り切れと表示された。",
        claim_subjects=(),
        dimension_role=None,
        dimension_axis=None,
    )

    model = owner._load_repository_model(ROOT)
    reviewed_external = [
        claim_id
        for article_id in owner.ARTICLE_IDS
        for claim_id, subjects in model.claim_subjects[article_id].items()
        if owner._is_external_candidate_claim(claim_id, subjects)
    ]
    assert reviewed_external

    # Exercise the repository loader, not only the shared predicate. Recompute
    # the normal integrity hashes after removing a selected product subject so
    # the failure must come from the semantic subject boundary itself.
    root = _copy_repository_inputs(tmp_path / "subjectless-selected")
    registry_path = root / owner.REGISTRY_RELATIVE
    locator_path = root / owner.LOCATOR_RELATIVE
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    packet = registry["source_packets"][0]
    selected_claim = next(
        claim for claim in packet["claims"] if claim["subject_product_ids"]
    )
    selected_claim["subject_product_ids"] = []
    packet["fact_packet_sha256"] = owner._packet_hash(packet)

    claims_by_source: dict[str, list[dict[str, object]]] = {}
    for source_packet in registry["source_packets"]:
        for claim in source_packet["claims"]:
            for source_ref in claim["evidence_refs"]:
                claims_by_source.setdefault(source_ref, []).append(claim)
    for source in registry["sources"]:
        source_ref = cast(str, source["source_ref"])
        if source_ref in claims_by_source:
            source["immutable_capture_sha256"] = owner._source_capture_hash(
                source, claims_by_source[source_ref]
            )
    _write_json(registry_path, registry)
    locator = json.loads(locator_path.read_text(encoding="utf-8"))
    locator["source_registry_sha256"] = owner._canonical_sha256(registry)
    _write_json(locator_path, locator)
    with pytest.raises(
        owner.CoverageFailure, match="manufacturer product claim has no subject"
    ):
        owner._load_repository_model(root)


def test_portfolio_reference_claims_are_route_bound_and_reader_owned(
    tmp_path: Path,
) -> None:
    model = owner._load_repository_model(ROOT)
    ledger = _ledger()
    reviewed_references: list[tuple[str, dict[str, object]]] = []
    for article_id in owner.ARTICLE_IDS:
        references = [
            claim
            for claim in model.claims[article_id].values()
            if claim.get("portfolio_candidate_disposition") == "REFERENCE_ONLY"
        ]
        reviewed_references.extend((article_id, claim) for claim in references)
        for claim in references:
            subjects = cast(list[str], claim["subject_product_ids"])
            assert len(subjects) == 1
            reference_product_id = subjects[0]
            selected = set(cast(list[str], model.articles[article_id]["product_ids"]))
            route_article_id = cast(str, claim["route_article_id"])
            route_selected = set(
                cast(list[str], model.articles[route_article_id]["product_ids"])
            )
            assert reference_product_id not in selected
            assert reference_product_id in route_selected
            article_binding = _article(ledger, article_id)
            assert any(
                claim["claim_id"] in cast(list[str], unit["claim_ids"])
                for unit in _units(article_binding)
            )

    assert len(reviewed_references) == 8
    lifecycle_references = [
        claim
        for article_id, claim in reviewed_references
        if article_id == "solota-vs-rakua-mini-plus"
    ]
    assert lifecycle_references == []

    # Integrity hashes are recomputed so this exercises the route semantic,
    # rather than failing early on ordinary generated-file drift.
    root = _copy_repository_inputs(tmp_path / "portfolio-route")
    registry_path = root / owner.REGISTRY_RELATIVE
    locator_path = root / owner.LOCATOR_RELATIVE
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    packet = cast(list[dict[str, object]], registry["source_packets"])[0]
    reference = next(
        claim
        for claim in cast(list[dict[str, object]], packet["claims"])
        if claim.get("portfolio_candidate_disposition") == "REFERENCE_ONLY"
    )
    reference["route_article_id"] = packet["article_id"]
    for source_packet in cast(list[dict[str, object]], registry["source_packets"]):
        source_packet["fact_packet_sha256"] = owner._packet_hash(source_packet)
    claims_by_source: dict[str, list[dict[str, object]]] = {}
    for source_packet in cast(list[dict[str, object]], registry["source_packets"]):
        for claim in cast(list[dict[str, object]], source_packet["claims"]):
            for source_ref in cast(list[str], claim["evidence_refs"]):
                claims_by_source.setdefault(source_ref, []).append(claim)
    for source in cast(list[dict[str, object]], registry["sources"]):
        source_ref = cast(str, source["source_ref"])
        source["immutable_capture_sha256"] = owner._source_capture_hash(
            source, claims_by_source.get(source_ref, [])
        )
    _write_json(registry_path, registry)
    locator = json.loads(locator_path.read_text(encoding="utf-8"))
    locator["source_registry_sha256"] = owner._canonical_sha256(registry)
    _write_json(locator_path, locator)
    with pytest.raises(
        owner.CoverageFailure, match="invalid portfolio candidate route"
    ):
        owner._load_repository_model(root)


def test_reference_heading_owner_does_not_pollute_selected_fallback() -> None:
    selected = "PRD-SELECTED"
    reference = "PRD-REFERENCE"
    aliases = {
        selected: ("Selected One",),
        reference: ("Reference Two",),
    }
    units = owner.extract_reader_units(
        "test-reference-owner",
        (
            '<div class="raos-editorial-v2">'
            "<p>1台を比較します。</p>"
            "<section><h3>Reference Two</h3>"
            "<p><a>関連する比較記事を確認する</a>。別記事で確認できます。</p>"
            "</section></div>"
        ).encode(),
        aliases,
        (selected,),
    )
    generic = next(unit for unit in units if unit.text == "1台を比較します。")
    assert generic.subject_product_ids == (selected,)
    reference_copy = next(
        unit for unit in units if unit.text == "。別記事で確認できます。"
    )
    assert reference_copy.owner_product_id == reference
    assert reference_copy.subject_product_ids == (reference,)

    external = "EXT-FREQUENTER-LIEVE-1-250"
    external_units = owner.extract_reader_units(
        "test-external-owner",
        (
            '<div class="raos-editorial-v2"><section>'
            "<h3>FREQUENTER LIEVE 1-250</h3>"
            "<p>33L・2.7kgのため比較表から外しました。</p>"
            "</section></div>"
        ).encode(),
        {selected: ("Selected One",), external: ("LIEVE 1-250",)},
        (selected,),
    )
    external_heading = next(
        unit for unit in external_units if unit.text == "FREQUENTER LIEVE 1-250"
    )
    external_reason = next(
        unit for unit in external_units if unit.text.startswith("33L")
    )
    for unit in (external_heading, external_reason):
        assert unit.owner_product_id == external
        assert unit.subject_product_ids == ()


def test_a07_two_expandable_models_excludes_the_reference_only_alias() -> None:
    c_lite = "PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549"
    applite = "PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002"
    aliases = {
        "PRD-PROTECA-AEROFLEX-DX2-01521": ("Aeroflex",),
        "PRD-RIMOWA-ESSENTIAL-LITE-CABIN-82353171": ("RIMOWA",),
        applite: ("APPLITE",),
        c_lite: ("C-Lite",),
        "PRD-PROTECA-TRI-AIR-01541": ("Tri-Air",),
    }
    assert owner._matching_product_group_ids(
        "拡張できる2モデルは、通常時と拡張時を分けて判断します。",
        aliases,
    ) == (c_lite, applite)


def test_external_candidate_owner_cannot_borrow_a_neighboring_exclusion() -> None:
    text = "比較表から外しました。"
    unit = owner.ReaderUnit(
        unit_id="RU-external-owner-boundary",
        locator="section[1]/p[1]::text",
        channel="VISIBLE_TEXT",
        text=text,
        text_sha256=owner._text_sha256(text),
        context="GENERAL",
        subject_product_ids=(),
        owner_product_id="EXT-CANDIDATE-A",
        dimension_role=None,
        dimension_axis=None,
        sequence=1,
    )
    claim_id = "CLM-NEIGHBOR-CANDIDATE-EXCLUDED"
    claim = {
        "claim_id": claim_id,
        "classification": "EDITORIAL_INFERENCE",
        "status": "INFERENCE_FROM_BOUND_OFFICIAL_FACTS",
        "statement": text,
        "subject_product_ids": [],
        "market_candidate_id": "EXT-CANDIDATE-B",
    }
    binding = {
        "unit_id": unit.unit_id,
        "locator": unit.locator,
        "channel": unit.channel,
        "text": unit.text,
        "text_sha256": unit.text_sha256,
        "context": unit.context,
        "subject_product_ids": [],
        "owner_product_id": unit.owner_product_id,
        "dimension_role": None,
        "dimension_axis": None,
        "kind": "EDITORIAL_INFERENCE",
        "claim_ids": [claim_id],
        "evidence_bindings": [],
        "assertion_tokens": [],
        "exemption_code": None,
        "decision_gate": None,
    }
    with pytest.raises(
        owner.CoverageFailure,
        match="external candidate claim does not match reader-unit owner",
    ):
        owner._validate_unit_binding(
            unit=unit,
            raw_binding=binding,
            packet_claims={claim_id: claim},
            support_by_claim={claim_id: text},
            claim_subjects={claim_id: ()},
            product_aliases={
                "EXT-CANDIDATE-A": ("Candidate A",),
                "EXT-CANDIDATE-B": ("Candidate B",),
            },
            sales_states={},
            allowed_product_ids=set(),
        )

    # A single sentence may explicitly compare two external exclusions.  The
    # structural owner remains the first candidate, but the second claim is
    # admissible only because its exact article-local alias is visible too.
    second_claim_id = "CLM-CANDIDATE-A-EXCLUDED"
    second_claim = {
        **claim,
        "claim_id": second_claim_id,
        "market_candidate_id": "EXT-CANDIDATE-A",
    }
    mixed_text = "Candidate AとCandidate Bを比較表から外しました。"
    mixed_unit = deepcopy(unit)
    object.__setattr__(mixed_unit, "text", mixed_text)
    object.__setattr__(mixed_unit, "text_sha256", owner._text_sha256(mixed_text))
    mixed_binding = deepcopy(binding)
    mixed_binding.update(
        text=mixed_text,
        text_sha256=owner._text_sha256(mixed_text),
        claim_ids=[second_claim_id, claim_id],
    )
    owner._validate_unit_binding(
        unit=mixed_unit,
        raw_binding=mixed_binding,
        packet_claims={second_claim_id: second_claim, claim_id: claim},
        support_by_claim={second_claim_id: mixed_text, claim_id: mixed_text},
        claim_subjects={second_claim_id: (), claim_id: ()},
        product_aliases={
            "EXT-CANDIDATE-A": ("Candidate A",),
            "EXT-CANDIDATE-B": ("Candidate B",),
        },
        sales_states={},
        allowed_product_ids=set(),
    )


def test_external_known_fact_inherits_only_its_unique_reviewed_alias() -> None:
    aliases = {
        "EXT-CANDIDATE-A": ("Candidate A",),
        "EXT-CANDIDATE-B": ("Candidate B",),
    }
    known_claim = {
        "claim_id": "CLM-CANDIDATE-A-KNOWN-SPECS-REFERENCE",
        "classification": "MAJOR_VERIFIABLE",
        "status": "VERIFIED_FROM_BOUND_OFFICIAL_SOURCE",
        "statement": "Candidate Aの容量は36Lです。",
        "subject_product_ids": [],
    }
    assert owner._external_claim_matches_owner(
        claim=known_claim,
        support=cast(str, known_claim["statement"]),
        external_owner="EXT-CANDIDATE-A",
        product_aliases=aliases,
    )
    assert not owner._external_claim_matches_owner(
        claim=known_claim,
        support="Candidate Bの容量は36Lです。",
        external_owner="EXT-CANDIDATE-A",
        product_aliases=aliases,
    )
    assert not owner._external_claim_matches_owner(
        claim=known_claim,
        support="候補の容量は36Lです。",
        external_owner="EXT-CANDIDATE-A",
        product_aliases=aliases,
    )
    assert not owner._external_claim_matches_owner(
        claim=known_claim,
        support="Candidate AとCandidate Bの容量は36Lです。",
        external_owner="EXT-CANDIDATE-A",
        product_aliases=aliases,
    )


def test_fact_packet_revision_requires_explicit_ledger_review() -> None:
    document = _ledger()
    tampered = deepcopy(document)
    _articles(tampered)[0]["fact_packet_sha256"] = "0" * 64
    with pytest.raises(owner.CoverageFailure, match="source packet changed"):
        owner.validate_repository(ROOT, tampered)


def test_legacy_ast_and_static_html_authoring_inputs_are_bound(tmp_path: Path) -> None:
    document = _ledger()
    inputs = [
        cast(dict[str, str], article["authoring_input"])
        for article in _articles(document)
    ]
    assert [value["kind"] for value in inputs[:5]] == ["LEGACY_AST_ARTICLE"] * 5
    assert [value["kind"] for value in inputs[5:]] == ["STATIC_HTML_FIXTURE"] * 5

    root = _copy_repository_inputs(tmp_path / "legacy-ast")
    content_path = root / owner.LEGACY_CONTENT_RELATIVE
    content = json.loads(content_path.read_text(encoding="utf-8"))
    content["articles"][0]["title"] += " 改変"
    _write_json(content_path, content)
    with pytest.raises(owner.CoverageFailure, match="authoring input changed"):
        owner.validate_repository(root)


@pytest.mark.parametrize(
    ("product_id", "expected_scope"),
    (
        ("PRD-PROTECA-TRI-AIR-01541", "MODEL"),
        ("PRD-ACE-DIFFERENCE-05721", "VARIANT"),
    ),
)
def test_reader_sales_state_is_bound_to_product_snapshot_hash_and_locator(
    tmp_path: Path,
    product_id: str,
    expected_scope: str,
) -> None:
    model = owner._load_repository_model(ROOT)
    article_id = owner.ARTICLE_IDS[0]
    assert product_id in cast(list[str], model.articles[article_id]["product_ids"])
    state = model.sales_states[product_id]
    assert state["state"] == "AVAILABLE"
    assert state["availability_scope"] == expected_scope
    text = "メーカー公式ストアで販売中です。"
    unit = owner.ReaderUnit(
        unit_id="RU-selected-sales-state",
        locator="section[1]/p[1]::text",
        channel="VISIBLE_TEXT",
        text=text,
        text_sha256=owner._text_sha256(text),
        context="GENERAL",
        subject_product_ids=(product_id,),
        owner_product_id=product_id,
        dimension_role=None,
        dimension_axis=None,
        sequence=1,
    )
    evidence = {
        "binding_id": f"MSS-{product_id}",
        "evidence_kind": "MANUFACTURER_SALES_STATE",
        "product_id": product_id,
        **{
            key: state[key]
            for key in (
                "state",
                "availability_scope",
                "variant_caveat",
                "checked_at_utc",
                "official_url",
                "structured_snapshot_sha256",
                "locator",
            )
        },
    }
    binding = {
        "unit_id": unit.unit_id,
        "locator": unit.locator,
        "channel": unit.channel,
        "text": unit.text,
        "text_sha256": unit.text_sha256,
        "context": unit.context,
        "subject_product_ids": [product_id],
        "owner_product_id": product_id,
        "dimension_role": None,
        "dimension_axis": None,
        "kind": "VERIFIABLE",
        "claim_ids": [],
        "evidence_bindings": [evidence],
        "assertion_tokens": [
            {
                "assertion_text": "販売中",
                "occurrence_index": 0,
                "claim_ids": [],
                "evidence_binding_ids": [f"MSS-{product_id}"],
            }
        ],
        "exemption_code": None,
        "decision_gate": None,
    }
    common = {
        "unit": unit,
        "packet_claims": {},
        "support_by_claim": {},
        "claim_subjects": {},
        "product_aliases": model.product_aliases[article_id],
        "sales_states": model.sales_states,
        "allowed_product_ids": set(
            cast(list[str], model.articles[article_id]["product_ids"])
        ),
    }
    owner._validate_unit_binding(raw_binding=binding, **common)

    tampered_binding = deepcopy(binding)
    cast(list[dict[str, object]], tampered_binding["evidence_bindings"])[0][
        "structured_snapshot_sha256"
    ] = "0" * 64
    with pytest.raises(owner.CoverageFailure, match="snapshot_sha256 drift"):
        owner._validate_unit_binding(raw_binding=tampered_binding, **common)

    root = _copy_repository_inputs(tmp_path / "sales-state")
    sales_path = root / owner.SALES_STATE_RELATIVE
    sales = json.loads(sales_path.read_text(encoding="utf-8"))
    sales["products"][0]["basis"] += " 改変"
    sales["products"][0]["structured_snapshot_sha256"] = owner._canonical_sha256(
        {field: sales["products"][0][field] for field in owner.SALES_STATE_HASH_FIELDS}
    )
    _write_json(sales_path, sales)
    with pytest.raises(owner.CoverageFailure, match="not the reviewed capture"):
        owner.validate_repository(root)


def test_sales_state_rejects_stale_wrong_origin_and_unhashed_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy_repository_inputs(tmp_path / "stale")
    sales_path = root / owner.SALES_STATE_RELATIVE
    sales = json.loads(sales_path.read_text(encoding="utf-8"))
    sales["checked_at_utc"] = "2000-01-01T00:00:00Z"
    for state in sales["products"]:
        state["checked_at_utc"] = sales["checked_at_utc"]
        state["structured_snapshot_sha256"] = owner._canonical_sha256(
            {field: state[field] for field in owner.SALES_STATE_HASH_FIELDS}
        )
    _write_sales_document(root, sales, monkeypatch)
    with pytest.raises(owner.CoverageFailure, match="snapshot is stale"):
        owner.validate_repository(root)

    root = _copy_repository_inputs(tmp_path / "wrong-origin")
    sales_path = root / owner.SALES_STATE_RELATIVE
    sales = json.loads(sales_path.read_text(encoding="utf-8"))
    sales["products"][0]["status_evidence_urls"] = [
        "https://attacker.invalid/available"
    ]
    sales["products"][0]["structured_snapshot_sha256"] = owner._canonical_sha256(
        {field: sales["products"][0][field] for field in owner.SALES_STATE_HASH_FIELDS}
    )
    _write_sales_document(root, sales, monkeypatch)
    with pytest.raises(owner.CoverageFailure, match="evidence origin is unregistered"):
        owner.validate_repository(root)

    root = _copy_repository_inputs(tmp_path / "row-hash")
    sales_path = root / owner.SALES_STATE_RELATIVE
    sales = json.loads(sales_path.read_text(encoding="utf-8"))
    sales["products"][0]["basis"] += " 改変"
    _write_sales_document(root, sales, monkeypatch)
    with pytest.raises(owner.CoverageFailure, match="snapshot hash mismatch"):
        owner.validate_repository(root)


def test_sales_state_uses_fresh_full_inventory_and_variant_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = owner._load_repository_model(ROOT)
    selected_products = {
        product_id
        for article in model.articles.values()
        for product_id in cast(list[str], article["product_ids"])
    }
    assert len(selected_products) == 33
    assert set(model.sales_states) == selected_products
    assert {state["state"] for state in model.sales_states.values()} == {"AVAILABLE"}
    state = model.sales_states["PRD-EUFY-AUTOEMPTY-C10-T2292"]
    assert state["variant_caveat"]["code"] == "OTHER_COLOR_NOT_ATTESTED"
    # A model-level row with a variant caveat does not support broad reader
    # prose such as "販売中". The exact black-variant observation is carried
    # separately by its source-packet field and must preserve that scope.
    assert not owner._sales_token_supported("販売中", state)
    difference = model.sales_states["PRD-ACE-DIFFERENCE-05721"]
    assert difference["availability_scope"] == "VARIANT"
    assert difference["variant_caveat"] is None
    assert owner._sales_token_supported("販売中", difference)

    document = json.loads(
        (ROOT / owner.SALES_STATE_RELATIVE).read_text(encoding="utf-8")
    )
    row_times = [row["checked_at_utc"] for row in document["products"]]
    assert min(row_times) == document["checked_at_utc"]
    assert max(row_times) >= document["checked_at_utc"]
    assert (
        owner.datetime.fromisoformat(max(row_times).removesuffix("Z") + "+00:00")
        - owner.datetime.fromisoformat(min(row_times).removesuffix("Z") + "+00:00")
    ) <= timedelta(seconds=owner.SALES_STATE_MAX_AGE_SECONDS)

    # Advancing the document timestamp past an older product receipt must not
    # silently make that older row part of the newer observation window.
    root = _copy_repository_inputs(tmp_path / "document-minimum")
    sales_path = root / owner.SALES_STATE_RELATIVE
    sales = json.loads(sales_path.read_text(encoding="utf-8"))
    observed = owner.datetime.fromisoformat(
        sales["checked_at_utc"].removesuffix("Z") + "+00:00"
    )
    sales["checked_at_utc"] = (observed + timedelta(seconds=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    _write_sales_document(root, sales, monkeypatch)
    with pytest.raises(owner.CoverageFailure, match="row timestamp is invalid"):
        owner._load_repository_model(root)


def test_sales_state_subject_resolution_is_occurrence_and_coordination_scoped() -> None:
    aliases = {
        "PRD-A": ("製品A",),
        "PRD-B": ("製品B",),
    }
    repeated = "製品Aは在庫切れです。製品Bも在庫切れです。"
    assert owner._local_assertion_subjects(
        repeated,
        "在庫切れ",
        aliases,
        ("PRD-A", "PRD-B"),
        occurrence_index=0,
    ) == ("PRD-A",)
    assert owner._local_assertion_subjects(
        repeated,
        "在庫切れ",
        aliases,
        ("PRD-A", "PRD-B"),
        occurrence_index=1,
    ) == ("PRD-B",)
    assert owner._local_assertion_subjects(
        "製品Aと製品Bは在庫切れです。",
        "在庫切れ",
        aliases,
        ("PRD-A", "PRD-B"),
    ) == ("PRD-A", "PRD-B")
    assert owner._local_assertion_subjects(
        "自動ゴミ収集は製品Aと製品B、手動ごみ捨ては製品Cです。",
        "自動ゴミ収集",
        {**aliases, "PRD-C": ("製品C",)},
        ("PRD-A", "PRD-B", "PRD-C"),
    ) == ("PRD-A", "PRD-B")
    assert owner._local_assertion_subjects(
        "自動ゴミ収集は製品Aと製品B、手動ごみ捨ては製品Cです。",
        "手動ごみ捨て",
        {**aliases, "PRD-C": ("製品C",)},
        ("PRD-A", "PRD-B", "PRD-C"),
    ) == ("PRD-C",)


def test_nested_model_token_is_owned_by_the_longer_exact_identity() -> None:
    aliases = {
        "PRD-C1000": ("Anker Solix C1000 Portable Power Station", "C1000"),
        "PRD-C1000-GEN2": (
            "Anker Solix C1000 Gen 2 Portable Power Station",
            "C1000 Gen 2",
        ),
    }
    text = "Anker Solix C1000 Gen 2 Portable Power Station"
    assert owner._local_assertion_subjects(
        text,
        "C1000",
        aliases,
        ("PRD-C1000-GEN2",),
    ) == ("PRD-C1000-GEN2",)


def test_article_local_aliases_and_coordinated_heading_keep_fact_ownership() -> None:
    model = owner._load_repository_model(ROOT)

    suitcase_aliases = model.product_aliases["st1703-first-suitcase-comparison"]
    assert owner._local_assertion_subjects(
        "35L・1.8kgで、比較した3モデルでは最も軽い候補です。",
        "最も軽い",
        suitcase_aliases,
        tuple(suitcase_aliases),
        owner_product_id="PRD-PROTECA-TRI-AIR-01541",
    ) == ("PRD-PROTECA-TRI-AIR-01541",)

    dish_aliases = model.product_aliases[
        "st1704-countertop-dishwasher-for-small-households"
    ]
    assert owner._local_assertion_subjects(
        "短い奥行ならSOLOTA、16点と2WAY給水ならSS-M171。",
        "16点",
        dish_aliases,
        tuple(dish_aliases),
    ) == ("PRD-SIROCA-SS-M171",)


def test_relative_comparison_requires_matching_winner_direction_and_metric() -> None:
    aliases = {
        "PRD-A": ("製品A",),
        "PRD-B": ("製品B",),
    }
    common = {
        "assertion_text": "最小",
        "reader_text": "製品Aは重量が最小です。",
        "occurrence_index": 0,
        "assertion_subjects": ("PRD-A",),
        "claim_subjects": ("PRD-A", "PRD-B"),
        "product_aliases": aliases,
    }
    assert owner._relative_supported(**common, support="製品Aは重量が最小です。")
    assert not owner._relative_supported(**common, support="製品Bは重量が最小です。")
    assert not owner._relative_supported(**common, support="製品Aは容量が最小です。")
    assert not owner._relative_supported(**common, support="製品Aは重量が最大です。")

    assert owner._relative_supported(
        assertion_text="最も軽い",
        reader_text="製品Aは重量が最も軽いです。",
        occurrence_index=0,
        assertion_subjects=("PRD-A",),
        support="製品Aは2製品で最軽量です。",
        claim_subjects=("PRD-A", "PRD-B"),
        product_aliases=aliases,
    )
    assert "最小" not in owner.required_assertion_tokens(
        "最小を一つ決めるのではなく、設置条件を先に決める。"
    )
    assert "最大" not in owner.required_assertion_tokens(
        "最大連続1200Wを超える機器を使う人"
    )
    assert "1200Wを超える" in owner.required_assertion_tokens(
        "最大連続1200Wを超える機器を使う人"
    )
    assert "キャスターストッパー" not in owner.required_assertion_tokens(
        "キャスターストッパーや拡張機能を優先したい",
        structural_fact=True,
    )


def test_dimension_support_preserves_axis_role_and_repeated_occurrence() -> None:
    triplet = "幅21.2×奥行17.8×高さ28.5cm"
    assert owner._token_supported(
        triplet,
        "ステーションは幅21.2×奥行17.8×高さ28.5cmです。",
        dimension_role="STATION",
    )
    assert not owner._token_supported(
        triplet,
        "本体は幅21.2×奥行17.8×高さ28.5cmです。",
        dimension_role="STATION",
    )
    assert not owner._token_supported(
        triplet,
        "ステーションは幅28.5×奥行17.8×高さ21.2cmです。",
        dimension_role="STATION",
    )
    support = "本体奥行315mmです。開扉時奥行594mmです。"
    assert owner._token_supported(
        "奥行315mm", support, dimension_role="BODY", dimension_axis="DEPTH"
    )
    assert not owner._token_supported(
        "奥行315mm", support, dimension_role="OPEN", dimension_axis="DEPTH"
    )
    assert not owner._token_supported(
        "奥行315mm", support, dimension_role="BODY", dimension_axis="WIDTH"
    )


def test_exact_measurements_support_only_true_editorial_thresholds() -> None:
    support = (
        "本体は幅24.8×奥行24.8×高さ9.2cm、ステーションは幅24×奥行18×高さ25cmです。"
    )
    assert owner._token_supported("24.0cm", support, dimension_role="STATION")
    assert owner._token_supported(
        "幅25cm以下", support, dimension_role="BODY", dimension_axis="WIDTH"
    )
    assert not owner._token_supported(
        "高さ9.2cm未満", support, dimension_role="BODY", dimension_axis="HEIGHT"
    )
    assert owner._token_supported("2kg台", "重量は2.2kgです。")
    assert not owner._token_supported("2kg台", "重量は3.0kgです。")


def test_open_depth_fallback_does_not_relabel_preceding_body_dimensions() -> None:
    text = "幅42cm・奥行43.5cm、ドア開放時奥行76cm"
    assert owner._local_dimension_role(text, "幅42cm", "OPEN") == "BODY"
    assert owner._local_dimension_role(text, "奥行43.5cm", "OPEN") == "BODY"
    assert owner._local_dimension_role(text, "ドア開放時奥行76cm", "OPEN") == "OPEN"


def test_per_cycle_cost_guidance_does_not_invent_an_event_count() -> None:
    assert "1回" not in owner.required_assertion_tokens(
        "Wだけでは、1回の電気代を比べられない。"
    )
    tokens = owner.required_assertion_tokens(
        "約2.5Lは1回あたりの公表値です。1日の運転回数で使用量は変わります。"
    )
    assert "2.5L" in tokens
    assert "1回" not in tokens
    assert "1日" not in tokens


def test_editorial_date_range_does_not_invent_a_one_day_product_claim() -> None:
    text = (
        "メーカーと航空会社の公式情報を2026年8月31日から9月1日に参照しています。"
        "実機試験は行っていません。"
    )
    assert "1日" not in owner.required_assertion_tokens(text)
    assert owner.required_assertion_tokens(text) == ()


def test_unknown_boundary_requires_the_same_explicit_topic() -> None:
    assert owner._unknown_boundary_supported(
        "公式ストアでカートを確認できないため候補から除外します。",
        "購入・カート導線を確認できなかったため候補から除外した。",
    )
    assert owner._unknown_boundary_supported(
        "ステーション寸法の軸が未確認です。",
        "軸ラベルがないため設置寸法を同じ基準で比較できない。",
    )
    assert not owner._unknown_boundary_supported(
        "カートを確認できません。",
        "実機の耐久性は確認できない。",
    )
    assert not owner._has_reader_decision_unknown(
        "一致する楽天商品を確認できなかったため、楽天購入リンクは掲載していません。"
    )
    assert owner._has_reader_decision_unknown(
        "一致する楽天商品を確認できなかったため、楽天購入リンクは掲載していません。"
        "耐久性も確認できません。"
    )
    assert not owner._has_reader_decision_unknown(
        "通常時115cm、拡張時118cm（比較対象外）"
    )
    assert "販売中" not in owner.required_assertion_tokens(
        "埋め込みデータだけで販売中とは判定しません"
    )
    assert "販売中" not in owner.required_assertion_tokens(
        "販売中と推測せず、次回確認へ回します"
    )
    assert "在庫切れ" in owner.required_assertion_tokens(
        "在庫切れかつ購入UIを確認できない"
    )
    assert owner._sales_unknown_overlap("在庫切れかつ購入UIを確認できない。")
    assert not owner._sales_unknown_overlap(
        "公式通販で在庫切れを確認した。実機は未確認です。"
    )
    assert (
        owner.required_assertion_tokens(
            "公式商品ページと公式サイト内の分類情報が一致せず、"
            "キャスターストッパーの有無は未確認 未確認"
        )
        == ()
    )
    assert "0.5m" in owner.required_assertion_tokens(
        "左右0.5m、前方1.5mの空間を確保する。"
    )
    assert "販売中" not in owner.required_assertion_tokens("販売中の小型候補を選ぶ場合")
    assert not owner._has_reader_decision_unknown(
        "このページからは確定できません。"
        "利用する運航会社、便、機材、運賃種別の最新条件と、"
        "荷物を入れた状態の外寸・総重量を照合してください。"
    )


def test_closed_wifi_band_boundary_preserves_negative_meaning() -> None:
    support = "2.4GHz Wi-Fiだけに対応する。"
    assert owner._closed_wifi_band_boundary_supported(
        "5GHz",
        "5GHzのみのSSIDでは設定できません。",
        support,
    )
    assert not owner._closed_wifi_band_boundary_supported(
        "5GHz", "5GHzに対応します。", support
    )


def test_external_recheck_cannot_be_promoted_to_a_completed_or_decision_kind() -> None:
    text = "販売状態は未確認（推奨根拠に使用しない） MC-RSC10"
    unit = owner.ReaderUnit(
        unit_id="RU-recheck-contract",
        locator="section[1]/p[1]::text",
        channel="VISIBLE_TEXT",
        text=text,
        text_sha256=owner._text_sha256(text),
        context="GENERAL",
        subject_product_ids=(),
        owner_product_id=None,
        dimension_role=None,
        dimension_axis=None,
        sequence=1,
    )
    claim_id = "CLM-EXTERNAL-RULO-MINI-REFERENCE"
    claim = {
        "claim_id": claim_id,
        "classification": "DECISION_CRITICAL_UNKNOWN",
        "evidence_level": "UNKNOWN",
        "statement": "MC-RSC10の販売状態は確定できず、推奨根拠に使用しない。",
        "evidence_refs": ["SRC-OFFICIAL"],
        "status": "UNCONFIRMED_FROM_BOUND_OFFICIAL_SOURCE",
        "subject_product_ids": [],
    }
    binding = {
        "unit_id": unit.unit_id,
        "locator": unit.locator,
        "channel": unit.channel,
        "text": unit.text,
        "text_sha256": unit.text_sha256,
        "context": unit.context,
        "subject_product_ids": [],
        "owner_product_id": None,
        "dimension_role": None,
        "dimension_axis": None,
        "kind": "RECHECK_REQUIRED",
        "claim_ids": [claim_id],
        "evidence_bindings": [],
        "assertion_tokens": [
            {
                "assertion_text": "販売状態は未確認",
                "occurrence_index": 0,
                "claim_ids": [claim_id],
                "evidence_binding_ids": [],
            },
            {
                "assertion_text": "MC-RSC10",
                "occurrence_index": 0,
                "claim_ids": [claim_id],
                "evidence_binding_ids": [],
            },
        ],
        "exemption_code": None,
        "decision_gate": None,
    }
    common = {
        "packet_claims": {claim_id: claim},
        "support_by_claim": {claim_id: cast(str, claim["statement"])},
        "claim_subjects": {claim_id: ()},
        "product_aliases": {},
        "sales_states": {},
        "allowed_product_ids": set(),
    }
    owner._validate_unit_binding(unit=unit, raw_binding=binding, **common)

    feature_text = "前開きとキャスターストッパーは未確認(推奨根拠に使用しない)です。"
    feature_unit = deepcopy(unit)
    object.__setattr__(feature_unit, "text", feature_text)
    object.__setattr__(feature_unit, "text_sha256", owner._text_sha256(feature_text))
    feature_binding = deepcopy(binding)
    feature_binding.update(
        text=feature_text,
        text_sha256=owner._text_sha256(feature_text),
        assertion_tokens=[
            {
                "assertion_text": token,
                "occurrence_index": 0,
                "claim_ids": [claim_id],
                "evidence_binding_ids": [],
            }
            for token in owner.required_assertion_tokens(feature_text)
        ],
    )
    feature_claim = {
        **claim,
        "statement": ("前開きとキャスターストッパーは未確認(推奨根拠に使用しない)。"),
    }
    owner._validate_unit_binding(
        unit=feature_unit,
        raw_binding=feature_binding,
        packet_claims={claim_id: feature_claim},
        support_by_claim={claim_id: cast(str, feature_claim["statement"])},
        claim_subjects={claim_id: ()},
        product_aliases={},
        sales_states={},
        allowed_product_ids=set(),
    )

    promoted = deepcopy(binding)
    promoted["kind"] = "EDITORIAL_INFERENCE"
    with pytest.raises(owner.CoverageFailure, match="promoted to a completed kind"):
        owner._validate_unit_binding(unit=unit, raw_binding=promoted, **common)

    decision_unit = deepcopy(unit)
    object.__setattr__(decision_unit, "context", "DECISION")
    decision = deepcopy(binding)
    decision["context"] = "DECISION"
    with pytest.raises(owner.CoverageFailure, match="reached a decision surface"):
        owner._validate_unit_binding(unit=decision_unit, raw_binding=decision, **common)

    excluded_claim_id = "CLM-EXTERNAL-RULO-MINI-EXCLUDED"
    excluded_claim = {**claim, "claim_id": excluded_claim_id}
    excluded = deepcopy(binding)
    excluded["claim_ids"] = [excluded_claim_id]
    cast(list[dict[str, object]], excluded["assertion_tokens"])[0]["claim_ids"] = [
        excluded_claim_id
    ]
    with pytest.raises(owner.CoverageFailure, match="completed/non-reference"):
        owner._validate_unit_binding(
            unit=unit,
            raw_binding=excluded,
            packet_claims={excluded_claim_id: excluded_claim},
            support_by_claim={excluded_claim_id: cast(str, claim["statement"])},
            claim_subjects={excluded_claim_id: ()},
            product_aliases={},
            sales_states={},
            allowed_product_ids=set(),
        )

    hidden = deepcopy(binding)
    hidden_text = "販売状態は未確認 MC-RSC10"
    hidden["text"] = hidden_text
    hidden["text_sha256"] = owner._text_sha256(hidden_text)
    hidden_unit = deepcopy(unit)
    object.__setattr__(hidden_unit, "text", hidden_text)
    object.__setattr__(hidden_unit, "text_sha256", owner._text_sha256(hidden_text))
    with pytest.raises(owner.CoverageFailure, match="disclosure is not reader-visible"):
        owner._validate_unit_binding(unit=hidden_unit, raw_binding=hidden, **common)

    # A terse comparison-cell UNKNOWN is a different state: it carries no
    # external candidate claim and cannot be used as a shorthand for a
    # RECHECK_REQUIRED market candidate.  Conversely, the market-candidate
    # prose cannot be downgraded to the table-cell kind.
    unknown_text = "未確認"
    comparison_unknown = owner.ReaderUnit(
        unit_id="RU-comparison-cell-unknown",
        locator="section[1]/table[1]/tbody[1]/tr[1]/td[1]::text",
        channel="VISIBLE_TEXT",
        text=unknown_text,
        text_sha256=owner._text_sha256(unknown_text),
        context="COMPARISON",
        subject_product_ids=(),
        owner_product_id=None,
        dimension_role=None,
        dimension_axis=None,
        sequence=2,
    )
    comparison_binding = {
        "unit_id": comparison_unknown.unit_id,
        "locator": comparison_unknown.locator,
        "channel": comparison_unknown.channel,
        "text": comparison_unknown.text,
        "text_sha256": comparison_unknown.text_sha256,
        "context": comparison_unknown.context,
        "subject_product_ids": [],
        "owner_product_id": None,
        "dimension_role": None,
        "dimension_axis": None,
        "kind": "UNKNOWN",
        "claim_ids": [],
        "evidence_bindings": [],
        "assertion_tokens": [],
        "exemption_code": None,
        "decision_gate": None,
    }
    owner._validate_unit_binding(
        unit=comparison_unknown,
        raw_binding=comparison_binding,
        packet_claims={},
        support_by_claim={},
        claim_subjects={},
        product_aliases={},
        sales_states={},
        allowed_product_ids=set(),
    )

    mistaken_recheck = deepcopy(comparison_binding)
    mistaken_recheck["kind"] = "RECHECK_REQUIRED"
    with pytest.raises(owner.CoverageFailure, match="has no external reference"):
        owner._validate_unit_binding(
            unit=comparison_unknown,
            raw_binding=mistaken_recheck,
            packet_claims={},
            support_by_claim={},
            claim_subjects={},
            product_aliases={},
            sales_states={},
            allowed_product_ids=set(),
        )

    downgraded_recheck = deepcopy(binding)
    downgraded_recheck["kind"] = "UNKNOWN"
    downgraded_recheck["claim_ids"] = []
    downgraded_recheck["assertion_tokens"] = []
    with pytest.raises(owner.CoverageFailure, match="UNKNOWN is allowed only"):
        owner._validate_unit_binding(
            unit=unit, raw_binding=downgraded_recheck, **common
        )


def test_external_out_of_stock_ui_gap_requires_the_same_closed_exclusion() -> None:
    text = "F155260は在庫切れかつ購入UIを確認できないため除外します。"
    unit = owner.ReaderUnit(
        unit_id="RU-external-oos-ui-gap",
        locator="section[1]/p[1]::text",
        channel="VISIBLE_TEXT",
        text=text,
        text_sha256=owner._text_sha256(text),
        context="GENERAL",
        subject_product_ids=(),
        owner_product_id=None,
        dimension_role=None,
        dimension_axis=None,
        sequence=1,
    )
    claim_id = "CLM-EXTERNAL-F155260-EXCLUDED"
    claim = {
        "claim_id": claim_id,
        "classification": "EDITORIAL_INFERENCE",
        "status": "INFERENCE_FROM_BOUND_OFFICIAL_FACTS",
        "statement": text,
        "subject_product_ids": [],
        "effective_lifecycle": "SOLD_OUT",
        "manufacturer_sales_state": {
            "status": "OUT_OF_STOCK",
            "recommendation_gate": "BLOCKED",
            "cta_gate": "BLOCKED",
        },
    }
    tokens = owner.required_assertion_tokens(text)
    assert tokens == ("F155260", "在庫切れ", "購入UIを確認できない")
    binding = {
        "unit_id": unit.unit_id,
        "locator": unit.locator,
        "channel": unit.channel,
        "text": unit.text,
        "text_sha256": unit.text_sha256,
        "context": unit.context,
        "subject_product_ids": [],
        "owner_product_id": None,
        "dimension_role": None,
        "dimension_axis": None,
        "kind": "EDITORIAL_INFERENCE",
        "claim_ids": [claim_id],
        "evidence_bindings": [],
        "assertion_tokens": [
            {
                "assertion_text": token,
                "occurrence_index": 0,
                "claim_ids": [claim_id],
                "evidence_binding_ids": [],
            }
            for token in tokens
        ],
        "exemption_code": None,
        "decision_gate": None,
    }
    common = {
        "packet_claims": {claim_id: claim},
        "support_by_claim": {claim_id: text},
        "claim_subjects": {claim_id: ()},
        "product_aliases": {},
        "sales_states": {},
        "allowed_product_ids": set(),
    }
    owner._validate_unit_binding(unit=unit, raw_binding=binding, **common)

    missing_gate = deepcopy(claim)
    missing_gate.pop("manufacturer_sales_state")
    with pytest.raises(owner.CoverageFailure, match="unknown qualifier"):
        owner._validate_unit_binding(
            unit=unit,
            raw_binding=binding,
            **{**common, "packet_claims": {claim_id: missing_gate}},
        )

    unrelated = deepcopy(claim)
    unrelated["statement"] = "F155260は在庫切れ。耐久性は確認できない。"
    with pytest.raises(owner.CoverageFailure, match="unknown qualifier"):
        owner._validate_unit_binding(
            unit=unit,
            raw_binding=binding,
            **{
                **common,
                "packet_claims": {claim_id: unrelated},
                "support_by_claim": {claim_id: cast(str, unrelated["statement"])},
            },
        )


def test_nested_comparator_negation_and_arbitrary_fact_laundering_fail_closed(
    tmp_path: Path,
) -> None:
    root = _copy_repository_inputs(tmp_path / "nested")
    nested = json.loads((root / owner.LEDGER_RELATIVE).read_text(encoding="utf-8"))
    article_id = "lightweight-carry-on-suitcase-under-3kg"
    article_html = (
        root / cast(str, _article(nested, article_id)["content_ref"])
    ).read_text(encoding="utf-8")
    subject = next(
        unit
        for unit in _units(_article(nested, article_id))
        if unit["channel"] == "VISIBLE_TEXT"
        and "以下" in cast(str, unit["text"])
        and cast(str, unit["text"]).count("以下") == 1
        and article_html.count(cast(str, unit["text"])) == 1
    )
    replacement = cast(str, subject["text"]).replace("以下", "以下ではない", 1)
    _rewrite_static_unit(root, nested, article_id, subject, replacement)
    with pytest.raises(owner.CoverageFailure, match="nested comparator negation"):
        owner.validate_repository(root, nested)

    root = _copy_repository_inputs(tmp_path / "arbitrary")
    document = json.loads((root / owner.LEDGER_RELATIVE).read_text(encoding="utf-8"))
    article_id = "carry-on-suitcase-under-100-seats"
    article_html = (
        root / cast(str, _article(document, article_id)["content_ref"])
    ).read_text(encoding="utf-8")
    unit = next(
        unit
        for unit in _units(_article(document, article_id))
        if unit["channel"] == "VISIBLE_TEXT"
        and unit["kind"] == "NON_CLAIM"
        and unit["exemption_code"] == "READER_SCOPE_OR_GUIDANCE"
        and "<" not in cast(str, unit["text"])
        and article_html.count(cast(str, unit["text"])) == 1
    )
    replacement = cast(str, unit["text"]) + " この製品は宇宙空間でも快適です。"
    rebound = _rewrite_static_unit(root, document, article_id, unit, replacement)
    assert not owner.required_assertion_tokens(cast(str, rebound["text"]))
    with pytest.raises(owner.CoverageFailure, match="independently reviewed"):
        owner.validate_repository(root, document)


@pytest.mark.parametrize(
    "exemption_code,base_text",
    (
        ("SOURCE_CITATION_LABEL", "メーカー公式情報を確認する"),
        ("EDITORIAL_METHOD", "比較方法を確認する"),
        ("NAVIGATION_OR_UI", "目次に戻る"),
    ),
)
def test_non_claim_substring_cannot_launder_an_added_product_fact(
    exemption_code: str,
    base_text: str,
) -> None:
    text = f"{base_text}。この製品は医療機器です。"
    unit = owner.ReaderUnit(
        unit_id=f"RU-nonclaim-substring-{exemption_code}",
        locator="section[1]/p[1]::text",
        channel="VISIBLE_TEXT",
        text=text,
        text_sha256=owner._text_sha256(text),
        context="GENERAL",
        subject_product_ids=(),
        owner_product_id=None,
        dimension_role=None,
        dimension_axis=None,
        sequence=1,
    )
    binding = {
        "unit_id": unit.unit_id,
        "locator": unit.locator,
        "channel": unit.channel,
        "text": unit.text,
        "text_sha256": unit.text_sha256,
        "context": unit.context,
        "subject_product_ids": [],
        "owner_product_id": None,
        "dimension_role": None,
        "dimension_axis": None,
        "kind": "NON_CLAIM",
        "claim_ids": [],
        "evidence_bindings": [],
        "assertion_tokens": [],
        "exemption_code": exemption_code,
        "decision_gate": None,
    }
    with pytest.raises(owner.CoverageFailure, match="fact-like NON_CLAIM"):
        owner._validate_unit_binding(
            unit=unit,
            raw_binding=binding,
            packet_claims={},
            support_by_claim={},
            claim_subjects={},
            product_aliases={},
            sales_states={},
            allowed_product_ids=set(),
        )


def test_wordpress_metadata_is_closed_and_external_exclusion_does_not_borrow_sales(
    tmp_path: Path,
) -> None:
    document = _ledger()
    a04_excerpt = next(
        unit
        for unit in _units(
            _article(
                document,
                "st1704-countertop-dishwasher-for-small-households",
            )
        )
        if unit["channel"] == "WORDPRESS_EXCERPT"
    )
    assert a04_excerpt["claim_ids"]
    a04_gate = cast(dict[str, object], a04_excerpt["decision_gate"])
    assert a04_gate["selection_gate"] == "BLOCKED"
    assert a04_gate["publication_gate"] == "BLOCKED"
    assert {
        cast(str, binding["product_id"])
        for binding in cast(list[dict[str, object]], a04_excerpt["evidence_bindings"])
    } == set(cast(list[str], a04_gate["product_ids"]))
    a04_assertions = cast(list[dict[str, object]], a04_excerpt["assertion_tokens"])
    current_models = next(
        assertion
        for assertion in a04_assertions
        if assertion["assertion_text"] == "現行モデル"
    )
    assert set(cast(list[str], current_models["evidence_binding_ids"])) == {
        "MSS-PRD-SIROCA-SS-M171",
        "MSS-PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "MSS-PRD-TOSHIBA-DWS-33B-W",
    }
    assert all(
        assertion["evidence_binding_ids"] == []
        for assertion in a04_assertions
        if assertion["assertion_text"] in {"NP-TMLK1", "販売状態未確認"}
    )

    a10_excerpt = _unit_containing(
        document,
        "solota-vs-rakua-mini-plus",
        "ラクアmini Plus",
        channel="WORDPRESS_EXCERPT",
    )
    assert "CLM-PORTFOLIO-DISH-RAKUA-MINI-PLUS-EXCLUDED" in cast(
        list[str], a10_excerpt["claim_ids"]
    )
    # A removed external candidate is supported by the article-local source
    # packet. It must never borrow the selected-product sales snapshot.
    assert a10_excerpt["evidence_bindings"] == []
    assert all(
        assertion["evidence_binding_ids"] == []
        for assertion in cast(list[dict[str, object]], a10_excerpt["assertion_tokens"])
    )

    root = _copy_repository_inputs(tmp_path / "post-drift")
    posts_path = root / owner.POSTS_RELATIVE
    posts = json.loads(posts_path.read_text(encoding="utf-8"))
    posts["posts"][0]["excerpt"] += " 改変"
    _write_json(posts_path, posts)
    with pytest.raises(owner.CoverageFailure, match="title/excerpt fixture drift"):
        owner.validate_repository(root)


def test_a10_model_identity_is_not_purchase_availability_evidence() -> None:
    document = _ledger()
    article = _article(document, "solota-vs-rakua-mini-plus")
    excerpt = next(
        unit for unit in _units(article) if unit["channel"] == "WORDPRESS_EXCERPT"
    )
    assertions = {
        assertion["assertion_text"]: assertion
        for assertion in cast(list[dict[str, object]], excerpt["assertion_tokens"])
    }
    assert assertions["NP-TMLK1-K"]["claim_ids"] == [
        "CLM-PORTFOLIO-DISH-SOLOTA-NP-TMLK1-IDENTITY-REFERENCE"
    ]
    assert assertions["TK-MDW22B"]["claim_ids"] == [
        "CLM-PORTFOLIO-DISH-RAKUA-MINI-PLUS-EXCLUDED"
    ]
    assert excerpt["decision_gate"] is None
    panasonic_boundary = _unit_containing(
        document,
        "solota-vs-rakua-mini-plus",
        "販売終了や購入不可とは判断しません",
    )
    assert panasonic_boundary["claim_ids"] == [
        "CLM-PORTFOLIO-DISH-SOLOTA-NP-TMLK1-IDENTITY-REFERENCE",
        "CLM-PORTFOLIO-DISH-SOLOTA-NP-TMLK1-EXCLUDED",
    ]
    assert panasonic_boundary["decision_gate"] is None
    assert all(unit["evidence_bindings"] == [] for unit in _units(article))
    assert all(
        "購入UI" not in cast(str, unit["text"])
        and "現行4候補" not in cast(str, unit["text"])
        for unit in _units(article)
    )


def test_conflicting_anker_switch_times_keep_explicit_two_product_scope() -> None:
    document = _ledger()
    unit = _unit_containing(
        document,
        "st1704-anker-solix-c300-c800-c1000-differences",
        "約0.01秒と約0.02秒",
    )
    assert set(unit["subject_product_ids"]) == {
        "PRD-ANKER-SOLIX-C1000",
        "PRD-ANKER-SOLIX-C1000-GEN2",
    }
    assertions = {
        assertion["assertion_text"]: assertion for assertion in unit["assertion_tokens"]
    }
    assert {"0.01秒", "0.02秒"} <= assertions.keys()
    for token in ("0.01秒", "0.02秒"):
        assert assertions[token]["claim_ids"] == ["CLM-ST1704-ANKER-C1000-FEATURE-DIFF"]


def _synthetic_sales_state(
    product_id: str, *, state: str = "UNKNOWN", caveat: object = None
) -> dict[str, object]:
    return {
        "product_id": product_id,
        "state": state,
        "availability_scope": "MODEL",
        "variant_caveat": caveat,
        "checked_at_utc": "2026-09-01T00:00:00Z",
        "official_url": "https://example.invalid/product",
        "structured_snapshot_sha256": "1" * 64,
        "locator": "reader-visible purchase state",
    }


def _synthetic_sales_binding(state: dict[str, object]) -> dict[str, object]:
    product_id = cast(str, state["product_id"])
    return {
        "binding_id": f"MSS-{product_id}",
        "evidence_kind": "MANUFACTURER_SALES_STATE",
        "product_id": product_id,
        **{
            key: state[key]
            for key in (
                "state",
                "availability_scope",
                "variant_caveat",
                "checked_at_utc",
                "official_url",
                "structured_snapshot_sha256",
                "locator",
            )
        },
    }


def test_decision_gate_binds_unknown_sales_safety_and_due_diligence_fail_closed() -> (
    None
):
    product_id = "PRD-TEST-PRODUCT"
    text = "この商品をおすすめする理由"
    unit = owner.ReaderUnit(
        unit_id="RU-decision-gate",
        locator="section[1]/h2[1]::text",
        channel="VISIBLE_TEXT",
        text=text,
        text_sha256=owner._text_sha256(text),
        context="DECISION",
        subject_product_ids=(product_id,),
        owner_product_id=product_id,
        dimension_role=None,
        dimension_axis=None,
        sequence=1,
    )
    sales = _synthetic_sales_state(product_id)
    safety = {
        product_id: {
            "product_id": product_id,
            "status": "BLOCKED_MISSING_RECEIPT",
            "receipt_sha256s": [],
            "missing_authority_kinds": list(owner.PRODUCT_SAFETY_REQUIRED_AUTHORITIES),
            "stale_authority_kinds": [],
            "matched_notice_ids": [],
        }
    }
    axes = {
        "article": {
            axis: "SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED"
            for axis in owner.DECISION_GATE_AXES
        }
    }
    gate = owner._expected_decision_gate(
        article_id="article",
        unit=unit,
        product_aliases={product_id: ("TEST",)},
        allowed_product_ids={product_id},
        sales_states={product_id: sales},
        safety_statuses=safety,
        market_axis_states=axes,
    )
    assert gate is not None
    assert gate["sales_gate"] == "BLOCKED"
    assert gate["safety_gate"] == "BLOCKED"
    assert gate["selection_gate"] == "BLOCKED"
    assert gate["publication_gate"] == "BLOCKED"
    assert any(
        cast(str, reason).startswith("SALES_STATE:")
        for reason in cast(list[str], gate["blocked_reasons"])
    )
    claim_id = "CLM-TEST-INFERENCE"
    claim = {
        "classification": "EDITORIAL_INFERENCE",
        "status": "INFERENCE_FROM_BOUND_OFFICIAL_FACTS",
    }
    binding = {
        "unit_id": unit.unit_id,
        "locator": unit.locator,
        "channel": unit.channel,
        "text": unit.text,
        "text_sha256": unit.text_sha256,
        "context": unit.context,
        "subject_product_ids": [product_id],
        "owner_product_id": product_id,
        "dimension_role": None,
        "dimension_axis": None,
        "kind": "EDITORIAL_INFERENCE",
        "claim_ids": [claim_id],
        "evidence_bindings": [_synthetic_sales_binding(sales)],
        "assertion_tokens": [],
        "exemption_code": None,
        "decision_gate": gate,
    }
    common = {
        "article_id": "article",
        "unit": unit,
        "packet_claims": {claim_id: claim},
        "support_by_claim": {claim_id: text},
        "claim_subjects": {claim_id: (product_id,)},
        "product_aliases": {product_id: ("TEST",)},
        "sales_states": {product_id: sales},
        "safety_statuses": safety,
        "market_axis_states": axes,
        "allowed_product_ids": {product_id},
    }
    owner._validate_unit_binding(raw_binding=binding, **common)

    fail_open = deepcopy(binding)
    cast(dict[str, object], fail_open["decision_gate"])["publication_gate"] = "ELIGIBLE"
    with pytest.raises(owner.CoverageFailure, match="decision gate drift"):
        owner._validate_unit_binding(raw_binding=fail_open, **common)

    missing_sales = deepcopy(binding)
    missing_sales["evidence_bindings"] = []
    with pytest.raises(owner.CoverageFailure, match="lacks bound manufacturer"):
        owner._validate_unit_binding(raw_binding=missing_sales, **common)


def test_recommendation_conclusion_requires_inference_and_gate() -> None:
    product_id = "PRD-TEST-PRODUCT"
    text = "おすすめする理由"
    unit = owner.ReaderUnit(
        unit_id="RU-recommendation",
        locator="section[1]/h2[1]::text",
        channel="VISIBLE_TEXT",
        text=text,
        text_sha256=owner._text_sha256(text),
        context="DECISION",
        subject_product_ids=(product_id,),
        owner_product_id=product_id,
        dimension_role=None,
        dimension_axis=None,
        sequence=1,
    )
    sales = _synthetic_sales_state(product_id, state="AVAILABLE")
    safety_row = {
        "product_id": product_id,
        "status": "COMPLETE_NONE_FOUND",
        "receipt_sha256s": ["2" * 64, "3" * 64],
        "missing_authority_kinds": [],
        "stale_authority_kinds": [],
        "matched_notice_ids": [],
    }
    axes = {
        "article": {axis: "OFFICIAL_EVIDENCE_USED" for axis in owner.DECISION_GATE_AXES}
    }
    gate = owner._expected_decision_gate(
        article_id="article",
        unit=unit,
        product_aliases={product_id: ("TEST",)},
        allowed_product_ids={product_id},
        sales_states={product_id: sales},
        safety_statuses={product_id: safety_row},
        market_axis_states=axes,
    )
    assert gate is not None and gate["publication_gate"] == "ELIGIBLE"
    binding = {
        "unit_id": unit.unit_id,
        "locator": unit.locator,
        "channel": unit.channel,
        "text": unit.text,
        "text_sha256": unit.text_sha256,
        "context": unit.context,
        "subject_product_ids": [product_id],
        "owner_product_id": product_id,
        "dimension_role": None,
        "dimension_axis": None,
        "kind": "VERIFIABLE",
        "claim_ids": ["CLM-FACT"],
        "evidence_bindings": [_synthetic_sales_binding(sales)],
        "assertion_tokens": [],
        "exemption_code": None,
        "decision_gate": gate,
    }
    with pytest.raises(owner.CoverageFailure, match="recommendation conclusion"):
        owner._validate_unit_binding(
            article_id="article",
            unit=unit,
            raw_binding=binding,
            packet_claims={"CLM-FACT": {"classification": "MAJOR_VERIFIABLE"}},
            support_by_claim={"CLM-FACT": text},
            claim_subjects={"CLM-FACT": (product_id,)},
            product_aliases={product_id: ("TEST",)},
            sales_states={product_id: sales},
            safety_statuses={product_id: safety_row},
            market_axis_states=axes,
            allowed_product_ids={product_id},
        )


def test_available_product_spec_in_decision_section_does_not_repeat_selection_gate() -> (
    None
):
    product_id = "PRD-TEST-PRODUCT"
    text = "本体重量は2.4kgです。"
    unit = owner.ReaderUnit(
        unit_id="RU-decision-spec",
        locator="section[1]/article[1]/p[1]::text",
        channel="VISIBLE_TEXT",
        text=text,
        text_sha256=owner._text_sha256(text),
        context="DECISION",
        subject_product_ids=(product_id,),
        owner_product_id=product_id,
        dimension_role=None,
        dimension_axis=None,
        sequence=1,
    )
    sales = _synthetic_sales_state(product_id, state="AVAILABLE")
    safety = {
        product_id: {
            "product_id": product_id,
            "status": "BLOCKED_MISSING_RECEIPT",
            "receipt_sha256s": [],
            "missing_authority_kinds": list(owner.PRODUCT_SAFETY_REQUIRED_AUTHORITIES),
            "stale_authority_kinds": [],
            "matched_notice_ids": [],
        }
    }
    axes = {
        "article": {
            axis: "SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED"
            for axis in owner.DECISION_GATE_AXES
        }
    }
    assert (
        owner._expected_decision_gate(
            article_id="article",
            unit=unit,
            product_aliases={product_id: ("TEST",)},
            allowed_product_ids={product_id},
            sales_states={product_id: sales},
            safety_statuses=safety,
            market_axis_states=axes,
        )
        is None
    )


def test_every_explicit_product_requires_its_own_semantic_coverage() -> None:
    first = "PRD-PANASONIC-SOLOTA"
    second = "PRD-THANKO-RAKUA"
    text = "SOLOTAとラクアminiを比較します。"
    unit = owner.ReaderUnit(
        unit_id="RU-multi-product",
        locator="section[1]/p[1]::text",
        channel="VISIBLE_TEXT",
        text=text,
        text_sha256=owner._text_sha256(text),
        context="GENERAL",
        subject_product_ids=(first, second),
        owner_product_id=None,
        dimension_role=None,
        dimension_axis=None,
        sequence=1,
    )
    binding = {
        "unit_id": unit.unit_id,
        "locator": unit.locator,
        "channel": unit.channel,
        "text": text,
        "text_sha256": unit.text_sha256,
        "context": "GENERAL",
        "subject_product_ids": [first, second],
        "owner_product_id": None,
        "dimension_role": None,
        "dimension_axis": None,
        "kind": "VERIFIABLE",
        "claim_ids": ["CLM-FIRST"],
        "evidence_bindings": [],
        "assertion_tokens": [],
        "exemption_code": None,
        "decision_gate": None,
    }
    common = {
        "unit": unit,
        "support_by_claim": {"CLM-FIRST": text, "CLM-SECOND": text},
        "product_aliases": {first: ("SOLOTA",), second: ("ラクアmini",)},
        "sales_states": {},
        "allowed_product_ids": {first, second},
    }
    with pytest.raises(owner.CoverageFailure, match="explicit product lacks"):
        owner._validate_unit_binding(
            raw_binding=binding,
            packet_claims={"CLM-FIRST": {"classification": "MAJOR_VERIFIABLE"}},
            claim_subjects={"CLM-FIRST": (first,)},
            **{**common, "support_by_claim": {"CLM-FIRST": text}},
        )
    covered = deepcopy(binding)
    covered["claim_ids"] = ["CLM-FIRST", "CLM-SECOND"]
    owner._validate_unit_binding(
        raw_binding=covered,
        packet_claims={
            "CLM-FIRST": {"classification": "MAJOR_VERIFIABLE"},
            "CLM-SECOND": {"classification": "MAJOR_VERIFIABLE"},
        },
        claim_subjects={"CLM-FIRST": (first,), "CLM-SECOND": (second,)},
        **common,
    )


@pytest.mark.parametrize(
    "text,exemption",
    (
        ("比較方法です。メーカー公式で現行表示を確認。", "EDITORIAL_METHOD"),
        ("広告を含みます。この商品をおすすめする理由。", "DISCLOSURE_POLICY"),
        ("注記・出典。この商品は生産終了です。", "SOURCE_CITATION_LABEL"),
    ),
)
def test_non_claim_exemption_cannot_hide_mixed_fact_or_recommendation(
    text: str, exemption: str
) -> None:
    unit = owner.ReaderUnit(
        unit_id=f"RU-nonclaim-{exemption}",
        locator="section[1]/p[1]::text",
        channel="VISIBLE_TEXT",
        text=text,
        text_sha256=owner._text_sha256(text),
        context="GENERAL",
        subject_product_ids=(),
        owner_product_id=None,
        dimension_role=None,
        dimension_axis=None,
        sequence=1,
    )
    binding = {
        "unit_id": unit.unit_id,
        "locator": unit.locator,
        "channel": unit.channel,
        "text": unit.text,
        "text_sha256": unit.text_sha256,
        "context": unit.context,
        "subject_product_ids": [],
        "owner_product_id": None,
        "dimension_role": None,
        "dimension_axis": None,
        "kind": "NON_CLAIM",
        "claim_ids": [],
        "evidence_bindings": [],
        "assertion_tokens": [],
        "exemption_code": exemption,
        "decision_gate": None,
    }
    with pytest.raises(owner.CoverageFailure, match="fact-like NON_CLAIM"):
        owner._validate_unit_binding(
            unit=unit,
            raw_binding=binding,
            packet_claims={},
            support_by_claim={},
            claim_subjects={},
            product_aliases={},
            sales_states={},
            allowed_product_ids=set(),
        )


def test_assertion_serialization_rejects_legacy_generic_token_field() -> None:
    text = "1200W"
    unit = owner.ReaderUnit(
        unit_id="RU-assertion-field",
        locator="section[1]/p[1]::text",
        channel="VISIBLE_TEXT",
        text=text,
        text_sha256=owner._text_sha256(text),
        context="GENERAL",
        subject_product_ids=(),
        owner_product_id=None,
        dimension_role=None,
        dimension_axis=None,
        sequence=1,
    )
    binding = {
        "unit_id": unit.unit_id,
        "locator": unit.locator,
        "channel": unit.channel,
        "text": text,
        "text_sha256": unit.text_sha256,
        "context": "GENERAL",
        "subject_product_ids": [],
        "owner_product_id": None,
        "dimension_role": None,
        "dimension_axis": None,
        "kind": "VERIFIABLE",
        "claim_ids": ["CLM-POWER"],
        "evidence_bindings": [],
        "assertion_tokens": [
            {
                "assertion_text": "1200W",
                "occurrence_index": 0,
                "claim_ids": ["CLM-POWER"],
                "evidence_binding_ids": [],
            }
        ],
        "exemption_code": None,
        "decision_gate": None,
    }
    common = {
        "unit": unit,
        "packet_claims": {"CLM-POWER": {"classification": "MAJOR_VERIFIABLE"}},
        "support_by_claim": {"CLM-POWER": "定格出力1200W"},
        "claim_subjects": {"CLM-POWER": ()},
        "product_aliases": {},
        "sales_states": {},
        "allowed_product_ids": set(),
    }
    owner._validate_unit_binding(raw_binding=binding, **common)
    legacy = deepcopy(binding)
    assertion = cast(list[dict[str, object]], legacy["assertion_tokens"])[0]
    assertion["token"] = assertion.pop("assertion_text")
    with pytest.raises(owner.CoverageFailure, match="unexpected fields"):
        owner._validate_unit_binding(raw_binding=legacy, **common)


def test_new_sales_lexemes_dates_and_exact_variant_scope_are_bound() -> None:
    assert owner.required_assertion_tokens(
        "2026年9月1日にメーカー公式で現行販売を確認しました。"
    ) == ("2026年9月1日", "現行販売")
    assert owner.required_assertion_tokens("メーカー公式で現行表示を確認。") == (
        "現行表示",
    )
    assert owner.required_assertion_tokens("再入荷通知のみを確認。") == (
        "再入荷通知のみ",
    )
    assert owner.required_assertion_tokens("購入UIを確認できる現行候補です。") == (
        "購入UIを確認できる",
    )
    assert owner.required_assertion_tokens("現行候補から除外しました。") == ()
    assert owner.required_assertion_tokens("Q. 商品ページがあれば販売中ですか。") == ()
    caveat = {
        "code": "OTHER_COLOR_NOT_ATTESTED",
        "detail": "ブラックT2292511のみ",
        "establishes_exact_rakuten_variant": False,
    }
    state = _synthetic_sales_state(
        "PRD-EUFY-AUTOEMPTY-C10-T2292", state="AVAILABLE", caveat=caveat
    )
    assert not owner._sales_token_supported("現行販売", state)
    assert owner._sales_token_supported("現行販売", state, "ブラックT2292511の現行販売")
    assert not owner._sales_token_supported("現行販売", state, "ホワイトの現行販売")


def test_missing_product_safety_receipts_derive_explicit_blocked_status(
    tmp_path: Path,
) -> None:
    root = tmp_path / "safety"
    target = root / owner.PRODUCT_SAFETY_RECEIPT_RELATIVE
    target.parent.mkdir(parents=True, exist_ok=True)
    document = json.loads(
        (ROOT / owner.PRODUCT_SAFETY_RECEIPT_RELATIVE).read_text(encoding="utf-8")
    )
    _write_json(target, document)
    statuses, document_hash = owner._load_product_safety_statuses(
        root=root,
        products_by_id={"PRD-TEST-PRODUCT": {"official_models": ["MODEL-1"]}},
        sources={},
        claims={},
    )
    assert len(document_hash) == 64
    assert statuses["PRD-TEST-PRODUCT"] == {
        "product_id": "PRD-TEST-PRODUCT",
        "status": "BLOCKED_MISSING_RECEIPT",
        "receipt_sha256s": [],
        "missing_authority_kinds": list(owner.PRODUCT_SAFETY_REQUIRED_AUTHORITIES),
        "stale_authority_kinds": [],
        "matched_notice_ids": [],
    }
    document["coverage_caveat_policy"] = {"required_receipt_value": "weaker"}
    _write_json(target, document)
    with pytest.raises(owner.CoverageFailure, match="receipt contract mismatch"):
        owner._load_product_safety_statuses(
            root=root,
            products_by_id={"PRD-TEST-PRODUCT": {"official_models": ["MODEL-1"]}},
            sources={},
            claims={},
        )
