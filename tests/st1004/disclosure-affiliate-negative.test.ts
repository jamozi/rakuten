import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PublicDisclosureAffiliateError,
  createPublicDisclosureAffiliateCandidate,
  validatePublicDisclosureAffiliateCandidate,
} from '../../packages/web-ui/src/disclosure-affiliate-cta.ts';

const HASH = 'c'.repeat(64);

function input(): Record<string, unknown> {
  return {
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: {
      kind: 'SYNTHETIC_ST1004_SEMANTIC_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    },
  };
}

function error(operation: () => unknown): PublicDisclosureAffiliateError {
  try {
    operation();
  } catch (caught) {
    assert.ok(caught instanceof PublicDisclosureAffiliateError);
    assert.equal(caught.message, caught.code);
    assert.ok(Object.isFrozen(caught));
    return caught;
  }
  assert.fail('expected operation to fail');
}

function create(value: unknown) {
  return createPublicDisclosureAffiliateCandidate(value as never);
}

describe('ST-1004 strict negative boundary', () => {
  it('rejects malformed context and hashes with closed codes', () => {
    assert.equal(error(() => create(null)).code, 'PUBLIC_DISCLOSURE_INPUT_INVALID');
    assert.equal(
      error(() => create({ ...input(), screenId: 'PUB-005' })).code,
      'PUBLIC_DISCLOSURE_SCREEN_INVALID',
    );
    assert.equal(
      error(() => create({ ...input(), route: '/affiliate-disclosure' })).code,
      'PUBLIC_DISCLOSURE_ROUTE_INVALID',
    );
    const wrongKind = input();
    (wrongKind['coordinate'] as Record<string, unknown>)['kind'] = 'LIVE';
    assert.equal(error(() => create(wrongKind)).code, 'PUBLIC_DISCLOSURE_COORDINATE_INVALID');
    const upper = input();
    (upper['coordinate'] as Record<string, unknown>)['expectedSha256'] = 'A'.repeat(64);
    assert.equal(error(() => create(upper)).code, 'PUBLIC_DISCLOSURE_HASH_INVALID');
    const mismatch = input();
    (mismatch['coordinate'] as Record<string, unknown>)['observedSha256'] = 'd'.repeat(64);
    assert.equal(error(() => create(mismatch)).code, 'PUBLIC_DISCLOSURE_HASH_MISMATCH');
  });

  it('rejects copy, link values, references, internals, and effect surfaces without echo', () => {
    const cases: readonly [string, string, unknown][] = [
      ['disclosureCopy', 'PUBLIC_DISCLOSURE_COPY_PROHIBITED', 'secret-copy'],
      ['affiliateUrl', 'PUBLIC_DISCLOSURE_LINK_VALUE_PROHIBITED', 'https://example.invalid'],
      ['offerRef', 'PUBLIC_DISCLOSURE_REFERENCE_PROHIBITED', 'secret-offer'],
      ['financeRate', 'PUBLIC_DISCLOSURE_INTERNAL_FIELD_PROHIBITED', 4],
      ['clickBeacon', 'PUBLIC_DISCLOSURE_EFFECT_PROHIBITED', true],
    ];
    for (const [key, code, value] of cases) {
      const caught = error(() => create({ ...input(), [key]: value }));
      assert.equal(caught.code, code);
      assert.doesNotMatch(caught.message, /secret|example/i);
    }
  });

  it('rejects subclasses, accessors, symbols, cycles, and throwing proxies', () => {
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
      assert.equal(error(() => create(value)).code, 'PUBLIC_DISCLOSURE_INPUT_INVALID');
    }
    assert.equal(getterCalled, false);
  });

  it('rejects semantic and authority escalation and freezes successful candidates', () => {
    const valid = create(input());
    const semantics = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    const semanticRecord = semantics['semantics'] as Record<string, Record<string, unknown>>;
    semanticRecord['affiliateCta']!['enabled'] = true;
    assert.equal(
      error(() => validatePublicDisclosureAffiliateCandidate(semantics)).code,
      'PUBLIC_DISCLOSURE_SEMANTICS_INVALID',
    );

    const authority = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    const boundaries = authority['boundaries'] as Record<string, Record<string, unknown>>;
    boundaries['production']!['value'] = true;
    assert.equal(
      error(() => validatePublicDisclosureAffiliateCandidate(authority)).code,
      'PUBLIC_DISCLOSURE_AUTHORITY_INVALID',
    );

    assert.throws(() => {
      (valid.actions as unknown as unknown[]).push('navigate');
    }, TypeError);
    assert.throws(() => {
      (valid.semantics.affiliateCta as { enabled: boolean }).enabled = true;
    }, TypeError);
  });
});
