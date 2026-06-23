"use client"

import { useMode } from "@/lib/theme"
import type { Mode } from "@/lib/theme"

const MODE_LABELS: Record<Mode, string> = {
  hearth: "Hearth",
  meridian: "Meridian",
}

const NEXT_MODE_LABELS: Record<Mode, string> = {
  hearth: "Switch to Meridian",
  meridian: "Switch to Hearth",
}

export function ModeToggle() {
  const { mode, toggle } = useMode()

  return (
    <button
      onClick={toggle}
      title={NEXT_MODE_LABELS[mode]}
      aria-label={NEXT_MODE_LABELS[mode]}
      className="flex items-center gap-2 px-3 py-1.5 rounded-meridian border border-whisper bg-chamber text-ash hover:text-dust hover:border-ash transition-all duration-200 font-ui text-xs font-medium tracking-wide uppercase"
    >
      <span
        className="material-symbols-outlined text-base"
        aria-hidden="true"
        style={{ fontVariationSettings: "'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 20" }}
      >
        {mode === "hearth" ? "toggle_off" : "toggle_on"}
      </span>
      <span>{MODE_LABELS[mode]}</span>
    </button>
  )
}
