import {
  getDashboardSummary,
  getDashboardTrends,
  listClaims,
  listConceptCandidates,
  listContradictions,
  listJobs,
} from "./api"
import type { DashboardSummary, DashboardTrends, TrendPoint } from "./types"

export type ActivityKind = "source" | "claim" | "contradiction"

export interface ActivityItem {
  kind: ActivityKind
  label: string
  at: string
  href: string
}

export interface NeedsAttentionCounts {
  contradictions: number
  jobs: number
  candidates: number
}

export interface DashboardData {
  summary: DashboardSummary
  trends: DashboardTrends
  needsAttention: NeedsAttentionCounts
  activity: ActivityItem[]
}

const ACTIVITY_CAP = 8
const WEEK = 7

// In-flight or failed jobs are the ones a human might need to act on.
const ATTENTION_JOB_STATUSES = new Set(["FAILED", "PENDING", "RUNNING", "INGESTING"])

/** Sum of the counts over the most recent 7 points (handles < 7 gracefully). */
export function deltaThisWeek(points: TrendPoint[]): number {
  return points.slice(-WEEK).reduce((sum, p) => sum + p.count, 0)
}

/** Merge activity lists, sort newest-first by `at`, cap at 8. Pure. */
export function mergeActivity(...lists: ActivityItem[][]): ActivityItem[] {
  return lists
    .flat()
    .sort((a, b) => b.at.localeCompare(a.at))
    .slice(0, ACTIVITY_CAP)
}

export async function loadDashboard(): Promise<DashboardData> {
  const [summary, trends, claims, contradictions, candidates, jobs] = await Promise.all([
    getDashboardSummary(),
    getDashboardTrends(),
    listClaims({ limit: ACTIVITY_CAP }),
    listContradictions({ limit: 50 }),
    listConceptCandidates({ status: "pending" }),
    listJobs({ limit: 100 }),
  ])

  const needsAttention: NeedsAttentionCounts = {
    contradictions: contradictions.filter((c) => c.classifiedAt === null).length,
    jobs: jobs.filter((j) => ATTENTION_JOB_STATUSES.has(j.status)).length,
    candidates: candidates.length,
  }

  const activity = mergeActivity(
    summary.recentSources.map((s) => ({
      kind: "source" as const,
      label: s.originalFilename ?? `${s.sourceType} source`,
      at: s.importedAt ?? "",
      href: `/sources/${s.id}`,
    })),
    claims.map((c) => ({
      kind: "claim" as const,
      label: c.claimText,
      at: c.createdAt,
      href: `/claims/${c.id}`,
    })),
    contradictions.map((c) => ({
      kind: "contradiction" as const,
      label: c.rationale || "Contradiction detected",
      at: c.createdAt,
      href: `/contradictions`,
    })),
  )

  return { summary, trends, needsAttention, activity }
}
