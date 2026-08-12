import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLICATION_REVIEW_SEMANTIC_IDS,
  createPublicationReviewWorkspaceModel,
} from '../../packages/web-ui/src/publication-review-workspace.ts';

describe('ST-0906 accessibility requirement projection', () => {
  it('projects one ordered landmark and region intent without claiming DOM implementation', () => {
    const model = createPublicationReviewWorkspaceModel({ screenId: 'REV-002' });
    assert.deepEqual(model.accessibility.semanticOrder, [
      'skip-link',
      'header',
      'main',
      'orientation',
      'blockers',
      'review',
      'diff',
      'preview',
      'status',
    ]);
    assert.equal(model.accessibility.h1.count, 1);
    assert.equal(model.accessibility.h1.level, 1);
    assert.equal(model.accessibility.h1.id, PUBLICATION_REVIEW_SEMANTIC_IDS.heading);
    const ids = model.accessibility.elements.map(({ id }) => id);
    assert.equal(new Set(ids).size, ids.length);
    assert.equal(model.accessibility.requirementsOnly, true);
    assert.equal(model.accessibility.conformanceClaimed, false);
  });

  it('keeps focus intent aligned with the calm utility information order', () => {
    const model = createPublicationReviewWorkspaceModel({ screenId: 'PUBA-002' });
    assert.deepEqual(model.accessibility.focusOrder, [
      PUBLICATION_REVIEW_SEMANTIC_IDS.skipLink,
      PUBLICATION_REVIEW_SEMANTIC_IDS.main,
      PUBLICATION_REVIEW_SEMANTIC_IDS.blockers,
      PUBLICATION_REVIEW_SEMANTIC_IDS.review,
      PUBLICATION_REVIEW_SEMANTIC_IDS.diff,
      PUBLICATION_REVIEW_SEMANTIC_IDS.preview,
    ]);
    assert.equal(model.accessibility.keyboardRequired, true);
    assert.equal(model.accessibility.screenReaderRequired, true);
    assert.equal(model.accessibility.visibleFocusRequired, true);
  });

  it('requires textual status and diff cues while implementing no motion or dialogs', () => {
    const model = createPublicationReviewWorkspaceModel({ screenId: 'PUBA-004' });
    assert.deepEqual(model.accessibility.statusPresentation, {
      textRequired: true,
      codeRequired: true,
      iconRequired: true,
      colorOnly: false,
    });
    assert.deepEqual(model.accessibility.diffPresentation, {
      addedLabelRequired: true,
      removedLabelRequired: true,
      changedLabelRequired: true,
      colorOnly: false,
    });
    assert.equal(model.accessibility.dialogImplemented, false);
    assert.equal(model.accessibility.stepUpDialogImplemented, false);
    assert.equal(model.accessibility.motion, 'NONE');
    assert.equal(model.accessibility.reducedMotion, 'NOT_APPLICABLE_NO_MOTION');
  });

  it('keeps browser, keyboard, screen-reader and formal evidence unexecuted', () => {
    const model = createPublicationReviewWorkspaceModel({ screenId: 'PUBA-003' });
    for (const status of Object.values(model.verification)) {
      assert.equal(status, 'NOT_EXECUTED');
    }
    assert.equal(model.acceptanceAchieved, false);
    assert.equal(model.storyComplete, false);
    assert.equal(model.productionEligible, false);
  });
});
