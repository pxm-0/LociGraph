const COLORS: Record<string, string> = {
  VERIFIED: "text-status-verified",
  INGESTING: "text-status-ingesting",
  PENDING: "text-status-ingesting",
  QUARANTINED: "text-status-quarantined",
  PURGED: "text-status-quarantined",
}

export function StatusBadge({ status }: { status: string }) {
  const color = COLORS[status] ?? "text-ash"
  return (
    <span className={`font-mono text-xs uppercase tracking-wide ${color}`}>
      {status === "INGESTING" && (
        <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-status-ingesting align-middle" />
      )}
      {status}
    </span>
  )
}
