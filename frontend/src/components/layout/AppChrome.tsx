"use client"

import type { ReactNode } from "react"
import { usePathname } from "next/navigation"
import { useMode } from "@/lib/theme"
import { Sidebar } from "@/components/layout/Sidebar"
import { NAV_ITEMS } from "@/components/layout/Sidebar"
import { ModeToggle } from "@/components/layout/ModeToggle"
import { Orb } from "@/components/custodian/Orb"

function currentPageTitle(pathname: string): string {
  const item = NAV_ITEMS.find((i) => pathname === i.href || pathname.startsWith(i.href + "/"))
  return item?.pageTitle ?? item?.label ?? "LociGraph"
}

// AppChrome reads mode after ThemeProvider mounts — must be a client component
export function AppChrome({ children }: { children: ReactNode }) {
  const { mode } = useMode()
  const pathname = usePathname()

  const isHearth = mode === "hearth"

  return (
    <div className="min-h-screen bg-canvas">
      {/* Mode-adaptive sidebar */}
      <Sidebar />

      {/* Main content area shifted by sidebar width */}
      <div className={isHearth ? "ml-60" : "ml-16"}>
        {/* Top app bar */}
        <header
          className={[
            "sticky top-0 z-30 flex items-center justify-between border-b border-hairline bg-canvas",
            isHearth ? "h-16 px-8" : "h-12 px-6",
          ].join(" ")}
        >
          {/* Left: current page title, derived from the active route */}
          <div className="flex items-center gap-3">
            {isHearth ? (
              <span className="font-heading text-lg text-ink tracking-tight">
                {currentPageTitle(pathname)}
              </span>
            ) : (
              <>
                <span className="font-heading text-base text-ink tracking-tight">
                  {currentPageTitle(pathname)}
                </span>
                <span className="px-2 py-0.5 bg-surface border border-hairline font-mono text-[10px] uppercase tracking-widest text-muted rounded-meridian">
                  Meridian Deck
                </span>
              </>
            )}
          </div>

          {/* Right: mode toggle + orb slot */}
          <div className="flex items-center gap-4">
            <ModeToggle />
          </div>
        </header>

        {/* Page canvas */}
        <main
          className={[
            "w-full",
            isHearth ? "p-8 max-w-[1400px] mx-auto" : "p-3",
          ].join(" ")}
        >
          {children}
        </main>
      </div>

      <Orb />
    </div>
  )
}
