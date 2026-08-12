import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  ANALYTICS_FINANCE_SCREEN_IDS,
  createAnalyticsFinanceWorkspaceCandidate,
  validateAnalyticsFinanceWorkspaceCandidate,
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

describe('ST-1104 headless analytics and finance workspace model', () => {
  it('is deterministic, detached, deeply frozen, and JSON-safe for every screen', () => {
    for (const screenId of ANALYTICS_FINANCE_SCREEN_IDS) {
      const first = createAnalyticsFinanceWorkspaceCandidate({ screenId });
      const second = createAnalyticsFinanceWorkspaceCandidate({ screenId });

      assert.deepEqual(first, second);
      assert.notStrictEqual(first, second);
      assert.notStrictEqual(first.screen, second.screen);
      assert.doesNotThrow(() => JSON.stringify(first));
      assert.deepEqual(JSON.parse(JSON.stringify(first)), first);
      assertDeepFrozen(first);
      assert.deepEqual(validateAnalyticsFinanceWorkspaceCandidate(first), first);
    }
  });

  it('keeps every data-bearing slot unavailable without values, amounts, rows, or formulas', () => {
    const candidate = createAnalyticsFinanceWorkspaceCandidate({ screenId: 'ANA-001' });

    assert.deepEqual(candidate.dataSlots, {
      kpiValues: { status: 'NOT_LOADED', payload: [] },
      attributionBasis: { status: 'NOT_EVALUATED', payload: null },
      freshness: { status: 'NOT_EVALUATED', payload: null },
      dataQuality: { status: 'NOT_EVALUATED', payload: null },
      imports: { status: 'NOT_LOADED', payload: [] },
      reconciliation: { status: 'NOT_EVALUATED', payload: null },
      unitEconomics: { status: 'NOT_EVALUATED', payload: null },
    });
    assert.equal(candidate.dependencies.kpiReadModels.valuesAvailable, false);
    assert.equal(candidate.dependencies.unitEconomics.laborCostValue, null);
  });

  it('accepts exactly one caller coordinate and never role, route, period, or basis input', () => {
    const candidate = createAnalyticsFinanceWorkspaceCandidate({ screenId: 'FIN-003' });

    assert.equal(candidate.screen.id, 'FIN-003');
    assert.equal(candidate.roleInputAccepted, false);
    assert.equal(
      candidate.roleMetadataAuthority,
      'DISPLAY_ONLY_NOT_AUTHENTICATION_OR_AUTHORIZATION',
    );
    assert.equal(candidate.routeRegistered, false);
    assert.equal(candidate.renderEnabled, false);
  });
});
