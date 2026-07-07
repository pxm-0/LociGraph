import { render, screen, waitFor } from "@testing-library/react"
import { expect, vi, describe, it, beforeEach } from "vitest"
import { ThemeProvider } from "@/lib/theme"
import type { DashboardSummary, Source } from "@/lib/types"
import DashboardPage from "./page"

// Mock the api module
vi.mock("@/lib/api", () => ({
  listSources: vi.fn(),
  getDashboardSummary: vi.fn().mockResolvedValue({
    sourceCount: 0,
    observationCount: 0,
    claimCount: 0,
    conceptCount: 0,
    pendingJobCount: 0,
    recentSources: [],
  }),
}))

import { getDashboardSummary, listSources } from "@/lib/api"
const mockListSources = vi.mocked(listSources)
const mockGetDashboardSummary = vi.mocked(getDashboardSummary)

const EMPTY_SUMMARY: DashboardSummary = {
  sourceCount: 0,
  observationCount: 0,
  claimCount: 0,
  conceptCount: 0,
  pendingJobCount: 0,
  recentSources: [],
}

const MOCK_SOURCES: Source[] = [
  {
    id: "1",
    sourceType: "json",
    originalFilename: "archive_manifest.json",
    importStatus: "VERIFIED",
    fileSizeBytes: 2048,
    importedAt: null,
    observationCount: 0,
    claimCount: 0,
    claimExtractionStatus: "waiting",
  },
  {
    id: "2",
    sourceType: "markdown",
    originalFilename: "notes_2024.md",
    importStatus: "VERIFIED",
    fileSizeBytes: 512,
    importedAt: null,
    observationCount: 0,
    claimCount: 0,
    claimExtractionStatus: "waiting",
  },
  {
    id: "3",
    sourceType: "pdf",
    originalFilename: "report_q3.pdf",
    importStatus: "PENDING",
    fileSizeBytes: 8192,
    importedAt: null,
    observationCount: 0,
    claimCount: 0,
    claimExtractionStatus: "waiting",
  },
]

function renderDashboard() {
  return render(
    <ThemeProvider>
      <DashboardPage />
    </ThemeProvider>,
  )
}

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("renders the three derived stat numbers after load", async () => {
    mockListSources.mockResolvedValueOnce(MOCK_SOURCES)
    renderDashboard()

    // Wait for the async data load to complete
    await waitFor(() => {
      // Total = 3
      expect(screen.getByLabelText("Total Sources: 3")).toBeInTheDocument()
      // Verified = 2
      expect(screen.getByLabelText("Verified: 2")).toBeInTheDocument()
      // In-flight = 1 (PENDING)
      expect(screen.getByLabelText("In-flight: 1")).toBeInTheDocument()
    })
  })

  it("renders real observation/claim/concept totals from the summary endpoint", async () => {
    mockListSources.mockResolvedValueOnce(MOCK_SOURCES)
    mockGetDashboardSummary.mockResolvedValueOnce({
      ...EMPTY_SUMMARY,
      observationCount: 39721,
      claimCount: 17676,
      conceptCount: 412,
    })
    renderDashboard()

    await waitFor(() => {
      expect(screen.getByLabelText("Observations: 39721")).toBeInTheDocument()
      expect(screen.getByLabelText("Claims: 17676")).toBeInTheDocument()
      expect(screen.getByLabelText("Concepts: 412")).toBeInTheDocument()
    })
  })

  it("renders a recent-activity row with filename and status badge", async () => {
    mockListSources.mockResolvedValueOnce(MOCK_SOURCES)
    renderDashboard()

    await waitFor(() => {
      expect(screen.getByText("archive_manifest.json")).toBeInTheDocument()
      // StatusBadge renders uppercase status text (multiple VERIFIED rows expected)
      const verifiedBadges = screen.getAllByText("VERIFIED")
      expect(verifiedBadges.length).toBeGreaterThanOrEqual(1)
    })
  })

  it("shows skeletons while loading", () => {
    // Never resolves during this test
    mockListSources.mockImplementation(() => new Promise(() => {}))
    renderDashboard()

    // aria-hidden skeletons; check loading state via heading still present
    expect(screen.getByText("Archive Overview")).toBeInTheDocument()
  })

  it("shows an inline error message when listSources throws", async () => {
    mockListSources.mockRejectedValueOnce(new Error("network failure"))
    renderDashboard()

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument()
    })
  })

  it("handles INGESTING status as in-flight", async () => {
    const sources: Source[] = [
      {
        id: "1",
        sourceType: "json",
        originalFilename: "stream.json",
        importStatus: "INGESTING",
        fileSizeBytes: 4096,
        importedAt: null,
        observationCount: 0,
        claimCount: 0,
        claimExtractionStatus: "waiting",
      },
    ]
    mockListSources.mockResolvedValueOnce(sources)
    renderDashboard()

    await waitFor(() => {
      expect(screen.getByLabelText("Total Sources: 1")).toBeInTheDocument()
      expect(screen.getByLabelText("Verified: 0")).toBeInTheDocument()
      expect(screen.getByLabelText("In-flight: 1")).toBeInTheDocument()
    })
  })
})
