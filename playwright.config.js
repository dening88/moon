// @ts-check
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 30000,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.QIWI_BASE_URL || 'https://edge.qiwi.com',
    extraHTTPHeaders: {
      Accept: 'application/json',
      'Content-Type': 'application/json'
    }
  }
});
