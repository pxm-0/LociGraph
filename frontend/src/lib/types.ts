export const SOURCE_TYPES = ["json", "markdown", "html", "pdf", "chatgpt", "meta"] as const
export type SourceType = (typeof SOURCE_TYPES)[number]

export interface Source {
  id: string
  sourceType: string
  originalFilename: string | null
  importStatus: string
  fileSizeBytes: number | null
}

export interface Observation {
  id: string
  content: string
  speaker: string | null
  observedAt: string | null
  confidence: number
  sourceId: string | null
}
