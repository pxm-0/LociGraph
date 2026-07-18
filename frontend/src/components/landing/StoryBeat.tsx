interface StoryBeatProps {
  heading: string
  title: string
  body: string
  imageSrc?: string
}

// One beat of the story scroll: a short kicker, a title, one sentence, and an
// optional real UI screenshot.
export function StoryBeat({ heading, title, body, imageSrc }: StoryBeatProps) {
  return (
    <section className="mx-auto flex max-w-3xl flex-col gap-3 px-6 py-16">
      <p className="font-mono text-[11px] uppercase tracking-widest text-ember">{heading}</p>
      <h2 className="font-heading text-3xl font-medium text-dust">{title}</h2>
      <p className="max-w-prose text-base leading-relaxed text-ash">{body}</p>
      {imageSrc && (
        <img
          src={imageSrc}
          alt={`${title} — LociGraph interface`}
          className="mt-4 w-full rounded-hearth border border-whisper"
        />
      )}
    </section>
  )
}
