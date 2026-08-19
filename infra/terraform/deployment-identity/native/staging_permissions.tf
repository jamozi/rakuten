data "aws_iam_policy_document" "staging_deployment" {
  statement {
    sid       = "UpdateExactStagingServices"
    effect    = "Allow"
    actions   = ["ecs:DescribeServices", "ecs:UpdateService"]
    resources = var.staging_deployment_resources.service_arns

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [var.staging_deployment_resources.cluster_arn]
    }
  }

  statement {
    sid       = "RunExactReviewedTasks"
    effect    = "Allow"
    actions   = ["ecs:RunTask"]
    resources = var.staging_deployment_resources.task_definition_arns

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [var.staging_deployment_resources.cluster_arn]
    }
  }

  statement {
    sid       = "ObserveOrStopOwnStagingTasks"
    effect    = "Allow"
    actions   = ["ecs:DescribeTasks", "ecs:StopTask"]
    resources = [var.staging_deployment_resources.task_namespace_arn]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [var.staging_deployment_resources.cluster_arn]
    }
  }

  statement {
    sid       = "PassOnlyExactEcsRoles"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = var.staging_deployment_resources.pass_role_arns

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }

  statement {
    sid       = "ReadExactTargetHealth"
    effect    = "Allow"
    actions   = ["elasticloadbalancing:DescribeTargetHealth"]
    resources = var.staging_deployment_resources.target_group_arns
  }

  statement {
    sid       = "InvalidateExactStagingDistributions"
    effect    = "Allow"
    actions   = ["cloudfront:CreateInvalidation"]
    resources = var.staging_deployment_resources.distribution_arns
  }
}

resource "aws_iam_role_policy" "staging_deployment" {
  name   = "raos-staging-deployment"
  role   = aws_iam_role.deployment["staging"].id
  policy = data.aws_iam_policy_document.staging_deployment.json
}
