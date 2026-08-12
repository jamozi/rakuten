import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLIC_COMPARISON_COMPONENT_CLASSIFICATION,
  PUBLIC_COMPARISON_COMPONENT_ERROR_CODES,
  PUBLIC_COMPARISON_COMPONENT_IDS,
  PUBLIC_COMPARISON_COMPONENT_SCREEN,
  PUBLIC_COMPARISON_COMPONENTS,
  createPublicComparisonComponentsCandidate,
} from '../../packages/web-ui/src/index.ts';

const HASH = 'a'.repeat(64);

describe('ST-1003 disabled semantic metadata contract', () => {
  it('pins the exact catalog components without claiming a tradeoff component ID', () => {
    assert.deepEqual(PUBLIC_COMPARISON_COMPONENT_IDS, ['UI-C032', 'UI-C033', 'UI-C036']);
    assert.deepEqual(
      PUBLIC_COMPARISON_COMPONENTS.map(({ id, name }) => ({ id, name })),
      [
        { id: 'UI-C032', name: 'ProductCard' },
        { id: 'UI-C033', name: 'ComparisonTable' },
        { id: 'UI-C036', name: 'UnknownValue' },
      ],
    );
    assert.ok(PUBLIC_COMPARISON_COMPONENTS.every((component) => component.keyboardRequired));
    assert.ok(PUBLIC_COMPARISON_COMPONENTS.every((component) => component.screenReaderRequired));
  });

  it('pins PUB-003 while leaving the route unregistered', () => {
    assert.equal(PUBLIC_COMPARISON_COMPONENT_SCREEN.id, 'PUB-003');
    assert.equal(PUBLIC_COMPARISON_COMPONENT_SCREEN.route, '/articles/{slug}');
    const candidate = createPublicComparisonComponentsCandidate({
      screenId: 'PUB-003',
      route: '/articles/{slug}',
      coordinate: {
        kind: 'SYNTHETIC_ST1003_SEMANTIC_FIXTURE',
        expectedSha256: HASH,
        observedSha256: HASH,
      },
    });
    assert.equal(candidate.classification, PUBLIC_COMPARISON_COMPONENT_CLASSIFICATION);
    assert.equal(candidate.route.routeRegistered, false);
    assert.equal(candidate.route.interactive, false);
  });

  it('deep-freezes exported screen metadata before candidate construction', () => {
    assert.ok(Object.isFrozen(PUBLIC_COMPARISON_COMPONENT_SCREEN));
    assert.ok(Object.isFrozen(PUBLIC_COMPARISON_COMPONENT_SCREEN.roles));
    assert.ok(Object.isFrozen(PUBLIC_COMPARISON_COMPONENT_SCREEN.apiDependencies));
    assert.throws(() => {
      (PUBLIC_COMPARISON_COMPONENT_SCREEN.roles as unknown as string[]).push('admin');
    }, TypeError);
    assert.throws(() => {
      (PUBLIC_COMPARISON_COMPONENT_SCREEN.apiDependencies as unknown as string[]).push(
        'LIVE_PROVIDER',
      );
    }, TypeError);
    assert.deepEqual(PUBLIC_COMPARISON_COMPONENT_SCREEN.roles, []);
    assert.deepEqual(PUBLIC_COMPARISON_COMPONENT_SCREEN.apiDependencies, []);
  });

  it('keeps a stable closed error vocabulary', () => {
    assert.equal(PUBLIC_COMPARISON_COMPONENT_ERROR_CODES.length, 14);
    assert.equal(new Set(PUBLIC_COMPARISON_COMPONENT_ERROR_CODES).size, 14);
  });
});
