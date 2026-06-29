/**
 * Smoke e2e: login → import → sources
 *
 * Prerequisites:
 *   - Backend + DB running with a seeded user:
 *       docker compose up -d postgres redis backend
 *       docker compose exec backend python -m backend.app.scripts.init_user
 *   - Next.js dev server running:
 *       BACKEND_ORIGIN=http://localhost:8000 npm run dev
 *
 * Run:
 *   E2E_RUN=1 LOCIGRAPH_PASSWORD=<password> npm run test:e2e
 *
 * The test is skipped automatically in CI / local unless E2E_RUN or E2E_BASE_URL is set.
 */

import { expect, test } from "@playwright/test"

const PASSWORD = process.env.LOCIGRAPH_PASSWORD || "test-password-123"

test.skip(
  !process.env.E2E_RUN && !process.env.E2E_BASE_URL,
  "Set E2E_RUN=1 (or E2E_BASE_URL) and LOCIGRAPH_PASSWORD to run this test against a live stack",
)

test("login, import a JSON source, see it in Sources", async ({ page }) => {
  await page.goto("/login")
  await page.getByLabel(/password/i).fill(PASSWORD)
  await page.getByRole("button", { name: /enter archive/i }).click()
  await expect(page).toHaveURL(/\/dashboard/)

  await page.goto("/import")
  await page.getByLabel(/source type/i).selectOption("json")
  await page.setInputFiles('input[type="file"]', {
    name: "e2e.json",
    mimeType: "application/json",
    buffer: Buffer.from('[{"text":"hello e2e"}]'),
  })
  await page.getByRole("button", { name: /upload|browse|import/i }).first().click()
  await expect(page.getByText(/PENDING|pending/)).toBeVisible()

  await page.goto("/sources")
  await expect(page.getByText("e2e.json")).toBeVisible()
})
