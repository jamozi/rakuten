import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PublicEventInstrumentationError,
  createPublicEventInstrumentationCandidate,
  validatePublicEventInstrumentationCandidate,
} from '../../packages/web-ui/src/public-event-instrumentation.ts';

const HASH = '0123456789abcdef'.repeat(4);
const CANARY = 'ST1202_REJECTED_CANARY_DO_NOT_ECHO';

function input(): Record<string, unknown> {
  return {
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: {
      kind: 'SYNTHETIC_ST1202_INSTRUMENTATION_REQUIREMENTS_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    },
  };
}

function candidate(): Record<string, unknown> {
  return JSON.parse(
    JSON.stringify(createPublicEventInstrumentationCandidate(input() as never)),
  ) as Record<string, unknown>;
}

function assertClosedFailure(run: () => unknown): PublicEventInstrumentationError {
  let observed: unknown;
  try {
    run();
  } catch (error) {
    observed = error;
  }
  assert.ok(observed instanceof PublicEventInstrumentationError);
  assert.doesNotMatch(`${observed.message} ${observed.stack ?? ''}`, new RegExp(CANARY));
  return observed;
}

describe('ST-1202 instrumentation negative boundaries', () => {
  it('rejects malformed, mismatched, and non-lowercase hash coordinates', () => {
    const malformed = input();
    (malformed.coordinate as Record<string, unknown>).expectedSha256 = CANARY;
    assert.equal(
      assertClosedFailure(() => createPublicEventInstrumentationCandidate(malformed as never)).code,
      'PUBLIC_EVENT_INSTRUMENTATION_HASH_INVALID',
    );

    const mismatch = input();
    (mismatch.coordinate as Record<string, unknown>).observedSha256 = 'b'.repeat(64);
    assert.equal(
      assertClosedFailure(() => createPublicEventInstrumentationCandidate(mismatch as never)).code,
      'PUBLIC_EVENT_INSTRUMENTATION_HASH_MISMATCH',
    );
  });

  it('rejects all attempts to inject IDs, time, consent, thresholds, values, or transport', () => {
    for (const key of [
      'eventId',
      'occurredAt',
      'receivedAt',
      'articleId',
      'snapshotId',
      'ctaId',
      'offerId',
      'sessionPseudonym',
      'consentState',
      'visibilityThreshold',
      'engagementThreshold',
      'transport',
      'payload',
    ]) {
      const value = input();
      value[key] = CANARY;
      assert.equal(
        assertClosedFailure(() => createPublicEventInstrumentationCandidate(value as never)).code,
        'PUBLIC_EVENT_INSTRUMENTATION_INPUT_INVALID',
      );
    }
  });

  it('rejects runtime, privacy, event, and authority escalation in candidates', () => {
    const mutations: Array<(value: Record<string, unknown>) => void> = [
      (value) => {
        (value.privacy as Record<string, unknown>).consentState = 'GRANTED';
      },
      (value) => {
        (value.navigation as Record<string, unknown>).beaconExecuted = true;
      },
      (value) => {
        (
          (value.eventRequirements as Array<Record<string, unknown>>)[0].trigger as Record<
            string,
            unknown
          >
        ).value = CANARY;
      },
      (value) => {
        (value.events as unknown[]).push({ eventId: CANARY });
      },
      (value) => {
        (value.actions as unknown[]).push('navigate');
      },
      (value) => {
        (value.authorization as Record<string, unknown>).production = true;
      },
    ];
    for (const mutate of mutations) {
      const value = candidate();
      mutate(value);
      assertClosedFailure(() => validatePublicEventInstrumentationCandidate(value));
    }
  });

  it('rejects accessors, symbols, cycles, subclasses, and unreadable structures', () => {
    const accessor = input();
    Object.defineProperty(accessor, 'eventId', {
      enumerable: true,
      get: () => CANARY,
    });
    assertClosedFailure(() => createPublicEventInstrumentationCandidate(accessor as never));

    const symbol = input();
    symbol[Symbol(CANARY) as never] = CANARY;
    assertClosedFailure(() => createPublicEventInstrumentationCandidate(symbol as never));

    const cycle = input();
    cycle.cycle = cycle;
    assertClosedFailure(() => createPublicEventInstrumentationCandidate(cycle as never));

    class InputSubclass {
      screenId = 'PUB-003';
      route = '/articles/{slug}';
      coordinate = input().coordinate as object;
    }
    assertClosedFailure(() =>
      createPublicEventInstrumentationCandidate(new InputSubclass() as never),
    );

    const unreadable = new Proxy(input(), {
      ownKeys() {
        throw new Error(CANARY);
      },
    });
    assertClosedFailure(() => createPublicEventInstrumentationCandidate(unreadable as never));
  });
});
