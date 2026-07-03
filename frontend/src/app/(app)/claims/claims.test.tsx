import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import { ThemeProvider } from "@/lib/theme"
import type { Claim } from "@/lib/types"
import ClaimsPage from "./page"

vi.mock("@/lib/api", () => ({
  listClaims: vi.fn(),
  listConceptCandidates: vi.fn().mockResolvedValue([]),
}))

import { listClaims } from "@/lib/api"
const mockListClaims = vi.mocked(listClaims)

function makeClaims(count: number, offset = 0): Claim[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `c${offset + i}`,
    sourceId: "src-1",
    observationId: "obs-1",
    claimText: `claim ${offset + i}`,
    claimType: "fact",
    confidence: 0.9,
    extractionMethod: "llm",
    modelName: null,
    promptVersion: null,
    status: "proposed",
    createdAt: "2024-05-12T14:32:01Z",
  }))
}

function renderPage() {
  return render(
    <ThemeProvider>
      <ClaimsPage />
    </ThemeProvider>,
  )
}

describe("ClaimsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("loads the first page with limit/offset and shows claim text", async () => {
    mockListClaims.mockResolvedValueOnce(makeClaims(2))
    renderPage()

    await waitFor(() => {
      expect(mockListClaims).toHaveBeenCalledTimes(1)
      expect(mockListClaims).toHaveBeenCalledWith({ limit: 100, offset: 0 })
      expect(screen.getByText("claim 0")).toBeInTheDocument()
    })
  })

  it("shows Load more when a full page is returned, and appends the next page on click", async () => {
    mockListClaims.mockResolvedValueOnce(makeClaims(100))
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("claim 0")).toBeInTheDocument()
    })

    const loadMoreBtn = screen.getByRole("button", { name: /load more/i })
    mockListClaims.mockResolvedValueOnce(makeClaims(50, 100))
    await userEvent.click(loadMoreBtn)

    await waitFor(() => {
      expect(mockListClaims).toHaveBeenCalledWith({ limit: 100, offset: 100 })
      expect(screen.getByText("claim 0")).toBeInTheDocument()
      expect(screen.getByText("claim 100")).toBeInTheDocument()
    })
  })

  it("does not show Load more when the first page is short", async () => {
    mockListClaims.mockResolvedValueOnce(makeClaims(10))
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("claim 0")).toBeInTheDocument()
    })

    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument()
  })

  it("hides Load more after a short subsequent page is loaded", async () => {
    mockListClaims.mockResolvedValueOnce(makeClaims(100))
    renderPage()

    const loadMoreBtn = await screen.findByRole("button", { name: /load more/i })
    mockListClaims.mockResolvedValueOnce(makeClaims(10, 100))
    await userEvent.click(loadMoreBtn)

    await waitFor(() => {
      expect(screen.getByText("claim 100")).toBeInTheDocument()
      expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument()
    })
  })

  it("shows inline error when loadMore fetch fails", async () => {
    mockListClaims.mockResolvedValueOnce(makeClaims(100))
    renderPage()

    const loadMoreBtn = await screen.findByRole("button", { name: /load more/i })
    mockListClaims.mockRejectedValueOnce(new Error("network error"))
    await userEvent.click(loadMoreBtn)

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument()
    })
  })
})
