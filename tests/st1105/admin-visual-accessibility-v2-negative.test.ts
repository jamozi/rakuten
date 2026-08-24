import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  ADMIN_VISUAL_ACCESSIBILITY_V2_ERROR_CODES,
  AdminVisualAccessibilityV2Error,
  createAdminVisualAccessibilityV2Candidate,
  validateAdminVisualAccessibilityV2Candidate,
} from '../../packages/web-ui/src/index.ts';
import type { AdminVisualAccessibilityV2Input } from '../../packages/web-ui/src/index.ts';

function expectCode(call: () => unknown, code: string): void {
  assert.throws(call, (error: unknown) => {
    assert.equal(error instanceof AdminVisualAccessibilityV2Error, true);
    assert.equal((error as AdminVisualAccessibilityV2Error).code, code);
    assert.equal((error as Error).message, code);
    return true;
  });
}

describe('ST-1105 V2 hostile input and evidence restraint', () => {
  it('rejects unknown, extra, accessor, prototype, and cyclic input shapes', () => {
    expectCode(
      () => createAdminVisualAccessibilityV2Candidate({ screenId: 'NOPE-999' }),
      'ADMIN_VISUAL_ACCESSIBILITY_V2_SCREEN_UNKNOWN',
    );
    expectCode(
      () =>
        createAdminVisualAccessibilityV2Candidate({
          screenId: 'PORT-001',
          extra: true,
        } as unknown as AdminVisualAccessibilityV2Input),
      'ADMIN_VISUAL_ACCESSIBILITY_V2_INPUT_INVALID',
    );
    const accessor = {} as Record<string, unknown>;
    Object.defineProperty(accessor, 'screenId', { enumerable: true, get: () => 'PORT-001' });
    expectCode(
      () =>
        createAdminVisualAccessibilityV2Candidate(
          accessor as unknown as AdminVisualAccessibilityV2Input,
        ),
      'ADMIN_VISUAL_ACCESSIBILITY_V2_INPUT_INVALID',
    );
    expectCode(
      () =>
        createAdminVisualAccessibilityV2Candidate(
          Object.create({ screenId: 'PORT-001' }) as AdminVisualAccessibilityV2Input,
        ),
      'ADMIN_VISUAL_ACCESSIBILITY_V2_INPUT_INVALID',
    );
    const cyclic: Record<string, unknown> = { screenId: 'PORT-001' };
    cyclic.self = cyclic;
    expectCode(
      () =>
        createAdminVisualAccessibilityV2Candidate(
          cyclic as unknown as AdminVisualAccessibilityV2Input,
        ),
      'ADMIN_VISUAL_ACCESSIBILITY_V2_INPUT_INVALID',
    );
  });

  it('rejects candidate tampering and formal evidence promotion', () => {
    const original = createAdminVisualAccessibilityV2Candidate({ screenId: 'OPS-004' });
    const scopeTampered = structuredClone(original) as unknown as {
      selectedScreen: { component_ids: string[] };
    };
    scopeTampered.selectedScreen.component_ids.push('UI-C046');
    expectCode(
      () => validateAdminVisualAccessibilityV2Candidate(scopeTampered),
      'ADMIN_VISUAL_ACCESSIBILITY_V2_CANDIDATE_INVALID',
    );
    const evidenceTampered = structuredClone(original);
    (evidenceTampered.formalBoundary as unknown as Record<string, unknown>)['TST-023'] = 'PASS';
    expectCode(
      () => validateAdminVisualAccessibilityV2Candidate(evidenceTampered),
      'ADMIN_VISUAL_ACCESSIBILITY_V2_EVIDENCE_BOUNDARY_INVALID',
    );
    const baselineTampered = structuredClone(original);
    (baselineTampered.visualBaseline as unknown as Record<string, unknown>)['approved'] = true;
    expectCode(
      () => validateAdminVisualAccessibilityV2Candidate(baselineTampered),
      'ADMIN_VISUAL_ACCESSIBILITY_V2_EVIDENCE_BOUNDARY_INVALID',
    );
  });

  it('returns deeply frozen deterministic candidates and a closed error vocabulary', () => {
    const first = createAdminVisualAccessibilityV2Candidate({ screenId: 'EVD-002' });
    const second = createAdminVisualAccessibilityV2Candidate({ screenId: 'EVD-002' });
    assert.deepEqual(first, second);
    assert.equal(Object.isFrozen(first), true);
    assert.equal(Object.isFrozen(first.selectedScreen), true);
    assert.equal(Object.isFrozen(first.checklistAssessments), true);
    assert.equal(
      new Set(ADMIN_VISUAL_ACCESSIBILITY_V2_ERROR_CODES).size,
      ADMIN_VISUAL_ACCESSIBILITY_V2_ERROR_CODES.length,
    );
    assert.doesNotMatch(JSON.stringify(first.formalBoundary), /"PASS"/u);
  });
});
