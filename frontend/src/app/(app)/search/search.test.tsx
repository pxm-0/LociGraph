import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import type { SearchResult } from "@/lib/types"
import SearchPage from "./page"

vi.mock("@/lib/api", () => ({
  search: vi.fn(),
}))

import { search } from "@/lib/api"
const mockSearch = vi.mocked(search)

const MOCK_RESULTS: SearchResult[] = [
  {
    id: "c1",
    sourceId: "s1",
    observationId: "o1",
    claimText: "The user prefers dark mode.",
    claimType: "preference",
    confidence: 0.9,
    extractionMethod: "test",
    modelName: null,
    promptVersion: null,
    status: "proposed",
    createdAt: "2024-01-01T00:00:00Z",
    similarity: 0.92,
  },
]

function renderPage() {
  return render(<SearchPage />)
}

describe("SearchPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("shows page title Search", () => {
    renderPage()
    expect(screen.getByRole("heading", { name: "Search" })).toBeInTheDocument()
  })

  it("runs a search on submit and renders results with similarity", async () => {
    mockSearch.mockResolvedValueOnce(MOCK_RESULTS)
    renderPage()

    await userEvent.type(screen.getByLabelText("Search claims"), "dark mode")
    await userEvent.click(screen.getByRole("button", { name: /search/i }))

    await waitFor(() => {
      expect(screen.getByText("The user prefers dark mode.")).toBeInTheDocument()
      expect(screen.getByText("92% match")).toBeInTheDocument()
    })
    expect(mockSearch).toHaveBeenCalledWith("dark mode")
  })

  it("shows empty state when no results match", async () => {
    mockSearch.mockResolvedValueOnce([])
    renderPage()

    await userEvent.type(screen.getByLabelText("Search claims"), "nothing")
    await userEvent.click(screen.getByRole("button", { name: /search/i }))

    await waitFor(() => {
      expect(screen.getByText("No matching claims found.")).toBeInTheDocument()
    })
  })

  it("shows inline error when search throws", async () => {
    mockSearch.mockRejectedValueOnce(new Error("search failed"))
    renderPage()

    await userEvent.type(screen.getByLabelText("Search claims"), "x")
    await userEvent.click(screen.getByRole("button", { name: /search/i }))

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument()
    })
  })
})
