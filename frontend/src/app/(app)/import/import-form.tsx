"use client"

import { useRef, useState } from "react"
import Link from "next/link"
import { detectSourceType, SOURCE_TYPES } from "@/lib/types"
import type { SourceType } from "@/lib/types"
import { Button } from "@/components/ui/Button"

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

// --- Success result type ---
interface UploadResult {
  sourceId: string
  status: string
}

// --- Staged file awaiting upload ---
interface StagedFile {
  id: string
  file: File
  sourceType: SourceType
  status: "pending" | "uploading" | "done" | "duplicate" | "error"
  error?: string
  sourceId?: string
}

function toStagedFile(file: File): StagedFile {
  const detected = detectSourceType(file.name)
  return {
    id: crypto.randomUUID(),
    file,
    sourceType: detected === "ambiguous" ? "json" : detected,
    status: "pending",
  }
}

export default function ImportForm() {
  const [sourceType, setSourceType] = useState<SourceType>("json")
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([])
  const [dragState, setDragState] = useState<DragState>("idle")
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<UploadResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  function handleFilesChange(incoming: FileList | File[] | null) {
    if (!incoming || incoming.length === 0) return
    setStagedFiles((prev) => [...prev, ...Array.from(incoming).map(toStagedFile)])
    setError(null)
    setResult(null)
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
    // Upload sequencing lands in a later task.
  }

  const isOver = dragState === "over"
  const hasPending = stagedFiles.some((f) => f.status === "pending")

  return (
    <form onSubmit={handleSubmit} className="space-y-10">
      {/* ── Source type selector ── */}
      <div className="space-y-2">
        <label
          htmlFor="source-type-select"
          className="block font-ui text-xs uppercase tracking-widest text-muted"
        >
          Source Type
        </label>
        <select
          id="source-type-select"
          aria-label="Source Type"
          value={sourceType}
          onChange={(e) => setSourceType(e.target.value as SourceType)}
          className="w-full max-w-xs rounded-meridian border border-hairline bg-canvas px-3 py-2 font-ui text-sm text-ink focus:outline-none focus:ring-1 focus:ring-ember"
        >
          {SOURCE_TYPES.map((t) => (
            <option key={t} value={t}>
              {FORMAT_META[t].label} ({FORMAT_META[t].ext})
            </option>
          ))}
        </select>
      </div>

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

      {/* ── Success state ── */}
      {result !== null && (
        <div className="rounded-hearth border border-hairline bg-surface px-5 py-4 space-y-2">
          <p className="font-ui text-sm text-ink">
            Import queued —{" "}
            <span className="font-mono text-xs text-ember">{result.sourceId}</span>
          </p>
          <p className="font-ui text-sm text-muted">
            Status:{" "}
            <span className="font-mono text-xs uppercase tracking-wide text-status-ingesting">
              {result.status}
            </span>
          </p>
          <Link
            href="/sources"
            className="inline-block font-ui text-sm text-ember underline-offset-2 hover:underline"
          >
            View all sources
          </Link>
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
            <FormatCard key={t} type={t} active={sourceType === t} />
          ))}
          {/* spacer to offset second row */}
          <div
            className="hidden md:block col-span-1"
            aria-hidden="true"
          />
          {SOURCE_TYPES.slice(3).map((t) => (
            <FormatCard key={t} type={t} active={sourceType === t} />
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
function FormatCard({
  type,
  active,
}: {
  type: SourceType
  active: boolean
}) {
  const meta = FORMAT_META[type]
  return (
    <div
      className={[
        "col-span-2 rounded-hearth border p-4 transition-colors",
        active
          ? "border-ember bg-surface-hover"
          : "border-hairline bg-surface hover:bg-surface-hover",
      ].join(" ")}
    >
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
