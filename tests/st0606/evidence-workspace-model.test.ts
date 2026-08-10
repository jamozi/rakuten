import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  EVIDENCE_WORKSPACE_SCREEN_IDS,
  createEvidenceWorkspaceModel,
} from '../../packages/web-ui/src/evidence-workspace.ts';
import { ADMIN_ROUTE_REGISTRY, evaluateAdminRoute } from '../../packages/web-ui/src/route-guard.ts';

describe('disabled headless evidence-workspace model', () => {
  it('creates one exact deterministic model for each canonical screen', () => {
    for (const screenId of EVIDENCE_WORKSPACE_SCREEN_IDS) {
      const first = createEvidenceWorkspaceModel({ screenId });
      const second = createEvidenceWorkspaceModel({ screenId });
      assert.deepEqual(first, second);
      assert.notEqual(first, second);
      assert.equal(first.screen.id, screenId);
      assert.deepEqual(first.canonicalScreenOrder, EVIDENCE_WORKSPACE_SCREEN_IDS);
      assert.equal(
        first.classification,
        'SOURCE_DERIVED_DISABLED_HEADLESS_EVIDENCE_WORKSPACE_MODEL',
      );
      assert.deepEqual(JSON.parse(JSON.stringify(first)), first);
      assert.ok(Object.isFrozen(first));
      assert.ok(Object.isFrozen(first.screen));
      assert.ok(Object.isFrozen(first.sourceBindings));
      assert.ok(Object.isFrozen(first.dataState));
      assert.ok(Object.isFrozen(first.dataState.items));
    }
  });

  it('keeps every route unregistered under the exact disabled ST-1101 shell', () => {
    assert.deepEqual(ADMIN_ROUTE_REGISTRY, [
      {
        screenId: 'ADM-001',
        path: '/admin',
        allowedRoles: [
          'PRODUCT_OWNER',
          'MANAGING_EDITOR',
          'EDITOR',
          'REVIEWER',
          'ANALYST',
          'OPERATOR',
          'SECURITY_AUDITOR',
          'READ_ONLY_AUDITOR',
        ],
        siteScopeRequired: true,
        securityAuthority: 'server',
        availability: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED',
      },
    ]);
    for (const screenId of EVIDENCE_WORKSPACE_SCREEN_IDS) {
      const model = createEvidenceWorkspaceModel({ screenId });
      const decision = evaluateAdminRoute({
        path: model.screen.route,
        authenticated: true,
        siteScope: 'synthetic-site',
        roles: ['EDITOR'],
      });
      assert.equal(decision.code, 'UNREGISTERED_ROUTE');
      assert.equal(model.availability, 'DISABLED');
      assert.equal(model.routeRegistration, 'UNREGISTERED');
      assert.equal(model.navigationEligible, false);
      assert.equal(model.renderEligible, false);
    }
  });

  it('never grants authorization, data access, commands, effects or actions', () => {
    for (const screenId of EVIDENCE_WORKSPACE_SCREEN_IDS) {
      const model = createEvidenceWorkspaceModel({ screenId });
      assert.equal(model.authorizationGranted, false);
      assert.equal(model.backendReauthenticationRequired, true);
      assert.equal(model.backendReauthorizationRequired, true);
      assert.equal(model.authentication, 'NOT_EXECUTED');
      assert.equal(model.dataAccess, 'NOT_EXECUTED');
      assert.equal(model.commandExecution, 'NOT_EXECUTED');
      assert.equal(model.effectExecution, 'NOT_EXECUTED');
      assert.deepEqual(model.actions, []);
      assert.equal(model.decision, 'NOT_READY');
      assert.equal(model.productionEligible, false);
    }
  });

  it('represents absent runtime data as not loaded rather than zero records', () => {
    for (const screenId of EVIDENCE_WORKSPACE_SCREEN_IDS) {
      assert.deepEqual(createEvidenceWorkspaceModel({ screenId }).dataState, {
        status: 'NOT_LOADED',
        items: [],
        itemCount: null,
      });
    }
  });
});
