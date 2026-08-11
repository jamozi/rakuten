import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { createAiGovernanceWorkspaceModel } from '../../packages/web-ui/src/index.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const source = readFileSync(
  resolve(repositoryRoot, 'packages/web-ui/src/ai-governance-workspace.ts'),
  'utf8',
);

describe('AI governance static safety boundaries', () => {
  it('has no React, Next, JSX, DOM, browser, fetch, HTTP, environment, or storage surface', () => {
    assert.doesNotMatch(source, /from ['"](?:react|react-dom|next(?:\/|['"]))/i);
    assert.doesNotMatch(source, /\.(?:jsx|tsx)['"]/i);
    assert.doesNotMatch(source, /\b(?:document|window|navigator|fetch|XMLHttpRequest|WebSocket)\b/);
    assert.doesNotMatch(source, /\b(?:http|https|node:http|node:https):?\/\//i);
    assert.doesNotMatch(source, /\bprocess\.env\b|\bimport\.meta\.env\b/);
    assert.doesNotMatch(source, /\b(?:localStorage|sessionStorage|indexedDB|cookieStore|caches)\b/);
  });

  it('has no provider SDK, effect hook, runtime registration, or action handler', () => {
    assert.doesNotMatch(
      source,
      /from ['"](?:openai|@aws-sdk\/|@google|firebase|next-auth|react-query)/i,
    );
    assert.doesNotMatch(source, /\b(?:useEffect|useLayoutEffect|addEventListener)\s*\(/);
    assert.doesNotMatch(
      source,
      /\b(?:registerRoute|registerRuntime|routeHandler|createRouter|createServer)\s*\(/,
    );
    assert.doesNotMatch(source, /\b(?:onClick|onSubmit|onActivate|onApprove|onRelease)\b/);
    assert.doesNotMatch(source, /\b(?:activate|approve|release|publish)\s*\(/i);
  });

  it('keeps the public export data-only and every authority-changing action forbidden', () => {
    const model = createAiGovernanceWorkspaceModel({ screenId: 'GOV-001' });
    assert.deepEqual(model.actions, []);
    assert.equal(model.activation, 'FORBIDDEN');
    assert.equal(model.approval, 'FORBIDDEN');
    assert.equal(model.release, 'FORBIDDEN');
    assert.equal(model.providerAction, 'FORBIDDEN');
    assert.equal(model.externalAction, 'FORBIDDEN');
    assert.equal(model.authorizationGranted, false);
    assert.equal(model.formalTst022, 'NOT_EXECUTED');
  });
});
