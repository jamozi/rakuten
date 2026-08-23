# ST-1704 owner-local editorial pilot ledger

This Story-local slice records sanitized, owner-supplied observations for the
14-day, five-article self-hosted pilot. It is a local calibration ledger, not a
tracking system, provider proof, formal TST artifact, release, or Production status.

Fixed owner-private paths:

- `.secrets/st1704-owner-local-pilot/ledger.v1.json`
- `.secrets/st1704-owner-local-pilot/observation-input.v1.json`
- `.secrets/st1704-owner-local-pilot/ledger.lock`
- `.secrets/st1704-owner-local-pilot/ledger.v1.json.preparing`

From the exact physical repository root:

```bash
make -f changes/st-1704/owner-local-pilot-v1/Makefile doctor
make -f changes/st-1704/owner-local-pilot-v1/Makefile init
make -f changes/st-1704/owner-local-pilot-v1/Makefile record
make -f changes/st-1704/owner-local-pilot-v1/Makefile report
```

`doctor` and `report` are read-only. `init` and `record` write only inside the
fixed pilot directory. `record` reads the fixed owner-private observation input;
there is no caller-selected path. Copy the tracked example to that path with
mode `0600`, replace its observation timestamp with the human-confirmed value,
and retain `NOT_OBSERVED` for access, clicks, and revenue until aggregate evidence
actually exists. Never paste credentials, URLs, article body, prompts, source text,
personal data, IP/UA, search queries, cookies, storage, or provider rows into it.

The report is deterministic. It can only propose `STOP_AND_REVIEW`,
`COLLECT_BASELINE`, `INSUFFICIENT_EVIDENCE`, or `REVIEW_CANDIDATES_ONLY`; it has
no WordPress, provider, browser, publication, tracking, or ranking capability.

The prior 30-day and 90-day pilot profiles remain unchanged and out of scope.
Formal `ST-1704`, `TST-018`, `TST-020`, and `TST-032` remain `NOT_STARTED` /
`NOT_EXECUTED`.
