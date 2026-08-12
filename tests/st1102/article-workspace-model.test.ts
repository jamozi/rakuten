import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  ARTICLE_WORKSPACE_SCREEN_IDS,
  ARTICLE_WORKSPACE_SCREENS,
  ARTICLE_WORKSPACE_SOURCE_REFS,
  createArticleWorkspaceCandidate,
} from '../../packages/web-ui/src/article-workspace.ts';
import { ADMIN_ROUTE_REGISTRY, evaluateAdminRoute } from '../../packages/web-ui/src/route-guard.ts';

describe('disabled headless article workspace candidate', () => {
  it('creates deterministic, detached, deeply frozen JSON for each mapped screen', () => {
    for (const screenId of ARTICLE_WORKSPACE_SCREEN_IDS) {
      const first = createArticleWorkspaceCandidate({ screenId });
      const second = createArticleWorkspaceCandidate({ screenId });
      assert.deepEqual(first, second);
      assert.notEqual(first, second);
      assert.notEqual(first.screen, ARTICLE_WORKSPACE_SCREENS[0]);
      assert.notEqual(first.sourceRefs, ARTICLE_WORKSPACE_SOURCE_REFS);
      assert.equal(
        first.classification,
        'SOURCE_DERIVED_DISABLED_HEADLESS_ARTICLE_WORKSPACE_CANDIDATE',
      );
      assert.equal(first.storyId, 'ST-1102');
      assert.equal(first.objective, 'AST/AI diff/Claim/Comparison/SEOを統合');
      assert.deepEqual(JSON.parse(JSON.stringify(first)), first);
      assert.ok(Object.isFrozen(first));
      assert.ok(Object.isFrozen(first.screen));
      assert.ok(Object.isFrozen(first.screen.roles));
      assert.ok(Object.isFrozen(first.coordinateSlots.article));
      assert.ok(Object.isFrozen(first.workspaceSignals.blockers));
      assert.ok(Object.isFrozen(first.projections));
      assert.ok(Object.isFrozen(first.projections[0]));
      assert.ok(Object.isFrozen(first.projections[0]?.componentIds));
      assert.ok(Object.isFrozen(first.accessibility));
      assert.ok(Object.isFrozen(first.verification));
    }
  });

  it('keeps every article route unregistered under the exact ST-1101 shell', () => {
    assert.deepEqual(
      ADMIN_ROUTE_REGISTRY.map(({ screenId, path }) => ({ screenId, path })),
      [{ screenId: 'ADM-001', path: '/admin' }],
    );
    for (const screenId of ARTICLE_WORKSPACE_SCREEN_IDS) {
      const model = createArticleWorkspaceCandidate({ screenId });
      assert.equal(
        evaluateAdminRoute({
          path: model.screen.route,
          authenticated: true,
          siteScope: 'synthetic-site',
          roles: [...model.screen.roles],
        }).code,
        'UNREGISTERED_ROUTE',
      );
      assert.equal(model.routeRegistered, false);
      assert.equal(model.renderEnabled, false);
    }
  });

  it('leaves coordinates, signals and all five objective projections unloaded', () => {
    const model = createArticleWorkspaceCandidate({ screenId: 'EDT-002' });
    for (const slot of Object.values(model.coordinateSlots)) {
      assert.deepEqual(slot, { status: 'NOT_LOADED', value: null });
    }
    for (const slot of Object.values(model.workspaceSignals)) {
      assert.deepEqual(slot, { status: 'NOT_LOADED', value: null });
    }
    assert.deepEqual(
      model.projections.map(({ id, status, reason, payload }) => [id, status, reason, payload]),
      [
        ['AST', 'NOT_LOADED', 'ARTICLE_VERSION_NOT_LOADED', null],
        ['AI_DIFF', 'NOT_LOADED', 'AI_DIFF_INPUT_NOT_LOADED', null],
        ['CLAIMS', 'NOT_LOADED', 'CLAIM_EVIDENCE_NOT_LOADED', null],
        ['COMPARISON', 'NOT_LOADED', 'COMPARISON_INPUT_NOT_LOADED', null],
        ['SEO', 'NOT_LOADED', 'SEO_INPUT_NOT_LOADED', null],
      ],
    );
  });

  it('does not infer ETag, unsaved state, or SEO output', () => {
    const model = createArticleWorkspaceCandidate({ screenId: 'EDT-009' });
    assert.deepEqual(model.concurrency, {
      etag: null,
      ifMatch: null,
      conflictDetection: 'NOT_EVALUATED',
      overwriteEnabled: false,
    });
    assert.deepEqual(model.unsavedChangesGuard, {
      componentId: 'UI-C014',
      status: 'NOT_EVALUATED',
      unsavedChangesKnown: false,
      navigationInterceptionEnabled: false,
    });
    assert.deepEqual(model.seoPreview, {
      status: 'NOT_LOADED',
      computationEnabled: false,
      canonical: null,
      robots: null,
      jsonLd: null,
    });
  });
});
