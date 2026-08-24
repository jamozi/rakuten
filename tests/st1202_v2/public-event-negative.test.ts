import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PublicEventInstrumentationErrorV2,
  createDisabledPublicEventInstrumentationRouteBoundaryV2,
  createRecordedPublicEventInstrumentationV2,
  validatePublicEventInstrumentationEnvelopeV2,
  validatePublicEventInstrumentationRecordedFixtureV2,
  type PublicEventInstrumentationEnvelopeV2,
} from '../../packages/web-ui/src/public-event-instrumentation.ts';

import { recordedEvents, recordedFixture } from './fixture.ts';

const CANARY = 'ST1202_V2_REJECTED_CANARY_DO_NOT_ECHO';

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function assertClosedFailure(run: () => unknown, code?: string): PublicEventInstrumentationErrorV2 {
  let observed: unknown;
  try {
    run();
  } catch (error) {
    observed = error;
  }
  assert.ok(observed instanceof PublicEventInstrumentationErrorV2);
  if (code !== undefined) assert.equal(observed.code, code);
  assert.doesNotMatch(`${observed.message} ${observed.stack ?? ''}`, new RegExp(CANARY));
  return observed;
}

describe('ST-1202 V2 strict route boundary', () => {
  it('rejects identities, a CTA, tracking state, or unknown route fields', () => {
    const base = {
      schemaVersion: 2,
      screenId: 'PUB-003',
      routePath: '/articles/synthetic-recorded-policy-seo',
      sourceProfile: 'EXACT_ST1002_RECORDED_PUBLIC_ARTICLE_V2',
      identities: { articleId: null, snapshotId: null, categoryId: null },
      affiliateCta: {
        state: 'UNAVAILABLE_SOURCE',
        ctaId: null,
        offerId: null,
        rendered: false,
      },
    };
    for (const mutate of [
      (value: Record<string, unknown>) => {
        (value.identities as Record<string, unknown>).articleId = CANARY;
      },
      (value: Record<string, unknown>) => {
        (value.affiliateCta as Record<string, unknown>).rendered = true;
      },
      (value: Record<string, unknown>) => {
        value.tracking = true;
      },
    ]) {
      const changed = clone(base) as Record<string, unknown>;
      mutate(changed);
      assertClosedFailure(
        () => createDisabledPublicEventInstrumentationRouteBoundaryV2(changed as never),
        'PUBLIC_INSTRUMENTATION_V2_ROUTE_CONTEXT_INVALID',
      );
    }
  });
});

describe('ST-1202 V2 hostile event and fixture inputs', () => {
  it('rejects PII and sensitive values without echo', () => {
    const event = clone(recordedEvents()[0]);
    assert.ok(event);
    (event.parameters[0] as { name: string; value: string }).value = `${CANARY}@example.invalid`;
    assertClosedFailure(
      () => validatePublicEventInstrumentationEnvelopeV2(event),
      'PUBLIC_INSTRUMENTATION_V2_PII_FORBIDDEN',
    );

    const prohibitedName = clone(recordedEvents()[0]);
    assert.ok(prohibitedName);
    (prohibitedName.parameters[0] as { name: string }).name = 'email';
    assertClosedFailure(
      () => validatePublicEventInstrumentationEnvelopeV2(prohibitedName),
      'PUBLIC_INSTRUMENTATION_V2_PII_FORBIDDEN',
    );
  });

  it('rejects missing/reordered parameters, unknown fields, bad IDs, and invalid time', () => {
    const reordered = clone(recordedEvents()[0]);
    assert.ok(reordered);
    (
      reordered.parameters as PublicEventInstrumentationEnvelopeV2['parameters'][number][]
    ).reverse();
    assertClosedFailure(
      () => validatePublicEventInstrumentationEnvelopeV2(reordered),
      'PUBLIC_INSTRUMENTATION_V2_EVENT_PARAMETER_INVALID',
    );

    const unknown = clone(recordedEvents()[0]) as unknown as Record<string, unknown>;
    unknown[CANARY] = true;
    assertClosedFailure(
      () => validatePublicEventInstrumentationEnvelopeV2(unknown),
      'PUBLIC_INSTRUMENTATION_V2_EVENT_SCHEMA_INVALID',
    );

    const badIdentity = clone(recordedEvents()[0]) as unknown as Record<string, unknown>;
    badIdentity.eventId = CANARY;
    assertClosedFailure(
      () => validatePublicEventInstrumentationEnvelopeV2(badIdentity),
      'PUBLIC_INSTRUMENTATION_V2_EVENT_IDENTITY_INVALID',
    );

    const badTime = clone(recordedEvents()[0]) as unknown as Record<string, unknown>;
    badTime.occurredAt = '2026-02-30T00:00:00.000Z';
    assertClosedFailure(
      () => validatePublicEventInstrumentationEnvelopeV2(badTime),
      'PUBLIC_INSTRUMENTATION_V2_EVENT_IDENTITY_INVALID',
    );
  });

  it('rejects non-recorded consent, event order, faults, and beacon claims', () => {
    const denied = clone(recordedFixture()) as unknown as Record<string, unknown>;
    (denied.consent as Record<string, unknown>).consentState = 'DENIED';
    assertClosedFailure(
      () => validatePublicEventInstrumentationRecordedFixtureV2(denied),
      'PUBLIC_INSTRUMENTATION_V2_CONSENT_INVALID',
    );

    const outOfOrder = clone(recordedFixture());
    const mutableEvents = outOfOrder.events as PublicEventInstrumentationEnvelopeV2[];
    [mutableEvents[0], mutableEvents[1]] = [mutableEvents[1]!, mutableEvents[0]!];
    assertClosedFailure(
      () => validatePublicEventInstrumentationRecordedFixtureV2(outOfOrder),
      'PUBLIC_INSTRUMENTATION_V2_RECORDED_SCRIPT_MISMATCH',
    );

    const unknownFault = clone(recordedFixture());
    (unknownFault.faultEventIds as string[]).push('018f3e90-7b00-7000-8000-000000009999');
    assertClosedFailure(
      () => validatePublicEventInstrumentationRecordedFixtureV2(unknownFault),
      'PUBLIC_INSTRUMENTATION_V2_RECORDED_SCRIPT_MISMATCH',
    );

    const click = clone(recordedEvents()[3]);
    assert.ok(click);
    (click.parameters[5] as { value: string }).value = 'sendBeacon';
    assertClosedFailure(
      () => validatePublicEventInstrumentationEnvelopeV2(click),
      'PUBLIC_INSTRUMENTATION_V2_EVENT_PARAMETER_INVALID',
    );
  });

  it('rejects accessors, symbols, cycles, subclasses, and unreadable structures', () => {
    const accessor = clone(recordedEvents()[0]) as unknown as Record<string, unknown>;
    Object.defineProperty(accessor, 'canary', {
      enumerable: true,
      get: () => CANARY,
    });
    assertClosedFailure(() => validatePublicEventInstrumentationEnvelopeV2(accessor));

    const symbol = clone(recordedEvents()[0]) as unknown as Record<PropertyKey, unknown>;
    symbol[Symbol(CANARY)] = CANARY;
    assertClosedFailure(() => validatePublicEventInstrumentationEnvelopeV2(symbol));

    const cycle = clone(recordedEvents()[0]) as unknown as Record<string, unknown>;
    cycle.cycle = cycle;
    assertClosedFailure(() => validatePublicEventInstrumentationEnvelopeV2(cycle));

    class EventSubclass {
      catalogId = 'EVT-001';
    }
    assertClosedFailure(() => validatePublicEventInstrumentationEnvelopeV2(new EventSubclass()));

    const source = recordedEvents()[0];
    assert.ok(source);
    const unreadable = new Proxy(clone(source), {
      ownKeys() {
        throw new Error(CANARY);
      },
    });
    assertClosedFailure(() => validatePublicEventInstrumentationEnvelopeV2(unreadable));
  });
});

describe('ST-1202 V2 idempotency and safe failure isolation', () => {
  it('rejects a changed body for an accepted event ID', () => {
    const recorder = createRecordedPublicEventInstrumentationV2(recordedFixture());
    const first = recordedEvents()[0];
    assert.ok(first);
    recorder.record(first);
    const changed = clone(first);
    (changed.parameters[4] as { value: string }).value = 'synthetic_other';
    assertClosedFailure(
      () => recorder.record(changed),
      'PUBLIC_INSTRUMENTATION_V2_EVENT_ID_CONFLICT',
    );
  });

  it('rejects out-of-order events without consuming the expected step', () => {
    const recorder = createRecordedPublicEventInstrumentationV2(recordedFixture());
    const events = recordedEvents();
    assert.ok(events[0]);
    assert.ok(events[1]);
    assertClosedFailure(
      () => recorder.record(events[1]!),
      'PUBLIC_INSTRUMENTATION_V2_RECORDED_SCRIPT_MISMATCH',
    );
    assert.equal(recorder.record(events[0]!).disposition, 'RECORDED_ACCEPTED');
  });

  it('swallows malformed event failure without reflecting input or blocking navigation', () => {
    const recorder = createRecordedPublicEventInstrumentationV2(recordedFixture());
    const malformed = { canary: CANARY } as unknown as PublicEventInstrumentationEnvelopeV2;
    const result = recorder.recordSafely(malformed);
    assert.equal(result.eventIdentity, null);
    assert.equal(result.disposition, 'DROPPED_LOCAL_FAILURE');
    assert.equal(result.failureReason, 'RECORDED_FAILURE_SWALLOWED');
    assert.equal(result.navigationBlocked, false);
    assert.equal(result.navigationAwaitedInstrumentation, false);
    assert.doesNotMatch(JSON.stringify(result), new RegExp(CANARY));
  });
});
