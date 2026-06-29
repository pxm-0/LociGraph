import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import { ThemeProvider } from "@/lib/theme"
import type { Observation } from "@/lib/types"
import ObservationsPage from "./page"

vi.mock("@/lib/api", () => ({
  listObservations: vi.fn(),
}))

import { listObservations } from "@/lib/api"
const mockListObservations = vi.mocked(listObservations)

const MOCK_OBSERVATIONS: Observation[] = [
  {
    id: "obs-1",
    content:
      "The data stream exhibits a rhythmic oscillation consistent with biological respiratory patterns, yet the origin signature remains localized within the silicon-substrate containment unit.",
    speaker: "Dr. Aris Thorne",
    observedAt: "2024-05-12T14:32:01Z",
    confidence: 0.984,
    sourceId: "src-abc123",
  },
  {
    id: "obs-2",
    content:
      "Signal degradation observed at the 14GHz frequency band. Correlation with the solar flare event of last Tuesday is high.",
    speaker: null,
    observedAt: "2024-05-12T12:05:44Z",
    confidence: 0.5,
    sourceId: null,
  },
]

function renderPage() {
  return render(
    <ThemeProvider>
      <ObservationsPage />
    </ThemeProvider>,
  )
}

describe("ObservationsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("renders both observation contents after load", async () => {
    mockListObservations.mockResolvedValueOnce(MOCK_OBSERVATIONS)
    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/rhythmic oscillation/i)).toBeInTheDocument()
      expect(screen.getByText(/Signal degradation/i)).toBeInTheDocument()
    })
  })

  it("shows confidence values in mono metadata row", async () => {
    mockListObservations.mockResolvedValueOnce(MOCK_OBSERVATIONS)
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("0.98")).toBeInTheDocument()
      expect(screen.getByText("0.50")).toBeInTheDocument()
    })
  })

  it("calls listObservations with speaker filter when submitted", async () => {
    mockListObservations.mockResolvedValue(MOCK_OBSERVATIONS)
    renderPage()

    // Wait for initial load to settle
    await waitFor(() => {
      expect(mockListObservations).toHaveBeenCalledTimes(1)
    })

    const speakerInput = screen.getByPlaceholderText(/speaker/i)
    await userEvent.clear(speakerInput)
    await userEvent.type(speakerInput, "x")

    const applyBtn = screen.getByRole("button", { name: /apply/i })
    await userEvent.click(applyBtn)

    await waitFor(() => {
      expect(mockListObservations).toHaveBeenCalledWith(
        expect.objectContaining({ speaker: "x" }),
      )
    })
  })

  it("shows inline error when listObservations throws", async () => {
    mockListObservations.mockRejectedValueOnce(new Error("network error"))
    renderPage()

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument()
    })
  })

  it("shows empty-state message when no observations returned", async () => {
    mockListObservations.mockResolvedValueOnce([])
    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/no observations/i)).toBeInTheDocument()
    })
  })
})
