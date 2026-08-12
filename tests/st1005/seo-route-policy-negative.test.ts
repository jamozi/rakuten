import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PublicSeoRoutePolicyError,
  createPublicSeoRoutePolicyCandidate,
  validatePublicSeoRoutePolicyCandidate,
} from '../../packages/web-ui/src/seo-route-policy.ts';

const HASH = 'c'.repeat(64);

function input(): Record<string, unknown> {
  return {
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: {
      kind: 'SYNTHETIC_ST1005_SEO_ROUTE_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    },
    origin: { mode: 'ROUTE_ONLY', callerSuppliedOrigin: null },
  };
}

function error(operation: () => unknown): PublicSeoRoutePolicyError {
  try {
    operation();
  } catch (caught) {
    assert.ok(caught instanceof PublicSeoRoutePolicyError);
    assert.equal(caught.message, caught.code);
    assert.ok(Object.isFrozen(caught));
    return caught;
  }
  assert.fail('expected operation to fail');
}

function create(value: unknown) {
  return createPublicSeoRoutePolicyCandidate(value as never);
}

describe('ST-1005 strict negative boundary', () => {
  it('rejects malformed context and opaque hash coordinates with closed codes', () => {
    assert.equal(error(() => create(null)).code, 'PUBLIC_SEO_ROUTE_INPUT_INVALID');
    assert.equal(
      error(() => create({ ...input(), screenId: 'PUB-004' })).code,
      'PUBLIC_SEO_ROUTE_SCREEN_INVALID',
    );
    assert.equal(
      error(() => create({ ...input(), route: '/articles/live' })).code,
      'PUBLIC_SEO_ROUTE_TEMPLATE_INVALID',
    );
    const wrongKind = input();
    (wrongKind['coordinate'] as Record<string, unknown>)['kind'] = 'LIVE';
    assert.equal(error(() => create(wrongKind)).code, 'PUBLIC_SEO_ROUTE_COORDINATE_INVALID');
    const upper = input();
    (upper['coordinate'] as Record<string, unknown>)['expectedSha256'] = 'A'.repeat(64);
    assert.equal(error(() => create(upper)).code, 'PUBLIC_SEO_ROUTE_HASH_INVALID');
    const mismatch = input();
    (mismatch['coordinate'] as Record<string, unknown>)['observedSha256'] = 'd'.repeat(64);
    assert.equal(error(() => create(mismatch)).code, 'PUBLIC_SEO_ROUTE_HASH_MISMATCH');
  });

  it('rejects origin-mode disagreement and every non-normalized or unsafe origin', () => {
    const routeOnlyWithOrigin = input();
    routeOnlyWithOrigin['origin'] = {
      mode: 'ROUTE_ONLY',
      callerSuppliedOrigin: 'https://example.invalid',
    };
    assert.equal(
      error(() => create(routeOnlyWithOrigin)).code,
      'PUBLIC_SEO_ROUTE_ORIGIN_MODE_MISMATCH',
    );
    const callerWithoutOrigin = input();
    callerWithoutOrigin['origin'] = { mode: 'CALLER_SUPPLIED_ORIGIN', callerSuppliedOrigin: null };
    assert.equal(
      error(() => create(callerWithoutOrigin)).code,
      'PUBLIC_SEO_ROUTE_ORIGIN_MODE_MISMATCH',
    );
    for (const origin of [
      'http://example.invalid',
      'https://user@example.invalid',
      'https://example.invalid/path',
      'https://example.invalid?query=1',
      'https://EXAMPLE.invalid',
      'https://example.invalid:443',
    ]) {
      const candidate = input();
      candidate['origin'] = { mode: 'CALLER_SUPPLIED_ORIGIN', callerSuppliedOrigin: origin };
      assert.equal(error(() => create(candidate)).code, 'PUBLIC_SEO_ROUTE_ORIGIN_INVALID');
    }
  });

  it('rejects content, internal, and effect surfaces without echoing hostile values', () => {
    const cases: readonly [string, string, unknown][] = [
      ['canonicalUrl', 'PUBLIC_SEO_ROUTE_CONTENT_PROHIBITED', 'https://secret.invalid'],
      ['renderedHtml', 'PUBLIC_SEO_ROUTE_CONTENT_PROHIBITED', '<script>secret</script>'],
      ['publicationId', 'PUBLIC_SEO_ROUTE_INTERNAL_FIELD_PROHIBITED', 'secret-publication'],
      ['publishCallback', 'PUBLIC_SEO_ROUTE_EFFECT_PROHIBITED', true],
    ];
    for (const [key, code, value] of cases) {
      const caught = error(() => create({ ...input(), [key]: value }));
      assert.equal(caught.code, code);
      assert.doesNotMatch(caught.message, /secret/i);
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
      assert.equal(error(() => create(value)).code, 'PUBLIC_SEO_ROUTE_INPUT_INVALID');
    }
    assert.equal(getterCalled, false);
  });

  it('rejects policy or authority escalation and leaves a valid result immutable', () => {
    const valid = create(input());
    const policy = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    const sitemap = policy['sitemap'] as Record<string, unknown>;
    sitemap['generated'] = true;
    assert.equal(
      error(() => validatePublicSeoRoutePolicyCandidate(policy)).code,
      'PUBLIC_SEO_ROUTE_POLICY_INVALID',
    );

    const authority = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    const authorization = authority['authorization'] as Record<string, unknown>;
    authorization['publication'] = true;
    assert.equal(
      error(() => validatePublicSeoRoutePolicyCandidate(authority)).code,
      'PUBLIC_SEO_ROUTE_AUTHORITY_INVALID',
    );

    assert.throws(() => {
      (valid.actions as unknown as unknown[]).push('publish');
    }, TypeError);
  });
});
