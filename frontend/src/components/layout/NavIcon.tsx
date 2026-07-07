/**
 * Inline SVG icon component replacing the Material Symbols icon font.
 * Self-hosted: no CDN dependency, no font requests, CSP-safe.
 *
 * Icons are line-art SVGs matching Material Symbols Outlined style at 24x24.
 */

import type { ReactNode } from "react"

export type IconName =
  | "dashboard"
  | "inventory_2"
  | "database"
  | "visibility"
  | "analytics"
  | "hub"
  | "search"
  | "orbit"
  | "toggle_off"
  | "toggle_on"

interface NavIconProps {
  name: IconName
  className?: string
  "aria-hidden"?: boolean | "true" | "false"
  "aria-label"?: string
}

const ICONS: Record<IconName, ReactNode> = {
  dashboard: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  ),
  inventory_2: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="6" width="18" height="15" rx="1.5" />
      <path d="M3 6l2-3h14l2 3" />
      <path d="M9 12h6" />
    </svg>
  ),
  database: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="6" rx="8" ry="3" />
      <path d="M4 6v6c0 1.657 3.582 3 8 3s8-1.343 8-3V6" />
      <path d="M4 12v6c0 1.657 3.582 3 8 3s8-1.343 8-3v-6" />
    </svg>
  ),
  visibility: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  ),
  analytics: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
      <line x1="3" y1="20" x2="21" y2="20" />
    </svg>
  ),
  hub: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="5" r="2.5" />
      <circle cx="5" cy="19" r="2.5" />
      <circle cx="19" cy="19" r="2.5" />
      <path d="M12 7.5L7 16.5" />
      <path d="M12 7.5l5 9" />
    </svg>
  ),
  search: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  ),
  orbit: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" />
      <ellipse cx="12" cy="12" rx="10" ry="4.5" />
      <circle cx="20.5" cy="12" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  ),
  toggle_off: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="7" width="22" height="10" rx="5" />
      <circle cx="7" cy="12" r="3" fill="currentColor" stroke="none" />
    </svg>
  ),
  toggle_on: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="7" width="22" height="10" rx="5" />
      <circle cx="17" cy="12" r="3" fill="currentColor" stroke="none" />
    </svg>
  ),
}

export function NavIcon({ name, className, ...props }: NavIconProps) {
  return (
    <span className={className} {...props} style={{ display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
      {ICONS[name]}
    </span>
  )
}
