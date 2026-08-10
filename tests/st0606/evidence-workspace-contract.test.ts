import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  EVIDENCE_WORKSPACE_SCREEN_IDS,
  EVIDENCE_WORKSPACE_SCREENS,
  EVIDENCE_WORKSPACE_SOURCE_BINDINGS,
} from '../../packages/web-ui/src/evidence-workspace.ts';

const expectedScreens = [
  {
    id: 'EVD-001',
    name: 'Source Packet一覧',
    route: '/admin/evidence/source-packets',
    area: 'evidence',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    purpose: '生成に使う承認済み情報束を管理',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'EVD-002',
    name: 'Source Packet詳細',
    route: '/admin/evidence/source-packets/{id}',
    area: 'evidence',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    purpose: 'Fact、Conflict、Freshness、Coverageを確認',
    mvp: true,
    criticalAction: true,
    apiDependencies: ['SourcePacket', 'Fact'],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'EVD-003',
    name: 'Fact Explorer',
    route: '/admin/evidence/facts',
    area: 'evidence',
    roles: ['EDITOR', 'REVIEWER', 'ANALYST'],
    purpose: 'FactをSource/対象/日時で検索',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'EVD-004',
    name: 'Evidence Conflict Queue',
    route: '/admin/evidence/conflicts',
    area: 'evidence',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    purpose: '矛盾Factを解決またはUnknown化',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
] as const;

describe('ST-0606 source-derived contract', () => {
  it('preserves the exact canonical EVD screen IDs, order and metadata', () => {
    assert.deepEqual(EVIDENCE_WORKSPACE_SCREEN_IDS, ['EVD-001', 'EVD-002', 'EVD-003', 'EVD-004']);
    assert.deepEqual(EVIDENCE_WORKSPACE_SCREENS, expectedScreens);
    assert.equal(new Set(EVIDENCE_WORKSPACE_SCREEN_IDS).size, 4);
  });

  it('pins the exact predecessor commits and complete committed artifact inventories', () => {
    assert.deepEqual(
      EVIDENCE_WORKSPACE_SOURCE_BINDINGS.map(({ storyId, commit, artifacts }) => ({
        storyId,
        commit,
        artifactCount: artifacts.length,
      })),
      [
        {
          storyId: 'ST-1101',
          commit: '6933612a49863591555137868ca0cec935cf65e4',
          artifactCount: 14,
        },
        {
          storyId: 'ST-0604',
          commit: '24e9640f7fa2b681ea40bb539837e40403928ec8',
          artifactCount: 9,
        },
        {
          storyId: 'ST-0605',
          commit: '72541b0e855954005231368e48a7811abe4b3ea4',
          artifactCount: 9,
        },
      ],
    );
    for (const binding of EVIDENCE_WORKSPACE_SOURCE_BINDINGS) {
      assert.match(binding.commit, /^[0-9a-f]{40}$/);
      assert.equal(
        new Set(binding.artifacts.map(({ path }) => path)).size,
        binding.artifacts.length,
      );
      for (const artifact of binding.artifacts) {
        assert.match(artifact.path, /^(?:changes|packages|scripts|tests)\//);
        assert.match(artifact.sha256, /^[0-9a-f]{64}$/);
      }
    }
  });

  it('preserves exact predecessor disabled and unavailable semantics', () => {
    const [foundation, lifecycle, coverage] = EVIDENCE_WORKSPACE_SOURCE_BINDINGS;
    assert.deepEqual(foundation.semantics, {
      registeredScreenIds: ['ADM-001'],
      registeredPaths: ['/admin'],
      adminAvailability: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED',
      evidenceScreenIdsRegistered: [],
      evidenceRoutesRegistered: [],
      navigationExecution: 'NOT_EXECUTED',
      renderExecution: 'NOT_EXECUTED',
      backendReauthenticationRequired: true,
      backendReauthorizationRequired: true,
    });
    assert.equal(lifecycle.semantics['decision'], 'NOT_READY');
    assert.deepEqual(lifecycle.semantics['packets'], []);
    assert.deepEqual(lifecycle.semantics['approvals'], []);
    assert.equal(lifecycle.semantics['packetCount'], null);
    assert.equal(lifecycle.semantics['approval'], false);
    assert.equal(lifecycle.semantics['generationPermitted'], false);
    assert.equal(coverage.semantics['decision'], 'NOT_READY');
    assert.deepEqual(coverage.semantics['claims'], []);
    assert.deepEqual(coverage.semantics['facts'], []);
    assert.deepEqual(coverage.semantics['links'], []);
    assert.equal(coverage.semantics['claimCount'], null);
    assert.equal(coverage.semantics['mappingAuthority'], 'UNAVAILABLE');
    assert.equal(coverage.semantics['coverageEvaluable'], false);
    assert.equal(coverage.semantics['publicationPermitted'], false);
  });

  it('deep-freezes every exported JSON authority value', () => {
    assert.ok(Object.isFrozen(EVIDENCE_WORKSPACE_SCREEN_IDS));
    assert.ok(Object.isFrozen(EVIDENCE_WORKSPACE_SCREENS));
    assert.ok(Object.isFrozen(EVIDENCE_WORKSPACE_SCREENS[0]));
    assert.ok(Object.isFrozen(EVIDENCE_WORKSPACE_SCREENS[0].roles));
    assert.ok(Object.isFrozen(EVIDENCE_WORKSPACE_SOURCE_BINDINGS));
    assert.ok(Object.isFrozen(EVIDENCE_WORKSPACE_SOURCE_BINDINGS[0].artifacts));
    assert.ok(Object.isFrozen(EVIDENCE_WORKSPACE_SOURCE_BINDINGS[0].semantics));
  });
});
