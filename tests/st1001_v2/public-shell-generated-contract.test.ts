import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { PUBLIC_POLICY_CONTENT_SOURCE } from '../../apps/web/src/public-policy-content.generated.ts';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const fixture = JSON.parse(
  readFileSync(
    resolve(root, 'changes/st-1001/generated/public-app-shell-recorded.v2.json'),
    'utf8',
  ),
) as Record<string, unknown>;

describe('ST-1001 V2 generated contract', () => {
  it('keeps the runtime TypeScript content byte-semantically equal to the recorded fixture', () => {
    assert.deepEqual(PUBLIC_POLICY_CONTENT_SOURCE, fixture);
  });

  it('retains no site identity, domain, contact, consent, or operational authority', () => {
    const identity = fixture['identityBoundary'] as Record<string, unknown>;
    const privacy = fixture['privacyBoundary'] as Record<string, unknown>;
    const authority = fixture['authority'] as Record<string, unknown>;
    assert.deepEqual(identity, {
      contact: null,
      decisionId: 'OD-002',
      domain: null,
      externalPublicationAllowed: false,
      metadataBase: null,
      operator: null,
      siteName: null,
      state: 'HUMAN_DECISION_REQUIRED',
    });
    assert.equal(privacy['nonessentialTrackingEnabled'], false);
    assert.equal(privacy['consentModeSelected'], false);
    assert.equal(privacy['firstPartyEventEmitted'], false);
    for (const [key, value] of Object.entries(authority)) {
      assert.equal(
        typeof value === 'boolean' ? value : value === 'NOT_EXECUTED',
        typeof value === 'boolean' ? false : true,
        key,
      );
    }
  });

  it('contains no URL, HTML, script, secret, personal data, or internal payload', () => {
    const serialized = JSON.stringify(fixture);
    assert.doesNotMatch(serialized, /https?:\/\/|javascript:|<\/?[a-z]|onerror|onclick/i);
    assert.doesNotMatch(
      serialized,
      /credential|secret|password|token|rawPrompt|sourcePacket|providerResponse|reviewBody/i,
    );
    assert.doesNotMatch(serialized, /@[a-z0-9.-]+\.[a-z]{2,}|\b\d{3}-\d{4}\b/i);
  });
});
