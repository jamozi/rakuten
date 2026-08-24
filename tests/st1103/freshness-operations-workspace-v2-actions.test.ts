import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  FreshnessOperationsWorkspaceV2Error,
  createFreshnessOperationsReviewIntentV2,
  createFreshnessOperationsWorkspaceV2,
  validateFreshnessOperationsReviewIntentV2,
} from '../../packages/web-ui/src/index.ts';

describe('ST-1103 V2 safe action boundary', () => {
  it('creates only an effect-free freshness human-review intent', () => {
    const model = createFreshnessOperationsWorkspaceV2({ screenId: 'FRESH-001' });
    const descriptor = model.projection.actionDescriptors[0]!;
    const intent = createFreshnessOperationsReviewIntentV2({
      screenId: 'FRESH-001',
      actionCode: descriptor.actionCode,
      targetFingerprint: descriptor.targetFingerprints[0]!,
      reasonCode: 'STALE_EVIDENCE',
      requestId: '11111111-1111-4111-8111-111111111111',
    });

    assert.equal(intent.intentKind, 'HUMAN_REVIEW_REQUEST_ONLY');
    assert.equal(intent.effect, 'NONE');
    assert.equal(intent.dispatch, 'NOT_EXECUTED');
    assert.equal(intent.persistence, 'NOT_EXECUTED');
    assert.equal(intent.authorizationGranted, false);
    assert.equal(intent.mutationAuthorized, false);
    assert.equal(intent.publicationAuthorized, false);
    assert.equal(intent.productionAuthorized, false);
    assert.equal(Object.isFrozen(intent), true);
    assert.deepEqual(validateFreshnessOperationsReviewIntentV2(intent), intent);
  });

  it('permits recorded quarantine investigation but never a DLQ redrive', () => {
    const model = createFreshnessOperationsWorkspaceV2({ screenId: 'OPS-002' });
    const review = model.projection.actionDescriptors.find(
      (candidate) => candidate.actionCode === 'REQUEST_QUARANTINE_REVIEW',
    )!;
    const intent = createFreshnessOperationsReviewIntentV2({
      screenId: 'OPS-002',
      actionCode: review.actionCode,
      targetFingerprint: review.targetFingerprints[0]!,
      reasonCode: 'QUARANTINE_INVESTIGATION',
      requestId: '22222222-2222-4222-8222-222222222222',
    });
    assert.equal(intent.effect, 'NONE');

    assert.throws(
      () =>
        createFreshnessOperationsReviewIntentV2({
          screenId: 'OPS-002',
          actionCode: 'REQUEST_DLQ_REDRIVE',
          targetFingerprint: review.targetFingerprints[0]!,
          reasonCode: 'DLQ_REDRIVE_REVIEW',
          requestId: '33333333-3333-4333-8333-333333333333',
        }),
      (error: unknown) =>
        error instanceof FreshnessOperationsWorkspaceV2Error &&
        error.code === 'FRESHNESS_OPERATIONS_V2_ACTION_BLOCKED',
    );
  });

  it('keeps kill-switch review blocked behind its undeclared dependency and step-up', () => {
    const model = createFreshnessOperationsWorkspaceV2({ screenId: 'OPS-004' });
    const descriptor = model.projection.actionDescriptors[0]!;
    assert.equal(descriptor.availability, 'BLOCKED_DEPENDENCY');
    assert.equal(descriptor.futureEffectRequirements.stepUpRequired, true);
    assert.deepEqual(descriptor.targetFingerprints, []);
    assert.equal(model.authority.killSwitchEnabled, false);
    assert.equal(model.authority.stepUpEstablished, false);
  });
});
