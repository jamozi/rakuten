# ST-0805 — content-addressed editorial policy engine V2

Local status: `LOCAL_IMPLEMENTATION_COMPLETE`.

This additive runtime keeps the historical V1 evaluator unchanged and wraps
its canonical 40-policy, 8-quality-axis, 13-zero-tolerance, and 12-gate result
in an exact dependency boundary. One input binds an ST-0802 UUIDv7 DRAFT and
canonical Content AST, an independently recomputed ST-0605 coverage
report/receipt, and an independently recomputed ST-0804 recommendation
report/receipt. Article, version, body, Packet, Claim set, candidate universe,
axis catalog, Fact set, temporal scope, decision context, and methodology
hashes must agree across the chain.

ST-0605 needs a complete COMPARISON validation receipt to produce `PASS`, while
ST-0803 correctly refuses a pre-existing COMPARISON receipt because it emits
that receipt itself. The generated fixture therefore derives two views from
the same immutable claim/evidence core: the complete ST-0605 view and the
precomputed-tuple ST-0803 view. V2 verifies their exact common core instead of
weakening either predecessor.

Structural, missing, or unevaluated material is `UNEVALUABLE`. Trusted hash,
receipt, semantic, policy, zero-tolerance, gate, or prohibited-input failure is
`BLOCK`. Only a complete finding-free chain is `LOCAL_EVALUATED`. Unknown,
missing, conflict, and unevaluated states are never converted to zero or PASS.

Affiliate, commission, rate, reward, EPC, RPM, revenue, profit, and sponsorship
keys are rejected recursively, including NFKC/fullwidth, case, and common leet
aliases. The exact schema-owned `affiliate_content` disclosure flag remains
permitted. These values cannot affect policy waivers or ranking. Findings and
waivers are proposals only; approval, application, merge, recommendation or
ranking override, publication, activation, and Production authority are all
false.

Generate and verify the two owner artifacts with:

```bash
.venv/bin/python scripts/build_st0805_policy_runtime.py
.venv/bin/python scripts/build_st0805_policy_runtime.py --check
```

The owner uses the hash-bound `secure_generated_publication.py` transaction:
existing targets use descriptor-relative `renameat2(RENAME_EXCHANGE)` with
displaced/reverse identity verification, missing targets use a no-clobber hard
link, and rollback preserves foreign material. Formal TST-019/TST-020, hosted
CI, live validation, staging, release, publication, and Production remain
`NOT_EXECUTED`.
