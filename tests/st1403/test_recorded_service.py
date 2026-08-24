"""Application and recorded-adapter behavior for ST-1403."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from typing import cast

import pytest

from raos.adapters.recorded_refresh_proposal import (
    RecordedRefreshProposalAdapter,
    RecordedRefreshProposalFixture,
)
from raos.application.freshness.refresh_proposal import (
    RefreshProposalService,
    bind_refresh_proposal_request,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.policy_engine_v2 import (
    PolicyEvaluationEnvelopeV2,
    PolicyEvaluationReportV2,
    evaluate_editorial_policy_v2,
)
from raos.domain.freshness.freshness import (
    FreshnessEvaluation,
    FreshnessEvaluationRequest,
)
from raos.domain.freshness.refresh_proposal import (
    MAX_RECORDED_REFRESH_PROPOSALS,
    RefreshChangeType,
    RefreshChangedEntityType,
    RefreshImpactLevel,
    RefreshProposal,
    RefreshProposalFailure,
    RefreshImpactSurface,
    RefreshProposalRequest,
    RefreshRequiredAction,
    build_refresh_proposal,
)
from raos.ports.refresh_proposal import RefreshProposalExchange
from raos.domain.shared.persistence import Sha256Digest

from conftest import (
    freshness_request,
    freshness_result,
    hex_digest,
    policy_result,
    proposal_candidate,
    recorded_adapter,
    refresh_diff,
    refresh_service,
    valid_policy_input,
)


class _CountingExchange:
    def __init__(self, outcome: object) -> None:
        self.calls = 0
        self.outcome = outcome

    def propose(self, request: RefreshProposalRequest) -> RefreshProposal:
        del request
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return cast(RefreshProposal, self.outcome)


class _MutatingExchange:
    def __init__(self, outcome: RefreshProposal) -> None:
        self.outcome = outcome
        self.calls = 0

    def propose(self, request: RefreshProposalRequest) -> RefreshProposal:
        self.calls += 1
        object.__setattr__(
            request.candidate,
            "candidate_snapshot_sha256",
            hex_digest("collaborator-mutation"),
        )
        return self.outcome


class _NestedMutatingExchange:
    def __init__(self, outcome: RefreshProposal) -> None:
        self.outcome = outcome

    def propose(self, request: RefreshProposalRequest) -> RefreshProposal:
        object.__setattr__(request.freshness, "live_eligible", True)
        return self.outcome


def _service(exchange: object) -> RefreshProposalService:
    return RefreshProposalService(
        environment=RuntimeEnvironment.ENV_DEV,
        exchange=cast(RefreshProposalExchange, exchange),
    )


@dataclass(frozen=True, slots=True)
class _BoundInputs:
    request: RefreshProposalRequest
    freshness_request: FreshnessEvaluationRequest
    freshness_result: FreshnessEvaluation
    policy_request: PolicyEvaluationEnvelopeV2
    policy_result: PolicyEvaluationReportV2


def _bound_inputs() -> _BoundInputs:
    exact_freshness_request = freshness_request()
    freshness = freshness_result(request=exact_freshness_request)
    exact_policy_request = valid_policy_input()
    policy = policy_result(exact_policy_request)
    request = bind_refresh_proposal_request(
        candidate=proposal_candidate(),
        freshness_request=exact_freshness_request,
        freshness_result=freshness,
        policy_request=exact_policy_request,
        policy_result=policy,
    )
    return _BoundInputs(
        request=request,
        freshness_request=exact_freshness_request,
        freshness_result=freshness,
        policy_request=exact_policy_request,
        policy_result=policy,
    )


@pytest.mark.parametrize(
    "environment",
    (RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI),
)
def test_exact_recorded_round_trip_is_available_only_in_dev_ci(
    environment: RuntimeEnvironment,
) -> None:
    candidate = proposal_candidate()
    exact_freshness_request = freshness_request()
    freshness = freshness_result(request=exact_freshness_request)
    exact_policy_request = valid_policy_input()
    policy = policy_result(exact_policy_request)
    request = bind_refresh_proposal_request(
        candidate=candidate,
        freshness_request=exact_freshness_request,
        freshness_result=freshness,
        policy_request=exact_policy_request,
        policy_result=policy,
    )
    proposal = build_refresh_proposal(request)
    adapter = RecordedRefreshProposalAdapter(
        environment=environment,
        fixture_capacity=1,
        fixtures=(RecordedRefreshProposalFixture(request, proposal),),
    )
    service = RefreshProposalService(environment=environment, exchange=adapter)

    result = service.propose(
        candidate=candidate,
        freshness_request=exact_freshness_request,
        freshness_result=freshness,
        policy_request=exact_policy_request,
        policy_result=policy,
    )

    assert result == proposal
    assert result.fingerprint == proposal.fingerprint


@pytest.mark.parametrize(
    "environment",
    (
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ),
)
def test_non_dev_ci_service_and_adapter_are_disabled(
    environment: RuntimeEnvironment,
) -> None:
    with pytest.raises(RefreshProposalFailure) as service_failure:
        RefreshProposalService(
            environment=environment,
            exchange=recorded_adapter(),
        )
    assert service_failure.value.code == "DEVELOPMENT_ONLY"

    inputs = _bound_inputs()
    with pytest.raises(RefreshProposalFailure) as adapter_failure:
        RecordedRefreshProposalAdapter(
            environment=environment,
            fixture_capacity=1,
            fixtures=(
                RecordedRefreshProposalFixture(
                    inputs.request,
                    build_refresh_proposal(inputs.request),
                ),
            ),
        )
    assert adapter_failure.value.code == "INVALID_ARGUMENT"


def test_service_calls_exchange_once_and_returns_owned_expected_value() -> None:
    inputs = _bound_inputs()
    expected = build_refresh_proposal(inputs.request)
    exchange = _CountingExchange(expected)

    result = _service(exchange).propose(
        candidate=inputs.request.candidate,
        freshness_request=inputs.freshness_request,
        freshness_result=inputs.freshness_result,
        policy_request=inputs.policy_request,
        policy_result=inputs.policy_result,
    )

    assert exchange.calls == 1
    assert result == expected
    assert result is not exchange.outcome


def test_exchange_exception_is_sanitized_as_unavailable() -> None:
    inputs = _bound_inputs()
    exchange = _CountingExchange(RuntimeError("untrusted collaborator material"))

    with pytest.raises(RefreshProposalFailure) as caught:
        _service(exchange).propose(
            candidate=inputs.request.candidate,
            freshness_request=inputs.freshness_request,
            freshness_result=inputs.freshness_result,
            policy_request=inputs.policy_request,
            policy_result=inputs.policy_result,
        )

    assert caught.value.code == "PROPOSER_UNAVAILABLE"
    assert "untrusted" not in str(caught.value)
    assert exchange.calls == 1


def test_exchange_cannot_mutate_the_sent_request() -> None:
    inputs = _bound_inputs()
    exchange = _MutatingExchange(build_refresh_proposal(inputs.request))

    with pytest.raises(RefreshProposalFailure) as caught:
        _service(exchange).propose(
            candidate=inputs.request.candidate,
            freshness_request=inputs.freshness_request,
            freshness_result=inputs.freshness_result,
            policy_request=inputs.policy_request,
            policy_result=inputs.policy_result,
        )

    assert caught.value.code == "PROPOSAL_MISMATCH"
    assert exchange.calls == 1
    assert inputs.request.candidate.candidate_snapshot_sha256 != hex_digest(
        "collaborator-mutation"
    )


def test_exchange_cannot_mutate_shared_nested_evidence() -> None:
    inputs = _bound_inputs()
    exchange = _NestedMutatingExchange(build_refresh_proposal(inputs.request))

    with pytest.raises(RefreshProposalFailure) as caught:
        _service(exchange).propose(
            candidate=inputs.request.candidate,
            freshness_request=inputs.freshness_request,
            freshness_result=inputs.freshness_result,
            policy_request=inputs.policy_request,
            policy_result=inputs.policy_result,
        )

    assert caught.value.code == "PROPOSAL_MISMATCH"
    assert inputs.request.freshness.live_eligible is False


def test_valid_but_different_exchange_outcome_is_rejected() -> None:
    inputs = _bound_inputs()
    other_request = bind_refresh_proposal_request(
        candidate=proposal_candidate(
            diffs=(replace(refresh_diff(), changed_entity_id="ENTITY-OTHER"),)
        ),
        freshness_request=inputs.freshness_request,
        freshness_result=inputs.freshness_result,
        policy_request=inputs.policy_request,
        policy_result=inputs.policy_result,
    )
    exchange = _CountingExchange(build_refresh_proposal(other_request))

    with pytest.raises(RefreshProposalFailure) as caught:
        _service(exchange).propose(
            candidate=inputs.request.candidate,
            freshness_request=inputs.freshness_request,
            freshness_result=inputs.freshness_result,
            policy_request=inputs.policy_request,
            policy_result=inputs.policy_result,
        )

    assert caught.value.code == "PROPOSAL_MISMATCH"
    assert exchange.calls == 1


def test_recorded_adapter_rejects_unbound_requests() -> None:
    adapter = recorded_adapter()
    candidate = proposal_candidate(
        diffs=(replace(refresh_diff(), changed_entity_id="ENTITY-UNBOUND"),)
    )
    exact_freshness_request = freshness_request()
    exact_policy_request = valid_policy_input()
    request = bind_refresh_proposal_request(
        candidate=candidate,
        freshness_request=exact_freshness_request,
        freshness_result=freshness_result(request=exact_freshness_request),
        policy_request=exact_policy_request,
        policy_result=policy_result(exact_policy_request),
    )

    with pytest.raises(RefreshProposalFailure) as caught:
        adapter.propose(request)

    assert caught.value.code == "PROPOSER_UNAVAILABLE"


def test_policy_result_field_mismatch_fails_before_exchange() -> None:
    inputs = _bound_inputs()
    policy = replace(inputs.policy_result, local_eligibility=False)
    exchange = _CountingExchange(object())

    with pytest.raises(RefreshProposalFailure) as caught:
        _service(exchange).propose(
            candidate=inputs.request.candidate,
            freshness_request=inputs.freshness_request,
            freshness_result=inputs.freshness_result,
            policy_request=inputs.policy_request,
            policy_result=policy,
        )

    assert caught.value.code == "POLICY_RESULT_INVALID"
    assert exchange.calls == 0


def test_policy_result_digest_mismatch_fails_before_exchange() -> None:
    inputs = _bound_inputs()
    policy = replace(inputs.policy_result, report_sha256=Sha256Digest("0" * 64))
    exchange = _CountingExchange(object())

    with pytest.raises(RefreshProposalFailure) as caught:
        _service(exchange).propose(
            candidate=inputs.request.candidate,
            freshness_request=inputs.freshness_request,
            freshness_result=inputs.freshness_result,
            policy_request=inputs.policy_request,
            policy_result=policy,
        )

    assert caught.value.code == "POLICY_RESULT_INVALID"
    assert exchange.calls == 0


@pytest.mark.parametrize(
    "coordinate",
    (
        "canonical_ast_sha256",
        "coverage_report_sha256",
        "recommendation_report_sha256",
        "evaluation_input_sha256",
        "policy_result_sha256",
    ),
)
def test_policy_report_internal_drift_fails_before_exchange(
    coordinate: str,
) -> None:
    inputs = _bound_inputs()
    forged = replace(
        inputs.policy_result,
        **{coordinate: Sha256Digest(hex_digest(f"forged-{coordinate}"))},
    )
    exchange = _CountingExchange(object())

    with pytest.raises(RefreshProposalFailure) as caught:
        _service(exchange).propose(
            candidate=inputs.request.candidate,
            freshness_request=inputs.freshness_request,
            freshness_result=inputs.freshness_result,
            policy_request=inputs.policy_request,
            policy_result=forged,
        )

    assert caught.value.code == "POLICY_RESULT_INVALID"
    assert exchange.calls == 0


def test_policy_request_internal_coordinate_drift_fails_before_exchange() -> None:
    inputs = _bound_inputs()
    forged_request = replace(
        inputs.policy_request,
        contract=replace(
            inputs.policy_request.contract,
            policy_catalog_sha256=Sha256Digest(hex_digest("forged-contract")),
        ),
    )
    exchange = _CountingExchange(object())

    with pytest.raises(RefreshProposalFailure) as caught:
        _service(exchange).propose(
            candidate=inputs.request.candidate,
            freshness_request=inputs.freshness_request,
            freshness_result=inputs.freshness_result,
            policy_request=forged_request,
            policy_result=inputs.policy_result,
        )

    assert caught.value.code == "POLICY_RESULT_INVALID"
    assert exchange.calls == 0


def test_matching_policy_ineligible_pair_fails_before_exchange() -> None:
    inputs = _bound_inputs()
    invalid_request = replace(
        inputs.policy_request,
        contract=replace(
            inputs.policy_request.contract,
            policy_catalog_sha256=Sha256Digest(hex_digest("invalid-contract")),
        ),
    )
    invalid_result = evaluate_editorial_policy_v2(invalid_request)
    assert invalid_result.local_eligibility is False
    exchange = _CountingExchange(object())

    with pytest.raises(RefreshProposalFailure) as caught:
        _service(exchange).propose(
            candidate=inputs.request.candidate,
            freshness_request=inputs.freshness_request,
            freshness_result=inputs.freshness_result,
            policy_request=invalid_request,
            policy_result=invalid_result,
        )

    assert caught.value.code == "POLICY_INELIGIBLE"
    assert exchange.calls == 0


def test_freshness_request_fingerprint_drift_fails_before_exchange() -> None:
    inputs = _bound_inputs()
    forged = replace(
        inputs.freshness_result,
        request_fingerprint=hex_digest("forged-freshness-request"),
    )
    exchange = _CountingExchange(object())

    with pytest.raises(RefreshProposalFailure) as caught:
        _service(exchange).propose(
            candidate=inputs.request.candidate,
            freshness_request=inputs.freshness_request,
            freshness_result=forged,
            policy_request=inputs.policy_request,
            policy_result=inputs.policy_result,
        )

    assert caught.value.code == "FRESHNESS_RESULT_INVALID"
    assert exchange.calls == 0


def test_impossible_fresh_age_pair_fails_before_exchange() -> None:
    inputs = _bound_inputs()
    impossible = replace(
        inputs.freshness_result,
        age_microseconds=int(timedelta(hours=100).total_seconds() * 1_000_000),
    )
    exchange = _CountingExchange(object())

    with pytest.raises(RefreshProposalFailure) as caught:
        _service(exchange).propose(
            candidate=inputs.request.candidate,
            freshness_request=inputs.freshness_request,
            freshness_result=impossible,
            policy_request=inputs.policy_request,
            policy_result=inputs.policy_result,
        )

    assert caught.value.code == "FRESHNESS_RESULT_INVALID"
    assert exchange.calls == 0


def test_freshness_request_result_pair_mismatch_fails_before_exchange() -> None:
    inputs = _bound_inputs()
    different_request = freshness_request(age=timedelta(hours=30))
    exchange = _CountingExchange(object())

    with pytest.raises(RefreshProposalFailure) as caught:
        _service(exchange).propose(
            candidate=inputs.request.candidate,
            freshness_request=different_request,
            freshness_result=inputs.freshness_result,
            policy_request=inputs.policy_request,
            policy_result=inputs.policy_result,
        )

    assert caught.value.code == "FRESHNESS_RESULT_INVALID"
    assert exchange.calls == 0


def test_review_candidate_cannot_bind_projection_only_none_diff() -> None:
    exact_freshness_request = freshness_request(recommendation_basis_affected=True)
    exact_policy_request = valid_policy_input()
    candidate = proposal_candidate(
        diffs=(
            refresh_diff(
                change_type=RefreshChangeType.PRICE,
                changed_entity_type=RefreshChangedEntityType.OFFER,
                impact_level=RefreshImpactLevel.LOW,
                required_action=RefreshRequiredAction.NONE,
                impact_surfaces=(RefreshImpactSurface.DYNAMIC_PUBLIC_PROJECTION,),
                affected_claim_ids=(),
            ),
        )
    )
    exchange = _CountingExchange(object())

    with pytest.raises(RefreshProposalFailure) as caught:
        _service(exchange).propose(
            candidate=candidate,
            freshness_request=exact_freshness_request,
            freshness_result=freshness_result(request=exact_freshness_request),
            policy_request=exact_policy_request,
            policy_result=policy_result(exact_policy_request),
        )

    assert caught.value.code == "CROSS_INPUT_MISMATCH"
    assert exchange.calls == 0


def test_recommendation_diff_requires_matching_freshness_review_marker() -> None:
    exact_freshness_request = freshness_request(recommendation_basis_affected=False)
    exact_policy_request = valid_policy_input()
    candidate = proposal_candidate(
        diffs=(
            refresh_diff(
                impact_surfaces=(RefreshImpactSurface.RECOMMENDATION,),
            ),
        )
    )
    exchange = _CountingExchange(object())

    with pytest.raises(RefreshProposalFailure) as caught:
        _service(exchange).propose(
            candidate=candidate,
            freshness_request=exact_freshness_request,
            freshness_result=freshness_result(request=exact_freshness_request),
            policy_request=exact_policy_request,
            policy_result=policy_result(exact_policy_request),
        )

    assert caught.value.code == "CROSS_INPUT_MISMATCH"
    assert exchange.calls == 0


def test_malformed_freshness_result_fails_before_exchange() -> None:
    inputs = _bound_inputs()
    freshness = inputs.freshness_result
    object.__setattr__(freshness, "live_eligible", True)
    exchange = _CountingExchange(object())

    with pytest.raises(RefreshProposalFailure) as caught:
        _service(exchange).propose(
            candidate=inputs.request.candidate,
            freshness_request=inputs.freshness_request,
            freshness_result=freshness,
            policy_request=inputs.policy_request,
            policy_result=inputs.policy_result,
        )

    assert caught.value.code == "FRESHNESS_RESULT_INVALID"
    assert exchange.calls == 0


def test_fixture_mismatch_and_duplicate_binding_fail_closed() -> None:
    inputs = _bound_inputs()
    other_request = bind_refresh_proposal_request(
        candidate=proposal_candidate(
            diffs=(replace(refresh_diff(), changed_entity_id="ENTITY-OTHER"),)
        ),
        freshness_request=inputs.freshness_request,
        freshness_result=inputs.freshness_result,
        policy_request=inputs.policy_request,
        policy_result=inputs.policy_result,
    )
    with pytest.raises(RefreshProposalFailure) as mismatch:
        RecordedRefreshProposalFixture(
            inputs.request,
            build_refresh_proposal(other_request),
        )
    assert mismatch.value.code == "PROPOSAL_MISMATCH"

    fixture = RecordedRefreshProposalFixture(
        inputs.request,
        build_refresh_proposal(inputs.request),
    )
    with pytest.raises(RefreshProposalFailure) as duplicate:
        RecordedRefreshProposalAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            fixture_capacity=2,
            fixtures=(fixture, fixture),
        )
    assert duplicate.value.code == "INVALID_ARGUMENT"


@pytest.mark.parametrize(
    "capacity",
    (False, 0, MAX_RECORDED_REFRESH_PROPOSALS + 1),
)
def test_recorded_adapter_capacity_is_exactly_bounded(capacity: object) -> None:
    inputs = _bound_inputs()
    fixture = RecordedRefreshProposalFixture(
        inputs.request,
        build_refresh_proposal(inputs.request),
    )

    with pytest.raises(RefreshProposalFailure) as caught:
        RecordedRefreshProposalAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            fixture_capacity=cast(int, capacity),
            fixtures=(fixture,),
        )

    assert caught.value.code == "INVALID_ARGUMENT"


def test_recorded_adapter_requires_at_least_one_exact_fixture() -> None:
    with pytest.raises(RefreshProposalFailure) as caught:
        RecordedRefreshProposalAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            fixture_capacity=1,
            fixtures=(),
        )

    assert caught.value.code == "INVALID_ARGUMENT"


def test_convenience_service_remains_exactly_fixture_bound() -> None:
    candidate = proposal_candidate()
    exact_freshness_request = freshness_request()
    freshness = freshness_result(request=exact_freshness_request)
    exact_policy_request = valid_policy_input()
    policy = policy_result(exact_policy_request)
    service = refresh_service(
        candidate=candidate,
        freshness_request_value=exact_freshness_request,
        freshness=freshness,
        policy_request_value=exact_policy_request,
        policy=policy,
    )

    result = service.propose(
        candidate=candidate,
        freshness_request=exact_freshness_request,
        freshness_result=freshness,
        policy_request=exact_policy_request,
        policy_result=policy,
    )

    assert result.can_change_state is False
    assert result.authority.value == "UNAPPROVED_PROPOSAL"
