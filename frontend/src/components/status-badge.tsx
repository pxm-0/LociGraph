const styles: Record<string, string> = {
  VERIFIED: "border-[#5A8C5A]/30 bg-[#5A8C5A]/16 text-[#B7D2B7]",
  INGESTING: "border-ember/40 bg-ember/10 text-[#F1C48C]",
  PENDING: "border-ash/30 bg-ash/10 text-ash",
  FAILED: "border-[#8C3D3D]/40 bg-[#8C3D3D]/18 text-[#E5A2A2]",
  QUARANTINED: "border-[#8C6A2A]/40 bg-[#8C6A2A]/18 text-[#E7CB86]",
  PURGED: "border-ash/20 bg-transparent text-ash"
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex h-6 items-center rounded-md border px-2 font-mono text-[11px] uppercase tracking-normal ${
        styles[status] ?? "border-ash/25 bg-ash/10 text-ash"
      }`}
    >
      {status}
    </span>
  );
}
