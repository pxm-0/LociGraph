import { act, render, screen } from "@testing-library/react"
import { beforeEach, expect, test } from "vitest"
import { ThemeProvider, useMode } from "./theme"

function Probe() {
  const { mode, toggle } = useMode()
  return <button onClick={toggle}>mode:{mode}</button>
}

beforeEach(() => localStorage.clear())

test("defaults to hearth and toggles to meridian", async () => {
  render(<ThemeProvider><Probe /></ThemeProvider>)
  const btn = screen.getByRole("button")
  expect(btn).toHaveTextContent("mode:hearth")
  await act(async () => btn.click())
  expect(btn).toHaveTextContent("mode:meridian")
  expect(localStorage.getItem("locigraph-mode")).toBe("meridian")
})

test("reads persisted mode on mount", () => {
  localStorage.setItem("locigraph-mode", "meridian")
  render(<ThemeProvider><Probe /></ThemeProvider>)
  expect(screen.getByRole("button")).toHaveTextContent("mode:meridian")
})
