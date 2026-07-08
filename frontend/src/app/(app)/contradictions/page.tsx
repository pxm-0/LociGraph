"use client"

import { useEffect, useMemo, useState } from "react"
import { classifyContradiction, getContradictionsCount, listContradictions } from "@/lib/api"
import type { Contradiction } from "@/lib/types"
import { Badge } from "@/components/ui/Badge"
import { Skeleton } from "@/components/ui/Skeleton"

const CLASSIFICATIONS = [
  "ALL",
  "unresolved",
  "true_conflict",
  "evolution",
  "contextual_difference",
  "both",
] as const

const CLASSIFY_ACTIONS = ["true_conflict", "evolution", "contextual_difference", "both"] as const

const PAGE_SIZE = 100

export default function ContradictionsPage() {
  const [contradictions, setContradictions] = useState<Contradiction[] | null>(null)
  const [total, setTotal] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [classification, setClassification] = useState("ALL")
  const [loadingMore, setLoadingMore] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([listContradictions({ limit: PAGE_SIZE, offset: 0 }), getContradictionsCount()])
      .then(([data, count]) => {
        if (!cancelled) {
          setContradictions(data)
          setTotal(count)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load contradictions")
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const hasMore = contradictions !== null && total !== null && contradictions.length < total

  async function loadMore() {
    if (loadingMore || !hasMore || contradictions === null) return
    setLoadingMore(true)
    try {
      const data = await listContradictions({ limit: PAGE_SIZE, offset: contradictions.length })
      setContradictions((prev) => [...(prev ?? []), ...data])
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load contradictions")
    } finally {
      setLoadingMore(false)
    }
  }

  async function handleClassify(id: string, value: string) {
    try {
      const updated = await classifyContradiction(id, value)
      setContradictions((prev) => (prev ?? []).map((c) => (c.id === id ? updated : c)))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to classify contradiction")
    }
  }

  const isLoading = contradictions === null && error === null
  const filtered = useMemo(() => {
    if (!contradictions) return []
    return contradictions.filter(
      (c) => classification === "ALL" || c.classification === classification
    )
  }, [contradictions, classification])

  return (
    <div className="space-y-6 p-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-baseline gap-3">
          <h1 className="font-heading text-2xl font-medium text-ink">Contradictions</h1>
          {contradictions !== null && total !== null && (
            <span className="rounded-meridian border border-hairline bg-surface px-2 py-0.5 font-mono text-xs text-accent">
              {contradictions.length < total ? `${contradictions.length} of ${total}` : total}
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by classification">
        {CLASSIFICATIONS.map((item) => (
          <button
            aria-pressed={classification === item}
            className={
              classification === item
                ? "rounded-meridian bg-ember px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-void transition-colors"
                : "rounded-meridian px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-muted transition-colors hover:text-ink"
            }
            key={item}
            onClick={() => setClassification(item)}
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
          Could not load contradictions: {error}
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton className="h-24" key={index} />
          ))}
        </div>
      ) : (
        <div className="divide-y divide-hairline border-y border-hairline">
          {filtered.map((c) => (
            <article className="space-y-3 py-4" key={c.id}>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-1">
                  <p className="text-sm leading-6 text-ink">{c.claimA.claimText}</p>
                  <Badge className="font-mono uppercase">{c.claimA.assertionType}</Badge>
                </div>
                <div className="space-y-1">
                  <p className="text-sm leading-6 text-ink">{c.claimB.claimText}</p>
                  <Badge className="font-mono uppercase">{c.claimB.assertionType}</Badge>
                </div>
              </div>
              <p className="text-sm text-muted">{c.rationale}</p>
              <div className="flex flex-wrap items-center gap-2">
                <Badge className="font-mono uppercase">{c.classification}</Badge>
                {c.classification === "unresolved" &&
                  CLASSIFY_ACTIONS.map((action) => (
                    <button
                      className="rounded-meridian border border-hairline px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-muted transition-colors hover:text-ink"
                      key={action}
                      onClick={() => handleClassify(c.id, action)}
                      type="button"
                    >
                      {action}
                    </button>
                  ))}
              </div>
            </article>
          ))}
          {filtered.length === 0 && error === null ? (
            <p className="py-8 text-sm text-muted">No contradictions match this filter.</p>
          ) : null}
        </div>
      )}

      {hasMore && contradictions !== null && error === null && (
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
