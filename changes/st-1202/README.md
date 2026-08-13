# ST-1202 disabled public event instrumentation requirements candidate

## Result and authority

This Story slice adds one strict TypeScript candidate named
`UNREGISTERED_DISABLED_HEADLESS_ST1202_PUBLIC_EVENT_INSTRUMENTATION_REQUIREMENTS_CANDIDATE`.
It records only the fixed local requirements for canonical `AN-SLICE-002` on
public screen `PUB-003` and route template `/articles/{slug}`.

The candidate is unregistered, disabled, headless, noninteractive, and
runtime-ineligible. It creates no route, renderer, CTA instance, DOM,
React/Next component, browser lifecycle hook, `PerformanceObserver`, clock,
random identifier, cookie/storage access, `sendBeacon`, keepalive fetch,
network request, `PUB-004` request, collector call, event, persistence, or
external effect. Canonical Story status remains `NOT_STARTED`; verification
remains `NOT_EXECUTED`. Local evidence grants no tracking, privacy, browser,
publication, release, or Production authority.

## Fixed event requirements

The candidate projects exactly the six MVP `public_web` events directly named
by ST-1202 and `AN-SLICE-002`:

- `EVT-001` `article_view`;
- `EVT-002` `qualified_decision_engagement`;
- `EVT-003` `affiliate_cta_impression`;
- `EVT-004` `affiliate_click`;
- `EVT-006` `comparison_interaction`; and
- `EVT-012` `web_vital`.

Their canonical ordered parameter names and common prohibited parameter set
are copied as requirements metadata only. No other public event, including
non-MVP `EVT-009 content_feedback`, is represented in the candidate. No
trigger, identity, parameter value, threshold, transport, or collector is
selected: each remains `null` or `NOT_EVALUATED`, instrumentation is false,
and emission is disabled.

## Privacy and navigation boundary

OD-012 remains a blocking human decision. The candidate preserves only the
safe default `NONESSENTIAL_TRACKING_DISABLED`, does not infer consent or
first-party-minimal-event eligibility, creates no session pseudonym, and uses
no cookie, storage, fingerprinting, or provider tracking.

The fixed navigation requirement remains declarative: a future affiliate CTA
must navigate directly to the canonical provider URL, must not use a RAOS
redirect, and must never wait for instrumentation or fail because collection
fails. Navigation and beacon execution are both false, no transport is
selected, and no browser claim is made.

## Why runtime instrumentation remains closed

Merged ST-1002 supplies no registered route, renderer, DOM, lifecycle signal,
or authoritative article/snapshot identity. Merged ST-1004 exposes only the
static `UI-C034` component type while the CTA, offer, link, URL, and instance
identities remain absent. Merged ST-1201 is a disabled process-local recorded
seam with no endpoint, browser binding, persistence, or durable dedupe. Its
documented `PUB-004` to `EVT-004` and canonical-event to ST-0305-row mappings
remain unresolved integration debt. ST-1006 likewise records RUM requirements
without observing or emitting them.

Canonical sources do not select article-view lifecycle semantics, qualified
engagement behavior, CTA visibility thresholds, comparison interaction values,
RUM observation/sampling values, event/site/correlation IDs, timestamps,
session/pseudonym behavior, consent state, transport choice, endpoint mapping,
or runtime collector binding. Choosing any of those would add an unauthorized
privacy or runtime decision.

## Strict synthetic boundary and owned files

Input contains only exact `PUB-003`, `/articles/{slug}`, and an explicitly
synthetic coordinate whose two caller-supplied lowercase SHA-256 strings must
be equal. The hashes are opaque coordinates: they are not recomputed,
canonicalized, attested, or treated as renderer, runtime, or formal evidence.

Validation is exact and closed. It rejects unknown shapes, malformed or
mismatched hashes, identifiers, times, sessions, consent, values, thresholds,
transports, payloads, effects, accessors, symbols, cycles, subclasses, hostile
structures, and authority escalation. Errors expose only stable codes and
never echo hostile values. Successful candidates are deterministic, detached,
JSON-safe, and deeply frozen.

The exact owned paths are:

```text
packages/web-ui/src/public-event-instrumentation.ts
packages/web-ui/src/index.ts
tests/st1202/public-event-instrumentation-contract.test.ts
tests/st1202/public-event-instrumentation-model.test.ts
tests/st1202/public-event-instrumentation-boundaries.test.ts
tests/st1202/public-event-instrumentation-negative.test.ts
changes/st-1202/README.md
```

## Explicitly out of scope

React/Next/DOM rendering, route registration, browser handlers, visibility or
engagement observers, Core Web Vitals measurement, `sendBeacon` or fetch,
actual navigation, API/endpoint/collector calls, event construction or
emission, IDs, timestamps, sessions, pseudonyms, consent UI or policy,
thresholds, sampling, CTA/link resolution, persistence, durable dedupe,
retention, GA4/provider integration, and formal `TST-022`/`TST-030`, browser,
live, staging, publication, release, and Production work remain unimplemented,
unavailable, unauthorized, or `NOT_EXECUTED`.
