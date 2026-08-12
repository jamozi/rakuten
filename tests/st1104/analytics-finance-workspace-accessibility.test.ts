import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  ANALYTICS_FINANCE_SCREEN_IDS,
  createAnalyticsFinanceWorkspaceCandidate,
} from '../../packages/web-ui/src/index.ts';

describe('ST-1104 visibility and accessibility requirements boundary', () => {
  it('requires basis, freshness, quality, source, period, and explicit unknown without claiming display', () => {
    for (const screenId of ANALYTICS_FINANCE_SCREEN_IDS) {
      const candidate = createAnalyticsFinanceWorkspaceCandidate({ screenId });

      assert.deepEqual(candidate.visibilityRequirements, {
        requirementsOnly: true,
        rendered: false,
        verified: false,
        dataSourceRequired: true,
        periodRequired: true,
        freshnessRequired: true,
        basisRequired: true,
        qualityRequired: true,
        unknownRequired: true,
        unknownAsZeroAllowed: false,
        unknownAsEmptyAllowed: false,
        unknownAsGuessAllowed: false,
      });
    }
  });

  it('records status, table, chart-alternative, and financial-action requirements only', () => {
    const candidate = createAnalyticsFinanceWorkspaceCandidate({ screenId: 'FIN-003' });

    assert.deepEqual(candidate.accessibility, {
      requirementsOnly: true,
      rendered: false,
      verified: false,
      statusPresentation: {
        textRequired: true,
        iconRequired: true,
        colorOnly: false,
        rendered: false,
        verified: false,
      },
      tableSemantics: {
        captionRequired: true,
        headersRequired: true,
        scopeRequired: true,
        rendered: false,
        verified: false,
      },
      chartAlternative: {
        tableOrTextSummaryRequired: true,
        rendered: false,
        verified: false,
      },
      financialActionCorrection: {
        confirmationOrCorrectionRequired: true,
        rendered: false,
        verified: false,
      },
      loadingSuccessFailureAnnouncement: {
        required: true,
        rendered: false,
        verified: false,
      },
    });
    assert.equal(candidate.verification.accessibility, 'NOT_VERIFIED');
    assert.equal(candidate.verification.TST_024, 'NOT_EXECUTED');
  });

  it('does not infer components, dashboards, DOM roles, focus order, or interactions', () => {
    const candidate = createAnalyticsFinanceWorkspaceCandidate({ screenId: 'ANA-002' });
    const serialized = JSON.stringify(candidate);

    assert.deepEqual(candidate.components, []);
    assert.equal(candidate.componentOwnership, 'NOT_INFERRED');
    assert.deepEqual(candidate.dashboards, []);
    assert.equal(candidate.dashboardOwnership, 'NOT_INFERRED');
    for (const absent of [
      'componentId',
      'dashboardId',
      'domId',
      'focusOrder',
      'tabIndex',
      'onClick',
    ]) {
      assert.equal(serialized.includes(absent), false, absent);
    }
  });
});
