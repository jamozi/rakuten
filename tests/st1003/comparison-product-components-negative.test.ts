import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PublicComparisonComponentError,
  createPublicComparisonComponentsCandidate,
  validatePublicComparisonComponentsCandidate,
} from '../../packages/web-ui/src/comparison-product-components.ts';

const HASH = 'c'.repeat(64);

function input(): Record<string, unknown> {
  return {
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: {
      kind: 'SYNTHETIC_ST1003_SEMANTIC_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    },
  };
}

function error(operation: () => unknown): PublicComparisonComponentError {
  try {
    operation();
  } catch (caught) {
    assert.ok(caught instanceof PublicComparisonComponentError);
    assert.equal(caught.message, caught.code);
    assert.ok(Object.isFrozen(caught));
    return caught;
  }
  assert.fail('expected operation to fail');
}

function create(value: unknown) {
  return createPublicComparisonComponentsCandidate(value as never);
}

describe('ST-1003 strict negative boundary', () => {
  it('rejects malformed context and hashes with closed codes', () => {
    assert.equal(error(() => create(null)).code, 'PUBLIC_COMPONENT_INPUT_INVALID');
    assert.equal(
      error(() => create({ ...input(), screenId: 'PUB-004' })).code,
      'PUBLIC_COMPONENT_SCREEN_INVALID',
    );
    assert.equal(
      error(() => create({ ...input(), route: '/articles/demo' })).code,
      'PUBLIC_COMPONENT_ROUTE_INVALID',
    );
    const wrongKind = input();
    (wrongKind['coordinate'] as Record<string, unknown>)['kind'] = 'LIVE';
    assert.equal(error(() => create(wrongKind)).code, 'PUBLIC_COMPONENT_COORDINATE_INVALID');
    const upper = input();
    (upper['coordinate'] as Record<string, unknown>)['expectedSha256'] = 'A'.repeat(64);
    assert.equal(error(() => create(upper)).code, 'PUBLIC_COMPONENT_HASH_INVALID');
    const mismatch = input();
    (mismatch['coordinate'] as Record<string, unknown>)['observedSha256'] = 'd'.repeat(64);
    assert.equal(error(() => create(mismatch)).code, 'PUBLIC_COMPONENT_HASH_MISMATCH');
  });

  it('rejects values, references, internal fields, and active surfaces without echo', () => {
    const cases: readonly [string, string, unknown][] = [
      ['productName', 'PUBLIC_COMPONENT_CONTENT_PROHIBITED', 'secret-product'],
      ['subjectRef', 'PUBLIC_COMPONENT_REFERENCE_PROHIBITED', 'secret-ref'],
      ['financeRate', 'PUBLIC_COMPONENT_INTERNAL_FIELD_PROHIBITED', 4],
      ['affiliateUrl', 'PUBLIC_COMPONENT_PROHIBITED_SURFACE', 'https://example.invalid'],
    ];
    for (const [key, code, value] of cases) {
      const hostile = { ...input(), [key]: value };
      const caught = error(() => create(hostile));
      assert.equal(caught.code, code);
      assert.doesNotMatch(caught.message, /secret|example/i);
    }
  });

  it('rejects subclasses, accessors, symbols, cycles, and hostile proxies', () => {
    class HostileInput {
      screenId = 'PUB-003';
    }
    let getterCalled = false;
    const accessor = input();
    Object.defineProperty(accessor, 'route', {
      enumerable: true,
      get() {
        getterCalled = true;
        return '/articles/{slug}';
      },
    });
    const symbol = input() as Record<PropertyKey, unknown>;
    symbol[Symbol('hidden')] = true;
    const cycle = input();
    cycle['cycle'] = cycle;
    const proxy = new Proxy(input(), {
      ownKeys() {
        throw new TypeError('canary');
      },
    });
    for (const value of [new HostileInput(), accessor, symbol, cycle, proxy]) {
      assert.equal(error(() => create(value)).code, 'PUBLIC_COMPONENT_INPUT_INVALID');
    }
    assert.equal(getterCalled, false);
  });

  it('rejects semantic or authority escalation and freezes successful candidates', () => {
    const valid = create(input());
    const semantics = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    const semanticRecord = semantics['semantics'] as Record<string, Record<string, unknown>>;
    semanticRecord['unknownValue']!['value'] = 'invented';
    assert.equal(
      error(() => validatePublicComparisonComponentsCandidate(semantics)).code,
      'PUBLIC_COMPONENT_SEMANTICS_INVALID',
    );

    const authority = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    const boundaries = authority['boundaries'] as Record<string, Record<string, unknown>>;
    boundaries['production']!['value'] = true;
    assert.equal(
      error(() => validatePublicComparisonComponentsCandidate(authority)).code,
      'PUBLIC_COMPONENT_AUTHORITY_INVALID',
    );

    assert.throws(() => {
      (valid.actions as unknown as unknown[]).push('publish');
    }, TypeError);
    assert.throws(() => {
      (valid.semantics.unknownValue as { value: unknown }).value = 0;
    }, TypeError);
  });
});
