# ST-1006 — disabled headless performance and RUM requirements candidate

## Result and authority

This Story slice adds one strict, dependency-free TypeScript candidate named
`UNREGISTERED_DISABLED_HEADLESS_ST1006_PERFORMANCE_RUM_REQUIREMENTS_CANDIDATE`.
It records only the approved local requirements for public Core Web Vitals,
layout stability, image sizing, and the `EVT-012` RUM vocabulary.

The candidate is unregistered, disabled, headless, noninteractive, and
ineligible. It creates no route, renderer, DOM, React/Next component, SSR path,
browser instrumentation, `PerformanceObserver`, beacon/fetch transport,
analytics event, cookie/storage access, consent decision, collector request,
network call, cache/image optimization, CTA layout, publication action, or
external effect. Canonical Story status remains `NOT_STARTED`; verification
and formal `TST-027` remain `NOT_EXECUTED`.

## Fixed targets are not observations

The candidate retains the approved provisional `SLO-012` field targets:

- LCP at the 75th percentile is at most 2.5 seconds;
- INP at the 75th percentile is at most 200 milliseconds; and
- CLS at the 75th percentile is at most 0.1.

These are requirement thresholds, not measurements. Every observed value and
rating is null, every lab/field/CTA-layout assessment is `NOT_EVALUATED`, and
measurement implementation and execution are false. The rolling 28-day field
target is not claimed achieved without real RUM.

The fixed UI requirements reserve image dimensions and prohibit layout shift
caused by affiliate/analytics scripts or CTA placement. No cache strategy,
image optimization strategy, or CTA layout strategy is selected because
ST-1002 provides no runtime renderer, DOM, route, or public projection.

## RUM, privacy, and dependency boundary

`EVT-012` is retained only as catalog metadata. Its exact permitted and
prohibited parameter names are visible, while instrumentation, collector,
transport, provider, and emission remain absent or disabled. The candidate
contains no metric events, actions, or effects.

Actual public instrumentation is downstream `ST-1202` and depends on the
`ST-1201` collector. `OD-012` remains a blocking human decision for privacy and
consent. This slice preserves the safe default `NONESSENTIAL_TRACKING_DISABLED`,
does not infer consent, does not decide whether even a minimal first-party
event is eligible, and selects no provider. No local result grants tracking,
approval, publication, staging, release, or Production authority.

## Strict synthetic boundary

Input contains only the exact `PUB-003` screen, `/articles/{slug}` route
template, and an explicitly synthetic coordinate whose caller-supplied
lower-case SHA-256 strings must be equal. The hashes are opaque coordinates:
they are not recomputed, canonicalized, attested, or treated as renderer,
runtime, or formal evidence.

Validation rejects unknown shapes, malformed or mismatched hashes, content,
internal data, executable/tracking surfaces, subclasses, accessors, symbols,
cycles, hostile proxies, observed-value injection, consent inference, event or
effect addition, and authority escalation. Failures use closed stable codes
and never echo hostile values. Successful values are detached, deterministic,
JSON-safe, and deeply frozen.

## Owned files and local checks

The exact owned paths are:

```text
packages/web-ui/src/public-performance-rum.ts
packages/web-ui/src/index.ts
tests/st1006/public-performance-rum-contract.test.ts
tests/st1006/public-performance-rum-model.test.ts
tests/st1006/public-performance-rum-boundaries.test.ts
tests/st1006/public-performance-rum-negative.test.ts
changes/st-1006/README.md
```

Focused tests cover the strict requirements model, zero-side-effect boundary,
privacy safe default, deterministic immutability, and critical negative paths.
They are local unit/static evidence only and are not browser, lab, field RUM,
staging, load, privacy-review, or formal `TST-027` evidence.

## Explicitly out of scope

Actual cache headers or cache runtime, image rendering/optimization, CTA DOM or
layout, article rendering, route registration, browser APIs, collection and
transport, event emission, consent/banner/cookie policy, provider selection,
analytics storage, network, browser lab, field RUM, alert evaluation, formal
TST execution, live validation, staging, approval, publication, release, and
Production remain unimplemented, unavailable, unauthorized, or
`NOT_EXECUTED`.

Canonical, upstream, generated, status, lock, and workflow artifacts are not
edited by this local candidate.
