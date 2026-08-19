from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "infra/terraform/deployment-identity/native/main.tf").read_text()
VARIABLES = (ROOT / "infra/terraform/deployment-identity/native/variables.tf").read_text()


def test_repository_identity_is_exact_and_numeric_id_is_bound() -> None:
    assert 'repository    = "jamozi/rakuten"' in MAIN
    assert 'repository_id = "1322590419"' in MAIN
    assert 'token.actions.githubusercontent.com:repository_id' in MAIN


def test_audience_subject_ref_environment_and_workflow_are_exact() -> None:
    for claim in (
        'token.actions.githubusercontent.com:aud',
        'token.actions.githubusercontent.com:sub',
        'token.actions.githubusercontent.com:ref',
        'token.actions.githubusercontent.com:environment',
        'token.actions.githubusercontent.com:workflow',
    ):
        assert claim in MAIN
    assert 'test     = "StringEquals"' in MAIN
    assert 'StringLike' not in MAIN
    assert 'repo:${local.repository}:environment:${each.value.name}' in MAIN


def test_staging_and_production_roles_are_distinct() -> None:
    assert 'staging    = var.environments.staging' in MAIN
    assert 'production = var.environments.production' in MAIN
    assert 'var.environments.staging.role_name != var.environments.production.role_name' in VARIABLES


def test_only_web_identity_assumption_is_trusted() -> None:
    assert 'sts:AssumeRoleWithWebIdentity' in MAIN
    assert 'sts:AssumeRole"' not in MAIN
    assert 'aws_iam_role_policy' not in MAIN
    assert 'aws_iam_role_policy_attachment' not in MAIN
    assert 'managed_policy_arns' not in MAIN


def test_provider_is_explicit_and_not_created_or_discovered() -> None:
    assert 'variable "github_oidc_provider_arn"' in VARIABLES
    assert 'aws_iam_openid_connect_provider' not in MAIN
    assert 'data "aws_iam_openid_connect_provider"' not in MAIN


def test_session_is_bounded_and_roles_are_destroy_protected() -> None:
    assert 'var.max_session_duration_seconds >= 900' in VARIABLES
    assert 'var.max_session_duration_seconds <= 3600' in VARIABLES
    assert 'prevent_destroy = true' in MAIN


def test_no_long_lived_cloud_key_material_exists() -> None:
    combined = MAIN + VARIABLES
    for token in ('access_key', 'secret_key', 'session_token', 'AWS_ACCESS_KEY_ID'):
        assert token not in combined
