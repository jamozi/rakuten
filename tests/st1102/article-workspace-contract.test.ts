import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  ARTICLE_WORKSPACE_COMPONENT_IDS,
  ARTICLE_WORKSPACE_COMPONENTS,
  ARTICLE_WORKSPACE_EXCLUDED_SCREEN_IDS,
  ARTICLE_WORKSPACE_SCREEN_IDS,
  ARTICLE_WORKSPACE_SCREENS,
  ARTICLE_WORKSPACE_SOURCE_REFS,
} from '../../packages/web-ui/src/article-workspace.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

function sha256(bytes: Uint8Array): string {
  return createHash('sha256').update(bytes).digest('hex');
}

describe('ST-1102 canonical static metadata contract', () => {
  it('maps exactly the objective-owned screens and excludes adjacent EDT screens', () => {
    assert.deepEqual(ARTICLE_WORKSPACE_SCREEN_IDS, [
      'EDT-002',
      'EDT-003',
      'EDT-005',
      'EDT-006',
      'EDT-007',
      'EDT-009',
    ]);
    assert.deepEqual(ARTICLE_WORKSPACE_EXCLUDED_SCREEN_IDS, [
      'EDT-001',
      'EDT-004',
      'EDT-008',
      'EDT-010',
    ]);
    assert.equal(
      ARTICLE_WORKSPACE_SCREEN_IDS.some((id) =>
        (ARTICLE_WORKSPACE_EXCLUDED_SCREEN_IDS as readonly string[]).includes(id),
      ),
      false,
    );
  });

  it('pins exact catalog id, route, role, purpose, critical and API tuples', () => {
    assert.deepEqual(
      ARTICLE_WORKSPACE_SCREENS.map(
        ({ id, name, route, roles, purpose, criticalAction, apiDependencies }) => [
          id,
          name,
          route,
          roles,
          purpose,
          criticalAction,
          apiDependencies,
        ],
      ),
      [
        [
          'EDT-002',
          'Article Workspace',
          '/admin/articles/{id}',
          ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
          '企画から公開までの統合Workspace',
          false,
          ['Article', 'ArticleVersion', 'Findings'],
        ],
        [
          'EDT-003',
          'Content AST Editor',
          '/admin/articles/{id}/versions/{versionId}/content',
          ['MANAGING_EDITOR', 'EDITOR'],
          '型付きBlockを編集し未知Fieldを拒否',
          false,
          [],
        ],
        [
          'EDT-005',
          'AI Diff Review',
          '/admin/articles/{id}/ai-diff',
          ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
          'AI提案と人間編集差分を比較',
          false,
          [],
        ],
        [
          'EDT-006',
          'Claim–Evidence Matrix',
          '/admin/articles/{id}/claims',
          ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
          'ClaimごとのEvidence、時刻、Conflictを確認',
          true,
          ['Claim', 'ClaimEvidenceLink'],
        ],
        [
          'EDT-007',
          'Comparison Preview',
          '/admin/articles/{id}/comparison',
          ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
          '比較軸・単位・Unknown・Variantを検査',
          false,
          [],
        ],
        [
          'EDT-009',
          'SEO Preview',
          '/admin/articles/{id}/seo',
          ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
          'Title、Canonical、Robots、JSON-LD Preview',
          false,
          [],
        ],
      ],
    );
    for (const screen of ARTICLE_WORKSPACE_SCREENS) {
      assert.equal(screen.area, 'editorial');
      assert.equal(screen.mvp, true);
      assert.equal(screen.designStatus, 'APPROVED_FOR_IMPLEMENTATION');
      assert.equal(screen.implementationStatus, 'NOT_STARTED');
      assert.equal(screen.runtimeVerification, 'NOT_EXECUTED');
    }
  });

  it('pins the exact relevant component metadata', () => {
    assert.deepEqual(ARTICLE_WORKSPACE_COMPONENT_IDS, [
      'UI-C014',
      'UI-C015',
      'UI-C021',
      'UI-C022',
      'UI-C023',
      'UI-C036',
    ]);
    assert.deepEqual(
      ARTICLE_WORKSPACE_COMPONENTS.map(({ id, name, area, purpose }) => [id, name, area, purpose]),
      [
        ['UI-C014', 'UnsavedChangesGuard', 'admin', '離脱防止'],
        ['UI-C015', 'VersionDiff', 'admin', '追加/削除/変更と出所を比較'],
        ['UI-C021', 'ClaimEvidenceMatrix', 'admin', 'Claim×Evidence、Conflict、Freshness'],
        ['UI-C022', 'ContentBlockEditor', 'admin', 'Typed AST Block編集'],
        ['UI-C023', 'ComparisonTableEditor', 'admin', '商品×軸、Unit、Unknown'],
        ['UI-C036', 'UnknownValue', 'shared', '欠損を推測せず表示'],
      ],
    );
    for (const component of ARTICLE_WORKSPACE_COMPONENTS) {
      assert.equal(component.keyboardRequired, true);
      assert.equal(component.screenReaderRequired, true);
      assert.equal(component.designStatus, 'APPROVED_FOR_IMPLEMENTATION');
      assert.equal(component.implementationStatus, 'NOT_STARTED');
      assert.equal(component.runtimeVerification, 'NOT_EXECUTED');
    }
  });

  it('binds canonical and predecessor source references to exact bytes', () => {
    assert.equal(ARTICLE_WORKSPACE_SOURCE_REFS.length, 8);
    for (const reference of ARTICLE_WORKSPACE_SOURCE_REFS) {
      const bytes =
        reference.commit === null
          ? readFileSync(resolve(repositoryRoot, reference.path))
          : execFileSync('git', ['show', `${reference.commit}:${reference.path}`], {
              cwd: repositoryRoot,
              maxBuffer: 4 * 1024 * 1024,
            });
      assert.equal(sha256(bytes), reference.sha256, reference.path);
    }
  });

  it('deep-freezes every exported catalog value', () => {
    assert.ok(Object.isFrozen(ARTICLE_WORKSPACE_SCREEN_IDS));
    assert.ok(Object.isFrozen(ARTICLE_WORKSPACE_EXCLUDED_SCREEN_IDS));
    assert.ok(Object.isFrozen(ARTICLE_WORKSPACE_SCREENS));
    assert.ok(Object.isFrozen(ARTICLE_WORKSPACE_SCREENS[0]));
    assert.ok(Object.isFrozen(ARTICLE_WORKSPACE_SCREENS[0]?.roles));
    assert.ok(Object.isFrozen(ARTICLE_WORKSPACE_COMPONENTS));
    assert.ok(Object.isFrozen(ARTICLE_WORKSPACE_COMPONENTS[0]));
    assert.ok(Object.isFrozen(ARTICLE_WORKSPACE_SOURCE_REFS));
    assert.ok(Object.isFrozen(ARTICLE_WORKSPACE_SOURCE_REFS[0]));
  });
});
