import Link from "next/link"
import { Button } from "@/components/ui/Button"

// Single primary CTA for the landing. Single-password model: "Enter" goes to
// the login screen, not a signup flow.
export function EnterCta({ className = "" }: { className?: string }) {
  return (
    <Link href="/login" className={className}>
      <Button variant="primary">Enter</Button>
    </Link>
  )
}
