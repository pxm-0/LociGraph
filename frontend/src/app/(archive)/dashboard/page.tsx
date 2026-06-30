"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { StatusBadge } from "@/components/status-badge";
import { api, DashboardSummary, formatDate } from "@/lib/api";

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .dashboard()
      .then(setSummary)
      .catch((err) => setError(err instanceof Error ? err.message : "Unable to load"));
  }, []);

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-8">
        <h1 className="font-display text-4xl font-semibold">Archive Overview</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-ash">
          Source intake, observation volume, and recent import state.
        </p>
      </div>

      {error ? <div className="rounded-md border border-[#8C3D3D]/30 p-4 text-sm">{error}</div> : null}

      <section className="grid gap-4 md:grid-cols-[1.1fr_1fr_0.9fr]">
        {[
          ["Sources", summary?.source_count],
          ["Observations", summary?.observation_count],
          ["Pending Jobs", summary?.pending_job_count]
        ].map(([label, value]) => (
          <div
            className="rounded-[10px] border border-teal/10 bg-white/55 p-5 text-[#172322]"
            key={label}
          >
            <div className="font-mono text-xs uppercase text-[#66807d]">{label}</div>
            <div className="mt-4 font-mono text-4xl text-teal">
              {typeof value === "number" ? value : "--"}
            </div>
          </div>
        ))}
      </section>

      <section className="mt-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-2xl font-medium">Recent Sources</h2>
          <Link className="text-sm text-teal" href="/sources">
            View sources
          </Link>
        </div>
        <div className="overflow-hidden rounded-[10px] border border-teal/10 bg-white/45">
          {(summary?.recent_sources ?? []).map((source) => (
            <div
              className="grid gap-3 border-t border-teal/10 px-4 py-4 first:border-t-0 md:grid-cols-[1fr_auto_auto]"
              key={source.id}
            >
              <div>
                <div className="font-display text-base">
                  {source.original_filename || "Unnamed source"}
                </div>
                <div className="mt-1 font-mono text-xs text-[#66807d]">
                  {source.source_type} / {formatDate(source.imported_at)}
                </div>
              </div>
              <div className="font-mono text-sm text-teal">
                {source.observation_count} observations
              </div>
              <StatusBadge status={source.import_status} />
            </div>
          ))}
          {summary && summary.recent_sources.length === 0 ? (
            <div className="p-6 text-sm text-[#66807d]">No sources imported yet.</div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
