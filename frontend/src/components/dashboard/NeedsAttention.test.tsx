import { render, screen } from "@testing-library/react"
import { describe, expect, test } from "vitest"
import { NeedsAttention } from "./NeedsAttention"

describe("NeedsAttention", () => {
  test("renders counts and correct hrefs when nonzero", () => {
    render(<NeedsAttention items={{ contradictions: 3, jobs: 1, candidates: 5 }} />)
    expect(screen.getByText("3")).toBeInTheDocument()
    expect(screen.getByText("Open contradictions").closest("a")).toHaveAttribute("href", "/contradictions")
    expect(screen.getByText("Jobs need attention").closest("a")).toHaveAttribute("href", "/jobs")
    expect(screen.getByText("Unreviewed candidates").closest("a")).toHaveAttribute("href", "/concept-candidates")
  })

  test("renders an all-clear state when all zero", () => {
    render(<NeedsAttention items={{ contradictions: 0, jobs: 0, candidates: 0 }} />)
    expect(screen.getByText(/All clear/i)).toBeInTheDocument()
  })
})
