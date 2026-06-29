import type { Observation, Source, SourceType } from "./types"

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = "ApiError"
  }
}

const JSON_HEADERS = { "Content-Type": "application/json" }
const base = (path: string) => `/api${path}`

async function req(path: string, init?: RequestInit): Promise<Response> {
  return fetch(base(path), { credentials: "include", ...init })
}

export async function login(password: string): Promise<{ userId: string }> {
  const r = await req("/auth/login", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ password }) })
  if (!r.ok) throw new ApiError(r.status, "login failed")
  const d = await r.json()
  return { userId: d.user_id }
}

export async function logout(): Promise<void> {
  await req("/auth/logout", { method: "POST" })
}

export async function me(): Promise<{ userId: string } | null> {
  const r = await req("/auth/me")
  if (r.status === 401) return null
  if (!r.ok) throw new ApiError(r.status, "me failed")
  const d = await r.json()
  return { userId: d.user_id }
}

function toSource(d: Record<string, unknown>): Source {
  return {
    id: String(d.id),
    sourceType: String(d.source_type),
    originalFilename: (d.original_filename as string | null) ?? null,
    importStatus: String(d.import_status),
    fileSizeBytes: (d.file_size_bytes as number | null) ?? null,
  }
}

export async function listSources(): Promise<Source[]> {
  const r = await req("/sources")
  if (!r.ok) throw new ApiError(r.status, "listSources failed")
  return (await r.json()).map(toSource)
}

export async function getSource(id: string): Promise<Source | null> {
  const r = await req(`/sources/${id}`)
  if (r.status === 404) return null
  if (!r.ok) throw new ApiError(r.status, "getSource failed")
  return toSource(await r.json())
}

export async function uploadSource(sourceType: SourceType, file: File): Promise<{ sourceId: string; status: string }> {
  const form = new FormData()
  form.set("source_type", sourceType)
  form.set("file", file)
  const r = await req("/sources/upload", { method: "POST", body: form })
  if (!r.ok) throw new ApiError(r.status, "upload failed")
  const d = await r.json()
  return { sourceId: d.source_id, status: d.status }
}

export interface ObservationQuery {
  sourceId?: string
  speaker?: string
  status?: string
  limit?: number
  offset?: number
}

export async function listObservations(q: ObservationQuery = {}): Promise<Observation[]> {
  const params = new URLSearchParams()
  if (q.sourceId) params.set("source_id", q.sourceId)
  if (q.speaker) params.set("speaker", q.speaker)
  if (q.status) params.set("status", q.status)
  if (q.limit != null) params.set("limit", String(q.limit))
  if (q.offset != null) params.set("offset", String(q.offset))
  const r = await req(`/observations?${params.toString()}`)
  if (!r.ok) throw new ApiError(r.status, "listObservations failed")
  return (await r.json()).map((d: Record<string, unknown>) => ({
    id: String(d.id),
    content: String(d.content),
    speaker: (d.speaker as string | null) ?? null,
    observedAt: (d.observed_at as string | null) ?? null,
    confidence: Number(d.confidence),
    sourceId: (d.source_id as string | null) ?? null,
  }))
}
