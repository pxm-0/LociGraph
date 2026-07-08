import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import { ThemeProvider } from "@/lib/theme"
import type { Contradiction } from "@/lib/types"
import ContradictionsPage from "./page"

vi.mock("@/lib/api", () => ({
  listContradictions: vi.fn(),
  getContradictionsCount: vi.fn().mockResolvedValue(0),
  classifyContradiction: vi.fn(),
}))

import { classifyContradiction, getContradictionsCount, listContradictions } from "@/lib/api"
const mockListContradictions = vi.mocked(listContradictions)
const mockGetContradictionsCount = vi.mocked(getContradictionsCount)
const mockClassifyContradiction = vi.mocked(classifyContradiction)

function makeContradiction(overrides: Partial<Contradiction> = {}): Contradiction {
  return {
    id: "c1",
    conceptId: "concept-1",
    claimA: {
      id: "claim-a",
      sourceId: "src-1",
      observationId: "obs-1",
      claimText: "It rained.",
      claimType: "fact",
      assertionType: "reality",
      confidence: 0.9,
      extractionMethod: "llm",
      modelName: null,
      promptVersion: null,
      status: "proposed",
      createdAt: "2024-05-12T14:32:01Z",
    },
    claimB: {
      id: "claim-b",
      sourceId: "src-1",
      observationId: "obs-2",
      claimText: "It was sunny.",
      claimType: "fact",
      assertionType: "reality",
      confidence: 0.9,
      extractionMethod: "llm",
      modelName: null,
      promptVersion: null,
      status: "proposed",
      createdAt: "2024-05-12T14:32:01Z",
    },
    similarity: 0.82,
    classification: "unresolved",
    rationale: "Both claims describe the same day's weather but disagree.",
    createdAt: "2024-05-12T14:32:01Z",
    classifiedAt: null,
    ...overrides,
  }
}

function renderPage() {
  return render(
    <ThemeProvider>
      <ContradictionsPage />
    </ThemeProvider>,
  )
}

describe("ContradictionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetContradictionsCount.mockResolvedValue(0)
  })

  it("loads and shows both claims side by side with the rationale", async () => {
    mockListContradictions.mockResolvedValueOnce([makeContradiction()])
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("It rained.")).toBeInTheDocument()
      expect(screen.getByText("It was sunny.")).toBeInTheDocument()
      expect(screen.getByText(/disagree/)).toBeInTheDocument()
    })
  })

  it("filters by classification", async () => {
    const unresolved = makeContradiction({ id: "c1", classification: "unresolved" })
    const resolved = makeContradiction({
      id: "c2",
      classification: "evolution",
      claimA: { ...unresolved.claimA, claimText: "resolved claim a" },
      claimB: { ...unresolved.claimB, claimText: "resolved claim b" },
    })
    mockListContradictions.mockResolvedValueOnce([unresolved, resolved])
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("It rained.")).toBeInTheDocument()
      expect(screen.getByText("resolved claim a")).toBeInTheDocument()
    })

    const filterGroup = screen.getByRole("group", { name: "Filter by classification" })
    await userEvent.click(within(filterGroup).getByRole("button", { name: "evolution" }))

    expect(screen.queryByText("It rained.")).not.toBeInTheDocument()
    expect(screen.getByText("resolved claim a")).toBeInTheDocument()
  })

  it("classifies an unresolved contradiction and updates it in place", async () => {
    mockListContradictions.mockResolvedValueOnce([makeContradiction()])
    mockClassifyContradiction.mockResolvedValueOnce(
      makeContradiction({ classification: "true_conflict", classifiedAt: "2024-05-12T15:00:00Z" })
    )
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("It rained.")).toBeInTheDocument()
    })

    const row = screen.getByRole("article")
    await userEvent.click(within(row).getByRole("button", { name: "true_conflict" }))

    await waitFor(() => {
      expect(mockClassifyContradiction).toHaveBeenCalledWith("c1", "true_conflict")
    })
  })

  it("hides classify actions once a contradiction is already resolved", async () => {
    mockListContradictions.mockResolvedValueOnce([makeContradiction({ classification: "both" })])
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("It rained.")).toBeInTheDocument()
    })

    const row = screen.getByRole("article")
    expect(within(row).queryByRole("button", { name: "true_conflict" })).not.toBeInTheDocument()
  })
})
