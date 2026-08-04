import { defineConfig } from 'vitest/config';

export default defineConfig({
  cacheDir: '.npm-cache/vite',
  test: {
    environment: 'node',
    include: ['tests/st0103/**/*.test.ts'],
    passWithNoTests: false,
    clearMocks: true,
    mockReset: true,
    restoreMocks: true,
    unstubEnvs: true,
    unstubGlobals: true,
    testTimeout: 5_000,
    hookTimeout: 5_000,
  },
});
