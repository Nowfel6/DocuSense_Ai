import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "foundation-shell.spec.ts",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev:e2e:foundation",
    url: "http://127.0.0.1:3100/foundation-preview",
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    { name: "narrow-390", use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } } },
    { name: "medium-768", use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 900 } } },
    { name: "laptop-1366", use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 768 } } },
    { name: "wide-1440", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "ultrawide-1920", use: { ...devices["Desktop Chrome"], viewport: { width: 1920, height: 1080 } } },
  ],
});
