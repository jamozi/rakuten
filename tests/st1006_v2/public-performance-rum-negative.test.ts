import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLIC_PERFORMANCE_RECORDED_BUDGET_INPUT_V2,
  PublicPerformanceV2Error,
  createDefaultDisabledPublicRumHookV2,
  evaluatePublicPerformanceBudgetV2,
  validatePublicPerformanceRuntimeV2,
  createRecordedPublicPerformanceRuntimeV2,
  type PublicPerformanceV2ErrorCode,
} from '../../packages/web-ui/src/public-performance-runtime-v2.ts';

function expectCode(operation: () => unknown, code: PublicPerformanceV2ErrorCode): void {
  try {
    operation();
  } catch (error) {
    assert.ok(error instanceof PublicPerformanceV2Error);
    assert.equal(error.code, code);
    assert.equal(error.message, code);
    assert.ok(Object.isFrozen(error));
    return;
  }
  assert.fail('expected ST-1006 V2 operation to fail');
}

describe('ST-1006 V2 RUM/privacy and hostile-input boundary', () => {
  it('drops candidates while disabled without inspecting hostile input', () => {
    const hook = createDefaultDisabledPublicRumHookV2();
    let getterCalled = false;
    const hostile = Object.defineProperty({}, 'article_body', {
      enumerable: true,
      get() {
        getterCalled = true;
        throw new TypeError('sensitive-canary');
      },
    });
    const proxy = new Proxy(
      {},
      {
        ownKeys() {
          throw new TypeError('sensitive-proxy-canary');
        },
      },
    );
    for (const candidate of [hostile, proxy, 'secret-canary', null]) {
      assert.deepEqual(hook.capture(candidate), {
        status: 'DROPPED_DISABLED',
        reason: 'OD_012_NONESSENTIAL_TRACKING_DISABLED',
        inputInspected: false,
        captured: false,
        transported: false,
        persisted: false,
      });
    }
    assert.equal(getterCalled, false);
    assert.deepEqual(hook.snapshot(), []);
    assert.equal(hook.enabled, false);
    assert.equal(hook.mode, 'DISABLED_OD_012');
    assert.ok(Object.isFrozen(hook));
  });

  it('rejects non-synthetic, observed, unknown and malformed budget input', () => {
    const base = structuredClone(PUBLIC_PERFORMANCE_RECORDED_BUDGET_INPUT_V2);
    for (const [mutation, code] of [
      [{ provenance: 'FIELD_RUM' }, 'PUBLIC_PERFORMANCE_V2_BUDGET_INVALID'],
      [{ formalEvidence: true }, 'PUBLIC_PERFORMANCE_V2_BUDGET_INVALID'],
      [{ browserObserved: true }, 'PUBLIC_PERFORMANCE_V2_BUDGET_INVALID'],
      [{ capturedEvents: [] }, 'PUBLIC_PERFORMANCE_V2_BUDGET_INVALID'],
    ] as const) {
      expectCode(() => evaluatePublicPerformanceBudgetV2({ ...base, ...mutation } as never), code);
    }
    expectCode(
      () =>
        evaluatePublicPerformanceBudgetV2({
          ...base,
          samples: { ...base.samples, LCP: [Number.NaN] },
        }),
      'PUBLIC_PERFORMANCE_V2_INPUT_INVALID',
    );
    expectCode(
      () =>
        evaluatePublicPerformanceBudgetV2({
          ...base,
          samples: { ...base.samples, CLS: [] },
        }),
      'PUBLIC_PERFORMANCE_V2_BUDGET_INVALID',
    );
  });

  it('rejects accessors, symbols, cycles and runtime authority escalation', () => {
    let getterCalled = false;
    const accessor = structuredClone(PUBLIC_PERFORMANCE_RECORDED_BUDGET_INPUT_V2);
    Object.defineProperty(accessor, 'samples', {
      enumerable: true,
      get() {
        getterCalled = true;
        return {};
      },
    });
    const symbolic = structuredClone(PUBLIC_PERFORMANCE_RECORDED_BUDGET_INPUT_V2) as Record<
      PropertyKey,
      unknown
    >;
    symbolic[Symbol('hidden')] = true;
    const cyclic = structuredClone(PUBLIC_PERFORMANCE_RECORDED_BUDGET_INPUT_V2) as Record<
      string,
      unknown
    >;
    cyclic['cycle'] = cyclic;
    for (const value of [accessor, symbolic, cyclic]) {
      expectCode(
        () => evaluatePublicPerformanceBudgetV2(value as never),
        'PUBLIC_PERFORMANCE_V2_INPUT_INVALID',
      );
    }
    assert.equal(getterCalled, false);

    const runtime = structuredClone(createRecordedPublicPerformanceRuntimeV2()) as Record<
      string,
      Record<string, unknown>
    >;
    runtime['authority']!['trackingAuthorized'] = true;
    expectCode(
      () => validatePublicPerformanceRuntimeV2(runtime),
      'PUBLIC_PERFORMANCE_V2_RUNTIME_INVALID',
    );
  });
});
