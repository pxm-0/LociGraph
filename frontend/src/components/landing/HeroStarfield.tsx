"use client"

import { CappedStarfield } from "@/components/planetarium/CappedStarfield"
import { DEMO_NODES } from "@/lib/demoGraph"

// Full-bleed hero backdrop. Fixed Meridian palette + slow drift; the landing
// commits to the dark cosmic look regardless of the stored app theme.
// Loaded via next/dynamic({ ssr: false }) from Landing so the overlay copy
// paints before the R3F bundle arrives.
export default function HeroStarfield() {
  return <CappedStarfield nodes={DEMO_NODES} mode="meridian" drift />
}
