import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import {
  ANALYTICS_FINANCE_SCREEN_IDS,
  createAnalyticsFinanceWorkspaceCandidate,
} from '../../packages/web-ui/src/index.ts';

function assertNoExecutableValue(value: unknown, seen = new WeakSet<object>()): void {
  assert.notEqual(typeof value, 'function');
  if (value === null || typeof value !== 'object' || seen.has(value)) {
    return;
  }
  seen.add(value);
  for (const item of Object.values(value)) {
    assertNoExecutableValue(item, seen);
  }
}

describe('ST-1104 protected analytics and finance boundaries', () => {
  it('retains exact dependency limitations and unresolved safe defaults', () => {
    const candidate = createAnalyticsFinanceWorkspaceCandidate({ screenId: 'FIN-003' });

    assert.deepEqual(candidate.dependencies, {
      adminFoundation: {
        storyId: 'ST-1101',
        status: 'DISABLED_HEADLESS',
        routeAuthority: false,
        payload: null,
      },
      kpiReadModels: {
        storyId: 'ST-1205',
        status: 'REFERENCE_PLAN_ONLY',
        decision: 'NOT_READY',
        definitionCount: 30,
        calculationCount: 0,
        verifiedCount: 0,
        valuesAvailable: false,
        payload: null,
      },
      unitEconomics: {
        storyId: 'ST-1304',
        status: 'UNAVAILABLE',
        openDecisions: ['OD-005', 'OD-009'],
        laborCostState: 'UNKNOWN',
        laborCostValue: null,
        unknownLaborAsZeroAllowed: false,
        payload: null,
      },
      revenueReport: {
        openDecision: 'OD-003',
        status: 'SYNTHETIC_ONLY_REAL_ATTRIBUTION_UNVERIFIED',
        payload: null,
      },
      analyticsConsent: {
        openDecision: 'OD-012',
        status: 'NONESSENTIAL_TRACKING_DISABLED',
        payload: null,
      },
      retention: {
        openDecision: 'OD-014',
        status: 'MINIMAL_COLLECTION_AUTO_DELETION_DISABLED',
        payload: null,
      },
      liveProviders: {
        openDecision: 'OD-015',
        status: 'RECORDED_FIXTURES_ONLY',
        payload: null,
      },
    });
  });

  it('keeps import and reconciliation reference-only and every action closed', () => {
    const candidate = createAnalyticsFinanceWorkspaceCandidate({ screenId: 'FIN-001' });

    assert.deepEqual(candidate.importBoundary, {
      workflowId: 'UI-WF-008',
      referenceOnly: true,
      implementationStatus: 'NOT_STARTED',
      runtimeVerification: 'NOT_EXECUTED',
      fileAccepted: false,
      securityScanExecuted: false,
      schemaDetectionExecuted: false,
      dryRunExecuted: false,
      reconciliationExecuted: false,
      humanConfirmationEstablished: false,
      commitExecuted: false,
      formulaDefenseVerified: false,
      duplicatePreventionVerified: false,
      estimatedAttributionOfficialized: false,
    });
    assert.deepEqual(candidate.actions, []);
    assert.equal(candidate.actionAvailability, 'UNAVAILABLE');
    assert.equal(candidate.effectAvailability, 'UNAVAILABLE');
    assert.equal(candidate.intentAvailability, 'UNAVAILABLE');
    assert.deepEqual(candidate.csvCommitPolicy, {
      criticalActionRequirement: true,
      available: false,
      authenticationEstablished: false,
      authorizationGranted: false,
      mfaEstablished: false,
      stepUpEstablished: false,
      reasonRecorded: false,
      idempotencyEstablished: false,
      auditRecorded: false,
    });
  });

  it('enforces finance isolation from Public and editorial recommendation surfaces', () => {
    const candidate = createAnalyticsFinanceWorkspaceCandidate({ screenId: 'FIN-002' });

    assert.deepEqual(candidate.financeIsolation, {
      dataClass: 'CONFIDENTIAL',
      publicExposure: false,
      publicProjectionEnabled: false,
      editorialRecommendationInput: false,
      financialValuesPresent: false,
      providerRowsPresent: false,
      personalDataPresent: false,
      secretsPresent: false,
    });
  });

  it('keeps every authority and external verification boundary closed', () => {
    for (const screenId of ANALYTICS_FINANCE_SCREEN_IDS) {
      const candidate = createAnalyticsFinanceWorkspaceCandidate({ screenId });

      assert.equal(
        Object.values(candidate.authority).every((value) => value === false),
        true,
      );
      assert.deepEqual(candidate.verification, {
        runtime: 'NOT_VERIFIED',
        accessibility: 'NOT_VERIFIED',
        formal: 'NOT_EXECUTED',
        live: 'NOT_EXECUTED',
        browser: 'NOT_EXECUTED',
        staging: 'NOT_EXECUTED',
        release: 'NOT_EXECUTED',
        publication: 'NOT_EXECUTED',
        production: 'NOT_EXECUTED',
        TST_022: 'NOT_EXECUTED',
        TST_024: 'NOT_EXECUTED',
        TST_030: 'NOT_EXECUTED',
      });
      assert.equal(candidate.acceptanceAchieved, false);
      assert.equal(candidate.storyComplete, false);
      assert.equal(candidate.productionEligible, false);
      assertNoExecutableValue(candidate);
    }
  });

  it('imports only the local serializable boundary and contains no runtime surface', () => {
    const source = readFileSync(
      new URL('../../packages/web-ui/src/analytics-finance-workspace.ts', import.meta.url),
      'utf8',
    );
    const imports = [...source.matchAll(/^import .* from ['"]([^'"]+)['"];$/gm)].map(
      (match) => match[1],
    );
    assert.deepEqual(imports, ['./serializable.ts']);
    for (const prohibited of [
      'react',
      'next/',
      'fetch(',
      'XMLHttpRequest',
      'document.',
      'window.',
      'Date.now',
      'Math.random',
      'process.env',
      'sqlalchemy',
      'queueMicrotask',
    ]) {
      assert.equal(source.includes(prohibited), false, prohibited);
    }
  });
});
