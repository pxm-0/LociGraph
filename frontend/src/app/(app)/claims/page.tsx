"use client"

import { useEffect, useMemo, useState } from "react"
import { getClaimsCount, listClaims } from "@/lib/api"
import type { Claim } from "@/lib/types"
import { ConceptCandidateReview } from "@/components/domain/ConceptCandidateReview"
import { Badge } from "@/components/ui/Badge"
import { Skeleton } from "@/components/ui/Skeleton"

const CLAIM_TYPES = [
  "ALL",
  "fact",
  "event",
  "belief",
  "preference",
  "definition",
  "relationship",
  "emotion",
  "interpretation",
  "decision",
  "task",
] as const

const ASSERTION_TYPES = ["ALL", "reality", "perception", "interpretation"] as const

const PAGE_SIZE = 100

export default function ClaimsPage() {
  const [claims, setClaims] = useState<Claim[] | null>(null)
  const [total, setTotal] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [claimType, setClaimType] = useState("ALL")
  const [assertionType, setAssertionType] = useState("ALL")
  const [query, setQuery] = useState("")
  const [loadingMore, setLoadingMore] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([listClaims({ limit: PAGE_SIZE, offset: 0 }), getClaimsCount()])
      .then(([data, count]) => {
        if (!cancelled) {
          setClaims(data)
          setTotal(count)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load claims")
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const hasMore = claims !== null && total !== null && claims.length < total

  async function loadMore() {
    if (loadingMore || !hasMore || claims === null) return
    setLoadingMore(true)
    try {
      const data = await listClaims({ limit: PAGE_SIZE, offset: claims.length })
      setClaims((prev) => [...(prev ?? []), ...data])
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load claims")
    } finally {
      setLoadingMore(false)
    }
  }

  const isLoading = claims === null && error === null
  const filtered = useMemo(() => {
    if (!claims) return []
    const needle = query.trim().toLowerCase()
    return claims.filter((claim) => {
      const matchesType = claimType === "ALL" || claim.claimType === claimType
      const matchesAssertion = assertionType === "ALL" || claim.assertionType === assertionType
      const matchesQuery = needle === "" || claim.claimText.toLowerCase().includes(needle)
      return matchesType && matchesAssertion && matchesQuery
    })
  }, [claims, claimType, assertionType, query])

  return (
    <div className="space-y-6 p-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-baseline gap-3">
          <h1 className="font-heading text-2xl font-medium text-ink">Claims</h1>
          {claims !== null && total !== null && (
            <span className="rounded-meridian border border-hairline bg-surface px-2 py-0.5 font-mono text-xs text-accent">
              {claims.length < total ? `${claims.length} of ${total}` : total}
            </span>
          )}
        </div>
        <input
          aria-label="Filter claims"
          className="w-full rounded-hearth border border-hairline bg-canvas px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-muted focus:border-accent sm:w-72"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter claims"
          value={query}
        />
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by claim type">
        {CLAIM_TYPES.map((item) => (
          <button
            aria-pressed={claimType === item}
            className={
              claimType === item
                ? "rounded-meridian bg-ember px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-void transition-colors"
                : "rounded-meridian px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-muted transition-colors hover:text-ink"
            }
            key={item}
            onClick={() => setClaimType(item)}
            type="button"
          >
            {item === "ALL" ? "All" : item}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by assertion type">
        {ASSERTION_TYPES.map((item) => (
          <button
            aria-pressed={assertionType === item}
            className={
              assertionType === item
                ? "rounded-meridian bg-ember px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-void transition-colors"
                : "rounded-meridian px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-muted transition-colors hover:text-ink"
            }
            key={item}
            onClick={() => setAssertionType(item)}
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
          Could not load claims: {error}
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton className="h-16" key={index} />
          ))}
        </div>
      ) : (
        <div className="divide-y divide-hairline border-y border-hairline">
          {filtered.map((claim) => (
            <article className="grid gap-3 py-4 md:grid-cols-[1fr_160px_120px]" key={claim.id}>
              <p className="text-sm leading-6 text-ink">{claim.claimText}</p>
              <div className="flex flex-wrap gap-1">
                <Badge className="font-mono uppercase">{claim.claimType}</Badge>
                <Badge className="font-mono uppercase">{claim.assertionType}</Badge>
              </div>
              <div className="font-mono text-xs text-muted">
                {Math.round(claim.confidence * 100)}% / {claim.status}
              </div>
            </article>
          ))}
          {filtered.length === 0 && error === null ? (
            <p className="py-8 text-sm text-muted">No claims match this filter.</p>
          ) : null}
        </div>
      )}

      {hasMore && claims !== null && error === null && (
        <button
          className="rounded-meridian bg-ember px-4 py-1.5 font-mono text-xs uppercase tracking-widest text-void transition-colors hover:opacity-90 disabled:opacity-50"
          disabled={loadingMore}
          onClick={loadMore}
          type="button"
        >
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}

      <ConceptCandidateReview />
    </div>
  )
}
