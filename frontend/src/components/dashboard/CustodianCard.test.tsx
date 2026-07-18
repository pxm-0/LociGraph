import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, test, vi } from "vitest"
import { CustodianCard } from "./CustodianCard"

describe("CustodianCard", () => {
  test("renders pending proposal count", () => {
    render(<CustodianCard pendingProposals={2} onAsk={() => {}} />)
    expect(screen.getByText(/2 proposals awaiting review/i)).toBeInTheDocument()
  })

  test("shows no-proposals state at zero", () => {
    render(<CustodianCard pendingProposals={0} onAsk={() => {}} />)
    expect(screen.getByText(/No open proposals/i)).toBeInTheDocument()
  })

  test("fires onAsk when the button is clicked", async () => {
    const onAsk = vi.fn()
    render(<CustodianCard pendingProposals={0} onAsk={onAsk} />)
    await userEvent.click(screen.getByRole("button", { name: /Ask the Custodian/i }))
    expect(onAsk).toHaveBeenCalledOnce()
  })
})
