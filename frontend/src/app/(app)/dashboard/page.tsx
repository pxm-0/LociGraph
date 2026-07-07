"use client"

import { useEffect, useState } from "react"
import { getDashboardSummary, listSources } from "@/lib/api"
import { summarize } from "@/lib/derive"
import type { DashboardSummary, Source } from "@/lib/types"
import { Skeleton } from "@/components/ui/Skeleton"
import { StatusBadge } from "@/components/ui/StatusBadge"
import { StatCard } from "@/components/domain/StatCard"

const RECENT_COUNT = 8

function DashboardSkeletons() {
  return (
    <>
      {/* Stat area skeletons — asymmetric: one wide + two narrow */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[2fr_1fr_1fr]">
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
      </div>
      {/* Activity list skeletons */}
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-10" />
        ))}
      </div>
    </>
  )
}

export default function DashboardPage() {
  const [sources, setSources] = useState<Source[] | null>(null)
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([listSources(), getDashboardSummary()])
      .then(([sourceData, summaryData]) => {
        if (!cancelled) {
          setSources(sourceData)
          setSummary(summaryData)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load sources")
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const isLoading = sources === null && error === null

  const stats = sources ? summarize(sources) : null
  const recent = sources
    ? [...sources]
        .sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }) * -1)
        .slice(0, RECENT_COUNT)
    : []

  return (
    <div className="space-y-10 p-8">
      {/* Page heading */}
      <div className="flex items-baseline justify-between">
        <h1 className="font-heading text-2xl font-medium text-ink">
          Archive Overview
        </h1>
        {sources !== null && (
          <span className="font-mono text-xs text-muted">
            {sources.length} source{sources.length !== 1 ? "s" : ""} indexed
          </span>
        )}
      </div>

      {isLoading ? (
        <DashboardSkeletons />
      ) : error !== null ? (
        <div
          role="alert"
          className="rounded-hearth border border-hairline bg-surface px-6 py-4 text-sm text-muted"
        >
          Could not load sources: {error}
        </div>
      ) : stats !== null ? (
        <>
          {/* Stat tiles — asymmetric layout: total takes the dominant slot */}
          <section aria-label="Source statistics">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-[2fr_1fr_1fr]">
              <StatCard value={stats.total} label="Total Sources" />
              <StatCard value={stats.verified} label="Verified" />
              <StatCard value={stats.inFlight} label="In-flight" />
            </div>
          </section>

          {/* Knowledge extracted — real totals across the whole archive, not just what's loaded on a page */}
          {summary !== null && (
            <section aria-label="Extraction statistics">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <StatCard value={summary.observationCount} label="Observations" />
                <StatCard value={summary.claimCount} label="Claims" />
                <StatCard value={summary.conceptCount} label="Concepts" />
              </div>
            </section>
          )}

          {/* Recent activity */}
          <section aria-label="Recent ingestions">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-heading text-base font-medium text-ink">
                Recent Ingestions
              </h2>
              <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
                Latest {Math.min(RECENT_COUNT, recent.length)}
              </span>
            </div>

            {recent.length === 0 ? (
              <p className="text-sm text-muted">No sources ingested yet.</p>
            ) : (
              <div className="rounded-hearth border border-hairline overflow-hidden">
                <table className="w-full border-collapse text-left text-sm">
                  <thead>
                    <tr className="border-b border-hairline bg-surface-hover">
                      <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-muted">
                        Source
                      </th>
                      <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-muted">
                        Status
                      </th>
                      <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-muted">
                        Type
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {recent.map((source) => (
                      <tr
                        key={source.id}
                        className="transition-colors hover:bg-surface-hover"
                      >
                        <td className="px-5 py-3 font-ui text-ink">
                          {source.originalFilename ?? (
                            <span className="text-muted">—</span>
                          )}
                        </td>
                        <td className="px-5 py-3">
                          <StatusBadge status={source.importStatus} />
                        </td>
                        <td className="px-5 py-3 font-mono text-xs uppercase tracking-wide text-muted">
                          {source.sourceType}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  )
}
