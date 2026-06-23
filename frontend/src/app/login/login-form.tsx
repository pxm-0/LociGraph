"use client"
import { useState } from "react"
import { useRouter } from "next/navigation"
import { login, ApiError } from "@/lib/api"
import { Button } from "@/components/ui/Button"
import { Input } from "@/components/ui/Input"

export function LoginForm() {
  const router = useRouter()
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)
    try {
      await login(password)
      router.replace("/dashboard")
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Invalid password. Please try again.")
      } else {
        setError("An unexpected error occurred.")
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <label htmlFor="password" className="text-sm font-ui text-ash">
        Password
      </label>
      <Input
        id="password"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Enter your password"
        autoComplete="current-password"
        disabled={pending}
      />
      {error && (
        <p role="alert" className="text-sm font-ui text-ember">
          {error}
        </p>
      )}
      <Button type="submit" disabled={pending}>
        Enter Archive
      </Button>
    </form>
  )
}
