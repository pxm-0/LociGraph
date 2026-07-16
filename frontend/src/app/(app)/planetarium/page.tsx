"use client"

import { useCallback, useEffect, useState } from "react"
import { listPlanetariumNodes } from "@/lib/api"
import type { PlanetariumNode } from "@/lib/types"
import { PlanetariumScene } from "@/components/planetarium/PlanetariumScene"
import { RebuildButton } from "@/components/planetarium/RebuildButton"

export default function PlanetariumPage() {
  const [nodes, setNodes] = useState<PlanetariumNode[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    listPlanetariumNodes()
      .then(setNodes)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load the Planetarium")
      })
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const isLoading = nodes === null && error === null

  return (
    <div className="relative h-screen w-full">
      <div className="absolute right-4 top-4 z-10">
        <RebuildButton onRebuildComplete={load} />
      </div>

      {error !== null && (
        <div
          role="alert"
          className="absolute left-4 top-4 z-10 rounded-hearth border border-hairline bg-surface px-4 py-2 text-sm text-muted"
        >
          {error}
        </div>
      )}

      {isLoading && <p className="absolute left-4 top-4 z-10 text-sm text-muted">Loading…</p>}

      {!isLoading && nodes !== null && nodes.length === 0 && (
        <p className="absolute left-4 top-4 z-10 text-sm text-muted">
          Nothing to show yet — trigger a rebuild.
        </p>
      )}

      {nodes !== null && nodes.length > 0 && (
        <PlanetariumScene nodes={nodes} onSelect={() => {}} />
      )}
    </div>
  )
}
