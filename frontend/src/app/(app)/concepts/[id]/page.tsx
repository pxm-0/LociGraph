"use client"

import { useEffect, useState } from "react"
import {
  createConceptRevision,
  getConcept,
  getConceptClaims,
  getConceptRevisions,
} from "@/lib/api"
import type { Claim, Concept, Revision } from "@/lib/types"
import { Badge } from "@/components/ui/Badge"
import { Skeleton } from "@/components/ui/Skeleton"

export default function ConceptDetailPage({ params }: { params: { id: string } }) {
  const conceptId = params.id
  const [concept, setConcept] = useState<Concept | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [claims, setClaims] = useState<Claim[] | null>(null)
  const [revisions, setRevisions] = useState<Revision[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [newDescription, setNewDescription] = useState("")
  const [rationale, setRationale] = useState("")
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let cancelled = false
    getConcept(conceptId)
      .then((data) => {
        if (cancelled) return
        if (data === null) {
          setNotFound(true)
          return
        }
        setConcept(data)
        return Promise.all([getConceptClaims(conceptId), getConceptRevisions(conceptId)]).then(
          ([claimsData, revisionsData]) => {
            if (!cancelled) {
              setClaims(claimsData)
              setRevisions(revisionsData)
            }
          }
        )
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load concept")
        }
      })
    return () => {
      cancelled = true
    }
  }, [conceptId])

  async function handleSubmitRevision() {
    if (!newDescription.trim() || submitting) return
    setSubmitting(true)
    try {
      const revision = await createConceptRevision(
        conceptId,
        newDescription.trim(),
        rationale.trim() || undefined
      )
      setRevisions((prev) => [revision, ...(prev ?? [])])
      setConcept((prev) => (prev ? { ...prev, description: revision.newDescription } : prev))
      setNewDescription("")
      setRationale("")
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create revision")
    } finally {
      setSubmitting(false)
    }
  }

  if (notFound) {
    return (
      <div className="space-y-6 p-8">
        <p className="text-sm text-muted">Concept not found.</p>
      </div>
    )
  }

  if (concept === null) {
    return (
      <div className="space-y-6 p-8">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24" />
      </div>
    )
  }

  return (
    <div className="space-y-8 p-8">
      <div className="space-y-2">
        <div className="flex items-baseline gap-3">
          <h1 className="font-heading text-2xl font-medium text-ink">{concept.conceptName}</h1>
          <Badge className="font-mono uppercase">{concept.conceptType}</Badge>
        </div>
        <p className="text-sm leading-6 text-ink">
          {concept.description ?? "No description yet."}
        </p>
      </div>

      {error !== null && (
        <div
          role="alert"
          className="rounded-hearth border border-hairline bg-surface px-6 py-4 text-sm text-muted"
        >
          {error}
        </div>
      )}

      <section className="space-y-3">
        <h2 className="font-heading text-lg text-ink">Write a revision</h2>
        <textarea
          aria-label="New description"
          className="w-full rounded-hearth border border-hairline bg-canvas px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-muted focus:border-accent"
          onChange={(event) => setNewDescription(event.target.value)}
          placeholder="Write the updated understanding of this concept"
          rows={3}
          value={newDescription}
        />
        <input
          aria-label="Rationale (optional)"
          className="w-full rounded-hearth border border-hairline bg-canvas px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-muted focus:border-accent"
          onChange={(event) => setRationale(event.target.value)}
          placeholder="Rationale (optional)"
          value={rationale}
        />
        <button
          className="rounded-meridian bg-ember px-4 py-1.5 font-mono text-xs uppercase tracking-widest text-void transition-colors hover:opacity-90 disabled:opacity-50"
          disabled={submitting || !newDescription.trim()}
          onClick={handleSubmitRevision}
          type="button"
        >
          {submitting ? "Saving…" : "Save revision"}
        </button>
      </section>

      <section className="space-y-3">
        <h2 className="font-heading text-lg text-ink">Claims</h2>
        <div className="divide-y divide-hairline border-y border-hairline">
          {(claims ?? []).map((claim) => (
            <article className="grid gap-3 py-4 md:grid-cols-[1fr_160px]" key={claim.id}>
              <p className="text-sm leading-6 text-ink">{claim.claimText}</p>
              <div className="flex flex-wrap gap-1">
                <Badge className="font-mono uppercase">{claim.claimType}</Badge>
                <Badge className="font-mono uppercase">{claim.assertionType}</Badge>
              </div>
            </article>
          ))}
          {claims !== null && claims.length === 0 ? (
            <p className="py-8 text-sm text-muted">No claims linked yet.</p>
          ) : null}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="font-heading text-lg text-ink">Revision history</h2>
        <div className="divide-y divide-hairline border-y border-hairline">
          {(revisions ?? []).map((revision) => (
            <article className="space-y-1 py-4" key={revision.id}>
              <div className="flex items-center gap-2">
                <Badge className="font-mono uppercase">{revision.source}</Badge>
                <span className="font-mono text-xs text-muted">{revision.createdAt}</span>
              </div>
              <p className="text-sm leading-6 text-muted line-through">
                {revision.previousDescription ?? "(no prior description)"}
              </p>
              <p className="text-sm leading-6 text-ink">{revision.newDescription}</p>
              {revision.rationale ? (
                <p className="text-sm text-muted">{revision.rationale}</p>
              ) : null}
            </article>
          ))}
          {revisions !== null && revisions.length === 0 ? (
            <p className="py-8 text-sm text-muted">No revisions yet.</p>
          ) : null}
        </div>
      </section>
    </div>
  )
}
