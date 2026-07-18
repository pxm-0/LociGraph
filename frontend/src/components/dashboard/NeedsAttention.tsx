import Link from "next/link"
import { Card } from "@/components/ui/Card"
import type { NeedsAttentionCounts } from "@/lib/dashboard"

interface AttentionEntry {
  count: number
  label: string
  href: string
}

function entries(items: NeedsAttentionCounts): AttentionEntry[] {
  return [
    { count: items.contradictions, label: "Open contradictions", href: "/contradictions" },
    { count: items.jobs, label: "Jobs need attention", href: "/jobs" },
    { count: items.candidates, label: "Unreviewed candidates", href: "/concept-candidates" },
  ]
}

export function NeedsAttention({ items }: { items: NeedsAttentionCounts }) {
  const rows = entries(items)
  const allClear = rows.every((r) => r.count === 0)

  if (allClear) {
    return (
      <Card className="flex items-center gap-3">
        <span className="font-mono text-sm text-status-verified">✓ All clear</span>
        <span className="text-sm text-muted">Nothing needs your attention right now.</span>
      </Card>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {rows.map((r) => (
        <Link key={r.label} href={r.href} className="group">
          <Card className="transition-colors group-hover:bg-surface-hover">
            <p className="font-mono text-[2rem] leading-none text-accent">{r.count}</p>
            <p className="mt-3 text-xs font-ui uppercase tracking-widest text-muted">{r.label}</p>
          </Card>
        </Link>
      ))}
    </div>
  )
}
