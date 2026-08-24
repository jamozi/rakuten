# ST-1007 V2 — local browser accessibility evidence

## Local result

V2 adds an executable, dependency-free Node owner runner that builds and starts
the real local Next application, launches one hash-pinned Chrome for Testing
binary through the Chrome DevTools Protocol, injects the hash-pinned local
`axe-core` bundle, and audits the current public DOM. Browser traffic is limited
to the ephemeral loopback origin; any other request fails the run.

The runner observes the five implemented canonical public screens `PUB-003`
through `PUB-007` and the framework's default 404 response for `PUB-008`. It
checks axe WCAG tags, unique titles, one H1, Japanese document language, main
landmarks, skip-link keyboard flow, visible focus, console/page errors, HTTP
status, and document overflow at 320, 360, 768, and 1440 CSS pixels. It writes a
deterministic, source-hash-bound JSON record with no timestamps, ports, process
IDs, host paths, or browser profile data.

## Fail-closed acceptance boundary

The local automated result cannot satisfy Canonical Story acceptance. `PUB-001`,
`PUB-002`, `PUB-009`, and `PUB-010` do not have runtime routes. The default 404
observation is not promoted to a designed `PUB-008` implementation. Product
cards, comparison tables, and the synthetic future affiliate anchor are not
mounted on the recorded article, so their static semantics are not promoted to
browser evidence.

Formal `TST-023` requires the formal CI environment. `TST-024` requires staging,
human keyboard and cognitive checks, actual 200% zoom review, and NVDA,
VoiceOver, or equivalent assistive technology. Those remain `NOT_EXECUTED`.
Automated checks do not claim WCAG conformance, all-screen P0 PASS, validation,
release readiness, or Production readiness.

## Owner commands

Run from the physical repository root with the pinned Node toolchain and the
exact browser binary whose SHA-256 is fixed by the V2 contract:

```text
node scripts/check_st1007_public_accessibility_browser.mjs \
  --browser-executable /path/to/hash-pinned/chrome \
  --write

node scripts/check_st1007_public_accessibility_browser.mjs \
  --browser-executable /path/to/hash-pinned/chrome \
  --check
```

`--write` atomically replaces only the owned generated record. `--check` never
writes that record and compares exact bytes; the ignored Next build cache may be
refreshed. The runner rejects unknown arguments,
non-regular or hash-mismatched executables, source drift, unclean server exits,
unexpected network, malformed CDP data, axe violations, duplicate titles,
missing landmarks, broken skip-link focus, console errors, page errors, and
horizontal document overflow.

No provider, public Internet, analytics, database, credential, publication,
staging, release, deployment, or Production action is performed. The existing
V1 requirements candidate remains unchanged.
