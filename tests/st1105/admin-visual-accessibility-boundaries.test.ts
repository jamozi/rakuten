import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { createAdminVisualAccessibilityCandidate } from '../../packages/web-ui/src/index.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const source = readFileSync(
  resolve(repositoryRoot, 'packages/web-ui/src/admin-visual-accessibility-acceptance.ts'),
  'utf8',
);

describe('ST-1105 protected headless boundaries', () => {
  it('exposes only the approved data boundary and no authority surfaces', () => {
    const candidate = createAdminVisualAccessibilityCandidate({ screenId: 'ANA-001' });
    assert.deepEqual(Object.keys(candidate).sort(), [
      'checklistAssessments',
      'classification',
      'componentOwnership',
      'components',
      'criticalWorkflowIds',
      'criticalWorkflowSelection',
      'screenScope',
      'selectedScreenId',
      'storyId',
      'suites',
      'visualBaseline',
    ]);
    for (const key of [
      'routes',
      'actions',
      'effects',
      'authorization',
      'runtime',
      'evidence',
      'conformance',
      'storyComplete',
    ]) {
      assert.equal(Object.hasOwn(candidate, key), false);
    }
  });

  it('imports no DOM, React, Next, browser, filesystem, network, clock, or random dependency', () => {
    assert.deepEqual(
      [...source.matchAll(/^import .* from ['"]([^'"]+)['"];$/gm)].map((match) => match[1]),
      ['./serializable.ts'],
    );
    assert.doesNotMatch(source, /from ['"](?:react|react-dom|next(?:\/|['"])|node:)/i);
    assert.doesNotMatch(source, /\b(?:document|window|navigator)\s*\./);
    assert.doesNotMatch(source, /\bfetch\s*\(/);
    assert.doesNotMatch(source, /\b(?:process\.env|Date\.now|Math\.random)\b/);
    assert.doesNotMatch(
      source,
      /\b(?:readFile|writeFile|openSync|createServer|createRouter|registerRoute)\s*\(/,
    );
    assert.doesNotMatch(source, /^import .* from ['"](?:playwright|axe-core)['"];$/gm);
  });

  it('contains no component or workflow inventory behind the empty ownership boundary', () => {
    const candidate = createAdminVisualAccessibilityCandidate({ screenId: 'EDT-005' });
    assert.deepEqual(candidate.components, []);
    assert.equal(candidate.componentOwnership, 'NOT_INFERRED');
    assert.deepEqual(candidate.criticalWorkflowIds, []);
    assert.equal(candidate.criticalWorkflowSelection, 'NOT_EVALUATED');
  });
});
