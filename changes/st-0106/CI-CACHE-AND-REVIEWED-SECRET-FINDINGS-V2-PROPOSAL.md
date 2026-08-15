# ST-0106 CI cache and reviewed secret findings V2 proposal

This is a proposal-only handshake for the exact design handoff:

- path: `changes/st-0106/DESIGN_HANDOFF_V1_ST0106_CI_CACHE_AND_REVIEWED_SECRET_FINDINGS_V2.yaml`
- bytes: `17,952`
- SHA-256: `88a6d97cd70728c860ed7ab1b600d0c8cc69239a48a43d5c1b0c82919ff86e0c`
- base commit: `8c8b9c4567392886f086d3dd69506619e5a83344`
- base tree: `7f8a0f7c0d84282b2824c135f78a708a1cd1ed00`

The YAML is the sole approval target. This Markdown file does not grant
authority. The YAML lists this path only as proposal inventory and does not
bind this Markdown file's bytes or SHA-256, so no identity cycle exists.

## Why implementation is paused

GitHub Actions run `31821288195` proves two separate ST-0106 failures:

1. Unit reached the denied-network repository checks, then the ST-0102 cache
   probe treated an incomplete uv cache as hydrated. The terminal ST-0102
   result was 40 passed, 7 failed, and 1 skipped.
2. Secrets reported 89 sanitized locations: 31 from the worktree and 58 from
   Git history. Every finding used `GENERIC_CREDENTIAL`; the four specific
   credential rules reported zero findings.

The repository requires a new exact design approval for the strict reviewed
ledger. The gated ChatGPT Pro attempt
`20260814T173045Z-ed4b223ee1af` did not return usable design authority: the
initial result was `RESPONSE_NOT_IDENTIFIABLE`, and the bounded response-only
recovery refused with `ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID`.

Consequently, no implementation source, workflow, generated artifact, ledger,
status, commit, push, or pull request was changed in this proposal slice.

## Approved behavior if the handoff is accepted

The Unit repair uses one explicit owner-safe mode-0700 uv cache below
`RUNNER_TEMP`. Online locked hydration and the denied-network verification
receive the same canonical cache path through fixed arguments. The denied
network phase cannot hydrate or repair the cache. Incomplete or drifted cache
state fails closed; ambient home/config/index/keyring/cache inputs cannot
override the binding.

The Secrets repair adds an optional `--reviewed-findings` input. Without it,
the scanner behaves exactly as it does today. A later exact owner-approved
ledger may remove only exact `GENERIC_CREDENTIAL` findings bound to source,
line, size, source SHA-256, and line SHA-256. AWS, GitHub, OpenAI, and private
key findings are never suppressible. Wildcards, prefixes, traversal, aliases,
merge keys, duplicates, unknown fields, stale entries, unsafe files, and hash
drift all fail closed. Matched values are forbidden from the ledger and all
output.

## Deliberate two-stage authority boundary

Approval of the YAML authorizes only the handoff's direct implementation cut
to be developed and tested by the required `implementation_worker`. It does
not approve a final findings ledger, activate the workflow ledger option, or
authorize downstream provenance updates.

The implementation worker must first produce the scanner/cache code, tests,
docs, and an unapproved ledger candidate. Before activation, the owner must
approve that final ledger by exact SHA-256 after the 89 sanitized locations
have been reviewed. Any plausible real credential stops and is handled as an
incident rather than entered in the ledger.

Changing `.github/workflows/ci.yml` also changes a pinned ST-0107 input and may
propagate beyond ST-0106. That fixed-point cut cannot be frozen until the
direct bytes exist. The handoff therefore prohibits all ST-0107 and downstream
mutation until a separate closed consumer map, semantic guards, and applicable
exact owner approval exist.

## Non-claims

- The handoff is not yet approved.
- Implementation has not started.
- No reviewed-findings ledger exists or is approved.
- No provenance closure is mapped or authorized.
- Hosted CI has not run for this candidate.
- TST-001 and TST-002 remain `NOT_EXECUTED`.
- Release and Production remain `NOT_AUTHORIZED`.

## Exact approval sentence

If this boundary is acceptable, approve only the YAML with:

> SHA-256 88a6d97cd70728c860ed7ab1b600d0c8cc69239a48a43d5c1b0c82919ff86e0c の ST0106_CI_CACHE_AND_REVIEWED_SECRET_FINDINGS_V2 handoff を承認します。

Any change to the YAML requires a new SHA-256 and a new approval. The
detached approval record is created only after receiving the exact sentence.
