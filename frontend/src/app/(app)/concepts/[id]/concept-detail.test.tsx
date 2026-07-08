import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import { ThemeProvider } from "@/lib/theme"
import type { Claim, Concept, Revision } from "@/lib/types"
import ConceptDetailPage from "./page"

vi.mock("@/lib/api", () => ({
  getConcept: vi.fn(),
  getConceptClaims: vi.fn().mockResolvedValue([]),
  getConceptRevisions: vi.fn().mockResolvedValue([]),
  createConceptRevision: vi.fn(),
}))

import {
  createConceptRevision,
  getConcept,
  getConceptClaims,
  getConceptRevisions,
} from "@/lib/api"
const mockGetConcept = vi.mocked(getConcept)
const mockGetConceptClaims = vi.mocked(getConceptClaims)
const mockGetConceptRevisions = vi.mocked(getConceptRevisions)
const mockCreateConceptRevision = vi.mocked(createConceptRevision)

function makeConcept(overrides: Partial<Concept> = {}): Concept {
  return {
    id: "concept-1",
    conceptName: "Careful Plans",
    conceptType: "idea",
    description: "Original description.",
    status: "active",
    createdAt: "2024-05-12T14:32:01Z",
    claimCount: 2,
    ...overrides,
  }
}

function makeClaim(overrides: Partial<Claim> = {}): Claim {
  return {
    id: "claim-1",
    sourceId: "src-1",
    observationId: "obs-1",
    claimText: "The user prefers small careful plans.",
    claimType: "preference",
    assertionType: "perception",
    confidence: 0.9,
    extractionMethod: "llm",
    modelName: null,
    promptVersion: null,
    status: "proposed",
    createdAt: "2024-05-12T14:32:01Z",
    ...overrides,
  }
}

function makeRevision(overrides: Partial<Revision> = {}): Revision {
  return {
    id: "rev-1",
    conceptId: "concept-1",
    contradictionId: null,
    source: "manual",
    previousDescription: "Older text.",
    newDescription: "Original description.",
    rationale: "Because I said so.",
    createdAt: "2024-05-10T00:00:00Z",
    ...overrides,
  }
}

function renderPage() {
  return render(
    <ThemeProvider>
      <ConceptDetailPage params={{ id: "concept-1" }} />
    </ThemeProvider>,
  )
}

describe("ConceptDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetConceptClaims.mockResolvedValue([])
    mockGetConceptRevisions.mockResolvedValue([])
  })

  it("shows the concept's name, description, claims, and revision history", async () => {
    mockGetConcept.mockResolvedValueOnce(makeConcept())
    mockGetConceptClaims.mockResolvedValueOnce([makeClaim()])
    mockGetConceptRevisions.mockResolvedValueOnce([makeRevision()])
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("Careful Plans")).toBeInTheDocument()
      // "Original description." intentionally appears twice: once as the concept's
      // current description, once as the latest revision's newDescription.
      expect(screen.getAllByText("Original description.").length).toBeGreaterThan(0)
      expect(screen.getByText("The user prefers small careful plans.")).toBeInTheDocument()
      expect(screen.getByText("Because I said so.")).toBeInTheDocument()
    })
  })

  it("submits a manual revision and shows it immediately", async () => {
    mockGetConcept.mockResolvedValueOnce(makeConcept())
    mockCreateConceptRevision.mockResolvedValueOnce(
      makeRevision({
        id: "rev-2",
        previousDescription: "Original description.",
        newDescription: "Rewritten by hand.",
        rationale: null,
      })
    )
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("Careful Plans")).toBeInTheDocument()
    })

    await userEvent.type(
      screen.getByLabelText("New description"),
      "Rewritten by hand."
    )
    await userEvent.click(screen.getByRole("button", { name: /save revision/i }))

    await waitFor(() => {
      expect(mockCreateConceptRevision).toHaveBeenCalledWith(
        "concept-1",
        "Rewritten by hand.",
        undefined
      )
      // Appears twice: the concept description mirrors the applied revision, plus
      // the new entry at the top of the revision history.
      expect(screen.getAllByText("Rewritten by hand.").length).toBeGreaterThan(0)
    })
  })

  it("shows a not-found message when the concept doesn't exist", async () => {
    mockGetConcept.mockResolvedValueOnce(null)
    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/concept not found/i)).toBeInTheDocument()
    })
  })

  it("shows an error message instead of an infinite skeleton when the initial load fails", async () => {
    mockGetConcept.mockRejectedValueOnce(new Error("network error"))
    renderPage()

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument()
    })
  })
})
