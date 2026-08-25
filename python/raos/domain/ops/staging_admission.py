"""Deterministic ST-1505 staging-admission simulation.

The model consumes only closed synthetic and recorded documents.  It performs
no network request, provider call, database migration, deployment, rollback,
release, or Production operation.  A successful result is local admission
logic evidence only and is never staging or formal TST evidence.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, NoReturn, cast
from urllib.parse import urlsplit


_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID: Final = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,127}$")
_FORBIDDEN_TEXT: Final = ("${{", "}}", "\x00")

PIPELINE_PHASES: Final = (
    "SAFETY_BOUNDARY",
    "ARTIFACT_ADMISSION",
    "MIGRATION_PLAN",
    "MIGRATION_DRY_RUN",
    "LOOPBACK_HEALTH",
    "ROLLBACK_RESTORE_SIMULATION",
    "LOCAL_ADMISSION_COMPLETE",
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
    "smoke",
    "browser",
    "telemetry",
    "alert",
    "rollback",
    "restore",
    "staging",
    "release",
    "production",
)
SURFACE_ORDER: Final = ("PUBLIC", "ADMIN", "INTERNAL")
SURFACE_EXPECTATIONS: Final = {
    "PUBLIC": {
        "port": 38101,
        "path": "/health/readiness",
        "data_scope": "PUBLIC_PROJECTION_ONLY",
        "identity_state": "NOT_APPLICABLE",
        "direct_data_plane_access": "FORBIDDEN",
    },
    "ADMIN": {
        "port": 38102,
        "path": "/admin/health/readiness",
        "data_scope": "OPERATIONS_METADATA_ONLY",
        "identity_state": "NOT_AUTHENTICATED_RECORDED_ONLY",
        "direct_data_plane_access": "PRIVATE_CORE_API_ONLY_NOT_CONFIGURED",
    },
    "INTERNAL": {
        "port": 38103,
        "path": "/internal/health/readiness",
        "data_scope": "CONTROL_METADATA_ONLY",
        "identity_state": "SERVICE_IDENTITY_NOT_CONFIGURED",
        "direct_data_plane_access": "LEAST_PRIVILEGE_NOT_CONFIGURED",
    },
}


class StagingAdmissionError(ValueError):
    """A closed, sanitized failure at the local admission boundary."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"{code} field={field}")


def _fail(code: str, field: str) -> NoReturn:
    raise StagingAdmissionError(code, field)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail("TYPE_MISMATCH", field)
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw):
        _fail("TYPE_MISMATCH", field)
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return cast(list[object], value)


def _exact_keys(value: Mapping[str, object], expected: set[str], field: str) -> None:
    if set(value) != expected:
        _fail("CLOSED_SCHEMA_VIOLATION", field)


def _string(value: object, field: str, *, maximum: int = 512) -> str:
    if type(value) is not str:
        _fail("TYPE_MISMATCH", field)
    if not value or value != value.strip() or len(value) > maximum:
        _fail("EXACT_VALUE_INVALID", field)
    if any(fragment in value for fragment in _FORBIDDEN_TEXT):
        _fail("UNSAFE_VALUE", field)
    if any(ord(character) < 0x20 for character in value):
        _fail("CONTROL_CHARACTER_FORBIDDEN", field)
    return value


def _payload(value: object, field: str) -> str:
    if type(value) is not str:
        _fail("TYPE_MISMATCH", field)
    if not value.endswith("\n") or len(value.encode("utf-8")) > 4096:
        _fail("SYNTHETIC_PAYLOAD_INVALID", field)
    if "ST-1505 synthetic" not in value or "fixture" not in value:
        _fail("NON_SYNTHETIC_PAYLOAD_FORBIDDEN", field)
    if value.count("\n") != 1 or any(ord(character) < 0x20 for character in value[:-1]):
        _fail("CONTROL_CHARACTER_FORBIDDEN", field)
    return value


def _literal(value: object, expected: str, field: str) -> None:
    if _string(value, field) != expected:
        _fail("FIXED_VALUE_VIOLATION", field)


def _bool(value: object, expected: bool, field: str) -> None:
    if type(value) is not bool:
        _fail("TYPE_MISMATCH", field)
    if value is not expected:
        _fail("SAFE_BOUNDARY_VIOLATION", field)


def _int(value: object, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int:
        _fail("TYPE_MISMATCH", field)
    if value < minimum:
        _fail("INTEGER_RANGE_INVALID", field)
    return value


def _zero(value: object, field: str) -> None:
    if _int(value, field) != 0:
        _fail("NONZERO_EXTERNAL_ACTION", field)


def _identifier(value: object, field: str, *, prefix: str) -> str:
    observed = _string(value, field, maximum=128)
    if not observed.startswith(prefix) or _SAFE_ID.fullmatch(observed) is None:
        _fail("IDENTIFIER_INVALID", field)
    return observed


def _sha256(value: object, field: str) -> str:
    observed = _string(value, field, maximum=64)
    if _SHA256.fullmatch(observed) is None:
        _fail("SHA256_INVALID", field)
    return observed


def canonical_bytes(value: object) -> bytes:
    """Return the sole deterministic JSON representation used for digests."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        _fail("CANONICAL_ENCODING_FAILED", "document")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class ArtifactAdmissionSpec:
    fixture_id: str
    payload_utf8: str
    payload_sha256: str
    sbom: Mapping[str, object]
    sbom_sha256: str
    provenance: Mapping[str, object]

    @classmethod
    def from_document(cls, document: object) -> ArtifactAdmissionSpec:
        value = _mapping(document, "artifact")
        _exact_keys(
            value,
            {
                "classification",
                "fixture_id",
                "media_type",
                "payload_utf8",
                "payload_sha256",
                "immutable",
                "sbom",
                "vulnerability_report",
                "provenance",
            },
            "artifact",
        )
        _literal(
            value["classification"],
            "SYNTHETIC_IMMUTABLE_ARTIFACT_ADMISSION_ONLY",
            "artifact.classification",
        )
        fixture_id = _identifier(
            value["fixture_id"], "artifact.fixture_id", prefix="st1505-artifact-"
        )
        _literal(value["media_type"], "application/octet-stream", "artifact.media")
        _bool(value["immutable"], True, "artifact.immutable")
        payload_utf8 = _payload(value["payload_utf8"], "artifact.payload")
        payload_sha256 = _sha256(value["payload_sha256"], "artifact.payload_sha256")
        if hashlib.sha256(payload_utf8.encode("utf-8")).hexdigest() != payload_sha256:
            _fail("ARTIFACT_DIGEST_MISMATCH", "artifact.payload_sha256")

        sbom = _mapping(value["sbom"], "artifact.sbom")
        _exact_keys(
            sbom,
            {
                "schema",
                "document_id",
                "classification",
                "packages",
                "external_references",
            },
            "artifact.sbom",
        )
        _literal(sbom["schema"], "RAOS_RECORDED_SBOM_V1", "artifact.sbom.schema")
        _identifier(
            sbom["document_id"],
            "artifact.sbom.document_id",
            prefix="st1505-sbom-",
        )
        _literal(
            sbom["classification"],
            "SYNTHETIC_RECORDED_LOCAL_ONLY",
            "artifact.sbom.classification",
        )
        packages = _sequence(sbom["packages"], "artifact.sbom.packages")
        if len(packages) != 1:
            _fail("SBOM_PACKAGE_INVENTORY_INVALID", "artifact.sbom.packages")
        package = _mapping(packages[0], "artifact.sbom.package")
        _exact_keys(
            package,
            {"name", "version", "supplier", "artifact_sha256"},
            "artifact.sbom.package",
        )
        _literal(package["name"], "raos-st1505-synthetic-fixture", "artifact.sbom.name")
        _literal(package["version"], "2.0.0-local", "artifact.sbom.version")
        _literal(package["supplier"], "NOASSERTION", "artifact.sbom.supplier")
        if (
            _sha256(package["artifact_sha256"], "artifact.sbom.artifact_sha256")
            != payload_sha256
        ):
            _fail("SBOM_SUBJECT_DIGEST_MISMATCH", "artifact.sbom.artifact_sha256")
        references = _sequence(
            sbom["external_references"], "artifact.sbom.external_references"
        )
        if references:
            _fail("EXTERNAL_REFERENCE_FORBIDDEN", "artifact.sbom.external_references")
        sbom_copy = dict(sbom)
        sbom_sha256 = canonical_sha256(sbom_copy)

        vulnerability = _mapping(
            value["vulnerability_report"], "artifact.vulnerability_report"
        )
        _exact_keys(
            vulnerability,
            {
                "classification",
                "scanner",
                "database_version",
                "critical_count",
                "high_count",
                "findings",
                "result",
                "formal_scan",
            },
            "artifact.vulnerability_report",
        )
        _literal(
            vulnerability["classification"],
            "SYNTHETIC_RECORDED_RULE_EVALUATION_ONLY",
            "artifact.vulnerability.classification",
        )
        _literal(
            vulnerability["scanner"],
            "RAOS_CLOSED_FIXTURE_VALIDATOR",
            "artifact.vulnerability.scanner",
        )
        _literal(
            vulnerability["database_version"],
            "SYNTHETIC-NO-CVE-DATABASE",
            "artifact.vulnerability.database",
        )
        _zero(vulnerability["critical_count"], "artifact.vulnerability.critical")
        _zero(vulnerability["high_count"], "artifact.vulnerability.high")
        if _sequence(vulnerability["findings"], "artifact.vulnerability.findings"):
            _fail("CRITICAL_HIGH_FINDING_PRESENT", "artifact.vulnerability.findings")
        _literal(vulnerability["result"], "PASS", "artifact.vulnerability.result")
        _literal(
            vulnerability["formal_scan"],
            "NOT_EXECUTED",
            "artifact.vulnerability.formal",
        )

        provenance = _mapping(value["provenance"], "artifact.provenance")
        _exact_keys(
            provenance,
            {
                "schema",
                "statement_id",
                "classification",
                "builder_id",
                "build_type",
                "subject_name",
                "subject_sha256",
                "sbom_sha256",
                "signature_kind",
                "cryptographic_signature_verification",
                "formal_attestation",
            },
            "artifact.provenance",
        )
        _literal(
            provenance["schema"],
            "RAOS_RECORDED_PROVENANCE_V1",
            "artifact.provenance.schema",
        )
        _identifier(
            provenance["statement_id"],
            "artifact.provenance.statement_id",
            prefix="st1505-provenance-",
        )
        _literal(
            provenance["classification"],
            "SYNTHETIC_DIGEST_BINDING_ONLY_NOT_SIGNED_ATTESTATION",
            "artifact.provenance.classification",
        )
        builder_id = _string(provenance["builder_id"], "artifact.provenance.builder")
        builder = urlsplit(builder_id)
        if (
            builder.scheme != "https"
            or builder.hostname is None
            or not builder.hostname.endswith(".invalid")
            or builder.username is not None
            or builder.password is not None
            or builder.query
            or builder.fragment
        ):
            _fail("RECORDED_BUILDER_ID_INVALID", "artifact.provenance.builder")
        _literal(
            provenance["build_type"],
            "RAOS_ST1505_RECORDED_LOCAL_BUILD_V1",
            "artifact.provenance.build_type",
        )
        _literal(
            provenance["subject_name"],
            "raos-st1505-synthetic-fixture.bin",
            "artifact.provenance.subject_name",
        )
        if (
            _sha256(provenance["subject_sha256"], "artifact.provenance.subject_sha256")
            != payload_sha256
        ):
            _fail("PROVENANCE_SUBJECT_MISMATCH", "artifact.provenance.subject_sha256")
        if (
            _sha256(provenance["sbom_sha256"], "artifact.provenance.sbom_sha256")
            != sbom_sha256
        ):
            _fail("PROVENANCE_SBOM_MISMATCH", "artifact.provenance.sbom_sha256")
        _literal(
            provenance["signature_kind"],
            "SYNTHETIC_CANONICAL_DIGEST_BINDING",
            "artifact.provenance.signature_kind",
        )
        _literal(
            provenance["cryptographic_signature_verification"],
            "NOT_PERFORMED",
            "artifact.provenance.signature_verification",
        )
        _literal(
            provenance["formal_attestation"],
            "NOT_EXECUTED",
            "artifact.provenance.formal_attestation",
        )
        return cls(
            fixture_id=fixture_id,
            payload_utf8=payload_utf8,
            payload_sha256=payload_sha256,
            sbom=sbom_copy,
            sbom_sha256=sbom_sha256,
            provenance=dict(provenance),
        )


@dataclass(frozen=True, slots=True)
class MigrationSimulationSpec:
    plan_id: str
    source_revision: str
    target_revision: str
    lock_budget_milliseconds: int
    observed_lock_milliseconds: int
    plan_sha256: str

    @classmethod
    def from_document(cls, document: object) -> MigrationSimulationSpec:
        value = _mapping(document, "migration")
        _exact_keys(
            value,
            {
                "classification",
                "plan_id",
                "strategy",
                "source_revision",
                "target_revision",
                "steps",
                "dry_run",
                "independent_review",
                "database_execution",
            },
            "migration",
        )
        _literal(
            value["classification"],
            "IN_MEMORY_EXPAND_MIGRATE_CONTRACT_SIMULATION_ONLY",
            "migration.classification",
        )
        plan_id = _identifier(
            value["plan_id"], "migration.plan_id", prefix="st1505-migration-"
        )
        _literal(value["strategy"], "EXPAND_MIGRATE_CONTRACT", "migration.strategy")
        source_revision = _identifier(
            value["source_revision"], "migration.source_revision", prefix="fixture-"
        )
        target_revision = _identifier(
            value["target_revision"], "migration.target_revision", prefix="fixture-"
        )
        if source_revision == target_revision:
            _fail("MIGRATION_REVISION_UNCHANGED", "migration.target_revision")
        steps = _sequence(value["steps"], "migration.steps")
        expected = (
            (1, "EXPAND", "ADD_OPTIONAL_SYNTHETIC_FIELD", "SIMULATED_PASS"),
            (2, "MIGRATE", "BACKFILL_SYNTHETIC_RECORD", "SIMULATED_PASS"),
            (3, "CONTRACT", "DEFER_DESTRUCTIVE_CONTRACT", "DEFERRED_LATER_RELEASE"),
        )
        observed_steps: list[dict[str, object]] = []
        if len(steps) != len(expected):
            _fail("MIGRATION_PHASE_INVENTORY_INVALID", "migration.steps")
        for raw, expected_row in zip(steps, expected, strict=True):
            row = _mapping(raw, "migration.step")
            _exact_keys(
                row,
                {
                    "sequence",
                    "phase",
                    "operation",
                    "destructive",
                    "database_write",
                    "status",
                },
                "migration.step",
            )
            sequence, phase, operation, status = expected_row
            if _int(row["sequence"], "migration.step.sequence", minimum=1) != sequence:
                _fail("MIGRATION_ORDER_INVALID", "migration.step.sequence")
            _literal(row["phase"], phase, "migration.step.phase")
            _literal(row["operation"], operation, "migration.step.operation")
            _bool(row["destructive"], False, "migration.step.destructive")
            _bool(row["database_write"], False, "migration.step.database_write")
            _literal(row["status"], status, "migration.step.status")
            observed_steps.append(dict(row))

        dry_run = _mapping(value["dry_run"], "migration.dry_run")
        _exact_keys(
            dry_run,
            {
                "execution_mode",
                "database_connection",
                "statement_execution_count",
                "external_action_count",
                "lock_budget_milliseconds",
                "observed_lock_milliseconds",
                "backward_compatible_before",
                "backward_compatible_after",
                "forward_fix_ready",
                "result",
            },
            "migration.dry_run",
        )
        _literal(
            dry_run["execution_mode"],
            "IN_MEMORY_RECORDED_ONLY",
            "migration.dry_run.mode",
        )
        _literal(dry_run["database_connection"], "ABSENT", "migration.dry_run.database")
        _zero(
            dry_run["statement_execution_count"],
            "migration.dry_run.statement_count",
        )
        _zero(dry_run["external_action_count"], "migration.dry_run.external_count")
        lock_budget = _int(
            dry_run["lock_budget_milliseconds"],
            "migration.dry_run.lock_budget",
            minimum=1,
        )
        observed_lock = _int(
            dry_run["observed_lock_milliseconds"],
            "migration.dry_run.observed_lock",
        )
        if observed_lock > lock_budget:
            _fail("MIGRATION_LOCK_BUDGET_EXCEEDED", "migration.dry_run.observed_lock")
        _bool(
            dry_run["backward_compatible_before"],
            True,
            "migration.dry_run.compatibility_before",
        )
        _bool(
            dry_run["backward_compatible_after"],
            True,
            "migration.dry_run.compatibility_after",
        )
        _bool(dry_run["forward_fix_ready"], True, "migration.dry_run.forward_fix")
        _literal(dry_run["result"], "PASS", "migration.dry_run.result")
        _literal(
            value["independent_review"],
            "NOT_EXECUTED",
            "migration.independent_review",
        )
        _literal(
            value["database_execution"],
            "NOT_EXECUTED",
            "migration.database_execution",
        )
        plan_payload = {
            "plan_id": plan_id,
            "strategy": "EXPAND_MIGRATE_CONTRACT",
            "source_revision": source_revision,
            "target_revision": target_revision,
            "steps": observed_steps,
            "dry_run": dict(dry_run),
        }
        return cls(
            plan_id=plan_id,
            source_revision=source_revision,
            target_revision=target_revision,
            lock_budget_milliseconds=lock_budget,
            observed_lock_milliseconds=observed_lock,
            plan_sha256=canonical_sha256(plan_payload),
        )


@dataclass(frozen=True, slots=True)
class RecordedHealthSurface:
    surface: str
    url: str
    response_sha256: str

    @classmethod
    def from_document(
        cls, document: object, *, expected_surface: str
    ) -> RecordedHealthSurface:
        value = _mapping(document, "health.surface")
        _exact_keys(
            value,
            {
                "surface",
                "trust_boundary",
                "url",
                "request_execution",
                "status_code",
                "body",
            },
            "health.surface",
        )
        _literal(value["surface"], expected_surface, "health.surface.name")
        _literal(value["trust_boundary"], expected_surface, "health.surface.trust")
        url = _string(value["url"], "health.surface.url")
        parsed = urlsplit(url)
        expected = SURFACE_EXPECTATIONS[expected_surface]
        try:
            host = ipaddress.ip_address(parsed.hostname or "")
            parsed_port = parsed.port
        except ValueError:
            _fail("LOOPBACK_URL_REQUIRED", "health.surface.url")
        if (
            parsed.scheme != "http"
            or not host.is_loopback
            or parsed.hostname != "127.0.0.1"
            or parsed_port != expected["port"]
            or parsed.path != expected["path"]
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            _fail("LOOPBACK_URL_REQUIRED", "health.surface.url")
        _literal(
            value["request_execution"],
            "NOT_PERFORMED_RECORDED_RESPONSE_ONLY",
            "health.surface.request_execution",
        )
        if _int(value["status_code"], "health.surface.status", minimum=100) != 200:
            _fail("RECORDED_HEALTH_STATUS_INVALID", "health.surface.status")
        body = _mapping(value["body"], "health.surface.body")
        _exact_keys(
            body,
            {
                "schema",
                "surface",
                "liveness",
                "readiness",
                "dependencies",
                "migration_compatibility",
                "data_scope",
                "identity_state",
                "direct_data_plane_access",
                "synthetic",
            },
            "health.surface.body",
        )
        _literal(body["schema"], "RAOS_RECORDED_HEALTH_V1", "health.body.schema")
        _literal(body["surface"], expected_surface, "health.body.surface")
        _literal(body["liveness"], "PASS_PROCESS_ONLY_RECORDED", "health.body.liveness")
        _literal(
            body["readiness"],
            "PASS_DEPENDENCY_AND_MIGRATION_RECORDED",
            "health.body.readiness",
        )
        _literal(
            body["dependencies"], "PASS_SYNTHETIC_RECORDED", "health.body.dependencies"
        )
        _literal(
            body["migration_compatibility"],
            "PASS_SYNTHETIC_RECORDED",
            "health.body.migration",
        )
        for field in ("data_scope", "identity_state", "direct_data_plane_access"):
            _literal(body[field], cast(str, expected[field]), f"health.body.{field}")
        _bool(body["synthetic"], True, "health.body.synthetic")
        return cls(
            surface=expected_surface,
            url=url,
            response_sha256=canonical_sha256(dict(body)),
        )


@dataclass(frozen=True, slots=True)
class RollbackRestoreSimulationSpec:
    simulation_id: str
    prior_artifact_sha256: str
    configuration_snapshot_sha256: str
    restored_integrity_sha256: str

    @classmethod
    def from_document(
        cls, document: object, *, current_artifact_sha256: str
    ) -> RollbackRestoreSimulationSpec:
        value = _mapping(document, "rollback_restore")
        _exact_keys(
            value,
            {
                "classification",
                "simulation_id",
                "execution_mode",
                "current_artifact_sha256",
                "prior_artifact_payload_utf8",
                "prior_artifact_sha256",
                "configuration_snapshot_sha256",
                "migration_compatible",
                "role_and_isolation_verified",
                "destructive_reversal",
                "external_action_count",
                "restored_integrity_sha256",
                "formal_restore",
            },
            "rollback_restore",
        )
        _literal(
            value["classification"],
            "IN_MEMORY_ROLLBACK_RESTORE_INTEGRITY_SIMULATION_ONLY",
            "rollback_restore.classification",
        )
        simulation_id = _identifier(
            value["simulation_id"],
            "rollback_restore.simulation_id",
            prefix="st1505-rollback-",
        )
        _literal(
            value["execution_mode"],
            "IN_MEMORY_RECORDED_ONLY",
            "rollback_restore.execution_mode",
        )
        if (
            _sha256(
                value["current_artifact_sha256"],
                "rollback_restore.current_artifact_sha256",
            )
            != current_artifact_sha256
        ):
            _fail(
                "ROLLBACK_CURRENT_ARTIFACT_MISMATCH",
                "rollback_restore.current_artifact_sha256",
            )
        prior_payload = _payload(
            value["prior_artifact_payload_utf8"], "rollback_restore.prior_payload"
        )
        prior_sha = _sha256(
            value["prior_artifact_sha256"], "rollback_restore.prior_sha256"
        )
        if hashlib.sha256(prior_payload.encode("utf-8")).hexdigest() != prior_sha:
            _fail("ROLLBACK_PRIOR_ARTIFACT_MISMATCH", "rollback_restore.prior_sha256")
        configuration_sha = _sha256(
            value["configuration_snapshot_sha256"],
            "rollback_restore.configuration_sha256",
        )
        _bool(
            value["migration_compatible"],
            True,
            "rollback_restore.migration_compatible",
        )
        _bool(
            value["role_and_isolation_verified"],
            True,
            "rollback_restore.role_isolation",
        )
        _bool(
            value["destructive_reversal"],
            False,
            "rollback_restore.destructive_reversal",
        )
        _zero(value["external_action_count"], "rollback_restore.external_actions")
        restored_sha = _sha256(
            value["restored_integrity_sha256"],
            "rollback_restore.restored_integrity_sha256",
        )
        expected_restored = canonical_sha256(
            {
                "prior_artifact_sha256": prior_sha,
                "configuration_snapshot_sha256": configuration_sha,
                "migration_compatible": True,
                "role_and_isolation_verified": True,
            }
        )
        if restored_sha != expected_restored:
            _fail("RESTORED_INTEGRITY_MISMATCH", "rollback_restore.restored_integrity")
        _literal(
            value["formal_restore"],
            "NOT_EXECUTED",
            "rollback_restore.formal_restore",
        )
        return cls(
            simulation_id=simulation_id,
            prior_artifact_sha256=prior_sha,
            configuration_snapshot_sha256=configuration_sha,
            restored_integrity_sha256=restored_sha,
        )


@dataclass(frozen=True, slots=True)
class LocalStagingAdmissionSpec:
    fixture_id: str
    pipeline_id: str
    semantic_sha256: str
    identity_policy_id: str
    identity_fixture_id: str
    identity_evaluation_digest: str
    artifact: ArtifactAdmissionSpec
    migration: MigrationSimulationSpec
    health_surfaces: tuple[RecordedHealthSurface, ...]
    rollback_restore: RollbackRestoreSimulationSpec
    action_counts: tuple[tuple[str, int], ...]

    @classmethod
    def from_document(cls, document: object) -> LocalStagingAdmissionSpec:
        value = _mapping(document, "runtime_contract")
        _exact_keys(
            value,
            {
                "document",
                "predecessor_bindings",
                "pipeline",
                "identity_boundary",
                "artifact",
                "migration",
                "health",
                "rollback_restore",
                "durable_journal",
                "execution_boundary",
                "evidence_boundary",
            },
            "runtime_contract",
        )
        metadata = _mapping(value["document"], "document")
        _exact_keys(
            metadata,
            {
                "id",
                "version",
                "story_id",
                "status",
                "canonical_status_effect",
                "formal_verification",
            },
            "document",
        )
        _literal(metadata["id"], "RAOS-LOCAL-STAGING-ADMISSION-002", "document.id")
        _literal(metadata["version"], "2.0.0", "document.version")
        _literal(metadata["story_id"], "ST-1505", "document.story")
        _literal(
            metadata["status"],
            "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE_PROPOSAL",
            "document.status",
        )
        _literal(metadata["canonical_status_effect"], "NONE", "document.effect")
        _literal(metadata["formal_verification"], "NOT_EXECUTED", "document.formal")

        predecessors = _mapping(value["predecessor_bindings"], "predecessors")
        if tuple(predecessors) != ("ST-1502", "ST-1503", "ST-1504"):
            _fail("PREDECESSOR_INVENTORY_INVALID", "predecessors")
        for story_id, raw in predecessors.items():
            row = _mapping(raw, "predecessor")
            _exact_keys(
                row,
                {
                    "story_id",
                    "contract_uri",
                    "contract_sha256",
                    "reference_plan_uri",
                    "reference_plan_sha256",
                    "required_status",
                    "required_activation",
                    "required_external_actions",
                },
                "predecessor",
            )
            _literal(row["story_id"], story_id, "predecessor.story_id")
            contract_uri = _string(row["contract_uri"], "predecessor.contract_uri")
            plan_uri = _string(row["reference_plan_uri"], "predecessor.plan_uri")
            if not contract_uri.startswith(
                "repo://changes/"
            ) or not plan_uri.startswith("repo://infra/terraform/"):
                _fail("PREDECESSOR_URI_INVALID", "predecessor.uri")
            _sha256(row["contract_sha256"], "predecessor.contract_sha256")
            _sha256(row["reference_plan_sha256"], "predecessor.plan_sha256")
            _literal(
                row["required_status"],
                "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE",
                "predecessor.status",
            )
            _literal(row["required_activation"], "DISABLED", "predecessor.activation")
            _zero(row["required_external_actions"], "predecessor.external_actions")

        pipeline = _mapping(value["pipeline"], "pipeline")
        _exact_keys(
            pipeline,
            {
                "schema",
                "fixture_id",
                "pipeline_id",
                "classification",
                "repository_inert",
                "default_enabled",
                "local_execution_mode",
                "phases",
            },
            "pipeline",
        )
        _literal(
            pipeline["schema"], "RAOS_LOCAL_STAGING_PIPELINE_V2", "pipeline.schema"
        )
        fixture_id = _identifier(
            pipeline["fixture_id"], "pipeline.fixture_id", prefix="st1505-fixture-"
        )
        pipeline_id = _identifier(
            pipeline["pipeline_id"], "pipeline.pipeline_id", prefix="st1505-pipeline-"
        )
        _literal(
            pipeline["classification"],
            "REPOSITORY_INERT_EXPLICIT_LOCAL_SIMULATION_ONLY",
            "pipeline.classification",
        )
        _bool(pipeline["repository_inert"], True, "pipeline.repository_inert")
        _bool(pipeline["default_enabled"], False, "pipeline.default_enabled")
        _literal(
            pipeline["local_execution_mode"],
            "EXPLICIT_CALL_RECORDED_FIXTURE_ONLY",
            "pipeline.local_execution_mode",
        )
        if (
            tuple(
                _string(item, "pipeline.phase")
                for item in _sequence(pipeline["phases"], "pipeline.phases")
            )
            != PIPELINE_PHASES
        ):
            _fail("PIPELINE_PHASE_ORDER_INVALID", "pipeline.phases")

        identity = _mapping(value["identity_boundary"], "identity")
        _exact_keys(
            identity,
            {
                "source_story",
                "source_manifest_uri",
                "source_manifest_sha256",
                "source_activation_port_uri",
                "source_activation_port_sha256",
                "policy_id",
                "fixture_id",
                "evaluation_fixture_uri",
                "evaluation_fixture_sha256",
                "evaluation_digest",
                "policy_match_only",
                "authentication",
                "signature_verification",
                "activation",
                "credential_issuance",
                "deployment_authority",
                "action_count",
            },
            "identity",
        )
        _literal(identity["source_story"], "ST-1504", "identity.source_story")
        _literal(
            identity["source_manifest_uri"],
            "repo://changes/st-1504/manifest.yaml",
            "identity.source_manifest_uri",
        )
        _sha256(
            identity["source_manifest_sha256"],
            "identity.source_manifest_sha256",
        )
        _literal(
            identity["source_activation_port_uri"],
            "repo://python/raos/ports/deployment_identity.py",
            "identity.source_activation_port_uri",
        )
        _sha256(
            identity["source_activation_port_sha256"],
            "identity.source_activation_port_sha256",
        )
        policy_id = _identifier(
            identity["policy_id"], "identity.policy_id", prefix="st1504-policy-"
        )
        identity_fixture_id = _identifier(
            identity["fixture_id"], "identity.fixture_id", prefix="st1504-fixture-"
        )
        _literal(
            identity["evaluation_fixture_uri"],
            "repo://infra/terraform/deployment-identity/github-oidc.evaluation.recorded.v1.json",
            "identity.evaluation_fixture_uri",
        )
        _sha256(identity["evaluation_fixture_sha256"], "identity.fixture_sha256")
        evaluation_digest = _sha256(
            identity["evaluation_digest"], "identity.evaluation_digest"
        )
        _bool(identity["policy_match_only"], True, "identity.policy_match_only")
        _literal(identity["authentication"], "NOT_AUTHENTICATED", "identity.auth")
        _literal(
            identity["signature_verification"],
            "NOT_PERFORMED",
            "identity.signature",
        )
        _literal(identity["activation"], "DISABLED", "identity.activation")
        _literal(identity["credential_issuance"], "FORBIDDEN", "identity.credential")
        _literal(
            identity["deployment_authority"], "NONE", "identity.deployment_authority"
        )
        _zero(identity["action_count"], "identity.action_count")

        artifact = ArtifactAdmissionSpec.from_document(value["artifact"])
        migration = MigrationSimulationSpec.from_document(value["migration"])

        health = _mapping(value["health"], "health")
        _exact_keys(
            health,
            {
                "classification",
                "network_requests",
                "generic_http_200_inference",
                "surfaces",
                "formal_smoke",
                "formal_browser",
            },
            "health",
        )
        _literal(
            health["classification"],
            "RECORDED_LOOPBACK_RESPONSE_VALIDATION_ONLY",
            "health.classification",
        )
        _zero(health["network_requests"], "health.network_requests")
        _literal(
            health["generic_http_200_inference"],
            "FORBIDDEN",
            "health.generic_http_200",
        )
        surfaces = _sequence(health["surfaces"], "health.surfaces")
        if len(surfaces) != len(SURFACE_ORDER):
            _fail("HEALTH_SURFACE_INVENTORY_INVALID", "health.surfaces")
        parsed_surfaces = tuple(
            RecordedHealthSurface.from_document(raw, expected_surface=surface)
            for raw, surface in zip(surfaces, SURFACE_ORDER, strict=True)
        )
        _literal(health["formal_smoke"], "NOT_EXECUTED", "health.formal_smoke")
        _literal(health["formal_browser"], "NOT_EXECUTED", "health.formal_browser")

        rollback = RollbackRestoreSimulationSpec.from_document(
            value["rollback_restore"],
            current_artifact_sha256=artifact.payload_sha256,
        )

        journal = _mapping(value["durable_journal"], "durable_journal")
        _exact_keys(
            journal,
            {
                "classification",
                "persistence",
                "owner_private",
                "initialization",
                "preexisting_empty_storage_adoption",
                "schema_inventory",
                "filesystem_identity_binding",
                "process_monotonic_anchor",
                "append_only_lifecycle_audit_guards",
                "replacement_and_rollback_detection",
                "idempotency",
                "commit_ambiguity_recovery",
                "restart_recovery",
                "hash_chain_tamper_detection",
                "concurrency_control",
                "credential_or_production_data",
            },
            "durable_journal",
        )
        _literal(
            journal["classification"],
            "OWNER_PRIVATE_LOCAL_SQLITE_JOURNAL_ONLY",
            "durable_journal.classification",
        )
        _literal(journal["persistence"], "LOCAL_ONLY", "durable_journal.persistence")
        _bool(journal["owner_private"], True, "durable_journal.owner_private")
        _literal(
            journal["initialization"],
            "CREATED_ONLY_FAIL_CLOSED",
            "durable_journal.initialization",
        )
        _literal(
            journal["preexisting_empty_storage_adoption"],
            "FORBIDDEN",
            "durable_journal.preexisting_empty_storage_adoption",
        )
        _literal(
            journal["schema_inventory"],
            "EXACT_STRICT_APPLICATION_ID_USER_VERSION",
            "durable_journal.schema_inventory",
        )
        _literal(
            journal["filesystem_identity_binding"],
            "ROOT_AND_DATABASE_DEVICE_INODE_REQUIRED",
            "durable_journal.filesystem_identity_binding",
        )
        for field in (
            "process_monotonic_anchor",
            "append_only_lifecycle_audit_guards",
            "replacement_and_rollback_detection",
            "idempotency",
            "commit_ambiguity_recovery",
            "restart_recovery",
            "hash_chain_tamper_detection",
            "concurrency_control",
        ):
            _literal(journal[field], "REQUIRED", f"durable_journal.{field}")
        _literal(
            journal["credential_or_production_data"],
            "FORBIDDEN",
            "durable_journal.data",
        )

        execution = _mapping(value["execution_boundary"], "execution")
        _exact_keys(
            execution,
            {
                "local_simulation",
                "external_activation",
                "credentials",
                "provider_sdk",
                "network_client",
                "selected_target",
                "action_counts",
            },
            "execution",
        )
        _literal(
            execution["local_simulation"],
            "IMPLEMENTED_EXPLICIT_ONLY",
            "execution.local_simulation",
        )
        _literal(execution["external_activation"], "DISABLED", "execution.activation")
        _literal(execution["credentials"], "ABSENT", "execution.credentials")
        _literal(execution["provider_sdk"], "ABSENT", "execution.provider_sdk")
        _literal(execution["network_client"], "ABSENT", "execution.network_client")
        if execution["selected_target"] is not None:
            _fail("SELECTION_MUST_REMAIN_UNSET", "execution.selected_target")
        actions = _mapping(execution["action_counts"], "execution.action_counts")
        if tuple(actions) != EXTERNAL_ACTION_NAMES:
            _fail("ACTION_INVENTORY_INVALID", "execution.action_counts")
        action_counts: list[tuple[str, int]] = []
        for name in EXTERNAL_ACTION_NAMES:
            _zero(actions[name], f"execution.action_counts.{name}")
            action_counts.append((name, 0))

        evidence = _mapping(value["evidence_boundary"], "evidence")
        _exact_keys(
            evidence,
            {
                "local_runtime",
                "artifact_admission",
                "migration_simulation",
                "loopback_health",
                "rollback_restore_simulation",
                "formal_tst_009",
                "formal_tst_022",
                "staging",
                "release",
                "production",
                "canonical_status_effect",
            },
            "evidence",
        )
        for field in (
            "local_runtime",
            "artifact_admission",
            "migration_simulation",
            "loopback_health",
            "rollback_restore_simulation",
        ):
            _literal(
                evidence[field], "IMPLEMENTED_LOCAL_NOT_FORMAL", f"evidence.{field}"
            )
        for field in (
            "formal_tst_009",
            "formal_tst_022",
            "staging",
            "release",
            "production",
        ):
            _literal(evidence[field], "NOT_EXECUTED", f"evidence.{field}")
        _literal(evidence["canonical_status_effect"], "NONE", "evidence.effect")

        semantic = canonical_sha256(dict(value))
        return cls(
            fixture_id=fixture_id,
            pipeline_id=pipeline_id,
            semantic_sha256=semantic,
            identity_policy_id=policy_id,
            identity_fixture_id=identity_fixture_id,
            identity_evaluation_digest=evaluation_digest,
            artifact=artifact,
            migration=migration,
            health_surfaces=parsed_surfaces,
            rollback_restore=rollback,
            action_counts=tuple(action_counts),
        )


@dataclass(frozen=True, slots=True)
class LocalAdmissionEvaluation:
    fixture_id: str
    pipeline_id: str
    contract_sha256: str
    stage_evidence: tuple[tuple[str, str], ...]
    action_counts: tuple[tuple[str, int], ...]
    result_sha256: str

    def to_document(self) -> dict[str, object]:
        base: dict[str, object] = {
            "schema": "RAOS_LOCAL_STAGING_ADMISSION_RESULT_V2",
            "version": 2,
            "fixture_id": self.fixture_id,
            "pipeline_id": self.pipeline_id,
            "status": "LOCAL_ADMISSION_SIMULATION_COMPLETE",
            "classification": "DETERMINISTIC_RECORDED_LOCAL_ONLY_NOT_STAGING_EVIDENCE",
            "contract_sha256": self.contract_sha256,
            "stage_evidence": [
                {"phase": phase, "evidence_sha256": digest}
                for phase, digest in self.stage_evidence
            ],
            "action_counts": dict(self.action_counts),
            "identity": {
                "activation": "DISABLED",
                "authentication": "NOT_AUTHENTICATED",
                "credentials_issued": False,
                "deployment_authorized": False,
                "actions_executed": 0,
            },
            "artifact": {
                "immutable_digest_verified": True,
                "sbom_binding_verified": True,
                "critical_high_findings": 0,
                "recorded_provenance_binding_verified": True,
                "cryptographic_signature_verification": "NOT_PERFORMED",
                "formal_attestation": "NOT_EXECUTED",
            },
            "migration": {
                "strategy": "EXPAND_MIGRATE_CONTRACT",
                "dry_run": "PASS_RECORDED_IN_MEMORY",
                "database_execution": "NOT_EXECUTED",
                "independent_review": "NOT_EXECUTED",
                "destructive_contract_current_release": False,
            },
            "health": {
                "surfaces": list(SURFACE_ORDER),
                "network_requests": 0,
                "formal_smoke": "NOT_EXECUTED",
                "formal_browser": "NOT_EXECUTED",
            },
            "rollback_restore": {
                "integrity_simulation": "PASS_RECORDED_IN_MEMORY",
                "external_actions": 0,
                "formal_restore": "NOT_EXECUTED",
            },
            "external_evidence": {
                "formal_tst_009": "NOT_EXECUTED",
                "formal_tst_022": "NOT_EXECUTED",
                "staging": "NOT_EXECUTED",
                "release": "NOT_EXECUTED",
                "production": "NOT_EXECUTED",
            },
        }
        if canonical_sha256(base) != self.result_sha256:
            _fail("RESULT_DIGEST_INTERNAL_MISMATCH", "result")
        base["result_sha256"] = self.result_sha256
        return base


def evaluate_local_admission(
    spec: LocalStagingAdmissionSpec,
    *,
    identity_activation_status: str,
    identity_activation_allowed: bool,
    identity_credentials_issued: bool,
    identity_actions_executed: int,
) -> LocalAdmissionEvaluation:
    """Evaluate all local phases after an exact ST-1504 disabled receipt."""

    if identity_activation_status != "DISABLED":
        _fail("IDENTITY_ACTIVATION_NOT_DISABLED", "identity_receipt.status")
    if type(identity_activation_allowed) is not bool or identity_activation_allowed:
        _fail("IDENTITY_ACTIVATION_AUTHORITY_FORBIDDEN", "identity_receipt.activation")
    if type(identity_credentials_issued) is not bool or identity_credentials_issued:
        _fail("IDENTITY_CREDENTIAL_ISSUANCE_FORBIDDEN", "identity_receipt.credentials")
    if type(identity_actions_executed) is not int or identity_actions_executed != 0:
        _fail("IDENTITY_ACTION_FORBIDDEN", "identity_receipt.actions")

    stage_payloads: tuple[tuple[str, object], ...] = (
        (
            "SAFETY_BOUNDARY",
            {
                "identity_policy_id": spec.identity_policy_id,
                "identity_fixture_id": spec.identity_fixture_id,
                "identity_evaluation_digest": spec.identity_evaluation_digest,
                "activation": "DISABLED",
                "actions": 0,
            },
        ),
        (
            "ARTIFACT_ADMISSION",
            {
                "artifact_sha256": spec.artifact.payload_sha256,
                "sbom_sha256": spec.artifact.sbom_sha256,
                "provenance_sha256": canonical_sha256(spec.artifact.provenance),
                "critical_high_findings": 0,
            },
        ),
        (
            "MIGRATION_PLAN",
            {
                "plan_id": spec.migration.plan_id,
                "plan_sha256": spec.migration.plan_sha256,
                "strategy": "EXPAND_MIGRATE_CONTRACT",
            },
        ),
        (
            "MIGRATION_DRY_RUN",
            {
                "lock_budget_milliseconds": spec.migration.lock_budget_milliseconds,
                "observed_lock_milliseconds": spec.migration.observed_lock_milliseconds,
                "database_execution": "NOT_EXECUTED",
                "result": "PASS_RECORDED_IN_MEMORY",
            },
        ),
        (
            "LOOPBACK_HEALTH",
            {
                "surfaces": [
                    {
                        "surface": surface.surface,
                        "url": surface.url,
                        "response_sha256": surface.response_sha256,
                    }
                    for surface in spec.health_surfaces
                ],
                "network_requests": 0,
            },
        ),
        (
            "ROLLBACK_RESTORE_SIMULATION",
            {
                "simulation_id": spec.rollback_restore.simulation_id,
                "prior_artifact_sha256": spec.rollback_restore.prior_artifact_sha256,
                "configuration_snapshot_sha256": spec.rollback_restore.configuration_snapshot_sha256,
                "restored_integrity_sha256": spec.rollback_restore.restored_integrity_sha256,
                "external_actions": 0,
            },
        ),
        (
            "LOCAL_ADMISSION_COMPLETE",
            {
                "contract_sha256": spec.semantic_sha256,
                "external_action_count": 0,
                "formal_tst_009": "NOT_EXECUTED",
                "formal_tst_022": "NOT_EXECUTED",
            },
        ),
    )
    if tuple(phase for phase, _ in stage_payloads) != PIPELINE_PHASES:
        _fail("PIPELINE_PHASE_ORDER_INVALID", "evaluation")
    stage_evidence = tuple(
        (phase, canonical_sha256(payload)) for phase, payload in stage_payloads
    )
    base: dict[str, object] = {
        "schema": "RAOS_LOCAL_STAGING_ADMISSION_RESULT_V2",
        "version": 2,
        "fixture_id": spec.fixture_id,
        "pipeline_id": spec.pipeline_id,
        "status": "LOCAL_ADMISSION_SIMULATION_COMPLETE",
        "classification": "DETERMINISTIC_RECORDED_LOCAL_ONLY_NOT_STAGING_EVIDENCE",
        "contract_sha256": spec.semantic_sha256,
        "stage_evidence": [
            {"phase": phase, "evidence_sha256": digest}
            for phase, digest in stage_evidence
        ],
        "action_counts": dict(spec.action_counts),
        "identity": {
            "activation": "DISABLED",
            "authentication": "NOT_AUTHENTICATED",
            "credentials_issued": False,
            "deployment_authorized": False,
            "actions_executed": 0,
        },
        "artifact": {
            "immutable_digest_verified": True,
            "sbom_binding_verified": True,
            "critical_high_findings": 0,
            "recorded_provenance_binding_verified": True,
            "cryptographic_signature_verification": "NOT_PERFORMED",
            "formal_attestation": "NOT_EXECUTED",
        },
        "migration": {
            "strategy": "EXPAND_MIGRATE_CONTRACT",
            "dry_run": "PASS_RECORDED_IN_MEMORY",
            "database_execution": "NOT_EXECUTED",
            "independent_review": "NOT_EXECUTED",
            "destructive_contract_current_release": False,
        },
        "health": {
            "surfaces": list(SURFACE_ORDER),
            "network_requests": 0,
            "formal_smoke": "NOT_EXECUTED",
            "formal_browser": "NOT_EXECUTED",
        },
        "rollback_restore": {
            "integrity_simulation": "PASS_RECORDED_IN_MEMORY",
            "external_actions": 0,
            "formal_restore": "NOT_EXECUTED",
        },
        "external_evidence": {
            "formal_tst_009": "NOT_EXECUTED",
            "formal_tst_022": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    return LocalAdmissionEvaluation(
        fixture_id=spec.fixture_id,
        pipeline_id=spec.pipeline_id,
        contract_sha256=spec.semantic_sha256,
        stage_evidence=stage_evidence,
        action_counts=spec.action_counts,
        result_sha256=canonical_sha256(base),
    )
