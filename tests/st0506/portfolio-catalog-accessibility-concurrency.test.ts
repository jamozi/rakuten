import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PORTFOLIO_CATALOG_SCREEN_IDS,
  createPortfolioCatalogWorkspaceModel,
} from '../../packages/web-ui/src/portfolio-catalog-workspace.ts';

describe('portfolio/catalog accessibility and concurrency boundary', () => {
  it('keeps concurrency values unavailable and evaluation unexecuted', () => {
    for (const screenId of PORTFOLIO_CATALOG_SCREEN_IDS) {
      assert.deepEqual(createPortfolioCatalogWorkspaceModel({ screenId }).concurrency, {
        etag: null,
        ifMatch: null,
        lockVersion: null,
        status: 'NOT_EVALUATED',
      });
    }
  });

  it('requires keyboard, focus, semantic structure and labels without evidence claims', () => {
    for (const screenId of PORTFOLIO_CATALOG_SCREEN_IDS) {
      const accessibility = createPortfolioCatalogWorkspaceModel({ screenId }).accessibility;
      assert.equal(accessibility.keyboardOperabilityRequired, true);
      assert.equal(accessibility.visibleFocusRequired, true);
      assert.equal(accessibility.semanticStructureRequired, true);
      assert.equal(accessibility.screenReaderLabelsRequired, true);
      assert.equal(accessibility.browserVerification, 'NOT_EXECUTED');
      assert.equal(accessibility.automatedAccessibilityVerification, 'NOT_EXECUTED');
      assert.equal(accessibility.manualKeyboardVerification, 'NOT_EXECUTED');
      assert.equal(accessibility.screenReaderVerification, 'NOT_EXECUTED');
    }
  });

  it('preserves OD-006 safe defaults and keeps critical CAT-003 actionless', () => {
    const workbench = createPortfolioCatalogWorkspaceModel({ screenId: 'CAT-003' });
    assert.equal(workbench.screen.criticalAction, true);
    assert.deepEqual(workbench.identityBoundary, {
      openDecision: 'OD-006',
      automaticMergeEnabled: false,
      automaticSplitEnabled: false,
      humanReviewRequired: true,
      humanReviewStatus: 'REQUIRED_NOT_EXECUTED',
      identityDecisions: [],
      reviews: [],
      approvals: [],
      merges: [],
      splits: [],
    });
    assert.deepEqual(workbench.actions, []);
    assert.equal(workbench.identityExecution, 'NOT_EXECUTED');
    assert.equal(workbench.commandExecution, 'NOT_EXECUTED');
  });

  it('keeps finance hidden for every portfolio and catalog screen', () => {
    for (const screenId of PORTFOLIO_CATALOG_SCREEN_IDS) {
      assert.deepEqual(createPortfolioCatalogWorkspaceModel({ screenId }).financeBoundary, {
        visibility: 'HIDDEN',
        fields: [],
        access: 'NOT_EXECUTED',
      });
    }
  });
});
