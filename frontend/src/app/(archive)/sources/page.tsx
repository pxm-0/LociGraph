"use client";

import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";

import { StatusBadge } from "@/components/status-badge";
import { api, formatBytes, formatDate, Source } from "@/lib/api";

const statuses = ["ALL", "PENDING", "INGESTING", "VERIFIED", "QUARANTINED", "PURGED"];

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [status, setStatus] = useState("ALL");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.sources().then(setSources).catch((err) => setError(err.message));
  }, []);

  const filtered = useMemo(
    () =>
      sources.filter((source) => {
        const matchesStatus = status === "ALL" || source.import_status === status;
        const name = source.original_filename || "";
        const matchesQuery = name.toLowerCase().includes(query.toLowerCase());
        return matchesStatus && matchesQuery;
      }),
    [sources, status, query]
  );

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display text-3xl font-semibold">
          Sources <span className="font-mono text-base text-ember">{sources.length}</span>
        </h1>
        <div className="flex items-center gap-2 rounded-md border border-dust/[0.08] px-3 py-2">
          <Search className="h-4 w-4 text-ash" />
          <input
            className="focus-ring w-44 bg-transparent text-sm text-dust placeholder:text-ash"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter sources"
            value={query}
          />
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {statuses.map((item) => (
          <button
            className={`rounded-md border px-3 py-1.5 font-mono text-xs ${
              status === item
                ? "border-ember/40 bg-ember/10 text-ember"
                : "border-dust/[0.07] text-ash"
            }`}
            key={item}
            onClick={() => setStatus(item)}
            type="button"
          >
            {item}
          </button>
        ))}
      </div>

      {error ? <div className="rounded-md border border-[#8C3D3D]/30 p-4 text-sm">{error}</div> : null}

      <div className="space-y-3 md:hidden">
        {filtered.map((source) => (
          <article
            className="rounded-md border border-teal/10 bg-white/55 p-4 text-[#172322]"
            key={source.id}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-display text-sm">
                  {source.original_filename || "Unnamed source"}
                </div>
                <div className="mt-1 font-mono text-xs text-[#66807d]">
                  {source.source_type} / {formatDate(source.imported_at)}
                </div>
              </div>
              <StatusBadge status={source.import_status} />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 font-mono text-xs text-[#66807d]">
              <div>{formatBytes(source.file_size_bytes)}</div>
              <div className="text-right text-ember">
                {source.observation_count} observations
              </div>
            </div>
          </article>
        ))}
        {filtered.length === 0 ? (
          <div className="rounded-md border border-teal/10 bg-white/55 p-4 text-sm text-[#66807d]">
            No matching sources.
          </div>
        ) : null}
      </div>

      <div className="hidden border-t border-dust/[0.08] md:block">
        <table className="w-full min-w-[820px] border-collapse text-left">
          <thead>
            <tr className="font-mono text-[11px] uppercase text-ash">
              <th className="py-3 font-normal">Filename</th>
              <th className="py-3 font-normal">Type</th>
              <th className="py-3 font-normal">Status</th>
              <th className="py-3 font-normal">Size</th>
              <th className="py-3 font-normal">Imported</th>
              <th className="py-3 text-right font-normal">Observations</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((source) => (
              <tr className="border-t border-dust/[0.07] hover:bg-dust/[0.03]" key={source.id}>
                <td className="py-4 pr-4 font-display text-sm">
                  {source.original_filename || "Unnamed source"}
                </td>
                <td className="py-4 pr-4 font-mono text-xs text-ember">{source.source_type}</td>
                <td className="py-4 pr-4">
                  <StatusBadge status={source.import_status} />
                </td>
                <td className="py-4 pr-4 font-mono text-xs text-ash">
                  {formatBytes(source.file_size_bytes)}
                </td>
                <td className="py-4 pr-4 font-mono text-xs text-ash">
                  {formatDate(source.imported_at)}
                </td>
                <td className="py-4 text-right font-mono text-sm text-ember">
                  {source.observation_count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 ? (
          <div className="border-t border-dust/[0.07] py-8 text-sm text-ash">
            No matching sources.
          </div>
        ) : null}
      </div>
    </div>
  );
}
