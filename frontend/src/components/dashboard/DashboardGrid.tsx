"use client"

import dynamic from "next/dynamic"
import { StatCard } from "@/components/domain/StatCard"
import { deltaThisWeek, type DashboardData } from "@/lib/dashboard"
import type { TrendPoint } from "@/lib/types"
import { CustodianCard } from "./CustodianCard"
import { NeedsAttention } from "./NeedsAttention"
import { RecentActivity } from "./RecentActivity"
import { Sparkline } from "./Sparkline"

const MiniPlanetarium = dynamic(() => import("./MiniPlanetarium").then((m) => m.MiniPlanetarium), {
  ssr: false,
})

// Reuse the existing Custodian orb open mechanism (its state is local to Orb).
// Clicking the mounted orb button opens the panel — no need to fork the panel
// or lift its state just for this entry point.
// ponytail: DOM click on the orb; lift to context only if a second caller appears.
function askCustodian() {
  document.querySelector<HTMLButtonElement>("[data-orb-slot]")?.click()
}

interface StatTileProps {
  value: number
  label: string
  points?: TrendPoint[]
}

function StatTile({ value, label, points }: StatTileProps) {
  return (
    <div className="flex flex-col gap-2">
      <StatCard value={value} label={label} />
      {points && (
        <div className="flex items-center justify-between px-1">
          <span className="font-mono text-[11px] text-muted">+{deltaThisWeek(points)} this week</span>
          <div className="w-24">
            <Sparkline points={points} />
          </div>
        </div>
      )}
    </div>
  )
}

export function DashboardGrid({ data }: { data: DashboardData }) {
  const { summary, trends, needsAttention, activity } = data

  return (
    <div className="space-y-10 p-8">
      <h1 className="font-heading text-2xl font-medium text-ink">Archive Overview</h1>

      <section aria-label="Needs attention">
        <NeedsAttention items={needsAttention} />
      </section>

      <section aria-label="Statistics" className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile value={summary.sourceCount} label="Sources" points={trends.series.sources} />
        <StatTile value={summary.claimCount} label="Claims" points={trends.series.claims} />
        <StatTile value={summary.conceptCount} label="Concepts" points={trends.series.concepts} />
        <StatTile value={summary.observationCount} label="Observations" />
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section aria-label="Planetarium">
          <MiniPlanetarium />
        </section>
        <section aria-label="Recent activity">
          <RecentActivity items={activity} />
        </section>
      </div>

      <section aria-label="Custodian">
        <CustodianCard pendingProposals={0} onAsk={askCustodian} />
      </section>
    </div>
  )
}
