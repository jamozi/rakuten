import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

function readJson(relative: string): Record<string, unknown> {
  return JSON.parse(readFileSync(resolve(repositoryRoot, relative), 'utf8')) as Record<
    string,
    unknown
  >;
}

describe('ST-1101 workspace package boundary', () => {
  it('declares one ESM source export and an owner-local strict typecheck', () => {
    const packageJson = readJson('packages/web-ui/package.json');
    assert.deepEqual(packageJson, {
      name: '@raos/web-ui',
      version: '0.0.0',
      private: true,
      type: 'module',
      exports: { '.': './src/index.ts' },
      scripts: { typecheck: 'tsc --noEmit --project tsconfig.json' },
    });

    const tsconfig = readJson('packages/web-ui/tsconfig.json');
    assert.deepEqual(tsconfig, {
      $schema: 'https://json.schemastore.org/tsconfig',
      extends: '../../tsconfig.base.json',
      compilerOptions: {
        allowImportingTsExtensions: true,
        erasableSyntaxOnly: true,
        lib: ['ES2024'],
        types: [],
      },
      include: ['src/**/*.ts'],
      exclude: ['node_modules', 'dist', 'build', 'coverage', '**/*.test.ts'],
    });
  });

  it('routes the repository typecheck through the web-ui owner package', () => {
    const packageJson = readJson('package.json');
    const scripts = packageJson.scripts as Record<string, unknown>;
    assert.equal(typeof scripts.typecheck, 'string');
    assert.match(scripts.typecheck as string, /tsc --noEmit --project packages\/web-ui\/tsconfig\.json/);
  });

  it('resolves the declared package export without registering a route or effect', async () => {
    const module = await import('@raos/web-ui');
    assert.deepEqual(module.ADMIN_ROUTE_REGISTRY, [
      {
        screenId: 'ADM-001',
        path: '/admin',
        allowedRoles: module.ADMIN_ROLES,
        siteScopeRequired: true,
        securityAuthority: 'server',
        availability: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED',
      },
    ]);
    assert.equal(module.evaluateAdminRouteContext, module.evaluateAdminRouteContext);
  });
});
