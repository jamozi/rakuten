from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from typing import cast

import pytest

from raos.adapters.affiliate_learning_json import (
    AffiliateLearningJsonStore,
    INPUT_FILE,
    LEDGER_FILE,
    PILOT_DIRECTORY,
    STAGE_FILE,
    decode_strict_json,
)
from raos.application.editorial.affiliate_learning import AffiliateLearningService
from raos.domain.editorial.affiliate_learning import (
    ARTICLE_OBSERVATION_SCHEMA,
    PROGRAM,
    PROGRAM_OBSERVATION_SCHEMA,
    AffiliateLearningLedger,
    AggregateValue,
    ArticleLearningObservation,
    CohortMaturity,
    MeasurementContract,
    MetricResultState,
    MetricUnavailableReason,
    ProgramLearningObservation,
    append_observation,
    build_learning_report,
    calculate_metrics,
    empty_ledger,
    parse_ledger,
    parse_observation,
)
from raos.domain.editorial.owner_local_pilot import (
    AppendDisposition,
    PilotFailure,
    PilotFailureCode,
    ValueState,
    digest,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = (
    ROOT / "changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json"
)
ARTICLE_COLLECTION_PATH = ROOT / (
    "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json"
)
COMPATIBILITY_TEMPLATE_PATH = ROOT / (
    "changes/st-1704/self-hosted-editorial-pilot-v1/operations/measurement-ledger.v1.json"
)


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def load_contract() -> MeasurementContract:
    return MeasurementContract.parse(decode_strict_json(CONTRACT_PATH.read_bytes()))


def value(
    amount: int,
    *,
    evidence: str,
    state: ValueState | None = None,
) -> dict[str, object]:
    if state is None:
        state = ValueState.OBSERVED_ZERO if amount == 0 else ValueState.OBSERVED_VALUE
    return {
        "input_sha256": evidence,
        "state": state.value,
        "value": amount,
    }


def unavailable(state: ValueState = ValueState.UNAVAILABLE) -> dict[str, object]:
    return {"input_sha256": None, "state": state.value, "value": None}


def article_document(
    contract: MeasurementContract,
    slot: int,
    *,
    observation_id: str | None = None,
    start: str = "2026-08-25",
    end: str = "2026-09-08",
    observed_at: str = "2026-09-08T12:00:00Z",
    mature: bool = True,
    verified: bool = True,
    overrides: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    outcome_hash = sha(f"outcome-{slot}-{start}")
    search_hash = sha(f"search-{slot}-{start}")
    article_hash = sha(f"article-{slot}-{start}")
    affiliate_hash = sha(f"affiliate-{slot}-{start}")
    work_hash = sha(f"work-{slot}-{start}")
    cost_hash = sha(f"cost-{slot}-{start}")
    link_hash = sha(f"links-{slot}-{start}")
    metrics = {
        "search_impressions": value(1000, evidence=search_hash),
        "search_clicks": value(100, evidence=search_hash),
        "article_views": value(500, evidence=article_hash),
        "affiliate_clicks": value(50, evidence=affiliate_hash),
        "pending_outcomes": value(0 if mature else 1, evidence=outcome_hash),
        "confirmed_outcomes": value(5, evidence=outcome_hash),
        "rejected_outcomes": value(5, evidence=outcome_hash),
        "direct_confirmed_reward_jpy": value(1000, evidence=outcome_hash),
        "work_minutes": value(120, evidence=work_hash),
        "incremental_cost_jpy": value(100, evidence=cost_hash),
        "broken_links": value(0, evidence=link_hash),
    }
    metrics.update(overrides or {})
    if verified:
        verification = {
            "attribution_basis": "OWNER_VERIFIED_DIRECT_AGGREGATE",
            "input_sha256": outcome_hash,
            "state": "VERIFIED",
        }
    else:
        verification = {
            "attribution_basis": "UNVERIFIED",
            "input_sha256": outcome_hash,
            "state": "UNVERIFIED",
        }
    return {
        "article": contract.article_for_slot(slot).payload(),
        "cohort": {
            "input_sha256": outcome_hash,
            "state": "MATURE" if mature else "IMMATURE",
            "verified_at_utc": observed_at if mature else None,
        },
        "metrics": metrics,
        "observation_id": observation_id or f"OBS.ARTICLE.{slot}.{start}",
        "observed_at_utc": observed_at,
        "period": {
            "duration_days": 14,
            "end_exclusive_date": end,
            "start_date": start,
        },
        "program": PROGRAM,
        "schema": ARTICLE_OBSERVATION_SCHEMA,
        "verification": verification,
    }


def program_document(contract: MeasurementContract) -> dict[str, object]:
    del contract
    evidence = sha("unattributed-program-period")
    return {
        "cohort": {
            "input_sha256": evidence,
            "state": "MATURE",
            "verified_at_utc": "2026-09-08T12:00:00Z",
        },
        "metrics": {"unattributed_confirmed_reward_jpy": value(777, evidence=evidence)},
        "observation_id": "OBS.PROGRAM.2026-08-25",
        "observed_at_utc": "2026-09-08T12:00:00Z",
        "period": {
            "duration_days": 14,
            "end_exclusive_date": "2026-09-08",
            "start_date": "2026-08-25",
        },
        "program": PROGRAM,
        "schema": PROGRAM_OBSERVATION_SCHEMA,
        "verification": {
            "attribution_basis": "UNATTRIBUTED_PROGRAM_TOTAL",
            "input_sha256": evidence,
            "state": "VERIFIED",
        },
    }


def parsed_articles(
    contract: MeasurementContract,
) -> tuple[ArticleLearningObservation, ...]:
    return tuple(
        cast(
            ArticleLearningObservation,
            parse_observation(article_document(contract, slot), contract=contract),
        )
        for slot in range(1, 6)
    )


def ledger_with(
    contract: MeasurementContract,
    observations: tuple[ArticleLearningObservation | ProgramLearningObservation, ...],
) -> AffiliateLearningLedger:
    ledger = empty_ledger(contract)
    for observation in observations:
        ledger, disposition, _ = append_observation(
            ledger, observation, contract=contract
        )
        assert disposition is AppendDisposition.APPENDED
    return ledger


def test_generated_contract_binds_exact_five_articles_and_immutable_v1() -> None:
    contract = load_contract()
    source = json.loads(ARTICLE_COLLECTION_PATH.read_text(encoding="utf-8"))
    assert len(contract.articles) == 5
    assert [article.slot for article in contract.articles] == [1, 2, 3, 4, 5]
    assert [article.article_id for article in contract.articles] == [
        article["article_id"] for article in source["articles"]
    ]
    assert [article.slug for article in contract.articles] == [
        article["slug"] for article in source["articles"]
    ]
    assert [article.intent_classification for article in contract.articles] == [
        "CONDITION_COMPARISON",
        "SELECTION_GUIDE",
        "MODEL_DIFFERENCES",
        "HOUSEHOLD_FIT_COMPARISON",
        "CONDITION_SHORTLIST",
    ]
    assert (
        contract.article_collection_sha256
        == hashlib.sha256(ARTICLE_COLLECTION_PATH.read_bytes()).hexdigest()
    )
    assert (
        contract.compatibility_template_sha256
        == hashlib.sha256(COMPATIBILITY_TEMPLATE_PATH.read_bytes()).hexdigest()
    )
    for expected, raw_article in zip(
        contract.articles, source["articles"], strict=True
    ):
        assert expected.packet_sha256 == digest(raw_article)


def test_all_requested_metrics_are_calculated_deterministically() -> None:
    contract = load_contract()
    results = calculate_metrics(parsed_articles(contract), require_five_slots=True)
    assert results["search_ctr"].value_decimal == "0.100000"
    assert results["affiliate_click_rate"].value_decimal == "0.100000"
    assert results["confirmed_reward_per_click_jpy"].value_decimal == "20.000000"
    assert results["confirmation_rate"].value_decimal == "0.500000"
    assert (
        results["confirmed_reward_per_content_hour_jpy"].value_decimal == "500.000000"
    )
    assert all(
        result.state is MetricResultState.AVAILABLE for result in results.values()
    )
    assert all(
        result.basis == "DIRECT_CONFIRMED_REWARD_ONLY_UNATTRIBUTED_EXCLUDED"
        for result in results.values()
    )


def test_explicit_zero_numerator_is_available_but_zero_denominator_is_not() -> None:
    contract = load_contract()
    rows = tuple(
        cast(
            ArticleLearningObservation,
            parse_observation(
                article_document(
                    contract,
                    slot,
                    overrides={
                        "search_clicks": value(
                            0, evidence=sha(f"search-{slot}-2026-08-25")
                        )
                    },
                ),
                contract=contract,
            ),
        )
        for slot in range(1, 6)
    )
    assert (
        calculate_metrics(rows, require_five_slots=True)["search_ctr"].value_decimal
        == "0.000000"
    )

    zero_views = tuple(
        cast(
            ArticleLearningObservation,
            parse_observation(
                article_document(
                    contract,
                    slot,
                    overrides={
                        "article_views": value(
                            0, evidence=sha(f"article-{slot}-2026-08-25")
                        ),
                        "affiliate_clicks": value(
                            0, evidence=sha(f"affiliate-{slot}-2026-08-25")
                        ),
                    },
                ),
                contract=contract,
            ),
        )
        for slot in range(1, 6)
    )
    result = calculate_metrics(zero_views, require_five_slots=True)[
        "affiliate_click_rate"
    ]
    assert result.state is MetricResultState.UNAVAILABLE
    assert result.unavailable_reason is MetricUnavailableReason.ZERO_DENOMINATOR
    assert result.value_decimal is None


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("missing_slots", MetricUnavailableReason.MISSING_ARTICLE_SLOTS),
        ("unverified", MetricUnavailableReason.UNVERIFIED_INPUT),
        ("immature", MetricUnavailableReason.COHORT_IMMATURE),
        ("period_mismatch", MetricUnavailableReason.PERIOD_MISMATCH),
    ],
)
def test_portfolio_prerequisites_never_coerce_to_zero(
    scenario: str, expected: MetricUnavailableReason
) -> None:
    contract = load_contract()
    rows = list(parsed_articles(contract))
    if scenario == "missing_slots":
        rows.pop()
    elif scenario == "unverified":
        rows[0] = cast(
            ArticleLearningObservation,
            parse_observation(
                article_document(contract, 1, verified=False, mature=False),
                contract=contract,
            ),
        )
    elif scenario == "immature":
        rows[0] = cast(
            ArticleLearningObservation,
            parse_observation(
                article_document(contract, 1, mature=False), contract=contract
            ),
        )
    elif scenario == "period_mismatch":
        rows[0] = cast(
            ArticleLearningObservation,
            parse_observation(
                article_document(
                    contract,
                    1,
                    start="2026-08-26",
                    end="2026-09-09",
                    observed_at="2026-09-09T12:00:00Z",
                ),
                contract=contract,
            ),
        )
    results = calculate_metrics(tuple(rows), require_five_slots=True)
    assert all(
        result.state is MetricResultState.UNAVAILABLE for result in results.values()
    )
    assert all(result.unavailable_reason is expected for result in results.values())
    assert all(result.value_decimal is None for result in results.values())


def test_metric_specific_missing_and_unverified_states_stay_unavailable() -> None:
    contract = load_contract()
    missing_rows = list(parsed_articles(contract))
    missing_rows[0] = cast(
        ArticleLearningObservation,
        parse_observation(
            article_document(
                contract,
                1,
                overrides={"search_impressions": unavailable()},
            ),
            contract=contract,
        ),
    )
    result = calculate_metrics(tuple(missing_rows), require_five_slots=True)[
        "search_ctr"
    ]
    assert result.unavailable_reason is MetricUnavailableReason.MISSING_INPUT

    unverified_rows = list(parsed_articles(contract))
    unverified_rows[0] = cast(
        ArticleLearningObservation,
        parse_observation(
            article_document(
                contract,
                1,
                overrides={
                    "search_impressions": value(
                        1000,
                        evidence=sha("unverified-search"),
                        state=ValueState.UNVERIFIED,
                    )
                },
            ),
            contract=contract,
        ),
    )
    result = calculate_metrics(tuple(unverified_rows), require_five_slots=True)[
        "search_ctr"
    ]
    assert result.unavailable_reason is MetricUnavailableReason.UNVERIFIED_INPUT


def test_pending_outcomes_make_confirmation_rate_unavailable() -> None:
    contract = load_contract()
    rows = list(parsed_articles(contract))
    document = article_document(contract, 1, mature=False)
    document["cohort"] = {
        "input_sha256": sha("outcome-1-2026-08-25"),
        "state": "MATURE",
        "verified_at_utc": "2026-09-08T12:00:00Z",
    }
    with pytest.raises(PilotFailure):
        parse_observation(document, contract=contract)
    result = calculate_metrics(
        (
            replace(
                rows[0],
                cohort=replace(
                    rows[0].cohort, state=CohortMaturity.IMMATURE, verified_at_utc=None
                ),
            ),
        ),
        require_five_slots=False,
    )["confirmation_rate"]
    assert result.unavailable_reason is MetricUnavailableReason.COHORT_IMMATURE


def test_report_keeps_unattributed_reward_program_scoped_and_proposal_only() -> None:
    contract = load_contract()
    program = cast(
        ProgramLearningObservation,
        parse_observation(program_document(contract), contract=contract),
    )
    ledger = ledger_with(contract, (*parsed_articles(contract), program))
    report = build_learning_report(ledger, contract=contract)
    assert report["decision"] == "REVIEW_CANDIDATES_ONLY"
    assert report["program_unattributed_reward"] == {
        "allocation_to_articles": "FORBIDDEN",
        "cohort": program.cohort.payload(),
        "metric": program.unattributed_confirmed_reward_jpy.payload(),
        "observation_id": program.observation_id,
        "period": program.period.payload(),
        "verification": program.verification.payload(),
    }
    assert all(
        "unattributed" not in cast(dict[str, object], article["metrics"])
        for article in cast(list[dict[str, object]], report["articles"])
    )
    boundaries = cast(dict[str, object], report["boundaries"])
    assert boundaries == {
        "analytics_activation": "NOT_EXECUTED",
        "article_html_mutation": False,
        "automatic_publication": False,
        "cta_mutation": False,
        "live_provider_calls": 0,
        "network_requests": 0,
        "product_selection_mutation": False,
        "publication_actions": 0,
        "publication_snapshot_mutation": False,
        "recommendation_order_mutation": False,
        "tracking_activation": "DISABLED_OD_012",
    }
    assert report["recommendation_input_policy"] == {
        "excluded": ["AFFILIATE_COMMISSION_RATE", "EPC", "RPM", "PROFIT"],
        "finance_may_change_recommendation_order": False,
    }


def test_report_proposes_review_codes_without_copy_or_order_changes() -> None:
    contract = load_contract()
    document = article_document(
        contract,
        1,
        overrides={
            "search_clicks": value(0, evidence=sha("search-1-2026-08-25")),
            "affiliate_clicks": value(0, evidence=sha("affiliate-1-2026-08-25")),
            "broken_links": value(2, evidence=sha("links-1-2026-08-25")),
        },
    )
    observation = cast(
        ArticleLearningObservation,
        parse_observation(document, contract=contract),
    )
    report = build_learning_report(
        ledger_with(contract, (observation,)), contract=contract
    )
    assert report["proposal_candidates"] == [
        {
            "article_id": observation.article.article_id,
            "candidate": "REVIEW_AFFILIATE_PRESENTATION",
        },
        {
            "article_id": observation.article.article_id,
            "candidate": "REVIEW_BROKEN_LINKS",
        },
        {
            "article_id": observation.article.article_id,
            "candidate": "REVIEW_SEARCH_DISCOVERABILITY",
        },
    ]
    rendered = json.dumps(report, sort_keys=True)
    assert "suggested_copy" not in rendered
    assert "suggested_product" not in rendered
    assert "suggested_order" not in rendered


@pytest.mark.parametrize(
    "mutation",
    [
        "article_id",
        "slug",
        "packet_sha256",
        "intent_classification",
        "program",
        "unknown_field",
    ],
)
def test_identity_program_and_unknown_field_tampering_is_rejected(
    mutation: str,
) -> None:
    contract = load_contract()
    document = article_document(contract, 1)
    article = cast(dict[str, object], document["article"])
    if mutation == "article_id":
        article["article_id"] = "different-article"
    elif mutation == "slug":
        article["slug"] = "different-slug"
    elif mutation == "packet_sha256":
        article["packet_sha256"] = "f" * 64
    elif mutation == "intent_classification":
        article["intent_classification"] = "MODEL_DIFFERENCES"
    elif mutation == "program":
        document["program"] = "YOUTUBE_SHOPPING_RAKUTEN"
    else:
        document["commission_rate"] = 20
    with pytest.raises(PilotFailure):
        parse_observation(document, contract=contract)


def test_strict_json_rejects_duplicate_keys_float_and_nonfinite() -> None:
    for raw in (
        b'{"schema":"x","schema":"y"}',
        b'{"value":1.5}',
        b'{"value":NaN}',
        b"\xef\xbb\xbf{}",
    ):
        with pytest.raises(PilotFailure):
            decode_strict_json(raw)


def test_hash_chain_replay_conflict_and_tamper() -> None:
    contract = load_contract()
    observation = parsed_articles(contract)[0]
    ledger = empty_ledger(contract)
    ledger, disposition, event_hash = append_observation(
        ledger, observation, contract=contract
    )
    assert disposition is AppendDisposition.APPENDED
    replay, disposition, replay_hash = append_observation(
        ledger, observation, contract=contract
    )
    assert disposition is AppendDisposition.REPLAYED
    assert replay == ledger
    assert replay_hash == event_hash
    changed = replace(
        observation,
        metrics={
            **observation.metrics,
            "broken_links": AggregateValue(
                state=ValueState.OBSERVED_VALUE,
                value=1,
                input_sha256=sha("links-1-2026-08-25"),
            ),
        },
    )
    with pytest.raises(PilotFailure) as conflict:
        append_observation(ledger, changed, contract=contract)
    assert conflict.value.code is PilotFailureCode.OBSERVATION_ID_CONFLICT

    payload = ledger.payload()
    cast(list[dict[str, object]], payload["events"])[0]["event_sha256"] = "0" * 64
    with pytest.raises(PilotFailure) as tampered:
        parse_ledger(payload, contract=contract)
    assert tampered.value.code is PilotFailureCode.LEDGER_TAMPERED


def _private_paths(root: Path) -> tuple[Path, Path]:
    private = root / ".secrets" / PILOT_DIRECTORY
    return private, private / INPUT_FILE


def _write_owner_input(path: Path, document: dict[str, object]) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def test_owner_private_adapter_is_atomic_idempotent_and_preserves_v1(
    tmp_path: Path,
) -> None:
    contract = load_contract()
    tmp_path.chmod(0o700)
    store = AffiliateLearningJsonStore(tmp_path, contract=contract)
    ledger, created = store.initialize()
    assert created is True
    assert ledger.events == ()
    private, input_path = _private_paths(tmp_path)
    v1 = private / "ledger.v1.json"
    v1.write_bytes(b"immutable-v1-sentinel\n")
    v1.chmod(0o600)
    _write_owner_input(input_path, article_document(contract, 1))
    observation = store.read_observation()
    result = store.append(observation)
    assert result.disposition is AppendDisposition.APPENDED
    replay = store.append(observation)
    assert replay.disposition is AppendDisposition.REPLAYED
    assert replay.ledger.payload() == result.ledger.payload()
    assert v1.read_bytes() == b"immutable-v1-sentinel\n"
    assert stat_mode(private / LEDGER_FILE) == 0o600
    assert stat_mode(private) == 0o700
    assert not (private / STAGE_FILE).exists()
    service = AffiliateLearningService(
        contract=contract,
        store=store,
        observation_input=store,
    )
    assert service.doctor()["writes"] == 0
    assert service.report()["event_count"] == 1


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_owner_private_adapter_rejects_stage_symlink_hardlink_and_mode(
    tmp_path: Path,
) -> None:
    contract = load_contract()
    tmp_path.chmod(0o700)
    store = AffiliateLearningJsonStore(tmp_path, contract=contract)
    store.initialize()
    private, input_path = _private_paths(tmp_path)

    (private / STAGE_FILE).write_text("unsafe", encoding="utf-8")
    (private / STAGE_FILE).chmod(0o600)
    with pytest.raises(PilotFailure) as staged:
        store.read()
    assert staged.value.code is PilotFailureCode.RECOVERY_REQUIRED
    (private / STAGE_FILE).unlink()

    target = private / "target.json"
    _write_owner_input(target, article_document(contract, 1))
    input_path.symlink_to(target.name)
    with pytest.raises(PilotFailure):
        store.read_observation()
    input_path.unlink()

    ledger_path = private / LEDGER_FILE
    hardlink = private / "ledger-copy.v2.json"
    os.link(ledger_path, hardlink)
    with pytest.raises(PilotFailure):
        store.read()
    hardlink.unlink()

    private.chmod(0o755)
    with pytest.raises(PilotFailure):
        store.read()


def test_generated_unavailable_examples_parse_without_claiming_observation() -> None:
    contract = load_contract()
    for name in ("article-observation.v2.json", "program-observation.v2.json"):
        raw = (
            ROOT / "changes/st-1704/affiliate-learning-v2/examples" / name
        ).read_bytes()
        observation = parse_observation(decode_strict_json(raw), contract=contract)
        assert observation.observation_id.startswith("EXAMPLE.UNAVAILABLE.")
        if isinstance(observation, ArticleLearningObservation):
            assert all(
                value.state is ValueState.UNAVAILABLE
                for value in observation.metrics.values()
            )
        else:
            assert (
                observation.unattributed_confirmed_reward_jpy.state
                is ValueState.UNAVAILABLE
            )
