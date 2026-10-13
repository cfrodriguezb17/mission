import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e',
  webServer: process.env['E2E_BASE_URL']
    ? undefined
    : {
        command: 'pnpm start --host 127.0.0.1',
        url: 'http://localhost:4200/login',
        reuseExistingServer: !process.env['CI'],
        timeout: 60000,
      },
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  use: {
    baseURL: process.env['E2E_BASE_URL'] ?? 'http://localhost:4200',
    viewport: { width: 1440, height: 1050 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  reporter: [['list'], ['html', { open: 'never' }]],
});
