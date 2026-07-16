import { expect, test } from "vitest"
import type { PlanetariumNodeDetail } from "@/lib/types"
import { describeNode } from "./describeNode"

function detail(overrides: Partial<PlanetariumNodeDetail> = {}): PlanetariumNodeDetail {
  return {
    conceptId: "c1",
    conceptName: "Alpha",
    conceptType: "entity",
    description: null,
    mass: 0.5,
    brightness: 0.5,
    visualClass: "planet",
    revisionCount: 0,
    edgeCount: 0,
    contradictionCount: 0,
    pinCount: 0,
    isEmbedded: true,
    ...overrides,
  }
}

test("describes a large, glowing black hole", () => {
  const text = describeNode(detail({ visualClass: "black_hole", mass: 0.9, brightness: 0.9 }))
  expect(text).toContain("black hole")
  expect(text).toContain("large")
  expect(text).toContain("glowing")
})

test("describes a small, dim planet", () => {
  const text = describeNode(detail({ visualClass: "planet", mass: 0.1, brightness: 0.05 }))
  expect(text).toContain("planet")
  expect(text).toContain("small")
  expect(text).toContain("dim")
})

test("describes a mid-size, moderately active planet", () => {
  const text = describeNode(detail({ visualClass: "planet", mass: 0.5, brightness: 0.5 }))
  expect(text).toContain("planet")
  expect(text).toContain("medium")
})
