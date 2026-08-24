import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLIC_EVENT_INSTRUMENTATION_CLASSIFICATION_V2,
  PUBLIC_EVENT_INSTRUMENTATION_EVENT_IDS_V2,
  createDisabledPublicEventInstrumentationRouteBoundaryV2,
  createRecordedPublicEventInstrumentationV2,
  validatePublicEventInstrumentationRecordedFixtureV2,
} from '../../packages/web-ui/src/index.ts';

import { recordedEvents, recordedFixture } from './fixture.ts';

function assertDeepFrozen(value: unknown, visited = new Set<object>()): void {
  if (value === null || typeof value !== 'object' || visited.has(value)) return;
  visited.add(value);
  assert.ok(Object.isFrozen(value));
  for (const child of Object.values(value)) assertDeepFrozen(child, visited);
}

describe('ST-1202 V2 actual route boundary', () => {
  it('executes the exact article route boundary with all collection disabled', () => {
    const boundary = createDisabledPublicEventInstrumentationRouteBoundaryV2({
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
    });
    assert.equal(boundary.classification, PUBLIC_EVENT_INSTRUMENTATION_CLASSIFICATION_V2);
    assert.equal(boundary.mode, 'DISABLED_OD_012');
    assert.equal(boundary.serverBoundaryEvaluated, true);
    assert.equal(boundary.clientInstrumentationInstalled, false);
    assert.equal(boundary.identityAvailable, false);
    assert.equal(boundary.affiliateCtaAvailable, false);
    assert.deepEqual(boundary.eligibleEventIds, []);
    assert.deepEqual(boundary.blockedEventIds, PUBLIC_EVENT_INSTRUMENTATION_EVENT_IDS_V2);
    assert.deepEqual(boundary.events, []);
    assert.deepEqual(boundary.effects, []);
    assert.equal(boundary.trackingEnabled, false);
    assert.equal(boundary.measurementObserved, false);
    assertDeepFrozen(boundary);
  });
});

describe('ST-1202 V2 recorded process-local instrumentation', () => {
  it('validates the exact six-event view/engagement/CTA/comparison/RUM fixture', () => {
    const fixture = validatePublicEventInstrumentationRecordedFixtureV2(recordedFixture());
    assert.deepEqual(
      fixture.events.map(({ catalogId, eventName }) => ({ catalogId, eventName })),
      [
        { catalogId: 'EVT-001', eventName: 'article_view' },
        { catalogId: 'EVT-002', eventName: 'qualified_decision_engagement' },
        { catalogId: 'EVT-003', eventName: 'affiliate_cta_impression' },
        { catalogId: 'EVT-004', eventName: 'affiliate_click' },
        { catalogId: 'EVT-006', eventName: 'comparison_interaction' },
        { catalogId: 'EVT-012', eventName: 'web_vital' },
      ],
    );
    assert.equal(fixture.consent.authority, 'UNRESOLVED_OD_012');
    assert.equal(fixture.consent.trackingActivation, 'DISABLED');
    assertDeepFrozen(fixture);
  });

  it('accepts the exact script without tracking, persistence, network, or measurement claims', () => {
    const recorder = createRecordedPublicEventInstrumentationV2(recordedFixture());
    for (const event of recordedEvents()) {
      const result = recorder.record(event);
      assert.equal(result.disposition, 'RECORDED_ACCEPTED');
      assert.equal(result.trackingActivation, 'DISABLED');
      assert.equal(result.persistence, 'NOT_EXECUTED');
      assert.equal(result.measurementObserved, false);
      assert.equal(result.networkUsed, false);
      assert.equal(result.navigationBlocked, false);
      assert.equal(result.navigationAwaitedInstrumentation, false);
      assert.equal(result.TST022, 'NOT_EXECUTED');
      assert.equal(result.TST030, 'NOT_EXECUTED');
      assertDeepFrozen(result);
    }
    assert.deepEqual(recorder.snapshot(), {
      mode: 'RECORDED_TEST_ONLY',
      scriptLength: 6,
      nextIndex: 6,
      remaining: 0,
      acceptedCount: 6,
      duplicateCount: 0,
      swallowedFailureCount: 0,
      complete: true,
      trackingActivation: 'DISABLED',
      persistence: 'NOT_EXECUTED',
      measurementObserved: false,
    });
  });

  it('deduplicates an identical event ID and canonical body process-locally', () => {
    const recorder = createRecordedPublicEventInstrumentationV2(recordedFixture());
    const first = recordedEvents()[0];
    assert.ok(first);
    assert.equal(recorder.record(first).disposition, 'RECORDED_ACCEPTED');
    assert.equal(recorder.record(first).disposition, 'RECORDED_DUPLICATE');
    assert.deepEqual(recorder.snapshot(), {
      mode: 'RECORDED_TEST_ONLY',
      scriptLength: 6,
      nextIndex: 1,
      remaining: 5,
      acceptedCount: 1,
      duplicateCount: 1,
      swallowedFailureCount: 0,
      complete: false,
      trackingActivation: 'DISABLED',
      persistence: 'NOT_EXECUTED',
      measurementObserved: false,
    });
  });

  it('swallows a recorded click failure and keeps direct navigation independent', () => {
    const fixture = recordedFixture();
    const click = fixture.events[3];
    assert.ok(click);
    const recorder = createRecordedPublicEventInstrumentationV2({
      ...fixture,
      faultEventIds: [click.eventId],
    });
    for (const event of fixture.events.slice(0, 3)) recorder.record(event);
    const result = recorder.recordSafely(click);
    assert.equal(result.disposition, 'DROPPED_LOCAL_FAILURE');
    assert.equal(result.failureReason, 'RECORDED_FAILURE_SWALLOWED');
    assert.equal(result.navigationBlocked, false);
    assert.equal(result.navigationAwaitedInstrumentation, false);
    assert.equal(result.networkUsed, false);
    assert.deepEqual(recorder.snapshot(), {
      mode: 'RECORDED_TEST_ONLY',
      scriptLength: 6,
      nextIndex: 3,
      remaining: 3,
      acceptedCount: 3,
      duplicateCount: 0,
      swallowedFailureCount: 1,
      complete: false,
      trackingActivation: 'DISABLED',
      persistence: 'NOT_EXECUTED',
      measurementObserved: false,
    });
  });
});
