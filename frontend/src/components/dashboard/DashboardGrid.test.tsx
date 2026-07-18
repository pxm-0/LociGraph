import { render, screen } from "@testing-library/react"
import { describe, expect, test, vi } from "vitest"

// The mini-planetarium pulls in R3F + useMode; stub the dynamic import so the
// grid test only exercises the layout/wiring.
vi.mock("next/dynamic", () => ({
  default: () => () => <div data-testid="mini-planetarium" />,
}))

import { DashboardGrid } from "./DashboardGrid"
import type { DashboardData } from "@/lib/dashboard"
import type { DashboardSummary } from "@/lib/types"

const summary: DashboardSummary = {
  sourceCount: 12,
  observationCount: 340,
  claimCount: 88,
  conceptCount: 25,
  pendingJobCount: 0,
  recentSources: [],
}

const data: DashboardData = {
  summary,
  trends: {
    window_days: 30,
    series: {
      sources: [{ date: "2026-07-01", count: 2 }, { date: "2026-07-02", count: 3 }],
      claims: [{ date: "2026-07-01", count: 5 }],
      concepts: [],
      contradictions: [],
    },
  },
  needsAttention: { contradictions: 1, jobs: 0, candidates: 2 },
  activity: [{ kind: "source", label: "notes.md", at: "2026-07-02", href: "/sources/1" }],
}

describe("DashboardGrid", () => {
  test("renders tiles, needs-attention, and activity", () => {
    render(<DashboardGrid data={data} />)
    expect(screen.getByText("12")).toBeInTheDocument() // sources
    expect(screen.getByText("Concepts")).toBeInTheDocument()
    expect(screen.getByText("Open contradictions")).toBeInTheDocument()
    expect(screen.getByText("notes.md")).toBeInTheDocument()
    expect(screen.getByText(/Ask the Custodian/i)).toBeInTheDocument()
  })
})
