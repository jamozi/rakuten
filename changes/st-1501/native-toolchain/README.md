# ST-1501 native Terraform toolchain candidate

This slice is the first repository-native Terraform implementation step after
the existing interface-only ST-1501 foundation. It intentionally stops before
provider installation, backend configuration, AWS authentication, planning,
or any infrastructure write.

## Pinned candidate toolchain

- Terraform CLI: `1.15.8`
- AWS provider: `6.57.1`

The pins were selected from official upstream sources retrieved on 2026-08-18.
Terraform 1.16 was still beta and 1.17 alpha, so neither prerelease was selected.
AWS provider 6.57.1 is the documented bug-fix release replacing defective
6.57.0.

## Native HCL boundary

`infra/terraform/foundation/native/versions.tf` contains only the Terraform CLI
and provider source/version requirements. It contains no provider block,
backend block, resource, data source, module, output, account, region, CIDR,
KMS reference, credential source, budget, or resource instance.

This deliberately satisfies only the existing requirement that a native
Terraform toolchain be pinned before later HCL resource work begins. It does
not resolve OD-013 or any account/backend/network decision.

## Recorded-evidence wrapper

Use an independently obtained Terraform binary through the repository wrapper:

```bash
scripts/terraform_toolchain.sh --terraform /absolute/path/to/terraform version
scripts/terraform_toolchain.sh --terraform /absolute/path/to/terraform fmt-check
```

The wrapper requires a non-symlink absolute executable, probes JSON version
output for exact Terraform 1.15.8, starts Terraform with a closed environment,
and exposes only `version` and `fmt-check`.

There is intentionally no wrapper dispatch for `init`, `validate`, `plan`,
`apply`, `destroy`, `import`, or `refresh`. Provider download and lock-file
generation remain a later bounded step because they require a separately
reviewed network/cache/provenance contract.

## Status

This is a `LOCAL_IMPLEMENTATION_CANDIDATE`. Formal TST-026, native Terraform
validation, provider installation, `.terraform.lock.hcl`, state backend,
credentials, AWS calls, staging, release, and Production remain `NOT_EXECUTED`
or forbidden as recorded by the candidate contract.
