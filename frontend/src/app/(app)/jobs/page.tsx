"use client"

import { useEffect, useState } from "react"
import { listJobs, listSources } from "@/lib/api"
import type { Job, Source } from "@/lib/types"

const ACTIVE_STATUSES = new Set(["pending", "running"])
const RECENT_TERMINAL_PER_SOURCE = 5
const REFRESH_INTERVAL_MS = 3000
const CLUSTER_SIZE = 200
const HUB_RADIUS = 26
const SATELLITE_RADIUS = 9
const ORBIT_RADIUS = 68

const STATUS_FILL_CLASS: Record<string, string> = {
  pending: "fill-muted",
  running: "fill-status-ingesting",
  completed: "fill-status-verified",
  failed: "fill-status-failed",
}

interface SourceCluster {
  source: Source | null
  sourceId: string
  jobs: Job[]
  hiddenTerminalCount: number
}

// Group jobs by source, keep every active (pending/running) job — that's
// what "watching" means — and cap terminal (completed/failed) jobs per
// source so one source's long history doesn't crowd out everyone else's.
function buildClusters(sources: Source[], jobs: Job[]): SourceCluster[] {
  const sourceById = new Map(sources.map((s) => [s.id, s]))
  const bySource = new Map<string, Job[]>()
  for (const job of jobs) {
    if (job.sourceId === null) continue
    const list = bySource.get(job.sourceId) ?? []
    list.push(job)
    bySource.set(job.sourceId, list)
  }

  const clusters: SourceCluster[] = []
  for (const [sourceId, sourceJobs] of bySource) {
    const active = sourceJobs.filter((j) => ACTIVE_STATUSES.has(j.status))
    const terminal = sourceJobs
      .filter((j) => !ACTIVE_STATUSES.has(j.status))
      .sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? ""))
    const visibleTerminal = terminal.slice(0, RECENT_TERMINAL_PER_SOURCE)
    clusters.push({
      source: sourceById.get(sourceId) ?? null,
      sourceId,
      jobs: [...active, ...visibleTerminal],
      hiddenTerminalCount: terminal.length - visibleTerminal.length,
    })
  }
  return clusters.sort((a, b) => b.jobs.length - a.jobs.length)
}

function jobTooltip(job: Job): string {
  const parts = [job.jobType, job.status]
  if (job.itemsTotal != null) parts.push(`${job.itemsCompleted ?? 0}/${job.itemsTotal}`)
  if (job.error) parts.push(job.error)
  return parts.join(" · ")
}

function SourceClusterGraph({ cluster }: { cluster: SourceCluster }) {
  const { jobs } = cluster
  const cx = CLUSTER_SIZE / 2
  const cy = CLUSTER_SIZE / 2
  const label = cluster.source?.originalFilename ?? `${cluster.sourceId.slice(0, 8)}…`

  return (
    <div className="rounded-hearth border border-hairline bg-surface p-4">
      <svg
        viewBox={`0 0 ${CLUSTER_SIZE} ${CLUSTER_SIZE}`}
        className="w-full"
        role="img"
        aria-label={`Jobs for ${label}`}
      >
        {jobs.map((job, i) => {
          const angle = (2 * Math.PI * i) / jobs.length - Math.PI / 2
          const x = cx + ORBIT_RADIUS * Math.cos(angle)
          const y = cy + ORBIT_RADIUS * Math.sin(angle)
          return (
            <g key={job.id}>
              <line x1={cx} y1={cy} x2={x} y2={y} className="stroke-hairline" strokeWidth={1} />
              <circle
                cx={x}
                cy={y}
                r={SATELLITE_RADIUS}
                className={STATUS_FILL_CLASS[job.status] ?? "fill-muted"}
                data-testid="job-node"
                data-status={job.status}
              >
                <title>{jobTooltip(job)}</title>
              </circle>
            </g>
          )
        })}
        <circle cx={cx} cy={cy} r={HUB_RADIUS} className="fill-surface stroke-accent" strokeWidth={2} />
        <text
          x={cx}
          y={cy}
          textAnchor="middle"
          dominantBaseline="middle"
          className="fill-ink font-mono"
          style={{ fontSize: 9 }}
        >
          {jobs.length}
        </text>
      </svg>
      <p className="mt-2 truncate text-center font-mono text-[11px] text-muted" title={label}>
        {label}
      </p>
      {cluster.hiddenTerminalCount > 0 && (
        <p className="text-center font-mono text-[10px] text-muted">
          +{cluster.hiddenTerminalCount} older
        </p>
      )}
    </div>
  )
}

export default function JobsGraphPage() {
  const [clusters, setClusters] = useState<SourceCluster[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const [sources, pending, running, completed, failed] = await Promise.all([
          listSources(),
          listJobs({ status: "pending", limit: 200 }),
          listJobs({ status: "running", limit: 200 }),
          listJobs({ status: "completed", limit: 100 }),
          listJobs({ status: "failed", limit: 100 }),
        ])
        if (cancelled) return
        setClusters(buildClusters(sources, [...pending, ...running, ...completed, ...failed]))
        setError(null)
      } catch (err: unknown) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load jobs")
      }
    }

    load()
    const interval = window.setInterval(load, REFRESH_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [])

  const isLoading = clusters === null && error === null

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-baseline gap-3">
        <h1 className="font-heading text-2xl font-medium text-ink">Jobs</h1>
        {clusters !== null && (
          <span className="font-mono text-xs text-accent bg-surface border border-hairline rounded-meridian px-2 py-0.5">
            {clusters.length}
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-4 font-mono text-[11px] text-muted" aria-label="Legend">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-muted" /> pending
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-status-ingesting" /> running
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-status-verified" /> completed
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-status-failed" /> failed
        </span>
      </div>

      {error !== null && (
        <div
          role="alert"
          className="rounded-hearth border border-hairline bg-surface px-6 py-4 text-sm text-muted"
        >
          {error}
        </div>
      )}

      {isLoading && <p className="text-sm text-muted">Loading…</p>}

      {!isLoading && clusters !== null && clusters.length === 0 && (
        <p className="text-sm text-muted">No active or recent jobs.</p>
      )}

      {clusters !== null && clusters.length > 0 && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
          {clusters.map((cluster) => (
            <SourceClusterGraph key={cluster.sourceId} cluster={cluster} />
          ))}
        </div>
      )}
    </div>
  )
}
