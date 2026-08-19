output "deployment_role_arns" {
  value = {
    for environment, role in aws_iam_role.deployment : environment => role.arn
  }
  sensitive = false
}
