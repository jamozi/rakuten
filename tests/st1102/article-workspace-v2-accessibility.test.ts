import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { createArticleWorkspaceV2 } from '../../packages/web-ui/src/article-workspace-v2.ts';

describe('ST-1102 V2 accessibility semantics', () => {
  it('provides stable unique semantics, one H1 and deterministic focus structure', () => {
    const model = createArticleWorkspaceV2({ screenId: 'EDT-002' });
    assert.deepEqual(model.accessibility.semanticOrder, [
      'skip-link',
      'header',
      'navigation',
      'main',
      'error-summary',
      'workspace-tabs',
      'pane-region',
      'footer',
    ]);
    const ids = Object.values(model.accessibility.semanticIds);
    assert.equal(ids.length, 10);
    assert.equal(new Set(ids).size, ids.length);
    assert.deepEqual(model.accessibility.h1, {
      count: 1,
      level: 1,
      textSource: 'SCREEN_NAME',
    });
    assert.deepEqual(model.accessibility.keyboardModel, [
      'Tab',
      'Shift+Tab',
      'ArrowLeft',
      'ArrowRight',
      'Home',
      'End',
      'Escape',
    ]);
  });

  it('uses text, code and icon cues and never color alone', () => {
    const model = createArticleWorkspaceV2({ screenId: 'EDT-002' });
    assert.equal(model.accessibility.statusTextPresent, true);
    assert.equal(model.accessibility.statusCodePresent, true);
    assert.equal(model.accessibility.statusIconPresent, true);
    assert.equal(model.accessibility.statusNotColorOnly, true);
    for (const pane of model.panes) {
      assert.equal(pane.statusCue.code, pane.status);
      assert.ok(pane.statusCue.text.length > 0);
      assert.match(pane.statusCue.icon, /^[a-z]+(?:-[a-z]+)*$/u);
      assert.equal(pane.statusCue.colorOnly, false);
    }
  });

  it('binds Claim table semantics without claiming browser or manual verification', () => {
    const model = createArticleWorkspaceV2({ screenId: 'EDT-006' });
    const claims = model.panes[0]?.payload;
    assert.equal(typeof claims?.['caption'], 'string');
    assert.equal(claims?.['rowHeaderColumn'], 'claim');
    const columns = claims?.['columns'];
    assert.ok(Array.isArray(columns));
    assert.ok(columns.length > 0);
    for (const rawColumn of columns) {
      const column = rawColumn as Record<string, unknown>;
      assert.equal(column['scope'], 'col');
      assert.equal(typeof column['label'], 'string');
    }
    assert.equal(model.accessibility.tableCaptionRequired, true);
    assert.equal(model.accessibility.columnHeadersRequired, true);
    assert.equal(model.accessibility.rowHeaderRequired, true);
    assert.equal(model.accessibility.zoomTargetPercent, 200);
    assert.equal(model.accessibility.rendered, false);
    assert.equal(model.accessibility.browserVerified, false);
    assert.equal(model.accessibility.screenReaderVerified, false);
    assert.equal(model.verification.TST_022, 'NOT_EXECUTED');
    assert.equal(model.verification.TST_024, 'NOT_EXECUTED');
  });
});
