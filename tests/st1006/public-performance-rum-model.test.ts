import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  createPublicPerformanceRumCandidate,
  validatePublicPerformanceRumCandidate,
} from '../../packages/web-ui/src/public-performance-rum.ts';

const HASH = '0123456789abcdef'.repeat(4);

function input() {
  return {
    screenId: 'PUB-003' as const,
    route: '/articles/{slug}' as const,
    coordinate: {
      kind: 'SYNTHETIC_ST1006_PERFORMANCE_REQUIREMENTS_FIXTURE' as const,
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

describe('ST-1006 headless performance and RUM model', () => {
  it('is deterministic, detached, JSON-safe, and deeply frozen', () => {
    const source = input();
    const first = createPublicPerformanceRumCandidate(source);
    const second = createPublicPerformanceRumCandidate(source);
    assert.deepEqual(first, second);
    assert.notEqual(first, second);
    assert.notEqual(first.coordinate, source.coordinate);
    assert.deepEqual(
      validatePublicPerformanceRumCandidate(JSON.parse(JSON.stringify(first))),
      first,
    );
    assertDeepFrozen(first);
  });

  it('retains only fixed optimization requirements and selects no strategy', () => {
    const requirements = createPublicPerformanceRumCandidate(input()).optimizationRequirements;
    assert.equal(requirements.imageDimensionsReservedRequired, true);
    assert.equal(requirements.affiliateOrAnalyticsScriptLayoutShiftAllowed, false);
    assert.equal(requirements.ctaLayoutShiftAllowed, false);
    assert.equal(requirements.cacheStrategy, null);
    assert.equal(requirements.imageOptimizationStrategy, null);
    assert.equal(requirements.ctaLayoutStrategy, null);
    assert.equal(requirements.runtimeApplied, false);
    assert.equal(requirements.cacheEvaluation.state, 'NOT_EVALUATED');
    assert.equal(requirements.ctaLayoutShiftEvaluation.value, null);
  });

  it('pins EVT-012 vocabulary while keeping RUM emission disabled', () => {
    const rum = createPublicPerformanceRumCandidate(input()).rumRequirements;
    assert.equal(rum.eventCatalogId, 'EVT-012');
    assert.equal(rum.eventName, 'web_vital');
    assert.deepEqual(rum.permittedParameters, [
      'article_id',
      'snapshot_id',
      'metric_name',
      'metric_value',
      'rating',
      'navigation_type',
    ]);
    assert.equal(rum.instrumentationImplemented, false);
    assert.equal(rum.collectorConnected, false);
    assert.equal(rum.transport, null);
    assert.equal(rum.provider, null);
    assert.equal(rum.eventEmissionEnabled, false);
  });

  it('preserves OD-012 and infers no consent or tracking authority', () => {
    const privacy = createPublicPerformanceRumCandidate(input()).privacy;
    assert.equal(privacy.decisionId, 'OD-012');
    assert.equal(privacy.decisionStatus, 'HUMAN_DECISION_REQUIRED');
    assert.equal(privacy.blocking, true);
    assert.equal(privacy.safeDefault, 'NONESSENTIAL_TRACKING_DISABLED');
    assert.equal(privacy.firstPartyMinimalEventEligibility, 'NOT_EVALUATED');
    assert.equal(privacy.consentState, 'NOT_EVALUATED');
    assert.equal(privacy.consentInferred, false);
    assert.equal(privacy.eventEmissionAllowed, false);
  });
});
