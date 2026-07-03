import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import { ThemeProvider } from "@/lib/theme"
import type { Source } from "@/lib/types"
import SourcesPage from "./page"

vi.mock("@/lib/api", () => ({
  listSources: vi.fn(),
  purgeSource: vi.fn(),
  extractClaims: vi.fn(),
  getJob: vi.fn(),
}))

import { extractClaims, getJob, listSources, purgeSource } from "@/lib/api"
const mockListSources = vi.mocked(listSources)
const mockPurgeSource = vi.mocked(purgeSource)
const mockExtractClaims = vi.mocked(extractClaims)
const mockGetJob = vi.mocked(getJob)

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
      mockExtractClaims.mockResolvedValueOnce({ jobId: "job-1", status: "running" })
      mockGetJob
        .mockResolvedValueOnce({
          id: "job-1",
          jobType: "extract_claims",
          status: "running",
          attempts: 0,
          error: null,
          createdAt: null,
          startedAt: null,
          completedAt: null,
          itemsCompleted: 4,
          itemsTotal: 10,
        })
        .mockResolvedValueOnce({
          id: "job-1",
          jobType: "extract_claims",
          status: "completed",
          attempts: 0,
          error: null,
          createdAt: null,
          startedAt: null,
          completedAt: null,
          itemsCompleted: 10,
          itemsTotal: 10,
        })
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
        expect(screen.getByText("4 / 10 processed")).toBeInTheDocument()
      })

      await vi.advanceTimersByTimeAsync(1200)
      await vi.waitFor(() => {
        expect(mockListSources).toHaveBeenCalledTimes(2)
      })

      vi.useRealTimers()
    })
  })

})
