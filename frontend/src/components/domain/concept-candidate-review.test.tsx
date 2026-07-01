import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import type { Concept, ConceptCandidate } from "@/lib/types"
import { ConceptCandidateReview } from "./ConceptCandidateReview"

vi.mock("@/lib/api", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api")>()
  return {
    ...actual,
    listConceptCandidates: vi.fn(),
    approveConceptCandidate: vi.fn(),
    rejectConceptCandidate: vi.fn(),
  }
})

import {
  ApiError,
  approveConceptCandidate,
  listConceptCandidates,
  rejectConceptCandidate,
} from "@/lib/api"

const mockList = vi.mocked(listConceptCandidates)
const mockApprove = vi.mocked(approveConceptCandidate)
const mockReject = vi.mocked(rejectConceptCandidate)

const CANDIDATE: ConceptCandidate = {
  id: "cand-1",
  sourceId: "src-1",
  claimId: "claim-1",
  candidateName: "Distributed Systems",
  conceptType: "idea",
  rationale: "Mentioned across multiple claims",
  confidence: 0.9,
  status: "proposed",
  createdAt: "2024-01-01T00:00:00Z",
}

const CONCEPT: Concept = {
  id: "concept-1",
  conceptName: "Distributed Systems",
  conceptType: "idea",
  description: null,
  status: "active",
  createdAt: "2024-01-01T00:00:00Z",
  claimCount: 1,
}

describe("ConceptCandidateReview", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("renders proposed candidates with name and type", async () => {
    mockList.mockResolvedValueOnce([CANDIDATE])
    render(<ConceptCandidateReview />)

    await waitFor(() => {
      expect(screen.getByText("Distributed Systems")).toBeInTheDocument()
      expect(screen.getByText("idea")).toBeInTheDocument()
    })
    expect(mockList).toHaveBeenCalledWith({ status: "proposed" })
  })

  it("approves a candidate and refreshes the list", async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValueOnce([CANDIDATE])
    mockApprove.mockResolvedValueOnce(CONCEPT)
    mockList.mockResolvedValueOnce([])

    render(<ConceptCandidateReview />)

    await waitFor(() => {
      expect(screen.getByText("Distributed Systems")).toBeInTheDocument()
    })

    await user.click(screen.getByRole("button", { name: /approve/i }))

    await waitFor(() => {
      expect(mockApprove).toHaveBeenCalledWith("cand-1")
    })

    await waitFor(() => {
      expect(screen.getByText("No concept candidates awaiting review.")).toBeInTheDocument()
    })
  })

  it("rejects a candidate and refreshes the list", async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValueOnce([CANDIDATE])
    mockReject.mockResolvedValueOnce({ ...CANDIDATE, status: "rejected" })
    mockList.mockResolvedValueOnce([])

    render(<ConceptCandidateReview />)

    await waitFor(() => {
      expect(screen.getByText("Distributed Systems")).toBeInTheDocument()
    })

    await user.click(screen.getByRole("button", { name: /reject/i }))

    await waitFor(() => {
      expect(mockReject).toHaveBeenCalledWith("cand-1")
    })

    await waitFor(() => {
      expect(screen.getByText("No concept candidates awaiting review.")).toBeInTheDocument()
    })
  })

  it("shows an inline error when approve rejects with 409", async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValueOnce([CANDIDATE])
    mockApprove.mockRejectedValueOnce(new ApiError(409, "concept candidate has status 'approved'"))

    render(<ConceptCandidateReview />)

    await waitFor(() => {
      expect(screen.getByText("Distributed Systems")).toBeInTheDocument()
    })

    await user.click(screen.getByRole("button", { name: /approve/i }))

    await waitFor(() => {
      const alert = screen.getByRole("alert")
      expect(alert).toBeInTheDocument()
      expect(alert.textContent?.toLowerCase()).toContain("approved")
    })
  })

  it("shows an inline error when reject rejects with 404", async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValueOnce([CANDIDATE])
    mockReject.mockRejectedValueOnce(new ApiError(404, "not found"))

    render(<ConceptCandidateReview />)

    await waitFor(() => {
      expect(screen.getByText("Distributed Systems")).toBeInTheDocument()
    })

    await user.click(screen.getByRole("button", { name: /reject/i }))

    await waitFor(() => {
      const alert = screen.getByRole("alert")
      expect(alert).toBeInTheDocument()
      expect(alert.textContent?.toLowerCase()).toContain("not found")
    })
  })

  it("shows empty state when there are no proposed candidates", async () => {
    mockList.mockResolvedValueOnce([])
    render(<ConceptCandidateReview />)

    await waitFor(() => {
      expect(screen.getByText("No concept candidates awaiting review.")).toBeInTheDocument()
    })
  })
})
