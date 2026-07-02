interface StatCardProps {
  value: number
  label: string
}

export function StatCard({ value, label }: StatCardProps) {
  return (
    <div className="rounded-hearth border border-hairline bg-surface p-6 transition-colors duration-200 hover:bg-surface-hover">
      <p className="mb-3 text-xs font-ui uppercase tracking-widest text-muted">
        {label}
      </p>
      <p
        className="font-mono text-[2rem] leading-none text-accent"
        aria-label={`${label}: ${value}`}
      >
        {value}
      </p>
    </div>
  )
}
