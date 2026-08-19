from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/staging-deployment.yml").read_text()
ADMISSION = (ROOT / "scripts/staging_deployment_admission.py").read_text()


def test_only_manual_trigger_is_present() -> None:
    assert "workflow_dispatch:" in WORKFLOW
    for forbidden in ("push:", "pull_request:", "schedule:", "release:", "workflow_run:"):
        assert forbidden not in WORKFLOW


def test_workflow_is_disabled_by_default() -> None:
    assert "vars.RAOS_STAGING_DEPLOYMENT_ENABLED == 'true'" in WORKFLOW
    assert "environment: staging" in WORKFLOW


def test_permissions_are_minimal_for_oidc() -> None:
    assert "contents: read" in WORKFLOW
    assert "id-token: write" in WORKFLOW
    assert "write-all" not in WORKFLOW
    assert "contents: write" not in WORKFLOW


def test_external_actions_are_immutable_pins() -> None:
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in WORKFLOW
    assert "aws-actions/configure-aws-credentials@e6de054238d6b7531b4efff3b6587d9aade6a06c" in WORKFLOW
    assert "persist-credentials: false" in WORKFLOW


def test_admission_occurs_before_oidc() -> None:
    assert WORKFLOW.index("Admit immutable staging inputs") < WORKFLOW.index("Acquire short-lived staging AWS session")
    assert "COMMIT_SHA: ${{ github.sha }}" in WORKFLOW


def test_concurrency_is_single_non_cancelling_lane() -> None:
    assert "group: raos-staging-deployment" in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW


def test_external_write_phases_are_still_closed() -> None:
    for marker in (
        "ARTIFACT_PROMOTION=DISABLED",
        "STAGING_DEPLOYMENT=DISABLED",
        "MIGRATE=DISABLED",
        "STAGING_SMOKE_GATE=DISABLED",
        "BROWSER_E2E_GATE=DISABLED",
        "EXTERNAL_WRITE_COUNT=0",
        "PRODUCTION_ACTION_COUNT=0",
    ):
        assert marker in WORKFLOW


def test_admission_rejects_production_tokens_and_requires_hashes() -> None:
    assert "PRODUCTION_FORBIDDEN" in ADMISSION
    assert 'SHA256 = re.compile(r"[0-9a-f]{64}' in ADMISSION
    assert 'GIT_COMMIT = re.compile' in ADMISSION
    assert '"environment": "STAGING"' in ADMISSION
    assert '"external_write_count": 0' in ADMISSION
    assert '"production_action_count": 0' in ADMISSION
