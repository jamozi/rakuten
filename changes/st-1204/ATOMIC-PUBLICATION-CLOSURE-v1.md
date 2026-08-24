# ST-1204 local atomic-publication closure record

- Finding: `ST1204-AUDIT-001`
- Local implementation disposition: `REMEDIATED_V3_PENDING_REAUDIT`
- V4 local implementation disposition: `REMEDIATED_V4_PENDING_REAUDIT`
- Independent read-only re-audit: `NOT_EXECUTED`
- Formal TST-030: `NOT_EXECUTED`
- Live provider validation: `NOT_EXECUTED`
- Staging / release / Production: `NOT_EXECUTED`

## V2 follow-up correction

The evidence below for commit `3a616957cac905618da3dc3e30aeddfac4b42ae6`
is retained as historical local evidence, but its implementation conclusion was
invalidated by a subsequent independent review. That review reproduced three
remaining defects: a final-entry and pre-exchange identity race, an
unrecoverable crash during destructive old-stage cleanup, and non-idempotent
legacy cleanup.

The V2 follow-up replaces the mutable three-state record with a hash-chained,
append-only journal whose state files are prepared, fsynced, and published with
`RENAME_NOREPLACE`. It binds transaction mode, old/new root identities, cleanup
tree identities and file hashes before mutation. Old-stage and complete legacy
trees are moved into transaction-specific no-replace quarantines before any
destructive cleanup; every owner checkpoint is restartable, identity mismatch
is restored when no-replace-safe or retained and refused, and completion
rechecks the authoritative bundle plus the closed cleanup inventory. Fresh
publication also uses `RENAME_NOREPLACE`, so a late destination is preserved.
Nonempty orphan stages and unbound cleanup names are not inferred owned from
matching bytes.

The local guarantee intentionally does not claim protection against an actively
malicious same-UID process that wins the final in-kernel `unlinkat` or
`rmdirat` name race after the last identity check: POSIX exposes no conditional
inode form of either syscall. All observable pre/post-rename and checkpoint
identity mismatches are covered and fail without deletion. This explicit trust
boundary is recorded in the V2 design handoff and is not a waiver of any
representable race.

## V3 terminal journal-state identity correction

An independent V2 re-audit reproduced one further observable swap. The
terminal journal directory identity was bound across its move, but its
individual state files were re-owned from valid bytes after the move. A
same-UID process could replace `state.000.json` with byte-identical bytes on a
different inode at `after-journal-cleanup-tombstone`; cleanup then deleted that
foreign inode. This invalidates the V2 claim that every terminal cleanup
checkpoint was safely restartable.

The V3 implementation captures each trusted chain entry's exact
`(dev, ino, mode, nlink, size, mtime_ns, ctime_ns)` signature while the active
journal root is still open. That immutable in-memory inventory crosses the
no-replace terminal-root move. Before any state quarantine, the source must
match its captured full signature and bytes; after quarantine, the opened
tombstone must retain the captured inode and exact bytes. Any observed mismatch
is retained and refused without deletion.

No external nonrecursive anchor persists that per-state identity inventory
after process death. A later invocation therefore never infers ownership from
journal bytes, root-name self-attestation, or a recursively trusted companion
file: any interrupted terminal journal root is preserved and refused for
manual evidence-led recovery. Bundle and legacy destructive cleanup remain
restartable. If the terminal root was already completely removed before the
crash, no recovery identity is needed and the next owner invocation proceeds.
The exact unavoidable final POSIX syscall-window limitation remains unchanged.

## V2 local evidence (superseded)

- Owner generation and the read-only owner `--check` pass at generated
  manifest SHA-256
  `22e002adcc6c043701f9e050cf3f64ffb37bccbe56ef5dad3f155fd478a201b7`.
  The three fixture payload bytes are unchanged from commit
  `3a616957cac905618da3dc3e30aeddfac4b42ae6`.
- The isolated ST-1204 suite passes `195` tests. Its `60` atomic-publication
  tests include subprocess termination at journal preparation, publication,
  quarantine, file unlink, directory removal, legacy migration and terminal
  cleanup checkpoints; concurrent owners; ancestor replacement; fresh
  no-replace collision; same-UID file, directory, bundle and legacy swaps;
  byte-identical unowned-orphan refusal; closed-inventory reappearance; and
  rejection of every tested mixed-generation state.
- Python 3.10 and 3.14 direct compilation, Ruff lint/format, strict mypy over
  the generator and all ST-1204 tests, configured repository Pyright,
  canonical import verification, workspace no-write verification, focused
  capability/static checks, focused maintained-file secret scanning, and
  `git diff --check` pass. The repository Pyright configuration excludes this
  generator and its tests; a forced direct invocation still reports the
  pre-existing untyped YAML/JSON and private-test-helper diagnostics and is
  not represented as green.
- The linked-worktree-wide secret scanner remains an inherited operational
  limitation with sanitized result
  `ERROR code=unsafe-git-metadata source="."`; the exact maintained-file scan
  is the applicable local result for this isolated worktree.
- The ST-1205 owner check continues to fail closed with
  `SOURCE_HASH_DRIFT field=predecessor.st1204`. Its direct drift is limited to
  the already changed ST-1204 runtime slice, application test and recorded
  adapter test; no downstream owner or generated output is changed here.
- This record is local implementation evidence only. Independent re-audit,
  formal TST-030, live provider/account/credential evidence, persistence,
  hosted CI, staging, release and Production remain `NOT_EXECUTED`; no
  `VALIDATED` or audit-`PASS` state is claimed.

## V3 local evidence

- Owner generation and read-only `--check` pass at manifest SHA-256
  `b0adffaa89c5ffdd931a46b319e19ace04246d19820e394c29795fbd9b3c47ce`;
  the three recorded fixture payloads remain byte-identical.
- The isolated ST-1204 suite passes `202` tests, including `67`
  atomic-publication tests. New hostile cases cover the exact byte-identical
  `state.000.json` swap after the terminal root move, a byte-identical
  post-quarantine tombstone swap, mode/mtime signature drift, a final remaining
  state swapped after prefix deletion, a preparing-state reappearance, every
  retained terminal-cleanup crash boundary, and the already-removed-root
  success boundary. A separate-process restart test replaces a crashed
  journal state with byte-identical bytes on a new inode and proves that
  recovery retains it without inferring ownership. The common
  success assertion now invokes the complete read-only managed-pending-state
  check instead of testing one literal cleanup name.
- Python 3.10/3.14 compilation, Ruff lint/format, strict mypy, configured
  Pyright, canonical import, workspace no-write, focused capability/static,
  focused maintained-file secret scanning, and `git diff --check` pass. The
  inherited linked-worktree-wide secret-scan limitation and out-of-config
  direct Pyright diagnostics remain reported rather than promoted to green.
- Independent V3 re-audit, formal TST-030, hosted CI, live provider,
  persistence, staging, release and Production remain `NOT_EXECUTED`. This is
  local implementation evidence only and does not claim `VALIDATED` or audit
  `PASS`.

## V4 invocation-identity and read-boundary correction

A subsequent independent review identified four remaining overclaims or
identity gaps. First, the terminal cleanup path captured active journal state
inodes only immediately before the root move, so a byte-identical state or
whole-root replacement earlier in the same invocation could be re-owned.
Second, pre-journal partial-stage cleanup inferred ownership again from the
expected bytes and current inode. Third, bundle acceptance revalidated only the
outer generated directory name, not the nested `fixtures` and `recorded` names
against their open descriptors. Fourth, the check-mode evidence omitted access
time while the design claimed that no metadata changed.

V4 keeps an invocation-scoped full signature for the active journal root and
every committed state. Each state signature is captured before its prepare and
commit checkpoints; the complete inventory is revalidated before every append
and immediately before the terminal root move. Same-invocation automatic
recovery receives the existing inventory rather than recapturing the active
journal, including when a checkpoint raises after a replacement. An observed
state or root swap raises a non-recapturable identity-drift refusal and
preserves the replacement.

Partial-stage cleanup now requires the same invocation's pre-checkpoint
directory identity and file-signature inventory. This preserves automatic
cleanup for ordinary pre-journal faults in the creating invocation. A detected
replacement is preserved and refused, and a nonempty stage that survives a
process boundary is no longer inferred owned from matching bytes. Nested
bundle reads revalidate both directory names against their already-open
descriptors before acceptance.

The exact check guarantee is narrowed to bytes, namespace, device/inode, size,
mode, mtime and ctime. Access time is explicitly excluded because portable
read-only opens may update it; V4 does not claim or conditionally fall back from
`O_NOATIME`.

## V4 local evidence

- Owner generation and the immediately following owner `--check` pass at
  generated manifest SHA-256
  `80ee0253d5a7d0a051932bee8a8916fddf16c7ace8580081a1331ffa56d65924`.
  All three recorded fixture payloads remain byte-identical.
- The isolated ST-1204 suite passes `210` tests, including `75`
  atomic-publication tests. New exact hostile regressions cover an active state
  replaced by byte-identical bytes at its commit checkpoint, a whole active
  journal root clone/swap before terminal movement, state and root replacement
  combined with a raising checkpoint, partial-stage root and byte-identical
  file replacements, and nested `fixtures` and `recorded` directory swaps
  before bundle acceptance. Existing same-invocation
  pre-journal fault recovery remains green; separate-process unbound nonempty
  stage recovery now proves preservation and refusal.
- Python compilation, Ruff lint/format, strict mypy, owner no-write checking,
  focused capability/static checking, and `git diff --check` are required by
  this V4 checkpoint. The exact final command results accompany the Story
  commit rather than being promoted to formal TST-030 evidence.
- Independent V4 re-audit, formal TST-030, hosted CI, live provider,
  persistence, staging, release and Production remain `NOT_EXECUTED`. This is
  local implementation evidence only and does not claim `VALIDATED` or audit
  `PASS`.

## Closed implementation boundary

The owner generator now publishes the manifest and all three recorded fixtures
as one exact `changes/st-1204/generated` directory generation. The four former
full-path, sequential replacements are no longer authoritative and are removed
only after the exact new generated tree has a durable committed journal state.

All mutation after repository-root identity capture is relative to a single
descriptor-opened physical `changes/st-1204` directory. A nonblocking flock on
that captured directory inode serializes generation and recovery and excludes a
concurrent shared-lock check. The publisher creates and fsyncs a closed hidden
stage, byte-verifies it, publishes a durable `PREPARED` journal, and uses one
same-parent namespace operation: rename for a fresh install or Linux
`renameat2(RENAME_EXCHANGE)` for replacement. A platform without the exact
exchange operation fails closed before changing an installed generation.

A failure before durable `COMMITTED` reverses the namespace operation and
verifies the exact old generation or exact absence. A failure after durable
`COMMITTED` retains the exact new generation. Bundle and legacy cleanup resume
deterministically on the next run; a process loss after the terminal journal
root is quarantined instead preserves that root and returns explicit recovery
required because no durable, nonrecursive per-file identity anchor survives.
`PREPARED`, `COMMITTED`, and `ROLLED_BACK` recovery, stale
stage/preparing/cleanup entries, lock contention, malformed journals, symlink,
special-file, and multiply-linked entries all have explicit recovery or
fail-closed behavior. Read-only check mode accepts only one exact complete
generation and refuses every pending recovery state.

The generated fixture payloads retain their prior semantic bytes. This change
does not add network, credential, environment-secret, Google SDK/API, database,
queue, job/event, analytics persistence, or runtime publication capability.
OD-012 therefore remains optional-tracking-disabled and OD-015 remains
recorded-fixture-only.

## Local evidence

- Owner generation and the immediately following no-write `--check` passed.
  The generated manifest SHA-256 is
  `76a2d81d36b43333d4bed1ae82fe017f6d2c186b2737aca5180261154eaf4328`.
- `tests/st1204` passed `159` tests. Its dedicated publication file passed `24`
  tests covering fresh and replacement publication, injected faults, real
  subprocess crashes, forward and reverse recovery, ancestor and final-entry
  swaps, shared/exclusive lock contention, mixed-generation exclusion, and
  hostile filesystem material.
- Python 3.14.6 direct compile/import, Ruff 0.16.1 lint and format, and strict
  mypy 2.3.0 with explicit package bases passed over the generator and all
  ST-1204 tests.
- Repository-configured Pyright 1.1.411 passed with `0 errors, 0 warnings, 0
  informations`. That maintained configuration excludes scripts and tests. A
  forced strict out-of-configuration analysis of the generator and ST-1204
  tests reports the existing untyped-YAML/JSON graph and private test-helper
  diagnostics and is not represented as positive direct-file Pyright evidence.
- Canonical import verification and the workspace drift check passed. The
  generator's closed AST/capability test passed as part of the isolated suite.
- The maintained-file scanner was applied descriptor-relatively to the exact
  current ST-1204 patch and reported zero focused findings. The broader
  linked-worktree command remains unavailable with the sanitized inherited
  result `ERROR code=unsafe-git-metadata source="."`; it is not represented as
  a green full-worktree scan.

Exact source hashes at the checkpoint are:

- publication decision:
  `4ce2bd89583b6d6887790f9b4279cd08a482408061ae8a440c6e9f828abc050e`
- source contract:
  `68234b1e7920ddbfa7202f3b14690a985022160cc655611fddb4639eeea4926d`
- generator:
  `4f2c73371275497cc67d964ac420d4702de225deed373518a48956bec8220faa`
- runtime slice:
  `ac85f07ee2325aa5e1f63ffd0323cc499417b2c85d4ac36b31d07fcbe58e0d0e`

## Direct downstream provenance drift

The ST-1205 owner intentionally remains outside this Story. Its current
ST-1204 predecessor inventory pins three bytes changed by this closure:

| Artifact | ST-1205 current pin | ST-1204 checkpoint SHA-256 |
|---|---|---|
| `changes/st-1204/RUNTIME-SLICE-v1.md` | `e5ca8b2e38e0b46c9a40232af26bd5b4ebbbf20099c6a7856a7ab007443ca17e` | `ac85f07ee2325aa5e1f63ffd0323cc499417b2c85d4ac36b31d07fcbe58e0d0e` |
| `tests/st1204/test_ga4_application.py` | `8e8aae09e0749a31957c91a1de8f76abbc61f2e57a3bfecb7382f137196caf52` | `6631568a32d3a510a1b35f349f4cddc365af1105af978fa5048b9079a5a1e7ff` |
| `tests/st1204/test_recorded_ga4.py` | `e8c427264d11fd9e88bfa92a663a8704fbccd70c443bd055e658062c48a95677` | `723d4a85d0e84784a207fcf61b23a59d9a944acb42c2f2c9f2d2f6f66fc90355` |

The exact read-only command
`/home/minami/rakuten/.venv/bin/python scripts/build_st1205_kpi_read_model_reference_plan.py --check`
exits one with
`ST-1205 build failed: SOURCE_HASH_DRIFT field=predecessor.st1204`.
The affected owner artifacts are the ST-1205 source contract, generated
reference plan, and manifest. No ST-1205 file was edited or regenerated here.

## Remaining boundary

This record closes the local publisher implementation deficiency; it does not
change the historical audit artifact or self-approve its required independent
read-only re-audit. A fresh independent audit must review these exact bytes
before the finding receives an audit `PASS`. Formal TST-030, OD-012/OD-015
external evidence, live property/account/credential work, persistence, hosted
CI, staging, release, and Production remain separate and unexecuted.
