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
  listLoggedItems: vi.fn().mockResolvedValue([]),
  acceptLoggedItem: vi.fn(),
  rejectLoggedItem: vi.fn(),
}))

import {
  createCustodianSession,
  listCustodianSessions,
  streamCustodianMessage,
  listLoggedItems,
  acceptLoggedItem,
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

  it("shows a proposal card after a turn that proposes something, and accepting removes it", async () => {
    mockCreate.mockResolvedValueOnce({
      id: "s1",
      title: null,
      startedAt: "2024-05-12T14:32:01Z",
      endedAt: null,
      model: "gpt-4o-mini",
      provider: "openai",
    })
    const proposal = {
      id: "p1",
      sessionId: "s1",
      itemType: "note",
      targetId: null,
      content: { content: "Remember this." },
      status: "proposed" as const,
      createdAt: "2024-05-12T14:32:01Z",
      resolvedAt: null,
    }
    vi.mocked(listLoggedItems).mockResolvedValueOnce([]).mockResolvedValueOnce([proposal])
    mockStream.mockImplementationOnce(async (_id, _content, handlers) => {
      handlers.onDone()
    })
    vi.mocked(acceptLoggedItem).mockResolvedValueOnce({ ...proposal, status: "accepted" })

    renderOrb()
    await userEvent.click(screen.getByLabelText("Open the Custodian"))
    await userEvent.type(screen.getByPlaceholderText("Ask the Custodian..."), "log it")
    await userEvent.keyboard("{Enter}")

    await waitFor(() => {
      expect(screen.getByText(/Save as note/)).toBeInTheDocument()
    })

    await userEvent.click(screen.getByText("Accept"))

    await waitFor(() => {
      expect(screen.getByText(/Logged: Save as note/)).toBeInTheDocument()
    })
  })

  it("summarizes a propose_* tool call as a generic archive-change notice, not a search", async () => {
    mockCreate.mockResolvedValueOnce({
      id: "s1",
      title: null,
      startedAt: "2024-05-12T14:32:01Z",
      endedAt: null,
      model: "gpt-4o-mini",
      provider: "openai",
    })
    mockStream.mockImplementationOnce(async (_id, _content, handlers) => {
      handlers.onToolCall("propose_note", "")
      handlers.onDone()
    })

    renderOrb()
    await userEvent.click(screen.getByLabelText("Open the Custodian"))
    await userEvent.type(screen.getByPlaceholderText("Ask the Custodian..."), "log it")
    await userEvent.keyboard("{Enter}")

    await waitFor(() => {
      expect(screen.getByText("Proposed a change to your archive")).toBeInTheDocument()
      expect(screen.queryByText(/Searched the archive for/)).not.toBeInTheDocument()
    })
  })
})
