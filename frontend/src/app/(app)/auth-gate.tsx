"use client"
import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import type { ReactNode } from "react"
import { me } from "@/lib/api"

interface AuthGateProps {
  children: ReactNode
}

// Client-side guard: calls me() on mount; redirects to /login if not authed.
// Renders children only once auth is confirmed to prevent flash of protected content.
export function AuthGate({ children }: AuthGateProps) {
  const router = useRouter()
  const [confirmed, setConfirmed] = useState(false)

  useEffect(() => {
    me()
      .then((user) => {
        if (!user) {
          router.replace("/login")
        } else {
          setConfirmed(true)
        }
      })
      .catch(() => router.replace("/login"))
  }, [router])

  if (!confirmed) return null

  return <>{children}</>
}
