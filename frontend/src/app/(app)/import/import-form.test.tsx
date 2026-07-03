import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import ImportForm from "./import-form"
import { detectSourceType } from "@/lib/types"

// Use importActual so any `instanceof ApiError` checks elsewhere in the
// component work against the same class reference tests would throw.
vi.mock("@/lib/api", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api")>()
  return {
    ...actual,
    uploadSource: vi.fn(),
  }
})

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
})
