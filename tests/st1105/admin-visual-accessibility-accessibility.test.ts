import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  ADMIN_VISUAL_ACCESSIBILITY_CHECKLIST,
  ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS,
  createAdminVisualAccessibilityCandidate,
} from '../../packages/web-ui/src/index.ts';

describe('ST-1105 accessibility acceptance restraint', () => {
  it('does not convert canonical target rows into applicability or conformance results', () => {
    for (const screenId of ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS) {
      const candidate = createAdminVisualAccessibilityCandidate({ screenId });
      assert.equal(
        candidate.checklistAssessments.length,
        ADMIN_VISUAL_ACCESSIBILITY_CHECKLIST.length,
      );
      assert.equal(
        candidate.checklistAssessments.every(
          ({ applicability, executionStatus, verificationResult }) =>
            applicability === 'NOT_EVALUATED' &&
            executionStatus === 'NOT_EXECUTED' &&
            verificationResult === 'NOT_VERIFIED',
        ),
        true,
      );
    }
  });

  it('does not invent a critical workflow selection from screen membership', () => {
    for (const screenId of ['REV-001', 'PUBA-004', 'FIN-001'] as const) {
      const candidate = createAdminVisualAccessibilityCandidate({ screenId });
      assert.deepEqual(candidate.criticalWorkflowIds, []);
      assert.equal(candidate.criticalWorkflowSelection, 'NOT_EVALUATED');
    }
  });

  it('contains no pass or not-applicable result', () => {
    const serialized = JSON.stringify(
      createAdminVisualAccessibilityCandidate({ screenId: 'FRESH-001' }),
    );
    assert.doesNotMatch(serialized, /"(?:PASS|N\/A|NOT_APPLICABLE)"/);
  });
});
