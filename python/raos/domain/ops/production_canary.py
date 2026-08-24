"""Pure ST-1506 local Production canary simulation domain.

The types in this module have no clock, network, credential, provider,
deployment, migration, traffic, telemetry, rollback, release, or public-write
capability.  They evaluate caller-supplied synthetic observations one explicit
step at a time.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, NoReturn, cast


EXPECTED_CONTRACT_SEMANTIC_SHA256: Final = (
    "6c4576882e38afbddb89aa8c2f63c2d383127ad0c2b1c017f4a56693abb9ab6a"
)

EXTERNAL_ACTION_NAMES: Final = (
    "network",
    "credential",
    "provider",
    "build",
    "promote",
    "approve",
    "deploy",
    "migrate",
    "traffic",
    "smoke",
    "telemetry",
    "alert",
    "rollback",
    "restore",
    "staging",
    "release",
    "production",
    "public_write",
)
APPROVAL_NAMES: Final = (
    "release_decision",
    "gate_report",
    "security_approval",
    "operations_approval",
)
APPROVAL_TYPES: Final = (
    "RELEASE_DECISION",
    "GATE_REPORT",
    "SECURITY_APPROVAL",
    "OPERATIONS_APPROVAL",
)
PREDECESSOR_STORIES: Final = (
    "ST-1501",
    "ST-1502",
    "ST-1503",
    "ST-1504",
    "ST-1505",
)
REQUIRED_CAPABILITY_IDS: Final = (
    "workload_runtime",
    "relational_persistence",
    "immutable_object_storage",
    "asynchronous_queue",
    "public_edge",
    "workload_identity_and_secrets",
    "telemetry_and_alerting",
    "backup_and_restore",
    "deployment_and_release",
    "region_and_data_residency",
)
PIPELINE_PHASES: Final = (
    "SAFETY_BOUNDARY",
    "PREDECESSOR_BINDING",
    "STAGING_ARTIFACT_ADMISSION",
    "HUMAN_APPROVAL_GATE",
    "CANARY",
    "OBSERVE",
    "ABORT_OR_ROLLBACK_DECISION",
    "LOCAL_SIMULATION_COMPLETE",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9.-]{2,95}$")
_MAX_CANONICAL_BYTES = 262_144
_MAX_DEPTH = 32


class ProductionCanaryError(ValueError):
    """Closed domain failure without untrusted values."""

    __slots__ = ("code", "field")

    def __init__(self, code: str, field: str) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", code):
            raise TypeError("INVALID_FAILURE_CODE")
        if not re.fullmatch(r"[a-z][a-z0-9_.]{0,95}", field):
            raise TypeError("INVALID_FAILURE_FIELD")
        self.code = code
        self.field = field
        super().__init__(code)


def _fail(code: str, field: str) -> NoReturn:
    raise ProductionCanaryError(code, field) from None


def _closed_json_value(value: object, *, depth: int = 0) -> object:
    if depth > _MAX_DEPTH:
        _fail("CANONICAL_VALUE_INVALID", "canonical")
    if value is None or type(value) in {str, bool, int}:
        if type(value) is str:
            text = value
            if len(text) > 4096 or "\x00" in text:
                _fail("CANONICAL_VALUE_INVALID", "canonical")
        return value
    if type(value) is list or type(value) is tuple:
        sequence = cast(Sequence[object], value)
        if len(sequence) > 512:
            _fail("CANONICAL_VALUE_INVALID", "canonical")
        return [_closed_json_value(item, depth=depth + 1) for item in sequence]
    if type(value) is dict:
        raw = cast(dict[object, object], value)
        if len(raw) > 512 or any(type(key) is not str for key in raw):
            _fail("CANONICAL_VALUE_INVALID", "canonical")
        return {
            cast(str, key): _closed_json_value(item, depth=depth + 1)
            for key, item in raw.items()
        }
    _fail("CANONICAL_VALUE_INVALID", "canonical")


def canonical_bytes(value: object) -> bytes:
    """Return strict deterministic UTF-8 JSON bytes for closed local data."""

    try:
        encoded = json.dumps(
            _closed_json_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        _fail("CANONICAL_VALUE_INVALID", "canonical")
    if not encoded or len(encoded) > _MAX_CANONICAL_BYTES:
        _fail("CANONICAL_VALUE_INVALID", "canonical")
    return encoded


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail("CONTRACT_SHAPE_INVALID", field)
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw):
        _fail("CONTRACT_SHAPE_INVALID", field)
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if type(value) is not list:
        _fail("CONTRACT_SHAPE_INVALID", field)
    return cast(Sequence[object], value)


def _string(value: object, field: str) -> str:
    if type(value) is not str or not value or len(value) > 4096 or "\x00" in value:
        _fail("CONTRACT_VALUE_INVALID", field)
    return value


def _sha256(value: object, field: str) -> str:
    text = _string(value, field)
    if _SHA256.fullmatch(text) is None:
        _fail("CONTRACT_VALUE_INVALID", field)
    return text


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail("CONTRACT_VALUE_INVALID", field)
    return value


class CanaryState(StrEnum):
    CANARY_READY = "CANARY_READY"
    OBSERVE = "OBSERVE"
    HOLD_FOR_HUMAN_APPROVAL = "HOLD_FOR_HUMAN_APPROVAL"
    ABORT_REQUIRED = "ABORT_REQUIRED"
    ROLLBACK_REQUIRED = "ROLLBACK_REQUIRED"


class CanaryCommandKind(StrEnum):
    START_CANARY_SIMULATION = "START_CANARY_SIMULATION"
    RECORD_SYNTHETIC_OBSERVATION = "RECORD_SYNTHETIC_OBSERVATION"


class CanaryOutcome(StrEnum):
    OBSERVE_REQUIRED = "OBSERVE_REQUIRED"
    DATA_BLOCKED = "DATA_BLOCKED"
    HUMAN_APPROVALS_REQUIRED = "HUMAN_APPROVALS_REQUIRED"
    ABORT_REQUIRED = "ABORT_REQUIRED"
    ROLLBACK_REQUIRED = "ROLLBACK_REQUIRED"


class ReleasePhase(StrEnum):
    CANARY = "CANARY"
    POST_CANARY = "POST_CANARY"


@dataclass(frozen=True, slots=True)
class ProductionCanarySpec:
    """Closed source contract values used by the pure evaluator."""

    semantic_sha256: str
    fixture_id: str
    pipeline_id: str
    predecessor_hashes: tuple[tuple[str, str], ...]
    capability_ids: tuple[str, ...]
    staging_contract_sha256: str
    staging_contract_semantic_sha256: str
    staging_manifest_sha256: str
    staging_pipeline_sha256: str
    staging_result_file_sha256: str
    staging_result_sha256: str
    artifact_sha256: str
    sbom_sha256: str
    provenance_sha256: str
    cohort_id: str
    maximum_age_seconds: int
    minimum_sample_count: int
    minimum_window_seconds: int
    maximum_error_rate_ppm: int
    maximum_latency_p95_milliseconds: int
    maximum_health_failure_count: int
    maximum_critical_alert_count: int
    action_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        hashes = (
            self.semantic_sha256,
            self.staging_contract_sha256,
            self.staging_contract_semantic_sha256,
            self.staging_manifest_sha256,
            self.staging_pipeline_sha256,
            self.staging_result_file_sha256,
            self.staging_result_sha256,
            self.artifact_sha256,
            self.sbom_sha256,
            self.provenance_sha256,
        )
        if any(_SHA256.fullmatch(value) is None for value in hashes):
            _fail("SPEC_INVALID", "spec")
        if (
            _IDENTIFIER.fullmatch(self.fixture_id) is None
            or _IDENTIFIER.fullmatch(self.pipeline_id) is None
            or _IDENTIFIER.fullmatch(self.cohort_id) is None
            or tuple(story for story, _ in self.predecessor_hashes)
            != PREDECESSOR_STORIES
            or self.capability_ids != REQUIRED_CAPABILITY_IDS
            or any(
                _SHA256.fullmatch(digest) is None
                for _, digest in self.predecessor_hashes
            )
            or tuple(name for name, _ in self.action_counts) != EXTERNAL_ACTION_NAMES
            or any(
                type(count) is not int or count != 0 for _, count in self.action_counts
            )
            or any(
                type(value) is not int or value < 0
                for value in (
                    self.maximum_age_seconds,
                    self.minimum_sample_count,
                    self.minimum_window_seconds,
                    self.maximum_error_rate_ppm,
                    self.maximum_latency_p95_milliseconds,
                    self.maximum_health_failure_count,
                    self.maximum_critical_alert_count,
                )
            )
            or self.maximum_age_seconds < 1
            or self.minimum_sample_count < 1
            or self.minimum_window_seconds < 1
        ):
            _fail("SPEC_INVALID", "spec")

    @classmethod
    def from_document(cls, value: object) -> ProductionCanarySpec:
        document = _mapping(value, "contract")
        semantic_sha256 = canonical_sha256(dict(document))
        if semantic_sha256 != EXPECTED_CONTRACT_SEMANTIC_SHA256:
            _fail("CONTRACT_DEFINITION_DRIFT", "contract")

        predecessor_rows = _mapping(
            document.get("predecessor_bindings"), "predecessors"
        )
        if tuple(predecessor_rows) != PREDECESSOR_STORIES:
            _fail("PREDECESSOR_BINDING_INVALID", "predecessors")
        predecessor_hashes: list[tuple[str, str]] = []
        for story in PREDECESSOR_STORIES:
            row = _mapping(predecessor_rows.get(story), "predecessor")
            if row.get("story_id") != story:
                _fail("PREDECESSOR_BINDING_INVALID", "predecessor")
            if (
                row.get("owner_check_required") is not True
                or row.get("admission_status") != "BLOCKED_NO_PRODUCTION_AUTHORITY"
            ):
                _fail("PREDECESSOR_BINDING_INVALID", "predecessor")
            predecessor_hashes.append(
                (story, _sha256(row.get("contract_sha256"), "predecessor.sha256"))
            )
        staging = _mapping(predecessor_rows.get("ST-1505"), "staging")
        pipeline = _mapping(document.get("pipeline"), "pipeline")
        if (
            pipeline.get("repository_inert") is not True
            or pipeline.get("default_enabled") is not False
            or pipeline.get("active_workflow_path") is not None
            or pipeline.get("trigger") != "NONE"
            or pipeline.get("auto_advance") is not False
            or tuple(_sequence(pipeline.get("phases"), "pipeline.phases"))
            != PIPELINE_PHASES
        ):
            _fail("PIPELINE_BOUNDARY_INVALID", "pipeline")

        approvals = _mapping(document.get("approval_boundary"), "approvals")
        for name, artifact_type in zip(APPROVAL_NAMES, APPROVAL_TYPES, strict=True):
            row = _mapping(approvals.get(name), "approval")
            if row != {
                "artifact_type": artifact_type,
                "artifact_value": None,
                "artifact_digest": None,
                "human_reviewer": None,
                "status": "ABSENT",
            }:
                _fail("APPROVAL_BOUNDARY_INVALID", "approval")
        if approvals.get("populated_artifact_count") != 0:
            _fail("APPROVAL_BOUNDARY_INVALID", "approvals")

        activation = _mapping(document.get("activation_boundary"), "activation")
        if (
            activation.get("default_enabled") is not False
            or activation.get("activation_enabled") is not False
            or any(
                activation.get(field) != "NONE"
                for field in (
                    "activation_authority",
                    "deployment_authority",
                    "migration_authority",
                    "traffic_authority",
                    "rollback_authority",
                    "release_authority",
                    "public_write_authority",
                )
            )
            or activation.get("credentials") != "ABSENT"
            or activation.get("provider_sdk") != "ABSENT"
            or activation.get("network_client") != "ABSENT"
            or activation.get("auto_advance") != "FORBIDDEN"
            or activation.get("external_actions") != "FORBIDDEN"
        ):
            _fail("ACTIVATION_BOUNDARY_INVALID", "activation")
        selected_fields = (
            "selected_provider",
            "selected_account",
            "selected_region",
            "selected_backup_region",
            "selected_target",
            "selected_repository",
            "selected_ref",
            "selected_workflow",
            "selected_environment",
            "selected_identity",
            "selected_credential",
            "selected_endpoint",
        )
        if any(activation.get(field) is not None for field in selected_fields):
            _fail("ACTIVATION_BOUNDARY_INVALID", "activation")

        kill_switch = _mapping(document.get("kill_switch_boundary"), "kill_switch")
        if (
            kill_switch.get("safeguard_enabled") is not True
            or kill_switch.get("fail_closed") is not True
            or kill_switch.get("deactivation_allowed") is not False
            or kill_switch.get("deactivation_authority") != "NONE"
            or kill_switch.get("stale_generation_override") != "FORBIDDEN"
            or kill_switch.get("bypass") != "FORBIDDEN"
            or kill_switch.get("external_action_count") != 0
        ):
            _fail("KILL_SWITCH_BOUNDARY_INVALID", "kill_switch")

        policy = _mapping(document.get("observation_policy"), "observation_policy")
        capability = _mapping(document.get("capability_boundary"), "capability")
        capability_ids = tuple(
            _string(item, "capability.id")
            for item in _sequence(
                capability.get("required_capability_ids"), "capability.ids"
            )
        )
        mappings = _sequence(
            capability.get("mapping_requirements"), "capability.mappings"
        )
        if (
            capability_ids != REQUIRED_CAPABILITY_IDS
            or len(mappings) != len(REQUIRED_CAPABILITY_IDS)
            or capability.get("selected_profile") is not None
            or capability.get("default_profile") is not None
            or capability.get("fallback_profile") is not None
            or capability.get("eligibility") != "BLOCKED_NOT_CONFIGURED"
        ):
            _fail("CAPABILITY_BOUNDARY_INVALID", "capability")
        for capability_id, raw_mapping in zip(
            REQUIRED_CAPABILITY_IDS, mappings, strict=True
        ):
            mapping = _mapping(raw_mapping, "capability.mapping")
            if mapping != {
                "capability_id": capability_id,
                "selected_mapping": None,
                "status": "ABSENT",
            }:
                _fail("CAPABILITY_BOUNDARY_INVALID", "capability.mapping")
        execution = _mapping(document.get("execution_boundary"), "execution")
        action_counts = _mapping(execution.get("action_counts"), "action_counts")
        if tuple(action_counts) != EXTERNAL_ACTION_NAMES or any(
            type(value) is not int or value != 0 for value in action_counts.values()
        ):
            _fail("EXTERNAL_ACTION_BOUNDARY_INVALID", "action_counts")
        return cls(
            semantic_sha256=semantic_sha256,
            fixture_id=_string(pipeline.get("fixture_id"), "pipeline.fixture_id"),
            pipeline_id=_string(pipeline.get("pipeline_id"), "pipeline.pipeline_id"),
            predecessor_hashes=tuple(predecessor_hashes),
            capability_ids=capability_ids,
            staging_contract_sha256=_sha256(
                staging.get("contract_sha256"), "staging.contract_sha256"
            ),
            staging_contract_semantic_sha256=_sha256(
                staging.get("contract_semantic_sha256"),
                "staging.contract_semantic_sha256",
            ),
            staging_manifest_sha256=_sha256(
                staging.get("manifest_sha256"), "staging.manifest_sha256"
            ),
            staging_pipeline_sha256=_sha256(
                staging.get("pipeline_sha256"), "staging.pipeline_sha256"
            ),
            staging_result_file_sha256=_sha256(
                staging.get("result_sha256"), "staging.result_file_sha256"
            ),
            staging_result_sha256=_sha256(
                staging.get("admitted_result_sha256"), "staging.result_sha256"
            ),
            artifact_sha256=_sha256(
                staging.get("artifact_payload_sha256"), "staging.artifact_sha256"
            ),
            sbom_sha256=_sha256(staging.get("sbom_sha256"), "staging.sbom_sha256"),
            provenance_sha256=_sha256(
                staging.get("provenance_sha256"), "staging.provenance_sha256"
            ),
            cohort_id=_string(policy.get("cohort_id"), "policy.cohort_id"),
            maximum_age_seconds=_integer(
                policy.get("maximum_age_seconds"), "policy.maximum_age", minimum=1
            ),
            minimum_sample_count=_integer(
                policy.get("minimum_sample_count"), "policy.minimum_samples", minimum=1
            ),
            minimum_window_seconds=_integer(
                policy.get("minimum_window_seconds"), "policy.minimum_window", minimum=1
            ),
            maximum_error_rate_ppm=_integer(
                policy.get("maximum_error_rate_ppm"), "policy.maximum_error"
            ),
            maximum_latency_p95_milliseconds=_integer(
                policy.get("maximum_latency_p95_milliseconds"),
                "policy.maximum_latency",
            ),
            maximum_health_failure_count=_integer(
                policy.get("maximum_health_failure_count"),
                "policy.maximum_health_failures",
            ),
            maximum_critical_alert_count=_integer(
                policy.get("maximum_critical_alert_count"),
                "policy.maximum_alerts",
            ),
            action_counts=tuple(
                (name, cast(int, action_counts[name])) for name in EXTERNAL_ACTION_NAMES
            ),
        )


@dataclass(frozen=True, slots=True)
class SyntheticObservation:
    """One untrusted recorded metric observation copied into closed values."""

    scenario_id: str
    source: str
    cohort_id: str
    release_phase: ReleasePhase
    contract_sha256: str
    artifact_sha256: str
    staging_result_sha256: str
    observed_at_epoch_seconds: int
    evaluated_at_epoch_seconds: int
    sample_count: int
    window_seconds: int
    error_rate_ppm: int
    latency_p95_milliseconds: int
    health_failure_count: int
    critical_alert_count: int
    kill_switch_triggered: bool
    external_action_count: int

    def __post_init__(self) -> None:
        if (
            type(self.scenario_id) is not str
            or _IDENTIFIER.fullmatch(self.scenario_id) is None
            or self.source != "SYNTHETIC_RECORDED_FIXTURE_ONLY"
            or type(self.cohort_id) is not str
            or _IDENTIFIER.fullmatch(self.cohort_id) is None
            or type(self.release_phase) is not ReleasePhase
            or any(
                _SHA256.fullmatch(value) is None
                for value in (
                    self.contract_sha256,
                    self.artifact_sha256,
                    self.staging_result_sha256,
                )
            )
            or any(
                type(value) is not int or value < 0
                for value in (
                    self.observed_at_epoch_seconds,
                    self.evaluated_at_epoch_seconds,
                    self.sample_count,
                    self.window_seconds,
                    self.error_rate_ppm,
                    self.latency_p95_milliseconds,
                    self.health_failure_count,
                    self.critical_alert_count,
                    self.external_action_count,
                )
            )
            or type(self.kill_switch_triggered) is not bool
            or self.external_action_count != 0
        ):
            _fail("OBSERVATION_INVALID", "observation")

    def to_payload(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "source": self.source,
            "cohort_id": self.cohort_id,
            "release_phase": self.release_phase.value,
            "contract_sha256": self.contract_sha256,
            "artifact_sha256": self.artifact_sha256,
            "staging_result_sha256": self.staging_result_sha256,
            "observed_at_epoch_seconds": self.observed_at_epoch_seconds,
            "evaluated_at_epoch_seconds": self.evaluated_at_epoch_seconds,
            "sample_count": self.sample_count,
            "window_seconds": self.window_seconds,
            "error_rate_ppm": self.error_rate_ppm,
            "latency_p95_milliseconds": self.latency_p95_milliseconds,
            "health_failure_count": self.health_failure_count,
            "critical_alert_count": self.critical_alert_count,
            "kill_switch_triggered": self.kill_switch_triggered,
            "external_action_count": self.external_action_count,
        }


@dataclass(frozen=True, slots=True)
class CanarySession:
    run_id: str
    version: int
    state: CanaryState

    def __post_init__(self) -> None:
        if (
            type(self.run_id) is not str
            or re.fullmatch(r"st1506-run-[a-z0-9][a-z0-9.-]{2,95}", self.run_id) is None
            or type(self.version) is not int
            or self.version < 0
            or type(self.state) is not CanaryState
        ):
            _fail("SESSION_INVALID", "session")


@dataclass(frozen=True, slots=True)
class CanaryDecision:
    previous_session: CanarySession
    session: CanarySession
    command: CanaryCommandKind
    outcome: CanaryOutcome
    observation_sha256: str | None
    block_reason: str | None

    def __post_init__(self) -> None:
        if (
            type(self.previous_session) is not CanarySession
            or type(self.session) is not CanarySession
            or type(self.command) is not CanaryCommandKind
            or type(self.outcome) is not CanaryOutcome
            or self.session.run_id != self.previous_session.run_id
            or self.session.version != self.previous_session.version + 1
            or (
                self.observation_sha256 is not None
                and _SHA256.fullmatch(self.observation_sha256) is None
            )
            or (
                self.block_reason is not None
                and self.block_reason
                not in {
                    "MISSING_OBSERVATION",
                    "FUTURE_OBSERVATION",
                    "STALE_OBSERVATION",
                    "CONTRACT_MISMATCH",
                    "ARTIFACT_MISMATCH",
                    "STAGING_RESULT_MISMATCH",
                    "COHORT_MISMATCH",
                    "IMMATURE_COHORT",
                }
            )
        ):
            _fail("DECISION_INVALID", "decision")
        expected_states = {
            CanaryOutcome.OBSERVE_REQUIRED: (
                CanaryState.CANARY_READY,
                CanaryState.OBSERVE,
            ),
            CanaryOutcome.DATA_BLOCKED: (CanaryState.OBSERVE, CanaryState.OBSERVE),
            CanaryOutcome.HUMAN_APPROVALS_REQUIRED: (
                CanaryState.OBSERVE,
                CanaryState.HOLD_FOR_HUMAN_APPROVAL,
            ),
            CanaryOutcome.ABORT_REQUIRED: (
                CanaryState.OBSERVE,
                CanaryState.ABORT_REQUIRED,
            ),
            CanaryOutcome.ROLLBACK_REQUIRED: (
                CanaryState.OBSERVE,
                CanaryState.ROLLBACK_REQUIRED,
            ),
        }
        if expected_states[self.outcome] != (
            self.previous_session.state,
            self.session.state,
        ):
            _fail("DECISION_INVALID", "decision")
        if (self.outcome is CanaryOutcome.DATA_BLOCKED) != (
            self.block_reason is not None
        ):
            _fail("DECISION_INVALID", "decision")

    def to_document(self, spec: ProductionCanarySpec) -> dict[str, object]:
        base: dict[str, object] = {
            "schema": "RAOS_LOCAL_PRODUCTION_CANARY_STEP_RESULT_V2",
            "version": 2,
            "run_id": self.session.run_id,
            "previous_version": self.previous_session.version,
            "current_version": self.session.version,
            "from_state": self.previous_session.state.value,
            "to_state": self.session.state.value,
            "command": self.command.value,
            "outcome": self.outcome.value,
            "observation_sha256": self.observation_sha256,
            "block_reason": self.block_reason,
            "contract_sha256": spec.semantic_sha256,
            "staging_admission": {
                "contract_sha256": spec.staging_contract_sha256,
                "contract_semantic_sha256": spec.staging_contract_semantic_sha256,
                "manifest_sha256": spec.staging_manifest_sha256,
                "pipeline_sha256": spec.staging_pipeline_sha256,
                "result_file_sha256": spec.staging_result_file_sha256,
                "result_sha256": spec.staging_result_sha256,
                "artifact_sha256": spec.artifact_sha256,
                "sbom_sha256": spec.sbom_sha256,
                "provenance_sha256": spec.provenance_sha256,
            },
            "capability_boundary": {
                "required_capability_ids": list(spec.capability_ids),
                "selected_mapping_count": 0,
                "selected_profile": None,
                "default_profile": None,
                "fallback_profile": None,
                "eligibility": "BLOCKED_NOT_CONFIGURED",
            },
            "human_approvals": {
                name: {"artifact_type": artifact_type, "status": "ABSENT"}
                for name, artifact_type in zip(
                    APPROVAL_NAMES, APPROVAL_TYPES, strict=True
                )
            },
            "approval_artifact_count": 0,
            "activation": {
                "enabled": False,
                "authority": "NONE",
                "public_write_authority": "NONE",
                "auto_advance": "FORBIDDEN",
            },
            "kill_switch": {
                "safeguard_enabled": True,
                "deactivation_allowed": False,
                "deactivation_authority": "NONE",
                "external_action_count": 0,
            },
            "action_counts": dict(spec.action_counts),
            "classification": "DETERMINISTIC_SYNTHETIC_LOCAL_ONLY_NOT_PRODUCTION_EVIDENCE",
            "external_evidence": {
                "formal_tst_009": "NOT_EXECUTED",
                "formal_tst_022": "NOT_EXECUTED",
                "formal_tst_032": "NOT_EXECUTED",
                "staging": "NOT_EXECUTED",
                "release": "NOT_EXECUTED",
                "production": "NOT_EXECUTED",
            },
        }
        digest = canonical_sha256(base)
        base["result_sha256"] = digest
        return base


def _blocked_reason(
    spec: ProductionCanarySpec,
    observation: SyntheticObservation,
) -> str | None:
    if observation.evaluated_at_epoch_seconds < observation.observed_at_epoch_seconds:
        return "FUTURE_OBSERVATION"
    if (
        observation.evaluated_at_epoch_seconds - observation.observed_at_epoch_seconds
        > spec.maximum_age_seconds
    ):
        return "STALE_OBSERVATION"
    if observation.contract_sha256 != spec.semantic_sha256:
        return "CONTRACT_MISMATCH"
    if observation.artifact_sha256 != spec.artifact_sha256:
        return "ARTIFACT_MISMATCH"
    if observation.staging_result_sha256 != spec.staging_result_sha256:
        return "STAGING_RESULT_MISMATCH"
    if observation.cohort_id != spec.cohort_id:
        return "COHORT_MISMATCH"
    if (
        observation.sample_count < spec.minimum_sample_count
        or observation.window_seconds < spec.minimum_window_seconds
    ):
        return "IMMATURE_COHORT"
    return None


def advance_once(
    spec: ProductionCanarySpec,
    session: CanarySession,
    *,
    command: CanaryCommandKind,
    observation: SyntheticObservation | None,
) -> CanaryDecision:
    """Evaluate exactly one state transition without a loop or side effect."""

    if type(spec) is not ProductionCanarySpec or type(session) is not CanarySession:
        _fail("STATE_MACHINE_INPUT_INVALID", "state_machine")
    if type(command) is not CanaryCommandKind:
        _fail("STATE_MACHINE_INPUT_INVALID", "command")
    if session.state is CanaryState.CANARY_READY:
        if command is not CanaryCommandKind.START_CANARY_SIMULATION:
            _fail("STATE_TRANSITION_FORBIDDEN", "command")
        if observation is not None:
            _fail("OBSERVATION_NOT_ALLOWED", "observation")
        return CanaryDecision(
            previous_session=session,
            session=CanarySession(
                run_id=session.run_id,
                version=session.version + 1,
                state=CanaryState.OBSERVE,
            ),
            command=command,
            outcome=CanaryOutcome.OBSERVE_REQUIRED,
            observation_sha256=None,
            block_reason=None,
        )
    if session.state is not CanaryState.OBSERVE:
        _fail("TERMINAL_STATE", "session")
    if command is not CanaryCommandKind.RECORD_SYNTHETIC_OBSERVATION:
        _fail("STATE_TRANSITION_FORBIDDEN", "command")
    if observation is None:
        return CanaryDecision(
            previous_session=session,
            session=CanarySession(
                run_id=session.run_id,
                version=session.version + 1,
                state=CanaryState.OBSERVE,
            ),
            command=command,
            outcome=CanaryOutcome.DATA_BLOCKED,
            observation_sha256=None,
            block_reason="MISSING_OBSERVATION",
        )
    if type(observation) is not SyntheticObservation:
        _fail("OBSERVATION_INVALID", "observation")
    observation_sha256 = canonical_sha256(observation.to_payload())
    blocked = _blocked_reason(spec, observation)
    if blocked is not None:
        return CanaryDecision(
            previous_session=session,
            session=CanarySession(
                run_id=session.run_id,
                version=session.version + 1,
                state=CanaryState.OBSERVE,
            ),
            command=command,
            outcome=CanaryOutcome.DATA_BLOCKED,
            observation_sha256=observation_sha256,
            block_reason=blocked,
        )
    regression = (
        observation.kill_switch_triggered
        or observation.error_rate_ppm > spec.maximum_error_rate_ppm
        or observation.latency_p95_milliseconds > spec.maximum_latency_p95_milliseconds
        or observation.health_failure_count > spec.maximum_health_failure_count
        or observation.critical_alert_count > spec.maximum_critical_alert_count
    )
    if regression and observation.release_phase is ReleasePhase.CANARY:
        outcome = CanaryOutcome.ABORT_REQUIRED
        state = CanaryState.ABORT_REQUIRED
    elif regression:
        outcome = CanaryOutcome.ROLLBACK_REQUIRED
        state = CanaryState.ROLLBACK_REQUIRED
    else:
        outcome = CanaryOutcome.HUMAN_APPROVALS_REQUIRED
        state = CanaryState.HOLD_FOR_HUMAN_APPROVAL
    return CanaryDecision(
        previous_session=session,
        session=CanarySession(
            run_id=session.run_id,
            version=session.version + 1,
            state=state,
        ),
        command=command,
        outcome=outcome,
        observation_sha256=observation_sha256,
        block_reason=None,
    )


__all__ = [
    "APPROVAL_NAMES",
    "APPROVAL_TYPES",
    "CanaryCommandKind",
    "CanaryDecision",
    "CanaryOutcome",
    "CanarySession",
    "CanaryState",
    "EXPECTED_CONTRACT_SEMANTIC_SHA256",
    "EXTERNAL_ACTION_NAMES",
    "PIPELINE_PHASES",
    "PREDECESSOR_STORIES",
    "REQUIRED_CAPABILITY_IDS",
    "ProductionCanaryError",
    "ProductionCanarySpec",
    "ReleasePhase",
    "SyntheticObservation",
    "advance_once",
    "canonical_bytes",
    "canonical_sha256",
]
