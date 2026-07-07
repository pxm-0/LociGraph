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
        // Status colors are mode-aware too — the Meridian hex values are too
        // light to clear 4.5:1 against Hearth's canvas (see globals.css).
        "status-verified": "var(--color-status-verified)",
        "status-ingesting": "var(--color-status-ingesting)",
        "status-quarantined": "var(--color-status-quarantined)",
        "status-failed": "var(--color-status-failed)",
        whisper: "rgba(245,237,226,0.07)",
        "whisper-faint": "rgba(245,237,226,0.03)",
        "chamber-hover": "#26211d",
        // Mode-aware semantic tokens — resolve via the CSS variables in
        // globals.css, which flip on the ThemeProvider's [data-mode]
        // attribute. Use these for any page/component content that must
        // read correctly in both Hearth and Meridian; use the literal
        // colors above only for chrome that's intentionally single-mode.
        canvas: "var(--color-canvas)",
        surface: "var(--color-surface)",
        "surface-hover": "var(--color-surface-hover)",
        ink: "var(--color-text-primary)",
        muted: "var(--color-text-secondary)",
        hairline: "var(--color-border)",
        accent: "var(--color-accent)",
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
