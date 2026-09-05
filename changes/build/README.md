# Build manifest v2

`manifest.v2.json` is the active generator registry and integrity manifest. Every
generated output has exactly one owner. Canonical packages, dependency locks, and
container images may be checksum-bound; ordinary tracked inputs use a repository URI,
semantic ID, and owner version without a digest.

Story-local v1 manifests remain historical compatibility snapshots. They are not active
build authority, are not consulted by `make generate` or `make check`, and their source,
approval, handoff, command, or commit bindings do not stop current development.

The source-packet and reader-claim checks have `validation_only` output scope:
they validate reviewed inputs and intentionally generate no files. This is an
explicit two-owner allowlist, not an automatic exemption for empty output lists.
Every ordinary `tracked` generator must still own at least one output, and a
validation-only owner cannot declare generated outputs.

## Historical editorial evidence versus publication

The ST-1704 reader-ledger and editorial-manifest owners use `--development` in
repository generation/checks. This validates the full source/claim/reader-unit
mapping and historical snapshot integrity without changing observation dates.
Private safety captures are not inputs to reproducible repository artifacts;
missing verified evidence remains blocked. The development ledger anchor is
separate from the unchanged independent-review anchor and grants no authority.

Direct validator calls remain strict by default. Publication still requires
fresh official/product evidence, current activation materialization, independent
review/signature and separate wp-admin approval. Neither a successful build nor
a GitHub merge satisfies those requirements. The acquisition-only
`--for-source-refresh` path is not used by CI or normal repository generation.

## Shared verification plan

`raos_build.py plan --json` is read-only and does not run generators. The plan
combines generator consumers, imports and explicit component routes from
`scripts/raos_test_plan.py`. `--critical` adds the bounded PR regressions;
`--all` selects the complete local suite. Unknown executable/configuration
inputs and shared infrastructure changes fall back to full verification.

`make fast` and CI execute the same plan. CI selects jobs before running them;
`Final Integration` accepts success only for required jobs and skipped only
for jobs explicitly omitted from that plan. Draft checks wait until ready.
Daily full CI runs at 03:00 JST. Results and timings stay in Actions rather
than becoming additional tracked evidence or approval artifacts.

The blocked WordPress quality template also has a generator owner. Its existing
contract supplies fingerprint inputs and predecessor ordering, including Make
and test edits. Regeneration retains a fixed NOT_EXECUTED timestamp and BLOCKED
status; it creates no review, freshness, signature or publication authority.
