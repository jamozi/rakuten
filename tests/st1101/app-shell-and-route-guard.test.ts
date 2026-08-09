import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  APP_SHELL_IDS,
  AppShellError,
  createAppShellModel,
} from '../../packages/web-ui/src/app-shell.ts';
import {
  ADMIN_ROLES,
  ADMIN_ROUTE_REGISTRY,
  evaluateAdminRoute,
  evaluateAdminRouteContext,
} from '../../packages/web-ui/src/route-guard.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

const validRequest = {
  path: '/admin',
  authenticated: true,
  siteScope: 'site-main',
  roles: ['EDITOR'],
} as const;

describe('advisory admin route guard', () => {
  it('registers only exact ADM-001 with all exact roles and disabled availability', () => {
    assert.deepEqual(ADMIN_ROUTE_REGISTRY, [
      {
        screenId: 'ADM-001',
        path: '/admin',
        allowedRoles: ADMIN_ROLES,
        siteScopeRequired: true,
        securityAuthority: 'server',
        availability: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED',
      },
    ]);
    assert.deepEqual(ADMIN_ROLES, [
      'PRODUCT_OWNER',
      'MANAGING_EDITOR',
      'EDITOR',
      'REVIEWER',
      'ANALYST',
      'OPERATOR',
      'SECURITY_AUDITOR',
      'READ_ONLY_AUDITOR',
    ]);
  });

  it('denies every unregistered route without normalization or prefix matching', () => {
    for (const path of ['/admin/', '/admin/users', '/Admin', '/', '/admin?query=1']) {
      assert.equal(evaluateAdminRoute({ ...validRequest, path }).code, 'UNREGISTERED_ROUTE');
    }
  });

  it('returns every closed context denial before the disabled feature result', () => {
    assert.equal(
      evaluateAdminRoute({ ...validRequest, authenticated: false }).code,
      'UNAUTHENTICATED',
    );
    for (const siteScope of [null, '', ' site-main', 'site/main', 'x'.repeat(129)]) {
      assert.equal(evaluateAdminRoute({ ...validRequest, siteScope }).code, 'SITE_SCOPE_MISSING');
    }
    for (const roles of [null, ['OWNER'], ['EDITOR', 'EDITOR'], [1]]) {
      assert.equal(evaluateAdminRoute({ ...validRequest, roles }).code, 'ROLE_SET_INVALID');
    }
    assert.equal(evaluateAdminRoute({ ...validRequest, roles: [] }).code, 'ROLE_DENIED');
    assert.equal(evaluateAdminRoute(validRequest).code, 'FEATURE_DISABLED');
  });

  it('allows every exact catalog role only at the UI-context stage', () => {
    for (const role of ADMIN_ROLES) {
      const context = evaluateAdminRouteContext({ ...validRequest, roles: [role] });
      assert.equal(context.code, 'ALLOW_UI_ONLY');
      assert.equal(context.navigationEligible, true);
      assert.equal(context.renderEligible, true);
      assert.equal(evaluateAdminRoute({ ...validRequest, roles: [role] }).code, 'FEATURE_DISABLED');
    }
  });

  it('never represents a UI decision as server authorization', () => {
    const decisions = [
      evaluateAdminRoute(validRequest),
      evaluateAdminRouteContext(validRequest),
      evaluateAdminRoute({ ...validRequest, path: '/admin/child' }),
      evaluateAdminRoute({ ...validRequest, roles: [] }),
    ];
    for (const decision of decisions) {
      assert.equal(decision.authorizationGranted, false);
      assert.equal(decision.backendReauthorizationRequired, true);
      assert.equal(decision.securityAuthority, 'server');
      assert.deepEqual(JSON.parse(JSON.stringify(decision)), decision);
    }
    assert.match(decisions[1]?.statement ?? '', /backend must reauthenticate and reauthorize/);
  });
});

describe('UI-C001 AppShell model', () => {
  it('has one title/H1, fixed landmarks and skip target, unique deterministic focus order', () => {
    const model = createAppShellModel({
      documentTitle: 'Operations dashboard',
      heading: 'Operations dashboard',
      authenticated: true,
      siteScope: 'site-main',
      roles: ['OPERATOR'],
      navigationItems: [
        { focusId: 'nav-dashboard', label: 'Dashboard', path: '/admin' },
        { focusId: 'nav-unregistered', label: 'Unregistered', path: '/admin/unregistered' },
      ],
    });

    assert.equal(model.componentId, 'UI-C001');
    assert.deepEqual(model.document, { title: 'Operations dashboard' });
    assert.deepEqual(model.skipLink, {
      id: APP_SHELL_IDS.skipLink,
      label: 'Skip to main content',
      targetId: APP_SHELL_IDS.main,
    });
    assert.deepEqual(
      model.landmarks.map((landmark) => landmark.kind),
      ['header', 'navigation', 'main'],
    );
    assert.equal(model.landmarks.filter((landmark) => landmark.kind === 'main').length, 1);
    assert.equal(model.navigationItems[0]?.routeDecision.code, 'FEATURE_DISABLED');
    assert.equal(model.navigationItems[1]?.routeDecision.code, 'UNREGISTERED_ROUTE');
    assert.deepEqual(model.focusOrder, [APP_SHELL_IDS.skipLink, APP_SHELL_IDS.main]);
    assert.equal(new Set(model.focusOrder).size, model.focusOrder.length);
    assert.deepEqual(JSON.parse(JSON.stringify(model)), model);
    assert.ok(Object.isFrozen(model));
  });

  it('rejects duplicate/untrusted IDs, paths, and callback-shaped extra fields', () => {
    const base = {
      documentTitle: 'Admin',
      heading: 'Admin',
      authenticated: true,
      siteScope: 'site-main',
      roles: ['EDITOR'],
    } as const;
    assert.throws(
      () =>
        createAppShellModel({
          ...base,
          navigationItems: [
            { focusId: 'nav-home', label: 'One', path: '/admin' },
            { focusId: 'nav-home', label: 'Two', path: '/admin/two' },
          ],
        }),
      (error) => error instanceof AppShellError && error.code === 'APP_SHELL_DUPLICATE_ID',
    );
    assert.throws(
      () =>
        createAppShellModel({
          ...base,
          navigationItems: [
            { focusId: 'nav-one', label: 'One', path: '/admin' },
            { focusId: 'nav-two', label: 'Two', path: '/admin' },
          ],
        }),
      (error) => error instanceof AppShellError && error.code === 'APP_SHELL_DUPLICATE_PATH',
    );
    assert.throws(
      () =>
        createAppShellModel({
          ...base,
          navigationItems: [
            {
              focusId: 'nav-one',
              label: 'One',
              path: '/admin',
              onClick: () => undefined,
            },
          ],
        }),
      (error) => error instanceof AppShellError && error.code === 'APP_SHELL_NAVIGATION_INVALID',
    );
  });

  it('keeps production source dependency-free and free of browser/data/effect APIs', () => {
    const sourceNames = [
      'serializable.ts',
      'tokens.ts',
      'route-guard.ts',
      'app-shell.ts',
      'data-table.ts',
      'form.ts',
      'dialog.ts',
      'index.ts',
    ];
    const combined = sourceNames
      .map((name) => readFileSync(resolve(repositoryRoot, 'packages/web-ui/src', name), 'utf8'))
      .join('\n');
    assert.doesNotMatch(combined, /from\s+['"](?:react|next(?:\/|['"]))/i);
    assert.doesNotMatch(combined, /\b(?:window|HTMLElement|localStorage|sessionStorage|fetch)\b/);
    assert.doesNotMatch(combined, /globalThis\.(?:document|window)/);
    assert.doesNotMatch(combined, /\b(?:cookie|bearer)\b|['"]Authorization['"]/i);
    assert.doesNotMatch(combined, /generated\/clients|web-contracts\/src\/generated/i);
    assert.doesNotMatch(combined, /\b(?:onClick|onSubmit|renderRow|renderCell)\b/);
    assert.doesNotMatch(combined, /\.(?:tsx|jsx)['"]/);
    assert.doesNotMatch(combined, /\b(?:enum|namespace)\s+[A-Za-z_$]/);
  });
});
