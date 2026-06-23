import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import ImportForm from "./import-form"

// Use importActual so the component's `instanceof ApiError` checks work
// against the same class reference that we throw in tests.
vi.mock("@/lib/api", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api")>()
  return {
    ...actual,
    uploadSource: vi.fn(),
  }
})

import { ApiError } from "@/lib/api"

import { uploadSource } from "@/lib/api"
const mockUpload = vi.mocked(uploadSource)

function renderForm() {
  return render(<ImportForm />)
}

describe("ImportForm", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("renders a source type selector", () => {
    renderForm()
    expect(screen.getByLabelText(/source type/i)).toBeInTheDocument()
  })

  it("calls uploadSource with selected type and file on submit, then shows success", async () => {
    const user = userEvent.setup()
    const file = new File(["{}"], "data.json", { type: "application/json" })
    const sourceId = "src-abc-123"

    mockUpload.mockResolvedValueOnce({ sourceId, status: "PENDING" })

    renderForm()

    // Select source type
    await user.selectOptions(screen.getByLabelText(/source type/i), "json")

    // Attach a file via the file input
    const fileInput = screen.getByLabelText(/choose file/i)
    await user.upload(fileInput, file)

    // Submit
    await user.click(screen.getByRole("button", { name: /import/i }))

    await waitFor(() => {
      expect(mockUpload).toHaveBeenCalledWith("json", file)
    })

    // Success state: show source id
    await waitFor(() => {
      expect(screen.getByText(sourceId)).toBeInTheDocument()
    })

    // Success state: link to /sources
    expect(screen.getByRole("link", { name: /sources/i })).toHaveAttribute(
      "href",
      "/sources",
    )
  })

  it("shows a duplicate alert when uploadSource rejects with 409", async () => {
    const user = userEvent.setup()
    const file = new File(["{}"], "data.json", { type: "application/json" })

    mockUpload.mockRejectedValueOnce(new ApiError(409, "duplicate"))

    renderForm()

    await user.selectOptions(screen.getByLabelText(/source type/i), "json")

    const fileInput = screen.getByLabelText(/choose file/i)
    await user.upload(fileInput, file)

    await user.click(screen.getByRole("button", { name: /import/i }))

    await waitFor(() => {
      const alert = screen.getByRole("alert")
      expect(alert).toBeInTheDocument()
      expect(alert.textContent?.toLowerCase()).toContain("duplicate")
    })
  })

  it("shows an invalid type alert when uploadSource rejects with 400", async () => {
    const user = userEvent.setup()
    const file = new File(["bad"], "bad.txt", { type: "text/plain" })

    mockUpload.mockRejectedValueOnce(new ApiError(400, "invalid type"))

    renderForm()

    await user.selectOptions(screen.getByLabelText(/source type/i), "json")

    const fileInput = screen.getByLabelText(/choose file/i)
    await user.upload(fileInput, file)

    await user.click(screen.getByRole("button", { name: /import/i }))

    await waitFor(() => {
      const alert = screen.getByRole("alert")
      expect(alert).toBeInTheDocument()
      expect(alert.textContent?.toLowerCase()).toMatch(/invalid|unsupported/)
    })
  })
})
