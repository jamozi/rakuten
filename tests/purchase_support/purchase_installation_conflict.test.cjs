'use strict';
// Decision 3 (2026-09-15): a site reference withheld because official sources
// disagree is described as a conflict, not as a missing site reference.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SOURCE = path.resolve(__dirname, '../../changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/purchase-support.js');
const CONFLICT_TEXT = '公式資料で値が異なるため、この項目は照合しません。メーカーへ確認してください。';
const UNKNOWN_TEXT = 'サイト側の基準が未確認のため、この項目は照合できません。利用者の未入力ではありません。型番の公式資料で確認してください。';
const INVALID_TEXT = '基準データの不備があるため、この項目は照合できません。型番の公式資料で確認してください。';
const reference = { width_mm: 550, depth_mm: 341, height_mm: 600, door_depth_mm: null, door_height_mm: 712, above_mm: 120, left_mm: 5, right_mm: 5, rear_mm: null };

const load = () => {
  const context = { module: { exports: {} } };
  vm.runInNewContext(fs.readFileSync(SOURCE, 'utf8'), context);
  return context.module.exports;
};

test('a conflicting reference gets the conflict text; other unset references keep theirs', () => {
  const { assessInstallation, installationConflictKeys, installationReferenceText } = load();
  assert.equal(typeof installationConflictKeys, 'function');
  assert.equal(typeof installationReferenceText, 'function');
  const conflicts = installationConflictKeys('["door_depth_mm"]');
  const fields = Object.fromEntries(assessInstallation(reference, {}).fields.map(f => [f.key, f]));
  assert.equal(installationReferenceText(fields.door_depth_mm, conflicts), CONFLICT_TEXT);
  assert.equal(installationReferenceText(fields.rear_mm, conflicts), UNKNOWN_TEXT);
  const invalid = Object.fromEntries(assessInstallation({ ...reference, rear_mm: -1 }, {}).fields.map(f => [f.key, f]));
  assert.equal(installationReferenceText(invalid.rear_mm, installationConflictKeys('["rear_mm"]')), INVALID_TEXT);
});

test('the summary counts conflicts apart from missing site references', () => {
  const { assessInstallation, installationConflictKeys, installationSummary } = load();
  const assessment = assessInstallation(reference, {});
  assert.match(installationSummary(assessment, installationConflictKeys('["door_depth_mm"]')), /／サイト側の基準未確認 1項目／公式資料で値が異なる 1項目。/);
  assert.match(installationSummary(assessment), /／サイト側の基準未確認 2項目。/);
  assert.doesNotMatch(installationSummary(assessment), /公式資料で値が異なる/);
});

test('conflict keys are read defensively', () => {
  const { installationConflictKeys } = load();
  for (const raw of [undefined, null, '', 'not json', '{"door_depth_mm":true}', '[1]', '["with_mm"]']) {
    assert.deepEqual([...installationConflictKeys(raw)], [], String(raw));
  }
  assert.deepEqual([...installationConflictKeys('["rear_mm","door_depth_mm","rear_mm"]')], ['rear_mm', 'door_depth_mm']);
});
