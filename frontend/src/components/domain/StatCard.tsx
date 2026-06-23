import { useMode } from "@/lib/theme"

interface StatCardProps {
  value: number
  label: string
}

export function StatCard({ value, label }: StatCardProps) {
  const { mode } = useMode()

  const accentClass =
    mode === "hearth" ? "text-hearth-accent" : "text-ember"

  return (
    <div className="rounded-hearth border border-whisper bg-chamber p-6 transition-colors duration-200 hover:bg-chamber-hover">
      <p className="mb-3 text-xs font-ui uppercase tracking-widest text-ash">
        {label}
      </p>
      <p
        className={`font-mono text-[2rem] leading-none ${accentClass}`}
        aria-label={`${label}: ${value}`}
      >
        {value}
      </p>
    </div>
  )
}
