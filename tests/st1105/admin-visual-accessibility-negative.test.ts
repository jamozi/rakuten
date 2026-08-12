import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  AdminVisualAccessibilityError,
  createAdminVisualAccessibilityCandidate,
  validateAdminVisualAccessibilityCandidate,
  type AdminVisualAccessibilityErrorCode,
  type AdminVisualAccessibilityInput,
} from '../../packages/web-ui/src/index.ts';

function expectCode(operation: () => unknown, code: AdminVisualAccessibilityErrorCode): void {
  assert.throws(
    operation,
    (error: unknown) =>
      error instanceof AdminVisualAccessibilityError &&
      error.code === code &&
      error.message === code &&
      Object.isFrozen(error),
  );
}

function mutableCandidate(): Record<string, unknown> {
  return JSON.parse(
    JSON.stringify(createAdminVisualAccessibilityCandidate({ screenId: 'PORT-001' })),
  ) as Record<string, unknown>;
}

describe('ST-1105 strict closed negative boundary', () => {
  it('accepts only the exact {screenId} shape and closed screen vocabulary', () => {
    for (const input of [
      null,
      {},
      [],
      { screenId: 1 },
      { screenId: 'PORT-001', role: 'EDITOR' },
      { storyId: 'ST-1105', screenId: 'PORT-001' },
    ]) {
      expectCode(
        () => createAdminVisualAccessibilityCandidate(input as AdminVisualAccessibilityInput),
        'ADMIN_VISUAL_ACCESSIBILITY_INPUT_INVALID',
      );
    }
    expectCode(
      () =>
        createAdminVisualAccessibilityCandidate({
          screenId: 'PORT-999',
        } as unknown as AdminVisualAccessibilityInput),
      'ADMIN_VISUAL_ACCESSIBILITY_SCREEN_UNKNOWN',
    );
  });

  it('rejects subclasses, accessors, symbols, cycles, callbacks, and unreadable proxies', () => {
    class InputSubclass {
      screenId = 'PORT-001';
    }
    let getterCalled = false;
    const accessor = {} as Record<string, unknown>;
    Object.defineProperty(accessor, 'screenId', {
      enumerable: true,
      get() {
        getterCalled = true;
        return 'PORT-001';
      },
    });
    const symbol = { screenId: 'PORT-001', [Symbol('hidden')]: true };
    const cycle: Record<string, unknown> = { screenId: 'PORT-001' };
    cycle['cycle'] = cycle;
    const callback = { screenId: 'PORT-001', onSelect: () => undefined };
    const throwing = new Proxy(
      { screenId: 'PORT-001' },
      {
        ownKeys() {
          throw new TypeError('untrusted-value');
        },
      },
    );

    for (const input of [new InputSubclass(), accessor, symbol, cycle, callback, throwing]) {
      expectCode(
        () => createAdminVisualAccessibilityCandidate(input as AdminVisualAccessibilityInput),
        'ADMIN_VISUAL_ACCESSIBILITY_INPUT_INVALID',
      );
    }
    assert.equal(getterCalled, false);
  });

  it('rejects scope, checklist, suite, and baseline escalation with closed non-echoing codes', () => {
    const scope = mutableCandidate();
    scope['criticalWorkflowIds'] = ['UI-WF-006'];
    expectCode(
      () => validateAdminVisualAccessibilityCandidate(scope),
      'ADMIN_VISUAL_ACCESSIBILITY_SCOPE_INVALID',
    );

    const checklist = mutableCandidate();
    const assessments = checklist['checklistAssessments'] as Record<string, unknown>[];
    assessments[0]!['verificationResult'] = 'PASS';
    expectCode(
      () => validateAdminVisualAccessibilityCandidate(checklist),
      'ADMIN_VISUAL_ACCESSIBILITY_CHECKLIST_INVALID',
    );

    const suite = mutableCandidate();
    const suites = suite['suites'] as Record<string, unknown>[];
    suites[0]!['executionStatus'] = 'PASS';
    expectCode(
      () => validateAdminVisualAccessibilityCandidate(suite),
      'ADMIN_VISUAL_ACCESSIBILITY_SUITE_INVALID',
    );

    const baseline = mutableCandidate();
    (baseline['visualBaseline'] as Record<string, unknown>)['approved'] = true;
    expectCode(
      () => validateAdminVisualAccessibilityCandidate(baseline),
      'ADMIN_VISUAL_ACCESSIBILITY_BASELINE_INVALID',
    );
  });

  it('rejects unknown fields and hostile complete-candidate shapes without echoing values', () => {
    const unknown = mutableCandidate();
    unknown['evidence'] = 'sensitive-canary';
    expectCode(
      () => validateAdminVisualAccessibilityCandidate(unknown),
      'ADMIN_VISUAL_ACCESSIBILITY_CANDIDATE_INVALID',
    );

    const candidate = mutableCandidate();
    Object.defineProperty(candidate, 'storyId', {
      enumerable: true,
      get() {
        throw new TypeError('sensitive-canary');
      },
    });
    expectCode(
      () => validateAdminVisualAccessibilityCandidate(candidate),
      'ADMIN_VISUAL_ACCESSIBILITY_CANDIDATE_INVALID',
    );
  });
});
