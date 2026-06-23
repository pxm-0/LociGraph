import type { HTMLAttributes } from "react"

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  className?: string
}

export function Badge({ className = "", children, ...props }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border border-whisper bg-chamber px-2 py-0.5 font-ui text-xs text-ash ${className}`}
      {...props}
    >
      {children}
    </span>
  )
}
