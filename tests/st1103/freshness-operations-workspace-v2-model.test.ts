import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  FRESHNESS_OPERATIONS_SCREEN_IDS,
  FRESHNESS_OPERATIONS_WORKSPACE_V2_CLASSIFICATION,
  createFreshnessOperationsWorkspaceV2,
  validateFreshnessOperationsWorkspaceV2,
} from '../../packages/web-ui/src/index.ts';

function assertDeepFrozen(value: unknown, seen = new WeakSet<object>()): void {
  if (value === null || typeof value !== 'object' || seen.has(value)) {
    return;
  }
  seen.add(value);
  assert.equal(Object.isFrozen(value), true);
  for (const child of Object.values(value)) {
    assertDeepFrozen(child, seen);
  }
}

describe('ST-1103 V2 recorded workspace model', () => {
  it('builds all eight deterministic, detached, deeply frozen screen models', () => {
    for (const screenId of FRESHNESS_OPERATIONS_SCREEN_IDS) {
      const first = createFreshnessOperationsWorkspaceV2({ screenId });
      const second = createFreshnessOperationsWorkspaceV2({ screenId });

      assert.equal(first.classification, FRESHNESS_OPERATIONS_WORKSPACE_V2_CLASSIFICATION);
      assert.equal(first.localStatus, 'LOCAL_IMPLEMENTATION_COMPLETE');
      assert.equal(first.screen.id, screenId);
      assert.deepEqual(first, second);
      assert.notStrictEqual(first, second);
      assert.notStrictEqual(first.projection, second.projection);
      assert.deepEqual(validateFreshnessOperationsWorkspaceV2(first), first);
      assertDeepFrozen(first);
    }
  });

  it('projects exact ST-1401 freshness states without treating unknown as zero', () => {
    const model = createFreshnessOperationsWorkspaceV2({ screenId: 'FRESH-001' });

    assert.equal(model.projection.dataStatus, 'AVAILABLE_RECORDED');
    assert.equal(model.projection.table.rows.length, 2);
    assert.deepEqual(
      model.projection.table.rows.map((row) => row['state']),
      ['CRITICAL', 'UNKNOWN'],
    );
    assert.equal(model.projection.unknownAsZeroAllowed, false);
    assert.equal(model.projection.rawPayloadPresent, false);
    assert.equal(model.projection.table.emptyState, null);
  });

  it('projects recorded ST-1404 job and quarantine metadata with no durability claim', () => {
    const jobs = createFreshnessOperationsWorkspaceV2({ screenId: 'OPS-001' });
    const quarantine = createFreshnessOperationsWorkspaceV2({ screenId: 'OPS-002' });

    assert.deepEqual(
      jobs.projection.table.rows.map((row) => row['state']),
      ['QUEUED', 'RUNNING', 'RETRY_SCHEDULED', 'QUARANTINED'],
    );
    assert.equal(quarantine.projection.table.rows.length, 1);
    assert.equal(quarantine.projection.table.rows[0]?.['state'], 'QUARANTINED');
    assert.equal(jobs.authority.retryEnabled, false);
    assert.equal(jobs.authority.persistenceEnabled, false);
  });

  it('keeps undeclared screen dependencies explicitly unavailable rather than empty', () => {
    for (const screenId of ['FRESH-002', 'FRESH-003', 'OPS-003', 'OPS-004', 'OPS-005'] as const) {
      const model = createFreshnessOperationsWorkspaceV2({ screenId });
      assert.equal(model.projection.dataStatus, 'UNAVAILABLE_DEPENDENCY');
      assert.equal(model.projection.table.state, 'UNAVAILABLE_DEPENDENCY');
      assert.deepEqual(model.projection.table.rows, []);
      assert.equal(model.projection.table.emptyState?.code, 'UNAVAILABLE_DEPENDENCY');
      assert.equal(model.projection.unknownAsZeroAllowed, false);
    }
  });
});
