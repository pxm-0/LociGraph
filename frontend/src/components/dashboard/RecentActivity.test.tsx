import { render, screen } from "@testing-library/react"
import { describe, expect, test } from "vitest"
import { RecentActivity } from "./RecentActivity"
import type { ActivityItem } from "@/lib/dashboard"

const items: ActivityItem[] = [
  { kind: "source", label: "export.zip", at: "2026-03-01", href: "/sources/1" },
  { kind: "claim", label: "A claim", at: "2026-02-01", href: "/claims/2" },
]

describe("RecentActivity", () => {
  test("renders items with links", () => {
    render(<RecentActivity items={items} />)
    expect(screen.getByText("export.zip").closest("a")).toHaveAttribute("href", "/sources/1")
    expect(screen.getByText("A claim").closest("a")).toHaveAttribute("href", "/claims/2")
  })

  test("renders an empty state", () => {
    render(<RecentActivity items={[]} />)
    expect(screen.getByText(/Nothing yet/i)).toBeInTheDocument()
  })
})
