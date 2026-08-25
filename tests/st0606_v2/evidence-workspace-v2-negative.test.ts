import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  EvidenceWorkspaceV2Error,
  ST0606_EVIDENCE_WORKSPACE_RECORDED_V2,
  createEvidenceWorkspaceModelV2,
  validateEvidenceWorkspaceProjectionV2,
} from '../../packages/web-ui/src/index.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

function expectError(operation: () => unknown, code: string): EvidenceWorkspaceV2Error {
  try {
    operation();
  } catch (error) {
    assert.ok(error instanceof EvidenceWorkspaceV2Error);
    assert.equal(error.code, code);
    assert.equal(error.message, code);
    return error;
  }
  assert.fail(`expected ${code}`);
}

interface MutableCandidate extends Record<string, unknown> {
  attestations: Array<Record<string, unknown>>;
  lifecycle: Record<string, unknown>;
  authority: Record<string, unknown>;
  source_access: {
    paths: unknown[];
  };
  coverage: Record<string, unknown>;
  screens: Array<{
    semantic_view: {
      h1: Record<string, unknown>;
    };
  }>;
}

function candidate(): MutableCandidate {
  return JSON.parse(JSON.stringify(ST0606_EVIDENCE_WORKSPACE_RECORDED_V2)) as MutableCandidate;
}

describe('ST-0606 V2 hostile boundaries', () => {
  it('rejects missing, unknown, extra, accessor, prototype and cyclic model inputs', () => {
    const canary = 'st0606-hostile-canary';
    for (const value of [
      null,
      [],
      {},
      { screenId: null },
      { screenId: 1 },
      { screenId: 'EVD-001', extra: canary },
      { screenID: 'EVD-001' },
    ]) {
      const error = expectError(
        () => createEvidenceWorkspaceModelV2(value),
        'EVIDENCE_WORKSPACE_V2_INPUT_INVALID',
      );
      assert.doesNotMatch(error.message, new RegExp(canary));
    }
    for (const value of [{ screenId: canary }, { screenId: 'evd-001' }, { screenId: ' EVD-001' }]) {
      const error = expectError(
        () => createEvidenceWorkspaceModelV2(value),
        'EVIDENCE_WORKSPACE_V2_SCREEN_UNKNOWN',
      );
      assert.doesNotMatch(error.message, new RegExp(canary));
    }
    const accessor = {};
    let getterCalled = false;
    Object.defineProperty(accessor, 'screenId', {
      enumerable: true,
      get() {
        getterCalled = true;
        return 'EVD-001';
      },
    });
    expectError(
      () => createEvidenceWorkspaceModelV2(accessor),
      'EVIDENCE_WORKSPACE_V2_INPUT_INVALID',
    );
    assert.equal(getterCalled, false);
    const cyclic: { screenId: string; self?: unknown } = { screenId: 'EVD-001' };
    cyclic.self = cyclic;
    expectError(
      () => createEvidenceWorkspaceModelV2(cyclic),
      'EVIDENCE_WORKSPACE_V2_INPUT_INVALID',
    );
    class Hostile {
      screenId = 'EVD-001';
    }
    expectError(
      () => createEvidenceWorkspaceModelV2(new Hostile()),
      'EVIDENCE_WORKSPACE_V2_INPUT_INVALID',
    );
  });

  it('fails closed on attestation kind/subject/input/contract provenance changes', () => {
    for (const key of ['kind', 'subject_sha256', 'input_sha256', 'contract_sha256']) {
      const value = candidate();
      const first = value.attestations[0];
      assert.ok(first);
      first[key] = key === 'kind' ? 'UNKNOWN_KIND' : 'f'.repeat(64);
      expectError(
        () => validateEvidenceWorkspaceProjectionV2(value),
        'EVIDENCE_WORKSPACE_V2_BINDING_INVALID',
      );
    }
    const missing = candidate();
    missing.attestations.pop();
    expectError(
      () => validateEvidenceWorkspaceProjectionV2(missing),
      'EVIDENCE_WORKSPACE_V2_BINDING_INVALID',
    );
  });

  it('rejects invented zero/pass, route authority, inaccessible sources and commercial inputs', () => {
    const unavailable = candidate();
    unavailable.lifecycle['packet_count'] = 0;
    expectError(
      () => validateEvidenceWorkspaceProjectionV2(unavailable),
      'EVIDENCE_WORKSPACE_V2_UNAVAILABLE_INVALID',
    );
    const authority = candidate();
    authority.authority['route_registration'] = true;
    expectError(
      () => validateEvidenceWorkspaceProjectionV2(authority),
      'EVIDENCE_WORKSPACE_V2_AUTHORITY_INVALID',
    );
    const unreachable = candidate();
    unreachable.source_access.paths.pop();
    expectError(
      () => validateEvidenceWorkspaceProjectionV2(unreachable),
      'EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE',
    );
    const commercial = candidate();
    commercial.coverage['profit'] = 1;
    expectError(
      () => validateEvidenceWorkspaceProjectionV2(commercial),
      'EVIDENCE_WORKSPACE_V2_PROHIBITED_INPUT',
    );
  });

  it('rejects semantic accessibility regressions and leaves the source headless', () => {
    const inaccessible = candidate();
    const firstScreen = inaccessible.screens[0];
    assert.ok(firstScreen);
    firstScreen.semantic_view.h1['count'] = 2;
    expectError(
      () => validateEvidenceWorkspaceProjectionV2(inaccessible),
      'EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID',
    );
    const source = readFileSync(
      resolve(repositoryRoot, 'packages/web-ui/src/evidence-workspace-v2.ts'),
      'utf8',
    );
    assert.doesNotMatch(source, /from ['"](?:react|next|next\/)/iu);
    assert.doesNotMatch(
      source,
      /\b(?:document|window|navigator|fetch|XMLHttpRequest|WebSocket)\b/u,
    );
    assert.doesNotMatch(source, /\b(?:onClick|onSubmit|useEffect|routeHandler)\b/u);
  });
});
