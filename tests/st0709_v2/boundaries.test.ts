import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { AI_GOVERNANCE_RECORDED_FIXTURE_V2 } from '../../packages/web-ui/src/index.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const source = readFileSync(
  resolve(repositoryRoot, 'packages/web-ui/src/ai-governance-workspace-v2.ts'),
  'utf8',
);
const fixtureText = JSON.stringify(AI_GOVERNANCE_RECORDED_FIXTURE_V2);

describe('ST-0709 V2 static and operational boundaries', () => {
  it('has no React, DOM, network, environment, storage, provider SDK or route registration', () => {
    assert.doesNotMatch(source, /from ['"](?:react|react-dom|next(?:\/|['"]))/i);
    assert.doesNotMatch(
      source,
      /\b(?:globalThis\.(?:document|window|navigator)|document\.|window\.|navigator\.|fetch\s*\(|XMLHttpRequest|WebSocket)\b/,
    );
    assert.doesNotMatch(source, /\bprocess\.env\b|\bimport\.meta\.env\b/);
    assert.doesNotMatch(source, /\b(?:localStorage|sessionStorage|indexedDB|cookieStore|caches)\b/);
    assert.doesNotMatch(
      source,
      /from ['"](?:openai|@aws-sdk\/|@google|firebase|next-auth|react-query)/i,
    );
    assert.doesNotMatch(
      source,
      /\b(?:registerRoute|registerRuntime|createRouter|createServer)\s*\(/,
    );
    assert.doesNotMatch(source, /\b(?:onClick|onSubmit|onActivate|onApprove|onRelease)\b/);
  });

  it('contains no raw prompt, source, provider response, job artifact, review body or secret field', () => {
    for (const key of [
      'promptBody',
      'rawPrompt',
      'rawSource',
      'providerResponse',
      'jobArtifact',
      'reviewBody',
      'personalData',
      'credential',
      'secret',
    ]) {
      assert.doesNotMatch(fixtureText, new RegExp(`"${key}"`));
    }
  });

  it('does not elevate local checks to formal, browser, live, staging or Production evidence', () => {
    assert.deepEqual(AI_GOVERNANCE_RECORDED_FIXTURE_V2.formalStatus, {
      accessibility: 'NOT_EXECUTED',
      browser: 'NOT_EXECUTED',
      live_provider: 'NOT_EXECUTED',
      production: 'NOT_EXECUTED',
      release: 'NOT_EXECUTED',
      staging: 'NOT_EXECUTED',
      tst_022: 'NOT_EXECUTED',
    });
    assert.equal(AI_GOVERNANCE_RECORDED_FIXTURE_V2.releaseGuard['action_count'], 0);
    assert.equal(
      AI_GOVERNANCE_RECORDED_FIXTURE_V2.releaseGuard['approval_authority'],
      'HUMAN_ONLY',
    );
  });
});
