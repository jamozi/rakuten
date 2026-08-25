import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  ST1102_RECORDED_WORKSPACE_V2_JSON,
  ST1102_RECORDED_WORKSPACE_V2_SHA256,
} from '../../packages/web-ui/src/article-workspace-recorded.v2.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

function sha256(value: Uint8Array | string): string {
  return createHash('sha256').update(value).digest('hex');
}

describe('ST-1102 V2 generated artifact bindings', () => {
  it('binds the TypeScript wrapper to exact generated JSON bytes', () => {
    const fixture = readFileSync(
      resolve(repositoryRoot, 'changes/st-1102/article-workspace-recorded.v2.json'),
    );
    assert.equal(fixture.toString('utf8'), ST1102_RECORDED_WORKSPACE_V2_JSON);
    assert.equal(sha256(fixture), ST1102_RECORDED_WORKSPACE_V2_SHA256);
    const parsed = JSON.parse(fixture.toString('utf8')) as Record<string, unknown>;
    assert.equal(parsed['storyId'], 'ST-1102');
    assert.equal(parsed['localStatus'], 'LOCAL_IMPLEMENTATION_COMPLETE');
  });

  it('keeps the historical V1 source byte-identical', () => {
    const historical = readFileSync(
      resolve(repositoryRoot, 'packages/web-ui/src/article-workspace.ts'),
    );
    assert.equal(
      sha256(historical),
      '01d2f680ddfb5a64fa9d84db1c10e1ae9cd3de490520e67f135f3be63260db89',
    );
  });

  it('records a closed no-authority manifest and exact generated hashes', () => {
    const manifest = readFileSync(
      resolve(repositoryRoot, 'changes/st-1102/runtime-manifest.v2.yaml'),
      'utf8',
    );
    assert.match(manifest, /story_id: ST-1102/u);
    assert.match(manifest, /status: LOCAL_IMPLEMENTATION_COMPLETE/u);
    assert.match(manifest, /authority: NONE/u);
    assert.match(manifest, /production_eligible: false/u);
    assert.match(manifest, new RegExp(ST1102_RECORDED_WORKSPACE_V2_SHA256, 'u'));
    assert.match(manifest, /formal_TST_022: NOT_EXECUTED/u);
    assert.match(manifest, /formal_TST_024: NOT_EXECUTED/u);
  });
});
