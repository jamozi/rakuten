import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  FRESHNESS_OPERATIONS_SCREEN_IDS,
  createFreshnessOperationsWorkspaceCandidate,
} from '../../packages/web-ui/src/index.ts';

describe('ST-1103 accessibility requirements boundary', () => {
  it('records text, code, and icon status cues without claiming rendered output', () => {
    for (const screenId of FRESHNESS_OPERATIONS_SCREEN_IDS) {
      const candidate = createFreshnessOperationsWorkspaceCandidate({ screenId });

      assert.deepEqual(candidate.accessibility, {
        requirementsOnly: true,
        rendered: false,
        verified: false,
        statusPresentation: {
          textRequired: true,
          codeRequired: true,
          iconRequired: true,
          colorOnly: false,
          rendered: false,
          verified: false,
        },
      });
      assert.equal(candidate.verification.accessibility, 'NOT_VERIFIED');
    }
  });

  it('does not infer components, DOM roles, focus order, or interaction behavior', () => {
    const candidate = createFreshnessOperationsWorkspaceCandidate({ screenId: 'FRESH-003' });
    const serialized = JSON.stringify(candidate);

    assert.deepEqual(candidate.components, []);
    assert.equal(candidate.componentOwnership, 'NOT_INFERRED');
    for (const absent of ['componentId', 'domId', 'focusOrder', 'tabIndex', 'onClick']) {
      assert.equal(serialized.includes(absent), false, absent);
    }
  });
});
