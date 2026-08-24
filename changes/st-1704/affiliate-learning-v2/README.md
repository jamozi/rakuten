# ST-1704 affiliate-learning measurement V2

This additive local slice binds the five editorial slots to their exact `article_id`,
slug, tracked article-object packet hash, intent classification, and the fixed program
`WORDPRESS_BLOG_RAKUTEN_AFFILIATE`. It records only sanitized aggregate observations.

The tracked
`self-hosted-editorial-pilot-v1/operations/measurement-ledger.v1.json` is an immutable
compatibility template. Actual observations belong only in these owner-private paths:

- `.secrets/st1704-owner-local-pilot/affiliate-learning-ledger.v2.json`
- `.secrets/st1704-owner-local-pilot/affiliate-learning-observation-input.v2.json`
- `.secrets/st1704-owner-local-pilot/affiliate-learning-ledger.v2.lock`
- `.secrets/st1704-owner-local-pilot/affiliate-learning-ledger.v2.json.preparing`

From the exact physical repository root:

```bash
make -f changes/st-1704/affiliate-learning-v2/Makefile check
make -f changes/st-1704/affiliate-learning-v2/Makefile init
make -f changes/st-1704/affiliate-learning-v2/Makefile doctor
make -f changes/st-1704/affiliate-learning-v2/Makefile record
make -f changes/st-1704/affiliate-learning-v2/Makefile report
```

Before `record`, an owner copies one generated example to the fixed input path with
mode `0600`, then replaces only the aggregate values and provenance hashes. The
examples are deliberately `UNAVAILABLE`; they are not observed facts or evidence.
Never paste credentials, URLs, provider rows, search queries, article body, prompts,
cookies, PII, IP addresses, or full user agents.

The report calculates search CTR, affiliate click rate, direct confirmed reward per
click, outcome confirmation rate, and direct confirmed reward per content hour only
for the same period/program with verified direct attribution and a mature cohort.
Missing, unverified, zero-denominator, immature, or mismatched inputs remain
`UNAVAILABLE`, never an invented zero. Explicitly observed numerator zero remains a
valid zero when its denominator is positive.

Unattributed confirmed reward is a separate program observation. It is never divided
among articles. The report may return human-review proposal codes, but has no article,
CTA, product, recommendation, snapshot, publication, provider, network, or tracking
mutation capability. Commission rate, EPC, RPM, and profit are excluded from
recommendation inputs.

Formal ST-1704, TST-018/TST-020/TST-032, live provider, staging, release, and
Production remain unexecuted.
