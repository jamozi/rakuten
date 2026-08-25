import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  PUBLICATION_REVIEW_SCREEN_IDS,
  createPublicationReviewWorkspaceV2,
  validatePublicationReviewWorkspaceV2,
} from '../../packages/web-ui/src/index.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

function assertDeeplyFrozen(value: unknown, visited = new WeakSet<object>()): void {
  if (value === null || typeof value !== 'object' || visited.has(value)) {
    return;
  }
  visited.add(value);
  assert.equal(Object.isFrozen(value), true);
  for (const child of Object.values(value)) {
    assertDeeplyFrozen(child, visited);
  }
}

describe('ST-0906 V2 recorded workspace model', () => {
  it('builds one deterministic deeply frozen local model for every canonical screen', () => {
    for (const screenId of PUBLICATION_REVIEW_SCREEN_IDS) {
      const first = createPublicationReviewWorkspaceV2({ screenId });
      const second = createPublicationReviewWorkspaceV2({ screenId });
      assert.deepEqual(first, second);
      assert.equal(first.screen.id, screenId);
      assert.deepEqual(first.screenOrder, PUBLICATION_REVIEW_SCREEN_IDS);
      assert.equal(first.localStatus, 'LOCAL_IMPLEMENTATION_COMPLETE');
      assert.deepEqual(first.canonicalStatus, {
        implementation: 'NOT_STARTED',
        verification: 'NOT_EXECUTED',
      });
      assertDeeplyFrozen(first);
      assert.deepEqual(
        validatePublicationReviewWorkspaceV2(JSON.parse(JSON.stringify(first))),
        first,
      );
    }
  });

  it('projects exact recorded review, approval, immutable snapshot, diff and preview state', () => {
    const model = createPublicationReviewWorkspaceV2({ screenId: 'REV-003' });
    assert.equal(model.review.assignmentState, 'COMPLETED');
    assert.equal(model.review.reviewDecision, 'APPROVE');
    assert.equal(model.review.checklistStatus, 'ALL_PASS');
    assert.equal(model.review.finalApprovalAuthorizedByReview, false);

    assert.equal(model.finalApproval.state, 'RECORDED_SYNTHETIC_APPROVED');
    assert.equal(model.finalApproval.actorKind, 'HUMAN');
    assert.equal(model.finalApproval.actorStatus, 'ACTIVE');
    assert.equal(model.finalApproval.actorRole, 'MANAGING_EDITOR');
    assert.match(model.finalApproval.mfaState, /^SATISFIED_RECORDED_SYNTHETIC$/u);
    assert.match(model.finalApproval.stepUpState, /^SATISFIED_RECORDED_SYNTHETIC$/u);
    assert.deepEqual(model.finalApproval.openBlockingFindingIds, []);
    assert.equal(model.finalApproval.realFinalApprovalAuthorized, false);

    assert.equal(model.snapshot.state, 'IMMUTABLE_RECORDED_CANDIDATE');
    assert.equal(model.snapshot.immutable, true);
    assert.equal(model.snapshot.readiness, 'NOT_READY');
    assert.equal(
      model.snapshot.compatibility,
      'CONTENT_AST_V1_BOUND_LEGACY_SCHEMA_RECONCILIATION_REQUIRED',
    );
    assert.equal(model.diff.bindingIntegrity, 'EXACT_RECORDED_BINDINGS_VERIFIED');
    assert.equal(model.diff.contentHashEquality, 'NOT_ESTABLISHED_RECONCILIATION_REQUIRED');
    assert.equal(model.diff.rows.length, 10);
    assert.equal(model.preview.blocks.length, 9);
    assert.equal(model.preview.productCardCount, 0);
    assert.equal(model.preview.offerCount, 0);
    assert.equal(model.preview.routeActivated, false);
    assert.equal(model.preview.publicReadServed, false);
  });

  it('keeps the V1 predecessor byte-identical while adding only an additive V2 API', () => {
    const digest = createHash('sha256')
      .update(
        readFileSync(
          resolve(repositoryRoot, 'packages/web-ui/src/publication-review-workspace.ts'),
        ),
      )
      .digest('hex');
    assert.equal(digest, '7c3e19a674dafc3acf660bad8f436185bbaf794661a5eb0ccec999b886a06a23');
  });
});
