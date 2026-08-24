import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  FreshnessOperationsWorkspaceV2Error,
  createFreshnessOperationsReviewIntentV2,
  createFreshnessOperationsWorkspaceV2,
  validateFreshnessOperationsWorkspaceV2,
  type FreshnessOperationsWorkspaceV2ErrorCode,
  type FreshnessOperationsWorkspaceV2Input,
} from '../../packages/web-ui/src/index.ts';

function expectCode(operation: () => unknown, code: FreshnessOperationsWorkspaceV2ErrorCode): void {
  assert.throws(
    operation,
    (error: unknown) => error instanceof FreshnessOperationsWorkspaceV2Error && error.code === code,
  );
}

describe('ST-1103 V2 strict negative boundary', () => {
  it('rejects unknown, additional, executable, accessor, and cyclic input', () => {
    const accessor: Record<string, unknown> = {};
    Object.defineProperty(accessor, 'screenId', {
      enumerable: true,
      get: () => 'OPS-001',
    });
    const cycle: Record<string, unknown> = { screenId: 'OPS-001' };
    cycle['cycle'] = cycle;

    for (const input of [
      null,
      {},
      [],
      { screenId: 1 },
      { screenId: 'OPS-001', role: 'OPERATOR' },
      { screenId: 'OPS-001', callback: () => undefined },
      accessor,
      cycle,
    ]) {
      expectCode(
        () => createFreshnessOperationsWorkspaceV2(input as FreshnessOperationsWorkspaceV2Input),
        'FRESHNESS_OPERATIONS_V2_INPUT_INVALID',
      );
    }
    expectCode(
      () =>
        createFreshnessOperationsWorkspaceV2({
          screenId: 'OPS-999',
        } as unknown as FreshnessOperationsWorkspaceV2Input),
      'FRESHNESS_OPERATIONS_V2_SCREEN_UNKNOWN',
    );
  });

  it('rejects model and authority tampering without echoing rejected material', () => {
    const model = createFreshnessOperationsWorkspaceV2({ screenId: 'OPS-001' });
    const mutated = JSON.parse(JSON.stringify(model)) as Record<string, unknown>;
    (mutated['authority'] as Record<string, unknown>)['retryEnabled'] = true;

    expectCode(
      () => validateFreshnessOperationsWorkspaceV2(mutated),
      'FRESHNESS_OPERATIONS_V2_CANDIDATE_INVALID',
    );
  });

  it('rejects wrong target, reason, request identity, and unknown actions', () => {
    const model = createFreshnessOperationsWorkspaceV2({ screenId: 'OPS-001' });
    const descriptor = model.projection.actionDescriptors[0]!;
    const base = {
      screenId: 'OPS-001' as const,
      actionCode: descriptor.actionCode,
      targetFingerprint: descriptor.targetFingerprints[0]!,
      reasonCode: descriptor.reasonCodes[0]!,
      requestId: '44444444-4444-4444-8444-444444444444',
    };

    expectCode(
      () => createFreshnessOperationsReviewIntentV2({ ...base, targetFingerprint: 'f'.repeat(64) }),
      'FRESHNESS_OPERATIONS_V2_TARGET_INVALID',
    );
    expectCode(
      () => createFreshnessOperationsReviewIntentV2({ ...base, reasonCode: 'UNAPPROVED_REASON' }),
      'FRESHNESS_OPERATIONS_V2_REASON_INVALID',
    );
    expectCode(
      () => createFreshnessOperationsReviewIntentV2({ ...base, requestId: 'not-a-uuid' }),
      'FRESHNESS_OPERATIONS_V2_REQUEST_ID_INVALID',
    );
    expectCode(
      () => createFreshnessOperationsReviewIntentV2({ ...base, actionCode: 'UNKNOWN_ACTION' }),
      'FRESHNESS_OPERATIONS_V2_ACTION_UNKNOWN',
    );
  });
});
