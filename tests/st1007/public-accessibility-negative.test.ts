import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PublicAccessibilityAcceptanceError,
  createPublicAccessibilityAcceptanceCandidate,
  validatePublicAccessibilityAcceptanceCandidate,
} from '../../packages/web-ui/src/public-accessibility-acceptance.ts';

const HASH = 'c'.repeat(64);

function input(): Record<string, unknown> {
  return {
    storyId: 'ST-1007',
    coordinate: {
      kind: 'SYNTHETIC_ST1007_ACCESSIBILITY_REQUIREMENTS_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    },
  };
}

function error(operation: () => unknown): PublicAccessibilityAcceptanceError {
  try {
    operation();
  } catch (caught) {
    assert.ok(caught instanceof PublicAccessibilityAcceptanceError);
    assert.equal(caught.message, caught.code);
    assert.ok(Object.isFrozen(caught));
    return caught;
  }
  assert.fail('expected operation to fail');
}

function create(value: unknown) {
  return createPublicAccessibilityAcceptanceCandidate(value as never);
}

describe('ST-1007 strict negative boundary', () => {
  it('rejects malformed story and opaque coordinates with closed codes', () => {
    assert.equal(error(() => create(null)).code, 'PUBLIC_ACCESSIBILITY_INPUT_INVALID');
    assert.equal(
      error(() => create({ ...input(), storyId: 'ST-1006' })).code,
      'PUBLIC_ACCESSIBILITY_STORY_INVALID',
    );
    const wrongKind = input();
    (wrongKind['coordinate'] as Record<string, unknown>)['kind'] = 'LIVE_EVIDENCE';
    assert.equal(error(() => create(wrongKind)).code, 'PUBLIC_ACCESSIBILITY_COORDINATE_INVALID');
    const upper = input();
    (upper['coordinate'] as Record<string, unknown>)['expectedSha256'] = 'A'.repeat(64);
    assert.equal(error(() => create(upper)).code, 'PUBLIC_ACCESSIBILITY_HASH_INVALID');
    const mismatch = input();
    (mismatch['coordinate'] as Record<string, unknown>)['observedSha256'] = 'd'.repeat(64);
    assert.equal(error(() => create(mismatch)).code, 'PUBLIC_ACCESSIBILITY_HASH_MISMATCH');
  });

  it('rejects content, internal data, claimed evidence, effects, and authority', () => {
    const cases: readonly [string, string, unknown][] = [
      ['renderedHtml', 'PUBLIC_ACCESSIBILITY_CONTENT_PROHIBITED', '<script>secret</script>'],
      ['finance', 'PUBLIC_ACCESSIBILITY_INTERNAL_FIELD_PROHIBITED', 'secret'],
      ['evidenceRefs', 'PUBLIC_ACCESSIBILITY_EVIDENCE_PROHIBITED', ['fake-pass']],
      ['browserExecuted', 'PUBLIC_ACCESSIBILITY_EVIDENCE_PROHIBITED', true],
      ['fetchHandler', 'PUBLIC_ACCESSIBILITY_EFFECT_PROHIBITED', true],
      ['approval', 'PUBLIC_ACCESSIBILITY_AUTHORITY_INVALID', true],
    ];
    for (const [key, code, value] of cases) {
      const caught = error(() => create({ ...input(), [key]: value }));
      assert.equal(caught.code, code);
      assert.doesNotMatch(caught.message, /secret|fake-pass/i);
    }
  });

  it('rejects subclasses, accessors, symbols, cycles, and throwing proxies', () => {
    class HostileInput {
      storyId = 'ST-1007';
    }
    let getterCalled = false;
    const accessor = input();
    Object.defineProperty(accessor, 'storyId', {
      enumerable: true,
      get() {
        getterCalled = true;
        return 'ST-1007';
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
      assert.equal(error(() => create(value)).code, 'PUBLIC_ACCESSIBILITY_INPUT_INVALID');
    }
    assert.equal(getterCalled, false);
  });

  it('rejects invented passes, evidence execution, catalog drift, and authority escalation', () => {
    const valid = create(input());

    const checklist = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    const assessments = checklist['checklistAssessments'] as Record<string, unknown>[];
    assessments[0]!['verificationResult'] = 'PASS';
    assert.equal(
      error(() => validatePublicAccessibilityAcceptanceCandidate(checklist)).code,
      'PUBLIC_ACCESSIBILITY_CHECKLIST_INVALID',
    );

    const evidence = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    (evidence['evidenceState'] as Record<string, unknown>)['browserExecuted'] = true;
    assert.equal(
      error(() => validatePublicAccessibilityAcceptanceCandidate(evidence)).code,
      'PUBLIC_ACCESSIBILITY_EVIDENCE_STATE_INVALID',
    );

    const catalog = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    const catalogValue = catalog['catalog'] as Record<string, unknown>;
    (catalogValue['screens'] as Record<string, unknown>[]).pop();
    assert.equal(
      error(() => validatePublicAccessibilityAcceptanceCandidate(catalog)).code,
      'PUBLIC_ACCESSIBILITY_CATALOG_INVALID',
    );

    const authority = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    (authority['authorization'] as Record<string, unknown>)['accessibilityConformance'] = true;
    assert.equal(
      error(() => validatePublicAccessibilityAcceptanceCandidate(authority)).code,
      'PUBLIC_ACCESSIBILITY_AUTHORITY_INVALID',
    );

    assert.throws(() => {
      (valid.effects as unknown as unknown[]).push('emit');
    }, TypeError);
  });
});
