"use client"

import { useEffect, useState } from "react"
import { getConceptsCount, listConcepts } from "@/lib/api"
import type { Concept } from "@/lib/types"
import { Badge } from "@/components/ui/Badge"
import { Skeleton } from "@/components/ui/Skeleton"

const CONCEPT_TYPES = [
  "ALL",
  "idea",
  "person",
  "place",
  "object",
  "event",
  "system",
  "value",
  "belief",
  "theme",
  "project",
] as const

const PAGE_SIZE = 100

function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, i) => (
        <tr key={i} className="border-t border-hairline">
          <td className="px-5 py-3" colSpan={3}>
            <Skeleton className="h-5 w-full" />
          </td>
        </tr>
      ))}
    </>
  )
}

export default function ConceptsPage() {
  const [concepts, setConcepts] = useState<Concept[] | null>(null)
  const [total, setTotal] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [conceptType, setConceptType] = useState("ALL")
  const [loadingMore, setLoadingMore] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([listConcepts({ limit: PAGE_SIZE, offset: 0 }), getConceptsCount()])
      .then(([data, count]) => {
        if (!cancelled) {
          setConcepts(data)
          setTotal(count)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load concepts")
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const hasMore = concepts !== null && total !== null && concepts.length < total

  async function loadMore() {
    if (loadingMore || !hasMore || concepts === null) return
    setLoadingMore(true)
    try {
      const data = await listConcepts({ limit: PAGE_SIZE, offset: concepts.length })
      setConcepts((prev) => [...(prev ?? []), ...data])
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load concepts")
    } finally {
      setLoadingMore(false)
    }
  }

  const isLoading = concepts === null && error === null
  const filtered = concepts
    ? concepts.filter((c) => conceptType === "ALL" || c.conceptType === conceptType)
    : []

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-baseline gap-3">
        <h1 className="font-heading text-2xl font-medium text-ink">Concepts</h1>
        {concepts !== null && total !== null && (
          <span className="rounded-meridian border border-hairline bg-surface px-2 py-0.5 font-mono text-xs text-accent">
            {concepts.length < total ? `${concepts.length} of ${total}` : total}
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by concept type">
        {CONCEPT_TYPES.map((item) => (
          <button
            aria-pressed={conceptType === item}
            className={
              conceptType === item
                ? "rounded-meridian bg-ember px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-void transition-colors"
                : "rounded-meridian px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-muted transition-colors hover:text-ink"
            }
            key={item}
            onClick={() => setConceptType(item)}
            type="button"
          >
            {item === "ALL" ? "All" : item}
          </button>
        ))}
      </div>

      {error !== null && (
        <div
          role="alert"
          className="rounded-hearth border border-hairline bg-surface px-6 py-4 text-sm text-muted"
        >
          Could not load concepts: {error}
        </div>
      )}

      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-hairline">
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-muted">
              Name
            </th>
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-muted">
              Type
            </th>
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-muted">
              Claims
            </th>
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            <SkeletonRows />
          ) : (
            filtered.map((concept) => (
              <tr className="border-t border-hairline transition-colors hover:bg-surface-hover" key={concept.id}>
                <td className="px-5 py-3 font-heading text-ink">{concept.conceptName}</td>
                <td className="px-5 py-3">
                  <Badge className="font-mono text-xs uppercase">{concept.conceptType}</Badge>
                </td>
                <td className="px-5 py-3 font-mono text-xs text-muted">{concept.claimCount}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      {!isLoading && error === null && filtered.length === 0 && (
        <p className="px-5 text-sm text-muted">No concepts match this filter.</p>
      )}

      {hasMore && error === null && (
        <button
          className="rounded-meridian bg-ember px-4 py-1.5 font-mono text-xs uppercase tracking-widest text-void transition-colors hover:opacity-90 disabled:opacity-50"
          disabled={loadingMore}
          onClick={loadMore}
          type="button"
        >
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  )
}
