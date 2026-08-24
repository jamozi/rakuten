import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { describe, it } from 'node:test';

import {
  ST0606_RECORDED_PROJECTION_V2_JSON,
  ST0606_RECORDED_PROJECTION_V2_SHA256,
} from '../../packages/web-ui/src/index.ts';

describe('ST-0606 V2 generated evidence projection', () => {
  it('binds exact deterministic bytes and the current ST-0604/ST-0605 sources', () => {
    const bytes = Buffer.from(`${ST0606_RECORDED_PROJECTION_V2_JSON}\n`, 'ascii');
    assert.equal(
      createHash('sha256').update(bytes).digest('hex'),
      ST0606_RECORDED_PROJECTION_V2_SHA256,
    );
    const projection = JSON.parse(ST0606_RECORDED_PROJECTION_V2_JSON) as {
      source_bindings: Array<{ uri: string; sha256: string }>;
      lifecycle: Record<string, unknown>;
      coverage: {
        authority: string;
        publication_authorized: boolean;
        production_eligible: boolean;
        live_state: string;
        report: Record<string, unknown>;
      };
      attestations: Array<Record<string, unknown>>;
    };
    assert.deepEqual(
      projection.source_bindings.find(
        (binding) =>
          binding.uri ===
          'repo://changes/st-0604/generated/source-packet-lifecycle-reference-plan.v1.json',
      ),
      {
        uri: 'repo://changes/st-0604/generated/source-packet-lifecycle-reference-plan.v1.json',
        sha256: '00e6e974f9003ee92cb0a9b4a0ca5a975286e7fd41a6e32cf1224e312cd78cec',
      },
    );
    assert.deepEqual(
      projection.source_bindings.find(
        (binding) =>
          binding.uri === 'repo://changes/st-0605/generated/claim-evidence-runtime-pass.v1.json',
      ),
      {
        uri: 'repo://changes/st-0605/generated/claim-evidence-runtime-pass.v1.json',
        sha256: 'eb1c36bd1f70ea27e57e1720b937211286578136e701664b5fb4c8c823395226',
      },
    );
    assert.equal(projection.lifecycle['authority'], 'CURRENT_LIFECYCLE_SOURCE');
    assert.equal(projection.lifecycle['availability'], 'UNAVAILABLE');
    assert.equal(projection.lifecycle['packet_count'], null);
    assert.equal(projection.lifecycle['approval'], false);
    assert.equal(projection.coverage.authority, 'RECORDED_SYNTHETIC_COVERAGE_ONLY');
    assert.equal(
      projection.coverage.report['report_sha256'],
      '3a824290625cb30ee75ede4c547540f06dcf28a5b9cb12e53ce3fa4bcc0bcd38',
    );
    assert.equal(
      projection.coverage.report['evaluation_input_sha256'],
      '96347887ace475691d5a62ff0b7d05525ca2465204d29601e2eb106573a90a30',
    );
    assert.equal(projection.coverage.publication_authorized, false);
    assert.equal(projection.coverage.production_eligible, false);
    assert.equal(projection.coverage.live_state, 'UNKNOWN');
  });

  it('retains every ST-0605 kind/subject/input/contract provenance binding', () => {
    const projection = JSON.parse(ST0606_RECORDED_PROJECTION_V2_JSON) as {
      attestations: Array<Record<string, unknown>>;
    };
    assert.equal(projection.attestations.length, 8);
    assert.deepEqual(
      projection.attestations.map((row) => row['kind']),
      [
        'CLAIM_INVENTORY',
        'ARTICLE_PACKET_BINDING',
        'PACKET_APPROVAL_MEMBERSHIP',
        'FACT_VALIDATION',
        'FACT_VALIDATION',
        'IDENTITY_DECISION',
        'IDENTITY_DECISION',
        'CONFLICT_CLOSURE',
      ],
    );
    for (const row of projection.attestations) {
      assert.equal(row['origin'], 'RECORDED_SYNTHETIC_ONLY');
      assert.equal(row['valid'], true);
      for (const key of ['contract_sha256', 'subject_sha256', 'input_sha256', 'decision_sha256']) {
        assert.match(String(row[key]), /^[0-9a-f]{64}$/u);
      }
    }
  });
});
