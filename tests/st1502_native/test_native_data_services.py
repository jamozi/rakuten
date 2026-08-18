from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "infra/terraform/data-services/native/main.tf"
VARIABLES = ROOT / "infra/terraform/data-services/native/variables.tf"
CONTRACT = ROOT / "changes/st-1502/native-data-services/contract.v1.yaml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_s3_is_private_encrypted_versioned_and_non_destructive() -> None:
    text = _text(MAIN)
    for statement in (
        "force_destroy       = false",
        "block_public_acls       = true",
        "block_public_policy     = true",
        "ignore_public_acls      = true",
        "restrict_public_buckets = true",
        'sse_algorithm     = "aws:kms"',
        'status = "Enabled"',
        'mode = "COMPLIANCE"',
        "prevent_destroy = true",
    ):
        assert statement in text


def test_queues_require_encryption_and_dlq_redrive() -> None:
    main = _text(MAIN)
    variables = _text(VARIABLES)
    for queue_class in (
        "ingestion",
        "ai",
        "quality",
        "publication",
        "freshness",
        "analytics",
        "notification",
    ):
        assert f'"{queue_class}"' in variables
    assert "kms_master_key_id         = aws_kms_key.data.arn" in main
    assert "deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn" in main
    assert "maxReceiveCount     = each.value.max_receive_count" in main


def test_rds_is_private_encrypted_recoverable_and_passwordless_input() -> None:
    main = _text(MAIN)
    variables = _text(VARIABLES)
    for statement in (
        'storage_type          = "gp3"',
        "storage_encrypted     = true",
        "publicly_accessible    = false",
        "manage_master_user_password   = true",
        "deletion_protection        = true",
        "skip_final_snapshot        = false",
        "prevent_destroy = true",
    ):
        assert statement in main
    assert 'variable "password"' not in variables
    assert "password_secret" not in variables
    assert "access_key" not in variables
    assert "secret_key" not in variables


def test_no_provider_backend_or_ambient_configuration_is_selected() -> None:
    text = "\n".join((_text(MAIN), _text(VARIABLES)))
    assert 'provider "aws"' not in text
    assert 'backend "' not in text
    assert "profile =" not in text
    assert "region =" not in text


def test_candidate_contract_preserves_external_action_boundary() -> None:
    text = _text(CONTRACT)
    for statement in (
        "status: LOCAL_IMPLEMENTATION_CANDIDATE",
        "aws_account_id: null",
        "region: null",
        "state_backend: null",
        "credential_source: null",
        "provider_calls: FORBIDDEN",
        "external_writes: FORBIDDEN",
        "apply: FORBIDDEN",
        "destroy: FORBIDDEN",
        "production: NOT_EXECUTED",
    ):
        assert statement in text
