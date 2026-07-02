import type { ButtonHTMLAttributes } from "react"

type Variant = "primary" | "ghost"

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-ember text-void font-ui font-medium hover:opacity-90 active:opacity-75 disabled:opacity-40",
  ghost:
    "bg-transparent text-muted border border-hairline font-ui font-medium hover:text-ink hover:border-accent disabled:opacity-40",
}

export function Button({
  variant = "primary",
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center rounded-hearth px-4 py-2 text-sm transition-opacity ${VARIANT_CLASSES[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
