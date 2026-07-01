import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import type { Concept } from "@/lib/types"
import ConceptsPage from "./page"

vi.mock("@/lib/api", () => ({
  listConcepts: vi.fn(),
}))

import { listConcepts } from "@/lib/api"
const mockListConcepts = vi.mocked(listConcepts)

const MOCK_CONCEPTS: Concept[] = [
  {
    id: "1",
    conceptName: "Distributed Systems",
    conceptType: "idea",
    description: null,
    status: "active",
    createdAt: "2024-01-01T00:00:00Z",
    claimCount: 5,
  },
  {
    id: "2",
    conceptName: "Ada Lovelace",
    conceptType: "person",
    description: null,
    status: "active",
    createdAt: "2024-01-02T00:00:00Z",
    claimCount: 2,
  },
]

function renderConcepts() {
  return render(<ConceptsPage />)
}

describe("ConceptsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("renders all concepts with type badge and claim count after load", async () => {
    mockListConcepts.mockResolvedValueOnce(MOCK_CONCEPTS)
    renderConcepts()

    await waitFor(() => {
      expect(screen.getByText("Distributed Systems")).toBeInTheDocument()
      expect(screen.getByText("Ada Lovelace")).toBeInTheDocument()
    })

    expect(screen.getAllByText("idea").length).toBeGreaterThan(0)
    expect(screen.getAllByText("person").length).toBeGreaterThan(0)
    expect(screen.getByText("5")).toBeInTheDocument()
    expect(screen.getAllByText("2").length).toBeGreaterThan(0)
  })

  it("filters to only person rows when the Person pill is clicked", async () => {
    mockListConcepts.mockResolvedValueOnce(MOCK_CONCEPTS)
    renderConcepts()

    await waitFor(() => {
      expect(screen.getByText("Distributed Systems")).toBeInTheDocument()
    })

    await userEvent.click(screen.getByRole("button", { name: "person" }))

    expect(screen.queryByText("Distributed Systems")).not.toBeInTheDocument()
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument()
  })

  it("shows inline error when listConcepts throws", async () => {
    mockListConcepts.mockRejectedValueOnce(new Error("network error"))
    renderConcepts()

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument()
    })
  })

  it("shows count badge after load", async () => {
    mockListConcepts.mockResolvedValueOnce(MOCK_CONCEPTS)
    renderConcepts()

    await waitFor(() => {
      expect(screen.getAllByText("2").length).toBeGreaterThan(0)
    })
  })

  it("shows page title Concepts", () => {
    mockListConcepts.mockImplementation(() => new Promise(() => {}))
    renderConcepts()
    expect(screen.getByText("Concepts")).toBeInTheDocument()
  })

  it("shows empty state when no concepts match the filter", async () => {
    mockListConcepts.mockResolvedValueOnce([])
    renderConcepts()

    await waitFor(() => {
      expect(screen.getByText("No concepts match this filter.")).toBeInTheDocument()
    })
  })
})
