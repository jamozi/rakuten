variable "cluster_name" {
  type = string

  validation {
    condition     = length(trimspace(var.cluster_name)) >= 3
    error_message = "cluster_name must be explicit."
  }
}

variable "private_subnet_ids" {
  type = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2 && length(toset(var.private_subnet_ids)) == length(var.private_subnet_ids)
    error_message = "At least two unique private subnets are required."
  }
}

variable "service_security_group_ids" {
  type = map(string)

  validation {
    condition     = toset(keys(var.service_security_group_ids)) == toset(["public_web", "admin_web", "core_api", "worker_pool"])
    error_message = "Security groups must be supplied for all four workload roles."
  }
}

variable "alb_security_group_ids" {
  type = object({
    public = string
    admin  = string
  })
}

variable "workloads" {
  type = map(object({
    image_uri          = string
    container_port     = number
    cpu                = number
    memory             = number
    desired_count      = number
    execution_role_arn = string
    task_role_arn      = string
    health_path        = optional(string)
  }))

  validation {
    condition     = toset(keys(var.workloads)) == toset(["public_web", "admin_web", "core_api", "worker_pool"])
    error_message = "workloads must contain exactly the four canonical roles."
  }

  validation {
    condition = alltrue([
      for role, workload in var.workloads :
      can(regex("@sha256:[0-9a-f]{64}$", workload.image_uri)) &&
      workload.container_port >= 1 && workload.container_port <= 65535 &&
      workload.cpu >= 256 && workload.memory >= 512 && workload.desired_count >= 1 &&
      length(trimspace(workload.execution_role_arn)) > 0 &&
      length(trimspace(workload.task_role_arn)) > 0 &&
      (contains(["public_web", "admin_web"], role) ? try(startswith(workload.health_path, "/"), false) : true)
    ])
    error_message = "Each workload requires immutable image digest, bounded resources, roles, and edge health path where applicable."
  }
}

variable "log_kms_key_arn" {
  type = string
}

variable "log_retention_days" {
  type = number

  validation {
    condition     = var.log_retention_days >= 30 && var.log_retention_days <= 3650
    error_message = "log_retention_days must be between 30 and 3650."
  }
}

variable "certificate_arn" {
  type = string
}

variable "domains" {
  type = object({
    public = string
    admin  = string
  })

  validation {
    condition     = length(trimspace(var.domains.public)) > 0 && length(trimspace(var.domains.admin)) > 0 && var.domains.public != var.domains.admin
    error_message = "Distinct explicit public and admin domains are required."
  }
}

variable "web_acl_ids" {
  type = object({
    public = string
    admin  = string
  })

  validation {
    condition     = length(trimspace(var.web_acl_ids.public)) > 0 && length(trimspace(var.web_acl_ids.admin)) > 0
    error_message = "WAF Web ACL IDs are mandatory for both CloudFront surfaces."
  }
}

variable "tags" {
  type = map(string)

  validation {
    condition     = length(var.tags) > 0
    error_message = "tags must be explicitly supplied."
  }
}
