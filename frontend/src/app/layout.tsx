import type { Metadata } from "next"
import type { ReactNode } from "react"
import { Outfit } from "next/font/google"
import { GeistSans } from "geist/font/sans"
import { GeistMono } from "geist/font/mono"
import "./globals.css"

const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit" })

export const metadata: Metadata = { title: "LociGraph" }

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      className={`${outfit.variable} ${GeistSans.variable} ${GeistMono.variable}`}
      style={{ ["--font-geist" as string]: GeistSans.style.fontFamily, ["--font-geist-mono" as string]: GeistMono.style.fontFamily }}
    >
      <body>{children}</body>
    </html>
  )
}
