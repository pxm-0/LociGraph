import type { TrendPoint } from "@/lib/types"

// Pure: map N points to an SVG polyline path scaled to the series min/max.
// Flat series → horizontal line at mid-height; <2 points → empty path.
export function sparklinePath(points: TrendPoint[], w: number, h: number): string {
  if (points.length < 2) return ""
  const counts = points.map((p) => p.count)
  const min = Math.min(...counts)
  const max = Math.max(...counts)
  const span = max - min
  const stepX = w / (points.length - 1)
  return points
    .map((p, i) => {
      const x = i * stepX
      // Invert Y (SVG origin is top-left); flat series sits at mid-height.
      const y = span === 0 ? h / 2 : h - ((p.count - min) / span) * h
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(" ")
}

interface SparklineProps {
  points: TrendPoint[]
  className?: string
}

export function Sparkline({ points, className = "" }: SparklineProps) {
  const w = 100
  const h = 24
  const d = sparklinePath(points, w, h)
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      className={`h-6 w-full text-accent ${className}`}
    >
      {d && <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />}
    </svg>
  )
}
