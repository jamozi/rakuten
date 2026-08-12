# ST-0906 disabled headless publication-review workspace

Status: `LOCAL_IMPLEMENTATION_CANDIDATE` / maximum-safe static slice.

This Story slice projects the seven canonical `REV` and `PUBA` screens into a
deep-frozen, JSON-serializable TypeScript model. It is a data-only orientation
surface for the unavailable review and publication workflow. It does not add a
web route, render a screen, load review or publication data, record a decision,
approve an article, render an authoritative snapshot, or emit a publish or
rollback intent.

## Exact screen and layout boundary

The projected screen set is exactly:

```text
REV-001   /admin/reviews
REV-002   /admin/reviews/{versionId}
REV-003   /admin/approvals/{versionId}
PUBA-001  /admin/publications
PUBA-002  /admin/publications/{id}/preview
PUBA-003  /admin/publications/{id}/publish
PUBA-004  /admin/publications/{id}/rollback
```

Routes are catalog metadata only. ST-1101 still registers only the disabled
`/admin` shell, so every route above remains unregistered. The headless layout
is a calm, cardless utility sequence: orientation, blockers, review, diff, and
preview. It contains no marketing hero, card mosaic, decorative motion, React,
Next.js, JSX, DOM, browser API, transport, generated client, or effect callback.

## Dependency and authority boundary

- ST-0901 supplies only pure/recorded local review seams. Its positive approval
  and applicability gates remain closed, and it supplies no UI or runtime
  authority.
- ST-0902 through ST-0905 are non-executable, non-authoritative reference plans.
  They supply no final approval, snapshot, projection, publish, or rollback
  runtime.
- ST-1101 is a disabled headless foundation. It supplies neither auth transport
  nor a StepUpDialog effect.

Consequently the model accepts only one exact screen ID. Role lists are display
metadata, never authorization input. Authentication and authorization remain
false, backend reauthorization remains required, and all data, network,
storage, persistence, mutation, external-action, and publication switches are
false. `actionIntents` is permanently empty. Final approval, publish, and
rollback remain `BLOCKED_DEPENDENCY_NOT_EXECUTABLE`.

OD-005, OD-007, OD-008, and OD-010 are represented only by their conservative
cross-boundary safeguards. No open decision is inferred or resolved. The
conflicting final-approval step-up sources retain the fail-closed value
`CONFLICT_UNRESOLVED_DENY`; publish and rollback step-up remain required but
unavailable.

## Accessibility and evidence boundary

The model records semantic, focus-order, textual-status, text-labelled diff,
keyboard, screen-reader, and visible-focus requirements. It implements no DOM
and makes no conformance claim. Motion is absent. Formal TST-022, TST-024,
browser, automated/manual accessibility, authentication, authorization,
step-up, API, database, live, staging, publication, rollback, release, and
Production verification remain `NOT_EXECUTED`.

Focused Node-native tests cover exact catalog metadata and hashes, deterministic
deep freezing and round-trip validation, the utility composition, unregistered
routes, absent action/effect surfaces, accessibility requirements, sanitized
strict-input failures, and tamper rejection. Local results are implementation
evidence only and do not grant approval, publication, release, or Production
authority.

## Exact owned files

```text
packages/web-ui/src/publication-review-workspace.ts
packages/web-ui/src/index.ts
tests/st0906/publication-review-workspace-contract.test.ts
tests/st0906/publication-review-workspace-model.test.ts
tests/st0906/publication-review-workspace-accessibility.test.ts
tests/st0906/publication-review-workspace-negative.test.ts
tests/st0906/publication-review-workspace-boundaries.test.ts
changes/st-0906/README.md
```

No canonical, upstream, generated, route, API, contract, migration, database,
job, event, audit, idempotency, outbox, provider, workflow, or lockfile artifact
is changed.
