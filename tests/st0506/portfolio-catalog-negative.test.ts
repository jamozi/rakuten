import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  PortfolioCatalogModelError,
  createPortfolioCatalogWorkspaceModel,
} from '../../packages/web-ui/src/portfolio-catalog-workspace.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

function modelError(value: unknown): PortfolioCatalogModelError {
  try {
    createPortfolioCatalogWorkspaceModel(value as never);
  } catch (error) {
    assert.ok(error instanceof PortfolioCatalogModelError);
    return error;
  }
  assert.fail('expected portfolio/catalog model creation to fail');
}

describe('portfolio/catalog hostile boundary', () => {
  it('rejects missing, unknown, mistyped and additional fields without value echo', () => {
    const canary = 'sensitive-screen-canary';
    const cases = [
      [null, 'PORTFOLIO_CATALOG_INPUT_INVALID'],
      [[], 'PORTFOLIO_CATALOG_INPUT_INVALID'],
      [{}, 'PORTFOLIO_CATALOG_INPUT_INVALID'],
      [{ screenId: null }, 'PORTFOLIO_CATALOG_INPUT_INVALID'],
      [{ screenId: 1 }, 'PORTFOLIO_CATALOG_INPUT_INVALID'],
      [{ screenId: 'PORT-001', extra: canary }, 'PORTFOLIO_CATALOG_INPUT_INVALID'],
      [{ screenID: 'PORT-001' }, 'PORTFOLIO_CATALOG_INPUT_INVALID'],
      [{ screenId: canary }, 'PORTFOLIO_CATALOG_SCREEN_UNKNOWN'],
      [{ screenId: 'port-001' }, 'PORTFOLIO_CATALOG_SCREEN_UNKNOWN'],
      [{ screenId: ' PORT-001' }, 'PORTFOLIO_CATALOG_SCREEN_UNKNOWN'],
      [{ screenId: 'CAT-007' }, 'PORTFOLIO_CATALOG_SCREEN_UNKNOWN'],
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
    const symbolInput = { screenId: 'PORT-001' } as Record<PropertyKey, unknown>;
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
      value: 'PORT-001',
    });
    const cyclic: { screenId: string; self?: unknown } = { screenId: 'PORT-001' };
    cyclic.self = cyclic;
    class HostileInput {
      screenId = 'PORT-001';
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
      assert.equal(error.code, 'PORTFOLIO_CATALOG_INPUT_INVALID');
      assert.doesNotMatch(error.message, new RegExp(canary));
    }
    assert.equal(getterCalled, false);
  });

  it('does not expose mutable state or permit invented actions and finance data', () => {
    const model = createPortfolioCatalogWorkspaceModel({ screenId: 'CAT-003' });
    assert.throws(() => {
      (model as { availability: string }).availability = 'ENABLED';
    }, TypeError);
    assert.throws(() => {
      (model.actions as unknown as unknown[]).push('MERGE');
    }, TypeError);
    assert.throws(() => {
      (model.dataState.items as unknown as unknown[]).push({ revenue: 1 });
    }, TypeError);
    assert.throws(() => {
      (model.identityBoundary.merges as unknown as unknown[]).push('invented');
    }, TypeError);
    assert.doesNotMatch(
      JSON.stringify(model),
      /affiliateRate|commission|revenue|profit|margin|epc/i,
    );
  });

  it('keeps the source headless, direct-import-only and free of runtime effects', () => {
    const source = readFileSync(
      resolve(repositoryRoot, 'packages/web-ui/src/portfolio-catalog-workspace.ts'),
      'utf8',
    );
    const index = readFileSync(resolve(repositoryRoot, 'packages/web-ui/src/index.ts'), 'utf8');
    assert.doesNotMatch(index, /portfolio-catalog-workspace/);
    assert.doesNotMatch(source, /from ['"](?:react|next|next\/)/i);
    assert.doesNotMatch(source, /\.(?:jsx|tsx)['"]/i);
    assert.doesNotMatch(
      source,
      /\b(?:document|window|navigator|fetch|XMLHttpRequest|WebSocket|localStorage|sessionStorage)\b/,
    );
    assert.doesNotMatch(source, /\b(?:cookie|bearer|redirect|router|routeHandler)\b/i);
    assert.doesNotMatch(source, /\b(?:onClick|onSubmit|dispatch|mutate|save|remove)\b/);
  });
});
