import type { PlanetariumNodeDetail } from "@/lib/types"

function sizeAdjective(mass: number): string {
  if (mass >= 0.66) return "large"
  if (mass >= 0.33) return "medium"
  return "small"
}

function brightnessAdjective(brightness: number): string {
  if (brightness >= 0.66) return "glowing"
  if (brightness >= 0.2) return "dimly lit"
  return "dim"
}

export function describeNode(detail: PlanetariumNodeDetail): string {
  const kind = detail.visualClass === "black_hole" ? "black hole" : "planet"
  const size = sizeAdjective(detail.mass)
  const glow = brightnessAdjective(detail.brightness)
  const activity =
    detail.revisionCount + detail.edgeCount + detail.contradictionCount + detail.pinCount > 0
      ? "well connected"
      : "not yet connected to much"
  return `A ${size}, ${glow} ${kind} — ${activity}.`
}
