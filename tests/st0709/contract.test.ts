import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  AI_GOVERNANCE_SCREEN,
  AI_GOVERNANCE_SECTION_IDS,
  AI_GOVERNANCE_SECTIONS,
  AI_GOVERNANCE_SOURCE_BINDINGS,
} from '../../packages/web-ui/src/ai-governance-workspace.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

function committedSha256(commit: string, path: string): string {
  const bytes = execFileSync('git', ['show', `${commit}:${path}`], {
    cwd: repositoryRoot,
    maxBuffer: 4 * 1024 * 1024,
  });
  return createHash('sha256').update(bytes).digest('hex');
}

describe('ST-0709 source-derived contract', () => {
  it('preserves exact GOV-001 catalog and Story objective metadata', () => {
    assert.deepEqual(AI_GOVERNANCE_SCREEN, {
      id: 'GOV-001',
      name: 'AI Governance',
      route: '/admin/governance/ai',
      area: 'governance',
      roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'SECURITY_AUDITOR'],
      purpose: 'Task/Prompt/Route/Evaluation/Releaseを表示',
      storyObjective: 'Task/Prompt/Route/Eval/Costを表示',
      mvp: true,
      criticalAction: false,
      apiDependencies: [],
      designStatus: 'APPROVED_FOR_IMPLEMENTATION',
      implementationStatus: 'NOT_STARTED',
      runtimeVerification: 'NOT_EXECUTED',
    });
  });

  it('fixes the exact read-only section order with unavailable values', () => {
    assert.deepEqual(AI_GOVERNANCE_SECTION_IDS, [
      'TASK',
      'PROMPT',
      'ROUTE',
      'EVALUATION',
      'RELEASE',
      'COST',
    ]);
    assert.deepEqual(
      AI_GOVERNANCE_SECTIONS.map(({ id, label }) => ({ id, label })),
      [
        { id: 'TASK', label: 'Task' },
        { id: 'PROMPT', label: 'Prompt' },
        { id: 'ROUTE', label: 'Route' },
        { id: 'EVALUATION', label: 'Evaluation' },
        { id: 'RELEASE', label: 'Release' },
        { id: 'COST', label: 'Cost' },
      ],
    );
    for (const section of AI_GOVERNANCE_SECTIONS) {
      assert.equal(section.mode, 'READ_ONLY');
      assert.equal(section.status, 'NOT_LOADED');
      assert.deepEqual(section.records, []);
      assert.equal(section.recordCount, null);
      assert.equal(section.availableCount, null);
      assert.equal(section.selectedRecordId, null);
      assert.deepEqual(section.actions, []);
    }
  });

  it('pins exact predecessor commits and complete committed artifact bytes', () => {
    assert.deepEqual(
      AI_GOVERNANCE_SOURCE_BINDINGS.map(({ storyId, commit, artifacts }) => ({
        storyId,
        commit,
        artifactCount: artifacts.length,
      })),
      [
        {
          storyId: 'ST-0706',
          commit: 'fe867f85c68ea661b055f4edd32ef6fbc600fa68',
          artifactCount: 9,
        },
        {
          storyId: 'ST-0707',
          commit: '14f0813c443e22faab81dfce3507aff320831ac1',
          artifactCount: 7,
        },
        {
          storyId: 'ST-1101',
          commit: '6933612a49863591555137868ca0cec935cf65e4',
          artifactCount: 14,
        },
      ],
    );
    for (const binding of AI_GOVERNANCE_SOURCE_BINDINGS) {
      assert.match(binding.commit, /^[0-9a-f]{40}$/);
      assert.equal(
        new Set(binding.artifacts.map(({ path }) => path)).size,
        binding.artifacts.length,
      );
      for (const artifact of binding.artifacts) {
        assert.match(artifact.path, /^(?:changes|packages|python|tests)\//);
        assert.match(artifact.sha256, /^[0-9a-f]{64}$/);
        assert.equal(
          committedSha256(binding.commit, artifact.path),
          artifact.sha256,
          `${binding.storyId} source drift: ${artifact.path}`,
        );
      }
    }
  });

  it('preserves predecessor disabled, unavailable and non-attesting semantics', () => {
    const [orchestration, evaluation, foundation] = AI_GOVERNANCE_SOURCE_BINDINGS;
    assert.deepEqual(orchestration.semantics['jobs'], []);
    assert.equal(orchestration.semantics['jobCount'], null);
    assert.deepEqual(orchestration.semantics['costs'], []);
    assert.equal(orchestration.semantics['costCount'], null);
    assert.equal(orchestration.semantics['liveProviderIntegration'], false);
    assert.equal(orchestration.semantics['approvalAvailable'], false);
    assert.equal(orchestration.semantics['releaseAvailable'], false);
    assert.equal(orchestration.semantics['liveExecution'], 'NOT_EXECUTED');

    assert.equal(evaluation.semantics['canonicalBootstrapPayloadBound'], false);
    assert.equal(evaluation.semantics['lockedHoldout'], 'NOT_LOADED');
    assert.deepEqual(evaluation.semantics['reports'], []);
    assert.equal(evaluation.semantics['reportCount'], null);
    assert.equal(evaluation.semantics['storyAcceptance'], false);
    assert.equal(evaluation.semantics['releaseDecision'], 'NOT_READY');
    assert.equal(evaluation.semantics['releaseEligible'], false);
    assert.equal(evaluation.semantics['externalActionCount'], 0);
    assert.equal(evaluation.semantics['actionCount'], 0);

    assert.deepEqual(foundation.semantics, {
      registeredScreenIds: ['ADM-001'],
      registeredPaths: ['/admin'],
      adminAvailability: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED',
      governanceScreenIdsRegistered: [],
      governanceRoutesRegistered: [],
      navigationExecution: 'NOT_EXECUTED',
      renderExecution: 'NOT_EXECUTED',
      backendReauthenticationRequired: true,
      backendReauthorizationRequired: true,
    });
  });

  it('deep-freezes every exported JSON authority value', () => {
    assert.ok(Object.isFrozen(AI_GOVERNANCE_SCREEN));
    assert.ok(Object.isFrozen(AI_GOVERNANCE_SCREEN.roles));
    assert.ok(Object.isFrozen(AI_GOVERNANCE_SECTION_IDS));
    assert.ok(Object.isFrozen(AI_GOVERNANCE_SECTIONS));
    assert.ok(Object.isFrozen(AI_GOVERNANCE_SECTIONS[0]));
    assert.ok(Object.isFrozen(AI_GOVERNANCE_SOURCE_BINDINGS));
    assert.ok(Object.isFrozen(AI_GOVERNANCE_SOURCE_BINDINGS[0].artifacts));
    assert.ok(Object.isFrozen(AI_GOVERNANCE_SOURCE_BINDINGS[0].semantics));
  });
});
