# LociGraph: what we actually built (PR #1 + #2)

A guided tour of the first two slices of Phase 0 — the tenant-isolated **data layer** (PR #1) and the **ingestion kernel** (PR #2). The goal isn't to list files; it's to teach the ideas underneath, including the bugs we hit and why they matter.

> A styled, browsable version of this guide is also published as an artifact. This Markdown copy is the canonical, in-repo reference.

**Scope:** PR #1 · Foundation & Data Layer · PR #2 · Ingestion Kernel — Python 3.12, async, PostgreSQL, TDD.

---

## 0 · The mental model

LociGraph turns raw personal data into **concepts**. Everything flows along one pipeline. PR #1 and #2 built the *left half* of it — getting raw sources into clean, evidence-bearing observations.

```
Source → Fragment → Observation → Claim → Concept → …Planetarium
└──────── built so far ────────┘
```

- A **Source** is an uploaded file.
- A **Fragment** is one extracted chunk (a chat message, a PDF page, a paragraph).
- An **Observation** is a normalized, queryable unit of evidence.

Two architectural commitments shaped everything:

- **Multi-tenant from day one** — every row belongs to a user, and the database itself enforces that one user can never see another's data. That's PR #1.
- **A pure "kernel"** — the business logic (`kernel/`) has no web framework in it. The API and workers are thin shells around it. PR #2's parsers live here and are pure functions: file in, data out, no database.

---

## 1 · The stack & why each piece exists

| Piece | What it is | Why we chose it |
|---|---|---|
| **PostgreSQL 16 + pgvector** | The database. pgvector adds vector columns for future semantic search. | Postgres has *Row-Level Security* — the feature our whole tenant-isolation model rests on. |
| **Redis** | In-memory store; will back the background job queue. | Standard broker for async work (Plan 3). |
| **SQLAlchemy 2.0 (Core, async)** | Talks to Postgres over `asyncpg`. | "Core" = we write SQL ourselves (no ORM magic), keeping the RLS transaction lifecycle explicit. |
| **Alembic** | Versioned database migrations. | The schema lives in code and is reproducible/reversible. |
| **Docker Compose (via colima)** | Runs Postgres + Redis locally. | One command to a real environment; maps 1:1 to AWS ECS later. No Kubernetes — needless overhead here. |

---

## 2 · Row-Level Security — the heart of PR #1 ★

This is the most important concept in the whole project, so we'll go slow.

### The problem

Multiple users share one database and one set of tables. How do you guarantee user A can *never* read user B's rows — even if you write a buggy query that forgets `WHERE user_id = …`?

### The answer: let the database enforce it

PostgreSQL **Row-Level Security (RLS)** attaches a *policy* to a table. The policy is a boolean rule evaluated on every row the query touches. Rows that fail the rule are invisible — they can't be selected, updated, or deleted. The check happens *inside the storage engine*, below your application code, so an app bug can't bypass it.

```sql
-- every data table gets this
ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE sources FORCE  ROW LEVEL SECURITY;

CREATE POLICY sources_user_isolation ON sources
  USING      (user_id = current_setting('app.current_user_id')::uuid)   -- reads/updates/deletes
  WITH CHECK (user_id = current_setting('app.current_user_id')::uuid);  -- inserts/updates
```

Two halves of the policy, and you need both:

- **USING** filters what you can *see/modify*. Without it, you could read others' rows.
- **WITH CHECK** validates what you *write*. Without it, user B could `INSERT` a row stamped with user A's id — poisoning A's data.

The rule compares each row's `user_id` against `current_setting('app.current_user_id')` — a per-connection variable the app sets to "who is asking right now."

> **⚠ Footgun #1 — the owner bypass.** By default, RLS is **not enforced against the table's owner.** If the app connected as the role that owns the tables, every policy would silently do nothing and all users could read everything. We avoid this two ways: (1) the app connects as a dedicated **non-owner** role `locigraph_app` that owns nothing; (2) `FORCE ROW LEVEL SECURITY` makes the policy apply even to owners as a backstop. The owner role `locigraph` is used *only* to run migrations.

> **⚠ Footgun #2 — fail-closed, not fail-open.** We call `current_setting('app.current_user_id')` *without* the "missing_ok" flag. So if the variable was never set, the query **raises an error** instead of returning NULL. "No identity set" must mean "no data" — never "all data." A test proves a context-less query throws.

### The two-role model

- **`locigraph`** (owner) → runs migrations only. Creates tables, owns them.
- **`locigraph_app`** (non-owner) → the app + workers connect as this. RLS fully enforced. Granted only SELECT/INSERT/UPDATE/DELETE — never ownership, never `SUPERUSER`, never `BYPASSRLS`.

---

## 3 · The async session contract

RLS needs the app to announce "who is asking" before each query. That's the job of one carefully-written context manager — **the single doorway to the database** in the whole kernel.

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def session(user_id):
    engine = get_engine()                          # connects as locigraph_app
    async with engine.connect() as conn:
        async with conn.begin():                   # ← opens a TRANSACTION
            await conn.execute(
                text("SELECT set_config('app.current_user_id', :uid, true)"),
                {"uid": str(user_id)},             # bound param — never string-glued
            )
            yield conn                             # your queries run here, scoped to user_id
```

Three subtle things make this correct:

> **⚠ Footgun #3 — why `set_config(…, true)` inside a transaction.** The `true` third argument makes the setting **transaction-local** — it's reset when the transaction ends. This matters because connections are *pooled and reused*. A plain session-level variable would linger on the connection after the request finished, and the *next* request that grabbed that same connection would inherit the *previous* user's identity — a silent cross-tenant leak. Transaction-local scoping means a returned connection always carries zero leftover identity.

- **Bound parameter, not string formatting.** The user id goes in as `:uid`, never f-string-glued into SQL. This prevents SQL injection — the database treats it as data, never as code.
- **It's the *only* way to get a connection.** There's no API to query without going through `session(user_id)`, so there's no path that skips setting the tenant context. Security by construction, not by discipline.

---

## 4 · Repositories & immutability

On top of the session, each table gets a **repository** — a small class that turns method calls into SQL:

```python
class SourceRepository(BaseRepository):
    async def create(self, user_id, source_type, checksum, ...) -> Source:
        row = (await self.conn.execute(
            text("INSERT INTO sources (...) VALUES (:user_id, :source_type, ...) "
                 "RETURNING ..."),
            {"user_id": str(user_id), ...},        # all values bound
        )).mappings().one()
        return Source.from_row(row)                # → immutable object
```

- **Repository pattern** — business logic depends on `create()`/`get()`, not on raw SQL strings. Swappable and testable.
- **Immutable domain models** — `Source`, `Observation`, etc. are `@dataclass(frozen=True)`. Once built, they can't be mutated. New objects instead of in-place edits kills a whole class of "spooky action at a distance" bugs.
- **Every value is a bound parameter** — across all four repositories, no user data is ever concatenated into SQL.

---

## 5 · Proving isolation actually works

An invisible security property is worthless unless you can demonstrate it. PR #1 ends with a **security gate** — an integration test that tries to break isolation and asserts it can't:

```python
# user A creates a source; user B must not see it
async with session(user_a) as conn:
    src = await SourceRepository(conn).create(user_a, ...)

async with session(user_b) as conn:
    leaked = await SourceRepository(conn).get(src.id)
assert leaked is None                              # RLS hides A's row from B
```

Three vectors are tested: B can't *read* A's rows, B can't *insert* a row stamped as A (WITH CHECK), and observations are isolated too. **All three pass** — the runtime proof the policy chain holds end to end.

> **✓ The lesson.** The test connects as the *non-owner* role on purpose. A test that ran as the owner would pass even if RLS were completely broken (owner bypass!). The test's own setup is part of the security argument.

---

## 6 · PR #2 — the ingestion pipeline

PR #2 is the other end: taking a raw uploaded file and producing observations.

```
file.pdf/.json/… → Parser.parse() → list[ParsedFragment] → Normalizer → observation rows
```

The defining property: **this whole layer is pure.** No database, no network, no global state — just functions from a file path to data. That makes it trivially testable (feed a fixture file, check the output) and means it has zero coupling to RLS or async. The database wiring happens later, in the worker (Plan 3).

---

## 7 · The Parser protocol — structural typing

Six different file formats, one shared shape, expressed with a Python **Protocol**:

```python
@runtime_checkable
class Parser(Protocol):
    def parse(self, path: Path) -> list[ParsedFragment]: ...
```

This is **structural typing** (duck typing made explicit): a class *is* a `Parser` if it has a `parse` method of the right shape — it does *not* need to inherit from anything. Adding a 7th format later means writing one class with one method; nothing else changes. `@runtime_checkable` even lets a test assert `isinstance(JsonParser(), Parser)`.

### ParsedFragment vs Fragment — a deliberate split

- **`ParsedFragment`** (ingestion) — what a parser *produces*: extracted text, an index, optional author/timestamp. Pre-database. Immutable.
- **`Fragment`** (data layer) — the persisted row, with `id`, `user_id`, `source_id`.

A small `to_fragment_row()` method bridges them. Keeping the pure parser output separate from the DB model is what lets the ingestion layer stay database-free.

---

## 8 · The six parsers

| Format | Library | One fragment per… | Notable logic |
|---|---|---|---|
| JSON | stdlib `json` | array item (or whole object) | strings kept as-is; dicts dumped compactly; original kept in `raw_payload` |
| Markdown | mistune 3.x | heading / paragraph / code block | walks the token tree, pulls plain text, skips empties |
| HTML | BeautifulSoup | block element (`p,h1–h6,li,blockquote`) | strips `<script>`/`<style>` first |
| PDF | pdfplumber | page | skips pages with no extractable text |
| ChatGPT export | stdlib `json` | message in `conversations.json` | sorts by `create_time` (nulls last); joins content parts; author = role |
| Meta export | stdlib `json` | message | sorts by `timestamp_ms`; epoch-*ms*→UTC; skips media-only msgs |

Every parser returns the same `list[ParsedFragment]`, converts timestamps to UTC, and uses a gap-free running index. The differences are entirely in *how each format exposes its content* — exactly the variation the Parser protocol absorbs.

---

## 9 · The Normalizer

Fragments become observations. The normalizer adds two things worth understanding:

```python
kept = [f for f in fragments if f.extracted_text.strip()]   # drop empties FIRST
for i, frag in enumerate(kept):
    rows.append({
        "content": frag.extracted_text,
        "speaker": frag.author,
        "observed_at": frag.timestamp,
        "context_before": kept[i-1].extracted_text if i > 0 else None,
        "context_after":  kept[i+1].extracted_text if i+1 < len(kept) else None,
        "confidence": 1.0,
    })
```

- **Context window.** Each observation carries the text of its neighbors, preserving a little surrounding context for later interpretation. Crucially, the window is computed over the *kept* list — after empties are removed — so a blank line never becomes a "neighbor."
- **confidence = 1.0.** A placeholder; there's no AI scoring yet. *(Review caught that the observations repository doesn't persist this field yet — tracked for Plan 3. A finding that's real but correctly deferred.)*

---

## 10 · The import-mode bug — a real teaching moment ★

Mid-PR-#2, tests suddenly failed with `ModuleNotFoundError: No module named 'kernel.ingestion.base'` — even though the file existed and imported fine in a plain Python shell.

**What happened:** pytest's default "prepend" import mode imports a test file by walking up through `__init__.py` files to decide its module name. Our test was at `tests/kernel/ingestion/test_base.py`, and both `tests/kernel/` and `tests/kernel/ingestion/` had `__init__.py` — but `tests/` did not. So pytest decided the test's package was `kernel.ingestion.test_base` and put `tests/` on the import path. Now there were *two* things called `kernel`: the real one, and `tests/kernel/`. The fake one won, and it had no `ingestion/base.py` inside it. Collision.

> **✓ The fix (and the principle).** Switch pytest to `--import-mode=importlib` and delete the `__init__.py` files under `tests/`. In importlib mode, pytest imports each test file by its path without hijacking `sys.path`, so a `tests/kernel/` directory can never shadow the real `kernel` package. **Principle:** don't give your test tree package names that collide with your source tree.

The same cleanup moved the "DATABASE_URL must be set" check out of a global fixture into the one fixture that actually opens a database — so the *pure* ingestion tests need no database at all.

---

## 11 · The craft — and every bug we caught

### How the code got written

- **TDD throughout.** Every feature: write a failing test (RED) → minimal code to pass (GREEN) → tidy up. The tests are the spec.
- **Subagent-driven, in parallel.** Each task was implemented by a fresh agent, then reviewed by a separate one, with a final whole-branch review. The six parsers were built by *seven concurrent agents* on disjoint files — real parallelism, because pure parsers don't touch each other.

### Bugs caught before merge (and what each teaches)

| Bug | Lesson |
|---|---|
| RLS not enforced against table owner | Security features have default-off edges; connect as non-owner + `FORCE`. |
| Pooled connections could leak tenant identity | Per-transaction state (`set_config(…, true)`), never session-level, with pooling. |
| Test teardown hit a foreign-key violation | Delete child rows before parents; FKs enforce order even in cleanup. |
| Migration role-creation wasn't re-runnable | Roles are cluster-global; guard `CREATE ROLE` with an existence check. |
| Test package shadowed the source package | Use `importlib` import mode; don't reuse source package names in tests. |
| Normalizer's `confidence` isn't persisted yet | Trace values end-to-end; a column default can mask a dropped field. (Deferred to Plan 3.) |

---

## 12 · Terms you now know

- **Row-Level Security (RLS)** — database-enforced per-row visibility rules.
- **USING / WITH CHECK** — the read-side and write-side halves of an RLS policy.
- **FORCE ROW LEVEL SECURITY** — apply RLS even to a table's owner.
- **set_config(key, val, true)** — set a transaction-local Postgres variable (resets at commit).
- **Fail-closed** — when identity is missing, deny/raise rather than expose.
- **Repository pattern** — a class that encapsulates a table's queries.
- **Frozen dataclass** — an immutable value object.
- **Protocol / structural typing** — "is-a" by shape (methods), not by inheritance.
- **Pure function** — output depends only on input; no side effects, no I/O.
- **Migration** — a versioned, reversible schema change.
- **pytest import modes** — how pytest decides a test file's module name (prepend vs importlib).
- **TDD red/green** — failing test first, then the minimal code to pass it.

---

*Next up — Plan 3: the async worker that connects these two halves (parser → fragments → normalizer → observations), plus JWT auth and the HTTP endpoints. That's where the `confidence` field gets wired through.*
