import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  EvidenceWorkspaceModelError,
  createEvidenceWorkspaceModel,
} from '../../packages/web-ui/src/evidence-workspace.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

function modelError(value: unknown): EvidenceWorkspaceModelError {
  try {
    createEvidenceWorkspaceModel(value as never);
  } catch (error) {
    assert.ok(error instanceof EvidenceWorkspaceModelError);
    return error;
  }
  assert.fail('expected evidence workspace model creation to fail');
}

describe('evidence-workspace hostile boundary', () => {
  it('rejects missing, unknown, mistyped and additional input fields without value echo', () => {
    const canary = 'sensitive-screen-canary';
    const cases = [
      [null, 'EVIDENCE_WORKSPACE_INPUT_INVALID'],
      [[], 'EVIDENCE_WORKSPACE_INPUT_INVALID'],
      [{}, 'EVIDENCE_WORKSPACE_INPUT_INVALID'],
      [{ screenId: null }, 'EVIDENCE_WORKSPACE_INPUT_INVALID'],
      [{ screenId: 1 }, 'EVIDENCE_WORKSPACE_INPUT_INVALID'],
      [{ screenId: 'EVD-001', extra: canary }, 'EVIDENCE_WORKSPACE_INPUT_INVALID'],
      [{ screenID: 'EVD-001' }, 'EVIDENCE_WORKSPACE_INPUT_INVALID'],
      [{ screenId: canary }, 'EVIDENCE_WORKSPACE_SCREEN_UNKNOWN'],
      [{ screenId: 'evd-001' }, 'EVIDENCE_WORKSPACE_SCREEN_UNKNOWN'],
      [{ screenId: ' EVD-001' }, 'EVIDENCE_WORKSPACE_SCREEN_UNKNOWN'],
      [{ screenId: 'EVD-005' }, 'EVIDENCE_WORKSPACE_SCREEN_UNKNOWN'],
    ] as const;
    for (const [value, expectedCode] of cases) {
      const error = modelError(value);
      assert.equal(error.code, expectedCode);
      assert.equal(error.message, expectedCode);
      assert.doesNotMatch(error.message, new RegExp(canary));
      assert.ok(Object.isFrozen(error));
    }
  });

  it('rejects non-JSON, prototype, symbol, accessor, hidden and cyclic input', () => {
    const canary = 'hostile-input-canary';
    const symbolInput = { screenId: 'EVD-001' } as Record<PropertyKey, unknown>;
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
      value: 'EVD-001',
    });
    const cyclic: { screenId: string; self?: unknown } = { screenId: 'EVD-001' };
    cyclic.self = cyclic;
    class HostileInput {
      screenId = 'EVD-001';
    }

    for (const value of [
      symbolInput,
      accessorInput,
      hiddenInput,
      cyclic,
      new HostileInput(),
      { screenId: () => canary },
      { screenId: Symbol(canary) },
    ]) {
      const error = modelError(value);
      assert.equal(error.code, 'EVIDENCE_WORKSPACE_INPUT_INVALID');
      assert.doesNotMatch(error.message, new RegExp(canary));
    }
    assert.equal(getterCalled, false);
  });

  it('does not expose mutable model, collection, screen or binding state', () => {
    const model = createEvidenceWorkspaceModel({ screenId: 'EVD-002' });
    assert.throws(() => {
      (model as { availability: string }).availability = 'ENABLED';
    }, TypeError);
    assert.throws(() => {
      (model.dataState.items as unknown as unknown[]).push('invented');
    }, TypeError);
    assert.throws(() => {
      (model.screen.roles as string[]).push('PRODUCT_OWNER');
    }, TypeError);
    assert.throws(() => {
      (model.sourceBindings[0]?.artifacts as unknown[]).push('invented');
    }, TypeError);
  });

  it('keeps production source headless and free of routes, browser, data and effects', () => {
    const source = readFileSync(
      resolve(repositoryRoot, 'packages/web-ui/src/evidence-workspace.ts'),
      'utf8',
    );
    assert.doesNotMatch(source, /from ['"](?:react|next|next\/)/i);
    assert.doesNotMatch(source, /\.(?:jsx|tsx)['"]/i);
    assert.doesNotMatch(
      source,
      /\b(?:document|window|navigator|fetch|XMLHttpRequest|WebSocket|localStorage|sessionStorage)\b/,
    );
    assert.doesNotMatch(
      source,
      /\b(?:cookie|bearer|authorization|redirect|router|routeHandler)\b/i,
    );
    assert.doesNotMatch(source, /\b(?:EDT-006|CAT-006|UI-C021)\b/);
    assert.doesNotMatch(
      source,
      /\b(?:onClick|onSubmit|execute|dispatch|mutate|persist|save|delete)\b/,
    );
  });
});
