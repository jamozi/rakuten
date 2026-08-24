import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  ArticleWorkspaceV2Error,
  createArticleWorkspaceV2,
  validateArticleWorkspaceV2Model,
} from '../../packages/web-ui/src/article-workspace-v2.ts';

function workspaceError(operation: () => unknown): ArticleWorkspaceV2Error {
  try {
    operation();
  } catch (error) {
    assert.ok(error instanceof ArticleWorkspaceV2Error);
    return error;
  }
  assert.fail('expected ST-1102 V2 validation failure');
}

function mutableModel(): Record<string, unknown> {
  return JSON.parse(JSON.stringify(createArticleWorkspaceV2({ screenId: 'EDT-002' }))) as Record<
    string,
    unknown
  >;
}

describe('ST-1102 V2 hostile input, authority and data boundary', () => {
  it('accepts only exact plain screen input and never echoes hostile values', () => {
    const canary = 'sensitive-workspace-v2-canary';
    for (const [value, code] of [
      [null, 'ARTICLE_WORKSPACE_V2_INPUT_INVALID'],
      [[], 'ARTICLE_WORKSPACE_V2_INPUT_INVALID'],
      [{}, 'ARTICLE_WORKSPACE_V2_INPUT_INVALID'],
      [{ screenId: null }, 'ARTICLE_WORKSPACE_V2_INPUT_INVALID'],
      [{ screenId: 'EDT-002', role: 'EDITOR' }, 'ARTICLE_WORKSPACE_V2_INPUT_INVALID'],
      [{ screenId: canary }, 'ARTICLE_WORKSPACE_V2_SCREEN_UNKNOWN'],
      [{ screenId: 'EDT-010' }, 'ARTICLE_WORKSPACE_V2_SCREEN_UNKNOWN'],
    ] as const) {
      const error = workspaceError(() => createArticleWorkspaceV2(value as never));
      assert.equal(error.code, code);
      assert.equal(error.message, code);
      assert.doesNotMatch(error.message, new RegExp(canary));
      assert.ok(Object.isFrozen(error));
    }
  });

  it('rejects accessors, symbols, subclasses, null prototypes, cycles and unreadable shapes', () => {
    const accessor = {};
    let getterCalled = false;
    Object.defineProperty(accessor, 'screenId', {
      enumerable: true,
      get() {
        getterCalled = true;
        return 'EDT-002';
      },
    });
    const symbol = { screenId: 'EDT-002' } as Record<PropertyKey, unknown>;
    symbol[Symbol('canary')] = true;
    const cyclic: { screenId: string; self?: unknown } = { screenId: 'EDT-002' };
    cyclic.self = cyclic;
    class HostileInput {
      screenId = 'EDT-002';
    }
    for (const value of [
      accessor,
      symbol,
      cyclic,
      new HostileInput(),
      Object.assign(Object.create(null), { screenId: 'EDT-002' }),
    ]) {
      assert.equal(
        workspaceError(() => createArticleWorkspaceV2(value as never)).code,
        'ARTICLE_WORKSPACE_V2_INPUT_INVALID',
      );
    }
    assert.equal(getterCalled, false);
  });

  it('rejects complete-model tampering and detaches a valid clone', () => {
    const input = mutableModel();
    const validated = validateArticleWorkspaceV2Model(input);
    assert.deepEqual(validated, input);
    assert.notEqual(validated, input);
    assert.notEqual(validated.article, input['article']);
    assert.ok(Object.isFrozen(validated));

    const status = mutableModel();
    status['localStatus'] = 'VALIDATED';
    assert.equal(
      workspaceError(() => validateArticleWorkspaceV2Model(status)).code,
      'ARTICLE_WORKSPACE_V2_MODEL_INVALID',
    );

    const authority = mutableModel();
    (authority['authority'] as Record<string, unknown>)['mutation_enabled'] = true;
    assert.equal(
      workspaceError(() => validateArticleWorkspaceV2Model(authority)).code,
      'ARTICLE_WORKSPACE_V2_MODEL_INVALID',
    );

    const extra = mutableModel();
    extra['unexpected'] = true;
    assert.equal(
      workspaceError(() => validateArticleWorkspaceV2Model(extra)).code,
      'ARTICLE_WORKSPACE_V2_MODEL_INVALID',
    );
  });

  it('rejects prohibited content/economics/callback surfaces without exposing them', () => {
    for (const [key, value] of [
      ['rawPrompt', 'canary'],
      ['rawSourceBody', 'canary'],
      ['reviewBody', 'canary'],
      ['rawHtml', '<script>canary</script>'],
      ['arbitraryUrl', 'https://example.invalid/canary'],
      ['financeData', { profit: 1 }],
      ['callback', 'canary'],
      ['publicProjection', { article: 'canary' }],
    ] as const) {
      const model = mutableModel();
      model[key] = value;
      const error = workspaceError(() => validateArticleWorkspaceV2Model(model));
      assert.equal(error.code, 'ARTICLE_WORKSPACE_V2_PROHIBITED_SURFACE');
      assert.equal(error.message, 'ARTICLE_WORKSPACE_V2_PROHIBITED_SURFACE');
      assert.doesNotMatch(error.message, /canary|example/i);
    }
  });

  it('keeps every authority/effect false and formal/external work unexecuted', () => {
    const model = createArticleWorkspaceV2({ screenId: 'EDT-002' });
    assert.ok(Object.values(model.authority).every((value) => value === false));
    assert.equal(model.concurrency.saveCommandAvailable, false);
    assert.equal(model.concurrency.overwriteAllowed, false);
    assert.equal(model.concurrency.automaticMergeAllowed, false);
    assert.equal(model.unsavedGuard.navigationEffectEnabled, false);
    assert.equal(model.unsavedGuard.saveAuthorized, false);
    assert.equal(model.unsavedGuard.discardAuthorized, false);
    assert.equal(model.formalAcceptanceAchieved, false);
    assert.equal(model.productionEligible, false);
    for (const [key, value] of Object.entries(model.verification)) {
      assert.equal(value, key === 'localModel' ? 'EXECUTED' : 'NOT_EXECUTED');
    }
  });
});
