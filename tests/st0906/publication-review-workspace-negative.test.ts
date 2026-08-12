import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PublicationReviewError,
  createPublicationReviewWorkspaceModel,
  validatePublicationReviewWorkspaceModel,
  type PublicationReviewErrorCode,
} from '../../packages/web-ui/src/publication-review-workspace.ts';

function expectCode(action: () => unknown, code: PublicationReviewErrorCode): void {
  assert.throws(action, (error: unknown) => {
    assert.ok(error instanceof PublicationReviewError);
    assert.equal(error.name, 'PublicationReviewError');
    assert.equal(error.code, code);
    assert.equal(error.message, code);
    assert.equal(error.cause, undefined);
    return true;
  });
}

function mutableModel(): Record<string, unknown> {
  return JSON.parse(
    JSON.stringify(createPublicationReviewWorkspaceModel({ screenId: 'REV-003' })),
  ) as Record<string, unknown>;
}

describe('ST-0906 closed input and candidate validation', () => {
  it('rejects unknown, malformed, expanded, subclassed, accessor and cyclic input', () => {
    expectCode(
      () => createPublicationReviewWorkspaceModel({ screenId: 'REV-999' as 'REV-001' }),
      'PUBLICATION_REVIEW_SCREEN_UNKNOWN',
    );
    for (const input of [null, 'REV-001', {}, { screenId: 'REV-001', roles: [] }]) {
      expectCode(
        () =>
          createPublicationReviewWorkspaceModel(
            input as unknown as { readonly screenId: 'REV-001' },
          ),
        'PUBLICATION_REVIEW_INPUT_INVALID',
      );
    }

    class InputRecord {
      readonly screenId = 'REV-001';
    }
    expectCode(
      () =>
        createPublicationReviewWorkspaceModel(
          new InputRecord() as unknown as { readonly screenId: 'REV-001' },
        ),
      'PUBLICATION_REVIEW_INPUT_INVALID',
    );

    const accessor = {} as { readonly screenId: 'REV-001' };
    Object.defineProperty(accessor, 'screenId', { enumerable: true, get: () => 'REV-001' });
    expectCode(
      () => createPublicationReviewWorkspaceModel(accessor),
      'PUBLICATION_REVIEW_INPUT_INVALID',
    );

    const cycle: { screenId: 'REV-001'; self?: unknown } = { screenId: 'REV-001' };
    cycle.self = cycle;
    expectCode(
      () => createPublicationReviewWorkspaceModel(cycle),
      'PUBLICATION_REVIEW_INPUT_INVALID',
    );
  });

  it('rejects metadata, layout, state, accessibility and authority tamper separately', () => {
    const metadata = mutableModel() as { screen: { route: string } };
    metadata.screen.route = '/admin/elsewhere';
    expectCode(
      () => validatePublicationReviewWorkspaceModel(metadata),
      'PUBLICATION_REVIEW_METADATA_INVALID',
    );

    const layout = mutableModel() as { layout: { cardMosaic: boolean } };
    layout.layout.cardMosaic = true;
    expectCode(
      () => validatePublicationReviewWorkspaceModel(layout),
      'PUBLICATION_REVIEW_LAYOUT_INVALID',
    );

    const state = mutableModel() as { criticalBoundary: { stepUpDialogEffectEnabled: boolean } };
    state.criticalBoundary.stepUpDialogEffectEnabled = true;
    expectCode(
      () => validatePublicationReviewWorkspaceModel(state),
      'PUBLICATION_REVIEW_STATE_INVALID',
    );

    const accessibility = mutableModel() as { accessibility: { conformanceClaimed: boolean } };
    accessibility.accessibility.conformanceClaimed = true;
    expectCode(
      () => validatePublicationReviewWorkspaceModel(accessibility),
      'PUBLICATION_REVIEW_ACCESSIBILITY_INVALID',
    );

    const authority = mutableModel() as { actionIntents: unknown[] };
    authority.actionIntents.push({ kind: 'PUBLISH' });
    expectCode(
      () => validatePublicationReviewWorkspaceModel(authority),
      'PUBLICATION_REVIEW_AUTHORITY_INVALID',
    );
  });

  it('rejects duplicate catalog identity and route before generic metadata drift', () => {
    const duplicateId = mutableModel() as { catalogScreens: { id: string }[] };
    duplicateId.catalogScreens[1]!.id = duplicateId.catalogScreens[0]!.id;
    expectCode(
      () => validatePublicationReviewWorkspaceModel(duplicateId),
      'PUBLICATION_REVIEW_DUPLICATE_ID',
    );

    const duplicateRoute = mutableModel() as { catalogScreens: { route: string }[] };
    duplicateRoute.catalogScreens[1]!.route = duplicateRoute.catalogScreens[0]!.route;
    expectCode(
      () => validatePublicationReviewWorkspaceModel(duplicateRoute),
      'PUBLICATION_REVIEW_DUPLICATE_ROUTE',
    );
  });

  it('rejects executable callback surfaces and never echoes caller text', () => {
    const marker = 'do-not-retain-sensitive-caller-text';
    const prohibited = mutableModel();
    prohibited['callback'] = marker;
    expectCode(
      () => validatePublicationReviewWorkspaceModel(prohibited),
      'PUBLICATION_REVIEW_PROHIBITED_SURFACE',
    );
    try {
      validatePublicationReviewWorkspaceModel(prohibited);
      assert.fail('expected closed validation failure');
    } catch (error: unknown) {
      assert.ok(error instanceof PublicationReviewError);
      assert.doesNotMatch(String(error), new RegExp(marker));
      assert.doesNotMatch(JSON.stringify(error), new RegExp(marker));
    }
  });
});
