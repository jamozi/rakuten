import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  AiGovernanceModelError,
  createAiGovernanceWorkspaceModel,
} from '../../packages/web-ui/src/ai-governance-workspace.ts';

function modelError(value: unknown): AiGovernanceModelError {
  try {
    createAiGovernanceWorkspaceModel(value as never);
  } catch (error) {
    assert.ok(error instanceof AiGovernanceModelError);
    return error;
  }
  assert.fail('expected AI governance model creation to fail');
}

describe('AI governance hostile input boundary', () => {
  it('rejects missing, unknown, mistyped and additional fields without echo', () => {
    const canary = 'sensitive-governance-canary';
    const cases = [
      [null, 'AI_GOVERNANCE_INPUT_INVALID'],
      [[], 'AI_GOVERNANCE_INPUT_INVALID'],
      [{}, 'AI_GOVERNANCE_INPUT_INVALID'],
      [{ screenId: null }, 'AI_GOVERNANCE_INPUT_INVALID'],
      [{ screenId: 1 }, 'AI_GOVERNANCE_INPUT_INVALID'],
      [{ screenID: 'GOV-001' }, 'AI_GOVERNANCE_INPUT_INVALID'],
      [{ screenId: 'GOV-001', extra: canary }, 'AI_GOVERNANCE_INPUT_INVALID'],
      [{ screenId: canary }, 'AI_GOVERNANCE_SCREEN_UNKNOWN'],
      [{ screenId: 'gov-001' }, 'AI_GOVERNANCE_SCREEN_UNKNOWN'],
      [{ screenId: ' GOV-001' }, 'AI_GOVERNANCE_SCREEN_UNKNOWN'],
      [{ screenId: 'GOV-002' }, 'AI_GOVERNANCE_SCREEN_UNKNOWN'],
    ] as const;

    for (const [value, expectedCode] of cases) {
      const error = modelError(value);
      assert.equal(error.code, expectedCode);
      assert.equal(error.message, expectedCode);
      assert.doesNotMatch(error.message, new RegExp(canary));
      assert.ok(Object.isFrozen(error));
    }
  });

  it('rejects non-JSON, prototype, symbol, accessor, hidden, cyclic and dangerous-key input', () => {
    const canary = 'hostile-governance-canary';
    const symbolInput = { screenId: 'GOV-001' } as Record<PropertyKey, unknown>;
    symbolInput[Symbol(canary)] = canary;

    const accessorInput = {};
    let getterCalled = false;
    Object.defineProperty(accessorInput, 'screenId', {
      enumerable: true,
      get() {
        getterCalled = true;
        return canary;
      },
    });

    const hiddenInput = {};
    Object.defineProperty(hiddenInput, 'screenId', {
      enumerable: false,
      value: 'GOV-001',
    });

    const cyclic: { screenId: string; self?: unknown } = { screenId: 'GOV-001' };
    cyclic.self = cyclic;

    const dangerousInput = Object.create(null) as Record<string, unknown>;
    Object.defineProperty(dangerousInput, 'screenId', {
      enumerable: true,
      value: 'GOV-001',
    });
    Object.defineProperty(dangerousInput, '__proto__', {
      enumerable: true,
      value: canary,
    });

    class HostileInput {
      screenId = 'GOV-001';
    }

    for (const value of [
      symbolInput,
      accessorInput,
      hiddenInput,
      cyclic,
      dangerousInput,
      new HostileInput(),
      { screenId: () => canary },
      { screenId: Symbol(canary) },
      { screenId: 1n },
    ]) {
      const error = modelError(value);
      assert.equal(error.code, 'AI_GOVERNANCE_INPUT_INVALID');
      assert.equal(error.message, 'AI_GOVERNANCE_INPUT_INVALID');
      assert.doesNotMatch(error.message, new RegExp(canary));
    }
    assert.equal(getterCalled, false);
  });

  it('exposes no mutable model, collection, metadata, section, or binding state', () => {
    const model = createAiGovernanceWorkspaceModel({ screenId: 'GOV-001' });
    assert.throws(() => {
      (model as { availability: string }).availability = 'ENABLED';
    }, TypeError);
    assert.throws(() => {
      (model.actions as unknown as unknown[]).push('activate');
    }, TypeError);
    assert.throws(() => {
      (model.screen.roles as string[]).push('EDITOR');
    }, TypeError);
    assert.throws(() => {
      (model.sections[0]?.records as unknown as unknown[]).push('invented');
    }, TypeError);
    assert.throws(() => {
      (model.sourceBindings[0]?.artifacts as unknown[]).push('invented');
    }, TypeError);
  });
});
