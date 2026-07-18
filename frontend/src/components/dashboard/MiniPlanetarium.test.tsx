import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, test, vi } from "vitest"
import { DEMO_NODES } from "@/lib/demoGraph"

// Stub the lazy R3F surface and useMode so the test only checks fetch → render
// wiring and the empty state.
vi.mock("next/dynamic", () => ({
  default: () => ({ nodes }: { nodes: { id: string }[] }) => (
    <div data-testid="starfield">{nodes.length} nodes</div>
  ),
}))
vi.mock("@/lib/theme", () => ({ useMode: () => ({ mode: "meridian" }) }))
vi.mock("@/lib/api", () => ({ listPlanetariumNodes: vi.fn() }))

import { MiniPlanetarium } from "./MiniPlanetarium"
import { listPlanetariumNodes } from "@/lib/api"

describe("MiniPlanetarium", () => {
  test("renders the starfield with fetched nodes (capped)", async () => {
    vi.mocked(listPlanetariumNodes).mockResolvedValue(DEMO_NODES)
    render(<MiniPlanetarium />)
    await waitFor(() => expect(screen.getByTestId("starfield")).toBeInTheDocument())
    // 40 demo nodes is at the cap.
    expect(screen.getByTestId("starfield")).toHaveTextContent("40 nodes")
  })

  test("shows an empty state when there are no nodes", async () => {
    vi.mocked(listPlanetariumNodes).mockResolvedValue([])
    render(<MiniPlanetarium />)
    await waitFor(() => expect(screen.getByText(/Nothing to show yet/i)).toBeInTheDocument())
  })
})
