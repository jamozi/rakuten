# ST-0709 completion evidence

Status: `LOCAL_IMPLEMENTATION_COMPLETE`

Base commit: `e3c3e561b3fde74c7236cb15daf16c2f848264b0`

This record covers repository-local implementation only. Canonical Status
Registry state is unchanged. Formal browser `TST-022`, rendered accessibility,
hosted CI, live provider execution, credentials, staging, release, and
Production remain `NOT_EXECUTED`. OD-009, OD-010, and OD-015 retain their
Canonical safe boundaries.

The installed V2 workspace is recorded/headless and route-unregistered. It
projects 12 Task, 12 Prompt, 5 Route, 1 synthetic Evaluation, 1 refusal-only
Release, and 12 candidate cost-limit rows. The exact ST-0707 and ST-0708
reports both remain `REFUSED_INCOMPLETE_EVIDENCE`. All operational authority is
false, action arrays are empty, actual cost is unavailable rather than zero,
and release approval remains human-only.

Introduced debt: `[]`.

## Installed local identities

- V2 contract artifact SHA-256:
  `3113b5aa3e192a3aa8b56556760ce43015a01a01f06c25927ce1fec87f40cdc9`
- V2 fixture artifact SHA-256:
  `d6875fb0848fcb32f04ab187de88fe66aaeb84bbae0f78d485d0dd9fdac0608f`
- V2 canonical fixture identity:
  `ec371b60a3c01e54043fa9b1ee904d69f5ffd9fe811e76216849a9ef32b0ce7d`
- V2 TypeScript binding artifact SHA-256:
  `9d05208310806ab432074da8dc9ae4783d5d3fc1cbb94381201d4b9bde5f52d9`
- V2 runtime-manifest artifact SHA-256:
  `9509ea3c75ac8f138770f607e1ed5d8f6fbffeecb63b7842cc596fafbdf08f99`
- V2 runtime-manifest identity:
  `7704195616879ee726c89faabed2eb054804bcdac0585aa14fc7d8bdbc3911ab`
- Recorded ST-0707 evaluation identity:
  `34f4fd238d209b11173afe8df8031a8931a63c6cbe143c19029e8f938331db86`
- Recorded ST-0708 release-proposal identity:
  `83da5c0e7d0b9fa71c0495d528e90957af471092f69e946ca8d22321708a1920`
- Preserved ST-0709 V1 source SHA-256:
  `07b240c8f127ec3676b7d111778f27a9eca0e288ed866e177be077e733b84875`

## Local check ledger

- ST-0709 owner generation and no-write `--check`: PASS.
- Historical V1 plus V2 focused Node suites: PASS, 31 tests.
- V2 generator/security Python suite: PASS, 6 tests.
- ST-0701 owner check and affected suite: PASS, 117 tests.
- ST-0706 affected suite: PASS, 29 tests.
- ST-0707 owner check and affected suites: PASS, 62 tests.
- ST-0708 owner check and affected suites: PASS, 158 tests.
- ST-1101 affected Node suite: PASS, 31 tests.
- Repository Node-native regression set: PASS, 317 tests; the separate Vitest
  toolchain suite also passed 4 tests with its declared runner.
- Package and standalone strict TypeScript compile: PASS.
- ESLint and Prettier on owned TypeScript/test files: PASS.
- Ruff format/lint and mypy strict on owned Python/test files: PASS.
- Workspace bootstrap no-write check: PASS.
- Canonical design import suite: PASS, 18 tests.
- `git diff --check`: PASS.
- Secret scan: the unchanged scanner correctly refused linked-worktree `.git`
  metadata with `unsafe-git-metadata`. A complete non-Git `git archive` snapshot
  was overlaid byte-for-byte with all owned changes and scanned using the exact
  repository V2 reviewed-findings ledger; exit 0, no unreviewed finding.

The first parallel ST-0701 affected-suite run observed one secure-root identity
refusal while other pytest processes changed the worktree root metadata. The
same owner check and all 117 tests passed sequentially with the pytest cache
disabled. This was test-runner interference, not an introduced product failure.

The final Story commit is the Git commit containing this record; embedding its
SHA here would create a self-referential content cycle. No push or merge was
performed.
