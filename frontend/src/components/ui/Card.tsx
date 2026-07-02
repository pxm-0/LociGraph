import type { HTMLAttributes } from "react"

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  className?: string
}

export function Card({ className = "", children, ...props }: CardProps) {
  return (
    <div
      className={`rounded-hearth border border-hairline bg-surface p-4 ${className}`}
      {...props}
    >
      {children}
    </div>
  )
}
