import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  AI_GOVERNANCE_RECORDED_FIXTURE_V2,
  AI_GOVERNANCE_V2_SECTION_IDS,
} from '../../packages/web-ui/src/ai-governance-workspace-v2.ts';
import {
  AI_GOVERNANCE_RECORDED_V2_JSON,
  AI_GOVERNANCE_RECORDED_V2_SHA256,
} from '../../packages/web-ui/src/ai-governance-recorded.v2.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

describe('ST-0709 V2 recorded governance contract', () => {
  it('binds exact canonical JSON bytes and the approved GOV-001 screen', () => {
    const fixtureBytes = readFileSync(
      resolve(repositoryRoot, 'changes/st-0709/generated/ai-governance-workspace.v2.json'),
    );
    assert.equal(fixtureBytes.toString('utf8'), `${AI_GOVERNANCE_RECORDED_V2_JSON}\n`);
    assert.equal(
      createHash('sha256').update(AI_GOVERNANCE_RECORDED_V2_JSON).digest('hex'),
      AI_GOVERNANCE_RECORDED_V2_SHA256,
    );
    assert.deepEqual(AI_GOVERNANCE_RECORDED_FIXTURE_V2.screen, {
      apiDependencies: [],
      area: 'governance',
      canonicalImplementationStatus: 'NOT_STARTED',
      canonicalRuntimeVerification: 'NOT_EXECUTED',
      criticalAction: false,
      designStatus: 'APPROVED_FOR_IMPLEMENTATION',
      id: 'GOV-001',
      mvp: true,
      name: 'AI Governance',
      purpose: 'Task/Prompt/Route/Evaluation/Releaseを表示',
      roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'SECURITY_AUDITOR'],
      route: '/admin/governance/ai',
      storyObjective: 'Task/Prompt/Route/Eval/Costを表示',
    });
  });

  it('projects the complete fixed section order and recorded row counts', () => {
    assert.deepEqual(AI_GOVERNANCE_V2_SECTION_IDS, [
      'TASK',
      'PROMPT',
      'ROUTE',
      'EVALUATION',
      'RELEASE',
      'COST',
    ]);
    assert.deepEqual(AI_GOVERNANCE_RECORDED_FIXTURE_V2.sectionOrder, [
      'TASK',
      'PROMPT',
      'ROUTE',
      'EVALUATION',
      'RELEASE',
      'COST',
    ]);
    assert.deepEqual(
      AI_GOVERNANCE_RECORDED_FIXTURE_V2.sections.map(({ id, recordCount }) => ({
        id,
        recordCount,
      })),
      [
        { id: 'TASK', recordCount: 12 },
        { id: 'PROMPT', recordCount: 12 },
        { id: 'ROUTE', recordCount: 5 },
        { id: 'EVALUATION', recordCount: 1 },
        { id: 'RELEASE', recordCount: 1 },
        { id: 'COST', recordCount: 12 },
      ],
    );
  });

  it('pins every canonical and dependency input to current exact bytes', () => {
    assert.equal(AI_GOVERNANCE_RECORDED_FIXTURE_V2.sourceBindings.length, 32);
    for (const binding of AI_GOVERNANCE_RECORDED_FIXTURE_V2.sourceBindings) {
      assert.match(binding.sha256, /^[0-9a-f]{64}$/);
      assert.equal(
        createHash('sha256')
          .update(readFileSync(resolve(repositoryRoot, binding.path)))
          .digest('hex'),
        binding.sha256,
        binding.path,
      );
    }
  });

  it('preserves the ST-0709 V1 source byte-for-byte', () => {
    assert.equal(
      createHash('sha256')
        .update(
          readFileSync(resolve(repositoryRoot, 'packages/web-ui/src/ai-governance-workspace.ts')),
        )
        .digest('hex'),
      '07b240c8f127ec3676b7d111778f27a9eca0e288ed866e177be077e733b84875',
    );
  });
});
