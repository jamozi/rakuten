import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  JsonValidationError,
  assertJsonValue,
  createJsonValue,
} from '../../packages/web-ui/src/serializable.ts';
import { UNBRANDED_TOKENS_V1 } from '../../packages/web-ui/src/tokens.ts';

function validationError(value: unknown): JsonValidationError {
  try {
    createJsonValue(value);
  } catch (error) {
    assert.ok(error instanceof JsonValidationError);
    return error;
  }
  assert.fail('expected JSON validation to fail');
}

describe('strict serializable values', () => {
  it('returns a detached, deeply frozen JSON value with stable round-trip bytes', () => {
    const source = {
      label: 'candidate',
      nested: [{ enabled: true, score: -0 }, null],
    };
    const created = createJsonValue(source);

    source.label = 'mutated';
    source.nested[0] = { enabled: false, score: 9 };

    assert.deepEqual(created, {
      label: 'candidate',
      nested: [{ enabled: true, score: 0 }, null],
    });
    assert.deepEqual(JSON.parse(JSON.stringify(created)), created);
    assert.ok(Object.isFrozen(created));
    assert.ok(Object.isFrozen((created as { readonly nested: readonly unknown[] }).nested));
    assert.ok(
      Object.isFrozen(
        (created as { readonly nested: readonly Record<string, unknown>[] }).nested[0],
      ),
    );
    assert.doesNotThrow(() => assertJsonValue(created));
  });

  it('accepts shared acyclic values but copies each occurrence', () => {
    const shared = { state: 'ready' };
    const created = createJsonValue({ first: shared, second: shared }) as {
      readonly first: object;
      readonly second: object;
    };

    assert.deepEqual(created.first, created.second);
    assert.notEqual(created.first, created.second);
  });

  it('rejects unsupported primitives and non-finite numbers without echoing values', () => {
    const secretCanary = 'rejected-secret-canary';
    const cases: readonly [unknown, string][] = [
      [undefined, 'JSON_UNSUPPORTED_TYPE'],
      [1n, 'JSON_UNSUPPORTED_TYPE'],
      [Symbol(secretCanary), 'JSON_UNSUPPORTED_TYPE'],
      [() => secretCanary, 'JSON_UNSUPPORTED_TYPE'],
      [Number.NaN, 'JSON_NON_FINITE_NUMBER'],
      [Number.POSITIVE_INFINITY, 'JSON_NON_FINITE_NUMBER'],
      [Number.NEGATIVE_INFINITY, 'JSON_NON_FINITE_NUMBER'],
    ];

    for (const [value, expectedCode] of cases) {
      const error = validationError(value);
      assert.equal(error.code, expectedCode);
      assert.equal(error.message, expectedCode);
      assert.doesNotMatch(error.message, new RegExp(secretCanary));
    }
  });

  it('rejects cycles, class instances, dates, and non-plain array subclasses', () => {
    const cyclic: { self?: unknown } = {};
    cyclic.self = cyclic;
    class HostileRecord {
      value = 'do-not-echo-class-value';
    }
    class HostileArray extends Array<unknown> {}

    assert.equal(validationError(cyclic).code, 'JSON_CYCLIC_REFERENCE');
    assert.equal(validationError(new HostileRecord()).code, 'JSON_NON_PLAIN_OBJECT');
    assert.equal(validationError(new Date(0)).code, 'JSON_NON_PLAIN_OBJECT');
    assert.equal(validationError(new HostileArray('x')).code, 'JSON_NON_PLAIN_OBJECT');
  });

  it('rejects dangerous keys, symbol keys, accessors, hidden properties, and sparse arrays', () => {
    const secretCanary = 'prototype-secret-canary';
    const dangerousKeyCases = [
      JSON.parse(`{"__proto__":"${secretCanary}"}`) as unknown,
      { constructor: secretCanary },
      { prototype: secretCanary },
    ];
    for (const value of dangerousKeyCases) {
      const error = validationError(value);
      assert.equal(error.code, 'JSON_DANGEROUS_KEY');
      assert.doesNotMatch(error.message, new RegExp(secretCanary));
    }

    const symbolRecord = { safe: true } as Record<PropertyKey, unknown>;
    symbolRecord[Symbol(secretCanary)] = secretCanary;
    assert.equal(validationError(symbolRecord).code, 'JSON_SYMBOL_KEY');

    let getterCalled = false;
    const accessorRecord = {};
    Object.defineProperty(accessorRecord, 'value', {
      enumerable: true,
      get() {
        getterCalled = true;
        throw new Error(secretCanary);
      },
    });
    assert.equal(validationError(accessorRecord).code, 'JSON_INVALID_PROPERTY');
    assert.equal(getterCalled, false);

    const hiddenRecord = {};
    Object.defineProperty(hiddenRecord, 'hidden', {
      enumerable: false,
      value: secretCanary,
    });
    assert.equal(validationError(hiddenRecord).code, 'JSON_INVALID_PROPERTY');

    assert.equal(validationError([, 'present']).code, 'JSON_INVALID_ARRAY');
    const decoratedArray: unknown[] & { extra?: string } = [];
    decoratedArray.extra = secretCanary;
    assert.equal(validationError(decoratedArray).code, 'JSON_INVALID_ARRAY');
  });
});

describe('UNBRANDED_TOKENS_V1', () => {
  it('is deeply frozen and JSON round-trip safe', () => {
    assert.deepEqual(JSON.parse(JSON.stringify(UNBRANDED_TOKENS_V1)), UNBRANDED_TOKENS_V1);
    assert.doesNotThrow(() => assertJsonValue(UNBRANDED_TOKENS_V1));
    assert.ok(Object.isFrozen(UNBRANDED_TOKENS_V1));
    assert.ok(Object.isFrozen(UNBRANDED_TOKENS_V1.semanticColor));
  });

  it('contains the exact semantic color and typography keys', () => {
    assert.deepEqual(Object.keys(UNBRANDED_TOKENS_V1.semanticColor).sort(), [
      'border',
      'danger',
      'info',
      'muted',
      'success',
      'surface',
      'text',
      'warning',
    ]);
    assert.deepEqual(Object.keys(UNBRANDED_TOKENS_V1.typography).sort(), [
      'body',
      'display',
      'heading',
      'label',
      'mono',
    ]);
    assert.equal(UNBRANDED_TOKENS_V1.schema, 'UNBRANDED_TOKENS_V1');
    assert.equal(UNBRANDED_TOKENS_V1.brandState, 'PROVISIONAL_UNBRANDED_OD_002');
  });

  it('uses a 4px spacing scale and neutral system fonts', () => {
    const spacing = Object.values(UNBRANDED_TOKENS_V1.spacingPx);
    assert.ok(spacing.includes(0));
    assert.ok(spacing.includes(4));
    assert.ok(spacing.every((value) => value % 4 === 0));
    assert.equal(UNBRANDED_TOKENS_V1.typography.body.fontFamily, 'system-ui, sans-serif');
    assert.equal(UNBRANDED_TOKENS_V1.typography.mono.fontFamily, 'ui-monospace, monospace');
  });

  it('pairs every status and severity color with stable text and icon names', () => {
    for (const collection of [UNBRANDED_TOKENS_V1.status, UNBRANDED_TOKENS_V1.severity]) {
      for (const token of Object.values(collection)) {
        assert.match(token.color, /^#[0-9A-F]{6}$/);
        assert.match(token.text, /^[A-Za-z][A-Za-z ]*$/);
        assert.match(token.icon, /^[a-z]+(?:-[a-z]+)*$/);
      }
    }
  });

  it('contains no brand, domain, or asset binding while OD-002 is unresolved', () => {
    const serialized = JSON.stringify(UNBRANDED_TOKENS_V1);
    assert.doesNotMatch(serialized, /rakuten|https?:|example\.invalid|logo|asset/i);
  });
});
