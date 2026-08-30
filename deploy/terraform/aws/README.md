# AWS managed data plane

This Terraform root is a cloud-ready template, not evidence of an active
deployment. It provisions the stateful data plane while leaving Dagster compute
in the operator's existing ECS, Kubernetes, or VM environment:

- private, encrypted PostgreSQL 16 RDS with RDS-managed credentials, automated
  backups, deletion protection, Performance Insights, PostgreSQL logs, and
  CPU/storage alarms;
- a private, encrypted, versioned S3 Parquet lake with noncurrent-version
  retention and an application IAM policy;
- security-group ingress only from explicitly named application security
  groups.

## Apply safely

Configure an encrypted remote Terraform backend with state locking in your
organization bootstrap layer; do not keep production state on a laptop. Then:

```bash
cp terraform.tfvars.example terraform.tfvars
# Replace every placeholder and review the monthly cost implications.
terraform init
terraform fmt -check
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
```

The RDS resource uses `prevent_destroy` and deletion protection. Disaster
recovery must be deliberate: retain a final snapshot, remove the lifecycle guard
in a reviewed change, and only then disable deletion protection.

Read the generated RDS secret at runtime through the workload role instead of
copying it into Terraform variables. Configure the application with the output
endpoint, database name/user, and `lake_uri`; attach
`lake_application_policy_arn` to its role. Keep the database on private subnets
and connect Dagster through the VPC.

RDS automated backups cover point-in-time recovery. They do not replace the
portable `f1-ingest backup-postgres` dump and scheduled restore drill described
in the production runbook. The restore-drill operator needs a tightly scoped
`CREATEDB` capability; the normal ingestion role does not.
