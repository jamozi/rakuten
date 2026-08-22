# ST-1603 security verification reference pack

Status: `INTERFACE_ONLY_PARTIAL_LOCAL_CODE`

This Story-owned slice implements the maximum-safe local portion of the
approved ST-1603 Security verification pack. It deterministically projects the
canonical 83-control inventory and the required TST-026/TST-031 suite IDs plus
their unexecuted boundary into a source-derived reference plan. The plan is deliberately non-attesting:
it contains no scan, manual-review, finding, remediation, exception, approval,
or runtime evidence and cannot make a security, GATE-0, ST-1607, release, or
Production decision.

The projection may report all 83 canonical controls as represented, while the
verified count remains exactly 0. An empty result collection means that no
result was collected; it never means zero findings. Open Critical and High
finding counts remain `null`, approvals remain `null`, ASVS mappings remain
empty and `NOT_EXECUTED`, and the decision remains `NOT_READY`.

## Authority and predecessor boundary

- The owner-approved implementation-first ExecPlan authorizes this reversible
  W1 interface-only slice. It does not authorize any external or live action.
- The canonical ST-1603 record is `APPROVED_FOR_IMPLEMENTATION`, depends on
  ST-0407 and ST-1505, has no Open Decision, and requires TST-026 and TST-031.
- ST-0407 is consumed only as a byte-bound, material-free, fail-closed workload
  credential seam. This Story cannot obtain or inspect credential material.
- ST-1505 is consumed only as a byte-bound, disabled, non-executable,
  zero-action provider-neutral staging-admission reference. AWS remains an optional
  historical mapping only and cannot become a default, fallback, selected binding,
  eligibility shortcut, admission requirement, or evidence substitute here.

## Owned artifacts

| Path | Purpose |
| --- | --- |
| `contracts/security-verification-pack.v1.yaml` | Closed source contract, exact source hashes, safe boundary, and non-attesting state |
| `generated/security-verification-pack.reference-plan.v1.json` | Deterministic ordered projection generated from the contract and canonical catalogs |
| `manifest.yaml` | Generated source/output hashes and explicit non-attesting boundary |
| `../../scripts/build_st1603_security_verification_pack.py` | Strict validator and atomic generator; accepts only optional `--check` |
| `../../tests/st1603/*.py` | Positive, hostile, provenance, path-safety, no-write, redaction, and prohibited-surface coverage |

Generated files are never hand-edited. After the pinned Python environment is
available, regenerate and check them with:

```bash
UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv

PYTHONDONTWRITEBYTECODE=1 "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads python scripts/build_st1603_security_verification_pack.py

PYTHONDONTWRITEBYTECODE=1 "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads python scripts/build_st1603_security_verification_pack.py \
  --check
```

The isolated tests use the same prefix followed by
`pytest -p no:cacheprovider -q tests/st1603`.

## Explicitly absent and unexecuted

This slice performs no scanner, network, subprocess, Git, AWS, GitHub,
environment-variable, credential, browser, staging, release, deployment, or
Production action. It invents no ASVS, threat, verification-method, or evidence
mapping. SAST, SCA, DAST, secret scanning, manual abuse review, privacy review,
TST-026, TST-031, staging verification, Security approval, and all formal/live
work remain `NOT_EXECUTED`. Local generation and tests are implementation
evidence only and do not establish security compliance, `VALIDATED`, GATE-0,
ST-1607 eligibility, release eligibility, staging status, or Production
readiness.
