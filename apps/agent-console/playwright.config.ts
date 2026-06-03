import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.HARNESS_PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5177";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: process.env.HARNESS_PLAYWRIGHT_EXTERNAL_SERVER
    ? undefined
    : {
        command: "npm run dev -- --port 5177",
        url: "http://127.0.0.1:5177",
        reuseExistingServer: !process.env.CI,
        timeout: 60_000,
      },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
      },
    },
  ],
});
