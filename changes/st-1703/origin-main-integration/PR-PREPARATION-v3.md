# ST-1703 origin/main integration — PR preparation v3

This document is a non-authoritative, one-way PR-preparation aid. It explains
the proposal in
`DESIGN_HANDOFF_V1_ST1703_ORIGIN_MAIN_INTEGRATION_V3.yaml`, whose frozen
identity is **46,856 UTF-8 bytes** and **SHA-256
`94e21a08ca051cf66c4c635c9e018b9db313ac649fd2b0c2461d16712a80daba`**.
Only that exact handoff is an owner-approval target. This Markdown, a branch,
a commit, a diff, and any future PR title or body grant no authority.

No import, rebind, generation, test mutation, detached approval, commit, push,
or pull request has been performed by this pre-approval slice. If
`refs/remotes/origin/main` no longer equals
`acd79848a1b5bc33974bbcdbf5e2bd1d8e2ca60d` with tree
`85620e53419b65e3053e4454c6c1cb522de4459b`, stop. A moved target requires a
new exact handoff and owner approval.

## Proposed PR coordinates

- Title: `feat(st-1703): integrate first-article slice onto current main`
- Base branch: `main`
- Head branch: `codex/st-1703-origin-main-integration`
- Exact proposed base: `acd79848a1b5bc33974bbcdbf5e2bd1d8e2ca60d`
- Exact source tip: `ca5ff2e419ffc07239b4c551146dd66b01489cc3`
- Source range: `290cb2e71b9b310e59500c5643fef4296c877f3f..ca5ff2e419ffc07239b4c551146dd66b01489cc3`
- Merge base: `317561ba2f56e9e9c55d65f24df13db3dc3fa77d`

Push and PR creation remain separately owner-gated external writes even after
an exact V3 implementation approval.

## Proposed scope

- Import the exact nine ST-1703 commits as the exact final 73-path range
  inventory: 25 `changes`, 22 tests, 20 Python, four scripts, one Makefile,
  and one worklog.
- Keep the three preceding source-only ST-0101 commits excluded.
- Preserve the absence of any ST-1703 runtime dependency on
  `chatgpt_pro_orchestrator`; handoff-only PRO record provenance remains data.
- Mechanically replace the one active Wave 3 approved-base literal with the
  exact target parent and regenerate the Wave 3 runtime manifest through its
  owner generator.
- Extend the low-cost generator for exact V3 handoff, detached approval,
  target, and current-runtime bindings; regenerate only its manifest.
- Preserve the low-cost projection at 9,380 bytes and SHA-256
  `34194a4dd874c0b2194733514aa6421131a51a0e2c843e517e207b9d46f96317`.
- Preserve the exact 8,116-byte source packet, including its known blank EOF.

The imported mutable set is closed to eight paths named in the handoff. The
other 65 imported paths remain byte-identical to the source tip. The only
additional post-approval path is the future exact-hash-bound detached V3
approval. Every other repository path is protected.

## Explicit exclusions

- No canonical, imported-design, status/evidence registry, shared Main,
  `.codex/config.toml`, `tmp`, ST-1903, or other-worktree mutation.
- No historical handoff, approval, source contract, generated projection,
  source packet, Wave 3 content, or ST-1703 worklog rewrite.
- No repair or authority substitution for the two nonexistent commit IDs in
  the immutable Wave 3A handoff.
- No retroactive exact approval for the OBJECT_DRIFT slice.
- No dependency promotion or claim that ST-1703 is implemented, accepted,
  validated, staged, released, published, or production-ready.
- No browser, provider, credential, Secret, journal, draft, external write,
  purchase, publication, staging, release, production, or kill-switch action.

## Proposed PR body

### Summary

Integrates the exact ST-1703 first-article implementation range onto the exact
current `origin/main` without importing unrelated ST-0101 history. Rebinds only
target ancestry metadata, regenerates its two owner manifests, and preserves
all publication and external-action gates.

### Exact input evidence

- Nine linear commits; zero merge commits.
- 73 paths: 72 additions and one Makefile modification.
- Full-index binary no-renames range patch: 1,153,555 bytes, SHA-256
  `46b5235bd50ec0db8d37ddadbc9924c22db55d7c1c5db2f4293f38b3579cd68e`.
- Canonical 73-record inventory with one final LF: 16,790 bytes, SHA-256
  `e3e642125a01e964f1849b181a727a184ae164196e7a96e8bc4247b527ebed3f`.
- Only target overlap: Makefile. Target and source-range parent share blob
  `1f07602c8aa2f93de36af3d380d883f92295e3fe`.
- `git apply --check --whitespace=nowarn`: PASS. `error-all` reports only the
  exact immutable source-packet blank-at-EOF warning; no other exception is
  allowed.

### Compatibility and security

No schema migration, provider integration, public API expansion, finance
input, or production runtime dependency is added. Existing publication
authority remains `NONE`. The target rebind changes only the ancestry anchor
needed by the existing fail-closed runtime identity verifier.

### Known retained gaps

- Wave 3A contains two immutable nonexistent embedded commit references.
- OBJECT_DRIFT lacks a separate exact hash-bound approval artifact.
- Source Packet remains `REVIEW_REQUIRED_NOT_APPROVED`.
- ST-1703 dependencies remain absent, disabled, or non-executable.

### Evidence boundary

Local generator, unit, static, and integration checks are repository-local
evidence only. Formal TST-021, TST-022, TST-032, live browser/provider,
credential, draft, staging, publication, release, and production evidence all
remain `NOT_EXECUTED`.

## Check matrix for an approved implementation

| Check | Required result | Boundary |
| --- | --- | --- |
| Exact target/source/range/inventory recheck | PASS before mutation | Stop if any identity moves |
| Range patch apply-check with `--whitespace=nowarn` | PASS | Source packet is exact-hash exception |
| Exact 73-path import and 65/8 final cut | PASS | No unlisted path mutation |
| Wave 3 runtime-manifest build and `--check` | PASS | Metadata only, not formal TST |
| Low-cost build and `--check` | PASS | Projection remains byte-identical |
| `tests/st1703_low_cost` isolated process | PASS | Local focused evidence |
| `tests/st1703` isolated process | PASS at valid boundary | See physical-root limitation |
| Ruff format/check, strict mypy, parse/import | PASS | Changed Python only plus affected scope |
| Workspace and canonical-import no-write checks | PASS | No generated canonical mutation |
| Exact-path sensitive-data scan and diff checks | PASS | Never traverse `.secrets` |
| Independent read-only exact-diff review | CLEAN or fixed/re-reviewed | Before any commit authority request |
| Formal TST-021/022/032 | NOT_EXECUTED | Separate CI/staging/product-owner evidence |
| Live/external/publication/release/production | NOT_EXECUTED | Separately authorized only |

## Physical-root limitation

The Wave 3 launcher intentionally requires the physical repository root
`/home/minami/rakuten`, the exact pinned Python runtime, committed HEAD bytes,
and runtime-manifest equality. A linked integration worktree cannot establish
that complete runtime-identity evidence and may correctly fail closed with a
root or source-binding refusal. The integration owner must run the affected
physical-root suite only after an authorized commit in an exact,
owner-controlled physical-root checkout. Until then, that evidence remains
unexecuted; it must not be relabeled PASS from worktree-only tests.

## Approval and PR stop conditions

Before implementation, request owner approval of exactly:

`SHA-256 94e21a08ca051cf66c4c635c9e018b9db313ac649fd2b0c2461d16712a80daba の ST1703_ORIGIN_MAIN_INTEGRATION_V3 handoff を承認します。`

After implementation, local commit, push, and PR creation retain their exact
separate gates as stated by the handoff. Stop rather than update this Markdown
if the target moves, any inventory byte differs, the source-packet exception
expands, an authority gap is silently repaired, or an external/publication
boundary would be weakened.
