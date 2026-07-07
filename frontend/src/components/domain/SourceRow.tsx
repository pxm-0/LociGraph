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
  isEmbedding?: boolean
  itemsCompleted?: number | null
  itemsTotal?: number | null
  onExtract?: (source: Source) => void
  onEmbed?: (source: Source) => void
  onDelete?: (source: Source) => void
}

export function SourceRow({
  source,
  isExtracting = false,
  isEmbedding = false,
  itemsCompleted = null,
  itemsTotal = null,
  onExtract,
  onEmbed,
  onDelete,
}: SourceRowProps) {
  const isPurged = source.importStatus === "PURGED"
  const filenameClass = isPurged
    ? "font-heading text-muted line-through"
    : "font-heading text-ink"
  const canExtract = source.importStatus === "VERIFIED" && onExtract !== undefined
  const canEmbed =
    source.importStatus === "VERIFIED" && source.claimCount > 0 && onEmbed !== undefined
  const canDelete = source.claimCount === 0 && !isPurged
  const showProgress = isExtracting && Boolean(itemsTotal)

  return (
    <tr className="border-t border-hairline transition-colors hover:bg-surface-hover">
      <td className="px-5 py-3">
        <span className={filenameClass}>
          {source.originalFilename ?? <span className="text-muted">—</span>}
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
      <td className="px-5 py-3 font-mono text-xs text-muted">
        {formatBytes(source.fileSizeBytes)}
      </td>
      <td className="px-5 py-3 font-mono text-xs text-muted">
        {source.observationCount}
      </td>
      <td className="px-5 py-3 font-mono text-xs text-muted">
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
        {onEmbed !== undefined && (
          <Button
            className="ml-2 px-3 py-1.5 font-mono text-[11px] uppercase"
            disabled={!canEmbed || isEmbedding}
            onClick={() => onEmbed(source)}
            type="button"
            variant="ghost"
          >
            {isEmbedding ? "Embedding" : "Embed"}
          </Button>
        )}
        <Button
          className="ml-2 px-3 py-1.5 font-mono text-[11px] uppercase"
          disabled={!canDelete}
          onClick={() => onDelete?.(source)}
          type="button"
          variant="ghost"
        >
          Delete
        </Button>
        {showProgress && (
          <div className="mt-2 space-y-1">
            <p className="font-mono text-[10px] text-muted">
              {itemsCompleted} / {itemsTotal} processed
            </p>
            <div className="h-0.5 w-full rounded-full bg-hairline">
              <div
                data-testid="extraction-progress-bar"
                className="h-0.5 rounded-full bg-ember transition-all"
                style={{ width: `${((itemsCompleted ?? 0) / (itemsTotal ?? 1)) * 100}%` }}
              />
            </div>
          </div>
        )}
      </td>
    </tr>
  )
}
