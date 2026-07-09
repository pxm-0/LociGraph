export const SOURCE_TYPES = ["json", "markdown", "html", "pdf", "chatgpt", "meta"] as const
export type SourceType = (typeof SOURCE_TYPES)[number]

const EXTENSION_TO_SOURCE_TYPE: Record<string, SourceType> = {
  ".md": "markdown",
  ".html": "html",
  ".pdf": "pdf",
  ".zip": "chatgpt",
}

export function detectSourceType(filename: string): SourceType | "ambiguous" {
  const ext = filename.slice(filename.lastIndexOf(".")).toLowerCase()
  return EXTENSION_TO_SOURCE_TYPE[ext] ?? "ambiguous"
}

export interface Source {
  id: string
  sourceType: string
  originalFilename: string | null
  importStatus: string
  fileSizeBytes: number | null
  importedAt: string | null
  observationCount: number
  claimCount: number
  claimExtractionStatus: string
}

export interface Observation {
  id: string
  content: string
  speaker: string | null
  observedAt: string | null
  confidence: number
  sourceId: string | null
}

export interface Job {
  id: string
  jobType: string
  status: string
  attempts: number
  error: string | null
  createdAt: string | null
  startedAt: string | null
  completedAt: string | null
  itemsCompleted: number | null
  itemsTotal: number | null
  sourceId: string | null
}

export interface Claim {
  id: string
  sourceId: string
  observationId: string
  claimText: string
  claimType: string
  assertionType: string
  confidence: number
  extractionMethod: string
  modelName: string | null
  promptVersion: string | null
  status: string
  createdAt: string
}

export interface SearchResult extends Claim {
  similarity: number
}

export interface Contradiction {
  id: string
  conceptId: string
  claimA: Claim
  claimB: Claim
  similarity: number
  classification: string
  rationale: string
  createdAt: string
  classifiedAt: string | null
}

export interface ConceptCandidate {
  id: string
  sourceId: string
  claimId: string
  candidateName: string
  conceptType: string
  rationale: string | null
  confidence: number
  status: string
  createdAt: string
}

export interface Concept {
  id: string
  conceptName: string
  conceptType: string
  description: string | null
  status: string
  createdAt: string
  claimCount: number
}

export interface Revision {
  id: string
  conceptId: string
  contradictionId: string | null
  source: string
  previousDescription: string | null
  newDescription: string
  rationale: string | null
  createdAt: string
}

export interface DashboardSummary {
  sourceCount: number
  observationCount: number
  claimCount: number
  conceptCount: number
  pendingJobCount: number
  recentSources: Source[]
}
