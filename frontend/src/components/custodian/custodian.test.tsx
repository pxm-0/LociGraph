import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import { ThemeProvider } from "@/lib/theme"
import { Orb } from "@/components/custodian/Orb"

vi.mock("@/lib/api", () => ({
  createCustodianSession: vi.fn(),
  listCustodianSessions: vi.fn().mockResolvedValue([]),
  getCustodianMessages: vi.fn().mockResolvedValue([]),
  endCustodianSession: vi.fn(),
  streamCustodianMessage: vi.fn(),
}))

import {
  createCustodianSession,
  listCustodianSessions,
  streamCustodianMessage,
} from "@/lib/api"
const mockCreate = vi.mocked(createCustodianSession)
const mockList = vi.mocked(listCustodianSessions)
const mockStream = vi.mocked(streamCustodianMessage)

function renderOrb() {
  return render(
    <ThemeProvider>
      <Orb />
    </ThemeProvider>,
  )
}

describe("Orb", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockList.mockResolvedValue([])
  })

  it("opens the chat panel on click", async () => {
    renderOrb()
    await userEvent.click(screen.getByLabelText("Open the Custodian"))

    expect(screen.getByPlaceholderText("Ask the Custodian...")).toBeInTheDocument()
  })

  it("creates a session lazily and streams a reply on first send", async () => {
    mockCreate.mockResolvedValueOnce({
      id: "s1",
      title: null,
      startedAt: "2024-05-12T14:32:01Z",
      endedAt: null,
      model: "gpt-4o-mini",
      provider: "openai",
    })
    mockStream.mockImplementationOnce(async (_id, _content, handlers) => {
      handlers.onToken("Hello")
      handlers.onDone()
    })

    renderOrb()
    await userEvent.click(screen.getByLabelText("Open the Custodian"))
    await userEvent.type(screen.getByPlaceholderText("Ask the Custodian..."), "Hi")
    await userEvent.keyboard("{Enter}")

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalled()
      expect(mockStream).toHaveBeenCalledWith("s1", "Hi", expect.anything())
      expect(screen.getByText("Hello")).toBeInTheDocument()
    })
  })
})
