output "database_endpoint" {
  description = "Private RDS hostname (configure as F1_PG_HOST)."
  value       = aws_db_instance.warehouse.address
}

output "database_port" {
  value = aws_db_instance.warehouse.port
}

output "database_master_secret_arn" {
  description = "Secrets Manager ARN generated and rotated by RDS."
  value       = aws_db_instance.warehouse.master_user_secret[0].secret_arn
}

output "lake_uri" {
  description = "Configure as F1_LAKE_URI."
  value       = "s3://${aws_s3_bucket.lake.id}/f1-lake"
}

output "lake_application_policy_arn" {
  description = "Attach this policy to the Dagster workload role."
  value       = aws_iam_policy.lake_application.arn
}
