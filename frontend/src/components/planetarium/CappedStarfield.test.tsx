import { render } from "@testing-library/react"
import { describe, expect, test, vi } from "vitest"

// Headless WebGL is out of scope — mock R3F/drei so we only assert wiring:
// the component mounts with the demo graph and renders a PlanetNode per node.
vi.mock("@react-three/fiber", () => ({
  Canvas: ({ children }: { children: React.ReactNode }) => <div data-testid="canvas">{children}</div>,
  useFrame: () => {},
}))
vi.mock("@react-three/drei", () => ({
  Bounds: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Stars: () => <div data-testid="stars" />,
}))
vi.mock("./PlanetNode", () => ({
  PlanetNode: ({ node }: { node: { id: string } }) => <div data-testid="planet-node">{node.id}</div>,
}))

import { CappedStarfield } from "./CappedStarfield"
import { DEMO_NODES } from "@/lib/demoGraph"

describe("CappedStarfield", () => {
  test("mounts with DEMO_NODES and renders a node per entry", () => {
    const { getByTestId, getAllByTestId } = render(<CappedStarfield nodes={DEMO_NODES} drift />)
    expect(getByTestId("canvas")).toBeInTheDocument()
    expect(getAllByTestId("planet-node")).toHaveLength(DEMO_NODES.length)
  })

  test("renders without throwing when empty", () => {
    const { getByTestId } = render(<CappedStarfield nodes={[]} />)
    expect(getByTestId("canvas")).toBeInTheDocument()
  })
})
