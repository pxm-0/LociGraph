import { render, screen } from "@testing-library/react"
import { expect, test, vi } from "vitest"
import { ThemeProvider } from "@/lib/theme"
import { AppChrome } from "./AppChrome"

vi.mock("next/navigation", () => ({ usePathname: () => mockPathname }))
let mockPathname = "/dashboard"

function renderChrome() {
  return render(
    <ThemeProvider>
      <AppChrome>
        <div data-testid="page-content">content</div>
      </AppChrome>
    </ThemeProvider>
  )
}

test("pads the main content area on a normal route", () => {
  mockPathname = "/dashboard"
  renderChrome()
  const main = screen.getByTestId("page-content").closest("main")
  expect(main?.className).toMatch(/p-8/)
})

test("skips padding on the Planetarium route", () => {
  mockPathname = "/planetarium"
  renderChrome()
  const main = screen.getByTestId("page-content").closest("main")
  expect(main?.className).not.toMatch(/p-8/)
  expect(main?.className).not.toMatch(/p-3/)
})
