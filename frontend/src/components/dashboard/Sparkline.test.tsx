import { describe, expect, test } from "vitest"
import { sparklinePath } from "./Sparkline"
import type { TrendPoint } from "@/lib/types"

const pts = (counts: number[]): TrendPoint[] => counts.map((count, i) => ({ date: `d${i}`, count }))

describe("sparklinePath", () => {
  test("maps N points to N SVG coords within bounds", () => {
    const d = sparklinePath(pts([0, 5, 10, 3]), 100, 24)
    const coords = d.split(" ")
    expect(coords).toHaveLength(4)
    for (const c of coords) {
      const [x, y] = c.slice(1).split(",").map(Number)
      expect(x).toBeGreaterThanOrEqual(0)
      expect(x).toBeLessThanOrEqual(100)
      expect(y).toBeGreaterThanOrEqual(0)
      expect(y).toBeLessThanOrEqual(24)
    }
  })

  test("flat series → horizontal line at mid-height", () => {
    const d = sparklinePath(pts([4, 4, 4]), 100, 24)
    expect(d).toBe("M0.00,12.00 L50.00,12.00 L100.00,12.00")
  })

  test("empty / single point → empty path", () => {
    expect(sparklinePath([], 100, 24)).toBe("")
    expect(sparklinePath(pts([1]), 100, 24)).toBe("")
  })
})
