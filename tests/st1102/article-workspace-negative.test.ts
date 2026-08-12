import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  ArticleWorkspaceError,
  createArticleWorkspaceCandidate,
  validateArticleWorkspaceCandidate,
} from '../../packages/web-ui/src/article-workspace.ts';

function workspaceError(operation: () => unknown): ArticleWorkspaceError {
  try {
    operation();
  } catch (error) {
    assert.ok(error instanceof ArticleWorkspaceError);
    return error;
  }
  assert.fail('expected article workspace validation to fail');
}

function mutableCandidate(): Record<string, unknown> {
  return JSON.parse(
    JSON.stringify(createArticleWorkspaceCandidate({ screenId: 'EDT-002' })),
  ) as Record<string, unknown>;
}

function asRecord(value: unknown): Record<string, unknown> {
  assert.notEqual(value, null);
  assert.equal(typeof value, 'object');
  assert.equal(Array.isArray(value), false);
  return value as Record<string, unknown>;
}

function arrayAt(record: Record<string, unknown>, key: string): unknown[] {
  const value = record[key];
  assert.ok(Array.isArray(value));
  return value;
}

describe('article workspace hostile input and candidate boundary', () => {
  it('normalizes direct and subclass construction to the closed error vocabulary', () => {
    const canary = 'hostile-error-code-canary';
    const direct = new ArticleWorkspaceError(canary as never);
    assert.equal(direct.code, 'ARTICLE_WORKSPACE_CANDIDATE_INVALID');
    assert.equal(direct.message, 'ARTICLE_WORKSPACE_CANDIDATE_INVALID');
    assert.doesNotMatch(direct.message, new RegExp(canary));
    assert.ok(Object.isFrozen(direct));

    class HostileWorkspaceError extends ArticleWorkspaceError {}
    const subclass = new HostileWorkspaceError(canary as never);
    assert.equal(subclass.code, 'ARTICLE_WORKSPACE_CANDIDATE_INVALID');
    assert.equal(subclass.message, 'ARTICLE_WORKSPACE_CANDIDATE_INVALID');
    assert.doesNotMatch(subclass.message, new RegExp(canary));
    assert.ok(Object.isFrozen(subclass));
  });

  it('accepts only the exact plain {screenId} input without echoing values', () => {
    const canary = 'sensitive-article-workspace-canary';
    const cases = [
      [null, 'ARTICLE_WORKSPACE_INPUT_INVALID'],
      [[], 'ARTICLE_WORKSPACE_INPUT_INVALID'],
      [{}, 'ARTICLE_WORKSPACE_INPUT_INVALID'],
      [{ screenId: null }, 'ARTICLE_WORKSPACE_INPUT_INVALID'],
      [{ screenId: 1 }, 'ARTICLE_WORKSPACE_INPUT_INVALID'],
      [{ screenID: 'EDT-002' }, 'ARTICLE_WORKSPACE_INPUT_INVALID'],
      [{ screenId: 'EDT-002', role: 'EDITOR' }, 'ARTICLE_WORKSPACE_INPUT_INVALID'],
      [{ screenId: 'EDT-002', extra: canary }, 'ARTICLE_WORKSPACE_INPUT_INVALID'],
      [{ screenId: canary }, 'ARTICLE_WORKSPACE_SCREEN_UNKNOWN'],
      [{ screenId: 'edt-002' }, 'ARTICLE_WORKSPACE_SCREEN_UNKNOWN'],
      [{ screenId: ' EDT-002' }, 'ARTICLE_WORKSPACE_SCREEN_UNKNOWN'],
      [{ screenId: 'EDT-001' }, 'ARTICLE_WORKSPACE_SCREEN_UNKNOWN'],
      [{ screenId: 'EDT-004' }, 'ARTICLE_WORKSPACE_SCREEN_UNKNOWN'],
      [{ screenId: 'EDT-008' }, 'ARTICLE_WORKSPACE_SCREEN_UNKNOWN'],
      [{ screenId: 'EDT-010' }, 'ARTICLE_WORKSPACE_SCREEN_UNKNOWN'],
    ] as const;
    for (const [value, code] of cases) {
      const error = workspaceError(() => createArticleWorkspaceCandidate(value as never));
      assert.equal(error.code, code);
      assert.equal(error.message, code);
      assert.doesNotMatch(error.message, new RegExp(canary));
      assert.ok(Object.isFrozen(error));
    }
  });

  it('rejects subclass, null-prototype, symbol, accessor, hidden, cyclic and dangerous input', () => {
    const canary = 'hostile-input-canary';
    const symbolInput = { screenId: 'EDT-002' } as Record<PropertyKey, unknown>;
    symbolInput[Symbol(canary)] = canary;
    const accessorInput = {};
    let getterCalled = false;
    Object.defineProperty(accessorInput, 'screenId', {
      enumerable: true,
      get() {
        getterCalled = true;
        return canary;
      },
    });
    const hiddenInput = {};
    Object.defineProperty(hiddenInput, 'screenId', {
      enumerable: false,
      value: 'EDT-002',
    });
    const cyclic: { screenId: string; self?: unknown } = { screenId: 'EDT-002' };
    cyclic.self = cyclic;
    const dangerousInput = Object.create(null) as Record<string, unknown>;
    Object.defineProperty(dangerousInput, 'screenId', {
      enumerable: true,
      value: 'EDT-002',
    });
    Object.defineProperty(dangerousInput, '__proto__', {
      enumerable: true,
      value: canary,
    });
    class HostileInput {
      screenId = 'EDT-002';
    }

    for (const value of [
      symbolInput,
      accessorInput,
      hiddenInput,
      cyclic,
      dangerousInput,
      new HostileInput(),
      Object.assign(Object.create(null), { screenId: 'EDT-002' }),
      { screenId: () => canary },
      { screenId: Symbol(canary) },
      { screenId: 1n },
    ]) {
      const error = workspaceError(() => createArticleWorkspaceCandidate(value as never));
      assert.equal(error.code, 'ARTICLE_WORKSPACE_INPUT_INVALID');
      assert.doesNotMatch(error.message, new RegExp(canary));
    }
    assert.equal(getterCalled, false);
  });

  it('rejects exact-candidate tampering and returns a detached deep-frozen clone', () => {
    const input = mutableCandidate();
    const validated = validateArticleWorkspaceCandidate(input);
    assert.deepEqual(validated, input);
    assert.notEqual(validated, input);
    assert.notEqual(validated.screen, input['screen']);
    assert.ok(Object.isFrozen(validated));
    assert.ok(Object.isFrozen(validated.screen));

    const metadata = mutableCandidate();
    asRecord(metadata['screen'])['purpose'] = 'invented';
    assert.equal(
      workspaceError(() => validateArticleWorkspaceCandidate(metadata)).code,
      'ARTICLE_WORKSPACE_METADATA_INVALID',
    );

    const state = mutableCandidate();
    asRecord(arrayAt(state, 'projections')[0])['payload'] = { invented: true };
    assert.equal(
      workspaceError(() => validateArticleWorkspaceCandidate(state)).code,
      'ARTICLE_WORKSPACE_STATE_INVALID',
    );

    const accessibility = mutableCandidate();
    asRecord(asRecord(accessibility['accessibility'])['h1'])['count'] = 2;
    assert.equal(
      workspaceError(() => validateArticleWorkspaceCandidate(accessibility)).code,
      'ARTICLE_WORKSPACE_ACCESSIBILITY_INVALID',
    );

    const authority = mutableCandidate();
    authority['mutationEnabled'] = true;
    assert.equal(
      workspaceError(() => validateArticleWorkspaceCandidate(authority)).code,
      'ARTICLE_WORKSPACE_AUTHORITY_INVALID',
    );

    const extra = mutableCandidate();
    extra['unexpected'] = true;
    assert.equal(
      workspaceError(() => validateArticleWorkspaceCandidate(extra)).code,
      'ARTICLE_WORKSPACE_CANDIDATE_INVALID',
    );
  });

  it('rejects duplicate identifiers and routes before ordinary metadata drift', () => {
    const duplicateId = mutableCandidate();
    const duplicateIdScreens = arrayAt(duplicateId, 'catalogScreens');
    asRecord(duplicateIdScreens[1])['id'] = asRecord(duplicateIdScreens[0])['id'];
    assert.equal(
      workspaceError(() => validateArticleWorkspaceCandidate(duplicateId)).code,
      'ARTICLE_WORKSPACE_DUPLICATE_ID',
    );

    const duplicateRoute = mutableCandidate();
    const duplicateRouteScreens = arrayAt(duplicateRoute, 'catalogScreens');
    asRecord(duplicateRouteScreens[1])['route'] = asRecord(duplicateRouteScreens[0])['route'];
    assert.equal(
      workspaceError(() => validateArticleWorkspaceCandidate(duplicateRoute)).code,
      'ARTICLE_WORKSPACE_DUPLICATE_ROUTE',
    );

    const duplicateSemanticId = mutableCandidate();
    const duplicateSemanticElements = arrayAt(
      asRecord(duplicateSemanticId['accessibility']),
      'elements',
    );
    asRecord(duplicateSemanticElements[1])['id'] = asRecord(duplicateSemanticElements[0])['id'];
    assert.equal(
      workspaceError(() => validateArticleWorkspaceCandidate(duplicateSemanticId)).code,
      'ARTICLE_WORKSPACE_DUPLICATE_ID',
    );
  });

  it('rejects raw content, finance/public data, callbacks, URLs, origins and escalation', () => {
    const prohibited = [
      ['rawHtml', '<script>canary</script>'],
      ['iframe', '<iframe>canary</iframe>'],
      ['onClick', 'canary'],
      ['rawPrompt', 'canary'],
      ['rawSource', 'canary'],
      ['articleText', 'canary'],
      ['financeData', { revenue: 1 }],
      ['publicData', { article: 'canary' }],
      ['callback', 'canary'],
      ['url', 'https://example.invalid/canary'],
      ['origin', 'https://example.invalid'],
      ['authorityToken', 'APPROVED'],
    ] as const;
    for (const [key, value] of prohibited) {
      const candidate = mutableCandidate();
      candidate[key] = value;
      const error = workspaceError(() => validateArticleWorkspaceCandidate(candidate));
      assert.equal(error.code, 'ARTICLE_WORKSPACE_PROHIBITED_SURFACE', key);
      assert.equal(error.message, 'ARTICLE_WORKSPACE_PROHIBITED_SURFACE');
      assert.doesNotMatch(error.message, /canary|example/i);
    }
  });

  it('does not expose any mutable candidate surface', () => {
    const model = createArticleWorkspaceCandidate({ screenId: 'EDT-006' });
    assert.throws(() => {
      (model as { availability: string }).availability = 'ENABLED';
    }, TypeError);
    assert.throws(() => {
      (model.actions as unknown as unknown[]).push('approve');
    }, TypeError);
    assert.throws(() => {
      (model.screen.roles as string[]).push('PRODUCT_OWNER');
    }, TypeError);
    assert.throws(() => {
      (model.projections[0]?.componentIds as string[]).push('UI-C999');
    }, TypeError);
    assert.throws(() => {
      (model.sourceRefs as unknown as unknown[]).push('invented');
    }, TypeError);
  });
});
