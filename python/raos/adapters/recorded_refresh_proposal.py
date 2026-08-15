"""Bounded immutable DEV/CI fixtures for ST-1403 refresh proposals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.freshness.refresh_proposal import (
    MAX_RECORDED_REFRESH_PROPOSALS,
    EditorialPolicyEvidenceBinding,
    FreshnessEvidenceBinding,
    RefreshDiff,
    RefreshProposal,
    RefreshProposalCandidate,
    RefreshProposalFailureCode,
    RefreshProposalRequest,
    build_refresh_proposal,
    fail_refresh_proposal,
)


def _snapshot_diff(value: RefreshDiff) -> RefreshDiff:
    return RefreshDiff(
        diff_id=value.diff_id,
        kind=value.kind,
        change_type=value.change_type,
        changed_entity_type=value.changed_entity_type,
        changed_entity_id=value.changed_entity_id,
        before_sha256=value.before_sha256,
        after_sha256=value.after_sha256,
        affected_claim_ids=value.affected_claim_ids,
        impact_level=value.impact_level,
        required_action=value.required_action,
        impact_surfaces=value.impact_surfaces,
        action_type=value.action_type,
        deterministic_priority_rank=value.deterministic_priority_rank,
        recommendation_rank_change=value.recommendation_rank_change,
    )


def _snapshot_candidate(value: RefreshProposalCandidate) -> RefreshProposalCandidate:
    return RefreshProposalCandidate(
        article_version_id=value.article_version_id,
        baseline_publication_snapshot_sha256=(
            value.baseline_publication_snapshot_sha256
        ),
        candidate_snapshot_sha256=value.candidate_snapshot_sha256,
        diffs=tuple(_snapshot_diff(item) for item in value.diffs),
    )


def _snapshot_freshness(value: FreshnessEvidenceBinding) -> FreshnessEvidenceBinding:
    return FreshnessEvidenceBinding(
        evaluation_fingerprint=value.evaluation_fingerprint,
        request_fingerprint=value.request_fingerprint,
        policy_binding_fingerprint=value.policy_binding_fingerprint,
        freshness_class_id=value.freshness_class_id,
        state=value.state,
        projection_action=value.projection_action,
        review_action=value.review_action,
        recommendation_order_action=value.recommendation_order_action,
        policy_activation=value.policy_activation,
        open_decision_id=value.open_decision_id,
        open_decision_status=value.open_decision_status,
        policy_active=value.policy_active,
        persistence=value.persistence,
        attestation=value.attestation,
        live_eligible=value.live_eligible,
    )


def _snapshot_editorial_policy(
    value: EditorialPolicyEvidenceBinding,
) -> EditorialPolicyEvidenceBinding:
    return EditorialPolicyEvidenceBinding(
        article_version_id=value.article_version_id,
        local_result_digest=value.local_result_digest,
        serialization_profile=value.serialization_profile,
        status=value.status,
        local_eligibility=value.local_eligibility,
        publication_authorized=value.publication_authorized,
        production_eligible=value.production_eligible,
        formal_test_status=value.formal_test_status,
        live_validation_status=value.live_validation_status,
        staging_status=value.staging_status,
        release_status=value.release_status,
        production_status=value.production_status,
    )


def _snapshot_request(value: object) -> RefreshProposalRequest:
    snapshot: RefreshProposalRequest | None = None
    matches = False
    if type(value) is RefreshProposalRequest:
        try:
            source_fingerprint = value.fingerprint
            snapshot = RefreshProposalRequest(
                candidate=_snapshot_candidate(value.candidate),
                freshness=_snapshot_freshness(value.freshness),
                editorial_policy=_snapshot_editorial_policy(value.editorial_policy),
            )
            matches = (
                snapshot == value
                and snapshot.fingerprint == source_fingerprint
                and value.fingerprint == source_fingerprint
            )
        except Exception:
            matches = False
    if snapshot is None or not matches:
        fail_refresh_proposal()
    return snapshot


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedRefreshProposalFixture:
    request: RefreshProposalRequest
    proposal: RefreshProposal

    def __post_init__(self) -> None:
        request: RefreshProposalRequest | None = None
        expected: RefreshProposal | None = None
        matches = False
        if (
            type(self.request) is RefreshProposalRequest
            and type(self.proposal) is RefreshProposal
        ):
            try:
                request = _snapshot_request(self.request)
                expected = build_refresh_proposal(request)
                self.proposal.__post_init__()
                matches = (
                    self.proposal == expected
                    and self.proposal.fingerprint == expected.fingerprint
                )
            except Exception:
                matches = False
        if request is None or expected is None or not matches:
            fail_refresh_proposal(RefreshProposalFailureCode.PROPOSAL_MISMATCH)
        object.__setattr__(self, "request", request)
        object.__setattr__(self, "proposal", expected)

    def __repr__(self) -> str:
        return "RecordedRefreshProposalFixture(<redacted-st1403-refresh-proposal>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("refresh proposal fixture serialization is not supported")


def _fixture_binding(
    fixture: RecordedRefreshProposalFixture,
) -> tuple[str, str]:
    fixture.__post_init__()
    request = _snapshot_request(fixture.request)
    expected = build_refresh_proposal(request)
    if (
        fixture.proposal != expected
        or fixture.proposal.fingerprint != expected.fingerprint
    ):
        fail_refresh_proposal(RefreshProposalFailureCode.PROPOSAL_MISMATCH)
    return request.fingerprint, expected.fingerprint


@final
class RecordedRefreshProposalAdapter:
    """Return only exact deterministic fixture outcomes without state writes."""

    __slots__ = ("_bindings",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        fixture_capacity: int,
        fixtures: tuple[RecordedRefreshProposalFixture, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(fixture_capacity) is not int
            or not 1 <= fixture_capacity <= MAX_RECORDED_REFRESH_PROPOSALS
            or type(fixtures) is not tuple
            or not 1 <= len(fixtures) <= fixture_capacity
            or any(
                type(item) is not RecordedRefreshProposalFixture for item in fixtures
            )
        ):
            fail_refresh_proposal()
        bindings: tuple[tuple[str, str], ...] = ()
        try:
            bindings = tuple(_fixture_binding(fixture) for fixture in fixtures)
        except Exception:
            fail_refresh_proposal()
        request_fingerprints = tuple(binding[0] for binding in bindings)
        if len(set(request_fingerprints)) != len(request_fingerprints):
            fail_refresh_proposal()
        self._bindings = bindings

    def __repr__(self) -> str:
        return "RecordedRefreshProposalAdapter(<redacted-st1403-refresh-proposal>)"

    def __str__(self) -> str:
        return "<redacted-st1403-refresh-proposal>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("refresh proposal adapter serialization is not supported")

    def propose(self, request: RefreshProposalRequest) -> RefreshProposal:
        snapshot = _snapshot_request(request)
        proposal = build_refresh_proposal(snapshot)
        matches = tuple(
            binding
            for binding in self._bindings
            if binding == (snapshot.fingerprint, proposal.fingerprint)
        )
        if len(matches) != 1:
            fail_refresh_proposal(RefreshProposalFailureCode.PROPOSER_UNAVAILABLE)
        return proposal


__all__ = [
    "RecordedRefreshProposalAdapter",
    "RecordedRefreshProposalFixture",
]
