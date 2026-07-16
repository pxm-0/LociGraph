"use client"

import { useEffect, useState } from "react"
import { getPlanetariumNodeDetail } from "@/lib/api"
import type { PlanetariumNodeDetail } from "@/lib/types"
import { describeNode } from "./describeNode"

export function buildConceptHref(conceptId: string): string {
  return `/concepts/${conceptId}`
}

interface ConceptDetailPanelProps {
  conceptId: string
  onClose: () => void
}

export function ConceptDetailPanel({ conceptId, onClose }: ConceptDetailPanelProps) {
  const [detail, setDetail] = useState<PlanetariumNodeDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setDetail(null)
    setError(null)
    getPlanetariumNodeDetail(conceptId)
      .then(setDetail)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load concept detail")
      })
  }, [conceptId])

  return (
    <div className="fixed right-6 top-24 z-50 w-80 rounded-hearth border border-hairline bg-surface p-4 shadow-lg">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-heading text-sm text-ink">
          {detail ? detail.conceptName : "Concept"}
        </span>
        <button onClick={onClose} aria-label="Close" className="text-xs font-ui text-muted hover:text-ink">
          Close
        </button>
      </div>

      {error !== null && (
        <p role="alert" className="text-xs text-muted">
          {error}
        </p>
      )}

      {error === null && detail === null && <p className="text-xs text-muted">Loading…</p>}

      {detail !== null && (
        <div className="space-y-2 text-xs text-muted">
          <p className="text-ink">{detail.conceptType}</p>
          <p>{describeNode(detail)}</p>
          <p>
            {detail.revisionCount} revisions, {detail.edgeCount} edges,{" "}
            {detail.contradictionCount} contradictions, {detail.pinCount} pins.
          </p>
          <p>
            {detail.isEmbedded
              ? "Positioned by content similarity to other concepts."
              : "No content yet — not semantically positioned, placed arbitrarily to avoid overlap."}
          </p>
          <a
            href={buildConceptHref(detail.conceptId)}
            className="inline-block font-ui text-ink underline hover:text-muted"
          >
            View full concept →
          </a>
        </div>
      )}
    </div>
  )
}
