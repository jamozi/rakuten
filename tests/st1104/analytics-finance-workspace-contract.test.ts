import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  ANALYTICS_FINANCE_SCREEN_IDS,
  ANALYTICS_FINANCE_SCREENS,
  ANALYTICS_FINANCE_WORKSPACE_CLASSIFICATION,
  ANALYTICS_FINANCE_WORKSPACE_ERROR_CODES,
  createAnalyticsFinanceWorkspaceCandidate,
} from '../../packages/web-ui/src/index.ts';

describe('ST-1104 analytics and finance workspace catalog contract', () => {
  it('pins the exact six canonical screen records in source order', () => {
    assert.deepEqual(ANALYTICS_FINANCE_SCREEN_IDS, [
      'ANA-001',
      'ANA-002',
      'ANA-003',
      'FIN-001',
      'FIN-002',
      'FIN-003',
    ]);
    assert.deepEqual(ANALYTICS_FINANCE_SCREENS, [
      {
        id: 'ANA-001',
        name: 'Content Performance',
        route: '/admin/analytics/content',
        area: 'analytics',
        roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'ANALYST'],
        purpose: '検索、行動、クリック、品質を記事別に表示',
        mvp: true,
        criticalAction: false,
        apiDependencies: [],
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        runtimeVerification: 'NOT_EXECUTED',
        routeRegistered: false,
      },
      {
        id: 'ANA-002',
        name: 'Search Performance',
        route: '/admin/analytics/search',
        area: 'analytics',
        roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'ANALYST'],
        purpose: 'Search Console指標とIntentを表示',
        mvp: true,
        criticalAction: false,
        apiDependencies: [],
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        runtimeVerification: 'NOT_EXECUTED',
        routeRegistered: false,
      },
      {
        id: 'ANA-003',
        name: 'Affiliate Clicks',
        route: '/admin/analytics/clicks',
        area: 'analytics',
        roles: ['PRODUCT_OWNER', 'ANALYST'],
        purpose: 'CTA別クリックと計測品質を表示',
        mvp: true,
        criticalAction: false,
        apiDependencies: [],
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        runtimeVerification: 'NOT_EXECUTED',
        routeRegistered: false,
      },
      {
        id: 'FIN-001',
        name: '成果Import',
        route: '/admin/finance/imports',
        area: 'finance',
        roles: ['PRODUCT_OWNER', 'ANALYST', 'OPERATOR'],
        purpose: 'CSV Upload、検査、Dry Run、Commit',
        mvp: true,
        criticalAction: false,
        apiDependencies: [],
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        runtimeVerification: 'NOT_EXECUTED',
        routeRegistered: false,
      },
      {
        id: 'FIN-002',
        name: 'Reconciliation',
        route: '/admin/finance/reconciliation/{id}',
        area: 'finance',
        roles: ['PRODUCT_OWNER', 'ANALYST'],
        purpose: 'Provider合計とCanonical取込を照合',
        mvp: true,
        criticalAction: false,
        apiDependencies: [],
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        runtimeVerification: 'NOT_EXECUTED',
        routeRegistered: false,
      },
      {
        id: 'FIN-003',
        name: 'Unit Economics',
        route: '/admin/finance/unit-economics',
        area: 'finance',
        roles: ['PRODUCT_OWNER', 'ANALYST'],
        purpose: '確定EPC/RPM/貢献利益と帰属Basisを表示',
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

  it('exposes only a disabled candidate with no component or dashboard ownership claim', () => {
    const candidate = createAnalyticsFinanceWorkspaceCandidate({ screenId: 'FIN-001' });

    assert.equal(candidate.classification, ANALYTICS_FINANCE_WORKSPACE_CLASSIFICATION);
    assert.equal(candidate.storyId, 'ST-1104');
    assert.equal(candidate.availability, 'DISABLED');
    assert.equal(candidate.componentOwnership, 'NOT_INFERRED');
    assert.deepEqual(candidate.components, []);
    assert.equal(candidate.dashboardOwnership, 'NOT_INFERRED');
    assert.deepEqual(candidate.dashboards, []);
    assert.equal(candidate.routeRegistered, false);
    assert.equal(candidate.screen.criticalAction, false);
    assert.equal(candidate.csvCommitPolicy.criticalActionRequirement, true);
    assert.equal(candidate.csvCommitPolicy.available, false);
    assert.deepEqual(candidate.actions, []);
  });

  it('keeps a unique closed error vocabulary', () => {
    assert.equal(
      new Set(ANALYTICS_FINANCE_WORKSPACE_ERROR_CODES).size,
      ANALYTICS_FINANCE_WORKSPACE_ERROR_CODES.length,
    );
    assert.equal(Object.isFrozen(ANALYTICS_FINANCE_WORKSPACE_ERROR_CODES), true);
  });
});
