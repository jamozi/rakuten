"""Positive local-only execution evidence for ST-1505."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from raos.adapters.disabled_deployment_identity import (
    DisabledDeploymentIdentityActivation,
)
from raos.application.ops.staging_admission import (
    LocalStagingAdmissionRun,
    LocalStagingAdmissionService,
)
from raos.domain.ops.staging_admission import (
    EXTERNAL_ACTION_NAMES,
    PIPELINE_PHASES,
    SURFACE_ORDER,
    LocalStagingAdmissionSpec,
    evaluate_local_admission,
)
from raos.adapters.recorded_staging_admission import (
    RecordedStagingAdmissionJournal,
)
from raos.staging_admission_runner import load_local_staging_admission_spec
from scripts import build_st1505_staging_deployment as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_contract_is_closed_hash_bound_and_local_only(
    runtime_document: dict[str, Any], runtime_spec: LocalStagingAdmissionSpec
) -> None:
    assert runtime_spec.semantic_sha256 == (
        "3177f52b7ed2dbf9f8651ce2961d9a8c21d679c750e13e54a876d0e5f09f5fca"
    )
    assert runtime_spec.action_counts == tuple(
        (name, 0) for name in EXTERNAL_ACTION_NAMES
    )
    assert runtime_document["execution_boundary"] == {
        "local_simulation": "IMPLEMENTED_EXPLICIT_ONLY",
        "external_activation": "DISABLED",
        "credentials": "ABSENT",
        "provider_sdk": "ABSENT",
        "network_client": "ABSENT",
        "selected_target": None,
        "action_counts": {name: 0 for name in EXTERNAL_ACTION_NAMES},
    }
    assert runtime_document["evidence_boundary"]["formal_tst_009"] == ("NOT_EXECUTED")
    assert runtime_document["evidence_boundary"]["formal_tst_022"] == ("NOT_EXECUTED")
    assert load_local_staging_admission_spec(REPOSITORY_ROOT) == runtime_spec


def test_artifact_sbom_scan_and_recorded_provenance_are_digest_bound(
    runtime_spec: LocalStagingAdmissionSpec,
) -> None:
    assert runtime_spec.artifact.payload_sha256 == (
        "d615727014ef5fd32023e7d1ce745cc89c08cbfde37d2838ace4acf3956cc345"
    )
    assert runtime_spec.artifact.sbom_sha256 == (
        "171cd38d63d5e37c8ec352a1a5fe8e735524d8fcf5bd909342e1536ce4a1a3df"
    )
    assert (
        runtime_spec.artifact.provenance["cryptographic_signature_verification"]
        == "NOT_PERFORMED"
    )
    assert runtime_spec.artifact.provenance["formal_attestation"] == "NOT_EXECUTED"
    assert runtime_spec.artifact.provenance["builder_id"].endswith(".invalid/builder")


def test_expand_migrate_contract_dry_run_and_restore_are_in_memory(
    runtime_document: dict[str, Any], runtime_spec: LocalStagingAdmissionSpec
) -> None:
    migration = runtime_document["migration"]
    assert [row["phase"] for row in migration["steps"]] == [
        "EXPAND",
        "MIGRATE",
        "CONTRACT",
    ]
    assert migration["steps"][-1]["status"] == "DEFERRED_LATER_RELEASE"
    assert all(row["database_write"] is False for row in migration["steps"])
    assert migration["dry_run"]["database_connection"] == "ABSENT"
    assert migration["database_execution"] == "NOT_EXECUTED"
    assert runtime_spec.migration.observed_lock_milliseconds == 0
    assert runtime_spec.rollback_restore.restored_integrity_sha256 == (
        "4cbc74b9e4e409154ea6869545f5765ec30f9d58a11505d09b40dbe02a49cd3b"
    )
    rollback = runtime_document["rollback_restore"]
    assert rollback["destructive_reversal"] is False
    assert rollback["external_action_count"] == 0
    assert rollback["formal_restore"] == "NOT_EXECUTED"


def test_recorded_health_covers_exact_isolated_loopback_surfaces(
    runtime_spec: LocalStagingAdmissionSpec,
) -> None:
    assert tuple(surface.surface for surface in runtime_spec.health_surfaces) == (
        SURFACE_ORDER
    )
    assert [surface.url for surface in runtime_spec.health_surfaces] == [
        "http://127.0.0.1:38101/health/readiness",
        "http://127.0.0.1:38102/admin/health/readiness",
        "http://127.0.0.1:38103/internal/health/readiness",
    ]
    assert (
        len({surface.response_sha256 for surface in runtime_spec.health_surfaces}) == 3
    )


def test_pure_evaluation_has_deterministic_phases_and_zero_external_actions(
    runtime_spec: LocalStagingAdmissionSpec,
) -> None:
    evaluation = evaluate_local_admission(
        runtime_spec,
        identity_activation_status="DISABLED",
        identity_activation_allowed=False,
        identity_credentials_issued=False,
        identity_actions_executed=0,
    )
    first = evaluation.to_document()
    second = evaluate_local_admission(
        runtime_spec,
        identity_activation_status="DISABLED",
        identity_activation_allowed=False,
        identity_credentials_issued=False,
        identity_actions_executed=0,
    ).to_document()
    assert first == second
    assert tuple(row["phase"] for row in first["stage_evidence"]) == PIPELINE_PHASES
    assert first["action_counts"] == {name: 0 for name in EXTERNAL_ACTION_NAMES}
    assert first["identity"] == {
        "activation": "DISABLED",
        "authentication": "NOT_AUTHENTICATED",
        "credentials_issued": False,
        "deployment_authorized": False,
        "actions_executed": 0,
    }
    assert set(first["external_evidence"].values()) == {"NOT_EXECUTED"}


def test_application_service_persists_only_local_canonical_result(
    runtime_spec: LocalStagingAdmissionSpec, owner_private_root: Path
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    service = LocalStagingAdmissionService(
        spec=runtime_spec,
        activation=DisabledDeploymentIdentityActivation(),
        journal=journal,
    )
    receipt = service.execute(
        LocalStagingAdmissionRun(
            run_id="st1505-run-positive-001",
            idempotency_key="st1505-key-positive-001",
        )
    )
    assert receipt.result_document["status"] == ("LOCAL_ADMISSION_SIMULATION_COMPLETE")
    assert receipt.persistence.sequence == 1
    assert receipt.persistence.replayed is False
    assert receipt.recovered_after_commit_ambiguity is False
    assert journal.verify_integrity() == 1
    database = owner_private_root / "st1505-local-admission.sqlite3"
    assert database.is_file()
    assert database.stat().st_mode & 0o777 == 0o600


def test_generated_pipeline_is_inert_and_recorded_result_is_not_staging_evidence(
    runtime_spec: LocalStagingAdmissionSpec,
) -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    pipeline = yaml.safe_load(outputs[generator.LOCAL_PIPELINE_PATH])
    result = json.loads(outputs[generator.LOCAL_RESULT_PATH])
    assert pipeline["activation"] == {
        "enabled": False,
        "default_enabled": False,
        "active_workflow_path": None,
        "trigger": "NONE",
        "selected_target": None,
        "credentials": "ABSENT",
        "provider_sdk": "ABSENT",
        "network_client": "ABSENT",
        "commands": [],
    }
    assert pipeline["pipeline"]["contract_sha256"] == runtime_spec.semantic_sha256
    assert pipeline["pipeline"]["action_counts"] == {
        name: 0 for name in EXTERNAL_ACTION_NAMES
    }
    assert result["classification"] == (
        "DETERMINISTIC_RECORDED_LOCAL_ONLY_NOT_STAGING_EVIDENCE"
    )
    assert result["external_evidence"] == {
        "formal_tst_009": "NOT_EXECUTED",
        "formal_tst_022": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
    }
