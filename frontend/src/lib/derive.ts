import type { Source } from "./types"

const IN_FLIGHT_STATUSES = new Set(["PENDING", "INGESTING"])

export interface SourceSummary {
  total: number
  verified: number
  inFlight: number
}

export function summarize(sources: Source[]): SourceSummary {
  let verified = 0
  let inFlight = 0

  for (const s of sources) {
    if (s.importStatus === "VERIFIED") verified++
    else if (IN_FLIGHT_STATUSES.has(s.importStatus)) inFlight++
  }

  return { total: sources.length, verified, inFlight }
}
