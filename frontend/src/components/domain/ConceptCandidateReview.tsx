"use client"

import { useEffect, useState } from "react"
import { approveConceptCandidate, listConceptCandidates, rejectConceptCandidate } from "@/lib/api"
import type { ConceptCandidate } from "@/lib/types"
import { Badge } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Button"
import { Skeleton } from "@/components/ui/Skeleton"

export function ConceptCandidateReview() {
  const [candidates, setCandidates] = useState<ConceptCandidate[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState<Record<string, boolean>>({})

  async function refresh() {
    await listConceptCandidates({ status: "proposed" })
      .then((data) => setCandidates(data))
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load concept candidates")
      })
  }

  useEffect(() => {
    let cancelled = false
    listConceptCandidates({ status: "proposed" })
      .then((data) => {
        if (!cancelled) setCandidates(data)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load concept candidates")
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleApprove(candidate: ConceptCandidate) {
    setError(null)
    setSubmitting((current) => ({ ...current, [candidate.id]: true }))
    try {
      await approveConceptCandidate(candidate.id)
      await refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to approve candidate")
    } finally {
      setSubmitting((current) => {
        const next = { ...current }
        delete next[candidate.id]
        return next
      })
    }
  }

  async function handleReject(candidate: ConceptCandidate) {
    setError(null)
    setSubmitting((current) => ({ ...current, [candidate.id]: true }))
    try {
      await rejectConceptCandidate(candidate.id)
      await refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to reject candidate")
    } finally {
      setSubmitting((current) => {
        const next = { ...current }
        delete next[candidate.id]
        return next
      })
    }
  }

  const isLoading = candidates === null && error === null

  return (
    <section className="space-y-4">
      <div className="flex items-baseline gap-3">
        <h2 className="font-heading text-xl font-medium text-ink">Review</h2>
        {candidates !== null && (
          <span className="rounded-meridian border border-hairline bg-surface px-2 py-0.5 font-mono text-xs text-accent">
            {candidates.length}
          </span>
        )}
      </div>

      {error !== null && (
        <div
          role="alert"
          className="rounded-hearth border border-hairline bg-surface px-6 py-4 text-sm text-muted"
        >
          Could not process concept candidate: {error}
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton className="h-16" key={index} />
          ))}
        </div>
      ) : (
        <div className="divide-y divide-hairline border-y border-hairline">
          {candidates?.map((candidate) => (
            <article
              className="grid gap-3 py-4 md:grid-cols-[1fr_140px_180px]"
              key={candidate.id}
            >
              <div>
                <p className="text-sm leading-6 text-ink">{candidate.candidateName}</p>
                {candidate.rationale && (
                  <p className="mt-1 text-xs text-muted">{candidate.rationale}</p>
                )}
              </div>
              <div>
                <Badge className="font-mono uppercase">{candidate.conceptType}</Badge>
              </div>
              <div className="flex items-center justify-end gap-2">
                <Button
                  className="px-3 py-1.5 font-mono text-[11px] uppercase"
                  disabled={Boolean(submitting[candidate.id])}
                  onClick={() => handleApprove(candidate)}
                  type="button"
                  variant="primary"
                >
                  {submitting[candidate.id] ? "Working" : "Approve"}
                </Button>
                <Button
                  className="px-3 py-1.5 font-mono text-[11px] uppercase"
                  disabled={Boolean(submitting[candidate.id])}
                  onClick={() => handleReject(candidate)}
                  type="button"
                  variant="ghost"
                >
                  {submitting[candidate.id] ? "Working" : "Reject"}
                </Button>
              </div>
            </article>
          ))}
          {candidates?.length === 0 && error === null ? (
            <p className="py-8 text-sm text-muted">No concept candidates awaiting review.</p>
          ) : null}
        </div>
      )}
    </section>
  )
}
