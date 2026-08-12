import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  PUBLICATION_REVIEW_COMPONENT_IDS,
  PUBLICATION_REVIEW_COMPONENTS,
  PUBLICATION_REVIEW_SCREEN_IDS,
  PUBLICATION_REVIEW_SCREENS,
  PUBLICATION_REVIEW_SOURCE_REFS,
} from '../../packages/web-ui/src/publication-review-workspace.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

describe('ST-0906 canonical static metadata contract', () => {
  it('projects exactly the seven REV/PUBA screens in canonical order', () => {
    assert.deepEqual(PUBLICATION_REVIEW_SCREEN_IDS, [
      'REV-001',
      'REV-002',
      'REV-003',
      'PUBA-001',
      'PUBA-002',
      'PUBA-003',
      'PUBA-004',
    ]);
    assert.deepEqual(
      PUBLICATION_REVIEW_SCREENS.map(({ id, route, roles, criticalAction, apiDependencies }) => [
        id,
        route,
        roles,
        criticalAction,
        apiDependencies,
      ]),
      [
        ['REV-001', '/admin/reviews', ['MANAGING_EDITOR', 'REVIEWER'], false, []],
        ['REV-002', '/admin/reviews/{versionId}', ['REVIEWER', 'MANAGING_EDITOR'], true, []],
        ['REV-003', '/admin/approvals/{versionId}', ['MANAGING_EDITOR'], true, ['FinalApproval']],
        ['PUBA-001', '/admin/publications', ['MANAGING_EDITOR', 'OPERATOR'], false, []],
        [
          'PUBA-002',
          '/admin/publications/{id}/preview',
          ['MANAGING_EDITOR', 'REVIEWER', 'OPERATOR'],
          false,
          [],
        ],
        ['PUBA-003', '/admin/publications/{id}/publish', ['MANAGING_EDITOR', 'OPERATOR'], true, []],
        [
          'PUBA-004',
          '/admin/publications/{id}/rollback',
          ['MANAGING_EDITOR', 'OPERATOR'],
          true,
          [],
        ],
      ],
    );
  });

  it('keeps catalog status closed and maps only display requirements', () => {
    for (const screen of PUBLICATION_REVIEW_SCREENS) {
      assert.equal(screen.mvp, true);
      assert.equal(screen.designStatus, 'APPROVED_FOR_IMPLEMENTATION');
      assert.equal(screen.implementationStatus, 'NOT_STARTED');
      assert.equal(screen.runtimeVerification, 'NOT_EXECUTED');
    }
    assert.deepEqual(PUBLICATION_REVIEW_COMPONENT_IDS, [
      'UI-C005',
      'UI-C006',
      'UI-C007',
      'UI-C008',
      'UI-C010',
      'UI-C011',
      'UI-C012',
      'UI-C013',
      'UI-C015',
      'UI-C016',
      'UI-C025',
      'UI-C026',
      'UI-C027',
      'UI-C028',
      'UI-C041',
    ]);
    assert.equal(PUBLICATION_REVIEW_COMPONENTS.length, 15);
    for (const component of PUBLICATION_REVIEW_COMPONENTS) {
      assert.equal(component.keyboardRequired, true);
      assert.equal(component.screenReaderRequired, true);
      assert.equal(component.implementationStatus, 'NOT_STARTED');
      assert.equal(component.runtimeVerification, 'NOT_EXECUTED');
    }
  });

  it('hash-binds every consumed canonical and dependency source', () => {
    assert.equal(PUBLICATION_REVIEW_SOURCE_REFS.length, 15);
    for (const reference of PUBLICATION_REVIEW_SOURCE_REFS) {
      const digest = createHash('sha256')
        .update(readFileSync(resolve(repositoryRoot, reference.path)))
        .digest('hex');
      assert.equal(digest, reference.sha256, reference.path);
    }
  });
});
