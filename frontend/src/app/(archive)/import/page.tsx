"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";
import { FileUp, UploadCloud } from "lucide-react";

import { StatusBadge } from "@/components/status-badge";
import { api, Job, SourceType, UploadResult } from "@/lib/api";

const formats: Array<{ type: SourceType; label: string; ext: string }> = [
  { type: "json", label: "JSON", ext: ".json" },
  { type: "markdown", label: "Markdown", ext: ".md" },
  { type: "html", label: "HTML", ext: ".html" },
  { type: "pdf", label: "PDF", ext: ".pdf" },
  { type: "chatgpt", label: "ChatGPT", ext: "export" },
  { type: "meta", label: "Meta", ext: "export" }
];

export default function ImportPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [sourceType, setSourceType] = useState<SourceType>("json");
  const [file, setFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!upload?.job_id) {
      return;
    }
    const id = window.setInterval(() => {
      api.job(upload.job_id).then(setJob).catch(() => undefined);
    }, 1400);
    api.job(upload.job_id).then(setJob).catch(() => undefined);
    return () => window.clearInterval(id);
  }, [upload]);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setError(null);
  }

  async function submit() {
    if (!file) {
      return;
    }
    setBusy(true);
    setError(null);
    setUpload(null);
    setJob(null);
    try {
      const result = await api.uploadSource(sourceType, file);
      setUpload(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl rounded-[10px] bg-archive p-6 text-dust md:p-8">
      <h1 className="font-display text-[28px] font-semibold">Import Source</h1>
      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-[12px] border border-dashed border-ember/30 bg-chamber p-8">
          <UploadCloud className="h-8 w-8 text-ash" />
          <div className="mt-5 font-display text-lg">Drop files here</div>
          <div className="mt-2 text-sm text-ash">
            JSON / PDF / HTML / Markdown / ChatGPT export / Meta export
          </div>
          <input className="hidden" onChange={chooseFile} ref={inputRef} type="file" />
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <button
              className="focus-ring rounded-md bg-ember px-4 py-2 text-sm font-medium text-archive"
              onClick={() => inputRef.current?.click()}
              type="button"
            >
              Browse Files
            </button>
            <button
              className="focus-ring inline-flex items-center gap-2 rounded-md border border-dust/[0.09] px-4 py-2 text-sm disabled:border-dust/[0.16] disabled:text-ash"
              disabled={!file || busy}
              onClick={submit}
              type="button"
            >
              <FileUp className="h-4 w-4" />
              {busy ? "Uploading" : "Upload"}
            </button>
            {file ? <span className="text-sm text-ash">{file.name}</span> : null}
          </div>
          {error ? <p className="mt-4 text-sm text-[#E5A2A2]">{error}</p> : null}
          {upload ? (
            <div className="mt-6 rounded-md border border-dust/[0.07] bg-archive p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="font-mono text-xs uppercase text-ash">Ingest Job</div>
                  <div className="mt-1 max-w-full truncate font-mono text-xs text-dust">
                    {upload.job_id}
                  </div>
                </div>
                <StatusBadge status={job?.status?.toUpperCase() ?? upload.status} />
              </div>
              {job?.status === "running" || job?.status === "pending" ? (
                <div className="mt-4 h-1 overflow-hidden rounded bg-dust/10">
                  <div
                    className="h-full w-1/2 bg-ember"
                    style={{ animation: "ember-progress 1.2s linear infinite" }}
                  />
                </div>
              ) : null}
            </div>
          ) : null}
        </section>

        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
          {formats.map((format) => (
            <button
              className={`rounded-md border p-4 text-left transition ${
                sourceType === format.type
                  ? "border-ember/50 bg-ember/10"
                  : "border-dust/[0.07] bg-chamber"
              }`}
              key={format.type}
              onClick={() => setSourceType(format.type)}
              type="button"
            >
              <div className="font-display text-base">{format.label}</div>
              <div className="mt-1 font-mono text-xs text-ember">{format.ext}</div>
            </button>
          ))}
        </section>
      </div>
    </div>
  );
}
