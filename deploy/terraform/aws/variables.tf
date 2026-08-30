variable "aws_region" {
  description = "AWS region for the data plane."
  type        = string
}

variable "name_prefix" {
  description = "Prefix for globally and regionally scoped resource names."
  type        = string
  default     = "f1-analytics-prod"
}

variable "vpc_id" {
  description = "Existing VPC containing the application runtime."
  type        = string
}

variable "private_subnet_ids" {
  description = "At least two private subnet IDs in separate availability zones."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "Provide at least two private subnets for the RDS subnet group."
  }
}

variable "application_security_group_ids" {
  description = "Security groups whose workloads may connect to PostgreSQL."
  type        = set(string)
}

variable "lake_bucket_name" {
  description = "Globally unique S3 bucket name for the Parquet lake."
  type        = string
}

variable "database_name" {
  description = "Initial PostgreSQL database name."
  type        = string
  default     = "f1"
}

variable "database_username" {
  description = "RDS master username; the password is managed by Secrets Manager."
  type        = string
  default     = "f1_admin"
}

variable "database_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "database_allocated_storage_gib" {
  description = "Initial gp3 storage allocation."
  type        = number
  default     = 20
}

variable "database_max_storage_gib" {
  description = "Storage autoscaling ceiling."
  type        = number
  default     = 100
}

variable "database_multi_az" {
  description = "Create a synchronous standby in another AZ. Disable only for low-cost demos."
  type        = bool
  default     = true
}

variable "backup_retention_days" {
  description = "RDS automated backup retention."
  type        = number
  default     = 14

  validation {
    condition     = var.backup_retention_days >= 7 && var.backup_retention_days <= 35
    error_message = "Use 7 to 35 days of automated RDS backup retention."
  }
}

variable "noncurrent_lake_version_expiration_days" {
  description = "Days to retain superseded Parquet object versions."
  type        = number
  default     = 90
}

variable "alarm_sns_topic_arn" {
  description = "Optional SNS topic ARN for RDS CloudWatch alarms."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Additional tags applied to every resource."
  type        = map(string)
  default     = {}
}
