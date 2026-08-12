import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  AnalyticsFinanceWorkspaceError,
  createAnalyticsFinanceWorkspaceCandidate,
  validateAnalyticsFinanceWorkspaceCandidate,
  type AnalyticsFinanceWorkspaceErrorCode,
  type AnalyticsFinanceWorkspaceInput,
} from '../../packages/web-ui/src/index.ts';

function expectCode(operation: () => unknown, code: AnalyticsFinanceWorkspaceErrorCode): void {
  assert.throws(
    operation,
    (error: unknown) => error instanceof AnalyticsFinanceWorkspaceError && error.code === code,
  );
}

function mutableCandidate(): Record<string, unknown> {
  const candidate = createAnalyticsFinanceWorkspaceCandidate({ screenId: 'ANA-001' });
  return JSON.parse(JSON.stringify(candidate)) as unknown as Record<string, unknown>;
}

describe('ST-1104 strict negative boundary', () => {
  it('rejects missing, unknown, mistyped, and additional input fields', () => {
    for (const input of [
      null,
      {},
      [],
      { screenId: 1 },
      { screenId: 'ANA-001', role: 'ANALYST' },
      { screenId: 'ANA-001', period: '2026-08' },
    ]) {
      expectCode(
        () => createAnalyticsFinanceWorkspaceCandidate(input as AnalyticsFinanceWorkspaceInput),
        'ANALYTICS_FINANCE_INPUT_INVALID',
      );
    }
    expectCode(
      () =>
        createAnalyticsFinanceWorkspaceCandidate({
          screenId: 'FIN-999',
        } as unknown as AnalyticsFinanceWorkspaceInput),
      'ANALYTICS_FINANCE_SCREEN_UNKNOWN',
    );
  });

  it('rejects subclasses, accessors, symbols, cycles, and callbacks', () => {
    class InputSubclass {
      screenId = 'ANA-001';
    }
    const accessor = {} as Record<string, unknown>;
    Object.defineProperty(accessor, 'screenId', {
      enumerable: true,
      get: () => 'ANA-001',
    });
    const symbol = { screenId: 'ANA-001', [Symbol('hidden')]: true };
    const cycle: Record<string, unknown> = { screenId: 'ANA-001' };
    cycle['cycle'] = cycle;
    const callback = { screenId: 'ANA-001', callback: () => undefined };

    for (const input of [new InputSubclass(), accessor, symbol, cycle, callback]) {
      expectCode(
        () => createAnalyticsFinanceWorkspaceCandidate(input as AnalyticsFinanceWorkspaceInput),
        'ANALYTICS_FINANCE_INPUT_INVALID',
      );
    }
  });

  it('fails closed for throwing and revoked unreadable proxies', () => {
    const throwing = new Proxy(
      { screenId: 'ANA-001' },
      {
        ownKeys() {
          throw new TypeError('canary');
        },
      },
    );
    const revocable = Proxy.revocable({ screenId: 'ANA-001' }, {});
    revocable.revoke();

    for (const input of [throwing, revocable.proxy]) {
      expectCode(
        () => createAnalyticsFinanceWorkspaceCandidate(input as AnalyticsFinanceWorkspaceInput),
        'ANALYTICS_FINANCE_INPUT_INVALID',
      );
    }
  });

  it('rejects metadata, state, visibility, accessibility, isolation, and authority tampering', () => {
    const metadata = mutableCandidate();
    (metadata['screen'] as Record<string, unknown>)['route'] = '/admin/other';
    expectCode(
      () => validateAnalyticsFinanceWorkspaceCandidate(metadata),
      'ANALYTICS_FINANCE_METADATA_INVALID',
    );

    const state = mutableCandidate();
    ((state['dataSlots'] as Record<string, unknown>)['kpiValues'] as Record<string, unknown>)[
      'status'
    ] = 'LOADED';
    expectCode(
      () => validateAnalyticsFinanceWorkspaceCandidate(state),
      'ANALYTICS_FINANCE_STATE_INVALID',
    );

    const visibility = mutableCandidate();
    (visibility['visibilityRequirements'] as Record<string, unknown>)['unknownAsZeroAllowed'] =
      true;
    expectCode(
      () => validateAnalyticsFinanceWorkspaceCandidate(visibility),
      'ANALYTICS_FINANCE_VISIBILITY_INVALID',
    );

    const accessibility = mutableCandidate();
    (accessibility['accessibility'] as Record<string, unknown>)['verified'] = true;
    expectCode(
      () => validateAnalyticsFinanceWorkspaceCandidate(accessibility),
      'ANALYTICS_FINANCE_ACCESSIBILITY_INVALID',
    );

    const isolation = mutableCandidate();
    (isolation['financeIsolation'] as Record<string, unknown>)['publicExposure'] = true;
    expectCode(
      () => validateAnalyticsFinanceWorkspaceCandidate(isolation),
      'ANALYTICS_FINANCE_ISOLATION_INVALID',
    );

    const authority = mutableCandidate();
    (authority['authority'] as Record<string, unknown>)['authorizationGranted'] = true;
    expectCode(
      () => validateAnalyticsFinanceWorkspaceCandidate(authority),
      'ANALYTICS_FINANCE_AUTHORITY_INVALID',
    );
  });

  it('rejects duplicate catalog IDs and routes before generic metadata mismatch', () => {
    const duplicateId = mutableCandidate();
    const idScreens = duplicateId['catalogScreens'] as Record<string, unknown>[];
    idScreens[1]!['id'] = idScreens[0]!['id'];
    expectCode(
      () => validateAnalyticsFinanceWorkspaceCandidate(duplicateId),
      'ANALYTICS_FINANCE_DUPLICATE_ID',
    );

    const duplicateRoute = mutableCandidate();
    const routeScreens = duplicateRoute['catalogScreens'] as Record<string, unknown>[];
    routeScreens[1]!['route'] = routeScreens[0]!['route'];
    expectCode(
      () => validateAnalyticsFinanceWorkspaceCandidate(duplicateRoute),
      'ANALYTICS_FINANCE_DUPLICATE_ROUTE',
    );
  });

  it('rejects financial values, rows, formulas, ownership, and executable surfaces', () => {
    for (const key of [
      'financialAmount',
      'kpiValue',
      'csvRows',
      'formula',
      'componentOwnershipMap',
      'dashboardOwnershipMap',
      'rawPayload',
      'html',
      'authorityToken',
    ]) {
      const candidate = mutableCandidate();
      candidate[key] = 'untrusted';
      expectCode(
        () => validateAnalyticsFinanceWorkspaceCandidate(candidate),
        'ANALYTICS_FINANCE_PROHIBITED_SURFACE',
      );
    }

    const callback = mutableCandidate();
    callback['onClick'] = () => undefined;
    expectCode(
      () => validateAnalyticsFinanceWorkspaceCandidate(callback),
      'ANALYTICS_FINANCE_CANDIDATE_INVALID',
    );
  });
});
