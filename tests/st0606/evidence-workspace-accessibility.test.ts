import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  EVIDENCE_WORKSPACE_SCREEN_IDS,
  createEvidenceWorkspaceModel,
} from '../../packages/web-ui/src/evidence-workspace.ts';

describe('evidence-workspace accessibility reference boundary', () => {
  it('requires semantic, keyboard, focus, label, error and contrast accessibility', () => {
    for (const screenId of EVIDENCE_WORKSPACE_SCREEN_IDS) {
      const accessibility = createEvidenceWorkspaceModel({ screenId }).accessibility;
      assert.equal(accessibility.semanticStructureRequired, true);
      assert.equal(accessibility.keyboardOperabilityRequired, true);
      assert.equal(accessibility.visibleFocusRequired, true);
      assert.equal(accessibility.screenReaderLabelsRequired, true);
      assert.equal(accessibility.errorIdentificationRequired, true);
      assert.equal(accessibility.contrastComplianceRequired, true);
    }
  });

  it('does not turn requirements into browser or accessibility evidence', () => {
    for (const screenId of EVIDENCE_WORKSPACE_SCREEN_IDS) {
      const accessibility = createEvidenceWorkspaceModel({ screenId }).accessibility;
      assert.equal(accessibility.browserVerification, 'NOT_EXECUTED');
      assert.equal(accessibility.automatedAccessibilityVerification, 'NOT_EXECUTED');
      assert.equal(accessibility.manualKeyboardVerification, 'NOT_EXECUTED');
      assert.equal(accessibility.screenReaderVerification, 'NOT_EXECUTED');
    }
  });

  it('keeps critical metadata inert without a control, handler or command', () => {
    const detail = createEvidenceWorkspaceModel({ screenId: 'EVD-002' });
    assert.equal(detail.screen.criticalAction, true);
    assert.deepEqual(detail.actions, []);
    assert.equal(detail.commandExecution, 'NOT_EXECUTED');
    assert.equal(detail.effectExecution, 'NOT_EXECUTED');
    assert.equal(detail.authorizationGranted, false);
    assert.equal(detail.decision, 'NOT_READY');
  });

  it('preserves role metadata without inferring UI or backend authorization', () => {
    for (const screenId of EVIDENCE_WORKSPACE_SCREEN_IDS) {
      const model = createEvidenceWorkspaceModel({ screenId });
      assert.ok(model.screen.roles.length > 0);
      assert.equal(model.authorizationGranted, false);
      assert.equal(model.authentication, 'NOT_EXECUTED');
      assert.equal(model.backendReauthenticationRequired, true);
      assert.equal(model.backendReauthorizationRequired, true);
    }
  });
});
