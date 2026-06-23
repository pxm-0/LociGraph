import type { ReactNode } from "react"
import { ThemeProvider } from "@/lib/theme"
import { AppChrome } from "@/components/layout/AppChrome"

// Server component — no "use client" needed; ThemeProvider and AppChrome are client components
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <AppChrome>{children}</AppChrome>
    </ThemeProvider>
  )
}
