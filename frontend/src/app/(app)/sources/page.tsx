"use client"

import { useEffect, useState } from "react"
import { extractClaims, getJob, listSources } from "@/lib/api"
import { filterByStatus } from "@/lib/derive"
import type { Source } from "@/lib/types"
import { SourceRow } from "@/components/domain/SourceRow"
import { Skeleton } from "@/components/ui/Skeleton"

const FILTER_PILLS = ["ALL", "PENDING", "INGESTING", "VERIFIED", "QUARANTINED", "PURGED"] as const
type FilterPill = (typeof FILTER_PILLS)[number]

function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, i) => (
        <tr key={i} className="border-t border-whisper">
          <td className="px-5 py-3" colSpan={7}>
            <Skeleton className="h-5 w-full" />
          </td>
        </tr>
      ))}
    </>
  )
}

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeFilter, setActiveFilter] = useState<FilterPill>("ALL")
  const [running, setRunning] = useState<Record<string, string>>({})

  async function refreshSources() {
    await listSources()
      .then((data) => {
        setSources(data)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load sources")
      })
  }

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

  async function startExtraction(source: Source) {
    setError(null)
    try {
      const result = await extractClaims(source.id, (source.claimCount ?? 0) > 0)
      setRunning((current) => ({ ...current, [source.id]: result.jobId }))

      let active = true
      while (active) {
        await new Promise((resolve) => window.setTimeout(resolve, 1200))
        const job = await getJob(result.jobId)
        if (job.status === "completed" || job.status === "failed") {
          active = false
          setRunning((current) => {
            const next = { ...current }
            delete next[source.id]
            return next
          })
          await refreshSources()
          if (job.status === "failed") setError(job.error ?? "Claim extraction failed")
        }
      }
    } catch (err: unknown) {
      setRunning((current) => {
        const next = { ...current }
        delete next[source.id]
        return next
      })
      setError(err instanceof Error ? err.message : "Claim extraction failed")
    }
  }

  const isLoading = sources === null && error === null
  const filtered = sources ? filterByStatus(sources, activeFilter) : []

  return (
    <div className="space-y-6 p-8">
      {/* Page heading */}
      <div className="flex items-baseline gap-3">
        <h1 className="font-heading text-2xl font-medium text-dust">Sources</h1>
        {sources !== null && (
          <span className="font-mono text-xs text-ember bg-chamber border border-whisper rounded-meridian px-2 py-0.5">
            {sources.length}
          </span>
        )}
      </div>

      {/* Filter pills */}
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
        {FILTER_PILLS.map((pill) => (
          <button
            key={pill}
            onClick={() => setActiveFilter(pill)}
            aria-pressed={activeFilter === pill}
            className={
              activeFilter === pill
                ? "rounded-meridian bg-ember px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-archive transition-colors"
                : "rounded-meridian px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-ash transition-colors hover:text-dust"
            }
          >
            {pill === "ALL" ? "All" : pill.charAt(0) + pill.slice(1).toLowerCase()}
          </button>
        ))}
      </div>

      {/* Error */}
      {error !== null && (
        <div
          role="alert"
          className="rounded-hearth border border-whisper bg-chamber px-6 py-4 text-sm text-ash"
        >
          Could not load sources: {error}
        </div>
      )}

      {/* Table — no outer card border, border-top dividers per row */}
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-whisper">
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-ash">
              Filename
            </th>
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-ash">
              Type
            </th>
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-ash">
              Status
            </th>
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-ash">
              Size
            </th>
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-ash">
              Obs
            </th>
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-ash">
              Claims
            </th>
            <th className="px-5 py-3 text-right font-mono text-[11px] uppercase tracking-widest text-ash">
              Extract
            </th>
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            <SkeletonRows />
          ) : (
            filtered.map((source) => (
              <SourceRow
                isExtracting={Boolean(running[source.id])}
                key={source.id}
                onExtract={startExtraction}
                source={source}
              />
            ))
          )}
        </tbody>
      </table>

      {!isLoading && error === null && filtered.length === 0 && (
        <p className="px-5 text-sm text-ash">No sources match this filter.</p>
      )}
    </div>
  )
}
