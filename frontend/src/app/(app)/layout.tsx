import type { ReactNode } from "react"
import { ThemeProvider } from "@/lib/theme"
import { AppChrome } from "@/components/layout/AppChrome"
import { AuthGate } from "./auth-gate"

// Server component — no "use client" needed; ThemeProvider, AppChrome, and AuthGate are client components.
// AuthGate calls me() on mount and redirects to /login if not authed.
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <AuthGate>
        <AppChrome>{children}</AppChrome>
      </AuthGate>
    </ThemeProvider>
  )
}
