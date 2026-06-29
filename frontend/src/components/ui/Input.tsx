import type { InputHTMLAttributes } from "react"

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  className?: string
}

export function Input({ className = "", ...props }: InputProps) {
  return (
    <input
      className={`w-full rounded-meridian border border-whisper bg-archive px-3 py-2 font-ui text-sm text-dust placeholder:text-ash focus:outline-none focus:ring-1 focus:ring-ember disabled:opacity-40 ${className}`}
      {...props}
    />
  )
}
