import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, test } from "vitest"
import { PlanetariumLegend } from "./PlanetariumLegend"

test("shows the legend by default and can be dismissed and reopened", async () => {
  render(<PlanetariumLegend />)

  expect(screen.getByText(/semantically similar/i)).toBeInTheDocument()
  expect(screen.getByText(/activity/i)).toBeInTheDocument()

  await userEvent.click(screen.getByRole("button", { name: /close legend/i }))
  expect(screen.queryByText(/semantically similar/i)).not.toBeInTheDocument()

  await userEvent.click(screen.getByRole("button", { name: /show legend/i }))
  expect(screen.getByText(/semantically similar/i)).toBeInTheDocument()
})
