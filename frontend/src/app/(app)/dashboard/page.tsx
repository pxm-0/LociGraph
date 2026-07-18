"use client"

import { useEffect, useState } from "react"
import { loadDashboard, type DashboardData } from "@/lib/dashboard"
import { Skeleton } from "@/components/ui/Skeleton"
import { DashboardGrid } from "@/components/dashboard/DashboardGrid"

function DashboardSkeletons() {
  return (
    <div className="space-y-10 p-8">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Skeleton className="h-72" />
        <Skeleton className="h-72" />
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    loadDashboard()
      .then((d) => !cancelled && setData(d))
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load the dashboard")
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (error !== null) {
    return (
      <div className="p-8">
        <div
          role="alert"
          className="rounded-hearth border border-hairline bg-surface px-6 py-4 text-sm text-muted"
        >
          Could not load the dashboard: {error}
        </div>
      </div>
    )
  }

  if (data === null) return <DashboardSkeletons />

  return <DashboardGrid data={data} />
}
