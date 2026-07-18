"use client"

import dynamic from "next/dynamic"
import { EnterCta } from "./EnterCta"
import { StoryBeat } from "./StoryBeat"

// R3F bundle is lazy + client-only so the hero copy paints before it arrives.
const HeroStarfield = dynamic(() => import("./HeroStarfield"), { ssr: false })

const BEATS = [
  {
    heading: "Capture",
    title: "Bring in what you've already said",
    body: "Import ChatGPT exports, conversations, and documents. LociGraph turns them into observations without you re-typing a thing.",
  },
  {
    heading: "Distill",
    title: "Claims and concepts, extracted",
    body: "Every observation is mined for the claims it makes and the concepts it touches — automatically, in the background.",
  },
  {
    heading: "Reconcile",
    title: "Contradictions surface themselves",
    body: "When two claims disagree across the archive, LociGraph flags them so your knowledge stays honest with itself.",
  },
  {
    heading: "Explore",
    title: "A living map of your mind",
    body: "Wander the concept planetarium in 3D, or ask the Custodian to reason over the whole archive with you.",
  },
]

export function Landing() {
  return (
    <div className="min-h-screen bg-void text-dust">
      {/* Hero */}
      <section className="relative h-screen w-full overflow-hidden">
        <div className="absolute inset-0">
          <HeroStarfield />
        </div>
        {/* Overlay copy — pointer-events-none so drag never fights the canvas,
            re-enabled on the CTA. */}
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-6 bg-gradient-to-b from-void/40 via-transparent to-void px-6 text-center">
          <h1 className="font-heading text-6xl font-semibold tracking-tight text-dust">LociGraph</h1>
          <p className="max-w-xl text-lg text-ash">
            A personal knowledge engine that turns your conversations into a living, self-reconciling map of what you think.
          </p>
          <p className="font-mono text-xs uppercase tracking-widest text-ember">Capture · Distill · Reconcile · Explore</p>
          <EnterCta className="pointer-events-auto mt-2" />
          <span className="pointer-events-none mt-8 font-mono text-[11px] uppercase tracking-widest text-ash">
            Scroll to see how ↓
          </span>
        </div>
      </section>

      {/* Story scroll */}
      <div className="border-t border-whisper">
        {BEATS.map((beat) => (
          <StoryBeat key={beat.heading} {...beat} />
        ))}
      </div>

      {/* Closing CTA */}
      <footer className="flex flex-col items-center gap-4 border-t border-whisper px-6 py-24 text-center">
        <h2 className="font-heading text-2xl font-medium text-dust">Ready when you are.</h2>
        <EnterCta />
      </footer>
    </div>
  )
}
