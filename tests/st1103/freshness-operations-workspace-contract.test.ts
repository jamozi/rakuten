import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  FRESHNESS_OPERATIONS_SCREEN_IDS,
  FRESHNESS_OPERATIONS_SCREENS,
  FRESHNESS_OPERATIONS_WORKSPACE_CLASSIFICATION,
  FRESHNESS_OPERATIONS_WORKSPACE_ERROR_CODES,
  createFreshnessOperationsWorkspaceCandidate,
} from '../../packages/web-ui/src/index.ts';

describe('ST-1103 freshness and operations workspace catalog contract', () => {
  it('pins the exact eight canonical screen records in source order', () => {
    assert.deepEqual(FRESHNESS_OPERATIONS_SCREEN_IDS, [
      'FRESH-001',
      'FRESH-002',
      'FRESH-003',
      'OPS-001',
      'OPS-002',
      'OPS-003',
      'OPS-004',
      'OPS-005',
    ]);
    assert.deepEqual(FRESHNESS_OPERATIONS_SCREENS, [
      {
        id: 'FRESH-001',
        name: 'Freshness Queue',
        route: '/admin/freshness',
        area: 'freshness',
        roles: ['MANAGING_EDITOR', 'EDITOR', 'OPERATOR'],
        purpose: 'Stale/Expired Factと影響記事を管理',
        mvp: true,
        criticalAction: false,
        apiDependencies: [],
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        runtimeVerification: 'NOT_EXECUTED',
        routeRegistered: false,
      },
      {
        id: 'FRESH-002',
        name: 'Link Health',
        route: '/admin/freshness/link-health',
        area: 'freshness',
        roles: ['EDITOR', 'OPERATOR'],
        purpose: 'Affiliate LinkとDestination異常を確認',
        mvp: true,
        criticalAction: false,
        apiDependencies: [],
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        runtimeVerification: 'NOT_EXECUTED',
        routeRegistered: false,
      },
      {
        id: 'FRESH-003',
        name: 'Refresh Proposal',
        route: '/admin/freshness/proposals/{id}',
        area: 'freshness',
        roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
        purpose: '更新差分と再承認範囲を確認',
        mvp: true,
        criticalAction: false,
        apiDependencies: [],
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        runtimeVerification: 'NOT_EXECUTED',
        routeRegistered: false,
      },
      {
        id: 'OPS-001',
        name: 'Job Monitor',
        route: '/admin/ops/jobs',
        area: 'operations',
        roles: ['OPERATOR', 'SECURITY_AUDITOR'],
        purpose: 'Job、Attempt、Lease、Retryを監視',
        mvp: true,
        criticalAction: false,
        apiDependencies: [],
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        runtimeVerification: 'NOT_EXECUTED',
        routeRegistered: false,
      },
      {
        id: 'OPS-002',
        name: 'DLQ / Quarantine',
        route: '/admin/ops/dlq',
        area: 'operations',
        roles: ['OPERATOR', 'SECURITY_AUDITOR'],
        purpose: '隔離Payloadを安全に調査・再実行',
        mvp: true,
        criticalAction: false,
        apiDependencies: [],
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        runtimeVerification: 'NOT_EXECUTED',
        routeRegistered: false,
      },
      {
        id: 'OPS-003',
        name: 'Incident',
        route: '/admin/ops/incidents/{id}',
        area: 'operations',
        roles: ['PRODUCT_OWNER', 'OPERATOR', 'SECURITY_AUDITOR'],
        purpose: 'Incident、Timeline、Action、Evidenceを管理',
        mvp: true,
        criticalAction: false,
        apiDependencies: [],
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        runtimeVerification: 'NOT_EXECUTED',
        routeRegistered: false,
      },
      {
        id: 'OPS-004',
        name: 'Kill Switches',
        route: '/admin/ops/kill-switches',
        area: 'operations',
        roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'OPERATOR'],
        purpose: 'Publication/Affiliate停止をstep-upで操作',
        mvp: true,
        criticalAction: true,
        apiDependencies: [],
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        runtimeVerification: 'NOT_EXECUTED',
        routeRegistered: false,
      },
      {
        id: 'OPS-005',
        name: 'Audit Log',
        route: '/admin/ops/audit',
        area: 'operations',
        roles: ['SECURITY_AUDITOR', 'READ_ONLY_AUDITOR'],
        purpose: '不変Audit Eventを検索',
        mvp: true,
        criticalAction: false,
        apiDependencies: [],
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        runtimeVerification: 'NOT_EXECUTED',
        routeRegistered: false,
      },
    ]);
  });

  it('exposes only a disabled catalog candidate and no component ownership claim', () => {
    const candidate = createFreshnessOperationsWorkspaceCandidate({ screenId: 'OPS-004' });

    assert.equal(candidate.classification, FRESHNESS_OPERATIONS_WORKSPACE_CLASSIFICATION);
    assert.equal(candidate.storyId, 'ST-1103');
    assert.equal(candidate.availability, 'DISABLED');
    assert.equal(candidate.componentOwnership, 'NOT_INFERRED');
    assert.deepEqual(candidate.components, []);
    assert.equal(candidate.routeRegistered, false);
    assert.equal(candidate.screen.criticalAction, true);
    assert.deepEqual(candidate.actions, []);
    assert.equal(candidate.authority.criticalActionExecutionEnabled, false);
  });

  it('keeps a unique closed error vocabulary', () => {
    assert.equal(
      new Set(FRESHNESS_OPERATIONS_WORKSPACE_ERROR_CODES).size,
      FRESHNESS_OPERATIONS_WORKSPACE_ERROR_CODES.length,
    );
    assert.equal(Object.isFrozen(FRESHNESS_OPERATIONS_WORKSPACE_ERROR_CODES), true);
  });
});
