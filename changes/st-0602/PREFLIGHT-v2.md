# ST-0602 V2 local implementation preflight

- Story: `ST-0602` — create exact typed OFFER Facts from exact durable ST-0601
  raw artifact readback and exact durable ST-0503 structural observations.
- Read inputs: Canonical integration precedence, ST-0602 backlog row, FR-004,
  TST-005/TST-007, the Fact/source-snapshot data model, extraction job and
  event contracts, SEC-DATA-004/005, SEC-AI-001/003, THR-009/017, OD-006,
  the V1 ST-0602 plan, and the exact ST-0601/ST-0503 V2 runtime boundaries.
- Confidence policy: fixed decimal `1.0000` means only exact structural
  extraction fidelity. It is separately labelled
  `EXACT_STRUCTURAL_EXTRACTION_NOT_TRUTH_ATTESTATION`; truth remains
  `NOT_ATTESTED` and publication readiness remains `NOT_READY`.
- Identity policy: OD-006 remains unresolved. Facts use the exact stable OFFER
  identifier only. No PRODUCT Fact, canonical product identifier, automatic
  identity decision, recommendation, or ranking is implemented.
- URL policy: the ST-0503 affiliate-link observation is deliberately not a
  Fact. Raw URLs and provider text are absent from ST-0602 mappings, SQLite
  payloads, generated fixtures, reports, and failure values.
- Planned owned files: additive V2 domain, port, application service,
  owner-private SQLite adapter, Story-local tests, closed JSON contract and
  synthetic fixture, deterministic owner generator, projection, manifest,
  and local completion record. Existing V1 plan semantics remain unchanged.
- Local checks: V1 and V2 Story suites separately, dependency regressions,
  owner generators with no-write checks, Ruff, strict mypy, pinned Pyright,
  compile/import, denied-network/static authority checks, and diff checking.
- Out of scope: formal TST-005/TST-007 execution, PostgreSQL, cross-restart
  rollback anchoring, live provider or credentials, event delivery, manual
  review decision, publication, recommendation, ranking, revenue, staging,
  release, and Production.
