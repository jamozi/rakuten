import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  AI_GOVERNANCE_SCREEN,
  AI_GOVERNANCE_SECTIONS,
  AI_GOVERNANCE_SOURCE_BINDINGS,
  createAiGovernanceWorkspaceModel,
} from '../../packages/web-ui/src/ai-governance-workspace.ts';
import { ADMIN_ROUTE_REGISTRY, evaluateAdminRoute } from '../../packages/web-ui/src/route-guard.ts';

describe('disabled headless AI governance workspace model', () => {
  it('creates an exact deterministic, detached, deeply frozen JSON model', () => {
    const first = createAiGovernanceWorkspaceModel({ screenId: 'GOV-001' });
    const second = createAiGovernanceWorkspaceModel({ screenId: 'GOV-001' });

    assert.deepEqual(first, second);
    assert.notEqual(first, second);
    assert.notEqual(first.screen, AI_GOVERNANCE_SCREEN);
    assert.notEqual(first.sections, AI_GOVERNANCE_SECTIONS);
    assert.notEqual(first.sourceBindings, AI_GOVERNANCE_SOURCE_BINDINGS);
    assert.equal(
      first.classification,
      'SOURCE_DERIVED_DISABLED_HEADLESS_AI_GOVERNANCE_WORKSPACE_MODEL',
    );
    assert.deepEqual(JSON.parse(JSON.stringify(first)), first);
    assert.ok(Object.isFrozen(first));
    assert.ok(Object.isFrozen(first.screen));
    assert.ok(Object.isFrozen(first.screen.roles));
    assert.ok(Object.isFrozen(first.sections));
    assert.ok(Object.isFrozen(first.sections[0]));
    assert.ok(Object.isFrozen(first.sections[0]?.records));
    assert.ok(Object.isFrozen(first.sourceBindings));
    assert.ok(Object.isFrozen(first.sourceBindings[0]?.semantics));
  });

  it('keeps GOV-001 unregistered beneath the exact disabled ST-1101 shell', () => {
    assert.deepEqual(
      ADMIN_ROUTE_REGISTRY.map(({ screenId, path, availability }) => ({
        screenId,
        path,
        availability,
      })),
      [
        {
          screenId: 'ADM-001',
          path: '/admin',
          availability: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED',
        },
      ],
    );
    const model = createAiGovernanceWorkspaceModel({ screenId: 'GOV-001' });
    const routeDecision = evaluateAdminRoute({
      path: model.screen.route,
      authenticated: true,
      siteScope: 'synthetic-site',
      roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'SECURITY_AUDITOR'],
    });
    assert.equal(routeDecision.code, 'UNREGISTERED_ROUTE');
    assert.equal(model.availability, 'DISABLED');
    assert.equal(model.routeRegistration, 'UNREGISTERED');
    assert.equal(model.navigation, 'DISABLED');
    assert.equal(model.rendering, 'DISABLED');
  });

  it('never grants data, auth, action, activation, approval, release, or provider authority', () => {
    const model = createAiGovernanceWorkspaceModel({ screenId: 'GOV-001' });
    assert.equal(model.authentication, 'NOT_EXECUTED');
    assert.equal(model.authorizationGranted, false);
    assert.equal(model.dataAccess, 'NOT_EXECUTED');
    assert.equal(model.dataStatus, 'NOT_LOADED');
    assert.deepEqual(model.actions, []);
    assert.equal(model.activation, 'FORBIDDEN');
    assert.equal(model.approval, 'FORBIDDEN');
    assert.equal(model.release, 'FORBIDDEN');
    assert.equal(model.providerAction, 'FORBIDDEN');
    assert.equal(model.externalAction, 'FORBIDDEN');
    assert.equal(model.decision, 'NOT_READY');
    assert.equal(model.productionEligible, false);
  });

  it('does not turn local model checks into formal TST-022 evidence', () => {
    const model = createAiGovernanceWorkspaceModel({ screenId: 'GOV-001' });
    assert.equal(model.screen.runtimeVerification, 'NOT_EXECUTED');
    assert.equal(model.formalTst022, 'NOT_EXECUTED');
  });
});
