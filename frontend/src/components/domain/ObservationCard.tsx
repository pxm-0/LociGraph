import type { Observation } from "@/lib/types"

interface ObservationCardProps {
  observation: Observation
  selected?: boolean
  onClick?: () => void
}

function formatTimestamp(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  return d.toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
}

function formatConfidence(value: number): string {
  return value.toFixed(2)
}

export function ObservationCard({ observation, selected = false, onClick }: ObservationCardProps) {
  const { content, speaker, observedAt, confidence, sourceId } = observation

  const timestamp = formatTimestamp(observedAt)
  const confidenceStr = formatConfidence(confidence)
  const shortSource = sourceId ? sourceId.slice(0, 12) : "—"

  const metaParts: { key: string; value: string }[] = []
  if (timestamp) metaParts.push({ key: "ts", value: timestamp })
  metaParts.push({ key: "src", value: shortSource })
  if (speaker) metaParts.push({ key: "spk", value: speaker })
  metaParts.push({ key: "conf", value: confidenceStr })

  return (
    <article
      onClick={onClick}
      className={[
        "rounded-hearth border-l-4 p-6 transition-colors cursor-pointer",
        selected
          ? "border-l-accent bg-surface-hover"
          : "border-l-transparent bg-surface hover:bg-surface-hover",
      ].join(" ")}
    >
      <p className="font-heading text-[15px] leading-[1.7] text-ink max-w-[65ch]">{content}</p>

      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-muted">
        {metaParts.map((part, i) => (
          <span key={part.key} className="flex items-center gap-1">
            {i > 0 && <span aria-hidden="true" className="w-1 h-1 rounded-full bg-hairline inline-block" />}
            {part.value}
          </span>
        ))}
      </div>
    </article>
  )
}
