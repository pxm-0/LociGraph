export const SOURCE_TYPES = ["json", "markdown", "html", "pdf", "chatgpt", "meta"] as const
export type SourceType = (typeof SOURCE_TYPES)[number]

export interface Source {
  id: string
  sourceType: string
  originalFilename: string | null
  importStatus: string
  fileSizeBytes: number | null
  importedAt?: string | null
  observationCount?: number
  claimCount?: number
  claimExtractionStatus?: string
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
}

export interface Claim {
  id: string
  sourceId: string
  observationId: string
  claimText: string
  claimType: string
  confidence: number
  extractionMethod: string
  modelName: string | null
  promptVersion: string | null
  status: string
  createdAt: string
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

export interface DashboardSummary {
  sourceCount: number
  observationCount: number
  pendingJobCount: number
  recentSources: Source[]
}
