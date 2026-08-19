from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/production-deployment.yml").read_text()
ADMISSION = (ROOT / "scripts/production_deployment_admission.py").read_text()


def test_only_manual_trigger_is_present() -> None:
    assert "workflow_dispatch:" in WORKFLOW
    for forbidden in ("push:", "pull_request:", "schedule:", "release:", "workflow_run:"):
        assert forbidden not in WORKFLOW


def test_production_is_disabled_by_default_and_environment_bound() -> None:
    assert "vars.RAOS_PRODUCTION_DEPLOYMENT_ENABLED == 'true'" in WORKFLOW
    assert "environment: production" in WORKFLOW


def test_four_independent_gate_inputs_are_required() -> None:
    for name in (
        "release_decision_sha256",
        "gate_report_sha256",
        "security_approval_sha256",
        "operations_approval_sha256",
    ):
        assert name in WORKFLOW
        assert name in ADMISSION
    assert "approval_gates:NOT_INDEPENDENT" in ADMISSION


def test_staging_and_rollback_evidence_are_bound() -> None:
    for name in (
        "staging_artifact_sha256",
        "staging_evidence_sha256",
        "rollback_artifact_sha256",
    ):
        assert name in WORKFLOW
        assert name in ADMISSION
    assert "SAME_AS_STAGING_ARTIFACT" in ADMISSION


def test_admission_precedes_oidc_and_commit_is_github_owned() -> None:
    assert WORKFLOW.index("Admit independent Production evidence") < WORKFLOW.index("Acquire short-lived Production AWS session")
    assert "COMMIT_SHA: ${{ github.sha }}" in WORKFLOW


def test_external_actions_are_immutable_pins() -> None:
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in WORKFLOW
    assert "aws-actions/configure-aws-credentials@e6de054238d6b7531b4efff3b6587d9aade6a06c" in WORKFLOW
    assert "persist-credentials: false" in WORKFLOW


def test_all_production_mutations_remain_disabled() -> None:
    for marker in (
        "ARTIFACT_PROMOTION=DISABLED",
        "PRODUCTION_DEPLOYMENT=DISABLED",
        "MIGRATION=DISABLED",
        "CANARY=DISABLED",
        "TRAFFIC_CHANGE=DISABLED",
        "ROLLBACK_EXECUTION=DISABLED",
        "TST_032=NOT_EXECUTED",
        "PRODUCTION_ACTION_COUNT=0",
        "TRAFFIC_CHANGE_COUNT=0",
    ):
        assert marker in WORKFLOW


def test_zero_hashes_and_duplicate_gates_fail_closed() -> None:
    assert 'ZERO_SHA256 = "0" * 64' in ADMISSION
    assert "INVALID_SHA256" in ADMISSION
    assert "len(set(gate_values)) != 4" in ADMISSION
