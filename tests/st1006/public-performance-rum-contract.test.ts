import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLIC_PERFORMANCE_RUM_CLASSIFICATION,
  PUBLIC_PERFORMANCE_RUM_ERROR_CODES,
  PUBLIC_PERFORMANCE_RUM_METRICS,
  PUBLIC_PERFORMANCE_RUM_SCREEN,
  createPublicPerformanceRumCandidate,
} from '../../packages/web-ui/src/index.ts';

const HASH = 'a'.repeat(64);

function candidate() {
  return createPublicPerformanceRumCandidate({
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: {
      kind: 'SYNTHETIC_ST1006_PERFORMANCE_REQUIREMENTS_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    },
  });
}

describe('ST-1006 disabled performance and RUM contract', () => {
  it('pins only the unregistered PUB-003 requirements boundary', () => {
    assert.equal(PUBLIC_PERFORMANCE_RUM_SCREEN.id, 'PUB-003');
    assert.equal(PUBLIC_PERFORMANCE_RUM_SCREEN.route, '/articles/{slug}');
    assert.equal(candidate().classification, PUBLIC_PERFORMANCE_RUM_CLASSIFICATION);
    assert.equal(
      candidate().classification,
      'UNREGISTERED_DISABLED_HEADLESS_ST1006_PERFORMANCE_RUM_REQUIREMENTS_CANDIDATE',
    );
    assert.deepEqual(candidate().route, {
      template: '/articles/{slug}',
      routeRegistered: false,
      rendererConnected: false,
    });
  });

  it('records the three provisional CWV targets without observed values', () => {
    const targets = candidate().performanceTargets;
    assert.deepEqual(PUBLIC_PERFORMANCE_RUM_METRICS, ['LCP', 'INP', 'CLS']);
    assert.deepEqual(
      targets.map(({ metric, targetThreshold, unit }) => ({ metric, targetThreshold, unit })),
      [
        { metric: 'LCP', targetThreshold: 2500, unit: 'MILLISECONDS' },
        { metric: 'INP', targetThreshold: 200, unit: 'MILLISECONDS' },
        { metric: 'CLS', targetThreshold: 0.1, unit: 'SCORE' },
      ],
    );
    for (const target of targets) {
      assert.equal(target.state, 'PROVISIONAL_TARGET');
      assert.equal(target.percentile, 75);
      assert.equal(target.fieldWindow, 'ROLLING_28_DAYS');
      assert.equal(target.observedValue, null);
      assert.equal(target.observedRating, null);
      assert.equal(target.observationState, 'NOT_EVALUATED');
      assert.equal(target.measurementExecuted, false);
    }
  });

  it('keeps a stable unique closed error vocabulary and frozen metadata', () => {
    assert.equal(PUBLIC_PERFORMANCE_RUM_ERROR_CODES.length, 15);
    assert.equal(new Set(PUBLIC_PERFORMANCE_RUM_ERROR_CODES).size, 15);
    assert.ok(Object.isFrozen(PUBLIC_PERFORMANCE_RUM_SCREEN));
    assert.ok(Object.isFrozen(PUBLIC_PERFORMANCE_RUM_SCREEN.roles));
    assert.ok(Object.isFrozen(PUBLIC_PERFORMANCE_RUM_SCREEN.apiDependencies));
  });
});
