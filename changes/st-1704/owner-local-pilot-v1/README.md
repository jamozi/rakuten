# ST-1704 owner-local editorial pilot ledger

This Story-local slice records sanitized, owner-supplied observations for the
14-day, five-article self-hosted pilot. It is a local calibration ledger, not a
tracking system, provider proof, formal TST artifact, release, or Production status.

Fixed owner-private paths:

- `.secrets/st1704-owner-local-pilot/ledger.v1.json`
- `.secrets/st1704-owner-local-pilot/observation-input.v1.json`
- `.secrets/st1704-owner-local-pilot/ledger.lock`
- `.secrets/st1704-owner-local-pilot/ledger.v1.json.preparing`

The single generated `runtime-manifest.v1.json` contains the closed observation
schema, owner-local policy, and exact runtime-file hashes. Every runtime command
verifies that manifest and descriptor-stably reads the closed source inventory
before loading only those verified source bytes. Runtime domain validation is
stricter still: it binds state/value pairs, the exact 14-day window, period
metadata, article identity, human-confirmation fields, and metric-specific
source/attribution contracts.

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
mode `0600`, set the exact pilot start and human-confirmed publication timestamp,
and retain `NOT_OBSERVED` for article views, affiliate CTA clicks, Search Console
organic clicks, and all four revenue buckets until aggregate evidence actually
exists. Revenue preserves provider total, direct, estimated, and unattributed
values separately, reconciles one exact period at a time, and rejects reuse of
the same provider input/period batch across article slots. Never paste
credentials, URLs, article body, prompts, source text, personal data, IP/UA,
search queries, cookies, storage, or provider rows into it.

The report is deterministic. It can only propose `STOP_AND_REVIEW`,
`COLLECT_BASELINE`, `INSUFFICIENT_EVIDENCE`, or `REVIEW_CANDIDATES_ONLY`; it has
no WordPress, provider, browser, publication, tracking, or ranking capability.

The prior 30-day and 90-day pilot profiles remain unchanged and out of scope.
Formal `ST-1704`, `TST-018`, `TST-020`, and `TST-032` remain `NOT_STARTED` /
`NOT_EXECUTED`.
