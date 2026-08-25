"""Bounded immutable DEV/CI fixtures for ST-1403 refresh proposals."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import NoReturn, SupportsIndex, cast, final

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


_MAX_RECORDED_RUNTIME_BYTES = 64 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_DEPENDENCY_BINDING_KEYS = (
    "canonicalDecisions",
    "canonicalIntegration",
    "canonicalOpenDecisions",
    "securePublication",
    "securityCatalog",
    "st0805Completion",
    "st0805Contract",
    "st0805Domain",
    "st0805Fixture",
    "st1401Completion",
    "st1401Domain",
    "storyBacklog",
    "testCatalog",
)


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_refresh_proposal()
    return value


def _object(value: object, keys: tuple[str, ...]) -> dict[str, object]:
    if type(value) is not dict:
        fail_refresh_proposal()
    validated = cast(dict[str, object], value)
    if set(validated) != set(keys):
        fail_refresh_proposal()
    return validated


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            fail_refresh_proposal()
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    del value
    fail_refresh_proposal()


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
        legacy_status=value.legacy_status,
        local_eligibility=value.local_eligibility,
        finding_proposal_only=value.finding_proposal_only,
        waiver_proposal_only=value.waiver_proposal_only,
        approval_authorized=value.approval_authorized,
        waiver_apply_authorized=value.waiver_apply_authorized,
        merge_authorized=value.merge_authorized,
        recommendation_override_authorized=(value.recommendation_override_authorized),
        ranking_override_authorized=value.ranking_override_authorized,
        publication_authorized=value.publication_authorized,
        activation_authorized=value.activation_authorized,
        production_eligible=value.production_eligible,
        formal_tst_019_status=value.formal_tst_019_status,
        formal_tst_020_status=value.formal_tst_020_status,
        formal_test_status=value.formal_test_status,
        live_validation_status=value.live_validation_status,
        staging_status=value.staging_status,
        release_status=value.release_status,
        publication_status=value.publication_status,
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


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedRefreshProposalBinding:
    request_fingerprint: str
    proposal_fingerprint: str

    def __post_init__(self) -> None:
        _sha256(self.request_fingerprint)
        _sha256(self.proposal_fingerprint)

    def __repr__(self) -> str:
        return "RecordedRefreshProposalBinding(<redacted-st1403-refresh-proposal>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("refresh proposal binding serialization is not supported")


def load_recorded_refresh_proposal_bindings(
    payload: bytes,
) -> tuple[RecordedRefreshProposalBinding, ...]:
    """Load only closed fingerprint bindings from an owner-generated record."""

    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > _MAX_RECORDED_RUNTIME_BYTES
        or payload.startswith(b"\xef\xbb\xbf")
    ):
        fail_refresh_proposal()
    try:
        decoded = payload.decode("utf-8", errors="strict")
        value = json.loads(
            decoded,
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except Exception:
        fail_refresh_proposal()
    root = _object(
        value,
        (
            "schemaVersion",
            "storyId",
            "classification",
            "environment",
            "recordedAt",
            "contractSha256",
            "dependencyBindings",
            "fixtureBindings",
            "authority",
            "formalStatus",
        ),
    )
    dependencies = _object(
        root["dependencyBindings"],
        _DEPENDENCY_BINDING_KEYS,
    )
    authority = _object(
        root["authority"],
        (
            "humanApprovalRequired",
            "proposalOnly",
            "automaticReorderingAuthorized",
            "canChangeState",
            "persistenceAuthorized",
            "publicationAuthorized",
            "releaseAuthorized",
            "productionEligible",
        ),
    )
    formal = _object(
        root["formalStatus"],
        (
            "TST-020",
            "TST-021",
            "hostedCi",
            "live",
            "staging",
            "publication",
            "release",
            "production",
        ),
    )
    fixtures_value = root["fixtureBindings"]
    if type(fixtures_value) is not list:
        fail_refresh_proposal()
    fixtures = cast(list[object], fixtures_value)
    _sha256(root["contractSha256"])
    for dependency_sha256 in dependencies.values():
        _sha256(dependency_sha256)
    if (
        root["schemaVersion"] != 2
        or root["storyId"] != "ST-1403"
        or root["classification"] != "RECORDED_SYNTHETIC_REFRESH_PROPOSAL_V2"
        or root["environment"] != "CI"
        or root["recordedAt"] != "2026-08-24T03:00:00Z"
        or authority
        != {
            "humanApprovalRequired": True,
            "proposalOnly": True,
            "automaticReorderingAuthorized": False,
            "canChangeState": False,
            "persistenceAuthorized": False,
            "publicationAuthorized": False,
            "releaseAuthorized": False,
            "productionEligible": False,
        }
        or set(formal.values()) != {"NOT_EXECUTED"}
        or not 1 <= len(fixtures) <= MAX_RECORDED_REFRESH_PROPOSALS
    ):
        fail_refresh_proposal()
    bindings: list[RecordedRefreshProposalBinding] = []
    for fixture in fixtures:
        item = _object(
            fixture,
            ("requestFingerprint", "proposalFingerprint"),
        )
        bindings.append(
            RecordedRefreshProposalBinding(
                request_fingerprint=_sha256(item["requestFingerprint"]),
                proposal_fingerprint=_sha256(item["proposalFingerprint"]),
            )
        )
    request_fingerprints = tuple(item.request_fingerprint for item in bindings)
    if len(set(request_fingerprints)) != len(request_fingerprints):
        fail_refresh_proposal()
    return tuple(bindings)


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
        fixtures: tuple[RecordedRefreshProposalFixture, ...] = (),
        bindings: tuple[RecordedRefreshProposalBinding, ...] = (),
    ) -> None:
        exactly_one_source = bool(fixtures) is not bool(bindings)
        selected_count = len(fixtures) if fixtures else len(bindings)
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(fixture_capacity) is not int
            or not 1 <= fixture_capacity <= MAX_RECORDED_REFRESH_PROPOSALS
            or type(fixtures) is not tuple
            or type(bindings) is not tuple
            or not exactly_one_source
            or not 1 <= selected_count <= fixture_capacity
            or any(
                type(item) is not RecordedRefreshProposalFixture for item in fixtures
            )
            or any(
                type(item) is not RecordedRefreshProposalBinding for item in bindings
            )
        ):
            fail_refresh_proposal()
        bound_pairs: tuple[tuple[str, str], ...] = ()
        try:
            if fixtures:
                bound_pairs = tuple(_fixture_binding(fixture) for fixture in fixtures)
            else:
                validated_bindings = tuple(
                    RecordedRefreshProposalBinding(
                        request_fingerprint=binding.request_fingerprint,
                        proposal_fingerprint=binding.proposal_fingerprint,
                    )
                    for binding in bindings
                )
                bound_pairs = tuple(
                    (binding.request_fingerprint, binding.proposal_fingerprint)
                    for binding in validated_bindings
                )
        except Exception:
            fail_refresh_proposal()
        request_fingerprints = tuple(binding[0] for binding in bound_pairs)
        if len(set(request_fingerprints)) != len(request_fingerprints):
            fail_refresh_proposal()
        self._bindings = bound_pairs

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
    "RecordedRefreshProposalBinding",
    "RecordedRefreshProposalFixture",
    "load_recorded_refresh_proposal_bindings",
]
