"use client"

import { useEffect, useState } from "react"
import { extractClaims, getJob, listSources, purgeSource } from "@/lib/api"
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
        <tr key={i} className="border-t border-hairline">
          <td className="px-5 py-3" colSpan={7}>
            <Skeleton className="h-5 w-full" />
          </td>
        </tr>
      ))}
    </>
  )
}

interface ExtractionProgress {
  jobId: string
  itemsCompleted: number | null
  itemsTotal: number | null
}

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeFilter, setActiveFilter] = useState<FilterPill>("ALL")
  const [running, setRunning] = useState<Record<string, ExtractionProgress>>({})

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
      const result = await extractClaims(source.id, source.claimCount > 0)
      setRunning((current) => ({
        ...current,
        [source.id]: { jobId: result.jobId, itemsCompleted: null, itemsTotal: null },
      }))

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
        } else {
          setRunning((current) => ({
            ...current,
            [source.id]: {
              jobId: result.jobId,
              itemsCompleted: job.itemsCompleted,
              itemsTotal: job.itemsTotal,
            },
          }))
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

  async function deleteSource(source: Source) {
    if (!window.confirm(`Delete "${source.originalFilename ?? source.id}"? This cannot be undone.`)) {
      return
    }
    setError(null)
    try {
      await purgeSource(source.id)
      await refreshSources()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to delete source")
    }
  }

  const isLoading = sources === null && error === null
  const filtered = sources ? filterByStatus(sources, activeFilter) : []

  return (
    <div className="space-y-6 p-8">
      {/* Page heading */}
      <div className="flex items-baseline gap-3">
        <h1 className="font-heading text-2xl font-medium text-ink">Sources</h1>
        {sources !== null && (
          <span className="font-mono text-xs text-accent bg-surface border border-hairline rounded-meridian px-2 py-0.5">
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
                ? "rounded-meridian bg-ember px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-void transition-colors"
                : "rounded-meridian px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-muted transition-colors hover:text-ink"
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
          className="rounded-hearth border border-hairline bg-surface px-6 py-4 text-sm text-muted"
        >
          {error}
        </div>
      )}

      {/* Table — no outer card border, border-top dividers per row */}
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-hairline">
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-muted">
              Filename
            </th>
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-muted">
              Type
            </th>
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-muted">
              Status
            </th>
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-muted">
              Size
            </th>
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-muted">
              Obs
            </th>
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-muted">
              Claims
            </th>
            <th className="px-5 py-3 text-right font-mono text-[11px] uppercase tracking-widest text-muted">
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
                itemsCompleted={running[source.id]?.itemsCompleted ?? null}
                itemsTotal={running[source.id]?.itemsTotal ?? null}
                key={source.id}
                onDelete={deleteSource}
                onExtract={startExtraction}
                source={source}
              />
            ))
          )}
        </tbody>
      </table>

      {!isLoading && error === null && filtered.length === 0 && (
        <p className="px-5 text-sm text-muted">No sources match this filter.</p>
      )}
    </div>
  )
}
