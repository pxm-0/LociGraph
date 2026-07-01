import type {
  Claim,
  Concept,
  ConceptCandidate,
  DashboardSummary,
  Job,
  Observation,
  Source,
  SourceType,
} from "./types"

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

async function readError(response: Response, fallback: string): Promise<ApiError> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    return new ApiError(response.status, String(body.detail ?? fallback))
  } catch {
    return new ApiError(response.status, fallback)
  }
}

function toSource(d: Record<string, unknown>): Source {
  const source: Source = {
    id: String(d.id),
    sourceType: String(d.source_type),
    originalFilename: (d.original_filename as string | null) ?? null,
    importStatus: String(d.import_status),
    fileSizeBytes: (d.file_size_bytes as number | null) ?? null,
    importedAt: (d.imported_at as string | null) ?? null,
    observationCount: Number(d.observation_count ?? 0),
    claimCount: Number(d.claim_count ?? 0),
    claimExtractionStatus: String(d.claim_extraction_status ?? "waiting"),
  }
  return source
}

function toObservation(d: Record<string, unknown>): Observation {
  return {
    id: String(d.id),
    content: String(d.content),
    speaker: (d.speaker as string | null) ?? null,
    observedAt: (d.observed_at as string | null) ?? null,
    confidence: Number(d.confidence),
    sourceId: (d.source_id as string | null) ?? null,
  }
}

function toJob(d: Record<string, unknown>): Job {
  return {
    id: String(d.id),
    jobType: String(d.job_type),
    status: String(d.status),
    attempts: Number(d.attempts ?? 0),
    error: (d.error as string | null) ?? null,
    createdAt: (d.created_at as string | null) ?? null,
    startedAt: (d.started_at as string | null) ?? null,
    completedAt: (d.completed_at as string | null) ?? null,
  }
}

function toClaim(d: Record<string, unknown>): Claim {
  return {
    id: String(d.id),
    sourceId: String(d.source_id),
    observationId: String(d.observation_id),
    claimText: String(d.claim_text),
    claimType: String(d.claim_type),
    confidence: Number(d.confidence),
    extractionMethod: String(d.extraction_method),
    modelName: (d.model_name as string | null) ?? null,
    promptVersion: (d.prompt_version as string | null) ?? null,
    status: String(d.status),
    createdAt: String(d.created_at),
  }
}

function toConceptCandidate(d: Record<string, unknown>): ConceptCandidate {
  return {
    id: String(d.id),
    sourceId: String(d.source_id),
    claimId: String(d.claim_id),
    candidateName: String(d.candidate_name),
    conceptType: String(d.concept_type),
    rationale: (d.rationale as string | null) ?? null,
    confidence: Number(d.confidence),
    status: String(d.status),
    createdAt: String(d.created_at),
  }
}

function toConcept(d: Record<string, unknown>): Concept {
  return {
    id: String(d.id),
    conceptName: String(d.concept_name),
    conceptType: String(d.concept_type),
    description: (d.description as string | null) ?? null,
    status: String(d.status),
    createdAt: String(d.created_at),
    claimCount: Number(d.claim_count ?? 0),
  }
}

export async function login(password: string): Promise<{ userId: string }> {
  const r = await req("/auth/login", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ password }) })
  if (!r.ok) throw await readError(r, "login failed")
  const d = await r.json()
  return { userId: d.user_id }
}

export async function logout(): Promise<void> {
  await req("/auth/logout", { method: "POST" })
}

export async function me(): Promise<{ userId: string } | null> {
  const r = await req("/auth/me")
  if (r.status === 401) return null
  if (!r.ok) throw await readError(r, "me failed")
  const d = await r.json()
  return { userId: d.user_id }
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  const r = await req("/dashboard/summary")
  if (!r.ok) throw await readError(r, "dashboard failed")
  const d = await r.json()
  return {
    sourceCount: Number(d.source_count ?? 0),
    observationCount: Number(d.observation_count ?? 0),
    pendingJobCount: Number(d.pending_job_count ?? 0),
    recentSources: ((d.recent_sources ?? []) as Record<string, unknown>[]).map(toSource),
  }
}

export async function listSources(): Promise<Source[]> {
  const r = await req("/sources")
  if (!r.ok) throw await readError(r, "listSources failed")
  return (await r.json()).map(toSource)
}

export async function getSource(id: string): Promise<Source | null> {
  const r = await req(`/sources/${id}`)
  if (r.status === 404) return null
  if (!r.ok) throw await readError(r, "getSource failed")
  return toSource(await r.json())
}

export async function uploadSource(
  sourceType: SourceType,
  file: File
): Promise<{ sourceId: string; jobId?: string; status: string }> {
  const form = new FormData()
  form.set("source_type", sourceType)
  form.set("file", file)
  const r = await req("/sources/upload", { method: "POST", body: form })
  if (!r.ok) throw await readError(r, "upload failed")
  const d = await r.json()
  return { sourceId: d.source_id, jobId: d.job_id, status: d.status }
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
  if (!r.ok) throw await readError(r, "listObservations failed")
  return (await r.json()).map(toObservation)
}

export interface ClaimQuery {
  sourceId?: string
  observationId?: string
  claimType?: string
  status?: string
  limit?: number
  offset?: number
}

export async function listClaims(q: ClaimQuery = {}): Promise<Claim[]> {
  const params = new URLSearchParams()
  if (q.sourceId) params.set("source_id", q.sourceId)
  if (q.observationId) params.set("observation_id", q.observationId)
  if (q.claimType) params.set("claim_type", q.claimType)
  if (q.status) params.set("status", q.status)
  if (q.limit != null) params.set("limit", String(q.limit))
  if (q.offset != null) params.set("offset", String(q.offset))
  const r = await req(`/claims?${params.toString()}`)
  if (!r.ok) throw await readError(r, "listClaims failed")
  return (await r.json()).map(toClaim)
}

export async function getClaim(id: string): Promise<Claim | null> {
  const r = await req(`/claims/${id}`)
  if (r.status === 404) return null
  if (!r.ok) throw await readError(r, "getClaim failed")
  return toClaim(await r.json())
}

export async function listConceptCandidates(q: { sourceId?: string; status?: string } = {}): Promise<ConceptCandidate[]> {
  const params = new URLSearchParams()
  if (q.sourceId) params.set("source_id", q.sourceId)
  if (q.status) params.set("status", q.status)
  const r = await req(`/concept-candidates?${params.toString()}`)
  if (!r.ok) throw await readError(r, "listConceptCandidates failed")
  return (await r.json()).map(toConceptCandidate)
}

export async function getJob(jobId: string): Promise<Job> {
  const r = await req(`/jobs/${jobId}`)
  if (!r.ok) throw await readError(r, "getJob failed")
  return toJob(await r.json())
}

export async function extractClaims(
  sourceId: string,
  force = false
): Promise<{ jobId: string; status: string }> {
  const r = await req(`/sources/${sourceId}/extract-claims${force ? "?force=true" : ""}`, {
    method: "POST",
  })
  if (!r.ok) throw await readError(r, "extractClaims failed")
  const d = await r.json()
  return { jobId: d.job_id, status: d.status }
}

export async function approveConceptCandidate(candidateId: string): Promise<Concept> {
  const r = await req(`/concept-candidates/${candidateId}/approve`, { method: "POST" })
  if (!r.ok) throw await readError(r, "approveConceptCandidate failed")
  const d = await r.json()
  return toConcept(d.concept)
}

export async function rejectConceptCandidate(candidateId: string): Promise<ConceptCandidate> {
  const r = await req(`/concept-candidates/${candidateId}/reject`, { method: "POST" })
  if (!r.ok) throw await readError(r, "rejectConceptCandidate failed")
  return toConceptCandidate(await r.json())
}

export interface ConceptQuery {
  conceptType?: string
  status?: string
  limit?: number
  offset?: number
}

export async function listConcepts(q: ConceptQuery = {}): Promise<Concept[]> {
  const params = new URLSearchParams()
  if (q.conceptType) params.set("concept_type", q.conceptType)
  if (q.status) params.set("status", q.status)
  if (q.limit != null) params.set("limit", String(q.limit))
  if (q.offset != null) params.set("offset", String(q.offset))
  const r = await req(`/concepts?${params.toString()}`)
  if (!r.ok) throw await readError(r, "listConcepts failed")
  return (await r.json()).map(toConcept)
}

export async function getConcept(conceptId: string): Promise<Concept | null> {
  const r = await req(`/concepts/${conceptId}`)
  if (r.status === 404) return null
  if (!r.ok) throw await readError(r, "getConcept failed")
  return toConcept(await r.json())
}

export async function getConceptClaims(conceptId: string): Promise<Claim[]> {
  const r = await req(`/concepts/${conceptId}/claims`)
  if (!r.ok) throw await readError(r, "getConceptClaims failed")
  return (await r.json()).map(toClaim)
}
