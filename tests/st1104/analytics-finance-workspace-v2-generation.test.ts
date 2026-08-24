import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { describe, it } from 'node:test';

import {
  ST1104_RECORDED_DASHBOARD_V2_JSON,
  ST1104_RECORDED_DASHBOARD_V2_SHA256,
} from '../../packages/web-ui/src/index.ts';

describe('ST-1104 V2 generated headless dashboard', () => {
  it('binds the immutable JSON bytes and exact six-screen order', () => {
    const bytes = Buffer.from(`${ST1104_RECORDED_DASHBOARD_V2_JSON}\n`, 'ascii');
    assert.equal(
      createHash('sha256').update(bytes).digest('hex'),
      ST1104_RECORDED_DASHBOARD_V2_SHA256,
    );
    const value = JSON.parse(ST1104_RECORDED_DASHBOARD_V2_JSON) as {
      screens: Array<{ screen_id: string; route_registered: boolean }>;
      authority: Record<string, boolean>;
      cross_source_comparison: string;
      live_verification: string;
    };
    assert.deepEqual(
      value.screens.map((screen) => screen.screen_id),
      ['ANA-001', 'ANA-002', 'ANA-003', 'FIN-001', 'FIN-002', 'FIN-003'],
    );
    assert.equal(
      value.screens.every((screen) => screen.route_registered === false),
      true,
    );
    assert.equal(
      Object.values(value.authority).every((allowed) => allowed === false),
      true,
    );
    assert.equal(value.cross_source_comparison, 'UNAVAILABLE_PERIOD_MISMATCH');
    assert.equal(value.live_verification, 'NOT_EXECUTED');
  });
});
