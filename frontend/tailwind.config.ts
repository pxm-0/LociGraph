import type { Config } from "tailwindcss"

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        void: "#0F0D0B",
        archive: "#141210",
        chamber: "#1E1A17",
        dust: "#F5EDE2",
        ash: "#A89070",
        ember: "#D4882F",
        "hearth-surface": "#f4fbfa",
        "hearth-accent": "#2d6a6a",
        "status-verified": "#5A8C5A",
        "status-ingesting": "#D4882F",
        "status-quarantined": "#8C6A2A",
        whisper: "rgba(245,237,226,0.07)",
        "whisper-faint": "rgba(245,237,226,0.03)",
        "chamber-hover": "#26211d",
      },
      borderRadius: { hearth: "10px", meridian: "6px" },
      fontFamily: {
        heading: ["var(--font-outfit)", "sans-serif"],
        ui: ["var(--font-geist)", "sans-serif"],
        mono: ["var(--font-geist-mono)", "monospace"],
      },
    },
  },
  plugins: [],
}
export default config
