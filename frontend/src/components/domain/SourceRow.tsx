"use client"

import type { Source } from "@/lib/types"
import { Badge } from "@/components/ui/Badge"
import { StatusBadge } from "@/components/ui/StatusBadge"

function formatBytes(bytes: number | null): string {
  if (bytes === null) return "—"
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

interface SourceRowProps {
  source: Source
}

export function SourceRow({ source }: SourceRowProps) {
  const isPurged = source.importStatus === "PURGED"
  const filenameClass = isPurged
    ? "font-heading text-ash line-through"
    : "font-heading text-dust"

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
      {/* NOTE: importTimestamp column omitted — API does not return a created/import timestamp in Phase 0 */}
      {/* NOTE: observations count column omitted — API does not provide per-source observation count in Phase 0 */}
    </tr>
  )
}
