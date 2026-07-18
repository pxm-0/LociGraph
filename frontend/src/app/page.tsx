"use client"
import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { me } from "@/lib/api"
import { Landing } from "@/components/landing/Landing"

// Root page: render the public landing by default (so first-time visitors see
// no login flash), and only redirect confirmed-authed owners to /dashboard.
// Running me() in the browser avoids relative-URL resolution issues behind the
// Caddy reverse proxy that does not forward the host header.
//
// The landing commits to the dark cosmic (Meridian) look regardless of the
// stored app theme, so we pin data-mode here rather than mounting ThemeProvider.
export default function RootPage() {
  const router = useRouter()

  useEffect(() => {
    me().then((user) => {
      if (user) router.replace("/dashboard")
    })
  }, [router])

  return (
    <div data-mode="meridian">
      <Landing />
    </div>
  )
}
