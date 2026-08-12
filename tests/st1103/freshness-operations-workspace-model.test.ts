import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  FRESHNESS_OPERATIONS_SCREEN_IDS,
  createFreshnessOperationsWorkspaceCandidate,
  validateFreshnessOperationsWorkspaceCandidate,
} from '../../packages/web-ui/src/index.ts';

function assertDeepFrozen(value: unknown, seen = new WeakSet<object>()): void {
  if (value === null || typeof value !== 'object' || seen.has(value)) {
    return;
  }
  seen.add(value);
  assert.equal(Object.isFrozen(value), true);
  for (const item of Object.values(value)) {
    assertDeepFrozen(item, seen);
  }
}

describe('ST-1103 headless freshness and operations workspace model', () => {
  it('is deterministic, detached, deeply frozen, and JSON-safe for every screen', () => {
    for (const screenId of FRESHNESS_OPERATIONS_SCREEN_IDS) {
      const first = createFreshnessOperationsWorkspaceCandidate({ screenId });
      const second = createFreshnessOperationsWorkspaceCandidate({ screenId });

      assert.deepEqual(first, second);
      assert.notStrictEqual(first, second);
      assert.notStrictEqual(first.screen, second.screen);
      assert.doesNotThrow(() => JSON.stringify(first));
      assert.deepEqual(JSON.parse(JSON.stringify(first)), first);
      assertDeepFrozen(first);
      assert.deepEqual(validateFreshnessOperationsWorkspaceCandidate(first), first);
    }
  });

  it('keeps all data unavailable without inventing payloads', () => {
    const candidate = createFreshnessOperationsWorkspaceCandidate({ screenId: 'FRESH-001' });

    assert.deepEqual(candidate.dataSlots, {
      primary: { status: 'NOT_LOADED', payload: null },
      status: { status: 'NOT_EVALUATED', payload: null },
      items: { status: 'NOT_LOADED', payload: [] },
      evidence: { status: 'NOT_EVALUATED', payload: [] },
    });
  });

  it('accepts exactly one caller coordinate and never a role or route coordinate', () => {
    const candidate = createFreshnessOperationsWorkspaceCandidate({ screenId: 'OPS-001' });

    assert.equal(candidate.screen.id, 'OPS-001');
    assert.equal(candidate.roleInputAccepted, false);
    assert.equal(
      candidate.roleMetadataAuthority,
      'DISPLAY_ONLY_NOT_AUTHENTICATION_OR_AUTHORIZATION',
    );
    assert.equal(candidate.routeRegistered, false);
    assert.equal(candidate.renderEnabled, false);
  });
});
