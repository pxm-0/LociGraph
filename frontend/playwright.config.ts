import { defineConfig } from "@playwright/test"

export default defineConfig({
  testDir: "./src/test/e2e",
  use: { baseURL: process.env.E2E_BASE_URL || "http://localhost:3000" },
  timeout: 30_000,
})
