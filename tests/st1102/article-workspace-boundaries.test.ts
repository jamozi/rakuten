import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  ARTICLE_WORKSPACE_SCREEN_IDS,
  createArticleWorkspaceCandidate,
} from '../../packages/web-ui/src/index.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const source = readFileSync(
  resolve(repositoryRoot, 'packages/web-ui/src/article-workspace.ts'),
  'utf8',
);

describe('article workspace static disabled boundaries', () => {
  it('contains no runtime, I/O, environment, clock, randomness, database or provider surface', () => {
    assert.doesNotMatch(source, /from ['"](?:react|react-dom|next(?:\/|['"]))/i);
    assert.doesNotMatch(
      source,
      /from ['"]node:(?:fs|http|https|net|tls|child_process|crypto|os)['"]/,
    );
    assert.doesNotMatch(source, /\.(?:jsx|tsx)['"]/i);
    assert.doesNotMatch(
      source,
      /\b(?:document|window|navigator|fetch|XMLHttpRequest|WebSocket|EventSource)\b/,
    );
    assert.doesNotMatch(source, /\bprocess\.env\b|\bimport\.meta\.env\b/);
    assert.doesNotMatch(source, /\b(?:Date\.now|new Date|Math\.random|crypto\.randomUUID)\b/);
    assert.doesNotMatch(
      source,
      /from ['"](?:openai|@aws-sdk\/|@google|firebase|next-auth|sqlalchemy|pg)['"]/i,
    );
    assert.doesNotMatch(source, /\b(?:localStorage|sessionStorage|indexedDB|cookieStore|caches)\b/);
    assert.doesNotMatch(
      source,
      /\b(?:registerRoute|registerRuntime|routeHandler|createRouter|createServer)\s*\(/,
    );
  });

  it('does not expose role input or any authority/effect surface', () => {
    for (const screenId of ARTICLE_WORKSPACE_SCREEN_IDS) {
      const model = createArticleWorkspaceCandidate({ screenId });
      assert.equal(model.roleInputAccepted, false);
      assert.equal(model.roleMetadataAuthority, 'DISPLAY_ONLY_NOT_AUTHORIZATION');
      assert.equal(model.authenticationEstablished, false);
      assert.equal(model.authorizationGranted, false);
      assert.equal(model.mutationEnabled, false);
      assert.equal(model.persistenceEnabled, false);
      assert.equal(model.providerInvocationEnabled, false);
      assert.equal(model.externalActionEnabled, false);
      assert.equal(model.publicationAuthorized, false);
      assert.equal(model.criticalActionExecutionEnabled, false);
      assert.deepEqual(model.actions, []);
      assert.equal(model.acceptanceAchieved, false);
      assert.equal(model.storyComplete, false);
      assert.equal(model.decision, 'NOT_READY');
      assert.equal(model.productionEligible, false);
    }
  });

  it('keeps formal, browser, accessibility, live and delivery claims not executed', () => {
    const model = createArticleWorkspaceCandidate({ screenId: 'EDT-002' });
    assert.deepEqual(model.verification, {
      formalTst022: 'NOT_EXECUTED',
      formalTst024: 'NOT_EXECUTED',
      browser: 'NOT_EXECUTED',
      accessibility: 'NOT_EXECUTED',
      keyboard: 'NOT_EXECUTED',
      screenReader: 'NOT_EXECUTED',
      live: 'NOT_EXECUTED',
      staging: 'NOT_EXECUTED',
      release: 'NOT_EXECUTED',
      publication: 'NOT_EXECUTED',
      production: 'NOT_EXECUTED',
    });
  });
});
