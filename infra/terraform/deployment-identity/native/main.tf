locals {
  repository    = "jamozi/rakuten"
  repository_id = "1322590419"
  audience      = "sts.amazonaws.com"
  bindings = {
    staging    = var.environments.staging
    production = var.environments.production
  }
}

data "aws_iam_policy_document" "trust" {
  for_each = local.bindings

  statement {
    sid     = "GitHubOidcExactEnvironment"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = [local.audience]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${local.repository}:environment:${each.value.name}"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:repository_id"
      values   = [local.repository_id]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:ref"
      values   = [each.value.ref]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:environment"
      values   = [each.value.name]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:workflow"
      values   = [each.value.workflow_name]
    }
  }
}

resource "aws_iam_role" "deployment" {
  for_each = local.bindings

  name                 = each.value.role_name
  assume_role_policy   = data.aws_iam_policy_document.trust[each.key].json
  max_session_duration = var.max_session_duration_seconds
  tags                 = merge(var.tags, { raos_environment = each.key })

  lifecycle {
    prevent_destroy = true
  }
}
