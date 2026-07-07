import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import { ThemeProvider } from "@/lib/theme"
import type { Job, Source } from "@/lib/types"
import SourcesPage from "./page"

vi.mock("@/lib/api", () => ({
  listSources: vi.fn(),
  purgeSource: vi.fn(),
  extractClaims: vi.fn(),
  embedClaims: vi.fn(),
  getJob: vi.fn(),
  listJobs: vi.fn().mockResolvedValue([]),
}))

import { embedClaims, extractClaims, getJob, listJobs, listSources, purgeSource } from "@/lib/api"
const mockListSources = vi.mocked(listSources)
const mockPurgeSource = vi.mocked(purgeSource)
const mockExtractClaims = vi.mocked(extractClaims)
const mockEmbedClaims = vi.mocked(embedClaims)
const mockGetJob = vi.mocked(getJob)
const mockListJobs = vi.mocked(listJobs)

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    jobType: "extract_claims",
    status: "running",
    attempts: 0,
    error: null,
    createdAt: null,
    startedAt: null,
    completedAt: null,
    itemsCompleted: null,
    itemsTotal: null,
    sourceId: null,
    ...overrides,
  }
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
  {
    id: "4",
    sourceType: "html",
    originalFilename: "chat_export.html",
    importStatus: "PURGED",
    fileSizeBytes: 1536,
    importedAt: null,
    observationCount: 0,
    claimCount: 0,
    claimExtractionStatus: "waiting",
  },
]

function renderSources() {
  return render(
    <ThemeProvider>
      <SourcesPage />
    </ThemeProvider>,
  )
}

describe("SourcesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("renders all sources after load", async () => {
    mockListSources.mockResolvedValueOnce(MOCK_SOURCES)
    renderSources()

    await waitFor(() => {
      expect(screen.getByText("archive_manifest.json")).toBeInTheDocument()
      expect(screen.getByText("notes_2024.md")).toBeInTheDocument()
      expect(screen.getByText("report_q3.pdf")).toBeInTheDocument()
      expect(screen.getByText("chat_export.html")).toBeInTheDocument()
    })
  })

  it("filters to only VERIFIED rows when Verified pill is clicked", async () => {
    mockListSources.mockResolvedValueOnce(MOCK_SOURCES)
    renderSources()

    await waitFor(() => {
      expect(screen.getByText("archive_manifest.json")).toBeInTheDocument()
    })

    await userEvent.click(screen.getByText("Verified"))

    expect(screen.getByText("archive_manifest.json")).toBeInTheDocument()
    expect(screen.getByText("notes_2024.md")).toBeInTheDocument()
    expect(screen.queryByText("report_q3.pdf")).not.toBeInTheDocument()
    expect(screen.queryByText("chat_export.html")).not.toBeInTheDocument()
  })

  it("shows inline error when listSources throws", async () => {
    mockListSources.mockRejectedValueOnce(new Error("network error"))
    renderSources()

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument()
    })
  })

  it("shows count badge after load", async () => {
    mockListSources.mockResolvedValueOnce(MOCK_SOURCES)
    renderSources()

    await waitFor(() => {
      expect(screen.getByText("4")).toBeInTheDocument()
    })
  })

  it("shows page title Sources", () => {
    mockListSources.mockImplementation(() => new Promise(() => {}))
    renderSources()
    expect(screen.getByText("Sources")).toBeInTheDocument()
  })

  describe("Delete button", () => {
    it("is disabled when claimCount > 0 or status is already PURGED", async () => {
      const sourcesWithClaims: Source[] = [
        { ...MOCK_SOURCES[0], claimCount: 2 },
        MOCK_SOURCES[3], // PURGED, claimCount 0
      ]
      mockListSources.mockResolvedValueOnce(sourcesWithClaims)
      renderSources()

      await waitFor(() => {
        expect(screen.getByText("archive_manifest.json")).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByRole("button", { name: "Delete" })
      expect(deleteButtons).toHaveLength(2)
      for (const button of deleteButtons) {
        expect(button).toBeDisabled()
      }
    })

    it("does not call purgeSource when confirmation is cancelled", async () => {
      const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false)
      mockListSources.mockResolvedValueOnce(MOCK_SOURCES)
      renderSources()

      await waitFor(() => {
        expect(screen.getByText("archive_manifest.json")).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByRole("button", { name: "Delete" })
      await userEvent.click(deleteButtons[0])

      expect(confirmSpy).toHaveBeenCalled()
      expect(mockPurgeSource).not.toHaveBeenCalled()
      confirmSpy.mockRestore()
    })

    it("calls purgeSource and refreshes the list when confirmed", async () => {
      const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true)
      mockListSources.mockResolvedValueOnce(MOCK_SOURCES)
      mockPurgeSource.mockResolvedValueOnce(undefined)
      const refreshedSources = MOCK_SOURCES.map((s) =>
        s.id === "1" ? { ...s, importStatus: "PURGED" } : s,
      )
      mockListSources.mockResolvedValueOnce(refreshedSources)
      renderSources()

      await waitFor(() => {
        expect(screen.getByText("archive_manifest.json")).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByRole("button", { name: "Delete" })
      await userEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(mockPurgeSource).toHaveBeenCalledWith("1")
      })
      await waitFor(() => {
        expect(mockListSources).toHaveBeenCalledTimes(2)
      })
      confirmSpy.mockRestore()
    })

    it("shows the error banner on a 409 without navigating away or crashing", async () => {
      const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true)
      mockListSources.mockResolvedValueOnce(MOCK_SOURCES)
      mockPurgeSource.mockRejectedValueOnce(
        new Error("source has claims — cannot delete after extraction"),
      )
      renderSources()

      await waitFor(() => {
        expect(screen.getByText("archive_manifest.json")).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByRole("button", { name: "Delete" })
      await userEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeInTheDocument()
      })
      expect(screen.getByText("archive_manifest.json")).toBeInTheDocument()
      confirmSpy.mockRestore()
    })
  })

  describe("Extraction progress polling", () => {
    it("updates progress numbers across successive poll ticks", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
      mockListSources.mockResolvedValueOnce([MOCK_SOURCES[0]])
      mockExtractClaims.mockResolvedValueOnce({ jobIds: ["job-1"], status: "running" })
      mockGetJob
        .mockResolvedValueOnce(makeJob({ status: "running", itemsCompleted: 4, itemsTotal: 10 }))
        .mockResolvedValueOnce(makeJob({ status: "completed", itemsCompleted: 10, itemsTotal: 10 }))
      mockListSources.mockResolvedValueOnce([{ ...MOCK_SOURCES[0], claimCount: 3 }])
      renderSources()

      await vi.waitFor(() => {
        expect(screen.getByText("archive_manifest.json")).toBeInTheDocument()
      })

      const extractButton = screen.getByRole("button", { name: "Extract" })
      await userEvent.click(extractButton, { delay: null })

      await vi.waitFor(() => expect(mockExtractClaims).toHaveBeenCalled())

      await vi.advanceTimersByTimeAsync(1200)
      await vi.waitFor(() => {
        expect(screen.getByText("Extract: 4 / 10 processed")).toBeInTheDocument()
      })

      await vi.advanceTimersByTimeAsync(1200)
      await vi.waitFor(() => {
        expect(mockListSources).toHaveBeenCalledTimes(2)
      })

      vi.useRealTimers()
    })

    it("surfaces the job error and stops polling when extraction fails", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
      mockListSources.mockResolvedValueOnce([MOCK_SOURCES[0]])
      mockExtractClaims.mockResolvedValueOnce({ jobIds: ["job-1"], status: "running" })
      mockGetJob.mockResolvedValueOnce(
        makeJob({ status: "failed", error: "OpenAI rejected the configured API key" })
      )
      mockListSources.mockResolvedValueOnce([MOCK_SOURCES[0]])
      renderSources()

      await vi.waitFor(() => {
        expect(screen.getByText("archive_manifest.json")).toBeInTheDocument()
      })
      await userEvent.click(screen.getByRole("button", { name: "Extract" }), { delay: null })
      await vi.waitFor(() => expect(mockExtractClaims).toHaveBeenCalled())

      await vi.advanceTimersByTimeAsync(1200)
      await vi.waitFor(() => {
        expect(screen.getByText("OpenAI rejected the configured API key")).toBeInTheDocument()
      })

      vi.useRealTimers()
    })
  })

  describe("Embedding progress polling", () => {
    it("shows embed progress and clears it once the job completes", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
      mockListSources.mockResolvedValueOnce([{ ...MOCK_SOURCES[0], claimCount: 5 }])
      mockEmbedClaims.mockResolvedValueOnce({ jobId: "embed-1", status: "pending" })
      mockGetJob
        .mockResolvedValueOnce(
          makeJob({ id: "embed-1", jobType: "embed_claims", itemsCompleted: 2, itemsTotal: 5 })
        )
        .mockResolvedValueOnce(
          makeJob({
            id: "embed-1",
            jobType: "embed_claims",
            status: "completed",
            itemsCompleted: 5,
            itemsTotal: 5,
          })
        )
      mockListSources.mockResolvedValueOnce([{ ...MOCK_SOURCES[0], claimCount: 5 }])
      renderSources()

      await vi.waitFor(() => {
        expect(screen.getByText("archive_manifest.json")).toBeInTheDocument()
      })

      await userEvent.click(screen.getByRole("button", { name: "Embed" }), { delay: null })
      await vi.waitFor(() => expect(mockEmbedClaims).toHaveBeenCalledWith("1"))

      await vi.advanceTimersByTimeAsync(1200)
      await vi.waitFor(() => {
        expect(screen.getByText("Embed: 2 / 5 processed")).toBeInTheDocument()
      })

      await vi.advanceTimersByTimeAsync(1200)
      await vi.waitFor(() => {
        expect(screen.queryByText(/processed/)).not.toBeInTheDocument()
      })

      vi.useRealTimers()
    })
  })

  describe("Resuming jobs already in flight on load", () => {
    it("shows extraction progress for a job it did not trigger, discovered via listJobs on mount", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
      mockListSources.mockResolvedValueOnce([MOCK_SOURCES[0]])
      mockListJobs.mockImplementation(({ status } = {}) =>
        Promise.resolve(
          status === "running"
            ? [makeJob({ id: "resumed-1", sourceId: "1", status: "running" })]
            : []
        )
      )
      mockGetJob.mockResolvedValueOnce(
        makeJob({ id: "resumed-1", status: "running", itemsCompleted: 7, itemsTotal: 20 })
      )
      renderSources()

      await vi.waitFor(() => {
        expect(screen.getByText("archive_manifest.json")).toBeInTheDocument()
      })
      await vi.waitFor(() => expect(mockListJobs).toHaveBeenCalled())

      await vi.advanceTimersByTimeAsync(1200)
      await vi.waitFor(() => {
        expect(screen.getByText("Extract: 7 / 20 processed")).toBeInTheDocument()
      })
      expect(mockExtractClaims).not.toHaveBeenCalled()

      vi.useRealTimers()
    })

    it("ignores active jobs for sources not currently loaded", async () => {
      // Fake timers, never advanced past the poll interval: the resumed
      // watcher for source "999" is started (proving hydration ran), but
      // its first getJob poll never fires within this test, so there's
      // nothing to render — and nothing left over to leak into later tests.
      vi.useFakeTimers({ shouldAdvanceTime: true })
      mockListSources.mockResolvedValueOnce([MOCK_SOURCES[0]])
      mockListJobs.mockImplementation(({ status } = {}) =>
        Promise.resolve(
          status === "pending" ? [makeJob({ id: "other-src-job", sourceId: "999" })] : []
        )
      )
      renderSources()

      await vi.waitFor(() => {
        expect(screen.getByText("archive_manifest.json")).toBeInTheDocument()
      })
      await vi.waitFor(() => expect(mockListJobs).toHaveBeenCalled())

      expect(screen.queryByText(/processed/)).not.toBeInTheDocument()
      expect(mockGetJob).not.toHaveBeenCalled()

      vi.useRealTimers()
    })
  })
})
