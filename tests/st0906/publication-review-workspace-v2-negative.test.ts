import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PublicationReviewWorkspaceV2Error,
  createPublicationReviewWorkspaceV2,
  renderPublicationReviewWorkspaceHtmlV2,
  validatePublicationReviewWorkspaceV2,
  type PublicationReviewWorkspaceV2ErrorCode,
} from '../../packages/web-ui/src/index.ts';

function expectCode(action: () => unknown, code: PublicationReviewWorkspaceV2ErrorCode): void {
  assert.throws(action, (error: unknown) => {
    assert.ok(error instanceof PublicationReviewWorkspaceV2Error);
    assert.equal(error.name, 'PublicationReviewWorkspaceV2Error');
    assert.equal(error.code, code);
    assert.equal(error.message, code);
    assert.equal(error.cause, undefined);
    return true;
  });
}

function mutableModel(): Record<string, unknown> {
  return JSON.parse(
    JSON.stringify(createPublicationReviewWorkspaceV2({ screenId: 'PUBA-003' })),
  ) as Record<string, unknown>;
}

describe('ST-0906 V2 hostile input and candidate validation', () => {
  it('rejects malformed, expanded, unknown, subclassed, accessor, proxy and cyclic inputs', () => {
    expectCode(
      () => createPublicationReviewWorkspaceV2({ screenId: 'REV-999' as 'REV-001' }),
      'PUBLICATION_REVIEW_V2_SCREEN_UNKNOWN',
    );
    for (const input of [null, 'REV-001', {}, { screenId: 'REV-001', role: 'OPERATOR' }]) {
      expectCode(
        () =>
          createPublicationReviewWorkspaceV2(input as unknown as { readonly screenId: 'REV-001' }),
        'PUBLICATION_REVIEW_V2_INPUT_INVALID',
      );
    }

    class InputRecord {
      readonly screenId = 'REV-001';
    }
    expectCode(
      () =>
        createPublicationReviewWorkspaceV2(
          new InputRecord() as unknown as { readonly screenId: 'REV-001' },
        ),
      'PUBLICATION_REVIEW_V2_INPUT_INVALID',
    );

    const accessor = {} as { readonly screenId: 'REV-001' };
    Object.defineProperty(accessor, 'screenId', { enumerable: true, get: () => 'REV-001' });
    expectCode(
      () => createPublicationReviewWorkspaceV2(accessor),
      'PUBLICATION_REVIEW_V2_INPUT_INVALID',
    );

    const proxied = new Proxy(
      { screenId: 'REV-001' as const },
      { ownKeys: () => ['screenId', Symbol('hostile')] },
    );
    expectCode(
      () => createPublicationReviewWorkspaceV2(proxied),
      'PUBLICATION_REVIEW_V2_INPUT_INVALID',
    );

    const cycle: { screenId: 'REV-001'; self?: unknown } = { screenId: 'REV-001' };
    cycle.self = cycle;
    expectCode(
      () => createPublicationReviewWorkspaceV2(cycle),
      'PUBLICATION_REVIEW_V2_INPUT_INVALID',
    );
  });

  it('rejects route, authority, command, snapshot, preview and verification tamper', () => {
    const cases: Record<string, unknown>[] = [];

    const route = mutableModel() as { route: { registered: boolean } };
    route.route.registered = true;
    cases.push(route);

    const authority = mutableModel() as { authority: { publicationAuthorized: boolean } };
    authority.authority.publicationAuthorized = true;
    cases.push(authority);

    const command = mutableModel() as { commands: { effectPerformedByUi: boolean }[] };
    command.commands[0]!.effectPerformedByUi = true;
    cases.push(command);

    const snapshot = mutableModel() as { snapshot: { immutable: boolean } };
    snapshot.snapshot.immutable = false;
    cases.push(snapshot);

    const preview = mutableModel() as { preview: { publicReadServed: boolean } };
    preview.preview.publicReadServed = true;
    cases.push(preview);

    const verification = mutableModel() as { verification: { production: string } };
    verification.verification.production = 'EXECUTED';
    cases.push(verification);

    for (const candidate of cases) {
      expectCode(
        () => validatePublicationReviewWorkspaceV2(candidate),
        'PUBLICATION_REVIEW_V2_CANDIDATE_INVALID',
      );
      expectCode(
        () => renderPublicationReviewWorkspaceHtmlV2(candidate),
        'PUBLICATION_REVIEW_V2_RENDER_INPUT_INVALID',
      );
    }
  });

  it('rejects executable surfaces and never echoes hostile caller text', () => {
    const marker = 'do-not-retain-sensitive-caller-text';
    const callback = mutableModel();
    callback['callback'] = () => marker;
    expectCode(
      () => validatePublicationReviewWorkspaceV2(callback),
      'PUBLICATION_REVIEW_V2_CANDIDATE_INVALID',
    );

    const expanded = mutableModel();
    expanded['rawArticleBody'] = `<script>${marker}</script>`;
    for (const action of [
      () => validatePublicationReviewWorkspaceV2(expanded),
      () => renderPublicationReviewWorkspaceHtmlV2(expanded),
    ]) {
      try {
        action();
        assert.fail('expected closed validation failure');
      } catch (error: unknown) {
        assert.ok(error instanceof PublicationReviewWorkspaceV2Error);
        assert.doesNotMatch(String(error), new RegExp(marker, 'u'));
        assert.doesNotMatch(JSON.stringify(error), new RegExp(marker, 'u'));
      }
    }
  });
});
