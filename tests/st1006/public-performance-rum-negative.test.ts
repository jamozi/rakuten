import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PublicPerformanceRumError,
  createPublicPerformanceRumCandidate,
  validatePublicPerformanceRumCandidate,
} from '../../packages/web-ui/src/public-performance-rum.ts';

const HASH = 'c'.repeat(64);

function input(): Record<string, unknown> {
  return {
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: {
      kind: 'SYNTHETIC_ST1006_PERFORMANCE_REQUIREMENTS_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    },
  };
}

function error(operation: () => unknown): PublicPerformanceRumError {
  try {
    operation();
  } catch (caught) {
    assert.ok(caught instanceof PublicPerformanceRumError);
    assert.equal(caught.message, caught.code);
    assert.ok(Object.isFrozen(caught));
    return caught;
  }
  assert.fail('expected operation to fail');
}

function create(value: unknown) {
  return createPublicPerformanceRumCandidate(value as never);
}

describe('ST-1006 strict negative boundary', () => {
  it('rejects malformed metadata and opaque coordinates with closed codes', () => {
    assert.equal(error(() => create(null)).code, 'PUBLIC_PERFORMANCE_RUM_INPUT_INVALID');
    assert.equal(
      error(() => create({ ...input(), screenId: 'PUB-004' })).code,
      'PUBLIC_PERFORMANCE_RUM_SCREEN_INVALID',
    );
    assert.equal(
      error(() => create({ ...input(), route: '/articles/live' })).code,
      'PUBLIC_PERFORMANCE_RUM_ROUTE_INVALID',
    );
    const wrongKind = input();
    (wrongKind['coordinate'] as Record<string, unknown>)['kind'] = 'LIVE';
    assert.equal(error(() => create(wrongKind)).code, 'PUBLIC_PERFORMANCE_RUM_COORDINATE_INVALID');
    const upper = input();
    (upper['coordinate'] as Record<string, unknown>)['expectedSha256'] = 'A'.repeat(64);
    assert.equal(error(() => create(upper)).code, 'PUBLIC_PERFORMANCE_RUM_HASH_INVALID');
    const mismatch = input();
    (mismatch['coordinate'] as Record<string, unknown>)['observedSha256'] = 'd'.repeat(64);
    assert.equal(error(() => create(mismatch)).code, 'PUBLIC_PERFORMANCE_RUM_HASH_MISMATCH');
  });

  it('rejects content, internal data, and executable or tracking surfaces', () => {
    const cases: readonly [string, string, unknown][] = [
      ['renderedHtml', 'PUBLIC_PERFORMANCE_RUM_CONTENT_PROHIBITED', '<script>secret</script>'],
      ['publicationId', 'PUBLIC_PERFORMANCE_RUM_INTERNAL_FIELD_PROHIBITED', 'secret-id'],
      ['performanceObserver', 'PUBLIC_PERFORMANCE_RUM_EFFECT_PROHIBITED', true],
      ['sendBeacon', 'PUBLIC_PERFORMANCE_RUM_EFFECT_PROHIBITED', true],
      ['consentState', 'PUBLIC_PERFORMANCE_RUM_EFFECT_PROHIBITED', 'GRANTED'],
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
      assert.equal(error(() => create(value)).code, 'PUBLIC_PERFORMANCE_RUM_INPUT_INVALID');
    }
    assert.equal(getterCalled, false);
  });

  it('rejects requirement, observation, privacy, and authority escalation', () => {
    const valid = create(input());

    const requirement = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    const targets = requirement['performanceTargets'] as Record<string, unknown>[];
    targets[0]!['observedValue'] = 1000;
    assert.equal(
      error(() => validatePublicPerformanceRumCandidate(requirement)).code,
      'PUBLIC_PERFORMANCE_RUM_REQUIREMENT_INVALID',
    );

    const observation = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    const observations = observation['observations'] as Record<string, unknown>;
    observations['metricValues'] = [1];
    assert.equal(
      error(() => validatePublicPerformanceRumCandidate(observation)).code,
      'PUBLIC_PERFORMANCE_RUM_OBSERVATION_INVALID',
    );

    const privacy = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    (privacy['privacy'] as Record<string, unknown>)['consentInferred'] = true;
    assert.equal(
      error(() => validatePublicPerformanceRumCandidate(privacy)).code,
      'PUBLIC_PERFORMANCE_RUM_PRIVACY_INVALID',
    );

    const authority = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    (authority['authorization'] as Record<string, unknown>)['production'] = true;
    assert.equal(
      error(() => validatePublicPerformanceRumCandidate(authority)).code,
      'PUBLIC_PERFORMANCE_RUM_AUTHORITY_INVALID',
    );

    assert.throws(() => {
      (valid.effects as unknown as unknown[]).push('emit');
    }, TypeError);
  });
});
