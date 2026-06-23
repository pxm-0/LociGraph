import { render, screen } from "@testing-library/react"
import { expect, test } from "vitest"
import { StatusBadge } from "./StatusBadge"

test("renders the status label in uppercase mono", () => {
  render(<StatusBadge status="VERIFIED" />)
  expect(screen.getByText("VERIFIED")).toBeInTheDocument()
})

test("maps unknown status without crashing", () => {
  render(<StatusBadge status="WEIRD" />)
  expect(screen.getByText("WEIRD")).toBeInTheDocument()
})
