import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  ST0906_RECORDED_WORKSPACE_V2_JSON,
  ST0906_RECORDED_WORKSPACE_V2_SHA256,
} from '../../packages/web-ui/src/publication-review-recorded.v2.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

describe('ST-0906 V2 generated TypeScript fixture binding', () => {
  it('embeds exactly the owner-generated JSON bytes and SHA-256', () => {
    const fixture = readFileSync(
      resolve(
        repositoryRoot,
        'changes/st-0906/generated/publication-review-workspace-recorded.v2.json',
      ),
    );
    assert.equal(`${ST0906_RECORDED_WORKSPACE_V2_JSON}\n`, fixture.toString('ascii'));
    assert.equal(
      ST0906_RECORDED_WORKSPACE_V2_SHA256,
      createHash('sha256').update(fixture).digest('hex'),
    );
  });

  it('contains only closed recorded data and no external authority', () => {
    const fixture = JSON.parse(ST0906_RECORDED_WORKSPACE_V2_JSON) as {
      authority: Record<string, boolean>;
      rawPayloadPresent: boolean;
      financeDataPresent: boolean;
      credentialDataPresent: boolean;
    };
    assert.deepEqual(
      Object.entries(fixture.authority).filter(([key]) => key === 'backendReauthorizationRequired'),
      [['backendReauthorizationRequired', true]],
    );
    assert.ok(
      Object.entries(fixture.authority).every(
        ([key, value]) => key === 'backendReauthorizationRequired' || value === false,
      ),
    );
    assert.equal(fixture.rawPayloadPresent, false);
    assert.equal(fixture.financeDataPresent, false);
    assert.equal(fixture.credentialDataPresent, false);
  });
});
