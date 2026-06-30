"use client"

import { useEffect, useMemo, useState } from "react"
import { listClaims } from "@/lib/api"
import type { Claim } from "@/lib/types"
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

export default function ClaimsPage() {
  const [claims, setClaims] = useState<Claim[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [claimType, setClaimType] = useState("ALL")
  const [query, setQuery] = useState("")

  useEffect(() => {
    let cancelled = false
    listClaims({ limit: 100 })
      .then((data) => {
        if (!cancelled) setClaims(data)
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

  const isLoading = claims === null && error === null
  const filtered = useMemo(() => {
    if (!claims) return []
    const needle = query.trim().toLowerCase()
    return claims.filter((claim) => {
      const matchesType = claimType === "ALL" || claim.claimType === claimType
      const matchesQuery = needle === "" || claim.claimText.toLowerCase().includes(needle)
      return matchesType && matchesQuery
    })
  }, [claims, claimType, query])

  return (
    <div className="space-y-6 p-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-baseline gap-3">
          <h1 className="font-heading text-2xl font-medium text-dust">Claims</h1>
          {claims !== null && (
            <span className="rounded-meridian border border-whisper bg-chamber px-2 py-0.5 font-mono text-xs text-ember">
              {claims.length}
            </span>
          )}
        </div>
        <input
          aria-label="Filter claims"
          className="w-full rounded-hearth border border-whisper bg-archive px-3 py-2 text-sm text-dust outline-none transition-colors placeholder:text-ash focus:border-ash sm:w-72"
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
                ? "rounded-meridian bg-ember px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-archive transition-colors"
                : "rounded-meridian px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-ash transition-colors hover:text-dust"
            }
            key={item}
            onClick={() => setClaimType(item)}
            type="button"
          >
            {item === "ALL" ? "All" : item}
          </button>
        ))}
      </div>

      {error !== null && (
        <div
          role="alert"
          className="rounded-hearth border border-whisper bg-chamber px-6 py-4 text-sm text-ash"
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
        <div className="divide-y divide-whisper border-y border-whisper">
          {filtered.map((claim) => (
            <article className="grid gap-3 py-4 md:grid-cols-[1fr_160px_120px]" key={claim.id}>
              <p className="text-sm leading-6 text-dust">{claim.claimText}</p>
              <div>
                <Badge className="font-mono uppercase">{claim.claimType}</Badge>
              </div>
              <div className="font-mono text-xs text-ash">
                {Math.round(claim.confidence * 100)}% / {claim.status}
              </div>
            </article>
          ))}
          {filtered.length === 0 && error === null ? (
            <p className="py-8 text-sm text-ash">No claims match this filter.</p>
          ) : null}
        </div>
      )}
    </div>
  )
}
