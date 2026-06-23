"use client"
import { createContext, useContext, useEffect, useMemo, useState } from "react"

export type Mode = "hearth" | "meridian"
const KEY = "locigraph-mode"

interface ThemeCtx {
  mode: Mode
  toggle(): void
  setMode(m: Mode): void
}

const Ctx = createContext<ThemeCtx | null>(null)

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<Mode>("hearth")

  useEffect(() => {
    const saved = localStorage.getItem(KEY)
    if (saved === "hearth" || saved === "meridian") setMode(saved)
  }, [])

  useEffect(() => {
    localStorage.setItem(KEY, mode)
  }, [mode])

  const toggle = () => setMode((m) => (m === "hearth" ? "meridian" : "hearth"))

  const value = useMemo<ThemeCtx>(
    () => ({ mode, toggle, setMode }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mode],
  )

  return (
    <div data-mode={mode} className="min-h-screen">
      <Ctx.Provider value={value}>{children}</Ctx.Provider>
    </div>
  )
}

export function useMode(): ThemeCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error("useMode must be used within ThemeProvider")
  return ctx
}
