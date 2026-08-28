from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
import yaml

from raos.adapters.decision_support_v2.local_events import LocalEventSink
from raos.domain.decision_support_v2.events import (
    AnalyticsEvent,
    EVENT_FIELD_POLICY,
    SessionTokenRotator,
    qualified_decision_sessions,
)


START = datetime.fromisoformat("2026-08-28T12:00:00+09:00")
LOCAL_HMAC_KEY = b"fixture-session-hmac-key"
ROOT = Path(__file__).resolve().parents[2]


def _event(
    event_name: str,
    at: datetime,
    session_hmac: str,
    *,
    result_state: str | None = None,
    source_id: str | None = None,
    product_id: str | None = None,
) -> AnalyticsEvent:
    return AnalyticsEvent(
        event_name=event_name,
        event_version=1,
        event_time_jst=at,
        session_token_hmac=session_hmac,
        article_id="A02",
        placement="main",
        consent_state="UNKNOWN",
        result_state=result_state,
        source_id=source_id,
        product_id=product_id,
    )


@pytest.mark.parametrize(
    "attributes",
    [
        {"raw_ip": "127.0.0.1"},
        {"raw_user_agent": "browser"},
        {"full_referrer": "https://example.invalid/private"},
        {"query_string": "q=secret"},
        {"email": "reader@example.invalid"},
        {"unknown_field": "value"},
        {"source_id": "https://example.invalid/full"},
    ],
)
def test_t_v2_045_event_rejects_pii_url_and_unknown_fields(
    attributes: dict[str, str],
) -> None:
    session_hmac = SessionTokenRotator(
        hmac_key=LOCAL_HMAC_KEY, ephemeral_session_id="browser-memory-only"
    ).token_for(START)
    payload: dict[str, object] = {
        "event_name": "comparison_view",
        "event_version": 1,
        "event_time_jst": START,
        "session_token_hmac": session_hmac,
        "article_id": "A02",
        "placement": "main",
        "consent_state": "UNKNOWN",
        "schema_version": "1.0.0",
        **attributes,
    }
    with pytest.raises(ValueError):
        AnalyticsEvent.from_payload(payload)


def test_unknown_event_is_rejected() -> None:
    session_hmac = SessionTokenRotator(
        hmac_key=LOCAL_HMAC_KEY, ephemeral_session_id="local"
    ).token_for(
        START
    )
    with pytest.raises(ValueError):
        _event("page_view", START, session_hmac)


@pytest.mark.parametrize(
    "event_time",
    [
        datetime.fromisoformat("2026-08-28T03:00:00+00:00"),
        datetime.fromisoformat("2026-08-28T12:00:00+08:00"),
    ],
)
def test_event_time_requires_explicit_jst_offset(event_time: datetime) -> None:
    session_hmac = SessionTokenRotator(
        hmac_key=LOCAL_HMAC_KEY, ephemeral_session_id="local"
    ).token_for(
        START
    )
    with pytest.raises(ValueError):
        _event("comparison_view", event_time, session_hmac)


def test_t_v2_046_inactivity_rotation_exact_boundary() -> None:
    rotator = SessionTokenRotator(
        hmac_key=LOCAL_HMAC_KEY, ephemeral_session_id="local"
    )
    first = rotator.token_for(START)
    assert rotator.token_for(START + timedelta(minutes=29, seconds=59)) == first
    # Activity at 29:59 resets inactivity; another 29:59 remains the same session.
    assert rotator.token_for(START + timedelta(minutes=59, seconds=58)) == first
    assert rotator.token_for(START + timedelta(minutes=89, seconds=58)) != first


def test_tool_result_alone_is_one_qds_and_duplicate_is_deduped() -> None:
    session_hmac = SessionTokenRotator(
        hmac_key=LOCAL_HMAC_KEY, ephemeral_session_id="local"
    ).token_for(
        START
    )
    event = _event("tool_result_view", START, session_hmac, result_state="UNKNOWN")
    assert qualified_decision_sessions((event, event)) == 1


@pytest.mark.parametrize(
    "result_state", ["PASS", "FAIL", "UNKNOWN", "STALE", "BLOCKED", "NO_MATCH"]
)
def test_every_visible_tool_result_state_qualifies_qds(result_state: str) -> None:
    session_hmac = SessionTokenRotator(
        hmac_key=LOCAL_HMAC_KEY, ephemeral_session_id="local"
    ).token_for(
        START
    )
    assert (
        qualified_decision_sessions(
            (
                _event(
                    "tool_result_view", START, session_hmac, result_state=result_state
                ),
            )
        )
        == 1
    )


def test_comparison_requires_a_followup_but_no_result_status() -> None:
    session_hmac = SessionTokenRotator(
        hmac_key=LOCAL_HMAC_KEY, ephemeral_session_id="local"
    ).token_for(
        START
    )
    comparison = _event("comparison_view", START, session_hmac)
    official = _event(
        "official_source_open",
        START + timedelta(minutes=2),
        session_hmac,
        source_id="SRC-V2-ANA-CARRY-ON",
    )
    assert qualified_decision_sessions((comparison,)) == 0
    assert qualified_decision_sessions((comparison, official)) == 1


def test_evidence_view_can_start_qds_but_article_complete_cannot_finish_it() -> None:
    session_hmac = SessionTokenRotator(
        hmac_key=LOCAL_HMAC_KEY, ephemeral_session_id="local"
    ).token_for(
        START
    )
    evidence = _event(
        "evidence_link_open", START, session_hmac, source_id="SRC-V2-ANA-CARRY-ON"
    )
    complete = _event("article_complete", START + timedelta(minutes=1), session_hmac)
    affiliate = _event(
        "affiliate_outbound_activate",
        START + timedelta(minutes=2),
        session_hmac,
        product_id="PRD-ACE-CRESTA-06316",
    )
    assert qualified_decision_sessions((evidence, complete)) == 0
    assert qualified_decision_sessions((evidence, affiliate)) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("article_id", "reader@example.invalid"),
        ("article_id", "自由記述"),
        ("source_id", "not-a-source-id"),
        ("product_id", "ACE-CRESTA-06316"),
        ("session_token_hmac", "A" * 64),
    ],
)
def test_machine_identifiers_and_hmac_are_fail_closed(field: str, value: str) -> None:
    session_hmac = SessionTokenRotator(
        hmac_key=LOCAL_HMAC_KEY, ephemeral_session_id="local"
    ).token_for(
        START
    )
    payload: dict[str, object] = {
        "event_name": "comparison_view",
        "event_version": 1,
        "event_time_jst": START,
        "session_token_hmac": session_hmac,
        "article_id": "A02",
        "placement": "main",
        "consent_state": "UNKNOWN",
        "schema_version": "1.0.0",
        field: value,
    }
    with pytest.raises(ValueError):
        AnalyticsEvent.from_payload(payload)


def test_local_sink_has_no_sender_or_external_action() -> None:
    rotator = SessionTokenRotator(
        hmac_key=LOCAL_HMAC_KEY, ephemeral_session_id="local"
    )
    event = _event("comparison_view", START, rotator.token_for(START))
    sink = LocalEventSink()
    assert sink.collect(event) == "LOCAL:000001"
    assert sink.events() == (event,)
    assert sink.mode == "LOCAL_SINK_ONLY"
    assert sink.external_action_count == 0


@pytest.mark.parametrize(
    ("event_name", "result_state", "source_id", "product_id"),
    [
        ("tool_result_view", None, None, None),
        ("evidence_link_open", None, None, None),
        ("official_source_open", None, None, None),
        ("affiliate_outbound_activate", None, None, None),
        ("error_state_view", None, None, None),
    ],
)
def test_event_specific_required_fields_fail_closed(
    event_name: str,
    result_state: str | None,
    source_id: str | None,
    product_id: str | None,
) -> None:
    session_hmac = SessionTokenRotator(
        hmac_key=LOCAL_HMAC_KEY, ephemeral_session_id="local"
    ).token_for(
        START
    )
    with pytest.raises(ValueError):
        _event(
            event_name,
            START,
            session_hmac,
            result_state=result_state,
            source_id=source_id,
            product_id=product_id,
        )


@pytest.mark.parametrize(
    ("event_name", "result_state", "source_id", "product_id"),
    [
        ("comparison_view", "PASS", None, None),
        ("comparison_view", None, "SRC-V2-ANA-CARRY-ON", None),
        ("comparison_view", None, None, "PRD-ACE-CRESTA-06316"),
        ("tool_result_view", "PASS", None, "PRD-ACE-CRESTA-06316"),
        (
            "official_source_open",
            "PASS",
            "SRC-V2-ANA-CARRY-ON",
            None,
        ),
        (
            "affiliate_outbound_activate",
            None,
            "SRC-V2-ANA-CARRY-ON",
            "PRD-ACE-CRESTA-06316",
        ),
        ("article_complete", "PASS", None, None),
    ],
)
def test_event_specific_irrelevant_fields_fail_closed(
    event_name: str,
    result_state: str | None,
    source_id: str | None,
    product_id: str | None,
) -> None:
    session_hmac = SessionTokenRotator(
        hmac_key=LOCAL_HMAC_KEY, ephemeral_session_id="local"
    ).token_for(
        START
    )
    with pytest.raises(ValueError):
        _event(
            event_name,
            START,
            session_hmac,
            result_state=result_state,
            source_id=source_id,
            product_id=product_id,
        )


def test_event_contract_record_validates_against_phase_1_schema() -> None:
    session_hmac = SessionTokenRotator(
        hmac_key=LOCAL_HMAC_KEY, ephemeral_session_id="local"
    ).token_for(
        START
    )
    event = _event("tool_result_view", START, session_hmac, result_state="STALE")
    schema = json.loads(
        (ROOT / "contracts/raos-v2/v1/analytics-event.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(event.to_contract_record())


def test_event_catalog_and_runtime_field_matrix_are_identical() -> None:
    catalog = yaml.safe_load(
        (ROOT / "changes/raos-v2/phase-2/events/event-catalog.v2.yaml").read_text(
            encoding="utf-8"
        )
    )
    optional_fields = {"result_state", "source_id", "product_id"}
    expected = {
        event_name: {
            "required_non_null": sorted(required),
            "must_be_null": sorted(optional_fields - set(allowed)),
        }
        for event_name, (required, allowed) in EVENT_FIELD_POLICY.items()
    }
    actual = {
        event_name: {
            "required_non_null": sorted(policy["required_non_null"]),
            "must_be_null": sorted(policy["must_be_null"]),
        }
        for event_name, policy in catalog["event_field_matrix"].items()
    }
    assert actual == expected


def test_event_schema_rejects_missing_required_and_irrelevant_measurement_fields() -> (
    None
):
    session_hmac = SessionTokenRotator(
        hmac_key=LOCAL_HMAC_KEY, ephemeral_session_id="local"
    ).token_for(
        START
    )
    schema = json.loads(
        (ROOT / "contracts/raos-v2/v1/analytics-event.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema)
    valid_tool = dict(
        _event(
            "tool_result_view", START, session_hmac, result_state="PASS"
        ).to_contract_record()
    )
    missing_result = {**valid_tool, "result_state": None}
    assert list(validator.iter_errors(missing_result))

    valid_affiliate = dict(
        _event(
            "affiliate_outbound_activate",
            START,
            session_hmac,
            product_id="PRD-ACE-CRESTA-06316",
        ).to_contract_record()
    )
    missing_product = {**valid_affiliate, "product_id": None}
    assert list(validator.iter_errors(missing_product))
    irrelevant_source = {
        **valid_affiliate,
        "source_id": "SRC-V2-ANA-CARRY-ON",
    }
    assert list(validator.iter_errors(irrelevant_source))
