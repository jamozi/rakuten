import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  FreshnessOperationsWorkspaceError,
  createFreshnessOperationsWorkspaceCandidate,
  validateFreshnessOperationsWorkspaceCandidate,
  type FreshnessOperationsWorkspaceErrorCode,
  type FreshnessOperationsWorkspaceInput,
} from '../../packages/web-ui/src/index.ts';

function expectCode(operation: () => unknown, code: FreshnessOperationsWorkspaceErrorCode): void {
  assert.throws(
    operation,
    (error: unknown) => error instanceof FreshnessOperationsWorkspaceError && error.code === code,
  );
}

function mutableCandidate(): Record<string, unknown> {
  const candidate = createFreshnessOperationsWorkspaceCandidate({ screenId: 'FRESH-001' });
  return JSON.parse(JSON.stringify(candidate)) as unknown as Record<string, unknown>;
}

describe('ST-1103 strict negative boundary', () => {
  it('rejects missing, unknown, mistyped, and additional input fields', () => {
    for (const input of [
      null,
      {},
      [],
      { screenId: 1 },
      { screenId: 'FRESH-001', role: 'EDITOR' },
    ]) {
      expectCode(
        () =>
          createFreshnessOperationsWorkspaceCandidate(input as FreshnessOperationsWorkspaceInput),
        'FRESHNESS_OPERATIONS_INPUT_INVALID',
      );
    }
    expectCode(
      () =>
        createFreshnessOperationsWorkspaceCandidate({
          screenId: 'FRESH-999',
        } as unknown as FreshnessOperationsWorkspaceInput),
      'FRESHNESS_OPERATIONS_SCREEN_UNKNOWN',
    );
  });

  it('rejects subclasses, accessors, symbols, cycles, and callbacks', () => {
    class InputSubclass {
      screenId = 'FRESH-001';
    }
    const accessor = {} as Record<string, unknown>;
    Object.defineProperty(accessor, 'screenId', {
      enumerable: true,
      get: () => 'FRESH-001',
    });
    const symbol = { screenId: 'FRESH-001', [Symbol('hidden')]: true };
    const cycle: Record<string, unknown> = { screenId: 'FRESH-001' };
    cycle['cycle'] = cycle;
    const callback = { screenId: 'FRESH-001', callback: () => undefined };

    for (const input of [new InputSubclass(), accessor, symbol, cycle, callback]) {
      expectCode(
        () =>
          createFreshnessOperationsWorkspaceCandidate(input as FreshnessOperationsWorkspaceInput),
        'FRESHNESS_OPERATIONS_INPUT_INVALID',
      );
    }
  });

  it('fails closed for throwing and revoked unreadable proxies', () => {
    const throwing = new Proxy(
      { screenId: 'FRESH-001' },
      {
        ownKeys() {
          throw new TypeError('canary');
        },
      },
    );
    const revocable = Proxy.revocable({ screenId: 'FRESH-001' }, {});
    revocable.revoke();

    for (const input of [throwing, revocable.proxy]) {
      expectCode(
        () =>
          createFreshnessOperationsWorkspaceCandidate(input as FreshnessOperationsWorkspaceInput),
        'FRESHNESS_OPERATIONS_INPUT_INVALID',
      );
    }
  });

  it('rejects metadata, state, accessibility, and authority tampering', () => {
    const metadata = mutableCandidate();
    (metadata['screen'] as Record<string, unknown>)['route'] = '/admin/other';
    expectCode(
      () => validateFreshnessOperationsWorkspaceCandidate(metadata),
      'FRESHNESS_OPERATIONS_METADATA_INVALID',
    );

    const state = mutableCandidate();
    ((state['dataSlots'] as Record<string, unknown>)['primary'] as Record<string, unknown>)[
      'status'
    ] = 'LOADED';
    expectCode(
      () => validateFreshnessOperationsWorkspaceCandidate(state),
      'FRESHNESS_OPERATIONS_STATE_INVALID',
    );

    const accessibility = mutableCandidate();
    (accessibility['accessibility'] as Record<string, unknown>)['verified'] = true;
    expectCode(
      () => validateFreshnessOperationsWorkspaceCandidate(accessibility),
      'FRESHNESS_OPERATIONS_ACCESSIBILITY_INVALID',
    );

    const authority = mutableCandidate();
    (authority['authority'] as Record<string, unknown>)['authorizationGranted'] = true;
    expectCode(
      () => validateFreshnessOperationsWorkspaceCandidate(authority),
      'FRESHNESS_OPERATIONS_AUTHORITY_INVALID',
    );
  });

  it('rejects duplicate catalog IDs and routes before generic metadata mismatch', () => {
    const duplicateId = mutableCandidate();
    const idScreens = duplicateId['catalogScreens'] as Record<string, unknown>[];
    idScreens[1]!['id'] = idScreens[0]!['id'];
    expectCode(
      () => validateFreshnessOperationsWorkspaceCandidate(duplicateId),
      'FRESHNESS_OPERATIONS_DUPLICATE_ID',
    );

    const duplicateRoute = mutableCandidate();
    const routeScreens = duplicateRoute['catalogScreens'] as Record<string, unknown>[];
    routeScreens[1]!['route'] = routeScreens[0]!['route'];
    expectCode(
      () => validateFreshnessOperationsWorkspaceCandidate(duplicateRoute),
      'FRESHNESS_OPERATIONS_DUPLICATE_ROUTE',
    );
  });

  it('rejects prohibited payload, component ownership, and executable surfaces', () => {
    for (const key of ['rawPayload', 'componentOwnershipMap', 'html', 'authorityToken']) {
      const candidate = mutableCandidate();
      candidate[key] = 'untrusted';
      expectCode(
        () => validateFreshnessOperationsWorkspaceCandidate(candidate),
        'FRESHNESS_OPERATIONS_PROHIBITED_SURFACE',
      );
    }

    const callback = mutableCandidate();
    callback['onClick'] = () => undefined;
    expectCode(
      () => validateFreshnessOperationsWorkspaceCandidate(callback),
      'FRESHNESS_OPERATIONS_CANDIDATE_INVALID',
    );
  });
});
