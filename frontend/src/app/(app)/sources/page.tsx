"use client"

import { useCallback, useEffect, useState } from "react"
import { embedClaims, extractClaims, getJob, listJobs, listSources, purgeSource } from "@/lib/api"
import { filterByStatus } from "@/lib/derive"
import type { Job, Source } from "@/lib/types"
import { SourceRow } from "@/components/domain/SourceRow"
import { Skeleton } from "@/components/ui/Skeleton"

const FILTER_PILLS = ["ALL", "PENDING", "INGESTING", "VERIFIED", "QUARANTINED", "PURGED"] as const
type FilterPill = (typeof FILTER_PILLS)[number]

type JobType = "extract_claims" | "embed_claims"

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

interface JobProgress {
  jobIds: string[]
  itemsCompleted: number | null
  itemsTotal: number | null
}

const TERMINAL_JOB_STATUSES = new Set(["completed", "failed"])
const ACTIVE_JOB_STATUSES = ["pending", "running"] as const

// A source's extraction (or embedding) may be split across several chunk
// jobs running in parallel; the UI shows one progress bar summing across
// all of them and waits for every chunk to finish before refreshing.
function sumJobProgress(jobs: Job[]): { itemsCompleted: number | null; itemsTotal: number | null } {
  const withTotals = jobs.filter((j) => j.itemsCompleted != null && j.itemsTotal != null)
  if (withTotals.length === 0) return { itemsCompleted: null, itemsTotal: null }
  return {
    itemsCompleted: withTotals.reduce((sum, j) => sum + (j.itemsCompleted ?? 0), 0),
    itemsTotal: withTotals.reduce((sum, j) => sum + (j.itemsTotal ?? 0), 0),
  }
}

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeFilter, setActiveFilter] = useState<FilterPill>("ALL")
  const [extracting, setExtracting] = useState<Record<string, JobProgress>>({})
  const [embedding, setEmbedding] = useState<Record<string, JobProgress>>({})

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

  // Poll a set of job ids (one source's chunk jobs for one job type) until
  // every one reaches a terminal status. Used both for a job just triggered
  // by a button click, and for jobs discovered already in flight on mount —
  // so progress survives a page refresh or a job started elsewhere (e.g.
  // extraction auto-enqueued after ingestion).
  const watchJobs = useCallback(async (sourceId: string, jobType: JobType, jobIds: string[]) => {
    const setProgress = jobType === "extract_claims" ? setExtracting : setEmbedding
    setProgress((current) => ({
      ...current,
      [sourceId]: { jobIds, itemsCompleted: null, itemsTotal: null },
    }))
    try {
      let active = true
      while (active) {
        await new Promise((resolve) => window.setTimeout(resolve, 1200))
        const jobs = await Promise.all(jobIds.map((jobId) => getJob(jobId)))
        if (jobs.every((job) => TERMINAL_JOB_STATUSES.has(job.status))) {
          active = false
          await refreshSources()
          const failed = jobs.find((job) => job.status === "failed")
          if (failed) {
            setError(
              failed.error ??
                (jobType === "extract_claims" ? "Claim extraction failed" : "Claim embedding failed")
            )
          }
        } else {
          setProgress((current) => ({
            ...current,
            [sourceId]: { jobIds, ...sumJobProgress(jobs) },
          }))
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Job polling failed")
    } finally {
      setProgress((current) => {
        const next = { ...current }
        delete next[sourceId]
        return next
      })
    }
  }, [])

  // On load, resume watching any extraction/embedding jobs already in
  // flight for this user — without this, progress is only ever visible to
  // whoever's browser tab triggered the job, and only until they navigate
  // away or refresh.
  useEffect(() => {
    let cancelled = false
    async function hydrateActiveJobs() {
      const activeByStatus = await Promise.all(
        ACTIVE_JOB_STATUSES.map((status) => listJobs({ status, limit: 200 }))
      )
      if (cancelled) return
      const bySourceAndType = new Map<string, Map<JobType, string[]>>()
      for (const job of activeByStatus.flat()) {
        if (job.sourceId === null) continue
        if (job.jobType !== "extract_claims" && job.jobType !== "embed_claims") continue
        const byType = bySourceAndType.get(job.sourceId) ?? new Map<JobType, string[]>()
        byType.set(job.jobType, [...(byType.get(job.jobType) ?? []), job.id])
        bySourceAndType.set(job.sourceId, byType)
      }
      for (const [sourceId, byType] of bySourceAndType) {
        for (const [jobType, jobIds] of byType) {
          void watchJobs(sourceId, jobType, jobIds)
        }
      }
    }
    hydrateActiveJobs().catch((err: unknown) => {
      if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load active jobs")
    })
    return () => {
      cancelled = true
    }
  }, [watchJobs])

  async function startExtraction(source: Source) {
    setError(null)
    try {
      const result = await extractClaims(source.id, source.claimCount > 0)
      void watchJobs(source.id, "extract_claims", result.jobIds)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Claim extraction failed")
    }
  }

  async function startEmbedding(source: Source) {
    setError(null)
    try {
      const result = await embedClaims(source.id)
      void watchJobs(source.id, "embed_claims", [result.jobId])
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Claim embedding failed")
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
                embedItemsCompleted={embedding[source.id]?.itemsCompleted ?? null}
                embedItemsTotal={embedding[source.id]?.itemsTotal ?? null}
                isEmbedding={Boolean(embedding[source.id])}
                isExtracting={Boolean(extracting[source.id])}
                itemsCompleted={extracting[source.id]?.itemsCompleted ?? null}
                itemsTotal={extracting[source.id]?.itemsTotal ?? null}
                key={source.id}
                onDelete={deleteSource}
                onEmbed={startEmbedding}
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
