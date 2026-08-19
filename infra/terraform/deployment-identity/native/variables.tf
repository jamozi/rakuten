variable "github_oidc_provider_arn" {
  type = string

  validation {
    condition = can(regex(
      "^arn:aws:iam::[0-9]{12}:oidc-provider/token\\.actions\\.githubusercontent\\.com$",
      var.github_oidc_provider_arn,
    ))
    error_message = "github_oidc_provider_arn must identify the exact GitHub Actions OIDC provider."
  }
}

variable "environments" {
  type = object({
    staging = object({
      name          = string
      ref           = string
      workflow_name = string
      role_name     = string
    })
    production = object({
      name          = string
      ref           = string
      workflow_name = string
      role_name     = string
    })
  })

  validation {
    condition = (
      length(trimspace(var.environments.staging.name)) > 0 &&
      length(trimspace(var.environments.production.name)) > 0 &&
      var.environments.staging.name != var.environments.production.name &&
      startswith(var.environments.staging.ref, "refs/heads/") &&
      startswith(var.environments.production.ref, "refs/heads/") &&
      length(trimspace(var.environments.staging.workflow_name)) > 0 &&
      length(trimspace(var.environments.production.workflow_name)) > 0 &&
      var.environments.staging.role_name != var.environments.production.role_name
    )
    error_message = "Staging and Production require distinct explicit environment, ref, workflow, and role bindings."
  }
}

variable "max_session_duration_seconds" {
  type = number
  default = 3600

  validation {
    condition     = var.max_session_duration_seconds == 3600
    error_message = "Deployment IAM roles use the minimum supported one-hour maximum session duration."
  }
}

variable "tags" {
  type = map(string)

  validation {
    condition     = length(var.tags) > 0
    error_message = "tags must be explicitly supplied."
  }
}
