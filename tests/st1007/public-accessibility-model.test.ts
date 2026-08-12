import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  createPublicAccessibilityAcceptanceCandidate,
  validatePublicAccessibilityAcceptanceCandidate,
} from '../../packages/web-ui/src/public-accessibility-acceptance.ts';

const HASH = '0123456789abcdef'.repeat(4);

function input() {
  return {
    storyId: 'ST-1007' as const,
    coordinate: {
      kind: 'SYNTHETIC_ST1007_ACCESSIBILITY_REQUIREMENTS_FIXTURE' as const,
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

describe('ST-1007 headless accessibility requirements model', () => {
  it('is deterministic, detached, JSON-safe, and deeply frozen', () => {
    const source = input();
    const first = createPublicAccessibilityAcceptanceCandidate(source);
    const second = createPublicAccessibilityAcceptanceCandidate(source);
    assert.deepEqual(first, second);
    assert.notEqual(first, second);
    assert.notEqual(first.coordinate, source.coordinate);
    assert.deepEqual(
      validatePublicAccessibilityAcceptanceCandidate(JSON.parse(JSON.stringify(first))),
      first,
    );
    assertDeepFrozen(first);
  });

  it('maps verification methods only to their required formal suites', () => {
    const assessments = createPublicAccessibilityAcceptanceCandidate(input()).checklistAssessments;
    const byId = new Map(
      assessments.map((assessment) => [assessment.checklistItem.id, assessment]),
    );
    assert.deepEqual(byId.get('A11Y-008')?.requiredSuiteIds, ['TST-023']);
    assert.deepEqual(byId.get('A11Y-015')?.requiredSuiteIds, ['TST-023', 'TST-024']);
    assert.deepEqual(byId.get('A11Y-016')?.requiredSuiteIds, ['TST-024']);
    assert.deepEqual(byId.get('A11Y-030')?.requiredSuiteIds, ['TST-024']);
  });

  it('keeps every checklist assessment unavailable and unverified', () => {
    for (const assessment of createPublicAccessibilityAcceptanceCandidate(input())
      .checklistAssessments) {
      assert.equal(assessment.applicability, 'NOT_EVALUATED');
      assert.equal(assessment.executionStatus, 'NOT_EXECUTED');
      assert.equal(assessment.verificationResult, 'NOT_VERIFIED');
      assert.deepEqual(assessment.evidenceRefs, []);
      assert.equal(assessment.environment, null);
      assert.equal(assessment.evaluator, null);
      assert.equal(assessment.executedAt, null);
    }
  });

  it('records only dependency non-readiness, not accessibility evidence', () => {
    const readiness = createPublicAccessibilityAcceptanceCandidate(input()).dependencyReadiness;
    assert.deepEqual(
      readiness.map((item) => item['storyId']),
      ['ST-1003', 'ST-1004', 'ST-1005'],
    );
    for (const item of readiness) {
      assert.equal(item['domAvailable'], false);
      assert.equal(item['browserAvailable'], false);
      assert.equal(item['acceptanceEvidenceAvailable'], false);
    }
  });
});
