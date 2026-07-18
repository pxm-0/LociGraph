import { describe, expect, test } from "vitest"
import { DEMO_NODES } from "./demoGraph"

describe("DEMO_NODES", () => {
  test("has at least 30 nodes", () => {
    expect(DEMO_NODES.length).toBeGreaterThanOrEqual(30)
  })

  test("every node satisfies the PlanetariumNode shape with numeric coords", () => {
    for (const node of DEMO_NODES) {
      expect(typeof node.id).toBe("string")
      expect(typeof node.conceptId).toBe("string")
      expect(typeof node.conceptName).toBe("string")
      expect(Number.isFinite(node.x)).toBe(true)
      expect(Number.isFinite(node.y)).toBe(true)
      expect(Number.isFinite(node.z)).toBe(true)
      expect(Number.isFinite(node.mass)).toBe(true)
      expect(Number.isFinite(node.brightness)).toBe(true)
      expect(node.visualClass === "black_hole" || node.visualClass === "planet").toBe(true)
    }
  })

  test("has at least 2 black_hole nodes", () => {
    const blackHoles = DEMO_NODES.filter((n) => n.visualClass === "black_hole")
    expect(blackHoles.length).toBeGreaterThanOrEqual(2)
  })

  test("ids are unique", () => {
    const ids = new Set(DEMO_NODES.map((n) => n.id))
    expect(ids.size).toBe(DEMO_NODES.length)
  })
})
