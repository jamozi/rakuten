resource "aws_kms_key" "data" {
  description             = var.kms_description
  enable_key_rotation     = true
  deletion_window_in_days = 30
  tags                    = var.tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket" "role" {
  for_each = var.bucket_names

  bucket              = each.value
  force_destroy       = false
  object_lock_enabled = each.key == "raw"
  tags                = merge(var.tags, { raos_role = each.key })

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "role" {
  for_each = aws_s3_bucket.role

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "role" {
  for_each = aws_s3_bucket.role

  bucket = each.value.id

  rule {
    bucket_key_enabled = true

    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.data.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_versioning" "role" {
  for_each = aws_s3_bucket.role

  bucket = each.value.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_object_lock_configuration" "raw" {
  bucket = aws_s3_bucket.role["raw"].id

  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = var.raw_object_lock_retention_days
    }
  }
}

resource "aws_sqs_queue" "dlq" {
  for_each = var.queue_configs

  name                      = each.value.dlq_name
  fifo_queue                = each.value.fifo
  message_retention_seconds = each.value.retention_seconds
  kms_master_key_id         = aws_kms_key.data.arn
  tags = merge(
    var.tags,
    { raos_queue_class = each.key, raos_queue_role = "dlq" },
  )
}

resource "aws_sqs_queue" "main" {
  for_each = var.queue_configs

  name                       = each.value.name
  fifo_queue                 = each.value.fifo
  visibility_timeout_seconds = each.value.visibility_timeout_seconds
  message_retention_seconds  = each.value.retention_seconds
  kms_master_key_id          = aws_kms_key.data.arn
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = each.value.max_receive_count
  })
  tags = merge(
    var.tags,
    { raos_queue_class = each.key, raos_queue_role = "main" },
  )
}

resource "aws_db_subnet_group" "postgres" {
  name       = "${var.database.identifier}-subnets"
  subnet_ids = var.database.subnet_ids
  tags       = var.tags
}

resource "aws_db_instance" "postgres" {
  identifier = var.database.identifier

  engine         = "postgres"
  engine_version = var.database.engine_version
  instance_class = var.database.instance_class

  allocated_storage     = var.database.allocated_storage_gib
  max_allocated_storage = var.database.max_allocated_storage_gib
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = aws_kms_key.data.arn

  db_name  = var.database.database_name
  username = var.database.username
  port     = var.database.port

  manage_master_user_password   = true
  master_user_secret_kms_key_id = aws_kms_key.data.arn

  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = var.database.vpc_security_group_ids
  publicly_accessible    = false
  multi_az               = var.database.multi_az

  backup_retention_period    = var.database.backup_retention_days
  deletion_protection        = true
  skip_final_snapshot        = false
  final_snapshot_identifier  = var.database.final_snapshot_identifier
  copy_tags_to_snapshot      = true
  auto_minor_version_upgrade = true
  apply_immediately          = false

  tags = var.tags

  lifecycle {
    prevent_destroy = true
  }
}
