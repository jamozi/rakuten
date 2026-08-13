# ST-1703 low-cost publication pilot V2 reconciliation handshake

Status: `PROPOSAL_ONLY_PENDING_REPOSITORY_OWNER_EXACT_SHA256_APPROVAL`

This document is a non-authoritative, one-way handshake explanation. It does
not approve, amend, or add to the V2 handoff, and its own bytes or SHA-256 are
not an approval target.

The sole approval target is:

- Handoff: `changes/st-1703/low-cost-publication-pilot/DESIGN_HANDOFF_V1_ST1703_LOW_COST_PUBLICATION_PILOT_RECONCILIATION_V2.yaml`
- Bytes: `28,414`
- SHA-256: `ff75d76479a6ebf85061e54529c0896cd1a203d8f1ab0d01655ecc18dc91a6db`

The V2 handoff preserves the approved V1 pilot semantics with delta `NONE`.
It does not silently replace the historical Wave 3 runtime-manifest binding
`ac5f80152c846df3be09b90a28a0bd5ca93f2e165807b9fcb50ca7eb569c908c`.
It separately binds the current committed manifest metadata at
`8cf00ace6e2988c3bfb7969f13cfec0786137077c1319be4b043c4b762b5fba9`
and forbids using a historical Git object as a substitute for required current
filesystem bytes.

The handoff also retains, without repairing or approving, two nonexistent
commit references embedded in the immutable Wave 3A handoff and the absence of
a separate exact hash-bound approval artifact for the final `OBJECT_DRIFT`
runtime slice. These gaps grant no Wave 3 or external authority.

Before exact handoff approval, implementation authority is `NONE`: no V1 file
import, cherry-pick, reconciliation implementation, integration, commit,
external action, live provider call, draft mutation, publication, staging,
release, or production action is authorized.

After exact approval, only the closed post-approval file cut inside the handoff
may be implemented. It requires a new detached V2 approval; exact import of the
eleven V1 source paths; byte preservation of the six protected V1 paths; changes
only to the five named V1 generator, generated-manifest, README, and test paths;
and no modification of Wave 3, canonical, status, evidence, worklog, or shared
Main files. Formal TST-021, TST-022, and TST-032 remain `NOT_EXECUTED`.

The exact owner approval statement is:

> SHA-256 ff75d76479a6ebf85061e54529c0896cd1a203d8f1ab0d01655ecc18dc91a6db の ST1703_LOW_COST_PUBLICATION_PILOT_RECONCILIATION_V2 handoff を承認します。

Approval of this explanatory Markdown, a summary, branch, commit, tree, V1
artifact, or any different SHA-256 is insufficient.
