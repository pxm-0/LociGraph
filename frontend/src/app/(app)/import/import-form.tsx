"use client"

import { useRef, useState } from "react"
import { detectSourceType, SOURCE_TYPES } from "@/lib/types"
import type { SourceType } from "@/lib/types"
import { Button } from "@/components/ui/Button"
import { ApiError, uploadSource } from "@/lib/api"

// --- Source type metadata ---
const FORMAT_META: Record<
  SourceType,
  { label: string; ext: string }
> = {
  json: { label: "JSON", ext: ".json" },
  markdown: { label: "Markdown", ext: ".md" },
  html: { label: "Web Archive", ext: ".html" },
  pdf: { label: "Portable Doc", ext: ".pdf" },
  chatgpt: { label: "LLM Export", ext: ".zip" },
  meta: { label: "Social Meta", ext: ".json" },
}

// --- Drag-and-drop state type ---
type DragState = "idle" | "over"

// --- Staged file awaiting upload ---
interface StagedFile {
  id: string
  file: File
  sourceType: SourceType
  status: "pending" | "uploading" | "done" | "duplicate" | "error"
  error?: string
  sourceId?: string
}

// crypto.randomUUID() requires a secure context (HTTPS/localhost); this id is only
// a local React key, so a plain random fallback is fine when served over HTTP.
function generateId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID()
  return Math.random().toString(36).slice(2)
}

function toStagedFile(file: File): StagedFile {
  const detected = detectSourceType(file.name)
  return {
    id: generateId(),
    file,
    sourceType: detected === "ambiguous" ? "json" : detected,
    status: "pending",
  }
}

export default function ImportForm() {
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([])
  const [dragState, setDragState] = useState<DragState>("idle")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  function handleFilesChange(incoming: FileList | File[] | null) {
    if (!incoming || incoming.length === 0) return
    setStagedFiles((prev) => [...prev, ...Array.from(incoming).map(toStagedFile)])
    setError(null)
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    handleFilesChange(e.target.files)
  }

  function onDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    e.stopPropagation()
    setDragState("over")
  }

  function onDragLeave(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    e.stopPropagation()
    setDragState("idle")
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    e.stopPropagation()
    setDragState("idle")
    handleFilesChange(e.dataTransfer.files)
  }

  function updateStagedType(id: string, newType: SourceType) {
    setStagedFiles((prev) =>
      prev.map((f) => (f.id === id ? { ...f, sourceType: newType } : f))
    )
  }

  function removeStagedFile(id: string) {
    setStagedFiles((prev) => prev.filter((f) => f.id !== id))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)

    const pendingIds = stagedFiles.filter((f) => f.status === "pending").map((f) => f.id)

    for (const id of pendingIds) {
      const row = stagedFiles.find((f) => f.id === id)
      if (!row) continue

      setStagedFiles((prev) =>
        prev.map((f) => (f.id === id ? { ...f, status: "uploading" } : f))
      )

      try {
        const uploadResult = await uploadSource(row.sourceType, row.file)
        setStagedFiles((prev) =>
          prev.map((f) =>
            f.id === id ? { ...f, status: "done", sourceId: uploadResult.sourceId } : f
          )
        )
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          setError("Session expired — please sign in again.")
          break
        }
        if (err instanceof ApiError && err.status === 409) {
          setStagedFiles((prev) =>
            prev.map((f) =>
              f.id === id
                ? { ...f, status: "duplicate", error: err.message || "Duplicate source (already imported)." }
                : f
            )
          )
          continue
        }
        setStagedFiles((prev) =>
          prev.map((f) =>
            f.id === id
              ? { ...f, status: "error", error: err instanceof Error ? err.message : "Upload failed." }
              : f
          )
        )
      }
    }

    setSubmitting(false)
  }

  const isOver = dragState === "over"
  const hasPending = stagedFiles.some((f) => f.status === "pending")

  const totalCount = stagedFiles.length
  const settledStatuses: StagedFile["status"][] = ["done", "duplicate", "error"]
  const settledCount = stagedFiles.filter((f) => settledStatuses.includes(f.status)).length
  const hasStartedUploading = stagedFiles.some(
    (f) => f.status === "uploading" || settledStatuses.includes(f.status)
  )
  const doneCount = stagedFiles.filter((f) => f.status === "done").length
  const duplicateCount = stagedFiles.filter((f) => f.status === "duplicate").length
  const errorCount = stagedFiles.filter((f) => f.status === "error").length

  const progressText =
    settledCount < totalCount
      ? `${settledCount} of ${totalCount} uploaded`
      : [
          doneCount > 0 && `${doneCount} uploaded`,
          duplicateCount > 0 && `${duplicateCount} duplicate`,
          errorCount > 0 && `${errorCount} failed`,
        ]
          .filter(Boolean)
          .join(", ")

  return (
    <form onSubmit={handleSubmit} className="space-y-10">
      {/* ── Drop zone ── */}
      <div
        role="region"
        aria-label="File drop zone"
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className={[
          "relative flex h-72 w-full cursor-pointer flex-col items-center justify-center",
          "rounded-hearth border-2 border-dashed transition-colors",
          isOver
            ? "border-ember bg-surface-hover"
            : "border-ember/30 bg-surface hover:border-ember/60 hover:bg-surface-hover",
        ].join(" ")}
      >
        {/* Hidden real file input */}
        <input
          ref={fileInputRef}
          id="file-input"
          aria-label="Choose file"
          type="file"
          multiple
          className="absolute inset-0 cursor-pointer opacity-0"
          onChange={onInputChange}
        />

        <div className="pointer-events-none flex flex-col items-center gap-4 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-void">
            <svg
              className={`h-7 w-7 transition-colors ${isOver ? "text-ember" : "text-ash"}`}
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
              />
            </svg>
          </div>

          <div className="space-y-1">
            <p className="font-heading text-lg font-medium text-ink">
              {stagedFiles.length > 0
                ? `${stagedFiles.length} file${stagedFiles.length === 1 ? "" : "s"} staged`
                : "Drop files here"}
            </p>
            <p className="font-mono text-xs text-muted">
              JSON · PDF · HTML · Markdown · ChatGPT export · Meta export
            </p>
          </div>

          <span className="mt-2 inline-flex items-center rounded-hearth bg-ember px-6 py-2 font-ui text-sm font-medium text-void transition-opacity hover:opacity-90">
            Browse Files
          </span>
        </div>
      </div>

      {/* ── Progress bar ── */}
      {hasStartedUploading && totalCount > 0 && (
        <div className="space-y-2">
          <p className="font-mono text-xs text-muted">{progressText}</p>
          <div className="h-0.5 w-full rounded-full bg-hairline">
            <div
              data-testid="upload-progress-bar"
              className="h-0.5 rounded-full bg-ember transition-all"
              style={{ width: `${(settledCount / totalCount) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* ── Staged file list ── */}
      {stagedFiles.length > 0 && (
        <ul aria-label="Staged files" className="divide-y divide-hairline rounded-hearth border border-hairline bg-surface">
          {stagedFiles.map((staged) => (
            <StagedFileRow
              key={staged.id}
              staged={staged}
              onTypeChange={(newType) => updateStagedType(staged.id, newType)}
              onRemove={() => removeStagedFile(staged.id)}
            />
          ))}
        </ul>
      )}

      {/* ── Error alert ── */}
      {error !== null && (
        <div
          role="alert"
          className="rounded-hearth border border-hairline bg-surface px-5 py-3 font-ui text-sm text-muted"
        >
          {error}
        </div>
      )}

      {/* ── Submit ── */}
      <div>
        <Button
          type="submit"
          disabled={!hasPending || submitting}
          className="min-w-[120px]"
        >
          {submitting ? "Uploading…" : "Upload All"}
        </Button>
      </div>

      {/* ── Format cards ── */}
      <section aria-label="Supported formats">
        <h2 className="mb-5 font-mono text-[11px] uppercase tracking-widest text-muted">
          Supported Formats
        </h2>
        {/*
          Layout: offset multi-column grid — NOT a 3-equal-column or 6-equal-column flat grid.
          Row 1: 3 cards, each spanning 2 cols in a 7-col grid (total 6 + 1 offset col).
          Row 2: 3 cards, offset by 1 col so they visually cascade.
        */}
        <div className="grid grid-cols-7 gap-3">
          {SOURCE_TYPES.slice(0, 3).map((t) => (
            <FormatCard key={t} type={t} />
          ))}
          {/* spacer to offset second row */}
          <div
            className="hidden md:block col-span-1"
            aria-hidden="true"
          />
          {SOURCE_TYPES.slice(3).map((t) => (
            <FormatCard key={t} type={t} />
          ))}
        </div>
      </section>
    </form>
  )
}

// --- Status indicator colors for staged rows ---
const STAGED_STATUS_COLORS: Record<StagedFile["status"], string> = {
  pending: "text-muted",
  uploading: "text-status-ingesting",
  done: "text-status-verified",
  duplicate: "text-status-quarantined",
  error: "text-status-quarantined",
}

// --- Staged file row sub-component ---
function StagedFileRow({
  staged,
  onTypeChange,
  onRemove,
}: {
  staged: StagedFile
  onTypeChange: (newType: SourceType) => void
  onRemove: () => void
}) {
  return (
    <li className="flex items-center gap-4 px-5 py-3">
      <span className="flex-1 truncate font-ui text-sm text-ink">
        {staged.file.name}
      </span>
      <select
        aria-label={`Source type for ${staged.file.name}`}
        value={staged.sourceType}
        onChange={(e) => onTypeChange(e.target.value as SourceType)}
        disabled={staged.status !== "pending"}
        className="rounded-meridian border border-hairline bg-canvas px-2 py-1 font-ui text-xs text-ink focus:outline-none focus:ring-1 focus:ring-ember disabled:opacity-40"
      >
        {SOURCE_TYPES.map((t) => (
          <option key={t} value={t}>
            {FORMAT_META[t].label}
          </option>
        ))}
      </select>
      <span
        className={`font-mono text-xs uppercase tracking-wide ${STAGED_STATUS_COLORS[staged.status]}`}
      >
        {staged.status}
      </span>
      <Button
        type="button"
        variant="ghost"
        disabled={staged.status !== "pending"}
        onClick={onRemove}
        aria-label={`Remove ${staged.file.name}`}
        className="px-3 py-1.5 font-mono text-[11px] uppercase"
      >
        Remove
      </Button>
    </li>
  )
}

// --- Format card sub-component ---
function FormatCard({ type }: { type: SourceType }) {
  const meta = FORMAT_META[type]
  return (
    <div className="col-span-2 rounded-hearth border border-hairline bg-surface p-4 transition-colors hover:bg-surface-hover">
      <svg
        className="mb-2 h-5 w-5 text-ember"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
        />
      </svg>
      <p className="font-ui text-sm font-medium text-ink">{meta.label}</p>
      <p className="font-mono text-xs text-muted">{meta.ext}</p>
    </div>
  )
}
