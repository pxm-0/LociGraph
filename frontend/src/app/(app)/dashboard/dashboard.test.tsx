import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { DashboardData } from "@/lib/dashboard"

// Stub the R3F mini-planetarium (dynamic import) and the aggregator.
vi.mock("next/dynamic", () => ({
  default: () => () => <div data-testid="mini-planetarium" />,
}))
vi.mock("@/lib/dashboard", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/dashboard")>()
  return { ...actual, loadDashboard: vi.fn() }
})

import DashboardPage from "./page"
import { loadDashboard } from "@/lib/dashboard"

const mockLoad = vi.mocked(loadDashboard)

const DATA: DashboardData = {
  summary: {
    sourceCount: 7,
    observationCount: 100,
    claimCount: 42,
    conceptCount: 9,
    pendingJobCount: 0,
    recentSources: [],
  },
  trends: {
    window_days: 30,
    series: { sources: [], claims: [], concepts: [], contradictions: [] },
  },
  needsAttention: { contradictions: 0, jobs: 0, candidates: 0 },
  activity: [],
}

describe("DashboardPage", () => {
  beforeEach(() => vi.clearAllMocks())

  it("renders the grid overview after load", async () => {
    mockLoad.mockResolvedValueOnce(DATA)
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText("Archive Overview")).toBeInTheDocument()
      expect(screen.getByText("7")).toBeInTheDocument() // source count
      expect(screen.getByText(/All clear/i)).toBeInTheDocument()
    })
  })

  it("shows skeletons while loading", () => {
    mockLoad.mockImplementation(() => new Promise(() => {}))
    const { container } = render(<DashboardPage />)
    expect(container.querySelector('[class*="animate"]') ?? container.firstChild).toBeTruthy()
    expect(screen.queryByText("Archive Overview")).not.toBeInTheDocument()
  })

  it("shows an inline error when the load fails", async () => {
    mockLoad.mockRejectedValueOnce(new Error("network failure"))
    render(<DashboardPage />)
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument())
  })
})
