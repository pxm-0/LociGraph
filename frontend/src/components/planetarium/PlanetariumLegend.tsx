"use client"

import { useState } from "react"

export function PlanetariumLegend() {
  const [open, setOpen] = useState(true)

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        aria-label="Show legend"
        className="rounded-hearth border border-hairline bg-surface px-3 py-1.5 text-xs font-ui text-muted hover:text-ink"
      >
        Legend
      </button>
    )
  }

  return (
    <div className="w-72 rounded-hearth border border-hairline bg-surface p-4 text-xs text-muted shadow-lg">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-heading text-sm text-ink">Reading the map</span>
        <button
          onClick={() => setOpen(false)}
          aria-label="Close legend"
          className="font-ui text-muted hover:text-ink"
        >
          Close
        </button>
      </div>
      <ul className="space-y-2">
        <li>
          <strong className="text-ink">Position</strong> — clustered concepts are
          semantically similar (based on content). Some nodes have no content
          yet and are spread out arbitrarily just to avoid overlap — not
          semantically positioned.
        </li>
        <li>
          <strong className="text-ink">Size</strong> — bigger means more
          activity: revisions, links to other concepts, contradictions, and
          pins.
        </li>
        <li>
          <strong className="text-ink">Color</strong> — dark &quot;black hole&quot; nodes
          are the top 10% most active/connected concepts.
        </li>
        <li>
          <strong className="text-ink">Glow</strong> — brighter means touched
          more recently; it fades over about a month.
        </li>
      </ul>
    </div>
  )
}
