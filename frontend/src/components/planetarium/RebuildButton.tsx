"use client"

import { useCallback, useState } from "react"
import { getJob, rebuildPlanetarium } from "@/lib/api"

const TERMINAL_JOB_STATUSES = new Set(["completed", "failed"])
const POLL_INTERVAL_MS = 1200

interface RebuildButtonProps {
  onRebuildComplete: () => void
}

export function RebuildButton({ onRebuildComplete }: RebuildButtonProps) {
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const watchJob = useCallback(
    async (jobId: string) => {
      let active = true
      while (active) {
        await new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS))
        const job = await getJob(jobId)
        if (TERMINAL_JOB_STATUSES.has(job.status)) {
          active = false
          if (job.status === "failed") {
            setError(job.error ?? "Planetarium rebuild failed")
          } else {
            onRebuildComplete()
          }
        }
      }
    },
    [onRebuildComplete]
  )

  async function startRebuild() {
    setError(null)
    setIsRunning(true)
    try {
      const result = await rebuildPlanetarium()
      await watchJob(result.jobId)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to trigger rebuild")
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <div className="space-y-2">
      <button
        onClick={startRebuild}
        disabled={isRunning}
        className="rounded-hearth border border-hairline bg-surface px-4 py-2 text-sm text-ink hover:bg-surface-hover disabled:opacity-50"
      >
        {isRunning ? "Rebuilding…" : "Rebuild Planetarium"}
      </button>
      {error !== null && (
        <div
          role="alert"
          className="rounded-hearth border border-hairline bg-surface px-4 py-2 text-sm text-muted"
        >
          {error}
        </div>
      )}
    </div>
  )
}
