import { redirect } from "next/navigation"
import { me } from "@/lib/api"

// Force dynamic rendering: this page makes an auth fetch that requires request-time
// context (cookies) and a relative URL that only resolves at runtime, not build time.
export const dynamic = "force-dynamic"

// Root page: checks auth state server-side and redirects accordingly.
// me() reads the httpOnly session cookie via credentials: "include".
export default async function RootPage() {
  const user = await me()
  if (user) {
    redirect("/dashboard")
  } else {
    redirect("/login")
  }
}
