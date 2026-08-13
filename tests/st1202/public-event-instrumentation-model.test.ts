import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  createPublicEventInstrumentationCandidate,
  validatePublicEventInstrumentationCandidate,
} from '../../packages/web-ui/src/public-event-instrumentation.ts';

const HASH = '0123456789abcdef'.repeat(4);

function input() {
  return {
    screenId: 'PUB-003' as const,
    route: '/articles/{slug}' as const,
    coordinate: {
      kind: 'SYNTHETIC_ST1202_INSTRUMENTATION_REQUIREMENTS_FIXTURE' as const,
      expectedSha256: HASH,
      observedSha256: HASH,
    },
  };
}

function assertDeepFrozen(value: unknown, visited = new Set<object>()): void {
  if (value === null || typeof value !== 'object' || visited.has(value)) return;
  visited.add(value);
  assert.ok(Object.isFrozen(value));
  for (const child of Object.values(value)) assertDeepFrozen(child, visited);
}

describe('ST-1202 disabled instrumentation model', () => {
  it('is deterministic, detached, JSON-safe, and deeply frozen', () => {
    const source = input();
    const first = createPublicEventInstrumentationCandidate(source);
    const second = createPublicEventInstrumentationCandidate(source);
    assert.deepEqual(first, second);
    assert.notEqual(first, second);
    assert.notEqual(first.coordinate, source.coordinate);
    assert.deepEqual(
      validatePublicEventInstrumentationCandidate(JSON.parse(JSON.stringify(first))),
      first,
    );
    assertDeepFrozen(first);
  });

  it('retains exact ordered parameters without selecting any runtime values', () => {
    const requirements = createPublicEventInstrumentationCandidate(input()).eventRequirements;
    assert.deepEqual(
      requirements.map(({ id, parameters }) => [id, parameters]),
      [
        [
          'EVT-001',
          [
            'event_id',
            'occurred_at',
            'anonymous_session_id',
            'article_id',
            'snapshot_id',
            'category_id',
            'referrer_class',
            'consent_state',
          ],
        ],
        ['EVT-002', ['article_id', 'snapshot_id', 'component_type', 'engagement_kind']],
        [
          'EVT-003',
          ['article_id', 'snapshot_id', 'cta_id', 'offer_id', 'placement', 'visibility_threshold'],
        ],
        [
          'EVT-004',
          [
            'article_id',
            'snapshot_id',
            'cta_id',
            'offer_id',
            'placement',
            'beacon_transport',
            'consent_state',
          ],
        ],
        ['EVT-006', ['article_id', 'snapshot_id', 'interaction', 'axis_code']],
        [
          'EVT-012',
          ['article_id', 'snapshot_id', 'metric_name', 'metric_value', 'rating', 'navigation_type'],
        ],
      ],
    );
    for (const requirement of requirements) {
      for (const field of [
        requirement.trigger,
        requirement.identity,
        requirement.eventValues,
        requirement.threshold,
        requirement.transport,
        requirement.collector,
      ]) {
        assert.deepEqual(field, { state: 'NOT_EVALUATED', value: null });
      }
      assert.equal(requirement.instrumentationImplemented, false);
      assert.equal(requirement.emissionEnabled, false);
    }
  });

  it('preserves the inherited OD-012 disabled default without inferring eligibility', () => {
    assert.deepEqual(createPublicEventInstrumentationCandidate(input()).privacy, {
      decisionId: 'OD-012',
      decisionStatus: 'HUMAN_DECISION_REQUIRED',
      blocking: true,
      safeDefault: 'NONESSENTIAL_TRACKING_DISABLED',
      firstPartyMinimalEventEligibility: 'NOT_EVALUATED',
      consentState: 'NOT_EVALUATED',
      consentInferred: false,
      sessionPseudonym: null,
      cookiesUsed: false,
      storageUsed: false,
      fingerprintingUsed: false,
      trackingEnabled: false,
      eventEmissionAllowed: false,
    });
  });

  it('keeps navigation priority declarative without adding out-of-scope events', () => {
    const value = createPublicEventInstrumentationCandidate(input());
    assert.deepEqual(value.navigation, {
      directProviderNavigationRequired: true,
      raosRedirectAllowed: false,
      navigationMustNotWaitForInstrumentation: true,
      collectorFailureMustNotBlockNavigation: true,
      navigationExecuted: false,
      beaconExecuted: false,
      browserVerified: false,
      selectedTransport: null,
    });
    assert.deepEqual(
      value.eventRequirements.map(({ id }) => id),
      ['EVT-001', 'EVT-002', 'EVT-003', 'EVT-004', 'EVT-006', 'EVT-012'],
    );
    assert.equal(Object.hasOwn(value, 'excludedPublicEvent'), false);
  });
});
