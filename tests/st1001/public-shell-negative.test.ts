import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PublicShellError,
  createPublicShellCandidate,
  validatePublicShellCandidate,
} from '../../packages/web-ui/src/public-shell.ts';

function modelError(operation: () => unknown): PublicShellError {
  try {
    operation();
  } catch (error) {
    assert.ok(error instanceof PublicShellError);
    assert.equal(error.message, error.code);
    assert.ok(Object.isFrozen(error));
    return error;
  }
  assert.fail('expected public-shell operation to fail');
}

interface MutableCandidate {
  [key: string]: unknown;
  screen: { route: string };
  metadata: { title: unknown };
  shell: {
    language: string;
    header: {
      id: string;
      navigationItems: [
        { id: string; route: string },
        { id: string; route: string },
        { id: string; route: string },
        { id: string; route: string },
      ];
    };
  };
  contentSlots: [{ renderedCopy: unknown }, ...{ renderedCopy: unknown }[]];
  boundaries: { routeRegistered: { value: boolean } };
}

function mutableCandidate(): MutableCandidate {
  return JSON.parse(
    JSON.stringify(createPublicShellCandidate({ screenId: 'PUB-004' })),
  ) as MutableCandidate;
}

describe('public-shell strict negative boundary', () => {
  it('rejects missing, unknown, mistyped and additional input without echo', () => {
    const canary = 'sensitive-public-shell-canary';
    const cases: readonly [unknown, string][] = [
      [null, 'PUBLIC_SHELL_INPUT_INVALID'],
      [[], 'PUBLIC_SHELL_INPUT_INVALID'],
      [{}, 'PUBLIC_SHELL_INPUT_INVALID'],
      [{ screenId: null }, 'PUBLIC_SHELL_INPUT_INVALID'],
      [{ screenId: 1 }, 'PUBLIC_SHELL_INPUT_INVALID'],
      [{ screenID: 'PUB-004' }, 'PUBLIC_SHELL_INPUT_INVALID'],
      [{ screenId: 'PUB-004', extra: canary }, 'PUBLIC_SHELL_INPUT_INVALID'],
      [{ screenId: canary }, 'PUBLIC_SHELL_SCREEN_UNKNOWN'],
      [{ screenId: 'pub-004' }, 'PUBLIC_SHELL_SCREEN_UNKNOWN'],
      [{ screenId: ' PUB-004' }, 'PUBLIC_SHELL_SCREEN_UNKNOWN'],
      [{ screenId: 'PUB-001' }, 'PUBLIC_SHELL_SCREEN_UNKNOWN'],
      [{ screenId: 'PUB-008' }, 'PUBLIC_SHELL_SCREEN_UNKNOWN'],
    ];
    for (const [value, expectedCode] of cases) {
      const error = modelError(() => createPublicShellCandidate(value as never));
      assert.equal(error.code, expectedCode);
      assert.doesNotMatch(error.message, new RegExp(canary));
    }
  });

  it('rejects subclasses, callbacks, symbols, accessors, hidden fields and dangerous keys', () => {
    const canary = 'hostile-public-shell-canary';
    class HostileInput {
      screenId = 'PUB-004';
    }
    const symbolInput = { screenId: 'PUB-004' } as Record<PropertyKey, unknown>;
    symbolInput[Symbol(canary)] = canary;
    let getterCalled = false;
    const accessorInput = {};
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
      value: 'PUB-004',
    });
    const dangerousInput = Object.create(null) as Record<string, unknown>;
    Object.defineProperty(dangerousInput, 'screenId', {
      enumerable: true,
      value: 'PUB-004',
    });
    Object.defineProperty(dangerousInput, '__proto__', {
      enumerable: true,
      value: canary,
    });

    for (const value of [
      new HostileInput(),
      symbolInput,
      accessorInput,
      hiddenInput,
      dangerousInput,
      { screenId: () => canary },
      { screenId: Symbol(canary) },
      { screenId: 1n },
    ]) {
      const error = modelError(() => createPublicShellCandidate(value as never));
      assert.equal(error.code, 'PUBLIC_SHELL_INPUT_INVALID');
      assert.doesNotMatch(error.message, new RegExp(canary));
    }
    assert.equal(getterCalled, false);
  });

  it('rejects metadata, accessibility, content and authority mutations with closed codes', () => {
    const cases: readonly [string, (candidate: MutableCandidate) => void][] = [
      [
        'PUBLIC_SHELL_METADATA_INVALID',
        (candidate) => {
          candidate['metadata']['title'] = 'Changed';
        },
      ],
      [
        'PUBLIC_SHELL_ACCESSIBILITY_INVALID',
        (candidate) => {
          candidate['shell']['language'] = 'en';
        },
      ],
      [
        'PUBLIC_SHELL_CONTENT_INVALID',
        (candidate) => {
          candidate['contentSlots'][0]['renderedCopy'] = 'invented';
        },
      ],
      [
        'PUBLIC_SHELL_AUTHORITY_INVALID',
        (candidate) => {
          candidate['boundaries']['routeRegistered']['value'] = true;
        },
      ],
    ];
    for (const [expectedCode, mutate] of cases) {
      for (const screenId of ['PUB-004', 'PUB-005', 'PUB-006', 'PUB-007'] as const) {
        const candidate = JSON.parse(
          JSON.stringify(createPublicShellCandidate({ screenId })),
        ) as MutableCandidate;
        mutate(candidate);
        assert.equal(modelError(() => validatePublicShellCandidate(candidate)).code, expectedCode);
      }
    }
  });

  it('rejects duplicate routes and IDs before accepting navigation', () => {
    const duplicateId = mutableCandidate();
    duplicateId['shell']['header']['navigationItems'][1]['id'] =
      duplicateId['shell']['header']['navigationItems'][0]['id'];
    assert.equal(
      modelError(() => validatePublicShellCandidate(duplicateId)).code,
      'PUBLIC_SHELL_DUPLICATE_ID',
    );

    const duplicateRoute = mutableCandidate();
    duplicateRoute['shell']['header']['navigationItems'][1]['route'] =
      duplicateRoute['shell']['header']['navigationItems'][0]['route'];
    assert.equal(
      modelError(() => validatePublicShellCandidate(duplicateRoute)).code,
      'PUBLIC_SHELL_DUPLICATE_ROUTE',
    );

    const duplicateLandmarkId = mutableCandidate();
    duplicateLandmarkId.shell.header.id = 'public-shell-main';
    assert.equal(
      modelError(() => validatePublicShellCandidate(duplicateLandmarkId)).code,
      'PUBLIC_SHELL_DUPLICATE_ID',
    );
  });

  it('rejects absolute origins, scripts, analytics, beacons, callbacks, CTA and article fields', () => {
    const cases: readonly ((candidate: MutableCandidate) => void)[] = [
      (candidate) => {
        candidate['screen']['route'] = 'https://example.invalid/editorial-policy';
      },
      (candidate) => {
        candidate['script'] = 'disabled';
      },
      (candidate) => {
        candidate['analytics'] = false;
      },
      (candidate) => {
        candidate['beacon'] = false;
      },
      (candidate) => {
        candidate['cookie'] = false;
      },
      (candidate) => {
        candidate['callback'] = 'forbidden';
      },
      (candidate) => {
        candidate['affiliate_link'] = null;
      },
      (candidate) => {
        candidate['cta'] = null;
      },
      (candidate) => {
        candidate['articleBody'] = null;
      },
      (candidate) => {
        candidate['articleTitle'] = null;
      },
    ];
    for (const mutate of cases) {
      const candidate = mutableCandidate();
      mutate(candidate);
      assert.equal(
        modelError(() => validatePublicShellCandidate(candidate)).code,
        'PUBLIC_SHELL_PROHIBITED_SURFACE',
      );
    }
  });

  it('returns detached immutable candidates and permits no authority escalation', () => {
    const candidate = createPublicShellCandidate({ screenId: 'PUB-007' });
    assert.throws(() => {
      (candidate.boundaries.production as { value: boolean }).value = true;
    }, TypeError);
    assert.throws(() => {
      (candidate.actions as unknown as unknown[]).push('publish');
    }, TypeError);
    assert.throws(() => {
      (candidate.contentSlots as unknown as unknown[]).push('copy');
    }, TypeError);
    assert.throws(() => {
      (candidate.shell.header.navigationItems as unknown as unknown[]).push('route');
    }, TypeError);
  });
});
