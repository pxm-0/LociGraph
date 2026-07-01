import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import { ThemeProvider } from "@/lib/theme"
import type { Source } from "@/lib/types"
import SourcesPage from "./page"

vi.mock("@/lib/api", () => ({
  listSources: vi.fn(),
}))

import { listSources } from "@/lib/api"
const mockListSources = vi.mocked(listSources)

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
})
