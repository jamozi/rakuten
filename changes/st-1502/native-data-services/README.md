# ST-1502 native data-services candidate

This slice translates the existing ST-1502 logical data-service intent into
native Terraform module code while preserving the repository's external-action
boundary.

The module is intentionally not wired to a provider block, backend, account,
region, VPC, environment, workflow, or credential source. Every physical name
and runtime sizing/network value is an explicit caller input. There are no
default resource names or secret values.

## Implemented safeguards

- one customer-managed KMS key with rotation and `prevent_destroy`;
- five explicitly named S3 role buckets with public-access block, KMS
encryption, versioning, `force_destroy = false`, and `prevent_destroy`;
- the `raw` bucket is created with Object Lock and COMPLIANCE retention;
- seven canonical SQS classes, each with an explicit DLQ, KMS encryption, and
bounded redrive count;
- PostgreSQL RDS with explicit private subnets/security groups,
`publicly_accessible = false`, KMS encryption, deletion protection, final
snapshot, backups, and RDS-managed master password storage instead of a
plaintext password input.

## Still deliberately absent

Provider installation/lock provenance, provider configuration, account and
region selection, remote state, IAM workload policies, DB parameter/security
policy tuning, alarms, restore execution, Terraform plan/apply, AWS calls,
staging deployment, release, and Production remain separate work.

This candidate is stacked on the P3A toolchain branch only to accelerate
implementation. Before Ready for review it must be reconstructed on the exact
integrated P3A/main predecessor so the final PR graph contains only canonical
minimum dependencies.
