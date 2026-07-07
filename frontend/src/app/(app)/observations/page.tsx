"use client"

import { useEffect, useState, useCallback } from "react"
import { getObservationsCount, listObservations } from "@/lib/api"
import type { Observation } from "@/lib/types"
import { ObservationCard } from "@/components/domain/ObservationCard"
import { Skeleton } from "@/components/ui/Skeleton"

const STATUS_OPTIONS = ["", "VERIFIED", "PENDING", "INGESTING", "QUARANTINED"] as const
const PAGE_SIZE = 100

function SkeletonCards() {
  return (
    <div className="space-y-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-28 w-full rounded-hearth" />
      ))}
    </div>
  )
}

export default function ObservationsPage() {
  const [observations, setObservations] = useState<Observation[] | null>(null)
  const [total, setTotal] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)

  // Filter field state (uncommitted until Apply)
  const [sourceInput, setSourceInput] = useState("")
  const [speakerInput, setSpeakerInput] = useState("")
  const [statusInput, setStatusInput] = useState("")

  // Committed filter state used for the actual API call
  const [activeSource, setActiveSource] = useState("")
  const [activeSpeaker, setActiveSpeaker] = useState("")
  const [activeStatus, setActiveStatus] = useState("")

  const fetchObservations = useCallback(
    (src: string, spk: string, sts: string) => {
      setObservations(null)
      setTotal(null)
      setError(null)
      let cancelled = false
      const filters = {
        ...(src ? { sourceId: src } : {}),
        ...(spk ? { speaker: spk } : {}),
        ...(sts ? { status: sts } : {}),
      }

      Promise.all([
        listObservations({ ...filters, limit: PAGE_SIZE, offset: 0 }),
        getObservationsCount(filters),
      ])
        .then(([data, count]) => {
          if (!cancelled) {
            setObservations(data)
            setTotal(count)
          }
        })
        .catch((err: unknown) => {
          if (!cancelled) {
            setError(err instanceof Error ? err.message : "Failed to load observations")
          }
        })

      return () => {
        cancelled = true
      }
    },
    [],
  )

  useEffect(() => {
    const cancel = fetchObservations(activeSource, activeSpeaker, activeStatus)
    return cancel
  }, [activeSource, activeSpeaker, activeStatus, fetchObservations])

  const hasMore = observations !== null && total !== null && observations.length < total

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore || observations === null) return
    setLoadingMore(true)
    try {
      const data = await listObservations({
        ...(activeSource ? { sourceId: activeSource } : {}),
        ...(activeSpeaker ? { speaker: activeSpeaker } : {}),
        ...(activeStatus ? { status: activeStatus } : {}),
        limit: PAGE_SIZE,
        offset: observations.length,
      })
      setObservations((prev) => [...(prev ?? []), ...data])
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load observations")
    } finally {
      setLoadingMore(false)
    }
  }, [activeSource, activeSpeaker, activeStatus, hasMore, loadingMore, observations])

  function handleApply(e: React.FormEvent) {
    e.preventDefault()
    setActiveSource(sourceInput)
    setActiveSpeaker(speakerInput)
    setActiveStatus(statusInput)
  }

  const isLoading = observations === null && error === null

  return (
    <div className="space-y-6 p-8">
      {/* Page heading */}
      <div className="flex items-baseline gap-3">
        <h1 className="font-heading text-2xl font-medium text-ink">Observations</h1>
        {observations !== null && total !== null && (
          <span className="rounded-meridian border border-hairline bg-surface px-2 py-0.5 font-mono text-xs text-accent">
            {observations.length < total ? `${observations.length} of ${total}` : total}
          </span>
        )}
      </div>

      {/* Filter bar */}
      <form
        onSubmit={handleApply}
        className="flex flex-wrap items-end gap-4 rounded-hearth border border-hairline bg-surface p-4"
      >
        <div className="flex flex-col gap-1">
          <label className="font-mono text-[11px] uppercase tracking-widest text-muted">
            Source
          </label>
          <input
            type="text"
            value={sourceInput}
            onChange={(e) => setSourceInput(e.target.value)}
            placeholder="Source ID"
            className="rounded-meridian border border-hairline bg-canvas px-3 py-1.5 font-ui text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="font-mono text-[11px] uppercase tracking-widest text-muted">
            Speaker
          </label>
          <input
            type="text"
            value={speakerInput}
            onChange={(e) => setSpeakerInput(e.target.value)}
            placeholder="Speaker"
            className="rounded-meridian border border-hairline bg-canvas px-3 py-1.5 font-ui text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="font-mono text-[11px] uppercase tracking-widest text-muted">
            Status
          </label>
          <select
            value={statusInput}
            onChange={(e) => setStatusInput(e.target.value)}
            className="rounded-meridian border border-hairline bg-canvas px-3 py-1.5 font-ui text-sm text-ink focus:border-accent focus:outline-none"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s === "" ? "All" : s.charAt(0) + s.slice(1).toLowerCase()}
              </option>
            ))}
          </select>
        </div>

        <button
          type="submit"
          className="rounded-meridian bg-ember px-4 py-1.5 font-mono text-xs uppercase tracking-widest text-void transition-colors hover:opacity-90"
        >
          Apply
        </button>
      </form>

      {/* Error */}
      {error !== null && (
        <div
          role="alert"
          className="rounded-hearth border border-hairline bg-surface px-6 py-4 text-sm text-muted"
        >
          Could not load observations: {error}
        </div>
      )}

      {/* Loading */}
      {isLoading && <SkeletonCards />}

      {/* Observations list */}
      {!isLoading && error === null && observations !== null && (
        <>
          {observations.length === 0 ? (
            <p className="px-5 text-sm text-muted">No observations match this filter.</p>
          ) : (
            <div className="space-y-4">
              {observations.map((obs) => (
                <ObservationCard
                  key={obs.id}
                  observation={obs}
                  selected={selectedId === obs.id}
                  onClick={() => setSelectedId((prev) => (prev === obs.id ? null : obs.id))}
                />
              ))}
            </div>
          )}
          {hasMore && (
            <button
              className="rounded-meridian bg-ember px-4 py-1.5 font-mono text-xs uppercase tracking-widest text-void transition-colors hover:opacity-90 disabled:opacity-50"
              disabled={loadingMore}
              onClick={loadMore}
              type="button"
            >
              {loadingMore ? "Loading…" : "Load more"}
            </button>
          )}
        </>
      )}
    </div>
  )
}
