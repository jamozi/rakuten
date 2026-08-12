import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLICATION_REVIEW_LAYOUT_SECTION_IDS,
  PUBLICATION_REVIEW_SCREEN_IDS,
  createPublicationReviewWorkspaceModel,
  validatePublicationReviewWorkspaceModel,
} from '../../packages/web-ui/src/publication-review-workspace.ts';

function assertDeeplyFrozen(value: unknown, visited = new WeakSet<object>()): void {
  if (value === null || typeof value !== 'object' || visited.has(value)) {
    return;
  }
  visited.add(value);
  assert.ok(Object.isFrozen(value));
  for (const child of Object.values(value)) {
    assertDeeplyFrozen(child, visited);
  }
}

describe('ST-0906 disabled headless workspace model', () => {
  it('builds one deterministic deeply frozen model for every owned screen', () => {
    for (const screenId of PUBLICATION_REVIEW_SCREEN_IDS) {
      const model = createPublicationReviewWorkspaceModel({ screenId });
      assert.equal(model.screen.id, screenId);
      assert.equal(model.orientation.screenId, screenId);
      assert.equal(model.orientation.catalogRoute, model.screen.route);
      assert.equal(model.availability, 'DISABLED_DEPENDENCY_NOT_EXECUTABLE');
      assertDeeplyFrozen(model);
      assert.deepEqual(
        validatePublicationReviewWorkspaceModel(JSON.parse(JSON.stringify(model))),
        model,
      );
    }
  });

  it('uses the approved utility information sequence without hero or cards', () => {
    const model = createPublicationReviewWorkspaceModel({ screenId: 'REV-003' });
    assert.deepEqual(PUBLICATION_REVIEW_LAYOUT_SECTION_IDS, [
      'ORIENTATION',
      'BLOCKERS',
      'REVIEW',
      'DIFF',
      'PREVIEW',
    ]);
    assert.deepEqual(model.layout.sequence, PUBLICATION_REVIEW_LAYOUT_SECTION_IDS);
    assert.equal(model.layout.visualThesis, 'CALM_CARDLESS_UTILITY_WORKSPACE');
    assert.equal(model.layout.marketingHero, false);
    assert.equal(model.layout.cardMosaic, false);
    assert.equal(model.layout.ornamentalMotion, false);
    assert.ok(model.layout.sections.every((section) => section.card === false));
  });

  it('keeps all dependency state non-authoritative and effect-free', () => {
    const model = createPublicationReviewWorkspaceModel({ screenId: 'PUBA-003' });
    assert.deepEqual(
      model.dependencyStates.map(({ storyId }) => storyId),
      ['ST-0901', 'ST-0902', 'ST-0903', 'ST-0904', 'ST-0905', 'ST-1101'],
    );
    for (const dependency of model.dependencyStates) {
      assert.equal(dependency.runtimeConnected, false);
      assert.equal(dependency.authoritative, false);
      assert.equal(dependency.effectPermitted, false);
    }
    assert.equal(
      model.crossBoundarySafeguards.every((item) => !item.resolved),
      true,
    );
    assert.equal(
      model.crossBoundarySafeguards.every((item) => !item.decisionInferred),
      true,
    );
  });
});
