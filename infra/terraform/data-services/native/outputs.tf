output "kms_key_arn" {
  value = aws_kms_key.data.arn
}

output "bucket_arns" {
  value = {
    for role, bucket in aws_s3_bucket.role : role => bucket.arn
  }
}

output "queue_arns" {
  value = {
    for class_name, queue in aws_sqs_queue.main : class_name => queue.arn
  }
}

output "queue_dlq_arns" {
  value = {
    for class_name, queue in aws_sqs_queue.dlq : class_name => queue.arn
  }
}

output "database_arn" {
  value = aws_db_instance.postgres.arn
}

output "database_endpoint" {
  value     = aws_db_instance.postgres.endpoint
  sensitive = true
}

output "database_master_secret_arn" {
  value = try(aws_db_instance.postgres.master_user_secret[0].secret_arn, null)
}
