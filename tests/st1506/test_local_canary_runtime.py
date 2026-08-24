"""Positive and closed-state evidence for the ST-1506 V2 local runtime."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from raos.adapters.disabled_production_activation import DisabledProductionActivation
from raos.adapters.recorded_production_canary import RecordedProductionCanaryJournal
from raos.application.ops.production_canary import (
    LocalProductionCanaryRun,
    LocalProductionCanaryService,
)
from raos.domain.ops.production_canary import (
    APPROVAL_NAMES,
    CanaryCommandKind,
    CanaryOutcome,
    CanarySession,
    CanaryState,
    EXTERNAL_ACTION_NAMES,
    ProductionCanaryError,
    ProductionCanarySpec,
    ReleasePhase,
    SyntheticObservation,
    advance_once,
)
from raos.production_canary_runner import (
    load_local_production_canary_spec,
    recorded_observations,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def spec() -> ProductionCanarySpec:
    return load_local_production_canary_spec(REPOSITORY_ROOT)


@pytest.fixture
def private_root(tmp_path: Path) -> Path:
    root = tmp_path / "owner-private"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    return root


def _service(
    spec: ProductionCanarySpec, private_root: Path
) -> LocalProductionCanaryService:
    return LocalProductionCanaryService(
        spec=spec,
        activation=DisabledProductionActivation(),
        journal=RecordedProductionCanaryJournal(private_root=private_root),
    )


def _observation(
    spec: ProductionCanarySpec,
    **overrides: object,
) -> SyntheticObservation:
    values: dict[str, object] = {
        "scenario_id": "st1506-custom-observation-v2",
        "source": "SYNTHETIC_RECORDED_FIXTURE_ONLY",
        "cohort_id": spec.cohort_id,
        "release_phase": ReleasePhase.CANARY,
        "contract_sha256": spec.semantic_sha256,
        "artifact_sha256": spec.artifact_sha256,
        "staging_result_sha256": spec.staging_result_sha256,
        "observed_at_epoch_seconds": 2_000_000_000,
        "evaluated_at_epoch_seconds": 2_000_000_060,
        "sample_count": 5,
        "window_seconds": 120,
        "error_rate_ppm": 100,
        "latency_p95_milliseconds": 250,
        "health_failure_count": 0,
        "critical_alert_count": 0,
        "kill_switch_triggered": False,
        "external_action_count": 0,
    }
    values.update(overrides)
    return SyntheticObservation(**values)  # type: ignore[arg-type]


def test_contract_exactly_binds_predecessors_and_staging_admission(
    spec: ProductionCanarySpec,
) -> None:
    assert spec.semantic_sha256 == (
        "6c4576882e38afbddb89aa8c2f63c2d383127ad0c2b1c017f4a56693abb9ab6a"
    )
    assert [story for story, _ in spec.predecessor_hashes] == [
        "ST-1501",
        "ST-1502",
        "ST-1503",
        "ST-1504",
        "ST-1505",
    ]
    assert spec.staging_contract_semantic_sha256 == (
        "509bfd0102d54c035e4c514b30389936695f8779c39adf02340fa66706c314fd"
    )
    assert spec.staging_result_sha256 == (
        "696668a3f9dc74e6de614cad18c4185b30cd2658c39f547d8070cbf733a342e9"
    )
    assert spec.artifact_sha256 == (
        "d615727014ef5fd32023e7d1ce745cc89c08cbfde37d2838ace4acf3956cc345"
    )
    assert spec.sbom_sha256 == (
        "171cd38d63d5e37c8ec352a1a5fe8e735524d8fcf5bd909342e1536ce4a1a3df"
    )
    assert spec.provenance_sha256 == (
        "254caf782caa5f8417f27d559231f594b37de21cd5a9da47a2874d532145211e"
    )


def test_every_external_action_is_exactly_zero(spec: ProductionCanarySpec) -> None:
    assert spec.action_counts == tuple((name, 0) for name in EXTERNAL_ACTION_NAMES)
    activation = DisabledProductionActivation()
    assert activation.mode == "DISABLED_RECORDED_LOCAL_ONLY"
    assert activation.external_action_counts == spec.action_counts


def test_recorded_scenarios_cover_human_hold_abort_and_rollback(
    spec: ProductionCanarySpec,
) -> None:
    observations = recorded_observations(REPOSITORY_ROOT, spec)
    expected = [
        (CanaryOutcome.HUMAN_APPROVALS_REQUIRED, CanaryState.HOLD_FOR_HUMAN_APPROVAL),
        (CanaryOutcome.ABORT_REQUIRED, CanaryState.ABORT_REQUIRED),
        (CanaryOutcome.ROLLBACK_REQUIRED, CanaryState.ROLLBACK_REQUIRED),
    ]
    for index, (observation, expected_pair) in enumerate(
        zip(observations, expected, strict=True), start=1
    ):
        initial = CanarySession(
            run_id=f"st1506-run-scenario-{index}",
            version=0,
            state=CanaryState.CANARY_READY,
        )
        started = advance_once(
            spec,
            initial,
            command=CanaryCommandKind.START_CANARY_SIMULATION,
            observation=None,
        )
        decided = advance_once(
            spec,
            started.session,
            command=CanaryCommandKind.RECORD_SYNTHETIC_OBSERVATION,
            observation=observation,
        )
        assert (decided.outcome, decided.session.state) == expected_pair


def test_explicit_two_step_runtime_persists_only_synthetic_result(
    spec: ProductionCanarySpec, private_root: Path
) -> None:
    service = _service(spec, private_root)
    started = service.execute(
        LocalProductionCanaryRun(
            run_id="st1506-run-runtime-healthy",
            idempotency_key="st1506-key-runtime-start",
            command=CanaryCommandKind.START_CANARY_SIMULATION,
            observation=None,
        )
    )
    assert started.result_document["to_state"] == "OBSERVE"
    assert started.result_document["outcome"] == "OBSERVE_REQUIRED"
    decided = service.execute(
        LocalProductionCanaryRun(
            run_id="st1506-run-runtime-healthy",
            idempotency_key="st1506-key-runtime-observe",
            command=CanaryCommandKind.RECORD_SYNTHETIC_OBSERVATION,
            observation=_observation(spec),
        )
    )
    assert decided.result_document["to_state"] == "HOLD_FOR_HUMAN_APPROVAL"
    assert decided.result_document["outcome"] == "HUMAN_APPROVALS_REQUIRED"
    assert decided.persistence.current_version == 2
    assert decided.persistence.sequence == 2
    action_counts = decided.result_document["action_counts"]
    assert type(action_counts) is dict
    assert all(value == 0 for value in action_counts.values())
    approvals = decided.result_document["human_approvals"]
    assert type(approvals) is dict
    assert tuple(approvals) == APPROVAL_NAMES
    assert all(row["status"] == "ABSENT" for row in approvals.values())


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"evaluated_at_epoch_seconds": 1_999_999_999}, "FUTURE_OBSERVATION"),
        ({"evaluated_at_epoch_seconds": 2_000_000_301}, "STALE_OBSERVATION"),
        ({"contract_sha256": "f" * 64}, "CONTRACT_MISMATCH"),
        ({"artifact_sha256": "f" * 64}, "ARTIFACT_MISMATCH"),
        ({"staging_result_sha256": "f" * 64}, "STAGING_RESULT_MISMATCH"),
        ({"cohort_id": "st1506-other-cohort-v2"}, "COHORT_MISMATCH"),
        ({"sample_count": 2}, "IMMATURE_COHORT"),
        ({"window_seconds": 59}, "IMMATURE_COHORT"),
    ],
)
def test_untrusted_or_immature_observations_block_without_advancing(
    spec: ProductionCanarySpec,
    overrides: dict[str, object],
    reason: str,
) -> None:
    session = CanarySession(
        run_id="st1506-run-blocked-data",
        version=1,
        state=CanaryState.OBSERVE,
    )
    decision = advance_once(
        spec,
        session,
        command=CanaryCommandKind.RECORD_SYNTHETIC_OBSERVATION,
        observation=_observation(spec, **overrides),
    )
    assert decision.outcome is CanaryOutcome.DATA_BLOCKED
    assert decision.session.state is CanaryState.OBSERVE
    assert decision.block_reason == reason


def test_missing_observation_blocks(spec: ProductionCanarySpec) -> None:
    decision = advance_once(
        spec,
        CanarySession(
            run_id="st1506-run-missing-observation",
            version=1,
            state=CanaryState.OBSERVE,
        ),
        command=CanaryCommandKind.RECORD_SYNTHETIC_OBSERVATION,
        observation=None,
    )
    assert decision.outcome is CanaryOutcome.DATA_BLOCKED
    assert decision.block_reason == "MISSING_OBSERVATION"


@pytest.mark.parametrize(
    "state",
    [
        CanaryState.HOLD_FOR_HUMAN_APPROVAL,
        CanaryState.ABORT_REQUIRED,
        CanaryState.ROLLBACK_REQUIRED,
    ],
)
def test_terminal_states_cannot_advance(
    spec: ProductionCanarySpec, state: CanaryState
) -> None:
    with pytest.raises(ProductionCanaryError) as captured:
        advance_once(
            spec,
            CanarySession(
                run_id="st1506-run-terminal-state",
                version=2,
                state=state,
            ),
            command=CanaryCommandKind.RECORD_SYNTHETIC_OBSERVATION,
            observation=_observation(spec),
        )
    assert captured.value.code == "TERMINAL_STATE"


@pytest.mark.parametrize(
    "overrides",
    [
        {"source": "LIVE"},
        {"external_action_count": 1},
        {"sample_count": -1},
        {"kill_switch_triggered": 1},
        {"release_phase": "CANARY"},
    ],
)
def test_observation_constructor_rejects_unknown_or_unsafe_values(
    spec: ProductionCanarySpec, overrides: dict[str, object]
) -> None:
    with pytest.raises(ProductionCanaryError) as captured:
        _observation(spec, **overrides)
    assert captured.value.code == "OBSERVATION_INVALID"


def test_recorded_scenarios_reject_an_independently_forged_spec(
    spec: ProductionCanarySpec,
) -> None:
    forged = replace(spec, cohort_id="st1506-forged-cohort-v2")
    with pytest.raises(ProductionCanaryError) as captured:
        recorded_observations(REPOSITORY_ROOT, forged)
    assert captured.value.code == "SPEC_BINDING_MISMATCH"
