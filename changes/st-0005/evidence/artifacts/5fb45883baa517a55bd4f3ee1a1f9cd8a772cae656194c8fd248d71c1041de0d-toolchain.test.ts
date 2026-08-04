import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const exactVersion = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;

type JsonObject = Record<string, unknown>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readObject(relativePath: string): JsonObject {
  const parsed = JSON.parse(readFileSync(resolve(repositoryRoot, relativePath), 'utf8')) as unknown;
  if (!isObject(parsed)) {
    throw new TypeError(`${relativePath} must contain a JSON object`);
  }
  return parsed;
}

function parsePackageManager(value: unknown): readonly [string, string] {
  if (typeof value !== 'string') {
    throw new TypeError('packageManager must be a string');
  }
  const match = /^(?<name>[a-z0-9-]+)@(?<version>\d+\.\d+\.\d+)$/.exec(value);
  if (match?.groups === undefined) {
    throw new TypeError('packageManager must be an exact name@version pin');
  }
  return [match.groups['name'] ?? '', match.groups['version'] ?? ''] as const;
}

function directPins(manifest: JsonObject): Map<string, string> {
  const pins = new Map<string, string>();
  for (const section of ['dependencies', 'devDependencies'] as const) {
    const dependencies = manifest[section];
    if (dependencies === undefined) {
      continue;
    }
    if (!isObject(dependencies)) {
      throw new TypeError(`${section} must be an object`);
    }
    for (const [name, version] of Object.entries(dependencies)) {
      if (typeof version !== 'string' || !exactVersion.test(version)) {
        throw new TypeError(`${name} must use an exact version`);
      }
      if (pins.has(name)) {
        throw new TypeError(`${name} is declared more than once`);
      }
      pins.set(name, version);
    }
  }
  return pins;
}

describe('ST-0103 TypeScript toolchain contract', () => {
  it('parses the exact npm package-manager pin', () => {
    const root = readObject('package.json');
    expect(parsePackageManager(root['packageManager'])).toEqual(['npm', '11.16.0']);
    expect(() => parsePackageManager('npm@^11.16.0')).toThrow(/exact/);
    expect(() => parsePackageManager('npm@latest')).toThrow(/exact/);
  });

  it('keeps the workspace allowlist ordered and explicit', () => {
    const root = readObject('package.json');
    expect(root['workspaces']).toEqual(['apps/web', 'packages/web-contracts', 'packages/web-ui']);
  });

  it('keeps the supply-chain overrides exact and closed', () => {
    const root = readObject('package.json');
    expect(root['overrides']).toEqual({
      'next@16.2.12': {
        postcss: '8.5.25',
        sharp: '0.35.3',
      },
      vite: '8.2.0',
    });
  });

  it('accepts only exact direct dependency pins', () => {
    const manifests = [
      readObject('package.json'),
      readObject('apps/web/package.json'),
      readObject('packages/web-contracts/package.json'),
      readObject('packages/web-ui/package.json'),
    ];
    const pins = manifests.flatMap((manifest) => [...directPins(manifest)]);
    expect(pins.length).toBeGreaterThan(0);
    expect(pins).toContainEqual(['next', '16.2.12']);
    expect(pins).toContainEqual(['@hey-api/openapi-ts', '0.99.0']);
    expect(pins).toContainEqual(['typescript', '6.0.3']);
    expect(pins).toContainEqual(['vitest', '4.1.10']);
  });
});
