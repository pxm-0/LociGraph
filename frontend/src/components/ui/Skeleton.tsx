import type { HTMLAttributes } from "react"

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  className?: string
}

export function Skeleton({ className = "", ...props }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse rounded-meridian bg-surface-hover ${className}`}
      aria-hidden="true"
      {...props}
    />
  )
}
