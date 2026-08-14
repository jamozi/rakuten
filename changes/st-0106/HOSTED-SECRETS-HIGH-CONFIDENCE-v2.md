# ST-0106 hosted Secrets high-confidence classifier V2 — approval handoff

This document explains the inert V2 proposal in
`DESIGN_HANDOFF_V1_ST0106_HOSTED_SECRETS_HIGH_CONFIDENCE_V2.yaml`. It is not
an approval record, implementation artifact, CI waiver, status transition,
release decision, or Production authority.

## Sole approval target

- Path: `changes/st-0106/DESIGN_HANDOFF_V1_ST0106_HOSTED_SECRETS_HIGH_CONFIDENCE_V2.yaml`
- Bytes: `18951`
- SHA-256: `019d8b1394b70a98aa2b7c7d0493eb55a20e043b7ea4cce758655229b058ae9a`
- Base commit: `6f8dafb511ed9492a51d7c831a3c212f8f52deae`
- Base tree: `9f263246f5aca387d30f6050b508c209eb148f1c`

The Markdown bytes are deliberately not referenced by the YAML. Any YAML byte
change creates a new approval target and requires this document to be updated.

## Why V2 is required

V1 was approved exactly and remains immutable. Implementation then proved that
two V1 requirements cannot both hold:

1. the safe negative-fixture declaration must be declaration-first; and
2. every current false-positive source and historical object must remain
   unchanged while the complete scan reaches zero findings.

Three protected observations in one maintained test source are complete
kind-first negative fixtures. They use only two credential kinds, hyphen
separators, a decimal fixture identifier, and lower-case x padding. Under exact
V1 they must be reported by the digit-bearing high-confidence family. No raw
candidate, assignment, or source line was exposed, and no protected source was
edited.

V1 produced no implementation commit. Its handoff, companion, and detached
approval remain byte-identical audit history. Exact V2 approval replaces V1's
implementation authority rather than modifying it retroactively.

## V2 correction

V2 retains every V1 classifier stage and adds only these complete kind-first
families:

```text
client-secret-not-real-<decimal>-x{4,}
access-token-not-real-<decimal>-x{4,}
```

The actual fixture values are not the strings shown above; this is the closed
grammar. Matching is case-sensitive and full-value only. Hyphens, a nonempty
decimal identifier, and at least four lower-case x characters are mandatory.

No other kind, underscore or mixed separator, ST ID, missing ID/padding,
upper-case padding, extra component, concatenation, interpolation, or residual
material is safe. A complete ASCII/Python str or bytes literal may be decoded
only to test this exact fixture grammar. It creates no other placeholder,
source-expression, reference, or credential exemption.

The V1 declaration-first grammar remains unchanged. `access-token` is admitted
only in the new complete kind-first family; it is not added to unrelated
vocabularies. Provider-specific detection, generic evidence thresholds,
redaction, CLI/exits, worktree/archive/Git-history traversal, network boundary,
workflow, and ST-0101 Unit selection remain unchanged.

No path, filename, line, key name, archive member, commit, blob, source, or
exact-value allowlist is permitted. Existing false-positive sources and Git
history remain protected.

## Pro advisory boundary

The new gated question was submitted once. Automated parsing and response-only
recovery failed closed, after which the owner copied the already-displayed
answer into the same run. Manual import used no browser call and no resubmission.
It was classified `PRO_REVIEW_TEXT_V1 / UNAPPROVED_REVIEW`, so no raw text is
copied and no design authority is derived from it. V2 is based on canonical
requirements and the sanitized local evidence above. No further Pro follow-up
is required.

## Closed implementation and evidence boundary

After exact V2 approval, one detached record may be created at
`changes/st-0106/DESIGN-HANDOFF-APPROVAL-HOSTED-SECRETS-HIGH-CONFIDENCE-v2.yaml`.
The V1 and V2 proposal/companion bytes then remain immutable.

Implementation may modify only the existing scanner, its ST-0106 tests, the
ST-0106 README/ExecPlan/worklog, and the root README. The worklog remains
append-only. The final local commit contains exactly the three V1 records,
three V2 records, and those six modified paths.

Required evidence includes hostile exact/near-miss tables, full isolated
ST-0106 tests, pinned Ruff/compile checks, unchanged hosted-like ST-0101
selection, workspace/canonical/protected/sensitive checks, an exact denied-
network Secrets equivalent where supported, and a clean non-shallow clone full
worktree-and-history scan with zero findings. An independent frozen review must
pass before the one local commit is final.

Local PASS is not hosted GitHub evidence, formal TST-001/TST-002, a status
transition, release, publication, or Production authority. Push, PR, merge, and
ST-0005 evidence remain outside this handoff.

## Exact approval statement

To authorize implementation of these exact V2 YAML bytes, reply with:

> SHA-256 019d8b1394b70a98aa2b7c7d0493eb55a20e043b7ea4cce758655229b058ae9a の ST0106_HOSTED_SECRETS_HIGH_CONFIDENCE_V2 handoff を承認します。
