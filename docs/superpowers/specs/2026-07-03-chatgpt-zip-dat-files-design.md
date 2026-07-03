# ChatGPT Export `.dat` File Compatibility — Design

## Summary
Real ChatGPT "Export data" zips contain more than `conversations.json` —
sibling files including some with a `.dat` extension (binary
attachments/blobs referenced from within `conversations.json`, not
conversation text themselves). `kernel/ingestion/chatgpt_parser.py`'s
existing zip-extraction fix (landed 2026-07-03, commit `3fd609f`) already
reads only `conversations.json` out of the archive via
`zf.read("conversations.json")` and never touches any other member —
which means `.dat` files sitting alongside it are already inert as far as
parsing is concerned. This plan verifies that explicitly with a test
using a real `.dat` member, and adds two small pieces of defensive
robustness uncovered while confirming it.

## Design

### What's already handled (verify, don't re-fix)
`ChatGptParser._read_conversations_json` only ever calls
`zf.read("conversations.json")` — it never iterates or opens any other
zip member. A `.dat` file (or any other sibling: `user.json`,
`chat.html`, media folders) sitting in the same archive cannot affect
parsing, regardless of its size or content, since `zipfile.ZipFile.read`
reads only the requested member's decompressed bytes. Add a regression
test with a `.dat` member present to lock this in and document it as
intentional, not accidental.

### Two gaps found while confirming this
1. **`conversations.json` not at the zip root.** Some export tooling
   nests files under a top-level folder (e.g.
   `chatgpt-export-2026-07-01/conversations.json`). The current lookup
   is an exact-name match against the root, so a nested archive would
   raise a raw `KeyError`. Fix: if the exact `"conversations.json"` name
   isn't present, fall back to searching `zf.namelist()` for any entry
   whose name **ends with** `"/conversations.json"` (still a full,
   unambiguous filename match, not a substring match) and use the first
   one found.
2. **Missing-file error is an unfriendly raw `KeyError`.** If no
   `conversations.json` is found by either lookup, raise a clear
   `ValueError("no conversations.json found in ChatGPT export zip")`
   instead of letting zipfile's `KeyError` propagate. Parsing happens
   during ingest, and `worker/tasks/ingest_source.py`'s exception
   handler (`except Exception as exc: ... error=str(exc)`, line ~63)
   records `str(exc)` directly with no redaction pass (unlike
   `extract_claims.py`/`embed_claims.py`'s `_public_error` — parsing
   errors don't carry secrets, so that's fine as-is). This is the exact
   string a user sees in the job's error field, so it should say what's
   actually wrong rather than a generic `KeyError` repr.

## Out of Scope
- Extracting anything *from* `.dat` files or other non-JSON zip members
  — they carry no conversation text `ChatGptParser` needs; this plan
  only confirms their presence is harmless, not that their content gets
  used.
- Any other source type's zip handling (this is specific to `chatgpt`).
- Validating zip contents beyond locating `conversations.json` (e.g. no
  checksum/virus-style scanning of attachments).
