import type {
  Claim,
  Concept,
  ConceptCandidate,
  Contradiction,
  CustodianLoggedItem,
  CustodianMessage,
  CustodianSession,
  DashboardSummary,
  Job,
  Observation,
  PlanetariumNode,
  PlanetariumNodeDetail,
  Revision,
  SearchResult,
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
    itemsCompleted: (d.items_completed as number | null) ?? null,
    itemsTotal: (d.items_total as number | null) ?? null,
    sourceId: (d.source_id as string | null) ?? null,
  }
}

function toClaim(d: Record<string, unknown>): Claim {
  return {
    id: String(d.id),
    sourceId: String(d.source_id),
    observationId: String(d.observation_id),
    claimText: String(d.claim_text),
    claimType: String(d.claim_type),
    assertionType: String(d.assertion_type),
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
    claimCount: Number(d.claim_count ?? 0),
    conceptCount: Number(d.concept_count ?? 0),
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

export async function getObservationsCount(
  q: Pick<ObservationQuery, "sourceId" | "speaker" | "status"> = {}
): Promise<number> {
  const params = new URLSearchParams()
  if (q.sourceId) params.set("source_id", q.sourceId)
  if (q.speaker) params.set("speaker", q.speaker)
  if (q.status) params.set("status", q.status)
  const r = await req(`/observations/count?${params.toString()}`)
  if (!r.ok) throw await readError(r, "getObservationsCount failed")
  return Number((await r.json()).total ?? 0)
}

export interface ClaimQuery {
  sourceId?: string
  observationId?: string
  claimType?: string
  assertionType?: string
  status?: string
  limit?: number
  offset?: number
}

export async function listClaims(q: ClaimQuery = {}): Promise<Claim[]> {
  const params = new URLSearchParams()
  if (q.sourceId) params.set("source_id", q.sourceId)
  if (q.observationId) params.set("observation_id", q.observationId)
  if (q.claimType) params.set("claim_type", q.claimType)
  if (q.assertionType) params.set("assertion_type", q.assertionType)
  if (q.status) params.set("status", q.status)
  if (q.limit != null) params.set("limit", String(q.limit))
  if (q.offset != null) params.set("offset", String(q.offset))
  const r = await req(`/claims?${params.toString()}`)
  if (!r.ok) throw await readError(r, "listClaims failed")
  return (await r.json()).map(toClaim)
}

export async function getClaimsCount(
  q: Pick<ClaimQuery, "sourceId" | "observationId" | "claimType" | "assertionType" | "status"> = {}
): Promise<number> {
  const params = new URLSearchParams()
  if (q.sourceId) params.set("source_id", q.sourceId)
  if (q.observationId) params.set("observation_id", q.observationId)
  if (q.claimType) params.set("claim_type", q.claimType)
  if (q.assertionType) params.set("assertion_type", q.assertionType)
  if (q.status) params.set("status", q.status)
  const r = await req(`/claims/count?${params.toString()}`)
  if (!r.ok) throw await readError(r, "getClaimsCount failed")
  return Number((await r.json()).total ?? 0)
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

export interface JobQuery {
  sourceId?: string
  jobType?: string
  status?: string
  limit?: number
  offset?: number
}

export async function listJobs(q: JobQuery = {}): Promise<Job[]> {
  const params = new URLSearchParams()
  if (q.sourceId) params.set("source_id", q.sourceId)
  if (q.jobType) params.set("job_type", q.jobType)
  if (q.status) params.set("status", q.status)
  if (q.limit != null) params.set("limit", String(q.limit))
  if (q.offset != null) params.set("offset", String(q.offset))
  const r = await req(`/jobs?${params.toString()}`)
  if (!r.ok) throw await readError(r, "listJobs failed")
  return (await r.json()).map(toJob)
}

export async function extractClaims(
  sourceId: string,
  force = false
): Promise<{ jobIds: string[]; status: string }> {
  const r = await req(`/sources/${sourceId}/extract-claims${force ? "?force=true" : ""}`, {
    method: "POST",
  })
  if (!r.ok) throw await readError(r, "extractClaims failed")
  const d = await r.json()
  return { jobIds: d.job_ids, status: d.status }
}

export async function purgeSource(sourceId: string): Promise<void> {
  const r = await req(`/sources/${sourceId}/purge`, { method: "POST" })
  if (!r.ok) throw await readError(r, "purgeSource failed")
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

export async function getConceptsCount(
  q: Pick<ConceptQuery, "conceptType" | "status"> = {}
): Promise<number> {
  const params = new URLSearchParams()
  if (q.conceptType) params.set("concept_type", q.conceptType)
  if (q.status) params.set("status", q.status)
  const r = await req(`/concepts/count?${params.toString()}`)
  if (!r.ok) throw await readError(r, "getConceptsCount failed")
  return Number((await r.json()).total ?? 0)
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

function toRevision(d: Record<string, unknown>): Revision {
  return {
    id: String(d.id),
    conceptId: String(d.concept_id),
    contradictionId: (d.contradiction_id as string | null) ?? null,
    source: String(d.source),
    previousDescription: (d.previous_description as string | null) ?? null,
    newDescription: String(d.new_description),
    rationale: (d.rationale as string | null) ?? null,
    createdAt: String(d.created_at),
  }
}

export async function getConceptRevisions(conceptId: string): Promise<Revision[]> {
  const r = await req(`/concepts/${conceptId}/revisions`)
  if (!r.ok) throw await readError(r, "getConceptRevisions failed")
  return (await r.json()).map(toRevision)
}

export async function createConceptRevision(
  conceptId: string,
  newDescription: string,
  rationale?: string
): Promise<Revision> {
  const r = await req(`/concepts/${conceptId}/revisions`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ new_description: newDescription, rationale: rationale ?? null }),
  })
  if (!r.ok) throw await readError(r, "createConceptRevision failed")
  return toRevision(await r.json())
}

export async function search(query: string, limit = 20): Promise<SearchResult[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  const r = await req(`/search?${params.toString()}`)
  if (!r.ok) throw await readError(r, "search failed")
  const rows = (await r.json()) as Record<string, unknown>[]
  return rows.map((d) => ({ ...toClaim(d), similarity: Number(d.similarity) }))
}

export async function embedClaims(sourceId: string): Promise<{ jobId: string; status: string }> {
  const r = await req(`/sources/${sourceId}/embed-claims`, { method: "POST" })
  if (!r.ok) throw await readError(r, "embedClaims failed")
  const d = await r.json()
  return { jobId: d.job_id, status: d.status }
}

function toPlanetariumNode(d: Record<string, unknown>): PlanetariumNode {
  return {
    id: String(d.id),
    conceptId: String(d.concept_id),
    conceptName: String(d.concept_name),
    conceptType: String(d.concept_type),
    x: Number(d.x),
    y: Number(d.y),
    z: Number(d.z),
    theta: Number(d.theta),
    phi: Number(d.phi),
    radius: Number(d.radius),
    mass: Number(d.mass),
    brightness: Number(d.brightness),
    color: String(d.color),
    visualClass: String(d.visual_class),
    projectionVersion: String(d.projection_version),
    projectionAlgorithm: String(d.projection_algorithm),
    createdAt: (d.created_at as string | null) ?? null,
  }
}

export async function listPlanetariumNodes(): Promise<PlanetariumNode[]> {
  const r = await req("/planetarium/nodes")
  if (!r.ok) throw await readError(r, "listPlanetariumNodes failed")
  return (await r.json()).map(toPlanetariumNode)
}

function toPlanetariumNodeDetail(d: Record<string, unknown>): PlanetariumNodeDetail {
  return {
    conceptId: String(d.concept_id),
    conceptName: String(d.concept_name),
    conceptType: String(d.concept_type),
    description: (d.description as string | null) ?? null,
    mass: Number(d.mass),
    brightness: Number(d.brightness),
    visualClass: String(d.visual_class),
    revisionCount: Number(d.revision_count),
    edgeCount: Number(d.edge_count),
    contradictionCount: Number(d.contradiction_count),
    pinCount: Number(d.pin_count),
    isEmbedded: Boolean(d.is_embedded),
  }
}

export async function getPlanetariumNodeDetail(conceptId: string): Promise<PlanetariumNodeDetail> {
  const r = await req(`/planetarium/nodes/${conceptId}/detail`)
  if (!r.ok) throw await readError(r, "getPlanetariumNodeDetail failed")
  return toPlanetariumNodeDetail(await r.json())
}

export async function rebuildPlanetarium(): Promise<{ jobId: string; status: string }> {
  const r = await req("/planetarium/rebuild", { method: "POST" })
  if (!r.ok) throw await readError(r, "rebuildPlanetarium failed")
  const d = await r.json()
  return { jobId: d.job_id, status: d.status }
}

function toContradiction(d: Record<string, unknown>): Contradiction {
  return {
    id: String(d.id),
    conceptId: String(d.concept_id),
    claimA: toClaim(d.claim_a as Record<string, unknown>),
    claimB: toClaim(d.claim_b as Record<string, unknown>),
    similarity: Number(d.similarity),
    classification: String(d.classification),
    rationale: String(d.rationale),
    createdAt: String(d.created_at),
    classifiedAt: (d.classified_at as string | null) ?? null,
  }
}

export interface ContradictionQuery {
  conceptId?: string
  classification?: string
  limit?: number
  offset?: number
}

export async function listContradictions(q: ContradictionQuery = {}): Promise<Contradiction[]> {
  const params = new URLSearchParams()
  if (q.conceptId) params.set("concept_id", q.conceptId)
  if (q.classification) params.set("classification", q.classification)
  if (q.limit != null) params.set("limit", String(q.limit))
  if (q.offset != null) params.set("offset", String(q.offset))
  const r = await req(`/contradictions?${params.toString()}`)
  if (!r.ok) throw await readError(r, "listContradictions failed")
  return (await r.json()).map(toContradiction)
}

export async function getContradictionsCount(
  q: Pick<ContradictionQuery, "conceptId" | "classification"> = {}
): Promise<number> {
  const params = new URLSearchParams()
  if (q.conceptId) params.set("concept_id", q.conceptId)
  if (q.classification) params.set("classification", q.classification)
  const r = await req(`/contradictions/count?${params.toString()}`)
  if (!r.ok) throw await readError(r, "getContradictionsCount failed")
  return Number((await r.json()).total ?? 0)
}

export async function classifyContradiction(
  contradictionId: string,
  classification: string
): Promise<Contradiction> {
  const r = await req(`/contradictions/${contradictionId}/classify`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ classification }),
  })
  if (!r.ok) throw await readError(r, "classifyContradiction failed")
  return toContradiction(await r.json())
}

function toCustodianSession(d: Record<string, unknown>): CustodianSession {
  return {
    id: String(d.id),
    title: (d.title as string | null) ?? null,
    startedAt: String(d.started_at),
    endedAt: (d.ended_at as string | null) ?? null,
    model: String(d.model),
    provider: String(d.provider),
  }
}

function toCustodianMessage(d: Record<string, unknown>): CustodianMessage {
  return {
    id: String(d.id),
    sessionId: String(d.session_id),
    role: d.role as CustodianMessage["role"],
    content: String(d.content),
    toolName: (d.tool_name as string | null) ?? null,
    toolInput: (d.tool_input as string | null) ?? null,
    toolOutput: (d.tool_output as string | null) ?? null,
    createdAt: String(d.created_at),
  }
}

export async function createCustodianSession(title: string | null = null): Promise<CustodianSession> {
  const r = await req("/custodian/sessions", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ title }),
  })
  if (!r.ok) throw await readError(r, "createCustodianSession failed")
  return toCustodianSession(await r.json())
}

export async function listCustodianSessions(): Promise<CustodianSession[]> {
  const r = await req("/custodian/sessions")
  if (!r.ok) throw await readError(r, "listCustodianSessions failed")
  return (await r.json()).map(toCustodianSession)
}

export async function getCustodianMessages(sessionId: string): Promise<CustodianMessage[]> {
  const r = await req(`/custodian/sessions/${sessionId}/messages`)
  if (!r.ok) throw await readError(r, "getCustodianMessages failed")
  return (await r.json()).map(toCustodianMessage)
}

export async function endCustodianSession(sessionId: string): Promise<CustodianSession> {
  const r = await req(`/custodian/sessions/${sessionId}/end`, { method: "POST" })
  if (!r.ok) throw await readError(r, "endCustodianSession failed")
  return toCustodianSession(await r.json())
}

export interface CustodianStreamHandlers {
  onToken(delta: string): void
  onToolCall(toolName: string, query: string): void
  onDone(): void
  onError(message: string): void
}

export async function streamCustodianMessage(
  sessionId: string,
  content: string,
  handlers: CustodianStreamHandlers
): Promise<void> {
  // The whole body is wrapped in try/catch so every failure mode — fetch()
  // itself rejecting (network/DNS/abort), reader.read() rejecting mid-stream,
  // or a malformed `data:` line throwing in JSON.parse — reaches
  // handlers.onError instead of becoming an unhandled promise rejection.
  try {
    const r = await fetch(base(`/custodian/sessions/${sessionId}/messages`), {
      method: "POST",
      credentials: "include",
      headers: JSON_HEADERS,
      body: JSON.stringify({ content }),
    })
    if (!r.ok || !r.body) {
      const err = await readError(r, "streamCustodianMessage failed")
      handlers.onError(err.message)
      return
    }
    const reader = r.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split("\n\n")
      buffer = events.pop() ?? ""
      for (const raw of events) {
        const lines = raw.split("\n")
        const eventLine = lines.find((l) => l.startsWith("event: "))
        const dataLine = lines.find((l) => l.startsWith("data: "))
        if (!eventLine || !dataLine) continue
        const eventName = eventLine.slice("event: ".length)
        const data = JSON.parse(dataLine.slice("data: ".length))
        if (eventName === "token") handlers.onToken(data.delta)
        else if (eventName === "tool_call") handlers.onToolCall(data.tool_name, data.query)
        else if (eventName === "done") handlers.onDone()
        else if (eventName === "error") handlers.onError(data.message)
      }
    }
  } catch (err) {
    handlers.onError(err instanceof Error ? err.message : "stream failed")
  }
}

function toCustodianLoggedItem(d: Record<string, unknown>): CustodianLoggedItem {
  return {
    id: String(d.id),
    sessionId: String(d.session_id),
    itemType: String(d.item_type),
    targetId: (d.target_id as string | null) ?? null,
    content: (d.content as Record<string, unknown>) ?? {},
    status: d.status as CustodianLoggedItem["status"],
    createdAt: String(d.created_at),
    resolvedAt: (d.resolved_at as string | null) ?? null,
  }
}

export async function listLoggedItems(sessionId: string): Promise<CustodianLoggedItem[]> {
  const r = await req(`/custodian/sessions/${sessionId}/logged-items`)
  if (!r.ok) throw await readError(r, "listLoggedItems failed")
  return (await r.json()).map(toCustodianLoggedItem)
}

export async function acceptLoggedItem(itemId: string): Promise<CustodianLoggedItem> {
  const r = await req(`/custodian/logged-items/${itemId}/accept`, { method: "POST" })
  if (!r.ok) throw await readError(r, "acceptLoggedItem failed")
  return toCustodianLoggedItem(await r.json())
}

export async function rejectLoggedItem(itemId: string): Promise<CustodianLoggedItem> {
  const r = await req(`/custodian/logged-items/${itemId}/reject`, { method: "POST" })
  if (!r.ok) throw await readError(r, "rejectLoggedItem failed")
  return toCustodianLoggedItem(await r.json())
}
