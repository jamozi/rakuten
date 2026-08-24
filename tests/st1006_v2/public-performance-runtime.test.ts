import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  PUBLIC_PERFORMANCE_RECORDED_BUDGET_INPUT_V2,
  PUBLIC_PERFORMANCE_RUNTIME_V2_CLASSIFICATION,
  createRecordedPublicPerformanceRuntimeV2,
  evaluatePublicPerformanceBudgetV2,
  validatePublicPerformanceRuntimeV2,
} from '../../packages/web-ui/src/index.ts';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const generated = JSON.parse(
  readFileSync(
    resolve(root, 'changes/st-1006/generated/public-performance-recorded.v2.json'),
    'utf8',
  ),
) as unknown;

function assertDeepFrozen(value: unknown, seen = new Set<object>()): void {
  if (value === null || typeof value !== 'object' || seen.has(value)) return;
  seen.add(value);
  assert.ok(Object.isFrozen(value));
  for (const child of Object.values(value)) assertDeepFrozen(child, seen);
}

describe('ST-1006 V2 deterministic performance runtime', () => {
  it('matches the owner-generated recorded runtime and remains detached/frozen', () => {
    const first = createRecordedPublicPerformanceRuntimeV2();
    const second = createRecordedPublicPerformanceRuntimeV2();
    assert.deepEqual(first, generated);
    assert.deepEqual(validatePublicPerformanceRuntimeV2(generated), first);
    assert.notEqual(first, second);
    assertDeepFrozen(first);
    assert.equal(first.classification, PUBLIC_PERFORMANCE_RUNTIME_V2_CLASSIFICATION);
  });

  it('evaluates canonical targets with deterministic nearest-rank p75 only', () => {
    const assessment = evaluatePublicPerformanceBudgetV2(
      PUBLIC_PERFORMANCE_RECORDED_BUDGET_INPUT_V2,
    );
    assert.equal(assessment.state, 'RECORDED_SYNTHETIC_PASS');
    assert.deepEqual(
      assessment.results.map(({ metric, threshold, recordedSyntheticValue, state }) => ({
        metric,
        threshold,
        recordedSyntheticValue,
        state,
      })),
      [
        {
          metric: 'LCP',
          threshold: 2500,
          recordedSyntheticValue: 2100,
          state: 'RECORDED_SYNTHETIC_PASS',
        },
        {
          metric: 'INP',
          threshold: 200,
          recordedSyntheticValue: 160,
          state: 'RECORDED_SYNTHETIC_PASS',
        },
        {
          metric: 'CLS',
          threshold: 0.1,
          recordedSyntheticValue: 0.05,
          state: 'RECORDED_SYNTHETIC_PASS',
        },
      ],
    );
    assert.equal(assessment.browserObserved, false);
    assert.equal(assessment.fieldMeasurement, false);
    assert.equal(assessment.formalEvidence, false);
  });

  it('returns a recorded failure instead of converting an over-budget sample to success', () => {
    const assessment = evaluatePublicPerformanceBudgetV2({
      ...PUBLIC_PERFORMANCE_RECORDED_BUDGET_INPUT_V2,
      samples: {
        ...PUBLIC_PERFORMANCE_RECORDED_BUDGET_INPUT_V2.samples,
        LCP: [2501, 2600, 2700, 2800],
      },
    });
    assert.equal(assessment.state, 'RECORDED_SYNTHETIC_FAIL');
    assert.equal(assessment.results[0]?.metric, 'LCP');
    assert.equal(assessment.results[0]?.recordedSyntheticValue, 2700);
    assert.equal(assessment.results[0]?.state, 'RECORDED_SYNTHETIC_FAIL');
    assert.equal(assessment.formalEvidence, false);
  });

  it('never promotes synthetic evaluation to browser, field, or formal evidence', () => {
    const runtime = createRecordedPublicPerformanceRuntimeV2();
    assert.equal(runtime.performanceBudgets.browserLabAssessment, 'NOT_EXECUTED');
    assert.equal(runtime.performanceBudgets.fieldAssessment, 'NOT_EXECUTED');
    assert.equal(runtime.performanceBudgets.formalTst027, 'NOT_EXECUTED');
    assert.equal(runtime.authority.browserLab, 'NOT_EXECUTED');
    assert.equal(runtime.authority.fieldRum, 'NOT_EXECUTED');
    assert.equal(runtime.authority.formalTst027, 'NOT_EXECUTED');
    assert.ok(
      Object.entries(runtime.authority)
        .filter(([, value]) => typeof value === 'boolean')
        .every(([, value]) => value === false),
    );
  });

  it('binds the inherited local route without changing its cache or content', () => {
    const runtime = createRecordedPublicPerformanceRuntimeV2();
    assert.deepEqual(runtime.routeBoundary, {
      screenId: 'PUB-003',
      routeTemplate: '/articles/{slug}',
      exactLocalPath: '/articles/synthetic-recorded-policy-seo',
      localRouteRegistered: true,
      sourceProjectionRouteActivated: false,
      publicReadServed: false,
      currentRouteImageCount: 0,
      currentRouteAffiliateCtaRendered: false,
    });
    assert.equal(runtime.cacheBoundary.currentRouteCacheControl, 'no-store');
    assert.equal(runtime.cacheBoundary.currentRouteCacheMutationApplied, false);
    assert.equal(runtime.cacheBoundary.publicCacheStrategySelected, false);
  });
});
