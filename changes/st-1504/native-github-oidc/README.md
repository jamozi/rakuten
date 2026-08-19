# ST-1504 native GitHub OIDC candidate

This slice converts the existing ST-1504 identity intent into native IAM trust-role Terraform without creating credentials or deployment permissions.

Two distinct roles are created for staging and Production. Each trust policy requires the exact GitHub Actions audience, environment-based subject, immutable repository ID, git ref, environment name, and workflow name using `StringEquals`. The repository is fixed to `jamozi/rakuten`; wildcard trust and organization-wide subjects are absent.

The GitHub OIDC provider ARN is an explicit prerequisite input and is not created or discovered here. The roles have no inline or managed permission policy in this slice. Long-lived AWS access keys, GitHub cloud-key secrets, role chaining, and PR credential paths are absent.

Live role assumption, GitHub environment protection, Terraform plan/apply, staging deployment, release and Production remain NOT_EXECUTED. Before integration this branch must be reconstructed onto the exact integrated ST-1503 predecessor and verified with the pinned native Terraform toolchain.
