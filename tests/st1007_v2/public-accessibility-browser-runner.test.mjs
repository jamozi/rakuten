import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import {
  ClosedFailure,
  buildEvidence,
  encodeJson,
  parseArguments,
  sortJson,
} from '../../scripts/check_st1007_public_accessibility_browser.mjs';

const contract = JSON.parse(
  readFileSync('changes/st-1007/contracts/public-accessibility-local-browser.v2.json', 'utf8'),
);
const source = readFileSync('scripts/check_st1007_public_accessibility_browser.mjs', 'utf8');
const evidence = JSON.parse(
  readFileSync('changes/st-1007/generated/public-accessibility-local-browser.v2.json', 'utf8'),
);

function assertClosed(code, callback) {
  assert.throws(callback, (error) => error instanceof ClosedFailure && error.code === code);
}

describe('ST-1007 V2 closed owner arguments', () => {
  it('requires one exact mode and an absolute browser path', () => {
    assert.deepEqual(
      parseArguments(['--browser-executable', '/recorded/chrome', '--check']),
      Object.freeze({ browserExecutable: '/recorded/chrome', mode: 'check' }),
    );
    assertClosed('ARGUMENT_MODE_REQUIRED', () =>
      parseArguments(['--browser-executable', '/recorded/chrome']),
    );
    assertClosed('ARGUMENT_BROWSER_REQUIRED', () => parseArguments(['--write']));
    assertClosed('ARGUMENT_BROWSER_REQUIRED', () =>
      parseArguments(['--browser-executable', 'relative/chrome', '--write']),
    );
    assertClosed('ARGUMENT_MODE_INVALID', () =>
      parseArguments(['--check', '--write', '--browser-executable', '/recorded/chrome']),
    );
    assertClosed('ARGUMENT_UNKNOWN', () =>
      parseArguments(['--check', '--browser-executable', '/recorded/chrome', '--url']),
    );
  });
});

describe('ST-1007 V2 deterministic evidence projection', () => {
  it('sorts object keys while preserving ordered arrays and a terminal newline', () => {
    const value = { z: 1, a: { d: 2, c: 3 }, list: [{ b: 2, a: 1 }] };
    assert.deepEqual(sortJson(value), {
      a: { c: 3, d: 2 },
      list: [{ a: 1, b: 2 }],
      z: 1,
    });
    assert.equal(
      encodeJson(value).toString('utf8'),
      '{"a":{"c":3,"d":2},"list":[{"a":1,"b":2}],"z":1}\n',
    );
  });

  it('keeps local browser success separate from formal and Story acceptance', () => {
    const routes = contract.observed_routes.map((route) => ({
      axe: { incomplete: [], pass_rule_count: 1, violations: [] },
      expected_status: route.expected_status,
      h1_count: 1,
      keyboard:
        route.expected_status === 200
          ? {
              first_focus: 'SKIP_LINK',
              focus_indicator_visible: true,
              target_reached: true,
            }
          : { status: 'NOT_APPLICABLE_NON_200' },
      language: 'ja',
      main_count: route.expected_status === 200 ? 1 : 0,
      observed_status: route.expected_status,
      path: route.path,
      runtime_kind: route.runtime_kind,
      screen_id: route.screen_id,
      title: route.screen_id,
      viewports: [],
    }));
    const evidence = buildEvidence(
      contract,
      [{ bytes: 1, path: 'recorded', sha256: 'a'.repeat(64) }],
      {
        browser: {
          executable_sha256: contract.runtime.browser.executable_sha256,
          product: contract.runtime.browser.product,
          version: contract.runtime.browser.version,
        },
        routes,
      },
    );
    assert.equal(
      evidence.automated_execution.result,
      'LOCAL_AUTOMATED_PASS_IMPLEMENTED_SURFACES_ONLY',
    );
    assert.equal(evidence.formal_boundary['TST-023'], 'NOT_EXECUTED');
    assert.equal(evidence.formal_boundary['TST-024'], 'NOT_EXECUTED');
    assert.equal(
      evidence.formal_boundary.story_acceptance,
      'BLOCKED_INCOMPLETE_CANONICAL_SCREEN_AND_MANUAL_EVIDENCE',
    );
    assert.equal(evidence.canonical_coverage.unavailable_canonical_screens.length, 4);
    assert.equal(evidence.authority.publication, 'NONE');
    assert.equal(evidence.authority.production, 'NONE');
    assert.doesNotMatch(JSON.stringify(evidence), /VALIDATED|WCAG_CONFORMANT|PRODUCTION_READY/u);
  });
});

describe('ST-1007 V2 browser and network boundary', () => {
  it('pins one browser and axe bundle by exact SHA-256', () => {
    assert.equal(contract.runtime.browser.product, 'Chrome for Testing');
    assert.match(contract.runtime.browser.version, /^[0-9]+(?:\.[0-9]+){3}$/u);
    assert.match(contract.runtime.browser.executable_sha256, /^[a-f0-9]{64}$/u);
    assert.equal(contract.runtime.axe.version, '4.12.1');
    assert.match(contract.runtime.axe.script_sha256, /^[a-f0-9]{64}$/u);
    assert.match(source, /BROWSER_EXECUTABLE_HASH_DRIFT/u);
    assert.match(source, /AXE_HASH_DRIFT/u);
    assert.match(source, /BROWSER_VERSION_DRIFT/u);
  });

  it('limits the server and page to ephemeral loopback and fails external requests', () => {
    assert.equal(contract.runtime.origin_mode, 'LOOPBACK_EPHEMERAL_ONLY');
    assert.equal(contract.runtime.network_policy, 'LOOPBACK_DOCUMENT_AND_ASSETS_ONLY');
    assert.match(source, /const LOOPBACK_HOST = '127\.0\.0\.1'/u);
    assert.match(source, /UNEXPECTED_OUTBOUND_REQUEST/u);
    assert.match(source, /--host-resolver-rules=MAP \* 0\.0\.0\.0/u);
    assert.doesNotMatch(source, /https:\/\//u);
  });

  it('records only available surfaces and keeps all manual evidence unavailable', () => {
    assert.deepEqual(
      contract.observed_routes.map(({ screen_id: screenId }) => screenId),
      ['PUB-003', 'PUB-004', 'PUB-005', 'PUB-006', 'PUB-007', 'PUB-008'],
    );
    assert.deepEqual(
      contract.unavailable_canonical_screens.map(({ screen_id: screenId }) => screenId),
      ['PUB-001', 'PUB-002', 'PUB-009', 'PUB-010'],
    );
    assert.equal(contract.formal_boundary.screen_reader, 'NOT_EXECUTED');
    assert.equal(contract.formal_boundary.manual_keyboard, 'NOT_EXECUTED');
    assert.equal(contract.formal_boundary.manual_200_percent_zoom, 'NOT_EXECUTED');
    assert.equal(contract.formal_boundary.wcag_conformance, 'NOT_CLAIMED');
  });

  it('commits only deterministic non-formal local evidence', () => {
    assert.equal(evidence.schema_version, 2);
    assert.equal(evidence.story_id, 'ST-1007');
    assert.equal(
      evidence.automated_execution.result,
      'LOCAL_AUTOMATED_PASS_IMPLEMENTED_SURFACES_ONLY',
    );
    assert.equal(evidence.automated_execution.routes.length, 6);
    assert.ok(
      evidence.automated_execution.routes.every(
        (route) => route.axe.violations.length === 0 && route.axe.incomplete.length === 0,
      ),
    );
    assert.ok(
      evidence.automated_execution.routes.every((route) =>
        route.viewports.every((viewport) => viewport.document_overflow_css_px === 0),
      ),
    );
    const serialized = JSON.stringify(evidence);
    assert.doesNotMatch(
      serialized,
      /executed_at|timestamp|process_id|localhost|127\.0\.0\.1|raos-st1007-browser|\/home\//iu,
    );
    assert.equal(evidence.formal_boundary['TST-023'], 'NOT_EXECUTED');
    assert.equal(evidence.formal_boundary['TST-024'], 'NOT_EXECUTED');
  });
});
