import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  ARTICLE_WORKSPACE_SCREEN_IDS,
  ARTICLE_WORKSPACE_V2_CLASSIFICATION,
  ARTICLE_WORKSPACE_V2_PROJECTION_IDS,
  createArticleWorkspaceV2,
} from '../../packages/web-ui/src/index.ts';
import { evaluateAdminRoute } from '../../packages/web-ui/src/route-guard.ts';

const expectedPanes = {
  'EDT-002': ['AST', 'AI_DIFF', 'CLAIMS', 'COMPARISON', 'SEO'],
  'EDT-003': ['AST'],
  'EDT-005': ['AI_DIFF'],
  'EDT-006': ['CLAIMS'],
  'EDT-007': ['COMPARISON'],
  'EDT-009': ['SEO'],
} as const;

describe('ST-1102 V2 recorded article workspace model', () => {
  it('maps every objective screen to the exact recorded pane set', () => {
    for (const screenId of ARTICLE_WORKSPACE_SCREEN_IDS) {
      const first = createArticleWorkspaceV2({ screenId });
      const second = createArticleWorkspaceV2({ screenId });
      assert.deepEqual(first, second);
      assert.notEqual(first, second);
      assert.equal(first.classification, ARTICLE_WORKSPACE_V2_CLASSIFICATION);
      assert.equal(first.storyId, 'ST-1102');
      assert.equal(first.localStatus, 'LOCAL_IMPLEMENTATION_COMPLETE');
      assert.deepEqual(first.paneOrder, expectedPanes[screenId]);
      assert.equal(first.panes.length, expectedPanes[screenId].length);
      assert.ok(Object.isFrozen(first));
      assert.ok(Object.isFrozen(first.article));
      assert.ok(Object.isFrozen(first.panes));
      assert.ok(Object.isFrozen(first.panes[0]));
      assert.deepEqual(JSON.parse(JSON.stringify(first)), first);
    }
  });

  it('integrates exact recorded ST-0806 AST, diff, Claim and Comparison metadata', () => {
    const model = createArticleWorkspaceV2({ screenId: 'EDT-002' });
    assert.deepEqual(model.paneOrder, ARTICLE_WORKSPACE_V2_PROJECTION_IDS);
    assert.deepEqual(
      model.panes.map(({ status }) => status),
      [
        'AVAILABLE_RECORDED',
        'AVAILABLE_RECORDED',
        'AVAILABLE_RECORDED',
        'AVAILABLE_RECORDED',
        'PARTIAL_RECORDED',
      ],
    );
    assert.equal(model.article['articleId'], '018f3e90-7b00-7000-8000-000000000806');
    assert.equal(model.article['versionId'], '018f3e90-7b00-7000-8000-000000000807');
    assert.equal(model.article['versionState'], 'DRAFT');
    assert.notEqual(model.article['baselineAstSha256'], model.article['proposalAstSha256']);
    assert.equal(model.article['proposalDisposition'], 'HUMAN_EDITABLE_PROPOSAL_ONLY');
    assert.equal(model.article['proposalApplied'], false);
    assert.equal(model.article['publicationAuthorized'], false);

    const ast = model.panes[0]?.payload;
    const active = ast?.['active'] as Record<string, unknown>;
    const proposed = ast?.['proposed'] as Record<string, unknown>;
    assert.equal(active['blockCount'], 10);
    assert.equal(proposed['blockCount'], 10);
    assert.equal(ast?.['proposalApplied'], false);

    const diff = model.panes[1]?.payload;
    assert.equal(diff?.['valuesExposed'], false);
    assert.equal(diff?.['adoptionAuthorized'], false);
    assert.ok(Array.isArray(diff?.['operations']));
    assert.ok((diff?.['operations'] as unknown[]).length > 0);

    const claims = model.panes[2]?.payload;
    assert.equal(claims?.['claimTextPresent'], false);
    assert.ok(Array.isArray(claims?.['rows']));
    assert.equal((claims?.['rows'] as unknown[]).length, 2);

    const comparison = model.panes[3]?.payload;
    assert.equal(comparison?.['showUnknownValues'], true);
    assert.equal(comparison?.['financeOrAffiliateEconomicsPresent'], false);
    assert.equal(comparison?.['recommendationOrderMutationAuthorized'], false);
  });

  it('keeps SEO partial and refuses to invent canonical, robots or JSON-LD', () => {
    const model = createArticleWorkspaceV2({ screenId: 'EDT-009' });
    const seo = model.panes[0];
    assert.equal(seo?.status, 'PARTIAL_RECORDED');
    assert.deepEqual(seo?.sourceStoryIds, ['ST-0806']);
    assert.equal(seo?.payload['titleSource'], 'TYPED_AST');
    assert.equal(seo?.payload['seoMetadataRef'], 'SEO-FIX-001');
    assert.equal(seo?.payload['canonical'], null);
    assert.equal(seo?.payload['robots'], null);
    assert.equal(seo?.payload['jsonLd'], null);
    assert.equal(seo?.payload['resolvedMetadataStatus'], 'UNAVAILABLE_DEPENDENCY');
    assert.equal(seo?.payload['missingOwner'], 'ST-0807_NOT_DECLARED_DEPENDENCY');
  });

  it('remains behind the exact disabled ST-1101 route boundary', () => {
    for (const screenId of ARTICLE_WORKSPACE_SCREEN_IDS) {
      const model = createArticleWorkspaceV2({ screenId });
      assert.equal(
        evaluateAdminRoute({
          path: model.screen.route,
          authenticated: true,
          siteScope: 'synthetic-site',
          roles: [...model.screen.roles],
        }).code,
        'UNREGISTERED_ROUTE',
      );
      assert.deepEqual(model.route, {
        registered: false,
        renderEnabled: false,
        status: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED',
        roleMetadataOnly: true,
      });
    }
  });
});
