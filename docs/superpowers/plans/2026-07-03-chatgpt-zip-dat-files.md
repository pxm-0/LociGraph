# ChatGPT Export `.dat` File Compatibility

## Summary
Confirm (via test) that `.dat` and other non-JSON sibling files inside a
real ChatGPT export zip are already harmless to `ChatGptParser`, and fix
two small gaps found while confirming it: a nested (non-root)
`conversations.json` isn't found today, and a missing-file failure raises
an unfriendly raw `KeyError` instead of a clear message. Spec:
`docs/superpowers/specs/2026-07-03-chatgpt-zip-dat-files-design.md`.

Single-file change: `kernel/ingestion/chatgpt_parser.py` +
`tests/kernel/ingestion/test_chatgpt_parser.py`. No backend/frontend
changes.

## Task Briefs

### Task 1: regression test + nested-path + friendly-error fixes
- In `tests/kernel/ingestion/test_chatgpt_parser.py`, add
  `test_ignores_non_json_zip_members_like_dat_files`: build a temp zip
  (same pattern as the existing
  `test_extracts_messages_from_a_real_export_zip`) containing
  `conversations.json` plus a `.dat` member with arbitrary binary
  content (e.g. `zf.writestr("assets/voice-message-a1b2c3.dat",
  b"\x00\x01\xff\xfe not valid utf-8 \x80\x81")`), and assert
  `ChatGptParser().parse(zip_path)` returns the same fragments as the
  plain-conversations.json case, proving the binary sibling doesn't
  affect parsing.
- Add `test_finds_conversations_json_nested_in_a_subdirectory`: build a
  temp zip with `conversations.json` stored as
  `"chatgpt-export/conversations.json"` (not at the root), and assert
  parsing still succeeds with the same fragments.
- Add `test_raises_a_clear_error_when_conversations_json_is_missing`:
  build a temp zip containing only an unrelated file (e.g.
  `zf.writestr("user.json", "{}")`, no `conversations.json` anywhere),
  and assert `ChatGptParser().parse(zip_path)` raises `ValueError` with
  a message containing `"conversations.json"` (don't assert the exact
  string verbatim — assert `"conversations.json" in str(exc_info.value)`
  — so the test doesn't become brittle to minor message wording).
- Run these three new tests first and confirm exactly which ones fail
  against the current code before implementing anything (the
  binary-sibling test should already pass unmodified, per the design
  doc's "what's already handled" section — if it doesn't, stop and
  re-read `_read_conversations_json` before proceeding, since that would
  mean the design's assumption was wrong).
- In `kernel/ingestion/chatgpt_parser.py`'s `_read_conversations_json`,
  update the zip-branch lookup: try `zf.read("conversations.json")`
  first; on `KeyError`, search `zf.namelist()` for any entry whose name
  ends with `"/conversations.json"` and use the first match's bytes via
  `zf.read(match)`; if neither lookup finds anything, raise
  `ValueError("no conversations.json found in ChatGPT export zip")`
  (don't let the underlying `KeyError` propagate).
- Run all four zip-related tests (the original
  `test_extracts_messages_from_a_real_export_zip` plus the three new
  ones) and the full `test_chatgpt_parser.py` file — all green.

## Testing
Run: `.venv/bin/pytest tests/kernel/ingestion/test_chatgpt_parser.py -v`
— expect 5 tests passing (2 original + 3 new). Then the full suite:
`.venv/bin/pytest -q`, `.venv/bin/ruff check kernel tests`,
`.venv/bin/mypy kernel` — all clean.

## Docs, review, publish
Folded into Task 1 above given the small size of this plan (one file,
one test file) — no separate docs/review task needed. Commit when Task
1's tests and gates are green. Do not push or open a PR — same
convention as the other two plans running alongside this one.

## Out of Scope
(carried over from the spec, unchanged)
- Extracting content from `.dat`/non-JSON zip members.
- Any other source type's zip handling.
- Content validation/scanning of attachments beyond locating
  `conversations.json`.
