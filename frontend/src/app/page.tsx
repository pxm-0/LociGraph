"use client"
import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { me } from "@/lib/api"

// Root page: checks auth state client-side and redirects accordingly.
// Running me() in the browser avoids relative-URL resolution issues behind
// the Caddy reverse proxy that does not forward the host header.
export default function RootPage() {
  const router = useRouter()

  useEffect(() => {
    me().then((user) => {
      if (user) {
        router.replace("/dashboard")
      } else {
        router.replace("/login")
      }
    })
  }, [router])

  return null
}
