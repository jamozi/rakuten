"""Hostile provider, cursor, and untrusted-text checks for ST-0502 V2."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, cast

import pytest

from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    IngestionSessionStateV2,
    IngestionStepOutcomeV2,
    ItemSearchIngestionSessionV2,
    ItemSearchProviderObservationV2,
    ItemSearchRuntimeFailure,
    ItemSearchRuntimeFailureCode,
    ItemSearchWireRequestV2,
    MAX_RAW_RESPONSE_BYTES,
    ProviderModeV2,
    parse_item_search_page_v2,
    success_transition_v2,
)

from runtime_v2_fixtures import (
    OBSERVED_AT_V2,
    SESSION_ID_V2,
    runtime_command_v2,
    runtime_exchange_v2,
    runtime_json_v2,
    runtime_payload_v2,
    runtime_plan_v2,
    runtime_provider_v2,
    runtime_service_v2,
    runtime_store_v2,
    runtime_success_observation_v2,
)


def _assert_parse_rejected(
    raw: bytes,
    *,
    code: ItemSearchRuntimeFailureCode = ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID,
) -> None:
    request = ItemSearchWireRequestV2.from_plan(runtime_plan_v2(), page=1)
    observation = runtime_success_observation_v2(
        request,
        observed_at=OBSERVED_AT_V2,
        raw=raw,
    )
    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        parse_item_search_page_v2(request=request, observation=observation)
    assert captured.value.code is code


@pytest.mark.parametrize(
    "raw",
    (
        b"\xff\xff",
        b'{"count":1,"count":1}',
        b'{"count":NaN}',
        b"[]",
        runtime_json_v2(
            {
                "nested": [
                    [[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[None]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]
                ]
            }
        ),
        runtime_json_v2([None] * 50_001),
    ),
)
def test_duplicate_malformed_nonfinite_and_complex_json_fail_closed(raw: bytes) -> None:
    _assert_parse_rejected(raw)


def test_oversized_raw_is_rejected_before_a_provider_observation_exists() -> None:
    request = ItemSearchWireRequestV2.from_plan(runtime_plan_v2(), page=1)
    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        runtime_success_observation_v2(
            request,
            observed_at=OBSERVED_AT_V2,
            raw=b"x" * (MAX_RAW_RESPONSE_BYTES + 1),
        )
    assert captured.value.code is ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID


@pytest.mark.parametrize(
    "pairs",
    (
        ((1, "value"),),
        (("name", object()),),
        (("", "value"),),
        (("name", ""),),
        (("duplicate", "1"), ("duplicate", "2")),
    ),
)
def test_hostile_nested_wire_parameter_shapes_fail_with_sanitized_error(
    pairs: object,
) -> None:
    request = ItemSearchWireRequestV2.from_plan(runtime_plan_v2(), page=1)
    with pytest.raises(ItemSearchRuntimeFailure):
        replace(
            request,
            parameter_pairs=cast(tuple[tuple[str, str], ...], pairs),
        )


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload.__setitem__("reviewCount", 500),
        lambda payload: payload.__setitem__("affiliateRate", 99.9),
        lambda payload: payload.__setitem__("page", 2),
        lambda payload: payload.__setitem__("hits", True),
        lambda payload: payload.__setitem__("pageCount", 101),
        lambda payload: payload.__setitem__("items", "not-a-list"),
    ),
)
def test_unknown_ranking_fields_and_wrong_cursor_shapes_fail_closed(
    mutation: Callable[[dict[str, object]], None],
) -> None:
    payload = runtime_payload_v2(page=1, page_count=1)
    mutation(payload)
    expected = (
        ItemSearchRuntimeFailureCode.CONTRACT_DRIFT
        if payload.get("page") == 2
        else ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID
    )
    _assert_parse_rejected(runtime_json_v2(payload), code=expected)


@pytest.mark.parametrize(
    "field",
    (
        "reviewCount",
        "reviewAverage",
        "affiliateRate",
        "commission",
        "EPC",
        "RPM",
        "profit",
    ),
)
def test_item_level_ranking_or_business_field_is_rejected(field: str) -> None:
    payload = runtime_payload_v2(page=1, page_count=1)
    items = cast(list[object], payload["items"])
    item = cast(dict[str, object], items[0])
    item[field] = 1
    _assert_parse_rejected(runtime_json_v2(payload))


@pytest.mark.parametrize(
    "value",
    (
        "provider\ncontrol",
        "provider\u202eoverride",
        "x" * 10_001,
        " leading",
        "trailing ",
    ),
)
def test_hostile_or_oversized_provider_text_is_rejected_without_echo(
    value: str,
) -> None:
    payload = runtime_payload_v2(page=1, page_count=1, item_name=value)
    raw = runtime_json_v2(payload)
    request = ItemSearchWireRequestV2.from_plan(runtime_plan_v2(), page=1)
    observation = runtime_success_observation_v2(
        request,
        observed_at=OBSERVED_AT_V2,
        raw=raw,
    )
    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        parse_item_search_page_v2(request=request, observation=observation)
    assert value not in str(captured.value)
    assert value not in repr(captured.value)


def test_parser_failure_is_archived_and_quarantined_without_reparse_on_replay(
    tmp_path: Path,
) -> None:
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    raw = b'{"count":1,"count":2}'
    provider = runtime_provider_v2(
        runtime_exchange_v2(
            request,
            runtime_success_observation_v2(
                request,
                observed_at=OBSERVED_AT_V2,
                raw=raw,
            ),
        )
    )
    store = runtime_store_v2(tmp_path / "private")
    service = runtime_service_v2(provider=provider, store=store)
    service.create_session(
        session_id=SESSION_ID_V2,
        plan=plan,
        created_at=OBSERVED_AT_V2,
    )
    command = runtime_command_v2(
        operation_index=0,
        expected_version=0,
        observed_at=OBSERVED_AT_V2,
    )

    result = service.step_once(command)
    replay = service.step_once(command)

    assert result.persisted.outcome is IngestionStepOutcomeV2.QUARANTINED
    assert result.persisted.session.state is IngestionSessionStateV2.QUARANTINED
    assert result.persisted.receipt is not None
    assert store.read_raw(result.persisted.receipt) == raw
    assert replay.persisted == result.persisted
    assert replay.page is None
    assert provider.call_count == 1


def test_duplicate_item_identity_across_pages_quarantines_cursor_loop(
    tmp_path: Path,
) -> None:
    plan = runtime_plan_v2(max_pages=3)
    request_1 = ItemSearchWireRequestV2.from_plan(plan, page=1)
    request_2 = ItemSearchWireRequestV2.from_plan(plan, page=2)
    second_at = OBSERVED_AT_V2 + timedelta(seconds=1)
    provider = runtime_provider_v2(
        runtime_exchange_v2(
            request_1,
            runtime_success_observation_v2(
                request_1,
                observed_at=OBSERVED_AT_V2,
                payload=runtime_payload_v2(
                    page=1,
                    page_count=2,
                    item_ordinals=(1,),
                ),
            ),
        ),
        runtime_exchange_v2(
            request_2,
            runtime_success_observation_v2(
                request_2,
                observed_at=second_at,
                payload=runtime_payload_v2(
                    page=2,
                    page_count=2,
                    item_ordinals=(1,),
                ),
            ),
        ),
    )
    store = runtime_store_v2(tmp_path / "private")
    service = runtime_service_v2(provider=provider, store=store)
    service.create_session(
        session_id=SESSION_ID_V2,
        plan=plan,
        created_at=OBSERVED_AT_V2,
    )
    first = service.step_once(
        runtime_command_v2(
            operation_index=0,
            expected_version=0,
            observed_at=OBSERVED_AT_V2,
        )
    )
    second = service.step_once(
        runtime_command_v2(
            operation_index=1,
            expected_version=1,
            observed_at=second_at,
        )
    )

    assert first.persisted.outcome is IngestionStepOutcomeV2.PAGE_ARCHIVED
    assert second.persisted.outcome is IngestionStepOutcomeV2.QUARANTINED
    assert second.persisted.session.state is IngestionSessionStateV2.QUARANTINED
    assert second.persisted.receipt is not None


def test_seen_response_hash_loop_is_rejected_by_pure_transition() -> None:
    plan = runtime_plan_v2(max_pages=3)
    request_1 = ItemSearchWireRequestV2.from_plan(plan, page=1)
    observation = runtime_success_observation_v2(
        request_1,
        observed_at=OBSERVED_AT_V2,
        payload=runtime_payload_v2(page=1, page_count=2),
    )
    page = parse_item_search_page_v2(request=request_1, observation=observation)
    session = ItemSearchIngestionSessionV2.initial(
        session_id=SESSION_ID_V2,
        plan=plan,
        created_at=OBSERVED_AT_V2,
    )
    after, _outcome = success_transition_v2(
        session=session,
        page=page,
        observed_at=OBSERVED_AT_V2,
    )
    request_2 = ItemSearchWireRequestV2.from_plan(plan, page=2)
    loop_page = replace(
        page,
        request_fingerprint=request_2.request_fingerprint,
        page=2,
        first=3,
        last=3,
        raw_sha256=page.raw_sha256,
    )

    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        success_transition_v2(
            session=after,
            page=loop_page,
            observed_at=OBSERVED_AT_V2 + timedelta(seconds=1),
        )
    assert captured.value.code is ItemSearchRuntimeFailureCode.CONTRACT_DRIFT


class _CrossRequestProvider:
    mode = ProviderModeV2.RECORDED_SYNTHETIC
    external_action_count = 0

    def __init__(self, observation: ItemSearchProviderObservationV2) -> None:
        self._observation = observation

    def fetch_once(
        self,
        request: ItemSearchWireRequestV2,
        *,
        observed_at: datetime,
    ) -> ItemSearchProviderObservationV2:
        del request, observed_at
        return self._observation


def test_cross_request_provider_observation_is_rejected_before_commit(
    tmp_path: Path,
) -> None:
    plan = runtime_plan_v2()
    expected = ItemSearchWireRequestV2.from_plan(plan, page=1)
    other = ItemSearchWireRequestV2.from_plan(
        replace(plan, keyword="別の商品"),
        page=1,
    )
    drift = runtime_success_observation_v2(
        other,
        observed_at=OBSERVED_AT_V2,
        payload=runtime_payload_v2(page=1, page_count=1),
    )
    store = runtime_store_v2(tmp_path / "private")
    service = runtime_service_v2(
        provider=_CrossRequestProvider(drift),
        store=store,
    )
    service.create_session(
        session_id=SESSION_ID_V2,
        plan=plan,
        created_at=OBSERVED_AT_V2,
    )

    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        service.step_once(
            runtime_command_v2(
                operation_index=0,
                expected_version=0,
                observed_at=OBSERVED_AT_V2,
            )
        )
    assert captured.value.code is ItemSearchRuntimeFailureCode.CONTRACT_DRIFT
    assert store.load_session(SESSION_ID_V2).version == 0
    assert expected.request_fingerprint != drift.request_fingerprint
