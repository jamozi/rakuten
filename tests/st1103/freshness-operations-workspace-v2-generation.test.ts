import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import {
  ST1103_RECORDED_PROJECTION_V2_JSON,
  ST1103_RECORDED_PROJECTION_V2_SHA256,
} from '../../packages/web-ui/src/freshness-operations-recorded.v2.ts';

describe('ST-1103 V2 generated projection binding', () => {
  it('binds the generated TypeScript wrapper to the exact canonical JSON bytes', () => {
    const bytes = readFileSync(
      new URL('../../changes/st-1103/freshness-operations-recorded.v2.json', import.meta.url),
    );
    assert.equal(
      createHash('sha256').update(bytes).digest('hex'),
      ST1103_RECORDED_PROJECTION_V2_SHA256,
    );
    assert.equal(bytes.toString('ascii').trimEnd(), ST1103_RECORDED_PROJECTION_V2_JSON);

    const fixture = JSON.parse(ST1103_RECORDED_PROJECTION_V2_JSON) as Record<string, unknown>;
    assert.deepEqual(Object.keys(fixture), [
      'schemaVersion',
      'storyId',
      'classification',
      'environment',
      'evaluatedAt',
      'bindings',
      'projections',
    ]);
    assert.deepEqual(Object.keys(fixture['projections'] as Record<string, unknown>), [
      'FRESH-001',
      'FRESH-002',
      'FRESH-003',
      'OPS-001',
      'OPS-002',
      'OPS-003',
      'OPS-004',
      'OPS-005',
    ]);
  });

  it('contains only metadata projections and no raw, secret, provider, or callback material', () => {
    const normalized = ST1103_RECORDED_PROJECTION_V2_JSON.toLowerCase();
    for (const prohibited of [
      'payloadbody',
      'credential',
      'secret',
      'bearer',
      'cookie',
      'reviewbody',
      'sourcebody',
      'onclick',
      'callback',
      'authorizationtoken',
    ]) {
      assert.equal(normalized.includes(prohibited), false, prohibited);
    }
    const fixture = JSON.parse(ST1103_RECORDED_PROJECTION_V2_JSON) as {
      projections: Record<string, { rawPayloadPresent: boolean }>;
    };
    assert.equal(
      Object.values(fixture.projections).every((projection) => !projection.rawPayloadPresent),
      true,
    );
  });

  it('preserves the historical V1 implementation bytes', () => {
    const source = readFileSync(
      new URL('../../packages/web-ui/src/freshness-operations-workspace.ts', import.meta.url),
    );
    assert.equal(
      createHash('sha256').update(source).digest('hex'),
      'a4134506264867f52022a7226c6adce45f920d73aafab1311082236534b2cde9',
    );
  });
});
