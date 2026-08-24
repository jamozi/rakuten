# ST-1201 local durability hardening preflight

## Story and objective

- Story: `ST-1201` — Canonical event collector.
- Scope: harden the existing maximum-safe owner-private SQLite recorded-event
  store and its application/port boundary without activating tracking or any
  external operation.

## Canonical and implementation inputs read

- Root and Canonical `AGENTS.md`, master readme, integration design, Canonical
  decisions, and open decisions.
- ST-1201 backlog row; dependencies ST-0305 and ST-0404; the current ST-1201
  contract, generated projection, manifest, completion record, generator,
  runtime modules, and 87-test suite.
- Canonical event catalog, security/privacy design, data classification and
  security control catalog; release-blocking TST-012, TST-030, and TST-031.
- Hardened local SQLite patterns owned by ST-0601, ST-0503, and ST-0602.

## Open decisions and safe boundary

- OD-012 remains unresolved. Nonessential/browser tracking remains disabled;
  only explicit synthetic `GRANTED` / `FULL_CONSENT` recorded-local input can
  reach the store.
- OD-014 remains unresolved. No retention, deletion, purge, export, restore, or
  lifecycle behavior is added.
- A same-process monotonic anchor can detect named-file replacement and an
  older valid same-inode snapshot. A fresh process has no external durable
  anchor and therefore cannot claim rollback detection; this limitation will
  remain explicit and tested.

## Planned owned changes

- Harden created-only initialization, descriptor-relative file validation,
  exact file identity, fsync, exact schema/PRAGMA inventory, append-only guards,
  metadata CAS, full canonical-event decoding, hash binding, monotonic prefix
  checks, and commit recovery classification.
- Harden the inward port/application collaborator boundary with reconstructed
  inputs, pre/post snapshots, and exact zero-action checks on every call.
- Update the ST-1201 contract, README, generator-owned artifacts, manifest,
  completion evidence, and add deterministic hostile/storage/concurrency tests
  with unique module basenames.

## Planned verification

- Isolated combined ST-1201 pytest plus repeated concurrency/commit recovery.
- Owner generation, `--check`, and no-write verification.
- Stable affected ST-0405 and ST-1202 suites where their existing provenance
  permits; compile/import, Ruff, mypy, Pyright, denied-network, target secret and
  scope checks, and `git diff --check`.

## Out of scope

- HTTP route/browser beacon activation, consent-policy selection, provider or
  network calls, credentials, analytics export, recommendation/content/revenue
  mutation, publication, retention/deletion, staging, release, and Production.
- Canonical status `APPLY` and formal/live TST evidence.
