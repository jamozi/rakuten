import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS,
  createAdminVisualAccessibilityCandidate,
  validateAdminVisualAccessibilityCandidate,
  type AdminVisualAccessibilityInput,
} from '../../packages/web-ui/src/index.ts';

function assertDeepFrozen(value: unknown, visited = new Set<object>()): void {
  if (value === null || typeof value !== 'object' || visited.has(value)) return;
  visited.add(value);
  assert.equal(Object.isFrozen(value), true);
  for (const child of Object.values(value)) assertDeepFrozen(child, visited);
}

describe('ST-1105 headless acceptance model', () => {
  it('is deterministic, detached, JSON-safe, and deeply frozen for every screen', () => {
    for (const screenId of ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS) {
      const input: AdminVisualAccessibilityInput = { screenId };
      const first = createAdminVisualAccessibilityCandidate(input);
      const second = createAdminVisualAccessibilityCandidate(input);

      assert.deepEqual(first, second);
      assert.notEqual(first, second);
      assert.equal(first.selectedScreenId, screenId);
      assert.deepEqual(
        validateAdminVisualAccessibilityCandidate(JSON.parse(JSON.stringify(first))),
        first,
      );
      assertDeepFrozen(first);
    }
  });

  it('keeps scope explicitly incomplete and avoids component or workflow inference', () => {
    const candidate = createAdminVisualAccessibilityCandidate({ screenId: 'EVD-002' });
    assert.equal(candidate.screenScope.completeness, 'INCOMPLETE_DEPENDENCY_EXPOSED_SCREEN_SCOPE');
    assert.equal(candidate.screenScope.applicability, 'NOT_EVALUATED');
    assert.deepEqual(candidate.components, []);
    assert.equal(candidate.componentOwnership, 'NOT_INFERRED');
    assert.deepEqual(candidate.criticalWorkflowIds, []);
    assert.equal(candidate.criticalWorkflowSelection, 'NOT_EVALUATED');
  });

  it('keeps every checklist row unevaluated, unexecuted, and unverified', () => {
    const candidate = createAdminVisualAccessibilityCandidate({ screenId: 'GOV-001' });
    assert.equal(candidate.checklistAssessments.length, 30);
    for (const assessment of candidate.checklistAssessments) {
      assert.equal(assessment.applicability, 'NOT_EVALUATED');
      assert.equal(assessment.executionStatus, 'NOT_EXECUTED');
      assert.equal(assessment.verificationResult, 'NOT_VERIFIED');
    }
  });

  it('keeps the visual baseline unavailable and empty', () => {
    const candidate = createAdminVisualAccessibilityCandidate({ screenId: 'FIN-003' });
    assert.deepEqual(candidate.visualBaseline, {
      availability: 'UNAVAILABLE',
      refs: [],
      results: [],
      screenshots: [],
      profile: null,
      tolerance: null,
      approved: false,
    });
  });
});
