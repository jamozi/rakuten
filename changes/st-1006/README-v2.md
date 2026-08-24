# ST-1006 V2 — local performance and image-safety runtime

## Local result

V2 replaces the historical requirements-only stopping point with executable,
deterministic local boundaries for the exact ST-1002 recorded article:

- canonical LCP/INP/CLS targets and a nearest-rank p75 evaluator for explicitly
  recorded-synthetic samples;
- an image presentation policy that requires intrinsic dimensions, an ordered
  responsive-width set, an explicit `sizes` value and reserved layout space;
- above-fold `eager`/`high` and below-fold `lazy`/`auto` loading policy, with
  async decode, no cropping and no upscaling;
- a deterministic CTA rectangle-reservation check that returns no inferred CLS
  score when the rectangles differ; and
- a default-disabled `EVT-012` hook that drops every candidate without reading
  it and can neither buffer nor transport an event.

The V1
`UNREGISTERED_DISABLED_HEADLESS_ST1006_PERFORMANCE_RUM_REQUIREMENTS_CANDIDATE`
remains unchanged and exported for compatibility.

## Recorded fixture is not measurement evidence

The fixture samples and rectangles are labelled
`RECORDED_SYNTHETIC_ONLY`. Their local pass result verifies the evaluator and
policy implementation only. It is not a browser lab run, field RUM, a 28-day
population, a Core Web Vitals claim, staging evidence or formal `TST-027`.
Every such external/formal state remains `NOT_EXECUTED`.

The current ST-1002 route remains exactly as inherited: one local noindex SSR
preview, `no-store`, with zero images and no rendered affiliate CTA. ST-1006
does not add a product image, media URL, CTA, route, cache mutation, client
component or script. Its recorded image fixture has no `src`, `srcset`, bytes,
alt copy or URL and is deliberately `renderable: false`; it proves only that a
future verified source must reserve dimensions and provide responsive sizing.

## RUM and privacy boundary

`OD-012` remains unresolved and blocking. `createDefaultDisabledPublicRumHookV2`
has no enabled variant in this Story. Its `capture` method does not inspect the
argument—even an accessor or hostile proxy—returns a frozen
`DROPPED_DISABLED` receipt, stores nothing, and leaves an empty snapshot. There
is no `PerformanceObserver`, browser lifecycle hook, clock, identifier,
cookie/storage access, fingerprinting, beacon/fetch, collector, provider,
network or persistence.

This preserves `EVT-012` as a catalog binding without treating its parameter
vocabulary as tracking authority. An enabled public instrumentation path, if
later authorized, belongs to the analytics/consent boundary and must not be
inferred from this local fixture.

## Owner artifacts

Owner source is
`changes/st-1006/contracts/public-performance-runtime.v2.yaml`. Generate and
verify the two deterministic outputs with:

```text
.venv/bin/python scripts/build_st1006_public_performance_runtime.py
.venv/bin/python scripts/build_st1006_public_performance_runtime.py --check
```

The generator validates the Canonical Story, `PUB-003`, `EVT-012`, `OD-012`,
`SEC-DATA-007`, `TST-027`, the exact ST-1002 local runtime dependency, the
budget calculation and the image/CTA fixture invariants. It writes only:

- `changes/st-1006/generated/public-performance-recorded.v2.json`; and
- `changes/st-1006/runtime-manifest.v2.yaml`.

## Authority and remaining work

This Story is `LOCAL_CODE_COMPLETE` at the maximum safe local boundary. It
performs no live/public observation, tracking, external write, publication,
staging, release or Production action and grants none of those authorities.
Real browser/lab/load checks, field RUM, consent/privacy approval, verified
media-source integration, cache calibration, formal `TST-027`, staging,
publication, release and Production remain explicitly `NOT_EXECUTED` or
unauthorized.
