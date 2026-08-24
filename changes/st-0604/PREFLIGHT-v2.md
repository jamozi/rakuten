# ST-0604 V2 implementation preflight

- Story: `ST-0604` only.
- Canonical input: the approved Story, `FR-006`, UI workflow `UI-WF-003`,
  `SEC-AI-001` through `SEC-AI-004`, and suites `TST-012` / `TST-020`.
- Dependencies inspected: executable ST-0602 V2 Fact runtime, executable
  ST-0603 V2 Conflict runtime, and the recorded-local ST-0403 durable
  authorization seam.
- Open decisions: none are attached to ST-0604. No business or provider
  decision is introduced here.
- Authorization boundary: a human review decision is accepted only after an
  exact ST-0403 `PUBADM-004` recorded allow is recovered for the packet's
  immutable review-assignment binding. Production identity and credentials are
  absent.
- Safety boundary: local owner-private SQLite and recorded/synthetic fixtures
  only. AI, network, provider, ranking, revenue, publication, release, staging,
  and Production actions are structurally absent.
- Completion boundary: local code and local integration evidence only. This
  work does not claim formal `VALIDATED`, staging, release, or Production
  status.
- Evidence boundary: the deterministic owner manifest binds the closed
  contract, synthetic fixture, implementation, tests, documentation, and
  local completion record. It does not promote local checks to formal suites.

The implementation is additive. The V1 reference plan remains a predecessor
compatibility artifact and is not treated as executable runtime evidence.
