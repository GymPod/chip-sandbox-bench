import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  reporter: [["list"]],
  timeout: 30_000,
  use: {},
  workers: process.env.CI ? 2 : undefined
});
