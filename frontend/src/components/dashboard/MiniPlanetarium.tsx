"use client"

import { useEffect, useState } from "react"
import dynamic from "next/dynamic"
import Link from "next/link"
import { listPlanetariumNodes } from "@/lib/api"
import { useMode } from "@/lib/theme"
import type { PlanetariumNode } from "@/lib/types"
import { Card } from "@/components/ui/Card"

// R3F bundle stays lazy + client-only so the rest of the dashboard paints first.
const CappedStarfield = dynamic(
  () => import("@/components/planetarium/CappedStarfield").then((m) => m.CappedStarfield),
  { ssr: false },
)

const MAX_NODES = 40

export function MiniPlanetarium() {
  const { mode } = useMode()
  const [nodes, setNodes] = useState<PlanetariumNode[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    listPlanetariumNodes()
      .then((all) => {
        if (cancelled) return
        // Cap to the heaviest nodes so the secondary surface stays calm.
        const capped = [...all].sort((a, b) => b.mass - a.mass).slice(0, MAX_NODES)
        setNodes(capped)
      })
      .catch(() => !cancelled && setError(true))
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <Card className="flex flex-col gap-3 p-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-4">
        <h2 className="font-heading text-base font-medium text-ink">Planetarium</h2>
        <Link href="/planetarium" className="font-mono text-xs text-accent hover:underline">
          Open full view →
        </Link>
      </div>
      <div className="relative h-64 w-full">
        {error ? (
          <p className="px-4 text-sm text-muted">Could not load the planetarium.</p>
        ) : nodes === null ? (
          <p className="px-4 text-sm text-muted">Loading…</p>
        ) : nodes.length === 0 ? (
          <p className="px-4 text-sm text-muted">Nothing to show yet — trigger a rebuild.</p>
        ) : (
          <CappedStarfield nodes={nodes} mode={mode} drift />
        )}
      </div>
    </Card>
  )
}
