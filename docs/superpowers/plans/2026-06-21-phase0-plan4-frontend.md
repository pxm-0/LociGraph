# Phase 0 — Plan 4: Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Phase 0 web UI — a Next.js app with Login, Dashboard, Import, Sources, and Observations — talking to the Plan 3 API over one origin, with the Hearth/Meridian dual-mode design system from DESIGN.md.

**Architecture:** A **Next.js (App Router) + TypeScript + Tailwind** app in `frontend/`. A single typed API client (`lib/api.ts`) is the only thing that talks to the backend; everything reaches it through relative `/api/*` paths (Next rewrites in dev, Caddy in prod — no CORS). Auth is the httpOnly `locigraph_token` cookie set by the backend; the browser never reads it — route protection is driven by `GET /api/auth/me`. A `ThemeProvider` switches **Hearth** (light/teal, cozy reading, low density) and **Meridian** (dark, command, high density) via a `data-mode` attribute + Tailwind tokens. The visual source of truth is the Stitch project (HTML pulled into `frontend/design/`); the animated Orb/Core companion is deferred to a later polish pass.

**Tech Stack:** Next.js 14 (App Router), React 18, TypeScript (strict), Tailwind CSS, `next/font` (Outfit, Geist, Geist Mono), Vitest + React Testing Library (unit/component), Playwright (one smoke e2e), Node 20.

## Global Constraints

- **One origin, relative API paths.** The browser only ever calls `/api/*`. Dev: Next rewrites `/api/:path*` → `http://localhost:8000/:path*`. Prod: Caddy routes `/api/*` → `backend:8000` (strip `/api`). **No CORS, no absolute backend URLs in client code.**
- **Auth cookie is httpOnly.** Client JS never reads/sets `locigraph_token`. Login = POST credentials, browser stores the cookie automatically. Protection = call `GET /api/auth/me`; 401 → redirect to `/login`. `fetch` must use `credentials: "include"` (same-origin) so the cookie rides along.
- **TypeScript `strict` clean; ESLint clean.** No `any` in `lib/`. `npm run build` (production build + type-check) must pass.
- **Design tokens come from DESIGN.md — verbatim hex.** Void `#0F0D0B`, Archive `#141210`, Chamber `#1E1A17`, Dust `#F5EDE2`, Ash `#A89070`, Ember `#D4882F`; Hearth Surface `#f4fbfa`, Hearth Accent `#2d6a6a`; status: VERIFIED `#5A8C5A`, INGESTING/active Ember `#D4882F`, QUARANTINED `#8C6A2A`. Radius 10px (Hearth) / 6px (Meridian). Border `1px solid rgba(245,237,226,0.07)`.
- **Fonts:** Outfit (headings), Geist (UI), Geist Mono (data/telemetry — UUIDs, timestamps, counts, confidence). No `Inter`.
- **Anti-patterns are banned** (DESIGN.md §8): no emojis, no pure black, no neon glow, no purple/cyber palette, no gradient headings, no 3-equal-column card rows, no centered hero for primary views, no circular spinners (skeleton loaders only), no AI-copywriting words ("Seamless/Unleash/Next-Gen/Elevate/Empower"), no scroll-arrow filler.
- **Dual-mode required; Orb deferred.** Both Hearth and Meridian modes + a working toggle + density tokens ship in this plan. The animated Orb/Core companion is OUT of scope (leave a documented placeholder slot).
- **Two-space indent, no semicolon-style bikeshedding** — match Next.js defaults / Prettier defaults; run `npm run lint` (`next lint`) clean.

## Interface contracts from Plan 3 (the API this consumes — do not redefine)

All paths below are reached as `/api/<path>` from the browser. Auth via the `locigraph_token` httpOnly cookie.

- `POST /auth/login` — body `{"password": string}` → `200 {"user_id": string}` + sets cookie. `401` on bad password.
- `POST /auth/logout` → `200 {"status": string}`, clears cookie.
- `GET /auth/me` → `200 {"user_id": string}` if authed, else `401`.
- `POST /sources/upload` — multipart form: `source_type` (string, one of the 6 types) + `file` (binary) → `202 {"source_id": string, "status": "PENDING"}`. `400` invalid `source_type`, `409` duplicate checksum, `401` unauth.
- `GET /sources` → `200` array of `{"id": string, "source_type": string, "original_filename": string|null, "import_status": string, "file_size_bytes": number|null}`. Newest first.
- `GET /sources/{id}` → `200` one source object (same shape), `404` if not found.
- `GET /observations?source_id=&speaker=&status=&limit=&offset=` → `200` array of `{"id": string, "content": string, "speaker": string|null, "observed_at": string|null (ISO), "confidence": number, "source_id": string|null}`.

**Known API gaps (do NOT add backend endpoints in this plan — derive or defer):**
- No per-source observation count and no jobs list endpoint. Dashboard stats derive from `GET /sources`: total sources, verified count, and "in-flight" = sources with `import_status ∈ {PENDING, INGESTING}`. Accurate global observation/job counts are deferred (would need Plan-3-area count endpoints).
- `source_type` values are the six the backend accepts: `json`, `markdown`, `html`, `pdf`, `chatgpt`, `meta`. (Confirm exact strings against `kernel/ingestion/base.py SourceType.ALL` during Task 2.)

## Design reference (Stitch)

Shared Stitch project `10480468985418032612`. **Before Task 5**, the controller pulls the raw HTML for the screens below into `frontend/design/<name>.html` (committed as read-only reference) so porting tasks read local files, not a live MCP. Screens:

| Component | Stitch screen | id |
|---|---|---|
| Dashboard (Hearth, light teal) | "Dashboard (Hearth Mode)" | `3656a89b6f604f499336195392765abd` |
| Dashboard (Meridian, dark) | "Dashboard (Meridian Mode)" | `1e51f315b8c24e0cbeebba6df45517fe` |
| Import (dark) | "Import / Ingest" | `c9c345f3fa744ceea0667cae35858728` |
| Import (teal) | "Import (Teal)" | `1316a52cf4714074bc92b1d597de8dea` |
| Observations (dark teal) | "Observation Browser (Dark Teal)" | `948657af29b84262bd579bc8fd55d125` |
| Observations | "Observation Browser" | `50b7ab981162444286fb5f72b119c6be` |

**Login** and **Sources list** have no Stitch screen — hand-build from DESIGN.md §7 Screen 1 (Login) and Screen 5 (Sources List). Stitch markup is static HTML with Tailwind utility classes + hardcoded hex; porting = lift the structure, replace hex with our Tailwind theme tokens (Task 1), and wire to `lib/api.ts`.

---

## File Structure

```
frontend/
├── package.json                      # T1
├── next.config.mjs                   # T1  — /api rewrite (dev), standalone output
├── tsconfig.json                     # T1
├── tailwind.config.ts                # T1  — design tokens (colors, radius, fonts, density)
├── postcss.config.mjs                # T1
├── .eslintrc.json                    # T1
├── vitest.config.ts                  # T1  — jsdom, RTL
├── vitest.setup.ts                   # T1
├── playwright.config.ts              # T1
├── Dockerfile                        # T11 — multi-stage, next standalone
├── .dockerignore                     # T11
├── design/                           # (controller-populated Stitch HTML refs)
├── public/
└── src/
    ├── app/
    │   ├── globals.css               # T1  — Tailwind layers, base mode vars
    │   ├── layout.tsx                # T1  — root layout, fonts, ThemeProvider
    │   ├── page.tsx                  # T6  — redirect to /dashboard or /login
    │   ├── login/page.tsx            # T6
    │   ├── (app)/layout.tsx          # T5  — authed shell (sidebar + mode chrome)
    │   ├── (app)/dashboard/page.tsx  # T7
    │   ├── (app)/import/page.tsx     # T8
    │   ├── (app)/sources/page.tsx    # T9
    │   └── (app)/observations/page.tsx # T10
    ├── components/
    │   ├── ui/
    │   │   ├── Button.tsx            # T4
    │   │   ├── Card.tsx              # T4
    │   │   ├── Input.tsx             # T4
    │   │   ├── Badge.tsx             # T4
    │   │   ├── StatusBadge.tsx       # T4
    │   │   └── Skeleton.tsx          # T4
    │   ├── layout/
    │   │   ├── Sidebar.tsx           # T5
    │   │   └── ModeToggle.tsx        # T5
    │   └── domain/
    │       ├── SourceRow.tsx         # T9
    │       ├── ObservationCard.tsx   # T10
    │       └── StatCard.tsx          # T7
    ├── lib/
    │   ├── api.ts                    # T2  — typed API client
    │   ├── api.test.ts               # T2
    │   ├── types.ts                  # T2  — Source, Observation, etc.
    │   └── theme.tsx                 # T3  — ThemeProvider, useMode, density tokens
    └── test/
        └── e2e/
            └── smoke.spec.ts         # T12 — login → import → sources
```

`docker-compose.yml` (frontend service) and `Caddyfile` (serve SPA + `/api/*`) are modified in T11.

---

### Task 1: Scaffold Next.js app, design tokens, test harness

**Files:**
- Create: `frontend/package.json`, `frontend/next.config.mjs`, `frontend/tsconfig.json`, `frontend/tailwind.config.ts`, `frontend/postcss.config.mjs`, `frontend/.eslintrc.json`, `frontend/vitest.config.ts`, `frontend/vitest.setup.ts`, `frontend/playwright.config.ts`, `frontend/src/app/globals.css`, `frontend/src/app/layout.tsx`, `frontend/.gitignore`
- Test: `frontend/src/app/smoke.test.tsx`

**Interfaces:**
- Produces: a runnable `npm run dev` (port 3000), `npm run build`, `npm run lint`, `npm test` (Vitest), `npm run test:e2e` (Playwright). Tailwind theme exposing tokens: colors `void/archive/chamber/dust/ash/ember/hearth-surface/hearth-accent/status-verified/status-ingesting/status-quarantined`, `borderRadius.hearth (10px)` / `.meridian (6px)`, font families `heading (Outfit)`, `ui (Geist)`, `mono (Geist Mono)`.

- [ ] **Step 1: Initialize the app non-interactively.** From repo root:
```bash
cd frontend 2>/dev/null || mkdir -p frontend
# Pin versions; create package.json + configs by hand (below) rather than create-next-app to avoid interactive prompts.
```
Create `frontend/package.json`:
```json
{
  "name": "locigraph-frontend",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:e2e": "playwright test"
  },
  "dependencies": {
    "next": "14.2.5",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "geist": "1.3.1"
  },
  "devDependencies": {
    "@playwright/test": "1.45.0",
    "@testing-library/jest-dom": "6.4.6",
    "@testing-library/react": "16.0.0",
    "@testing-library/user-event": "14.5.2",
    "@types/node": "20.14.9",
    "@types/react": "18.3.3",
    "@types/react-dom": "18.3.0",
    "@vitejs/plugin-react": "4.3.1",
    "autoprefixer": "10.4.19",
    "eslint": "8.57.0",
    "eslint-config-next": "14.2.5",
    "jsdom": "24.1.0",
    "postcss": "8.4.39",
    "tailwindcss": "3.4.4",
    "typescript": "5.5.3",
    "vitest": "1.6.0"
  }
}
```
> `geist` package provides Geist + Geist Mono via `next/font`. Outfit comes from `next/font/google`.

- [ ] **Step 2: Write configs.**

`frontend/next.config.mjs`:
```js
/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_ORIGIN || "http://localhost:8000"
const nextConfig = {
  output: "standalone",
  async rewrites() {
    // Dev only: in prod, Caddy proxies /api/* → backend and this app is served as static/standalone.
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }]
  },
}
export default nextConfig
```
`frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "ES2022"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```
`frontend/tailwind.config.ts`:
```ts
import type { Config } from "tailwindcss"

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        void: "#0F0D0B",
        archive: "#141210",
        chamber: "#1E1A17",
        dust: "#F5EDE2",
        ash: "#A89070",
        ember: "#D4882F",
        "hearth-surface": "#f4fbfa",
        "hearth-accent": "#2d6a6a",
        "status-verified": "#5A8C5A",
        "status-ingesting": "#D4882F",
        "status-quarantined": "#8C6A2A",
        whisper: "rgba(245,237,226,0.07)",
      },
      borderRadius: { hearth: "10px", meridian: "6px" },
      fontFamily: {
        heading: ["var(--font-outfit)", "sans-serif"],
        ui: ["var(--font-geist)", "sans-serif"],
        mono: ["var(--font-geist-mono)", "monospace"],
      },
    },
  },
  plugins: [],
}
export default config
```
`frontend/postcss.config.mjs`:
```js
export default { plugins: { tailwindcss: {}, autoprefixer: {} } }
```
`frontend/.eslintrc.json`:
```json
{ "extends": "next/core-web-vitals" }
```
`frontend/vitest.config.ts`:
```ts
import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"
import path from "node:path"

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    exclude: ["**/node_modules/**", "**/src/test/e2e/**"],
  },
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
})
```
`frontend/vitest.setup.ts`:
```ts
import "@testing-library/jest-dom/vitest"
```
`frontend/playwright.config.ts`:
```ts
import { defineConfig } from "@playwright/test"

export default defineConfig({
  testDir: "./src/test/e2e",
  use: { baseURL: process.env.E2E_BASE_URL || "http://localhost:3000" },
  timeout: 30_000,
})
```
`frontend/.gitignore`:
```
node_modules
.next
out
playwright-report
test-results
next-env.d.ts
```

- [ ] **Step 3: Root layout + fonts + globals.**

`frontend/src/app/globals.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root { --gap: 2rem; }            /* Hearth density */
[data-mode="meridian"] { --gap: 0.5rem; }

html, body { padding: 0; margin: 0; }
body { font-family: var(--font-geist), sans-serif; }
```
`frontend/src/app/layout.tsx`:
```tsx
import type { Metadata } from "next"
import { Outfit } from "next/font/google"
import { GeistSans } from "geist/font/sans"
import { GeistMono } from "geist/font/mono"
import "./globals.css"

const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit" })

export const metadata: Metadata = { title: "LociGraph" }

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${outfit.variable} ${GeistSans.variable} ${GeistMono.variable}`}
      style={{ ["--font-geist" as string]: GeistSans.style.fontFamily, ["--font-geist-mono" as string]: GeistMono.style.fontFamily }}
    >
      <body>{children}</body>
    </html>
  )
}
```
> The `geist` package already exposes `--font-geist-sans`/`--font-geist-mono`; the inline `style` aliases them to the names Tailwind expects. If the executor finds the geist package exports those variable names directly, prefer wiring `variable: "--font-geist"` via its API and drop the inline style. Keep Tailwind's `fontFamily` names stable.

- [ ] **Step 4: Smoke test (proves the harness runs).** `frontend/src/app/smoke.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react"
import { expect, test } from "vitest"

function Hello() { return <h1>LociGraph</h1> }

test("test harness renders a component", () => {
  render(<Hello />)
  expect(screen.getByRole("heading", { name: "LociGraph" })).toBeInTheDocument()
})
```

- [ ] **Step 5: Install + verify.**
```bash
cd frontend && npm install && npx playwright install chromium
npm test            # smoke test passes
npm run lint        # clean (may warn no pages yet — acceptable)
npm run build       # production build + type-check passes
```
Expected: Vitest 1/1 pass; build succeeds (an app with only a root layout builds — add a temporary `src/app/page.tsx` returning `<main/>` if build requires a page, it's replaced in T6).

- [ ] **Step 6: Commit.**
```bash
git add frontend
git commit -m "chore(frontend): next.js + tailwind tokens + vitest/playwright harness"
```

---

### Task 2: Typed API client + domain types

**Files:**
- Create: `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`, `frontend/src/lib/api.test.ts`

**Interfaces:**
- Consumes: the Plan 3 API contracts (top of this plan).
- Produces:
  - `types.ts`: `Source { id, sourceType, originalFilename, importStatus, fileSizeBytes }`, `Observation { id, content, speaker, observedAt, confidence, sourceId }`, `SourceType` union, `SOURCE_TYPES: readonly SourceType[]`.
  - `api.ts`: `login(password): Promise<{userId: string}>`, `logout(): Promise<void>`, `me(): Promise<{userId: string} | null>` (null on 401), `listSources(): Promise<Source[]>`, `getSource(id): Promise<Source | null>` (null on 404), `uploadSource(sourceType, file): Promise<{sourceId: string; status: string}>` (throws `ApiError` with `.status` on 400/409/401), `listObservations(params?): Promise<Observation[]>`. `class ApiError extends Error { status: number }`.

- [ ] **Step 1: Confirm the source-type strings.** Read `kernel/ingestion/base.py` to confirm `SourceType.ALL`. Set `SOURCE_TYPES` to exactly those strings (expected: `["json","markdown","html","pdf","chatgpt","meta"]`).

- [ ] **Step 2: Write the failing tests** `frontend/src/lib/api.test.ts`:
```ts
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"
import { ApiError, getSource, listObservations, listSources, login, me, uploadSource } from "./api"

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response)
}

beforeEach(() => { vi.stubGlobal("fetch", mockFetch(200, {})) })
afterEach(() => { vi.unstubAllMocks() })

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
  expect(s).toEqual({ id: "s1", sourceType: "json", originalFilename: "a.json", importStatus: "VERIFIED", fileSizeBytes: 12 })
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
```

- [ ] **Step 3: Run → RED.** `npm test -- src/lib/api.test.ts` (module not found).

- [ ] **Step 4: Implement** `frontend/src/lib/types.ts`:
```ts
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
```
`frontend/src/lib/api.ts`:
```ts
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
```

- [ ] **Step 5: Run → GREEN.** `npm test -- src/lib/api.test.ts` (all pass). `npm run typecheck` clean.

- [ ] **Step 6: Commit.**
```bash
git add frontend/src/lib
git commit -m "feat(frontend): typed api client + domain types"
```

---

### Task 3: Theme/mode system (Hearth ↔ Meridian)

**Files:**
- Create: `frontend/src/lib/theme.tsx`, `frontend/src/lib/theme.test.tsx`

**Interfaces:**
- Produces: `type Mode = "hearth" | "meridian"`; `ThemeProvider` (sets `data-mode` on a wrapper, persists to `localStorage["locigraph-mode"]`, defaults to `"hearth"`); `useMode(): { mode: Mode; toggle(): void; setMode(m: Mode): void }`.

- [ ] **Step 1: Failing test** `frontend/src/lib/theme.test.tsx`:
```tsx
import { act, render, screen } from "@testing-library/react"
import { beforeEach, expect, test } from "vitest"
import { ThemeProvider, useMode } from "./theme"

function Probe() {
  const { mode, toggle } = useMode()
  return <button onClick={toggle}>mode:{mode}</button>
}

beforeEach(() => localStorage.clear())

test("defaults to hearth and toggles to meridian", async () => {
  render(<ThemeProvider><Probe /></ThemeProvider>)
  const btn = screen.getByRole("button")
  expect(btn).toHaveTextContent("mode:hearth")
  await act(async () => btn.click())
  expect(btn).toHaveTextContent("mode:meridian")
  expect(localStorage.getItem("locigraph-mode")).toBe("meridian")
})

test("reads persisted mode on mount", () => {
  localStorage.setItem("locigraph-mode", "meridian")
  render(<ThemeProvider><Probe /></ThemeProvider>)
  expect(screen.getByRole("button")).toHaveTextContent("mode:meridian")
})
```

- [ ] **Step 2: Run → RED.** `npm test -- src/lib/theme.test.tsx`.

- [ ] **Step 3: Implement** `frontend/src/lib/theme.tsx`:
```tsx
"use client"
import { createContext, useContext, useEffect, useState } from "react"

export type Mode = "hearth" | "meridian"
const KEY = "locigraph-mode"

interface ThemeCtx { mode: Mode; toggle(): void; setMode(m: Mode): void }
const Ctx = createContext<ThemeCtx | null>(null)

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<Mode>("hearth")
  useEffect(() => {
    const saved = localStorage.getItem(KEY)
    if (saved === "hearth" || saved === "meridian") setMode(saved)
  }, [])
  useEffect(() => { localStorage.setItem(KEY, mode) }, [mode])
  const toggle = () => setMode((m) => (m === "hearth" ? "meridian" : "hearth"))
  return <div data-mode={mode} className="min-h-screen">{
    /* eslint-disable-next-line react/jsx-no-constructed-context-values */
  }<Ctx.Provider value={{ mode, toggle, setMode }}>{children}</Ctx.Provider></div>
}

export function useMode(): ThemeCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error("useMode must be used within ThemeProvider")
  return ctx
}
```
> Tailwind reads mode via the `[data-mode="meridian"]` selector (set in `globals.css` for density vars; components use `data-mode` ancestor + Tailwind variants where needed). Keep the provider's `value` memoized if lint complains (`useMemo`).

- [ ] **Step 4: Run → GREEN.** Re-run. `npm run typecheck` clean.

- [ ] **Step 5: Commit.**
```bash
git add frontend/src/lib/theme.tsx frontend/src/lib/theme.test.tsx
git commit -m "feat(frontend): hearth/meridian theme provider + mode toggle"
```

---

### Task 4: UI primitives (Button, Card, Input, Badge, StatusBadge, Skeleton)

**Files:**
- Create: `frontend/src/components/ui/{Button,Card,Input,Badge,StatusBadge,Skeleton}.tsx`, `frontend/src/components/ui/StatusBadge.test.tsx`

**Interfaces:**
- Produces: presentational primitives styled with the Task 1 tokens. `StatusBadge({ status }: { status: string })` maps a source `import_status` to label + color: `VERIFIED` → status-verified, `INGESTING`/`PENDING` → status-ingesting (with a pulsing dot for INGESTING), `QUARANTINED`/`PURGED` → status-quarantined; unknown → ash. Uses Geist Mono. `Skeleton` is a non-spinner shimmer block (no circular spinner — banned).

- [ ] **Step 1: Failing test** `frontend/src/components/ui/StatusBadge.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react"
import { expect, test } from "vitest"
import { StatusBadge } from "./StatusBadge"

test("renders the status label in uppercase mono", () => {
  render(<StatusBadge status="VERIFIED" />)
  expect(screen.getByText("VERIFIED")).toBeInTheDocument()
})

test("maps unknown status without crashing", () => {
  render(<StatusBadge status="WEIRD" />)
  expect(screen.getByText("WEIRD")).toBeInTheDocument()
})
```

- [ ] **Step 2: Run → RED.**

- [ ] **Step 3: Implement** the primitives. `StatusBadge.tsx` carries the explicit mapping (this is the testable logic):
```tsx
const COLORS: Record<string, string> = {
  VERIFIED: "text-status-verified",
  INGESTING: "text-status-ingesting",
  PENDING: "text-status-ingesting",
  QUARANTINED: "text-status-quarantined",
  PURGED: "text-status-quarantined",
}

export function StatusBadge({ status }: { status: string }) {
  const color = COLORS[status] ?? "text-ash"
  return (
    <span className={`font-mono text-xs uppercase tracking-wide ${color}`}>
      {status === "INGESTING" && (
        <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-status-ingesting align-middle" />
      )}
      {status}
    </span>
  )
}
```
Build `Button` (ember primary / ash ghost, radius via mode), `Card` (chamber surface, whisper border, mode radius), `Input` (ember focus ring), `Badge` (generic pill), `Skeleton` (`animate-pulse` block) from the DESIGN.md component stylings. Keep each file small and presentational; no business logic.

- [ ] **Step 4: Run → GREEN.** `npm test -- src/components/ui` + `npm run typecheck`.

- [ ] **Step 5: Commit.**
```bash
git add frontend/src/components/ui
git commit -m "feat(frontend): ui primitives + status badge"
```

---

### Task 5: Authed app shell (sidebar + mode chrome)

> **Controller pre-step (before dispatching this task):** pull the Stitch reference HTML into `frontend/design/` for the dashboard screens (Hearth `3656a89b…`, Meridian `1e51f315…`) so this and later tasks port the nav/sidebar structure from local files.

**Files:**
- Create: `frontend/src/components/layout/Sidebar.tsx`, `frontend/src/components/layout/ModeToggle.tsx`, `frontend/src/app/(app)/layout.tsx`

**Interfaces:**
- Consumes: `useMode` (T3), primitives (T4).
- Produces: `(app)/layout.tsx` — wraps authed pages in `ThemeProvider` + chrome. **Hearth:** left sidebar (Overview/Import/Sources/Observations), teal active indicator, `hearth-surface` canvas. **Meridian:** compact top "Instrument Panel" nav, `archive` canvas, tight density. `ModeToggle` flips modes. **Orb: leave a `data-orb-slot` placeholder div with a comment — not implemented this plan.**

- [ ] **Step 1:** Build `Sidebar.tsx` and `ModeToggle.tsx`, porting nav structure from `frontend/design/dashboard-hearth.html` / `dashboard-meridian.html`, mapping hardcoded hex → Tailwind tokens. Active link = current route (`usePathname`). Nav items link to `/dashboard`, `/import`, `/sources`, `/observations`.
- [ ] **Step 2:** Build `(app)/layout.tsx` composing `ThemeProvider` → chrome → `{children}`, switching sidebar (Hearth) vs top-nav (Meridian) off `useMode`. Include the Orb placeholder slot.
- [ ] **Step 3: Verify render.** Add a throwaway `(app)/dashboard/page.tsx` stub returning `<main>shell</main>` if not present, then `npm run build`. Manually confirm via `npm run dev` that the shell renders in both modes and the toggle works (no test required for layout chrome — visual).
- [ ] **Step 4: Lint/build.** `npm run lint && npm run build`.
- [ ] **Step 5: Commit.**
```bash
git add frontend/src/components/layout "frontend/src/app/(app)/layout.tsx" frontend/design
git commit -m "feat(frontend): authed shell — sidebar, mode chrome, orb placeholder"
```

---

### Task 6: Login page + auth routing

**Files:**
- Create: `frontend/src/app/login/page.tsx`, `frontend/src/app/page.tsx`, `frontend/src/app/(app)/auth-gate.tsx` (client guard), `frontend/src/app/login/login-form.test.tsx`

**Interfaces:**
- Consumes: `login`, `me` (T2), primitives (T4).
- Produces: `/login` (password-only form per DESIGN.md Screen 1 — "Enter Archive" ember button, ceremonial dark card). `/` redirects: calls `me()`; authed → `/dashboard`, else → `/login`. `(app)/auth-gate.tsx` — a client component used in `(app)/layout.tsx` that calls `me()` on mount and `router.replace("/login")` on null.

- [ ] **Step 1: Failing test** `frontend/src/app/login/login-form.test.tsx` — render the form, type a password, submit, assert `login()` is called and on success it navigates. Mock `@/lib/api` `login` and `next/navigation` `useRouter`:
```tsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, test, vi } from "vitest"

const push = vi.fn()
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: push, push }) }))
const login = vi.fn().mockResolvedValue({ userId: "u1" })
vi.mock("@/lib/api", () => ({ login: (...a: unknown[]) => login(...a), ApiError: class extends Error {} }))

import { LoginForm } from "./login-form"

test("submits password and redirects to dashboard on success", async () => {
  render(<LoginForm />)
  await userEvent.type(screen.getByLabelText(/password/i), "secret")
  await userEvent.click(screen.getByRole("button", { name: /enter archive/i }))
  expect(login).toHaveBeenCalledWith("secret")
})

test("shows an error message on 401", async () => {
  login.mockRejectedValueOnce(Object.assign(new Error("bad"), { status: 401 }))
  render(<LoginForm />)
  await userEvent.type(screen.getByLabelText(/password/i), "nope")
  await userEvent.click(screen.getByRole("button", { name: /enter archive/i }))
  expect(await screen.findByRole("alert")).toBeInTheDocument()
})
```
> Extract the form into `login/login-form.tsx` (client component) so it is unit-testable; `login/page.tsx` is a thin wrapper.

- [ ] **Step 2: Run → RED.**
- [ ] **Step 3: Implement** `login/login-form.tsx` (state, submit → `login()` → `router.replace("/dashboard")`, catch → set error shown in `role="alert"`), `login/page.tsx` (ceremonial layout, dark `archive` bg, centered `chamber` card, Outfit "LociGraph" heading, ember focus, "Enter Archive" button), `app/page.tsx` (server or client redirect via `me()`), and `(app)/auth-gate.tsx` wired into `(app)/layout.tsx`.
- [ ] **Step 4: Run → GREEN.** `npm test -- src/app/login` + `npm run typecheck`.
- [ ] **Step 5: Commit.**
```bash
git add "frontend/src/app/login" "frontend/src/app/page.tsx" "frontend/src/app/(app)/auth-gate.tsx" "frontend/src/app/(app)/layout.tsx"
git commit -m "feat(frontend): login page + auth routing guard"
```

---

### Task 7: Dashboard page

**Files:**
- Create: `frontend/src/app/(app)/dashboard/page.tsx`, `frontend/src/components/domain/StatCard.tsx`, `frontend/src/app/(app)/dashboard/dashboard.test.tsx`

**Interfaces:**
- Consumes: `listSources` (T2), `StatCard`, `StatusBadge`, `Skeleton`, `useMode`.
- Produces: a dashboard that fetches sources and renders three derived stats — **Total Sources**, **Verified**, **In-flight** (`import_status ∈ {PENDING, INGESTING}`) — plus a recent-activity list (newest sources with filename, `StatusBadge`, type). Stat numbers in Geist Mono accent (teal in Hearth, ember in Meridian). Skeleton while loading. **Not** a 3-equal-column layout (asymmetric per DESIGN.md). Port visual structure from `frontend/design/dashboard-*.html`.

- [ ] **Step 1: Failing test** `dashboard.test.tsx` — mock `@/lib/api listSources` to return a mix of statuses; render inside `ThemeProvider`; assert the three computed numbers appear and a recent row renders. Example: 3 sources (2 VERIFIED, 1 PENDING) → Total `3`, Verified `2`, In-flight `1`.
- [ ] **Step 2: Run → RED.**
- [ ] **Step 3: Implement** the page (client component: `useEffect` → `listSources`, `useState` for loading/data, compute counts; render `StatCard`s + activity list). Add a `lib/derive.ts` pure helper `summarize(sources): {total, verified, inFlight}` and **unit-test that helper** (pure function — easy, high-value) rather than asserting DOM numbers if simpler.
- [ ] **Step 4: Run → GREEN.** `npm test -- src/app/(app)/dashboard` (and the derive test) + typecheck.
- [ ] **Step 5: Commit.**
```bash
git add "frontend/src/app/(app)/dashboard" frontend/src/components/domain/StatCard.tsx frontend/src/lib/derive.ts frontend/src/lib/derive.test.ts
git commit -m "feat(frontend): dashboard with derived stats + recent activity"
```

---

### Task 8: Import page (upload)

> **Controller pre-step:** pull Stitch Import HTML into `frontend/design/import-dark.html` + `import-teal.html`.

**Files:**
- Create: `frontend/src/app/(app)/import/page.tsx`, `frontend/src/app/(app)/import/import-form.tsx`, `frontend/src/app/(app)/import/import-form.test.tsx`

**Interfaces:**
- Consumes: `uploadSource`, `SOURCE_TYPES` (T2), `ApiError`, primitives.
- Produces: a drop zone + file picker + `source_type` selector (the six types) + "Browse Files"/submit. On success → `202`, show the returned `source_id` + PENDING status and a link to `/sources`. Surface `400` (invalid type) and `409` (duplicate) as inline messages. Dashed ember drop zone per DESIGN.md Screen 4; format cards grid (not 3-equal-column — use the Stitch grid).

- [ ] **Step 1: Failing test** `import-form.test.tsx` — mock `uploadSource`; select a type, attach a `File`, submit; assert `uploadSource("json", file)` called and success state shows the source id. Add a case: `uploadSource` rejects with `{status:409}` → a `role="alert"` "duplicate" message shows.
- [ ] **Step 2: Run → RED.**
- [ ] **Step 3: Implement** `import-form.tsx` (controlled `sourceType`, `File` state via input + drag/drop handlers, submit → `uploadSource`, success/error UI) and `import/page.tsx` (chrome + heading "Import Source", port drop-zone visuals).
- [ ] **Step 4: Run → GREEN** + typecheck.
- [ ] **Step 5: Commit.**
```bash
git add "frontend/src/app/(app)/import"
git commit -m "feat(frontend): import page — upload with type select + 400/409 handling"
```

---

### Task 9: Sources page (list + filters)

**Files:**
- Create: `frontend/src/app/(app)/sources/page.tsx`, `frontend/src/components/domain/SourceRow.tsx`, `frontend/src/app/(app)/sources/sources.test.tsx`

**Interfaces:**
- Consumes: `listSources` (T2), `StatusBadge`, `Skeleton`.
- Produces: a Meridian-density table (filename in Outfit cream, type pill, `StatusBadge`, file size + count placeholder in Geist Mono) with client-side status filter pills (All / Pending / Ingesting / Verified / Quarantined / Purged) filtering the fetched list, and a total-count badge. **Hand-build from DESIGN.md Screen 5** (no Stitch screen). Per-source observation count is not available from the API → omit that column for Phase 0 (note in code comment); do not add a backend endpoint.

- [ ] **Step 1: Failing test** `sources.test.tsx` — mock `listSources` with several statuses; render; assert all rows show; click the "Verified" filter pill → only VERIFIED rows remain. (Filtering is the testable logic — extract `filterByStatus(sources, status)` into `lib/derive.ts` and unit-test it.)
- [ ] **Step 2: Run → RED.**
- [ ] **Step 3: Implement** `SourceRow.tsx`, the page (fetch + filter state + pills), and the `filterByStatus` helper.
- [ ] **Step 4: Run → GREEN** + typecheck.
- [ ] **Step 5: Commit.**
```bash
git add "frontend/src/app/(app)/sources" frontend/src/components/domain/SourceRow.tsx frontend/src/lib/derive.ts frontend/src/lib/derive.test.ts
git commit -m "feat(frontend): sources table with status filter pills"
```

---

### Task 10: Observations page

> **Controller pre-step:** pull Stitch Observation Browser HTML into `frontend/design/observations-darkteal.html` + `observations.html`.

**Files:**
- Create: `frontend/src/app/(app)/observations/page.tsx`, `frontend/src/components/domain/ObservationCard.tsx`, `frontend/src/app/(app)/observations/observations.test.tsx`

**Interfaces:**
- Consumes: `listObservations` (T2), `useMode`.
- Produces: a filter bar (source filter, speaker filter, status filter → passed to `listObservations`) + stacked `ObservationCard`s (content in Outfit, max ~65ch, line-height 1.7; metadata row in Geist Mono: timestamp · source · speaker · confidence). Hearth = light teal cards w/ teal left-accent on selection; Meridian = dense dark. Port from `frontend/design/observations-*.html`.

- [ ] **Step 1: Failing test** `observations.test.tsx` — mock `listObservations` returning two observations; render; assert both contents render and the metadata (confidence in mono) shows. Add: typing in the speaker filter and submitting calls `listObservations({ speaker: "x" })`.
- [ ] **Step 2: Run → RED.**
- [ ] **Step 3: Implement** `ObservationCard.tsx` + the page (filter state → re-fetch on apply, skeleton while loading).
- [ ] **Step 4: Run → GREEN** + typecheck.
- [ ] **Step 5: Commit.**
```bash
git add "frontend/src/app/(app)/observations" frontend/src/components/domain/ObservationCard.tsx
git commit -m "feat(frontend): observations browser with filters"
```

---

### Task 11: Dockerize frontend + Caddy + compose

**Files:**
- Create: `frontend/Dockerfile`, `frontend/.dockerignore`
- Modify: `docker-compose.yml` (add `frontend` service), `Caddyfile` (serve frontend + `/api/*` → backend)

**Interfaces:** `docker compose up` brings up all 6 services (postgres, redis, backend, worker, frontend, caddy). Caddy serves the frontend at `:80` and proxies `/api/*` → `backend:8000`.

- [ ] **Step 1: `frontend/Dockerfile`** — multi-stage Next standalone:
```dockerfile
FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:20-slim AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-slim AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```
`frontend/.dockerignore`: `node_modules`, `.next`, `.git`, `playwright-report`, `test-results`.

- [ ] **Step 2: `docker-compose.yml`** — add:
```yaml
  frontend:
    build: ./frontend
    environment:
      BACKEND_ORIGIN: http://backend:8000
    depends_on: [backend]
```
(No published port; Caddy fronts it.) Keep all existing services intact.

- [ ] **Step 3: `Caddyfile`** — serve the SPA and proxy the API:
```
:80 {
	handle /api/* {
		uri strip_prefix /api
		reverse_proxy backend:8000
	}
	handle {
		reverse_proxy frontend:3000
	}
}
```
(Replaces the placeholder `respond` line; the API handler is unchanged.)

- [ ] **Step 4: Verify.** `docker compose config` validates. Then `docker compose up -d --build frontend caddy backend` and confirm: `curl -s localhost/api/auth/me` → `401` (proxied to backend), `curl -sI localhost/` → `200` and HTML from Next. If full build is too heavy in the environment, validate `docker compose config` + a standalone `docker compose build frontend` and report honestly. Bring added services down after (leave postgres/redis up).

- [ ] **Step 5: Commit.**
```bash
git add frontend/Dockerfile frontend/.dockerignore docker-compose.yml Caddyfile
git commit -m "chore(frontend): dockerize + caddy serves SPA with /api proxy"
```

---

### Task 12: Smoke e2e (login → import → sources) + final gate

**Files:**
- Create: `frontend/src/test/e2e/smoke.spec.ts`

**Interfaces:** none (test only). Proves the real stack: log in, upload a JSON source, see it appear in the Sources list.

- [ ] **Step 1: Write the smoke test** `frontend/src/test/e2e/smoke.spec.ts`:
```ts
import { expect, test } from "@playwright/test"

const PASSWORD = process.env.LOCIGRAPH_PASSWORD || "test-password-123"

test("login, import a JSON source, see it in Sources", async ({ page }) => {
  await page.goto("/login")
  await page.getByLabel(/password/i).fill(PASSWORD)
  await page.getByRole("button", { name: /enter archive/i }).click()
  await expect(page).toHaveURL(/\/dashboard/)

  await page.goto("/import")
  await page.getByLabel(/source type/i).selectOption("json")
  await page.setInputFiles('input[type="file"]', {
    name: "e2e.json",
    mimeType: "application/json",
    buffer: Buffer.from('[{"text":"hello e2e"}]'),
  })
  await page.getByRole("button", { name: /upload|browse|import/i }).first().click()
  await expect(page.getByText(/PENDING|pending/)).toBeVisible()

  await page.goto("/sources")
  await expect(page.getByText("e2e.json")).toBeVisible()
})
```
> The test runs against a live stack. Document the prerequisite in the test header: backend + DB up with a seeded user (`init_user`), and `npm run dev` (with `BACKEND_ORIGIN` set) or `docker compose up`. The e2e is allowed to be skipped in environments without the running stack (`test.skip(!process.env.E2E_BASE_URL && !process.env.E2E_RUN)`), but the controller MUST run it once against a real stack and record the result.

- [ ] **Step 2: Run the e2e against a live stack.** Bring up backend + DB (`docker compose up -d postgres redis backend`, run `init_user`), start `npm run dev`, then `E2E_RUN=1 npm run test:e2e`. Record pass/fail + any screenshot artifact.
- [ ] **Step 3: Final gate.** `npm run lint && npm run typecheck && npm run build && npm test` — all clean. Report the unit test count.
- [ ] **Step 4: Commit.**
```bash
git add frontend/src/test/e2e/smoke.spec.ts
git commit -m "test(frontend): smoke e2e — login → import → sources"
```

---

## Self-Review

**Spec coverage (Phase 0 spec §"Next.js frontend: Login, Dashboard, Import, Sources, Observations" + DESIGN.md):**
- Login → Task 6 ✓ · Dashboard → Task 7 ✓ · Import → Task 8 ✓ · Sources → Task 9 ✓ · Observations → Task 10 ✓
- Dual-mode (Hearth/Meridian) + toggle + density tokens → Tasks 1, 3, 5 ✓ · Orb → explicitly deferred (placeholder slot, Task 5) ✓
- Design tokens, fonts, anti-patterns → Task 1 + Global Constraints, enforced in every visual task ✓
- Typed API client over one origin, no CORS → Task 2 + Global Constraints ✓
- 6-service Docker Compose + Caddy SPA/API routing → Task 11 ✓
- Lean testing (API client, theme, StatusBadge, derive helpers, login form; one Playwright smoke) → Tasks 2,3,4,6,7,9,12 ✓

**Decisions baked in (flag for review):**
- **Hand-build Login + Sources** (no Stitch screen exists for them) from DESIGN.md prompts; all other screens port from the shared Stitch project.
- **Dashboard stats derive from `GET /sources`** (total / verified / in-flight) — no jobs or observation-count endpoint added. Accurate global counts deferred.
- **Auth via `GET /auth/me` client guard** (not Next middleware) — middleware can't read an httpOnly cookie's validity without calling the backend anyway; a client gate keeps it simple for a single-user app.
- **Orb/Core + Planetarium/Graph deferred** — Planetarium needs concepts/graph data that Phase 0 doesn't produce.
- **`next/font` for Geist via the `geist` package**; Outfit via `next/font/google`. No webfont `<link>` (keeps it offline-friendly, satisfies no-Inter).
- **Pinned dependency versions** for reproducible builds (Next 14.2.5 line).

**Out of scope (later plans):** the animated Orb/Core, the Planetarium knowledge-graph view, accurate global counts / jobs UI, real-time job-status polling/websockets, source detail/quarantine actions, Plan 5 CI (will run `npm run build/lint/test` for the frontend).

**Placeholder scan:** API client, theme, StatusBadge, login form, and derive helpers ship with complete code + tests. Visual page/component bodies are specified by (a) the exact API/types they consume, (b) the named Stitch screen to port or DESIGN.md screen to build, and (c) the token mapping — the honest representation for taste-driven UI built from a design source, per the chosen build method. **Type/interface consistency:** `lib/api.ts` return types match `lib/types.ts`; pages consume only those typed functions; `Mode` and `useMode` are used identically across shell, dashboard, observations.

**Note for executor:** Tasks 1–4, 6–10 need only Node (no backend). Task 12 needs the live stack (backend + DB + seeded user). Task 11 needs Docker. Before Tasks 5, 8, 10 the controller drops the referenced Stitch HTML into `frontend/design/`.
