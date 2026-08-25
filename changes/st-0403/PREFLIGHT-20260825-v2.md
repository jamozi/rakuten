# ST-0403 durable authorization hardening preflight

- Story: `ST-0403`
- Mode: `STRICT_STORY`
- Environment boundary: recorded `ENV-DEV` / `CI` only
- External action count: exactly `0`
- Publication, credential, live-provider, staging, release, and production authority: absent

## Canonical and dependency inputs read before editing

- root, Canonical, integration, and Codex `AGENTS.md` instructions
- Canonical integration design and Story backlog entries for `ST-0306`, `ST-0401`, and `ST-0403`
- Canonical role/permission matrix, security/privacy design, security-control catalog, threat register, data classification, implementation slices, and TST-011/TST-012/TST-026 definitions
- `ST-0306` database-role/grant contract
- current hardened `ST-0401` runtime, contract, owner evidence, and tests
- `ST-0402` local step-up runtime contract
- the complete current ST-0403 contract, owner generator, generated registry, manifest, runtime, adapters, tests, README, and completion evidence

## Reproduced baseline

`tests/st0403` produced 92 passing behavior tests and three owner-evidence failures. All three failures were the same inherited provenance drift: ST-0403 still pinned the predecessor ST-0401 contract hash from before its schema-V2 hardening. The pin is rebound first to the exact current ST-0401 contract bytes.

## Local implementation gaps selected for this Story

- reject every pre-existing empty, partial, or foreign database instead of initializing it
- replace the mutable schema-V1 store with an exact SQLite schema-V2 contract using `STRICT`, foreign keys, closed PRAGMAs, and append-only mutation/audit/command history
- pin owner-root and database file identity for each repository and detect process-local valid-prefix rollback with a full-chain anchor
- make every persisted document a canonical byte encoding with redundant relational bindings checked during decode
- preserve exact revision compare-and-set semantics under concurrency and classify commit failures by whether commit is known rolled back or genuinely unknown
- detach caller, repository, session, step-up, and HTTP boundary values and keep the recorded runtime's local external-action count exactly zero
- retain deny-by-default, horizontal/vertical denial, site/state/scope, separation-of-duties, and disabled external-action semantics

## Explicit limitation

The process-local anchor detects replacement and rollback while a valid prefix has been observed in this process. Detecting a valid-prefix rollback across process restarts requires an independent external anchor. ST-0403 does not invent that live or operational authority; the limitation remains explicit and fail-closed within the available local boundary.

## Verification boundary

Focused hostile-input, tamper, concurrency, recovery, generation, parse/type/static, secret, denied-network, and scope checks are local evidence only. Formal TST, hosted CI, staging, provider, release, publication, and production verification remain unexecuted.
