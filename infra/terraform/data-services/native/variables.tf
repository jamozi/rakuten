variable "kms_description" {
  type = string

  validation {
    condition     = length(trimspace(var.kms_description)) >= 8
    error_message = "kms_description must be explicit and non-empty."
  }
}

variable "bucket_names" {
  type = object({
    raw                = string
    publication        = string
    uploads_quarantine = string
    exports            = string
    audit_logs         = string
  })

  validation {
    condition = alltrue([
      for name in values(var.bucket_names) :
      length(trimspace(name)) >= 3 && length(name) <= 63
    ]) && length(toset(values(var.bucket_names))) == 5
    error_message = "All five S3 bucket names must be explicit, valid-length, and unique."
  }
}

variable "raw_object_lock_retention_days" {
  type = number

  validation {
    condition     = var.raw_object_lock_retention_days >= 1 && var.raw_object_lock_retention_days <= 3650
    error_message = "raw_object_lock_retention_days must be between 1 and 3650."
  }
}

variable "queue_configs" {
  type = map(object({
    name                       = string
    dlq_name                   = string
    visibility_timeout_seconds = number
    retention_seconds          = number
    max_receive_count          = number
    fifo                       = bool
  }))

  validation {
    condition = toset(keys(var.queue_configs)) == toset([
      "ingestion",
      "ai",
      "quality",
      "publication",
      "freshness",
      "analytics",
      "notification",
    ])
    error_message = "queue_configs must contain exactly the seven canonical queue classes."
  }

  validation {
    condition = alltrue([
      for config in values(var.queue_configs) :
      length(trimspace(config.name)) > 0 &&
      length(trimspace(config.dlq_name)) > 0 &&
      config.name != config.dlq_name &&
      config.visibility_timeout_seconds >= 1 &&
      config.visibility_timeout_seconds <= 43200 &&
      config.retention_seconds >= 60 &&
      config.retention_seconds <= 1209600 &&
      config.max_receive_count >= 1 &&
      config.max_receive_count <= 1000
    ])
    error_message = "Every queue requires explicit bounded names, timeout, retention, and redrive count."
  }
}

variable "database" {
  type = object({
    identifier                   = string
    engine_version               = string
    instance_class               = string
    allocated_storage_gib        = number
    max_allocated_storage_gib    = number
    storage_type                 = string
    subnet_ids                   = list(string)
    vpc_security_group_ids       = list(string)
    database_name                = string
    username                     = string
    port                         = number
    multi_az                     = bool
    backup_retention_days        = number
    final_snapshot_identifier    = string
  })

  validation {
    condition = (
      length(trimspace(var.database.identifier)) > 0 &&
      length(trimspace(var.database.engine_version)) > 0 &&
      length(trimspace(var.database.instance_class)) > 0 &&
      var.database.allocated_storage_gib >= 20 &&
      var.database.max_allocated_storage_gib >= var.database.allocated_storage_gib &&
      contains(["gp3", "io1", "io2"], var.database.storage_type) &&
      length(var.database.subnet_ids) >= 2 &&
      length(toset(var.database.subnet_ids)) == length(var.database.subnet_ids) &&
      length(var.database.vpc_security_group_ids) >= 1 &&
      length(toset(var.database.vpc_security_group_ids)) == length(var.database.vpc_security_group_ids) &&
      length(trimspace(var.database.database_name)) > 0 &&
      length(trimspace(var.database.username)) > 0 &&
      var.database.port >= 1 && var.database.port <= 65535 &&
      var.database.backup_retention_days >= 7 && var.database.backup_retention_days <= 35 &&
      length(trimspace(var.database.final_snapshot_identifier)) > 0
    )
    error_message = "database requires explicit private networking, storage, identity, port, backup, and snapshot configuration."
  }
}

variable "tags" {
  type = map(string)

  validation {
    condition     = length(var.tags) > 0
    error_message = "tags must be explicitly supplied."
  }
}
