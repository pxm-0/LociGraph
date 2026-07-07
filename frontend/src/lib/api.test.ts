import { afterEach, beforeEach, expect, test, vi } from "vitest"
import {
  ApiError,
  embedClaims,
  getClaimsCount,
  getConceptsCount,
  getObservationsCount,
  getSource,
  listJobs,
  listObservations,
  listSources,
  login,
  me,
  search,
  uploadSource,
} from "./api"

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response)
}

beforeEach(() => { vi.stubGlobal("fetch", mockFetch(200, {})) })
afterEach(() => { vi.unstubAllGlobals() })

test("login posts password to /api/auth/login and returns userId", async () => {
  const f = mockFetch(200, { user_id: "u1" }); vi.stubGlobal("fetch", f)
  const r = await login("pw")
  expect(r.userId).toBe("u1")
  const [url, init] = f.mock.calls[0]
  expect(url).toBe("/api/auth/login")
  expect(init.method).toBe("POST")
  expect(init.credentials).toBe("include")
  expect(JSON.parse(init.body)).toEqual({ password: "pw" })
})

test("login throws ApiError with status 401 on bad password", async () => {
  vi.stubGlobal("fetch", mockFetch(401, { detail: "invalid credentials" }))
  await expect(login("nope")).rejects.toMatchObject({ status: 401 })
})

test("me returns null on 401 (not authenticated)", async () => {
  vi.stubGlobal("fetch", mockFetch(401, {}))
  expect(await me()).toBeNull()
})

test("listSources maps snake_case API fields to camelCase Source", async () => {
  vi.stubGlobal("fetch", mockFetch(200, [
    { id: "s1", source_type: "json", original_filename: "a.json", import_status: "VERIFIED", file_size_bytes: 12 },
  ]))
  const [s] = await listSources()
  expect(s).toEqual({
    id: "s1",
    sourceType: "json",
    originalFilename: "a.json",
    importStatus: "VERIFIED",
    fileSizeBytes: 12,
    importedAt: null,
    observationCount: 0,
    claimCount: 0,
    claimExtractionStatus: "waiting",
  })
})

test("getSource returns null on 404", async () => {
  vi.stubGlobal("fetch", mockFetch(404, {}))
  expect(await getSource("missing")).toBeNull()
})

test("uploadSource sends multipart with source_type + file and throws ApiError on 409", async () => {
  const f = mockFetch(409, { detail: "duplicate" }); vi.stubGlobal("fetch", f)
  const file = new File([new Blob(["[]"])], "a.json", { type: "application/json" })
  await expect(uploadSource("json", file)).rejects.toMatchObject({ status: 409 })
  const [url, init] = f.mock.calls[0]
  expect(url).toBe("/api/sources/upload")
  expect(init.body).toBeInstanceOf(FormData)
})

test("listObservations forwards filters as query params", async () => {
  const f = mockFetch(200, []); vi.stubGlobal("fetch", f)
  await listObservations({ sourceId: "s1", speaker: "me", limit: 10 })
  const [url] = f.mock.calls[0]
  expect(url).toContain("/api/observations?")
  expect(url).toContain("source_id=s1")
  expect(url).toContain("speaker=me")
  expect(url).toContain("limit=10")
})

test("listJobs forwards filters as query params and maps source_id to sourceId", async () => {
  const f = mockFetch(200, [
    { id: "j1", job_type: "extract_claims", status: "running", attempts: 0, error: null, created_at: null, started_at: null, completed_at: null, items_completed: 4, items_total: 10, source_id: "s1" },
  ])
  vi.stubGlobal("fetch", f)
  const [job] = await listJobs({ sourceId: "s1", jobType: "extract_claims", status: "running" })
  expect(job.sourceId).toBe("s1")
  expect(job.itemsCompleted).toBe(4)
  const [url] = f.mock.calls[0]
  expect(url).toContain("/api/jobs?")
  expect(url).toContain("source_id=s1")
  expect(url).toContain("job_type=extract_claims")
  expect(url).toContain("status=running")
})

test("getObservationsCount hits /observations/count and returns the real total, not a page size", async () => {
  vi.stubGlobal("fetch", mockFetch(200, { total: 39721 }))
  expect(await getObservationsCount({ sourceId: "s1" })).toBe(39721)
})

test("getClaimsCount hits /claims/count and returns the real total", async () => {
  const f = mockFetch(200, { total: 17676 }); vi.stubGlobal("fetch", f)
  expect(await getClaimsCount({ sourceId: "s1", claimType: "fact" })).toBe(17676)
  const [url] = f.mock.calls[0]
  expect(url).toContain("/api/claims/count?")
  expect(url).toContain("claim_type=fact")
})

test("getConceptsCount hits /concepts/count and returns the real total", async () => {
  vi.stubGlobal("fetch", mockFetch(200, { total: 412 }))
  expect(await getConceptsCount()).toBe(412)
})

test("search sends q and limit as query params and maps similarity", async () => {
  const f = mockFetch(200, [
    { id: "c1", source_id: "s1", observation_id: "o1", claim_text: "hi", claim_type: "fact", confidence: 0.9, extraction_method: "test", model_name: null, prompt_version: null, status: "proposed", created_at: "2024-01-01T00:00:00Z", similarity: 0.87 },
  ])
  vi.stubGlobal("fetch", f)
  const [result] = await search("hello", 5)
  expect(result.similarity).toBe(0.87)
  expect(result.claimText).toBe("hi")
  const [url] = f.mock.calls[0]
  expect(url).toContain("/api/search?")
  expect(url).toContain("q=hello")
  expect(url).toContain("limit=5")
})

test("embedClaims posts to /sources/:id/embed-claims and returns jobId/status", async () => {
  const f = mockFetch(200, { job_id: "j1", status: "pending" })
  vi.stubGlobal("fetch", f)
  const result = await embedClaims("s1")
  expect(result).toEqual({ jobId: "j1", status: "pending" })
  const [url, init] = f.mock.calls[0]
  expect(url).toBe("/api/sources/s1/embed-claims")
  expect(init.method).toBe("POST")
})
