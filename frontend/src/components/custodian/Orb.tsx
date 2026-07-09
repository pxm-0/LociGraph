"use client"

import { useState } from "react"
import { useMode } from "@/lib/theme"
import { CustodianPanel } from "@/components/custodian/CustodianPanel"

export function Orb() {
  const { mode } = useMode()
  const [open, setOpen] = useState(false)
  const isHearth = mode === "hearth"

  return (
    <>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Open the Custodian"
        data-orb-slot
        className={[
          "fixed z-50 w-14 h-14 rounded-full [animation:orb-breathe_1.4s_ease-in-out_infinite]",
          isHearth
            ? "bottom-6 right-6 bg-accent shadow-[0_0_24px_rgba(45,106,106,0.35)]"
            : "bottom-6 right-6 bg-ember shadow-[0_0_24px_rgba(212,136,47,0.35)]",
        ].join(" ")}
      />
      {open && <CustodianPanel onClose={() => setOpen(false)} />}
    </>
  )
}
