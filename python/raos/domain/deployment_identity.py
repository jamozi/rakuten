"""Provider-neutral, offline-only deployment identity trust evaluation.

This module deliberately does not parse JWTs, verify signatures, authenticate a
GitHub workload, exchange a federation token, or issue a credential.  It only
compares a closed recorded claim fixture with a closed recorded policy fixture.
The result is therefore policy-match evidence, never authentication or deploy
authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, NoReturn, cast


RECORDED_CLAIM_KEYS: Final = (
    "iss",
    "aud",
    "sub",
    "repository",
    "repository_id",
    "repository_owner_id",
    "ref",
    "ref_type",
    "workflow",
    "workflow_ref",
    "workflow_sha",
    "job_workflow_ref",
    "environment",
    "event_name",
    "repository_visibility",
    "actor_id",
    "run_id",
    "run_attempt",
    "base_ref",
    "head_ref",
)

_ENVELOPE_KEYS: Final = {
    "schema",
    "version",
    "fixture_id",
    "classification",
    "authentication_status",
    "signature_verification_status",
    "token_material",
    "claims",
}
_POLICY_KEYS: Final = {
    "schema",
    "version",
    "policy_id",
    "fixture_id",
    "classification",
    "source_system",
    "authentication_authority",
    "credential_issuance_authority",
    "expected_claims",
    "trust",
    "session",
    "approval",
    "lifecycle",
    "activation",
}
_TRUST_KEYS: Final = {
    "exact_match_required",
    "wildcards_allowed",
    "fork_pull_request_allowed",
    "pull_request_allowed",
    "pull_request_target_allowed",
    "reusable_workflow_callers",
}
_SESSION_KEYS: Final = {
    "requested_duration_seconds",
    "maximum_duration_seconds",
    "permission_scopes",
    "least_privilege_required",
    "role_chaining_allowed",
    "privilege_escalation_allowed",
    "static_credentials_allowed",
    "human_credentials_allowed",
    "cross_environment_reuse_allowed",
}
_APPROVAL_KEYS: Final = {
    "protected_environment_required",
    "distinct_human_approval_required",
    "self_approval_allowed",
    "bypass_allowed",
    "approval_record_status",
}
_LIFECYCLE_KEYS: Final = {
    "signed_provenance_required",
    "immutable_audit_required",
    "revocation_required",
    "rollback_required",
    "evidence_retention_required",
    "evidence_status",
}
_ACTIVATION_KEYS: Final = {"enabled", "status", "planned_actions"}
_ACTION_KEYS: Final = {"create", "update", "delete"}
_SAFE_COMPONENT = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,99}$")
_DECIMAL = re.compile(r"^[1-9][0-9]{0,19}$")
_LOWER_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_EXACT_FRAGMENTS: Final = ("*", "?", "${{", "}}", "\x00")


class DeploymentIdentityPolicyError(ValueError):
    """A closed, sanitized failure at the recorded trust boundary."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"{code} field={field}")


def _fail(code: str, field: str) -> NoReturn:
    raise DeploymentIdentityPolicyError(code, field)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail("TYPE_MISMATCH", field)
    untyped = cast(dict[object, object], value)
    if any(type(key) is not str for key in untyped):
        _fail("TYPE_MISMATCH", field)
    return cast(Mapping[str, object], value)


def _exact_keys(value: Mapping[str, object], expected: set[str], field: str) -> None:
    if set(value) != expected:
        _fail("CLOSED_SCHEMA_VIOLATION", field)


def _exact_string(value: object, field: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        _fail("TYPE_MISMATCH", field)
    if len(value) > 512 or value != value.strip():
        _fail("EXACT_VALUE_INVALID", field)
    if not value and not allow_empty:
        _fail("EXACT_VALUE_INVALID", field)
    if any(fragment in value for fragment in _FORBIDDEN_EXACT_FRAGMENTS):
        _fail("WILDCARD_OR_TEMPLATE_FORBIDDEN", field)
    if any(ord(character) < 0x20 for character in value):
        _fail("CONTROL_CHARACTER_FORBIDDEN", field)
    return value


def _exact_bool(value: object, expected: bool, field: str) -> None:
    if type(value) is not bool:
        _fail("TYPE_MISMATCH", field)
    if value is not expected:
        _fail("SAFE_BOUNDARY_VIOLATION", field)


def _exact_int(value: object, field: str) -> int:
    if type(value) is not int:
        _fail("TYPE_MISMATCH", field)
    return value


def _exact_literal(value: object, expected: str, field: str) -> None:
    observed = _exact_string(value, field)
    if observed != expected:
        _fail("FIXED_VALUE_VIOLATION", field)


def _string_list(value: object, field: str) -> tuple[str, ...]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    observed: list[str] = []
    for item in cast(list[object], value):
        observed.append(_exact_string(item, f"{field}.item"))
    if len(observed) != len(set(observed)):
        _fail("DUPLICATE_VALUE", field)
    return tuple(observed)


def _validate_claims(value: object, field: str) -> tuple[tuple[str, str], ...]:
    claims = _mapping(value, field)
    _exact_keys(claims, set(RECORDED_CLAIM_KEYS), field)
    observed: dict[str, str] = {}
    for claim_name in RECORDED_CLAIM_KEYS:
        observed[claim_name] = _exact_string(
            claims[claim_name],
            f"{field}.{claim_name}",
            allow_empty=claim_name in {"job_workflow_ref", "base_ref", "head_ref"},
        )

    repository = observed["repository"]
    components = repository.split("/")
    if len(components) != 2 or any(
        _SAFE_COMPONENT.fullmatch(component) is None for component in components
    ):
        _fail("REPOSITORY_IDENTITY_INVALID", field)
    if "fixture" not in repository or "fixture" not in observed["environment"]:
        _fail("NON_SYNTHETIC_BINDING_FORBIDDEN", field)
    if not observed["iss"].startswith("https://") or not observed["iss"].endswith(
        ".invalid"
    ):
        _fail("RECORDED_ISSUER_INVALID", field)
    if not observed["aud"].endswith(".invalid"):
        _fail("RECORDED_AUDIENCE_INVALID", field)
    if observed["ref_type"] != "branch" or not observed["ref"].startswith(
        "refs/heads/"
    ):
        _fail("TRUSTED_REF_INVALID", field)
    if "fixture" not in observed["ref"]:
        _fail("NON_SYNTHETIC_BINDING_FORBIDDEN", field)
    expected_subject = f"repo:{repository}:environment:{observed['environment']}"
    if observed["sub"] != expected_subject:
        _fail("SUBJECT_BINDING_INVALID", field)
    expected_workflow_suffix = f"@{observed['ref']}"
    if not observed["workflow_ref"].startswith(f"{repository}/") or not observed[
        "workflow_ref"
    ].endswith(expected_workflow_suffix):
        _fail("WORKFLOW_BINDING_INVALID", field)
    if observed["job_workflow_ref"]:
        _fail("REUSABLE_CALLER_AMBIGUITY", field)
    if observed["event_name"] != "workflow_dispatch":
        _fail("UNTRUSTED_EVENT", field)
    if observed["base_ref"] or observed["head_ref"]:
        _fail("PULL_REQUEST_CONTEXT_FORBIDDEN", field)
    if observed["repository_visibility"] != "private":
        _fail("REPOSITORY_VISIBILITY_INVALID", field)
    if _LOWER_HEX_40.fullmatch(observed["workflow_sha"]) is None:
        _fail("WORKFLOW_SHA_INVALID", field)
    for numeric_claim in (
        "repository_id",
        "repository_owner_id",
        "actor_id",
        "run_id",
        "run_attempt",
    ):
        if _DECIMAL.fullmatch(observed[numeric_claim]) is None:
            _fail("NUMERIC_CLAIM_INVALID", f"{field}.{numeric_claim}")
    return tuple((name, observed[name]) for name in RECORDED_CLAIM_KEYS)


@dataclass(frozen=True, slots=True)
class RecordedClaimEnvelope:
    """A decoded, unauthenticated, token-free synthetic claim fixture."""

    fixture_id: str
    claims: tuple[tuple[str, str], ...]

    @classmethod
    def from_document(cls, document: object) -> RecordedClaimEnvelope:
        value = _mapping(document, "claim_envelope")
        _exact_keys(value, _ENVELOPE_KEYS, "claim_envelope")
        _exact_literal(value["schema"], "RAOS_RECORDED_GITHUB_OIDC_CLAIMS_V1", "schema")
        if _exact_int(value["version"], "version") != 1:
            _fail("FIXED_VALUE_VIOLATION", "version")
        fixture_id = _exact_string(value["fixture_id"], "fixture_id")
        if not fixture_id.startswith("st1504-fixture-"):
            _fail("FIXTURE_ID_INVALID", "fixture_id")
        _exact_literal(
            value["classification"],
            "SYNTHETIC_DECODED_CLAIM_SHAPE_ONLY",
            "classification",
        )
        _exact_literal(
            value["authentication_status"],
            "NOT_AUTHENTICATED",
            "authentication_status",
        )
        _exact_literal(
            value["signature_verification_status"],
            "NOT_PERFORMED",
            "signature_verification_status",
        )
        _exact_literal(value["token_material"], "ABSENT", "token_material")
        return cls(
            fixture_id=fixture_id,
            claims=_validate_claims(value["claims"], "claims"),
        )

    def claim_map(self) -> dict[str, str]:
        return dict(self.claims)


@dataclass(frozen=True, slots=True)
class OfflineTrustPolicy:
    """A strict recorded policy that has no provider or activation authority."""

    policy_id: str
    fixture_id: str
    expected_claims: tuple[tuple[str, str], ...]
    permission_scopes: tuple[str, ...]
    requested_duration_seconds: int
    maximum_duration_seconds: int

    @classmethod
    def from_document(cls, document: object) -> OfflineTrustPolicy:
        value = _mapping(document, "trust_policy")
        _exact_keys(value, _POLICY_KEYS, "trust_policy")
        _exact_literal(
            value["schema"], "RAOS_OFFLINE_GITHUB_OIDC_TRUST_POLICY_V1", "schema"
        )
        if _exact_int(value["version"], "version") != 1:
            _fail("FIXED_VALUE_VIOLATION", "version")
        policy_id = _exact_string(value["policy_id"], "policy_id")
        fixture_id = _exact_string(value["fixture_id"], "fixture_id")
        if not policy_id.startswith("st1504-policy-") or not fixture_id.startswith(
            "st1504-fixture-"
        ):
            _fail("FIXTURE_ID_INVALID", "policy_identity")
        _exact_literal(
            value["classification"],
            "RECORDED_SYNTHETIC_PROVIDER_NEUTRAL_OFFLINE_FIXTURE",
            "classification",
        )
        _exact_literal(value["source_system"], "GITHUB_ACTIONS_OIDC", "source")
        _exact_literal(
            value["authentication_authority"], "NONE", "authentication_authority"
        )
        _exact_literal(
            value["credential_issuance_authority"],
            "NONE",
            "credential_issuance_authority",
        )

        trust = _mapping(value["trust"], "trust")
        _exact_keys(trust, _TRUST_KEYS, "trust")
        _exact_bool(trust["exact_match_required"], True, "trust.exact_match")
        for field in (
            "wildcards_allowed",
            "fork_pull_request_allowed",
            "pull_request_allowed",
            "pull_request_target_allowed",
        ):
            _exact_bool(trust[field], False, f"trust.{field}")
        if _string_list(trust["reusable_workflow_callers"], "trust.callers"):
            _fail("REUSABLE_CALLER_AMBIGUITY", "trust.callers")

        session = _mapping(value["session"], "session")
        _exact_keys(session, _SESSION_KEYS, "session")
        requested_duration = _exact_int(
            session["requested_duration_seconds"], "session.requested_duration"
        )
        maximum_duration = _exact_int(
            session["maximum_duration_seconds"], "session.maximum_duration"
        )
        if not (300 <= requested_duration <= maximum_duration <= 900):
            _fail("SESSION_DURATION_UNBOUNDED", "session")
        scopes = _string_list(session["permission_scopes"], "session.scopes")
        if scopes != ("deployment-fixture:evaluate",):
            _fail("LEAST_PRIVILEGE_SCOPE_INVALID", "session.scopes")
        _exact_bool(
            session["least_privilege_required"], True, "session.least_privilege"
        )
        for field in (
            "role_chaining_allowed",
            "privilege_escalation_allowed",
            "static_credentials_allowed",
            "human_credentials_allowed",
            "cross_environment_reuse_allowed",
        ):
            _exact_bool(session[field], False, f"session.{field}")

        approval = _mapping(value["approval"], "approval")
        _exact_keys(approval, _APPROVAL_KEYS, "approval")
        _exact_bool(
            approval["protected_environment_required"],
            True,
            "approval.protected_environment",
        )
        _exact_bool(
            approval["distinct_human_approval_required"],
            True,
            "approval.distinct_human",
        )
        _exact_bool(approval["self_approval_allowed"], False, "approval.self")
        _exact_bool(approval["bypass_allowed"], False, "approval.bypass")
        _exact_literal(
            approval["approval_record_status"],
            "NOT_EXECUTED",
            "approval.record_status",
        )

        lifecycle = _mapping(value["lifecycle"], "lifecycle")
        _exact_keys(lifecycle, _LIFECYCLE_KEYS, "lifecycle")
        for field in (
            "signed_provenance_required",
            "immutable_audit_required",
            "revocation_required",
            "rollback_required",
            "evidence_retention_required",
        ):
            _exact_bool(lifecycle[field], True, f"lifecycle.{field}")
        _exact_literal(
            lifecycle["evidence_status"],
            "RECORDED_FIXTURE_ONLY_NOT_FORMAL",
            "lifecycle.evidence_status",
        )

        activation = _mapping(value["activation"], "activation")
        _exact_keys(activation, _ACTIVATION_KEYS, "activation")
        _exact_bool(activation["enabled"], False, "activation.enabled")
        _exact_literal(activation["status"], "DISABLED", "activation.status")
        actions = _mapping(activation["planned_actions"], "activation.actions")
        _exact_keys(actions, _ACTION_KEYS, "activation.actions")
        for action in sorted(_ACTION_KEYS):
            if _exact_int(actions[action], f"activation.actions.{action}") != 0:
                _fail("NONZERO_ACTION_FORBIDDEN", f"activation.actions.{action}")

        return cls(
            policy_id=policy_id,
            fixture_id=fixture_id,
            expected_claims=_validate_claims(
                value["expected_claims"], "expected_claims"
            ),
            permission_scopes=scopes,
            requested_duration_seconds=requested_duration,
            maximum_duration_seconds=maximum_duration,
        )

    def expected_claim_map(self) -> dict[str, str]:
        return dict(self.expected_claims)


@dataclass(frozen=True, slots=True)
class TrustEvaluation:
    """Deterministic policy-match evidence with all authorities denied."""

    policy_id: str
    fixture_id: str
    classification: str
    policy_match: bool
    authentication_status: str
    signature_verification_status: str
    credential_issuance_authorized: bool
    activation_authorized: bool
    deployment_authorized: bool
    action_count: int
    reason_codes: tuple[str, ...]
    evidence_digest: str


def _evaluation_digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evaluate_recorded_claims(
    policy: OfflineTrustPolicy, envelope: RecordedClaimEnvelope
) -> TrustEvaluation:
    """Compare exact recorded values without authenticating or issuing anything."""

    reasons: list[str] = []
    if policy.fixture_id != envelope.fixture_id:
        reasons.append("FIXTURE_ID_MISMATCH")
    if policy.expected_claims != envelope.claims:
        reasons.append("EXACT_CLAIM_MISMATCH")
    policy_match = not reasons
    if policy_match:
        reasons.append("RECORDED_EXACT_CLAIMS_MATCHED")
    reasons.extend(
        (
            "SIGNATURE_NOT_VERIFIED",
            "AUTHENTICATION_NOT_PERFORMED",
            "ACTIVATION_DISABLED",
            "CREDENTIAL_ISSUANCE_FORBIDDEN",
            "DEPLOYMENT_FORBIDDEN",
        )
    )
    payload: dict[str, object] = {
        "policy_id": policy.policy_id,
        "fixture_id": envelope.fixture_id,
        "classification": "OFFLINE_POLICY_MATCH_ONLY_NOT_AUTHENTICATION",
        "policy_match": policy_match,
        "authentication_status": "NOT_AUTHENTICATED",
        "signature_verification_status": "NOT_PERFORMED",
        "credential_issuance_authorized": False,
        "activation_authorized": False,
        "deployment_authorized": False,
        "action_count": 0,
        "reason_codes": reasons,
    }
    return TrustEvaluation(
        policy_id=policy.policy_id,
        fixture_id=envelope.fixture_id,
        classification="OFFLINE_POLICY_MATCH_ONLY_NOT_AUTHENTICATION",
        policy_match=policy_match,
        authentication_status="NOT_AUTHENTICATED",
        signature_verification_status="NOT_PERFORMED",
        credential_issuance_authorized=False,
        activation_authorized=False,
        deployment_authorized=False,
        action_count=0,
        reason_codes=tuple(reasons),
        evidence_digest=_evaluation_digest(payload),
    )


def validate_evaluation_digest(value: object) -> str:
    """Validate an opaque local evaluation digest for the disabled port."""

    digest = _exact_string(value, "evaluation_digest")
    if _SHA256.fullmatch(digest) is None:
        _fail("EVALUATION_DIGEST_INVALID", "evaluation_digest")
    return digest
