import type { Metadata } from "next";
import { Outfit } from "next/font/google";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import "./globals.css";

const outfit = Outfit({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-outfit"
});

export const metadata: Metadata = {
  title: "LociGraph",
  description: "A concept-centric memory architecture."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable} ${outfit.variable}`}
      suppressHydrationWarning
    >
      <body>{children}</body>
    </html>
  );
}
