from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = (ROOT / "infra/terraform/deployment-identity/native/staging_permissions.tf").read_text()
VARIABLES = (ROOT / "infra/terraform/deployment-identity/native/staging_permissions_variables.tf").read_text()


def test_policy_attaches_only_to_staging_role() -> None:
    assert 'aws_iam_role.deployment["staging"].id' in POLICY
    assert 'deployment["production"]' not in POLICY


def test_task_definition_registration_is_not_allowed() -> None:
    assert "ecs:RegisterTaskDefinition" not in POLICY
    assert "ecs:DescribeTaskDefinition" not in POLICY


def test_actions_are_closed_and_no_global_wildcards_exist() -> None:
    for forbidden in ('Action = "*"', 'Resource = "*"', 'iam:*', 'kms:*', 's3:*', 'rds:*'):
        assert forbidden not in POLICY
    for allowed in (
        "ecs:DescribeServices",
        "ecs:UpdateService",
        "ecs:RunTask",
        "ecs:DescribeTasks",
        "ecs:StopTask",
        "iam:PassRole",
        "elasticloadbalancing:DescribeTargetHealth",
        "cloudfront:CreateInvalidation",
    ):
        assert allowed in POLICY


def test_passrole_is_limited_to_ecs_tasks() -> None:
    assert 'variable = "iam:PassedToService"' in POLICY
    assert 'values   = ["ecs-tasks.amazonaws.com"]' in POLICY


def test_ecs_operations_are_cluster_bound() -> None:
    assert POLICY.count('variable = "ecs:cluster"') == 3
    assert 'values   = [var.staging_deployment_resources.cluster_arn]' in POLICY


def test_ephemeral_task_wildcard_is_cluster_namespace_only() -> None:
    assert 'task/[^/]+/\\*$' in VARIABLES
    assert 'task_namespace_arn' in POLICY


def test_every_resource_class_is_explicit_input() -> None:
    for name in (
        "cluster_arn",
        "service_arns",
        "task_definition_arns",
        "task_namespace_arn",
        "pass_role_arns",
        "target_group_arns",
        "distribution_arns",
    ):
        assert name in VARIABLES
        assert name in POLICY
