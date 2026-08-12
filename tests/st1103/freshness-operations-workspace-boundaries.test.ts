import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import {
  FRESHNESS_OPERATIONS_SCREEN_IDS,
  createFreshnessOperationsWorkspaceCandidate,
} from '../../packages/web-ui/src/index.ts';

function assertNoExecutableValue(value: unknown, seen = new WeakSet<object>()): void {
  assert.notEqual(typeof value, 'function');
  if (value === null || typeof value !== 'object' || seen.has(value)) {
    return;
  }
  seen.add(value);
  for (const item of Object.values(value)) {
    assertNoExecutableValue(item, seen);
  }
}

describe('ST-1103 protected freshness and operations boundaries', () => {
  it('keeps OD-007, runtime, kill-switch, and audit authority unavailable', () => {
    const candidate = createFreshnessOperationsWorkspaceCandidate({ screenId: 'OPS-005' });

    assert.deepEqual(candidate.dependencies, {
      freshnessPolicy: {
        storyId: 'ST-1401',
        openDecision: 'OD-007',
        status: 'UNAVAILABLE',
        payload: null,
      },
      jobRuntime: {
        storyId: 'ST-1404',
        status: 'RECORDED_ONLY',
        runtimeAuthority: false,
        payload: null,
      },
      killSwitch: {
        screenId: 'OPS-004',
        storyId: 'ST-1405',
        status: 'UNAVAILABLE',
        authority: 'UNDECLARED',
        payload: null,
      },
      auditLog: {
        screenId: 'OPS-005',
        status: 'UNAVAILABLE',
        authority: 'UNDECLARED',
        payload: null,
      },
    });
  });

  it('keeps every action, effect, authority, and external boundary closed', () => {
    for (const screenId of FRESHNESS_OPERATIONS_SCREEN_IDS) {
      const candidate = createFreshnessOperationsWorkspaceCandidate({ screenId });

      assert.deepEqual(candidate.actions, []);
      assert.equal(candidate.actionAvailability, 'UNAVAILABLE');
      assert.equal(candidate.effectAvailability, 'UNAVAILABLE');
      assert.equal(candidate.intentAvailability, 'UNAVAILABLE');
      assert.equal(
        Object.values(candidate.authority).every((value) => value === false),
        true,
      );
      assert.deepEqual(candidate.verification, {
        runtime: 'NOT_VERIFIED',
        accessibility: 'NOT_VERIFIED',
        formal: 'NOT_EXECUTED',
        live: 'NOT_EXECUTED',
        staging: 'NOT_EXECUTED',
        release: 'NOT_EXECUTED',
        publication: 'NOT_EXECUTED',
        production: 'NOT_EXECUTED',
      });
      assert.equal(candidate.acceptanceAchieved, false);
      assert.equal(candidate.storyComplete, false);
      assert.equal(candidate.productionEligible, false);
      assertNoExecutableValue(candidate);
    }
  });

  it('imports only the local serializable boundary and contains no runtime surface', () => {
    const source = readFileSync(
      new URL('../../packages/web-ui/src/freshness-operations-workspace.ts', import.meta.url),
      'utf8',
    );

    const imports = [...source.matchAll(/^import .* from ['"]([^'"]+)['"];$/gm)].map(
      (match) => match[1],
    );
    assert.deepEqual(imports, ['./serializable.ts']);
    for (const prohibited of [
      'react',
      'next/',
      'fetch(',
      'XMLHttpRequest',
      'document.',
      'window.',
      'Date.now',
      'Math.random',
      'process.env',
      'sqlalchemy',
      'queueMicrotask',
    ]) {
      assert.equal(source.includes(prohibited), false, prohibited);
    }
  });
});
