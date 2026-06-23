"use client"

import { useEffect, useState } from "react"
import { listSources } from "@/lib/api"
import { summarize } from "@/lib/derive"
import type { Source } from "@/lib/types"
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
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listSources()
      .then((data) => {
        if (!cancelled) setSources(data)
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
        <h1 className="font-heading text-2xl font-medium text-dust">
          Archive Overview
        </h1>
        {sources !== null && (
          <span className="font-mono text-xs text-ash">
            {sources.length} source{sources.length !== 1 ? "s" : ""} indexed
          </span>
        )}
      </div>

      {isLoading ? (
        <DashboardSkeletons />
      ) : error !== null ? (
        <div
          role="alert"
          className="rounded-hearth border border-whisper bg-chamber px-6 py-4 text-sm text-ash"
        >
          Could not load sources: {error}
        </div>
      ) : (
        <>
          {/* Stat tiles — asymmetric layout: total takes the dominant slot */}
          <section aria-label="Source statistics">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-[2fr_1fr_1fr]">
              <StatCard value={stats!.total} label="Total Sources" />
              <StatCard value={stats!.verified} label="Verified" />
              <StatCard value={stats!.inFlight} label="In-flight" />
            </div>
          </section>

          {/* Recent activity */}
          <section aria-label="Recent ingestions">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-heading text-base font-medium text-dust">
                Recent Ingestions
              </h2>
              <span className="font-mono text-[11px] uppercase tracking-widest text-ash">
                Latest {Math.min(RECENT_COUNT, recent.length)}
              </span>
            </div>

            {recent.length === 0 ? (
              <p className="text-sm text-ash">No sources ingested yet.</p>
            ) : (
              <div className="rounded-hearth border border-whisper overflow-hidden">
                <table className="w-full border-collapse text-left text-sm">
                  <thead>
                    <tr className="border-b border-whisper bg-[rgba(245,237,226,0.03)]">
                      <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-ash">
                        Source
                      </th>
                      <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-ash">
                        Status
                      </th>
                      <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-ash">
                        Type
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-whisper">
                    {recent.map((source) => (
                      <tr
                        key={source.id}
                        className="transition-colors hover:bg-[#26211d]"
                      >
                        <td className="px-5 py-3 font-ui text-dust">
                          {source.originalFilename ?? (
                            <span className="text-ash">—</span>
                          )}
                        </td>
                        <td className="px-5 py-3">
                          <StatusBadge status={source.importStatus} />
                        </td>
                        <td className="px-5 py-3 font-mono text-xs uppercase tracking-wide text-ash">
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
      )}
    </div>
  )
}
