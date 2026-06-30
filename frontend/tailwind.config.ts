import type { Config } from "tailwindcss";

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
        hearth: "#f4fbfa",
        teal: "#2d6a6a",
        ledge: "#28221d"
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)"],
        mono: ["var(--font-geist-mono)"],
        display: ["var(--font-outfit)"]
      }
    }
  },
  plugins: []
};

export default config;
