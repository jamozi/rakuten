import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  AI_GOVERNANCE_RECORDED_FIXTURE_V2,
  AiGovernanceWorkspaceErrorV2,
  createAiGovernanceWorkspaceModelV2,
  validateAiGovernanceWorkspaceCandidateV2,
} from '../../packages/web-ui/src/ai-governance-workspace-v2.ts';

function expectError(operation: () => unknown, code: string): AiGovernanceWorkspaceErrorV2 {
  try {
    operation();
  } catch (error) {
    assert.ok(error instanceof AiGovernanceWorkspaceErrorV2);
    assert.equal(error.code, code);
    assert.equal(error.message, code);
    assert.ok(Object.isFrozen(error));
    return error;
  }
  assert.fail('expected ST-0709 V2 validation to fail');
}

type MutableJson = null | boolean | number | string | MutableJson[] | MutableRecord;
type MutableRecord = { [key: string]: MutableJson };

function mutableFixture(): MutableRecord {
  return JSON.parse(JSON.stringify(AI_GOVERNANCE_RECORDED_FIXTURE_V2)) as MutableRecord;
}

function mutableRecord(value: MutableJson | undefined): MutableRecord {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError('invalid test fixture record');
  }
  return value;
}

function mutableList(value: MutableJson | undefined): MutableJson[] {
  if (!Array.isArray(value)) {
    throw new TypeError('invalid test fixture list');
  }
  return value;
}

function row(candidate: MutableRecord, sectionIndex: number): MutableRecord {
  const section = mutableRecord(mutableList(candidate['sections'])[sectionIndex]);
  const table = mutableRecord(section['table']);
  return mutableRecord(mutableList(table['rows'])[0]);
}

describe('ST-0709 V2 hostile boundary', () => {
  it('rejects malformed and unknown screen input without rejected-value echo', () => {
    const canary = 'private-governance-canary';
    for (const input of [null, [], {}, { screenId: 1 }, { screenID: 'GOV-001' }]) {
      const error = expectError(
        () => createAiGovernanceWorkspaceModelV2(input as never),
        'AI_GOVERNANCE_V2_INPUT_INVALID',
      );
      assert.doesNotMatch(error.message, new RegExp(canary));
    }
    for (const input of [{ screenId: canary }, { screenId: 'gov-001' }, { screenId: ' GOV-001' }]) {
      const error = expectError(
        () => createAiGovernanceWorkspaceModelV2(input as never),
        'AI_GOVERNANCE_V2_SCREEN_UNKNOWN',
      );
      assert.doesNotMatch(error.message, new RegExp(canary));
    }
    expectError(
      () =>
        createAiGovernanceWorkspaceModelV2({
          screenId: 'GOV-001',
          extra: canary,
        } as never),
      'AI_GOVERNANCE_V2_INPUT_INVALID',
    );
  });

  it('never invokes accessors and rejects symbol, cycle, prototype and non-JSON input', () => {
    let getterCalled = false;
    const accessor = {};
    Object.defineProperty(accessor, 'screenId', {
      enumerable: true,
      get() {
        getterCalled = true;
        return 'GOV-001';
      },
    });
    const symbol = { screenId: 'GOV-001' } as Record<PropertyKey, unknown>;
    symbol[Symbol('hidden')] = 'hidden';
    const cycle: { screenId: string; self?: unknown } = { screenId: 'GOV-001' };
    cycle.self = cycle;
    class NonPlain {
      screenId = 'GOV-001';
    }
    for (const input of [accessor, symbol, cycle, new NonPlain(), { screenId: 1n }]) {
      expectError(
        () => createAiGovernanceWorkspaceModelV2(input as never),
        'AI_GOVERNANCE_V2_INPUT_INVALID',
      );
    }
    assert.equal(getterCalled, false);
  });

  it('rejects authority, action, release, route, raw-field and cost tampering', () => {
    const mutations = [
      (candidate: MutableRecord) => {
        mutableRecord(candidate['authority'])['release'] = true;
      },
      (candidate: MutableRecord) => {
        mutableRecord(candidate['releaseGuard'])['direct_activation'] = true;
      },
      (candidate: MutableRecord) => {
        const section = mutableRecord(mutableList(candidate['sections'])[0]);
        mutableList(section['actions']).push('activate');
      },
      (candidate: MutableRecord) => {
        mutableRecord(candidate['route'])['registration'] = 'REGISTERED';
      },
      (candidate: MutableRecord) => {
        row(candidate, 1)['promptBody'] = 'private-canary';
      },
      (candidate: MutableRecord) => {
        row(candidate, 2)['activationAuthorized'] = true;
      },
      (candidate: MutableRecord) => {
        row(candidate, 4)['outcome'] = 'PROPOSAL_REVIEW_REQUIRED';
      },
      (candidate: MutableRecord) => {
        row(candidate, 5)['observedActualCostJpy'] = 0;
      },
      (candidate: MutableRecord) => {
        row(candidate, 5)['unknownTreatedAsZero'] = true;
      },
    ];
    for (const mutate of mutations) {
      const candidate = mutableFixture();
      mutate(candidate);
      const error = expectError(
        () => validateAiGovernanceWorkspaceCandidateV2(candidate),
        'AI_GOVERNANCE_V2_CANDIDATE_INVALID',
      );
      assert.doesNotMatch(error.message, /private-canary/);
    }
  });

  it('exposes no mutable section, row, authority or binding state', () => {
    const model = createAiGovernanceWorkspaceModelV2({ screenId: 'GOV-001' });
    assert.throws(() => {
      (model.sections as unknown as unknown[]).push('invented');
    }, TypeError);
    assert.throws(() => {
      (model.sections[0]?.actions as unknown as unknown[]).push('activate');
    }, TypeError);
    assert.throws(() => {
      (model.authority as Record<string, unknown>)['release'] = true;
    }, TypeError);
    assert.throws(() => {
      (model.sourceBindings as unknown as unknown[]).push('invented');
    }, TypeError);
  });
});
