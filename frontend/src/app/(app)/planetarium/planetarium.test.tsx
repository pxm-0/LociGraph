import { render, screen } from "@testing-library/react"
import { beforeEach, expect, test, vi } from "vitest"
import type { PlanetariumNode } from "@/lib/types"

vi.mock("@/lib/api", () => ({ listPlanetariumNodes: vi.fn() }))
vi.mock("@/components/planetarium/PlanetariumScene", () => ({
  PlanetariumScene: ({ nodes }: { nodes: PlanetariumNode[] }) => (
    <div data-testid="scene">{nodes.length} nodes</div>
  ),
}))
vi.mock("@/components/planetarium/RebuildButton", () => ({
  RebuildButton: () => <button>Rebuild Planetarium</button>,
}))

import { listPlanetariumNodes } from "@/lib/api"
import PlanetariumPage from "./page"

const mockListPlanetariumNodes = vi.mocked(listPlanetariumNodes)

beforeEach(() => {
  vi.clearAllMocks()
})

test("shows an empty-state message when there are no nodes yet", async () => {
  mockListPlanetariumNodes.mockResolvedValue([])
  render(<PlanetariumPage />)
  expect(await screen.findByText(/nothing to show yet/i)).toBeInTheDocument()
})

test("renders the scene once nodes load", async () => {
  mockListPlanetariumNodes.mockResolvedValue([{ id: "n1" } as PlanetariumNode])
  render(<PlanetariumPage />)
  expect(await screen.findByTestId("scene")).toHaveTextContent("1 nodes")
})

test("shows an error message on fetch failure", async () => {
  mockListPlanetariumNodes.mockRejectedValue(new Error("boom"))
  render(<PlanetariumPage />)
  expect(await screen.findByRole("alert")).toHaveTextContent("boom")
})

test("always renders the rebuild button", async () => {
  mockListPlanetariumNodes.mockResolvedValue([])
  render(<PlanetariumPage />)
  expect(await screen.findByRole("button", { name: /rebuild planetarium/i })).toBeInTheDocument()
})
