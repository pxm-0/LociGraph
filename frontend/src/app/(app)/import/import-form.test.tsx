import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import ImportForm from "./import-form"
import { detectSourceType } from "@/lib/types"
import { ApiError, uploadSource } from "@/lib/api"

// Use importActual so any `instanceof ApiError` checks elsewhere in the
// component work against the same class reference tests would throw.
vi.mock("@/lib/api", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api")>()
  return {
    ...actual,
    uploadSource: vi.fn(),
  }
})

const mockUploadSource = vi.mocked(uploadSource)

function renderForm() {
  return render(<ImportForm />)
}

function makeFile(name: string, contents = "content"): File {
  return new File([contents], name)
}

describe("detectSourceType", () => {
  it("detects markdown from .md", () => {
    expect(detectSourceType("notes.md")).toBe("markdown")
  })

  it("detects html from .html", () => {
    expect(detectSourceType("page.html")).toBe("html")
  })

  it("detects pdf from .pdf", () => {
    expect(detectSourceType("doc.pdf")).toBe("pdf")
  })

  it("detects chatgpt from .zip", () => {
    expect(detectSourceType("export.zip")).toBe("chatgpt")
  })

  it("treats .json as ambiguous", () => {
    expect(detectSourceType("data.json")).toBe("ambiguous")
  })

  it("treats unrecognized extensions as ambiguous", () => {
    expect(detectSourceType("mystery.xyz")).toBe("ambiguous")
  })

  it("is case-insensitive on the extension", () => {
    expect(detectSourceType("NOTES.MD")).toBe("markdown")
  })
})

describe("ImportForm", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("stages 2 files with correct pre-filled types on selection, including ambiguous .json defaulting to json", async () => {
    const user = userEvent.setup()
    const mdFile = makeFile("notes.md")
    const jsonFile = makeFile("data.json")

    renderForm()

    const fileInput = screen.getByLabelText(/choose file/i)
    await user.upload(fileInput, [mdFile, jsonFile])

    const rows = screen.getByLabelText(/staged files/i)
    expect(rows).toBeInTheDocument()

    expect(screen.getByText("notes.md")).toBeInTheDocument()
    expect(screen.getByText("data.json")).toBeInTheDocument()

    const mdSelect = screen.getByLabelText(/source type for notes\.md/i) as HTMLSelectElement
    expect(mdSelect.value).toBe("markdown")

    const jsonSelect = screen.getByLabelText(/source type for data\.json/i) as HTMLSelectElement
    expect(jsonSelect.value).toBe("json")
    // Still editable, not disabled just because it was ambiguous.
    expect(jsonSelect).not.toBeDisabled()
  })

  it("appends dropped files to the existing staged list rather than replacing it", async () => {
    const user = userEvent.setup()
    const fileA = makeFile("a.md")
    const fileB = makeFile("b.pdf")
    const fileC = makeFile("c.html")

    renderForm()

    const fileInput = screen.getByLabelText(/choose file/i)
    await user.upload(fileInput, [fileA, fileB])

    expect(screen.getByText("a.md")).toBeInTheDocument()
    expect(screen.getByText("b.pdf")).toBeInTheDocument()

    const dropZone = screen.getByLabelText(/file drop zone/i)
    const dataTransfer = { files: [fileC] }
    // fireEvent is more appropriate than userEvent for native DragEvent with dataTransfer
    const { fireEvent } = await import("@testing-library/react")
    fireEvent.drop(dropZone, { dataTransfer })

    const staged = screen.getByLabelText(/staged files/i)
    expect(staged.querySelectorAll("li")).toHaveLength(3)
    expect(screen.getByText("c.html")).toBeInTheDocument()
  })

  it("removes only the clicked row when its status is pending", async () => {
    const user = userEvent.setup()
    const fileA = makeFile("a.md")
    const fileB = makeFile("b.pdf")

    renderForm()

    const fileInput = screen.getByLabelText(/choose file/i)
    await user.upload(fileInput, [fileA, fileB])

    await user.click(screen.getByLabelText(/remove a\.md/i))

    expect(screen.queryByText("a.md")).not.toBeInTheDocument()
    expect(screen.getByText("b.pdf")).toBeInTheDocument()
  })

  it("disables Upload All when the staged list is empty", () => {
    renderForm()
    expect(screen.getByRole("button", { name: /upload all/i })).toBeDisabled()
  })

  it("enables Upload All once a file is staged", async () => {
    const user = userEvent.setup()
    renderForm()

    const fileInput = screen.getByLabelText(/choose file/i)
    await user.upload(fileInput, makeFile("a.md"))

    expect(screen.getByRole("button", { name: /upload all/i })).toBeEnabled()
  })

  describe("Upload All", () => {
    async function stageThreeFiles(user: ReturnType<typeof userEvent.setup>) {
      const fileA = makeFile("a.md")
      const fileB = makeFile("b.pdf")
      const fileC = makeFile("c.html")
      const fileInput = screen.getByLabelText(/choose file/i)
      await user.upload(fileInput, [fileA, fileB, fileC])
      return { fileA, fileB, fileC }
    }

    it("calls uploadSource exactly 3 times, in staged order, with each row's sourceType", async () => {
      const user = userEvent.setup()
      mockUploadSource.mockResolvedValue({ sourceId: "s1", status: "queued" })
      renderForm()

      const { fileA, fileB, fileC } = await stageThreeFiles(user)
      await user.click(screen.getByRole("button", { name: /upload all/i }))

      await waitFor(() => expect(mockUploadSource).toHaveBeenCalledTimes(3))
      expect(mockUploadSource).toHaveBeenNthCalledWith(1, "markdown", fileA)
      expect(mockUploadSource).toHaveBeenNthCalledWith(2, "pdf", fileB)
      expect(mockUploadSource).toHaveBeenNthCalledWith(3, "html", fileC)
    })

    it("marks a 409 duplicate but still uploads the third file", async () => {
      const user = userEvent.setup()
      mockUploadSource
        .mockResolvedValueOnce({ sourceId: "s1", status: "queued" })
        .mockRejectedValueOnce(new ApiError(409, "already imported"))
        .mockResolvedValueOnce({ sourceId: "s3", status: "queued" })
      renderForm()

      await stageThreeFiles(user)
      await user.click(screen.getByRole("button", { name: /upload all/i }))

      await waitFor(() => expect(mockUploadSource).toHaveBeenCalledTimes(3))
      const rows = screen.getByLabelText(/staged files/i)
      const statuses = Array.from(rows.querySelectorAll("li")).map((li) =>
        li.textContent
      )
      expect(statuses[1]).toMatch(/duplicate/i)
      expect(statuses[0]).toMatch(/done/i)
      expect(statuses[2]).toMatch(/done/i)
    })

    it("stops the loop on a 401, leaving remaining rows pending and showing one page-level error", async () => {
      const user = userEvent.setup()
      mockUploadSource.mockRejectedValueOnce(new ApiError(401, "unauthorized"))
      renderForm()

      await stageThreeFiles(user)
      await user.click(screen.getByRole("button", { name: /upload all/i }))

      await waitFor(() => expect(mockUploadSource).toHaveBeenCalledTimes(1))
      const alerts = screen.getAllByRole("alert")
      expect(alerts).toHaveLength(1)
      expect(alerts[0]).toHaveTextContent(/session expired/i)

      const rows = screen.getByLabelText(/staged files/i)
      const statuses = Array.from(rows.querySelectorAll("li")).map((li) =>
        li.textContent
      )
      expect(statuses[1]).toMatch(/pending/i)
      expect(statuses[2]).toMatch(/pending/i)
    })

    it("shows a summary with counts once all rows settle", async () => {
      const user = userEvent.setup()
      mockUploadSource
        .mockResolvedValueOnce({ sourceId: "s1", status: "queued" })
        .mockResolvedValueOnce({ sourceId: "s2", status: "queued" })
        .mockRejectedValueOnce(new ApiError(409, "already imported"))
      renderForm()

      await stageThreeFiles(user)
      await user.click(screen.getByRole("button", { name: /upload all/i }))

      await waitFor(() =>
        expect(screen.getByText("2 uploaded, 1 duplicate")).toBeInTheDocument()
      )
    })

    it("reflects settled/total progress in the progress bar width at each step", async () => {
      const user = userEvent.setup()
      let resolveFirst: (v: { sourceId: string; status: string }) => void = () => {}
      mockUploadSource
        .mockImplementationOnce(
          () =>
            new Promise((resolve) => {
              resolveFirst = resolve
            })
        )
        .mockResolvedValueOnce({ sourceId: "s2", status: "queued" })
        .mockResolvedValueOnce({ sourceId: "s3", status: "queued" })
      renderForm()

      await stageThreeFiles(user)
      await user.click(screen.getByRole("button", { name: /upload all/i }))

      const bar = await screen.findByTestId("upload-progress-bar")
      resolveFirst({ sourceId: "s1", status: "queued" })

      await waitFor(() =>
        expect(bar).toHaveStyle({ width: `${(1 / 3) * 100}%` })
      )

      await waitFor(() => expect(mockUploadSource).toHaveBeenCalledTimes(3))
      await waitFor(() => expect(bar).toHaveStyle({ width: "100%" }))
    })
  })
})
