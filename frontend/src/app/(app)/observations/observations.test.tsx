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

function makeObservations(count: number, offset = 0): Observation[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `obs-${offset + i}`,
    content: `obs ${offset + i}`,
    speaker: null,
    observedAt: "2024-05-12T14:32:01Z",
    confidence: 0.9,
    sourceId: null,
  }))
}

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

  it("loads the first page with limit/offset and no filters", async () => {
    mockListObservations.mockResolvedValueOnce(MOCK_OBSERVATIONS)
    renderPage()

    await waitFor(() => {
      expect(mockListObservations).toHaveBeenCalledWith({ limit: 100, offset: 0 })
    })
  })

  it("shows Load more for a full page and appends next page with same filters", async () => {
    const fullPage = makeObservations(100)
    mockListObservations.mockResolvedValueOnce(fullPage)
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("obs 0")).toBeInTheDocument()
    })

    const speakerInput = screen.getByPlaceholderText(/speaker/i)
    await userEvent.type(speakerInput, "x")
    mockListObservations.mockResolvedValueOnce(fullPage)
    await userEvent.click(screen.getByRole("button", { name: /apply/i }))

    await waitFor(() => {
      expect(mockListObservations).toHaveBeenLastCalledWith({
        speaker: "x",
        limit: 100,
        offset: 0,
      })
    })

    const loadMoreBtn = screen.getByRole("button", { name: /load more/i })
    mockListObservations.mockResolvedValueOnce(makeObservations(50, 100))
    await userEvent.click(loadMoreBtn)

    await waitFor(() => {
      expect(mockListObservations).toHaveBeenLastCalledWith({
        speaker: "x",
        limit: 100,
        offset: 100,
      })
      expect(screen.getByText("obs 0")).toBeInTheDocument()
      expect(screen.getByText("obs 100")).toBeInTheDocument()
    })
  })

  it("does not show Load more for a short page", async () => {
    mockListObservations.mockResolvedValueOnce(makeObservations(10))
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("obs 0")).toBeInTheDocument()
    })

    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument()
  })

  it("resets to a fresh single page when a new filter is applied", async () => {
    mockListObservations.mockResolvedValueOnce(makeObservations(100))
    renderPage()

    const loadMoreBtn = await screen.findByRole("button", { name: /load more/i })
    mockListObservations.mockResolvedValueOnce(makeObservations(50, 100))
    await userEvent.click(loadMoreBtn)

    await waitFor(() => {
      expect(screen.getByText("obs 100")).toBeInTheDocument()
    })

    const speakerInput = screen.getByPlaceholderText(/speaker/i)
    await userEvent.type(speakerInput, "y")
    mockListObservations.mockResolvedValueOnce(makeObservations(5))
    await userEvent.click(screen.getByRole("button", { name: /apply/i }))

    await waitFor(() => {
      expect(mockListObservations).toHaveBeenLastCalledWith({
        speaker: "y",
        limit: 100,
        offset: 0,
      })
      expect(screen.queryByText("obs 100")).not.toBeInTheDocument()
    })
  })
})
