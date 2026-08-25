import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  ArticleWorkspaceV2Error,
  createArticleWorkspaceV2,
  evaluateArticleWorkspaceEtagV2,
  evaluateArticleWorkspaceUnsavedGuardV2,
} from '../../packages/web-ui/src/article-workspace-v2.ts';

function workspaceError(operation: () => unknown): ArticleWorkspaceV2Error {
  try {
    operation();
  } catch (error) {
    assert.ok(error instanceof ArticleWorkspaceV2Error);
    return error;
  }
  assert.fail('expected ST-1102 V2 validation failure');
}

describe('ST-1102 V2 pure ETag and unsaved-change decisions', () => {
  it('models a missing If-Match as 428 without a command', () => {
    const observedEtag = createArticleWorkspaceV2({ screenId: 'EDT-003' }).concurrency.baselineEtag;
    const decision = evaluateArticleWorkspaceEtagV2({ ifMatch: null, observedEtag });
    assert.deepEqual(decision, {
      automaticMergeAllowed: false,
      classification: 'LOCAL_EFFECT_FREE_ETAG_DECISION_V2',
      code: 'PRECONDITION_REQUIRED',
      commandAvailable: false,
      conflictResolutionRequired: false,
      dispatch: 'NOT_EXECUTED',
      httpStatus: 428,
      ifMatch: null,
      matched: false,
      mutationAuthorized: false,
      observedEtag,
      overwriteAllowed: false,
      persistence: 'NOT_EXECUTED',
      publicationAuthorized: false,
      storyId: 'ST-1102',
    });
  });

  it('models exact match but never upgrades it to save authority', () => {
    const observedEtag = createArticleWorkspaceV2({ screenId: 'EDT-003' }).concurrency.baselineEtag;
    const decision = evaluateArticleWorkspaceEtagV2({
      ifMatch: observedEtag,
      observedEtag,
    });
    assert.equal(decision.code, 'MATCHED_NO_COMMAND');
    assert.equal(decision.httpStatus, null);
    assert.equal(decision.matched, true);
    assert.equal(decision.commandAvailable, false);
    assert.equal(decision.mutationAuthorized, false);
    assert.equal(decision.dispatch, 'NOT_EXECUTED');
    assert.equal(decision.persistence, 'NOT_EXECUTED');
  });

  it('models stale If-Match as 412 and requires explicit conflict resolution', () => {
    const model = createArticleWorkspaceV2({ screenId: 'EDT-003' });
    const stale = '"sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"';
    const decision = evaluateArticleWorkspaceEtagV2({
      ifMatch: stale,
      observedEtag: model.concurrency.baselineEtag,
    });
    assert.equal(decision.code, 'PRECONDITION_FAILED');
    assert.equal(decision.httpStatus, 412);
    assert.equal(decision.matched, false);
    assert.equal(decision.conflictResolutionRequired, true);
    assert.equal(decision.overwriteAllowed, false);
    assert.equal(decision.automaticMergeAllowed, false);
    assert.equal(decision.commandAvailable, false);
  });

  it('allows a clean modeled transition and blocks a dirty one without navigating', () => {
    const model = createArticleWorkspaceV2({ screenId: 'EDT-003' });
    const baseline = model.article['baselineAstSha256'];
    const proposal = model.article['proposalAstSha256'];
    if (typeof baseline !== 'string' || typeof proposal !== 'string') {
      assert.fail('recorded AST hashes must be strings');
    }
    const clean = evaluateArticleWorkspaceUnsavedGuardV2({
      baselineAstSha256: baseline,
      currentAstSha256: baseline,
      targetScreenId: 'EDT-006',
    });
    assert.equal(clean.dirty, false);
    assert.equal(clean.code, 'ALLOW_CLEAN');
    assert.equal(clean.dialogRequired, false);
    assert.equal(clean.focusTargetId, 'article-workspace-v2-main');
    assert.equal(clean.navigationPerformed, false);

    const dirty = evaluateArticleWorkspaceUnsavedGuardV2({
      baselineAstSha256: baseline,
      currentAstSha256: proposal,
      targetScreenId: 'EDT-006',
    });
    assert.equal(dirty.dirty, true);
    assert.equal(dirty.code, 'BLOCK_UNSAVED_CHANGES');
    assert.equal(dirty.dialogRequired, true);
    assert.equal(dirty.focusTargetId, 'article-workspace-v2-unsaved-dialog');
    assert.equal(dirty.navigationPerformed, false);
    assert.equal(dirty.navigationInterceptionImplemented, false);
    assert.equal(dirty.saveAuthorized, false);
    assert.equal(dirty.discardAuthorized, false);
    assert.equal(dirty.mutationAuthorized, false);
    assert.deepEqual(dirty.statusCue, {
      colorOnly: false,
      code: 'BLOCK_UNSAVED_CHANGES',
      icon: 'triangle-alert',
      text: 'Unsaved changes block navigation',
    });
  });

  it('rejects malformed/weak ETags, invalid hashes and unknown navigation targets', () => {
    assert.equal(
      workspaceError(() =>
        evaluateArticleWorkspaceEtagV2({ ifMatch: 'W/"weak"', observedEtag: '"strong"' }),
      ).code,
      'ARTICLE_WORKSPACE_V2_ETAG_INVALID',
    );
    assert.equal(
      workspaceError(() =>
        evaluateArticleWorkspaceEtagV2({
          ifMatch: '"strong"',
          observedEtag: '"strong"',
          extra: true,
        } as never),
      ).code,
      'ARTICLE_WORKSPACE_V2_ETAG_INPUT_INVALID',
    );
    assert.equal(
      workspaceError(() =>
        evaluateArticleWorkspaceUnsavedGuardV2({
          baselineAstSha256: 'not-a-hash',
          currentAstSha256: 'f'.repeat(64),
          targetScreenId: 'EDT-003',
        }),
      ).code,
      'ARTICLE_WORKSPACE_V2_AST_SHA256_INVALID',
    );
    assert.equal(
      workspaceError(() =>
        evaluateArticleWorkspaceUnsavedGuardV2({
          baselineAstSha256: 'e'.repeat(64),
          currentAstSha256: 'f'.repeat(64),
          targetScreenId: 'EDT-010',
        } as never),
      ).code,
      'ARTICLE_WORKSPACE_V2_SCREEN_UNKNOWN',
    );
  });
});
