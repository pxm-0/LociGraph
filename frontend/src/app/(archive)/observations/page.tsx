"use client";

import { useEffect, useMemo, useState } from "react";

import { api, formatDate, Observation, Source } from "@/lib/api";

export default function ObservationsPage() {
  const [observations, setObservations] = useState<Observation[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [speaker, setSpeaker] = useState("");
  const [status, setStatus] = useState("active");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.sources().then(setSources).catch(() => undefined);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (sourceId) {
      params.set("source_id", sourceId);
    }
    if (speaker) {
      params.set("speaker", speaker);
    }
    if (status) {
      params.set("status", status);
    }
    api.observations(params).then(setObservations).catch((err) => setError(err.message));
  }, [sourceId, speaker, status]);

  const sourceNames = useMemo(
    () => new Map(sources.map((source) => [source.id, source.original_filename || source.id])),
    [sources]
  );

  return (
    <div className="mx-auto max-w-5xl text-[#172322]">
      <h1 className="font-display text-3xl font-semibold">Observations</h1>
      <div className="mt-5 grid gap-3 rounded-[10px] border border-teal/10 bg-white/55 p-4 md:grid-cols-[1fr_1fr_0.7fr]">
        <select
          className="focus-ring h-10 rounded-md border border-teal/10 bg-white px-3 text-sm"
          onChange={(event) => setSourceId(event.target.value)}
          value={sourceId}
        >
          <option value="">All sources</option>
          {sources.map((source) => (
            <option key={source.id} value={source.id}>
              {source.original_filename || source.id}
            </option>
          ))}
        </select>
        <input
          className="focus-ring h-10 rounded-md border border-teal/10 bg-white px-3 text-sm"
          onChange={(event) => setSpeaker(event.target.value)}
          placeholder="Speaker"
          value={speaker}
        />
        <select
          className="focus-ring h-10 rounded-md border border-teal/10 bg-white px-3 text-sm"
          onChange={(event) => setStatus(event.target.value)}
          value={status}
        >
          <option value="">Any status</option>
          <option value="active">active</option>
          <option value="archived">archived</option>
          <option value="deleted">deleted</option>
          <option value="superseded">superseded</option>
        </select>
      </div>

      {error ? <div className="mt-4 rounded-md border border-[#8C3D3D]/30 p-4 text-sm">{error}</div> : null}

      <section className="mt-5 space-y-3">
        {observations.map((observation) => (
          <article
            className="rounded-[10px] border border-teal/10 border-l-4 border-l-teal bg-white/70 p-5"
            key={observation.id}
          >
            <p className="max-w-[65ch] font-display text-[15px] leading-7">
              {observation.content}
            </p>
            <div className="mt-4 font-mono text-[11px] text-[#66807d]">
              {formatDate(observation.observed_at)} /{" "}
              {observation.source_id ? sourceNames.get(observation.source_id) : "no source"} /{" "}
              {observation.speaker || "unknown speaker"} / {observation.confidence.toFixed(2)}
            </div>
          </article>
        ))}
        {observations.length === 0 ? (
          <div className="rounded-[10px] border border-teal/10 bg-white/55 p-6 text-sm text-[#66807d]">
            No observations match the current filters.
          </div>
        ) : null}
      </section>
    </div>
  );
}
