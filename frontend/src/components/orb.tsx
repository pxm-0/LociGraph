export function Orb({ mode }: { mode: "hearth" | "meridian" }) {
  const hearth = mode === "hearth";
  return (
    <div
      aria-hidden="true"
      className={
        hearth
          ? "fixed bottom-6 right-6 z-20 h-16 w-16 rounded-full border border-teal/25 bg-teal/20 shadow-[0_0_34px_rgba(45,106,106,0.24)]"
          : "fixed bottom-5 left-1/2 z-20 h-14 w-14 -translate-x-1/2 rounded-full border border-ember/35 bg-ember/10 shadow-[0_0_30px_rgba(212,136,47,0.2)]"
      }
      style={{ animation: "orb-breathe 1.4s ease-in-out infinite" }}
    >
      <div
        className={
          hearth
            ? "m-3 h-10 w-10 rounded-full bg-teal/50"
            : "m-3 h-8 w-8 rounded-full border border-ember/50 bg-archive"
        }
      />
    </div>
  );
}
