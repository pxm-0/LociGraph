"use client"

import { useState } from "react"
import { acceptLoggedItem, rejectLoggedItem } from "@/lib/api"
import type { CustodianLoggedItem } from "@/lib/types"

function summarize(item: CustodianLoggedItem): string {
  const c = item.content
  switch (item.itemType) {
    case "observation":
      return `Log as observation: "${c.content}"`
    case "note":
      return `Save as note: "${c.content}"`
    case "claim":
      return `Log as claim (${c.claim_type}, ${c.assertion_type}): "${c.claim_text}"`
    case "task":
      return `Log as task: "${c.claim_text}"`
    case "concept_candidate":
      return `Link to concept "${c.candidate_name}" (${c.concept_type})`
    case "reality_assertion":
      return "Mark this claim as reality"
    case "perception_assertion":
      return "Mark this claim as perception"
    case "contradiction":
      return "Flag these two claims as contradicting each other"
    case "importance_signal":
      return `Pin this ${c.target_type} as important`
    case "contradiction_classification":
      return `Classify contradiction as ${c.classification}`
    default:
      return item.itemType
  }
}

export function ProposalCard({
  item,
  onResolved,
}: {
  item: CustodianLoggedItem
  onResolved: (item: CustodianLoggedItem) => void
}) {
  const [busy, setBusy] = useState(false)

  async function accept() {
    setBusy(true)
    onResolved(await acceptLoggedItem(item.id))
  }

  async function reject() {
    setBusy(true)
    onResolved(await rejectLoggedItem(item.id))
  }

  if (item.status !== "proposed") {
    return (
      <div className="text-xs text-muted italic px-3 py-2 border border-hairline rounded-meridian">
        {item.status === "accepted" ? `Logged: ${summarize(item)}` : "Rejected"}
      </div>
    )
  }

  return (
    <div className="border border-hairline rounded-meridian px-3 py-2 space-y-2">
      <div className="text-sm text-ink">{summarize(item)}</div>
      <div className="flex gap-2">
        <button
          onClick={accept}
          disabled={busy}
          className="px-2 py-1 rounded-meridian bg-accent text-canvas text-xs font-ui disabled:opacity-50"
        >
          Accept
        </button>
        <button
          onClick={reject}
          disabled={busy}
          className="px-2 py-1 rounded-meridian border border-hairline text-muted text-xs font-ui disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  )
}
