import { Card } from "@/components/ui/Card"
import { Button } from "@/components/ui/Button"

interface CustodianCardProps {
  pendingProposals: number
  onAsk: () => void
}

export function CustodianCard({ pendingProposals, onAsk }: CustodianCardProps) {
  return (
    <Card className="flex flex-col gap-4">
      <div>
        <h2 className="font-heading text-base font-medium text-ink">The Custodian</h2>
        <p className="mt-1 text-sm text-muted">
          {pendingProposals > 0
            ? `${pendingProposals} proposal${pendingProposals === 1 ? "" : "s"} awaiting review`
            : "No open proposals"}
        </p>
      </div>
      <Button variant="primary" onClick={onAsk} className="self-start">
        Ask the Custodian
      </Button>
    </Card>
  )
}
