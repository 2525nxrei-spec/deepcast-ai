import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['tests/**/*.test.js'],
    testTimeout: 30000,
    coverage: {
      provider: 'v8',
      include: ['functions/**/*.js'],
      exclude: ['functions/**/node_modules/**'],
      reporter: ['text', 'text-summary'],
    },
  },
});
