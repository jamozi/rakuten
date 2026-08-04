import { defineConfig, globalIgnores } from 'eslint/config';
import nextCoreWebVitals from 'eslint-config-next/core-web-vitals';
import nextTypeScript from 'eslint-config-next/typescript';

export default defineConfig([
  ...nextCoreWebVitals,
  ...nextTypeScript,
  {
    files: ['**/*.{js,mjs,cjs,ts,tsx}'],
    linterOptions: {
      reportUnusedDisableDirectives: 'error',
    },
    rules: {
      // The web workspace is intentionally package-only in ST-0103. Routes are
      // introduced by their own Stories, so a pages-directory probe is noise.
      '@next/next/no-html-link-for-pages': 'off',
    },
  },
  globalIgnores([
    '.next/**',
    '.npm-cache/**',
    '.node-offline-check.*/**',
    'build/**',
    'changes/**',
    'coverage/**',
    'dist/**',
    'docs/**',
    'node_modules/**',
    'zip/**',
  ]),
]);
