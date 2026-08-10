import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PORTFOLIO_CATALOG_SCREEN_IDS,
  PORTFOLIO_CATALOG_SCREENS,
  PORTFOLIO_CATALOG_SOURCE_BINDINGS,
} from '../../packages/web-ui/src/portfolio-catalog-workspace.ts';

const expectedMetadata = [
  [
    'PORT-001',
    'カテゴリ一覧',
    '/admin/portfolio/categories',
    'portfolio',
    ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'EDITOR', 'ANALYST'],
    'カテゴリとMVP Scope管理',
    false,
    [],
  ],
  [
    'PORT-002',
    'カテゴリ詳細',
    '/admin/portfolio/categories/{id}',
    'portfolio',
    ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'EDITOR', 'ANALYST'],
    'カテゴリ設定、Freshness、Identity Rule参照',
    false,
    [],
  ],
  [
    'PORT-003',
    'Keyword一覧',
    '/admin/portfolio/keywords',
    'portfolio',
    ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'EDITOR', 'ANALYST'],
    'Keyword、意図、Source、優先度を管理',
    false,
    [],
  ],
  [
    'PORT-004',
    'Intent Cluster',
    '/admin/portfolio/intents',
    'portfolio',
    ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'EDITOR', 'ANALYST'],
    '同一意思決定のKeywordをCluster化',
    false,
    [],
  ],
  [
    'PORT-005',
    'Opportunity Queue',
    '/admin/portfolio/opportunities',
    'portfolio',
    ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'EDITOR', 'ANALYST'],
    'AI/Ruleによる候補を人間が評価',
    false,
    [],
  ],
  [
    'PORT-006',
    'Article Plan',
    '/admin/portfolio/article-plans/{id}',
    'portfolio',
    ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'EDITOR'],
    '記事目的、候補Universe、記事型を確定',
    false,
    ['ArticlePlan', 'IntentCluster'],
  ],
  [
    'CAT-001',
    '楽天取込Run',
    '/admin/catalog/ingestion-runs',
    'catalog',
    ['EDITOR', 'OPERATOR', 'ANALYST'],
    '取得状況、Rate Limit、Raw Artifactを確認',
    false,
    [],
  ],
  [
    'CAT-002',
    '商品候補一覧',
    '/admin/catalog/candidates',
    'catalog',
    ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    '未統合候補を検索・絞込',
    false,
    [],
  ],
  [
    'CAT-003',
    '商品同一性Workbench',
    '/admin/catalog/identity-workbench',
    'catalog',
    ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    '型番・Variant・Bundleを根拠付きで統合/分離',
    true,
    ['ProductCandidate', 'GroupingDecision'],
  ],
  [
    'CAT-004',
    'Canonical Product',
    '/admin/catalog/products/{id}',
    'catalog',
    ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER', 'ANALYST'],
    '商品属性、Variant、Evidence、履歴を表示',
    false,
    [],
  ],
  [
    'CAT-005',
    'Offer詳細',
    '/admin/catalog/offers/{id}',
    'catalog',
    ['EDITOR', 'REVIEWER', 'ANALYST'],
    'ショップ別Offer、価格、在庫、送料、鮮度を表示',
    false,
    [],
  ],
  [
    'CAT-006',
    'Raw Artifact Viewer',
    '/admin/artifacts/{id}',
    'catalog',
    ['EDITOR', 'REVIEWER', 'OPERATOR', 'SECURITY_AUDITOR'],
    '原本Hash、取得情報、許可された表示を確認',
    false,
    [],
  ],
] as const;

describe('ST-0506 source-derived contract', () => {
  it('preserves the exact twelve canonical screen IDs and order', () => {
    assert.deepEqual(PORTFOLIO_CATALOG_SCREEN_IDS, [
      'PORT-001',
      'PORT-002',
      'PORT-003',
      'PORT-004',
      'PORT-005',
      'PORT-006',
      'CAT-001',
      'CAT-002',
      'CAT-003',
      'CAT-004',
      'CAT-005',
      'CAT-006',
    ]);
    assert.equal(new Set(PORTFOLIO_CATALOG_SCREEN_IDS).size, 12);
  });

  it('preserves every exact canonical metadata field', () => {
    assert.deepEqual(
      PORTFOLIO_CATALOG_SCREENS.map((screen) => [
        screen.id,
        screen.name,
        screen.route,
        screen.area,
        screen.roles,
        screen.purpose,
        screen.criticalAction,
        screen.apiDependencies,
      ]),
      expectedMetadata,
    );
    for (const screen of PORTFOLIO_CATALOG_SCREENS) {
      assert.equal(screen.mvp, true);
      assert.equal(screen.designStatus, 'APPROVED_FOR_IMPLEMENTATION');
      assert.equal(screen.implementationStatus, 'NOT_STARTED');
      assert.equal(screen.runtimeVerification, 'NOT_EXECUTED');
    }
  });

  it('pins exact predecessor commits and complete committed inventories', () => {
    assert.deepEqual(
      PORTFOLIO_CATALOG_SOURCE_BINDINGS.map(({ storyId, commit, artifacts }) => ({
        storyId,
        commit,
        artifactCount: artifacts.length,
      })),
      [
        {
          storyId: 'ST-0501',
          commit: '1021982aff6bcab504e2c060ea0f82797b4dccf2',
          artifactCount: 9,
        },
        {
          storyId: 'ST-0504',
          commit: 'b78b4e3330faadc571207ccec889ba107eaf3bb7',
          artifactCount: 9,
        },
        {
          storyId: 'ST-1101',
          commit: '6933612a49863591555137868ca0cec935cf65e4',
          artifactCount: 14,
        },
      ],
    );
    for (const binding of PORTFOLIO_CATALOG_SOURCE_BINDINGS) {
      assert.match(binding.commit, /^[0-9a-f]{40}$/);
      assert.equal(
        new Set(binding.artifacts.map(({ path }) => path)).size,
        binding.artifacts.length,
      );
      for (const artifact of binding.artifacts) {
        assert.match(artifact.path, /^(?:changes|packages|python|scripts|tests)\//);
        assert.match(artifact.sha256, /^[0-9a-f]{64}$/);
      }
    }
  });

  it('preserves predecessor non-persistence, Human Review and disabled-route semantics', () => {
    const [workflow, identity, foundation] = PORTFOLIO_CATALOG_SOURCE_BINDINGS;
    assert.equal(workflow.semantics['operationCount'], 16);
    assert.deepEqual(workflow.semantics['operations'], ['LIST', 'CREATE', 'GET', 'UPDATE']);
    assert.equal(workflow.semantics['deleteRepresented'], false);
    assert.equal(workflow.semantics['repository'], 'ABSENT');
    assert.equal(workflow.semantics['persistence'], 'NOT_EXECUTED');
    assert.equal(identity.semantics['openDecision'], 'OD-006');
    assert.equal(identity.semantics['decision'], 'NOT_READY');
    assert.equal(identity.semantics['automaticMergeEnabled'], false);
    assert.equal(identity.semantics['automaticSplitEnabled'], false);
    assert.equal(identity.semantics['humanReviewRequired'], true);
    assert.deepEqual(identity.semantics['identityDecisions'], []);
    assert.deepEqual(foundation.semantics['registeredScreenIds'], ['ADM-001']);
    assert.deepEqual(foundation.semantics['registeredPaths'], ['/admin']);
    assert.deepEqual(foundation.semantics['portfolioCatalogRoutesRegistered'], []);
  });
});
