import { render, screen, waitFor } from "@testing-library/react"
import { expect, vi, describe, it, beforeEach, afterEach } from "vitest"
import type { Job, Source } from "@/lib/types"
import JobsGraphPage from "./page"

vi.mock("@/lib/api", () => ({
  listSources: vi.fn(),
  listJobs: vi.fn().mockResolvedValue([]),
}))

import { listJobs, listSources } from "@/lib/api"
const mockListSources = vi.mocked(listSources)
const mockListJobs = vi.mocked(listJobs)

const SOURCE: Source = {
  id: "s1",
  sourceType: "json",
  originalFilename: "archive_manifest.json",
  importStatus: "VERIFIED",
  fileSizeBytes: 2048,
  importedAt: null,
  observationCount: 100,
  claimCount: 10,
  claimExtractionStatus: "proposed",
}

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    jobType: "extract_claims",
    status: "running",
    attempts: 0,
    error: null,
    createdAt: "2024-01-01T00:00:00Z",
    startedAt: null,
    completedAt: null,
    itemsCompleted: 3,
    itemsTotal: 10,
    sourceId: "s1",
    ...overrides,
  }
}

function renderPage() {
  return render(<JobsGraphPage />)
}

describe("JobsGraphPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockListJobs.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("shows page title Jobs", async () => {
    mockListSources.mockResolvedValue([])
    renderPage()
    expect(screen.getByText("Jobs")).toBeInTheDocument()
  })

  it("shows the empty state when there are no active or recent jobs", async () => {
    mockListSources.mockResolvedValue([])
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("No active or recent jobs.")).toBeInTheDocument()
    })
  })

  it("renders one satellite node per job, colored by status, grouped under their source", async () => {
    mockListSources.mockResolvedValue([SOURCE])
    mockListJobs.mockImplementation(({ status } = {}) => {
      if (status === "running") return Promise.resolve([makeJob({ id: "j1", status: "running" })])
      if (status === "failed") {
        return Promise.resolve([makeJob({ id: "j2", status: "failed", error: "boom" })])
      }
      return Promise.resolve([])
    })
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("archive_manifest.json")).toBeInTheDocument()
    })

    const nodes = screen.getAllByTestId("job-node")
    expect(nodes).toHaveLength(2)
    expect(nodes.map((n) => n.getAttribute("data-status")).sort()).toEqual(["failed", "running"])
  })

  it("caps recent terminal jobs per source and shows a hidden-count note", async () => {
    mockListSources.mockResolvedValue([SOURCE])
    const manyCompleted = Array.from({ length: 8 }, (_, i) =>
      makeJob({ id: `done-${i}`, status: "completed", createdAt: `2024-01-0${i + 1}T00:00:00Z` })
    )
    mockListJobs.mockImplementation(({ status } = {}) =>
      Promise.resolve(status === "completed" ? manyCompleted : [])
    )
    renderPage()

    await waitFor(() => {
      expect(screen.getAllByTestId("job-node")).toHaveLength(5)
    })
    expect(screen.getByText("+3 older")).toBeInTheDocument()
  })

  it("shows an inline error when a fetch fails", async () => {
    mockListSources.mockRejectedValue(new Error("network error"))
    renderPage()

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument()
    })
  })

  it("refreshes on an interval", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockListSources.mockResolvedValue([])
    renderPage()

    await vi.waitFor(() => expect(mockListSources).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(3000)
    await vi.waitFor(() => expect(mockListSources).toHaveBeenCalledTimes(2))
  })
})
