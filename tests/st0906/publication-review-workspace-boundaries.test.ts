import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  PUBLICATION_REVIEW_SCREEN_IDS,
  createPublicationReviewWorkspaceModel,
} from '../../packages/web-ui/src/publication-review-workspace.ts';
import {
  ADMIN_ROUTE_REGISTRY,
  evaluateAdminRouteContext,
} from '../../packages/web-ui/src/route-guard.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

describe('ST-0906 authority and runtime boundaries', () => {
  it('keeps all seven catalog paths unregistered', () => {
    const registeredPaths = new Set<string>(ADMIN_ROUTE_REGISTRY.map(({ path }) => path));
    for (const screenId of PUBLICATION_REVIEW_SCREEN_IDS) {
      const model = createPublicationReviewWorkspaceModel({ screenId });
      assert.equal(registeredPaths.has(model.screen.route), false);
      const decision = evaluateAdminRouteContext({
        path: model.screen.route,
        authenticated: true,
        siteScope: 'synthetic-site',
        roles: model.screen.roles,
      });
      assert.equal(decision.code, 'UNREGISTERED_ROUTE');
      assert.equal(decision.authorizationGranted, false);
      assert.equal(model.routeCatalogOnly, true);
      assert.equal(model.routeRegistered, false);
      assert.equal(model.renderEnabled, false);
    }
  });

  it('cannot emit approval, publish, or rollback intents', () => {
    for (const screenId of PUBLICATION_REVIEW_SCREEN_IDS) {
      const model = createPublicationReviewWorkspaceModel({ screenId });
      assert.deepEqual(model.actionIntents, []);
      assert.equal(model.criticalIntentEmittable, false);
      assert.equal(model.authorizationGranted, false);
      assert.equal(model.backendReauthorizationRequired, true);
      assert.equal(model.mutationEnabled, false);
      assert.equal(model.externalActionEnabled, false);
      assert.equal(model.publicationAuthorized, false);
      assert.ok(
        model.capabilityStates.every(
          (capability) => !capability.effectPermitted && !capability.intentEmittable,
        ),
      );
    }
  });

  it('has no framework, browser, transport, persistence, or generated-client import', () => {
    const source = readFileSync(
      resolve(repositoryRoot, 'packages/web-ui/src/publication-review-workspace.ts'),
      'utf8',
    );
    assert.doesNotMatch(
      source,
      /(?:from\s*|import\s*\(|require\s*\()['"](?:react|next)(?:\/|['"])/,
    );
    assert.doesNotMatch(source, /(?:\b|\.)(?:fetch|sendBeacon)\s*\(/);
    assert.doesNotMatch(
      source,
      /\b(?:window|document|navigator|localStorage|sessionStorage|indexedDB|caches|WebSocket|XMLHttpRequest|EventSource)\b/,
    );
    assert.doesNotMatch(source, /['"]node:(?:http|https|net|tls|dns|dgram)['"]/);
    assert.doesNotMatch(source, /generated\/clients/);
    assert.doesNotMatch(source, /from ['"].*(?:adapter|repository|database|api-client)/);
  });
});
