"use client"

import { useState } from "react"
import { search } from "@/lib/api"
import type { SearchResult } from "@/lib/types"
import { Badge } from "@/components/ui/Badge"

export default function SearchPage() {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const data = await search(query.trim())
      setResults(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Search failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6 p-8">
      <h1 className="font-heading text-2xl font-medium text-ink">Search</h1>

      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          aria-label="Search claims"
          className="w-full rounded-hearth border border-hairline bg-canvas px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-muted focus:border-accent"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search claims by meaning…"
          value={query}
        />
        <button
          className="rounded-meridian bg-ember px-4 py-2 font-mono text-xs uppercase tracking-widest text-void transition-colors hover:opacity-90 disabled:opacity-50"
          disabled={loading || !query.trim()}
          type="submit"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error !== null && (
        <div
          role="alert"
          className="rounded-hearth border border-hairline bg-surface px-6 py-4 text-sm text-muted"
        >
          {error}
        </div>
      )}

      {results !== null && (
        <div className="divide-y divide-hairline border-y border-hairline">
          {results.map((result) => (
            <article className="grid gap-3 py-4 md:grid-cols-[1fr_160px_120px]" key={result.id}>
              <p className="text-sm leading-6 text-ink">{result.claimText}</p>
              <div>
                <Badge className="font-mono uppercase">{result.claimType}</Badge>
              </div>
              <div className="font-mono text-xs text-muted">
                {Math.round(result.similarity * 100)}% match
              </div>
            </article>
          ))}
          {results.length === 0 && (
            <p className="py-8 text-sm text-muted">No matching claims found.</p>
          )}
        </div>
      )}
    </div>
  )
}
