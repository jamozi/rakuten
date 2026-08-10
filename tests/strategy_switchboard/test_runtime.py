from __future__ import annotations

from collections.abc import Mapping

import pytest

from scripts import build_all_story_strategy_catalog as generator

from raos.strategy_switchboard.catalog import (
    ADVANCED_EXTERNAL_PROFILE,
    BALANCED_STAGING_PROFILE,
    SAFE_LOCAL_PROFILE,
    build_complete_catalog,
)
from raos.strategy_switchboard.model import (
    Environment,
    GateContext,
    StrategySelectionError,
)
from raos.strategy_switchboard.runtime import StrategyRuntime
from raos.strategy_switchboard.switchboard import StrategySwitchboard


class EchoAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Mapping[str, object]]] = []

    def execute(
        self,
        *,
        boundary_id: str,
        strategy_id: str,
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        self.calls.append((boundary_id, strategy_id, payload))
        return {"echo": payload.get("value"), "ok": True}


class RaisingAdapter:
    def execute(
        self,
        *,
        boundary_id: str,
        strategy_id: str,
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        del boundary_id, strategy_id, payload
        raise RuntimeError("raw provider body must not escape")


class InvalidResultAdapter:
    def execute(
        self,
        *,
        boundary_id: str,
        strategy_id: str,
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        del boundary_id, strategy_id, payload
        return {"invalid": float("nan")}


def _switchboard() -> StrategySwitchboard:
    story_ids = generator.canonical_story_ids(generator.REPOSITORY_ROOT)
    return StrategySwitchboard(build_complete_catalog(story_ids))


def _advanced_category_context() -> GateContext:
    return GateContext(
        environment=Environment.PRODUCTION,
        approvals=frozenset({"OD-001", "production-use"}),
        evidence=frozenset({"category-portfolio-evidence"}),
        capabilities=frozenset({"external-io"}),
    )


def test_deterministic_plan_executes_without_adapter_or_payload_disclosure() -> None:
    runtime = StrategyRuntime(switchboard=_switchboard())

    execution = runtime.execute(
        boundary_id="OD-001",
        profile=SAFE_LOCAL_PROFILE,
        context=GateContext.local_empty(),
        payload={"sensitive": "not-recorded"},
    )

    assert execution.status == "planned"
    assert execution.side_effects == ()
    assert execution.result["status"] == "planned"
    assert execution.result["payload_sha256"] == execution.payload_sha256
    assert b"not-recorded" not in execution.result_bytes


def test_manual_strategy_requires_nonempty_explicit_input() -> None:
    runtime = StrategyRuntime(switchboard=_switchboard())
    context = GateContext(
        environment=Environment.LOCAL,
        approvals=frozenset({"OD-003"}),
        evidence=frozenset({"anonymized-report-sample"}),
    )

    with pytest.raises(StrategySelectionError) as captured:
        runtime.execute(
            boundary_id="OD-003",
            profile=BALANCED_STAGING_PROFILE,
            context=context,
            payload={},
        )

    assert captured.value.code == "STRATEGY_MANUAL_INPUT_REQUIRED"


def test_manual_strategy_accepts_reviewed_payload_without_storing_content() -> None:
    runtime = StrategyRuntime(switchboard=_switchboard())
    context = GateContext(
        environment=Environment.LOCAL,
        approvals=frozenset({"OD-003"}),
        evidence=frozenset({"anonymized-report-sample"}),
    )

    execution = runtime.execute(
        boundary_id="OD-003",
        profile=BALANCED_STAGING_PROFILE,
        context=context,
        payload={"sample": "reviewed-but-content-free-at-runtime-boundary"},
    )

    assert execution.status == "accepted"
    assert execution.result["status"] == "accepted"
    assert b"reviewed-but-content-free-at-runtime-boundary" not in execution.result_bytes


def test_advanced_strategy_requires_injected_adapter() -> None:
    runtime = StrategyRuntime(switchboard=_switchboard())

    with pytest.raises(StrategySelectionError) as captured:
        runtime.execute(
            boundary_id="OD-001",
            profile=ADVANCED_EXTERNAL_PROFILE,
            context=_advanced_category_context(),
            payload={"value": "x"},
        )

    assert captured.value.code == "STRATEGY_ADAPTER_MISSING"
    assert captured.value.strategy_id == "OD-001:approved-multi-category"


def test_advanced_strategy_executes_injected_adapter_after_all_gates() -> None:
    adapter = EchoAdapter()
    runtime = StrategyRuntime(
        switchboard=_switchboard(),
        adapters={"category.portfolio": adapter},
    )

    execution = runtime.execute(
        boundary_id="OD-001",
        profile=ADVANCED_EXTERNAL_PROFILE,
        context=_advanced_category_context(),
        payload={"value": "approved"},
    )

    assert execution.status == "executed"
    assert execution.side_effects == ("external-read",)
    assert execution.result["adapter_result"] == {"echo": "approved", "ok": True}
    assert len(adapter.calls) == 1
    assert adapter.calls[0][0:2] == (
        "OD-001",
        "OD-001:approved-multi-category",
    )


def test_adapter_exception_is_replaced_by_stable_content_free_error() -> None:
    runtime = StrategyRuntime(
        switchboard=_switchboard(),
        adapters={"category.portfolio": RaisingAdapter()},
    )

    with pytest.raises(StrategySelectionError) as captured:
        runtime.execute(
            boundary_id="OD-001",
            profile=ADVANCED_EXTERNAL_PROFILE,
            context=_advanced_category_context(),
            payload={"value": "approved"},
        )

    assert captured.value.code == "STRATEGY_ADAPTER_FAILED"
    assert str(captured.value) == "STRATEGY_ADAPTER_FAILED"
    assert captured.value.__cause__ is None
    assert "raw provider body" not in str(captured.value)


def test_non_json_payload_fails_before_selection_or_adapter_execution() -> None:
    adapter = EchoAdapter()
    runtime = StrategyRuntime(
        switchboard=_switchboard(),
        adapters={"category.portfolio": adapter},
    )

    with pytest.raises(StrategySelectionError) as captured:
        runtime.execute(
            boundary_id="OD-001",
            profile=ADVANCED_EXTERNAL_PROFILE,
            context=_advanced_category_context(),
            payload={"invalid": float("nan")},
        )

    assert captured.value.code == "STRATEGY_PAYLOAD_INVALID"
    assert adapter.calls == []


def test_invalid_adapter_result_is_sanitized() -> None:
    runtime = StrategyRuntime(
        switchboard=_switchboard(),
        adapters={"category.portfolio": InvalidResultAdapter()},
    )

    with pytest.raises(StrategySelectionError) as captured:
        runtime.execute(
            boundary_id="OD-001",
            profile=ADVANCED_EXTERNAL_PROFILE,
            context=_advanced_category_context(),
            payload={"value": "approved"},
        )

    assert captured.value.code == "STRATEGY_ADAPTER_RESULT_INVALID"
