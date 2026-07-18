import { describe, expect, test } from "vitest"
import { deltaThisWeek, mergeActivity, type ActivityItem } from "./dashboard"
import type { TrendPoint } from "./types"

function point(date: string, count: number): TrendPoint {
  return { date, count }
}

function item(at: string, label = at): ActivityItem {
  return { kind: "claim", label, at, href: "/claims/x" }
}

describe("deltaThisWeek", () => {
  test("sums the last 7 points", () => {
    const points = Array.from({ length: 30 }, (_, i) => point(`d${i}`, 1))
    expect(deltaThisWeek(points)).toBe(7)
  })

  test("handles fewer than 7 points", () => {
    expect(deltaThisWeek([point("a", 2), point("b", 3)])).toBe(5)
  })

  test("empty series is 0", () => {
    expect(deltaThisWeek([])).toBe(0)
  })
})

describe("mergeActivity", () => {
  test("interleaves and sorts by `at` descending", () => {
    const result = mergeActivity([item("2026-01-01")], [item("2026-03-01"), item("2026-02-01")])
    expect(result.map((r) => r.at)).toEqual(["2026-03-01", "2026-02-01", "2026-01-01"])
  })

  test("caps at 8", () => {
    const many = Array.from({ length: 20 }, (_, i) => item(`2026-01-${String(i + 1).padStart(2, "0")}`))
    expect(mergeActivity(many)).toHaveLength(8)
  })
})
