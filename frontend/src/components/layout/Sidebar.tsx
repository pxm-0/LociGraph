"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useMode } from "@/lib/theme"
import { NavIcon } from "@/components/layout/NavIcon"
import type { IconName } from "@/components/layout/NavIcon"

interface NavItem {
  label: string
  href: string
  icon: IconName
}

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: "dashboard" },
  { label: "Import", href: "/import", icon: "inventory_2" },
  { label: "Sources", href: "/sources", icon: "database" },
  { label: "Observations", href: "/observations", icon: "visibility" },
  { label: "Claims", href: "/claims", icon: "analytics" },
]

// Hearth: wide left sidebar with label + icon, teal active indicator
function HearthSidebar({ pathname }: { pathname: string }) {
  return (
    <aside className="fixed left-0 top-0 h-screen w-60 bg-archive border-r border-whisper flex flex-col py-3 z-40">
      {/* Brand */}
      <div className="px-6 mb-12">
        <h1 className="font-heading text-2xl text-ember tracking-tight">LociGraph</h1>
        <p className="text-xs text-ash opacity-60 uppercase tracking-widest mt-1">Archivist Deck</p>
      </div>

      {/* Nav links */}
      <nav className="flex-1 space-y-1">
        {NAV_ITEMS.map(({ label, href, icon }) => {
          const isActive = pathname === href || pathname.startsWith(href + "/")
          return (
            <Link
              key={href}
              href={href}
              className={[
                "flex items-center px-6 py-3 transition-all duration-200 border-l-2",
                isActive
                  ? "text-hearth-accent border-hearth-accent bg-chamber"
                  : "text-ash border-transparent hover:bg-chamber hover:text-dust",
              ].join(" ")}
            >
              <NavIcon
                name={icon}
                className="mr-3 w-5 h-5 shrink-0"
                aria-hidden="true"
              />
              <span className={`font-ui text-sm ${isActive ? "font-medium" : ""}`}>{label}</span>
            </Link>
          )
        })}
      </nav>

      {/* Orb placeholder */}
      <div className="px-6 mt-auto mb-4">
        {/* Orb/Core companion — deferred (Plan 4 scope: dual-mode, Orb later) */}
        <div data-orb-slot className="hidden" aria-hidden="true" />
      </div>

      {/* Footer utility links */}
      <div className="px-6 pb-4 border-t border-whisper pt-4 space-y-3">
        <span className="flex items-center text-xs text-ash hover:text-dust transition-colors cursor-default">
          <NavIcon
            name="analytics"
            className="w-4 h-4 mr-2 shrink-0"
            aria-hidden="true"
          />
          System Status
        </span>
      </div>
    </aside>
  )
}

// Meridian: compact icon-only left sidebar (64px wide), tight density
function MeridianSidebar({ pathname }: { pathname: string }) {
  return (
    <aside className="fixed left-0 top-0 h-screen w-16 bg-archive border-r border-whisper flex flex-col items-center py-3 z-40">
      {/* Brand icon */}
      <div className="mb-8 p-2">
        <NavIcon
          name="database"
          className="text-ember w-6 h-6"
          aria-label="LociGraph"
        />
      </div>

      {/* Nav icon buttons */}
      <nav className="flex flex-col gap-1 w-full px-2">
        {NAV_ITEMS.map(({ label, href, icon }) => {
          const isActive = pathname === href || pathname.startsWith(href + "/")
          return (
            <Link
              key={href}
              href={href}
              title={label}
              aria-label={label}
              className={[
                "w-12 h-12 flex items-center justify-center rounded-meridian transition-all duration-200 border-l-2",
                isActive
                  ? "bg-chamber text-hearth-accent border-hearth-accent"
                  : "text-ash border-transparent hover:bg-chamber hover:text-dust",
              ].join(" ")}
            >
              <NavIcon
                name={icon}
                className="w-5 h-5"
                aria-hidden="true"
              />
            </Link>
          )
        })}
      </nav>

      {/* Orb placeholder */}
      <div className="mt-auto mb-2">
        {/* Orb/Core companion — deferred (Plan 4 scope: dual-mode, Orb later) */}
        <div data-orb-slot className="hidden" aria-hidden="true" />
      </div>

      {/* Footer icon */}
      <div className="flex flex-col gap-1 w-full px-2 pb-2">
        <span
          className="w-12 h-12 flex items-center justify-center text-ash cursor-default"
          aria-label="System Status"
          title="System Status"
        >
          <NavIcon
            name="analytics"
            className="w-5 h-5"
            aria-hidden="true"
          />
        </span>
      </div>
    </aside>
  )
}

export function Sidebar() {
  const { mode } = useMode()
  const pathname = usePathname()

  return mode === "hearth" ? (
    <HearthSidebar pathname={pathname} />
  ) : (
    <MeridianSidebar pathname={pathname} />
  )
}
