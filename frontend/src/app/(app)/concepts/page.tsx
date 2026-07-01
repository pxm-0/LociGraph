"use client"

import { useEffect, useState } from "react"
import { listConcepts } from "@/lib/api"
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

function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, i) => (
        <tr key={i} className="border-t border-whisper">
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
  const [error, setError] = useState<string | null>(null)
  const [conceptType, setConceptType] = useState("ALL")

  useEffect(() => {
    let cancelled = false
    listConcepts({ limit: 100 })
      .then((data) => {
        if (!cancelled) setConcepts(data)
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

  const isLoading = concepts === null && error === null
  const filtered = concepts
    ? concepts.filter((c) => conceptType === "ALL" || c.conceptType === conceptType)
    : []

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-baseline gap-3">
        <h1 className="font-heading text-2xl font-medium text-dust">Concepts</h1>
        {concepts !== null && (
          <span className="rounded-meridian border border-whisper bg-chamber px-2 py-0.5 font-mono text-xs text-ember">
            {concepts.length}
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by concept type">
        {CONCEPT_TYPES.map((item) => (
          <button
            aria-pressed={conceptType === item}
            className={
              conceptType === item
                ? "rounded-meridian bg-ember px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-archive transition-colors"
                : "rounded-meridian px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-ash transition-colors hover:text-dust"
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
          className="rounded-hearth border border-whisper bg-chamber px-6 py-4 text-sm text-ash"
        >
          Could not load concepts: {error}
        </div>
      )}

      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-whisper">
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-ash">
              Name
            </th>
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-ash">
              Type
            </th>
            <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-ash">
              Claims
            </th>
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            <SkeletonRows />
          ) : (
            filtered.map((concept) => (
              <tr className="border-t border-whisper transition-colors hover:bg-chamber-hover" key={concept.id}>
                <td className="px-5 py-3 font-heading text-dust">{concept.conceptName}</td>
                <td className="px-5 py-3">
                  <Badge className="font-mono text-xs uppercase">{concept.conceptType}</Badge>
                </td>
                <td className="px-5 py-3 font-mono text-xs text-ash">{concept.claimCount}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      {!isLoading && error === null && filtered.length === 0 && (
        <p className="px-5 text-sm text-ash">No concepts match this filter.</p>
      )}
    </div>
  )
}
