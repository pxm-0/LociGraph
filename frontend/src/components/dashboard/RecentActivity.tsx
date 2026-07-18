import Link from "next/link"
import { NavIcon, type IconName } from "@/components/layout/NavIcon"
import { Card } from "@/components/ui/Card"
import type { ActivityItem, ActivityKind } from "@/lib/dashboard"

const ICON_FOR: Record<ActivityKind, IconName> = {
  source: "inventory_2",
  claim: "visibility",
  contradiction: "balance",
}

export function RecentActivity({ items }: { items: ActivityItem[] }) {
  return (
    <Card className="flex flex-col gap-1">
      <h2 className="mb-3 font-heading text-base font-medium text-ink">Recent Activity</h2>
      {items.length === 0 ? (
        <p className="text-sm text-muted">Nothing yet — import a source to get started.</p>
      ) : (
        <ul className="divide-y divide-hairline">
          {items.map((item, i) => (
            <li key={`${item.kind}-${i}`}>
              <Link
                href={item.href}
                className="flex items-center gap-3 py-2 text-sm text-ink transition-colors hover:text-accent"
              >
                <NavIcon name={ICON_FOR[item.kind]} aria-hidden className="h-4 w-4 shrink-0 text-muted" />
                <span className="truncate">{item.label}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
