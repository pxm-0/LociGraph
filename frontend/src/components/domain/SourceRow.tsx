"use client"

import type { Source } from "@/lib/types"
import { Badge } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Button"
import { StatusBadge } from "@/components/ui/StatusBadge"

function formatBytes(bytes: number | null): string {
  if (bytes === null) return "—"
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

interface SourceRowProps {
  source: Source
  isExtracting?: boolean
  onExtract?: (source: Source) => void
}

export function SourceRow({ source, isExtracting = false, onExtract }: SourceRowProps) {
  const isPurged = source.importStatus === "PURGED"
  const filenameClass = isPurged
    ? "font-heading text-ash line-through"
    : "font-heading text-dust"
  const canExtract = source.importStatus === "VERIFIED" && onExtract !== undefined

  return (
    <tr className="border-t border-whisper transition-colors hover:bg-chamber-hover">
      <td className="px-5 py-3">
        <span className={filenameClass}>
          {source.originalFilename ?? <span className="text-ash">—</span>}
        </span>
      </td>
      <td className="px-5 py-3">
        <Badge className="font-mono text-xs uppercase">
          {source.sourceType}
        </Badge>
      </td>
      <td className="px-5 py-3">
        <StatusBadge status={source.importStatus} />
      </td>
      <td className="px-5 py-3 font-mono text-xs text-ash">
        {formatBytes(source.fileSizeBytes)}
      </td>
      <td className="px-5 py-3 font-mono text-xs text-ash">
        {source.observationCount}
      </td>
      <td className="px-5 py-3 font-mono text-xs text-ash">
        {source.claimCount}
      </td>
      <td className="px-5 py-3 text-right">
        <Button
          className="px-3 py-1.5 font-mono text-[11px] uppercase"
          disabled={!canExtract || isExtracting}
          onClick={() => onExtract?.(source)}
          type="button"
          variant="ghost"
        >
          {isExtracting ? "Running" : source.claimCount > 0 ? "Retry" : "Extract"}
        </Button>
      </td>
    </tr>
  )
}
