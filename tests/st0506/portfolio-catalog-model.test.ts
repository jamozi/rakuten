import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PORTFOLIO_CATALOG_SCREEN_IDS,
  createPortfolioCatalogWorkspaceModel,
} from '../../packages/web-ui/src/portfolio-catalog-workspace.ts';
import { ADMIN_ROUTE_REGISTRY, evaluateAdminRoute } from '../../packages/web-ui/src/route-guard.ts';

describe('disabled headless portfolio/catalog workspace model', () => {
  it('creates one deterministic deeply frozen JSON model for each screen', () => {
    for (const screenId of PORTFOLIO_CATALOG_SCREEN_IDS) {
      const first = createPortfolioCatalogWorkspaceModel({ screenId });
      const second = createPortfolioCatalogWorkspaceModel({ screenId });
      assert.deepEqual(first, second);
      assert.notEqual(first, second);
      assert.equal(first.screen.id, screenId);
      assert.deepEqual(first.canonicalScreenOrder, PORTFOLIO_CATALOG_SCREEN_IDS);
      assert.equal(
        first.classification,
        'SOURCE_DERIVED_DISABLED_HEADLESS_PORTFOLIO_CATALOG_WORKSPACE_MODEL',
      );
      assert.deepEqual(JSON.parse(JSON.stringify(first)), first);
      assert.ok(Object.isFrozen(first));
      assert.ok(Object.isFrozen(first.screen));
      assert.ok(Object.isFrozen(first.screen.roles));
      assert.ok(Object.isFrozen(first.sourceBindings));
      assert.ok(Object.isFrozen(first.dataState));
      assert.ok(Object.isFrozen(first.dataState.items));
    }
  });

  it('keeps every metadata route unregistered under the disabled ST-1101 shell', () => {
    assert.equal(ADMIN_ROUTE_REGISTRY.length, 1);
    assert.equal(ADMIN_ROUTE_REGISTRY[0]?.screenId, 'ADM-001');
    assert.equal(ADMIN_ROUTE_REGISTRY[0]?.path, '/admin');
    assert.equal(ADMIN_ROUTE_REGISTRY[0]?.availability, 'DISABLED_AUTH_TRANSPORT_UNRESOLVED');
    for (const screenId of PORTFOLIO_CATALOG_SCREEN_IDS) {
      const model = createPortfolioCatalogWorkspaceModel({ screenId });
      assert.equal(
        evaluateAdminRoute({
          path: model.screen.route,
          authenticated: true,
          siteScope: 'synthetic-site',
          roles: ['EDITOR'],
        }).code,
        'UNREGISTERED_ROUTE',
      );
      assert.equal(model.availability, 'DISABLED');
      assert.equal(model.routeRegistration, 'UNREGISTERED');
      assert.equal(model.navigationEligible, false);
      assert.equal(model.renderEligible, false);
    }
  });

  it('keeps roles display-only and all runtime capabilities disabled', () => {
    for (const screenId of PORTFOLIO_CATALOG_SCREEN_IDS) {
      const model = createPortfolioCatalogWorkspaceModel({ screenId });
      assert.ok(model.screen.roles.length > 0);
      assert.equal(model.roleMetadataAuthority, 'DISPLAY_ONLY_NOT_AUTHORIZATION');
      assert.equal(model.authorizationGranted, false);
      assert.equal(model.backendReauthenticationRequired, true);
      assert.equal(model.backendReauthorizationRequired, true);
      assert.equal(model.authentication, 'NOT_EXECUTED');
      assert.equal(model.dataAccess, 'NOT_EXECUTED');
      assert.equal(model.apiAccess, 'NOT_EXECUTED');
      assert.equal(model.crudExecution, 'NOT_EXECUTED');
      assert.equal(model.identityExecution, 'NOT_EXECUTED');
      assert.equal(model.commandExecution, 'NOT_EXECUTED');
      assert.equal(model.effectExecution, 'NOT_EXECUTED');
      assert.deepEqual(model.actions, []);
      assert.equal(model.decision, 'NOT_READY');
      assert.equal(model.productionEligible, false);
    }
  });

  it('represents unavailable data as not loaded rather than zero records', () => {
    for (const screenId of PORTFOLIO_CATALOG_SCREEN_IDS) {
      assert.deepEqual(createPortfolioCatalogWorkspaceModel({ screenId }).dataState, {
        status: 'NOT_LOADED',
        items: [],
        itemCount: null,
      });
    }
  });
});
