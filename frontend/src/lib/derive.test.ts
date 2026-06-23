import { describe, expect, it } from "vitest"
import { summarize } from "./derive"
import type { Source } from "./types"

function makeSource(importStatus: string, id = "1"): Source {
  return {
    id,
    sourceType: "json",
    originalFilename: `file-${id}.json`,
    importStatus,
    fileSizeBytes: 1024,
  }
}

describe("summarize", () => {
  it("returns zeros for an empty array", () => {
    const result = summarize([])
    expect(result).toEqual({ total: 0, verified: 0, inFlight: 0 })
  })

  it("counts VERIFIED sources correctly", () => {
    const sources = [
      makeSource("VERIFIED", "1"),
      makeSource("VERIFIED", "2"),
      makeSource("PENDING", "3"),
    ]
    const result = summarize(sources)
    expect(result).toEqual({ total: 3, verified: 2, inFlight: 1 })
  })

  it("counts INGESTING as in-flight", () => {
    const sources = [
      makeSource("VERIFIED", "1"),
      makeSource("INGESTING", "2"),
      makeSource("INGESTING", "3"),
    ]
    const result = summarize(sources)
    expect(result).toEqual({ total: 3, verified: 1, inFlight: 2 })
  })

  it("counts both PENDING and INGESTING as in-flight", () => {
    const sources = [
      makeSource("VERIFIED", "1"),
      makeSource("VERIFIED", "2"),
      makeSource("PENDING", "3"),
      makeSource("INGESTING", "4"),
    ]
    const result = summarize(sources)
    expect(result).toEqual({ total: 4, verified: 2, inFlight: 2 })
  })

  it("handles sources with statuses outside the known set", () => {
    const sources = [
      makeSource("VERIFIED", "1"),
      makeSource("QUARANTINED", "2"),
      makeSource("PURGED", "3"),
    ]
    const result = summarize(sources)
    expect(result).toEqual({ total: 3, verified: 1, inFlight: 0 })
  })

  it("correctly totals a single source", () => {
    const result = summarize([makeSource("VERIFIED", "1")])
    expect(result).toEqual({ total: 1, verified: 1, inFlight: 0 })
  })
})
