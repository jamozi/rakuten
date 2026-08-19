variable "staging_deployment_resources" {
  type = object({
    cluster_arn          = string
    service_arns         = list(string)
    task_definition_arns = list(string)
    task_namespace_arn   = string
    pass_role_arns       = list(string)
    target_group_arns    = list(string)
    distribution_arns    = list(string)
  })

  validation {
    condition = (
      length(var.staging_deployment_resources.service_arns) >= 1 &&
      length(var.staging_deployment_resources.task_definition_arns) >= 1 &&
      length(var.staging_deployment_resources.pass_role_arns) >= 1 &&
      length(var.staging_deployment_resources.target_group_arns) >= 1 &&
      length(var.staging_deployment_resources.distribution_arns) >= 1 &&
      length(toset(var.staging_deployment_resources.service_arns)) == length(var.staging_deployment_resources.service_arns) &&
      length(toset(var.staging_deployment_resources.task_definition_arns)) == length(var.staging_deployment_resources.task_definition_arns) &&
      length(toset(var.staging_deployment_resources.pass_role_arns)) == length(var.staging_deployment_resources.pass_role_arns)
    )
    error_message = "Staging deployment resources must be explicit, non-empty, and unique."
  }

  validation {
    condition = (
      can(regex("^arn:aws:ecs:[a-z0-9-]+:[0-9]{12}:cluster/.+$", var.staging_deployment_resources.cluster_arn)) &&
      can(regex("^arn:aws:ecs:[a-z0-9-]+:[0-9]{12}:task/[^/]+/\\*$", var.staging_deployment_resources.task_namespace_arn)) &&
      alltrue([for arn in var.staging_deployment_resources.service_arns : can(regex("^arn:aws:ecs:[a-z0-9-]+:[0-9]{12}:service/[^/]+/.+$", arn))]) &&
      alltrue([for arn in var.staging_deployment_resources.task_definition_arns : can(regex("^arn:aws:ecs:[a-z0-9-]+:[0-9]{12}:task-definition/.+:[0-9]+$", arn))]) &&
      alltrue([for arn in var.staging_deployment_resources.pass_role_arns : can(regex("^arn:aws:iam::[0-9]{12}:role/.+$", arn))]) &&
      alltrue([for arn in var.staging_deployment_resources.target_group_arns : can(regex("^arn:aws:elasticloadbalancing:[a-z0-9-]+:[0-9]{12}:targetgroup/.+$", arn))]) &&
      alltrue([for arn in var.staging_deployment_resources.distribution_arns : can(regex("^arn:aws:cloudfront::[0-9]{12}:distribution/.+$", arn))])
    )
    error_message = "Every staging deployment resource must use the expected bounded AWS ARN shape."
  }
}
