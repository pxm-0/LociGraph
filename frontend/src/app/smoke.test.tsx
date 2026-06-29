import { render, screen } from "@testing-library/react"
import { expect, test } from "vitest"

function Hello() { return <h1>LociGraph</h1> }

test("test harness renders a component", () => {
  render(<Hello />)
  expect(screen.getByRole("heading", { name: "LociGraph" })).toBeInTheDocument()
})
