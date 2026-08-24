# ST-0708 completion evidence

Status: `LOCAL_IMPLEMENTATION_COMPLETE`

Base commit: `71c709844d625ee26026b2ba8555a16fa351b982`

This record covers repository-local implementation only. Formal TST-018, live
provider execution, credentials, staging, release, and Production remain
`NOT_EXECUTED`. OD-015 remains `EXTERNAL_EVIDENCE_REQUIRED` and blocking.

The installed deterministic release-decision candidate is a proposal-only
`REFUSED_INCOMPLETE_EVIDENCE`. No model, prompt, route, dataset label, approval,
publication, release, or Production state was selected or changed.

Introduced debt: `[]`.

## Installed local evidence

- V2 runtime contract SHA-256:
  `e8b2607955b3e5de9dad1b50bb028710e49e71af8bd40805ee2ef46fa50946af`
- Historical V1 compatibility artifact SHA-256:
  `6310dd1107e8685feb8b86f9babbb0d889ffe611e3e2d92f4e0b83154e65d805`
- V2 request artifact SHA-256:
  `d089a3da197112f62b4338d4915e67ccc3ae132fabb6aab824f6d6d420989788`
- V2 request identity:
  `51bd6efc5a5efbbc492c4a034f228cc0d2e3da089ecf160d05feb70bab7b8fc2`
- V2 report artifact SHA-256:
  `b2697d5e73766cd1c67ac1ba2ea29f1bf07709a1ea319a81aee72ca7d537b652`
- V2 report identity:
  `83da5c0e7d0b9fa71c0495d528e90957af471092f69e946ca8d22321708a1920`
- V2 runtime-manifest artifact SHA-256:
  `d7b77b420ada0244710f62e02104e3e3a4c8dec4f852115a846526fce33ecfae`
- V2 runtime-manifest identity:
  `75f26f08d01cc053e6354511208590cd40f18b34944338c328340a347a2d255d`
- Owner manifest SHA-256:
  `5b560dab40071f0200171638cc700be541e6eb60e04909782b1fe0ec4690abc4`
- Hardened publication helper SHA-256:
  `38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e`

The installed report binds ST-0703 candidate identity
`78b441e412807279824dc2487ed7aa1d668a7c0e68d49220aa065f61dcb03fda`,
ST-0707 bundle
`95279655c5e1dec9ab5c63333bb08fad3da82637a8ab5087f83d19f3d30f42fb`,
and ST-0707 report
`34f4fd238d209b11173afe8df8031a8931a63c6cbe143c19029e8f938331db86`.
All nine AIT-004 CRITICAL metrics and all eight zero-tolerance classes remain
`UNAVAILABLE`, so the result is not a pass.

## Local check ledger

- Owner generation followed by `--check`: PASS.
- Historical plus V2 focused suites: PASS, 158 tests.
- ST-0703/ST-0707 affected suites: PASS, 425 tests.
- Hardened multi-output publication foreign-preservation, rollback,
  existing-target exchange race, missing-target hardlink no-clobber race, and
  parent-swap cases: PASS within the focused suite.
- Ruff 0.16.1 format check and lint: PASS on all 15 changed Python files.
- Mypy 2.3.0 `--strict --explicit-package-bases`: PASS, 14 source files.
- Python 3.14.6 compile/import and two-run deterministic evaluation: PASS.
- `git diff --check`: PASS.
- Secret scan: the unchanged repository scanner correctly refused linked
  worktree metadata with `unsafe-git-metadata`. A complete non-Git `git archive`
  snapshot was overlaid byte-for-byte with the 25 owned changed files and
  scanned with the exact V2 reviewed-findings ledger; exit 0, zero findings.

The final Story commit is the Git commit containing this record; embedding its
SHA here would create a self-referential content cycle. No push or merge was
performed.
