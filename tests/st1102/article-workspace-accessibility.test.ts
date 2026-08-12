import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  ARTICLE_WORKSPACE_SCREEN_IDS,
  ARTICLE_WORKSPACE_SEMANTIC_IDS,
  createArticleWorkspaceCandidate,
} from '../../packages/web-ui/src/article-workspace.ts';

describe('article workspace accessibility metadata candidate', () => {
  it('pins semantic landmark and focus order with one H1 and stable unique IDs', () => {
    const model = createArticleWorkspaceCandidate({ screenId: 'EDT-002' });
    assert.deepEqual(model.accessibility.semanticOrder, [
      'skip-link',
      'header',
      'navigation',
      'main',
      'error-summary',
      'pane-region',
      'footer',
    ]);
    assert.deepEqual(
      model.accessibility.elements.map(({ kind, role }) => [kind, role]),
      [
        ['skip-link', 'link'],
        ['header', 'banner'],
        ['navigation', 'navigation'],
        ['main', 'main'],
        ['error-summary', 'alert'],
        ['pane-region', 'region'],
        ['footer', 'contentinfo'],
      ],
    );
    const ids = model.accessibility.elements.map(({ id }) => id);
    assert.equal(new Set(ids).size, ids.length);
    assert.deepEqual(model.accessibility.h1, {
      id: ARTICLE_WORKSPACE_SEMANTIC_IDS.heading,
      count: 1,
      level: 1,
      textSource: 'SCREEN_NAME',
    });
    assert.deepEqual(model.accessibility.focusOrder, [
      ARTICLE_WORKSPACE_SEMANTIC_IDS.skipLink,
      ARTICLE_WORKSPACE_SEMANTIC_IDS.main,
      ARTICLE_WORKSPACE_SEMANTIC_IDS.errorSummary,
      ARTICLE_WORKSPACE_SEMANTIC_IDS.paneRegion,
    ]);
  });

  it('requires keyboard, visible focus and screen-reader support without claiming proof', () => {
    for (const screenId of ARTICLE_WORKSPACE_SCREEN_IDS) {
      const accessibility = createArticleWorkspaceCandidate({ screenId }).accessibility;
      assert.equal(accessibility.candidateOnly, true);
      assert.equal(accessibility.keyboardRequired, true);
      assert.equal(accessibility.visibleFocusRequired, true);
      assert.equal(accessibility.screenReaderRequired, true);
      assert.equal(accessibility.motion, 'NONE');
    }
  });

  it('requires text, code and icon status cues and forbids color-only state', () => {
    const presentation = createArticleWorkspaceCandidate({
      screenId: 'EDT-007',
    }).accessibility.statusPresentation;
    assert.deepEqual(presentation, {
      textRequired: true,
      codeRequired: true,
      iconRequired: true,
      colorOnly: false,
    });
  });

  it('keeps critical EDT-006 metadata inert with no action', () => {
    const model = createArticleWorkspaceCandidate({ screenId: 'EDT-006' });
    assert.equal(model.screen.criticalAction, true);
    assert.deepEqual(model.actions, []);
    assert.equal(model.criticalActionExecutionEnabled, false);
    assert.equal(model.authorizationGranted, false);
  });
});
