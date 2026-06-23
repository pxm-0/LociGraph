"use client"

import type { ReactNode } from "react"
import { useMode } from "@/lib/theme"
import { Sidebar } from "@/components/layout/Sidebar"
import { ModeToggle } from "@/components/layout/ModeToggle"

// AppChrome reads mode after ThemeProvider mounts — must be a client component
export function AppChrome({ children }: { children: ReactNode }) {
  const { mode } = useMode()

  const isHearth = mode === "hearth"

  return (
    <div
      className={[
        "min-h-screen",
        isHearth ? "bg-hearth-surface" : "bg-archive",
      ].join(" ")}
    >
      {/* Mode-adaptive sidebar */}
      <Sidebar />

      {/* Main content area shifted by sidebar width */}
      <div className={isHearth ? "ml-60" : "ml-16"}>
        {/* Top app bar */}
        <header
          className={[
            "sticky top-0 z-30 flex items-center justify-between border-b border-whisper bg-archive",
            isHearth ? "h-16 px-8" : "h-12 px-6",
          ].join(" ")}
        >
          {/* Left: page title slot (filled by page via <title> or a context — kept minimal here) */}
          <div className="flex items-center gap-3">
            {isHearth ? (
              <span className="font-heading text-lg text-dust tracking-tight">Archive Overview</span>
            ) : (
              <>
                <span className="font-heading text-base text-dust tracking-tight">LociGraph</span>
                <span className="px-2 py-0.5 bg-chamber border border-whisper font-mono text-[10px] uppercase tracking-widest text-ash rounded-meridian">
                  Meridian Deck
                </span>
              </>
            )}
          </div>

          {/* Right: mode toggle + orb slot */}
          <div className="flex items-center gap-4">
            {/* Orb/Core companion — deferred (Plan 4 scope: dual-mode, Orb later) */}
            <div data-orb-slot className="hidden" aria-hidden="true" />
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
    </div>
  )
}
