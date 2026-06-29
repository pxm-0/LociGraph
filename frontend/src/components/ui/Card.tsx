import type { HTMLAttributes } from "react"

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  className?: string
}

export function Card({ className = "", children, ...props }: CardProps) {
  return (
    <div
      className={`rounded-hearth border border-whisper bg-chamber p-4 ${className}`}
      {...props}
    >
      {children}
    </div>
  )
}
