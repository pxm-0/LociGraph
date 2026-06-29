import type { ButtonHTMLAttributes } from "react"

type Variant = "primary" | "ghost"

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-ember text-void font-ui font-medium hover:opacity-90 active:opacity-75 disabled:opacity-40",
  ghost:
    "bg-transparent text-ash border border-whisper font-ui font-medium hover:text-dust hover:border-ash disabled:opacity-40",
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
