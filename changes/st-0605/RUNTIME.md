# ST-0605 executable local runtime V1

The historical Claim/evidence reference plan remains a separate immutable
record. This additive runtime implements a recorded-synthetic Claim--Evidence
evaluator. Its owner contract is
`contracts/claim-evidence-runtime.v1.yaml`; its generated passing fixture and
runtime manifest are owned by
`scripts/build_st0605_claim_evidence_runtime.py`.

The evaluator binds one Article Version/body hash to the exact Source Packet
Version/content selected by the Article. It recomputes the Claim-set hash and
also requires a distinct version/hash-bound Claim-inventory attestation. The
pure evaluator is deterministic but grants no authority. At the recording
boundary, the Article Version ID is resolved through the trusted preloaded
snapshot reader and the complete snapshot is evaluated again, so a caller
cannot shrink the coverage denominator or substitute a different snapshot or
report.
Packet approval/membership, Fact validation, complete conflict closure, and
Product/Variant identity decisions are separate receipts with exact owner
Story, contract version, contract hash, subject hash, input hash, decision
hash, and validation time. This V1 accepts only recorded-synthetic receipts;
missing, extra, stale, mismatched, or self-renamed receipts make the result
`UNEVALUABLE`.
Recorded-synthetic attestation decision hashes are deterministic corruption
checks for fixture integrity; they are not signatures, authentication, or
proof that an owner Story executed in a live system.

The nine policy Claim types, six policy Source tiers, and policy link types are
explicit ST-0605 namespaces. They are not inferred from the non-isomorphic
persisted or AI vocabularies. ST-0605 verifies closure, bindings, source and
citation eligibility, and coverage arithmetic; it does not reimplement the
owner algorithms for Fact derivation, comparison, recommendation, experience,
Offer freshness, or safety compliance. Those Claim types require their exact
owner receipt before coverage is evaluated. Only a current,
identity-matched, in-packet, citation-resolved `SUPPORTS` link from an eligible
source counts. `QUALIFIES` alone does not count; contradictory, future/stale,
out-of-packet, wrong-subject, unresolved/conflicting identity, unreviewed
conflict resolution, missing citation, prohibited-source, and imputed-unknown
paths fail closed.

Major coverage uses exact integer equality and all-Claim coverage uses
`evidenced * 100 >= total * 95`; an unsupported non-major Claim within the 5%
tolerance does not silently turn the threshold into 100%. A zero denominator
is `UNEVALUABLE`.
Predictive Claims remain default-blocked by the explicit policy even though the
generic repeated content-matrix row labels a fully evidenced predictive case
as `PASS`. Derived, comparative/superlative, recommendation, experience, and
safety/legal types require both their explicit proof binding and the separate
owner attestation. Every report binds evaluator version, evaluation time, the
canonical hash of every evaluation input relation, and a coherent report hash;
the append boundary independently re-evaluates its immutable input anchor, so
semantically empty or coherent self-hashed forged `PASS` reports are rejected.
Preloaded snapshot anchors and append history are stored as immutable digest/
byte values rather than relying on caller-owned frozen dataclass references.

The application surface is a read-only snapshot evaluator plus an internal
append-only, process-local result recorder. It has no article, CTA,
recommendation, Publication Snapshot, repository, database, network, provider,
credential, approval, or publication mutation. Every report fixes
`publication_authorized=false` and `production_eligible=false`; formal
TST-020/TST-021, live, staging, release, and Production remain
`NOT_EXECUTED`.

The runtime package facades resolve their public compatibility exports lazily.
A fresh ST-0605 import therefore does not initialize OpenAI, HTTPX, generated
Content AST models, or unrelated registries. The isolated-process import test
hash-checks every repository-backed `raos` module loaded by this runtime
against the generated source manifest.

Generate and check only through the owner command:

```text
.venv/bin/python scripts/build_st0605_claim_evidence_runtime.py
.venv/bin/python scripts/build_st0605_claim_evidence_runtime.py --check
```

The generator rejects anything other than CPython 3.14.6, PyYAML 6.0.3,
Pydantic 2.13.4, pydantic-core 2.46.4, and pytest 9.1.1. The Pydantic pair is
part of the actual bounded runtime import closure; pytest is the recorded
verification tool. `pyproject.toml` and `uv.lock` are manifest-bound. These
commands use the already provisioned locked environment and do not perform
dependency synchronization or network access.
The two generated files are replaced with rollback for synchronous failures
and `KeyboardInterrupt`/`SystemExit` before the commit point. After every
replacement has committed, cleanup catches and retries asynchronous
interruptions without undoing the complete result; a persistent cleanup
failure returns the closed `GENERATION_POST_COMMIT_CLEANUP_FAILED` diagnostic.
Machine power loss or process termination that prevents Python cleanup is
outside this local transaction guarantee; generated artifacts must be rerun
and checked after such a crash.
