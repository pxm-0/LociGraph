# Phase 0 — Plan 2: Ingestion Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure-Python ingestion layer that turns raw source files (JSON, Markdown, HTML, PDF, ChatGPT export, Meta export) into normalized observation rows, behind one common `Parser` interface plus a `Normalizer`.

**Architecture:** A `kernel/ingestion/` package. A `Parser` protocol with a single `parse(path) -> list[ParsedFragment]` method; six concrete parsers; a registry that maps a `source_type` string to the right parser. A `Normalizer` converts `ParsedFragment`s into observation row dicts (the shape `ObservationRepository.bulk_insert` consumes), adding a 1-fragment context window. Everything here is pure and deterministic — **no database, no Docker, no network**. Wiring into the worker + repositories happens in Plan 3.

**Tech Stack:** Python 3.12, stdlib `json`, `beautifulsoup4` (HTML), `pdfplumber` (PDF), `mistune` 3.x (Markdown), `fpdf2` (test-only, to generate a PDF fixture). pytest.

## Global Constraints

- Python version floor: **3.12**.
- Parsers are **pure**: `parse(path: Path) -> list[ParsedFragment]`. No DB access, no network, no global state.
- Every parser implements the `Parser` protocol structurally (no inheritance required).
- Parser output objects are **immutable** (`@dataclass(frozen=True, slots=True)`), consistent with `kernel/models.py`.
- A `ParsedFragment.to_fragment_row()` produces a dict whose keys are a superset of what `FragmentRepository.bulk_insert` reads (`raw_index, extracted_text, timestamp, author`); extra keys (e.g. `raw_payload`) are ignored by the current repo and are forward-compatible.
- `Normalizer.normalize(fragments) -> list[dict]` produces observation row dicts with keys `content` (required), `observed_at, speaker, context_before, context_after, confidence`. `confidence` is `1.0` in Phase 0 (no AI scoring). Drop fragments whose `extracted_text` is empty/whitespace.
- `mypy --strict` clean on `kernel`; `ruff check kernel tests` clean (no unused imports; `datetime.UTC` not `timezone.utc`; narrow `pytest.raises` to specific exception types, never bare `Exception`).
- Test coverage minimum: **80%** for `kernel/ingestion`.
- Source-type string constants live in ONE place (`kernel/ingestion/base.py`) and are reused everywhere — no string literals scattered across parsers/registry/tests.
- Naming: `snake_case` functions, `PascalCase` classes, `UPPER_SNAKE_CASE` constants.

## Interface contracts carried over from Plan 1 (do not redefine)

- `FragmentRepository.bulk_insert(rows: list[dict], source_id, user_id)` reads per row: `raw_index, extracted_text, timestamp, author` (via `.get()`).
- `ObservationRepository.bulk_insert(rows: list[dict], source_id, user_id)` reads per row: `content` (required), `observed_at, speaker, fragment_id, context_before, context_after`.
- These repos already exist; Plan 2 does NOT call them. The worker in Plan 3 will glue parser → fragment rows → normalizer → observation rows.

---

## File Structure

```
kernel/ingestion/
├── __init__.py                 # Task 1
├── base.py                     # Task 1 — ParsedFragment, Parser protocol, SourceType consts, registry stub
├── json_parser.py              # Task 2
├── markdown_parser.py          # Task 3
├── html_parser.py              # Task 4
├── pdf_parser.py               # Task 5
├── chatgpt_parser.py           # Task 6
├── meta_parser.py              # Task 7
├── normalizer.py               # Task 8
└── registry.py                 # Task 9 — get_parser(source_type) -> Parser

tests/kernel/ingestion/
├── __init__.py                 # Task 1
├── fixtures/                   # sample source files (added per parser task)
│   ├── sample.json             # Task 2
│   ├── sample.md               # Task 3
│   ├── sample.html             # Task 4
│   ├── conversations.json      # Task 6 (ChatGPT shape)
│   └── meta_messages.json      # Task 7 (Meta shape)
├── test_base.py                # Task 1
├── test_json_parser.py         # Task 2
├── test_markdown_parser.py     # Task 3
├── test_html_parser.py         # Task 4
├── test_pdf_parser.py          # Task 5 (generates its PDF via fpdf2)
├── test_chatgpt_parser.py      # Task 6
├── test_meta_parser.py         # Task 7
├── test_normalizer.py          # Task 8
└── test_registry.py            # Task 9 — routing + end-to-end parse→normalize
```

---

### Task 1: Ingestion package, ParsedFragment, Parser protocol, source-type constants

**Files:**
- Create: `kernel/ingestion/__init__.py`, `kernel/ingestion/base.py`
- Create: `tests/kernel/ingestion/__init__.py`, `tests/kernel/ingestion/test_base.py`
- Modify: `pyproject.toml` (add ingestion deps + test dep)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ParsedFragment` frozen dataclass: `raw_index: int`, `extracted_text: str`, `timestamp: datetime | None = None`, `author: str | None = None`, `raw_payload: dict[str, Any] | None = None`, `metadata: dict[str, Any] | None = None`; method `to_fragment_row() -> dict[str, Any]`.
  - `Parser` protocol: `parse(self, path: Path) -> list[ParsedFragment]`.
  - `SourceType` constants: `JSON="json"`, `MARKDOWN="markdown"`, `HTML="html"`, `PDF="pdf"`, `CHATGPT="chatgpt"`, `META="meta"`; plus `ALL: tuple[str, ...]`.

- [ ] **Step 1: Add dependencies to `pyproject.toml`**

Add to `[project].dependencies`:
```toml
    "beautifulsoup4>=4.12,<5.0",
    "pdfplumber>=0.11,<0.12",
    "mistune>=3.0,<4.0",
```
Add to `[project.optional-dependencies].dev`:
```toml
    "fpdf2>=2.7,<3.0",
```
Then install: `.venv/bin/pip install -e ".[dev]"`

- [ ] **Step 2: Write the failing test**

`tests/kernel/ingestion/__init__.py`: empty file.

`tests/kernel/ingestion/test_base.py`:
```python
from datetime import UTC, datetime

from kernel.ingestion.base import ParsedFragment, SourceType


def test_to_fragment_row_exposes_repo_keys():
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    frag = ParsedFragment(
        raw_index=0, extracted_text="hello", timestamp=ts, author="me"
    )
    row = frag.to_fragment_row()
    assert row["raw_index"] == 0
    assert row["extracted_text"] == "hello"
    assert row["timestamp"] == ts
    assert row["author"] == "me"


def test_parsed_fragment_is_immutable():
    frag = ParsedFragment(raw_index=0, extracted_text="x")
    try:
        frag.extracted_text = "y"  # type: ignore[misc]
        raised = False
    except AttributeError:
        raised = True
    assert raised


def test_source_type_all_contains_every_type():
    assert set(SourceType.ALL) == {
        SourceType.JSON,
        SourceType.MARKDOWN,
        SourceType.HTML,
        SourceType.PDF,
        SourceType.CHATGPT,
        SourceType.META,
    }
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kernel.ingestion'`

- [ ] **Step 4: Implement base**

`kernel/ingestion/__init__.py`:
```python
"""Ingestion layer: raw source files -> ParsedFragments -> observation rows."""
```

`kernel/ingestion/base.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class SourceType:
    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
    CHATGPT = "chatgpt"
    META = "meta"
    ALL: tuple[str, ...] = (JSON, MARKDOWN, HTML, PDF, CHATGPT, META)


@dataclass(frozen=True, slots=True)
class ParsedFragment:
    """One unit of extracted content from a source, before persistence."""

    raw_index: int
    extracted_text: str
    timestamp: datetime | None = None
    author: str | None = None
    raw_payload: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    def to_fragment_row(self) -> dict[str, Any]:
        """Shape consumed by FragmentRepository.bulk_insert (extra keys ignored)."""
        return {
            "raw_index": self.raw_index,
            "extracted_text": self.extracted_text,
            "timestamp": self.timestamp,
            "author": self.author,
            "raw_payload": self.raw_payload,
        }


@runtime_checkable
class Parser(Protocol):
    def parse(self, path: Path) -> list[ParsedFragment]: ...
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_base.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Lint & type check**

Run: `.venv/bin/ruff check kernel tests && .venv/bin/mypy kernel`
Expected: clean

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml kernel/ingestion/__init__.py kernel/ingestion/base.py \
        tests/kernel/ingestion/__init__.py tests/kernel/ingestion/test_base.py
git commit -m "feat: ingestion base — ParsedFragment, Parser protocol, source types"
```

---

### Task 2: JSON parser

**Files:**
- Create: `kernel/ingestion/json_parser.py`
- Create: `tests/kernel/ingestion/fixtures/sample.json`
- Create: `tests/kernel/ingestion/test_json_parser.py`

**Interfaces:**
- Consumes: `ParsedFragment` from `base`.
- Produces: `JsonParser` with `parse(path) -> list[ParsedFragment]`. Rules: if the top-level JSON is a list, emit one fragment per item; if it is an object, emit a single fragment. `extracted_text` = compact JSON dump of the item for non-string items, or the string itself for string items. `raw_payload` = the item if it's a dict, else `{"value": item}`. `raw_index` = position (0 for the single-object case).

- [ ] **Step 1: Write the fixture**

`tests/kernel/ingestion/fixtures/sample.json`:
```json
[
  {"text": "first entry", "author": "alice"},
  {"text": "second entry", "author": "bob"}
]
```

- [ ] **Step 2: Write the failing test**

`tests/kernel/ingestion/test_json_parser.py`:
```python
from pathlib import Path

from kernel.ingestion.json_parser import JsonParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_top_level_array_into_one_fragment_per_item():
    frags = JsonParser().parse(FIXTURES / "sample.json")
    assert len(frags) == 2
    assert frags[0].raw_index == 0
    assert frags[1].raw_index == 1
    assert "first entry" in frags[0].extracted_text
    assert frags[0].raw_payload == {"text": "first entry", "author": "alice"}


def test_parses_top_level_object_into_single_fragment(tmp_path):
    p = tmp_path / "obj.json"
    p.write_text('{"a": 1, "b": "two"}', encoding="utf-8")
    frags = JsonParser().parse(p)
    assert len(frags) == 1
    assert frags[0].raw_index == 0
    assert frags[0].raw_payload == {"a": 1, "b": "two"}


def test_string_array_items_use_the_string_as_text(tmp_path):
    p = tmp_path / "strs.json"
    p.write_text('["hello", "world"]', encoding="utf-8")
    frags = JsonParser().parse(p)
    assert [f.extracted_text for f in frags] == ["hello", "world"]
    assert frags[0].raw_payload == {"value": "hello"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_json_parser.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement**

`kernel/ingestion/json_parser.py`:
```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kernel.ingestion.base import ParsedFragment


class JsonParser:
    def parse(self, path: Path) -> list[ParsedFragment]:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else [data]
        return [self._fragment(i, item) for i, item in enumerate(items)]

    @staticmethod
    def _fragment(index: int, item: Any) -> ParsedFragment:
        if isinstance(item, str):
            text = item
            payload: dict[str, Any] = {"value": item}
        elif isinstance(item, dict):
            text = json.dumps(item, ensure_ascii=False, sort_keys=True)
            payload = item
        else:
            text = json.dumps(item, ensure_ascii=False)
            payload = {"value": item}
        return ParsedFragment(raw_index=index, extracted_text=text, raw_payload=payload)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_json_parser.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Lint, type check, commit**

```bash
.venv/bin/ruff check kernel tests && .venv/bin/mypy kernel
git add kernel/ingestion/json_parser.py tests/kernel/ingestion/fixtures/sample.json tests/kernel/ingestion/test_json_parser.py
git commit -m "feat: json source parser"
```

---

### Task 3: Markdown parser

**Files:**
- Create: `kernel/ingestion/markdown_parser.py`
- Create: `tests/kernel/ingestion/fixtures/sample.md`
- Create: `tests/kernel/ingestion/test_markdown_parser.py`

**Interfaces:**
- Produces: `MarkdownParser.parse(path) -> list[ParsedFragment]`. Uses `mistune` 3.x to tokenize, then emits one fragment per top-level **heading**, **paragraph**, and **block_code** token (in document order). `extracted_text` is the token's plain text. Empty blocks are skipped. `raw_index` is the sequential index among emitted fragments.

- [ ] **Step 1: Write the fixture**

`tests/kernel/ingestion/fixtures/sample.md`:
```markdown
# Title

First paragraph with some text.

Second paragraph here.
```

- [ ] **Step 2: Write the failing test**

`tests/kernel/ingestion/test_markdown_parser.py`:
```python
from pathlib import Path

from kernel.ingestion.markdown_parser import MarkdownParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_emits_a_fragment_per_block():
    frags = MarkdownParser().parse(FIXTURES / "sample.md")
    texts = [f.extracted_text for f in frags]
    assert "Title" in texts
    assert "First paragraph with some text." in texts
    assert "Second paragraph here." in texts
    assert [f.raw_index for f in frags] == list(range(len(frags)))


def test_skips_empty_blocks(tmp_path):
    p = tmp_path / "spaced.md"
    p.write_text("para one\n\n\n\npara two\n", encoding="utf-8")
    frags = MarkdownParser().parse(p)
    assert [f.extracted_text for f in frags] == ["para one", "para two"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_markdown_parser.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement**

`kernel/ingestion/markdown_parser.py`:
```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import mistune

from kernel.ingestion.base import ParsedFragment

_BLOCK_TYPES = {"heading", "paragraph", "block_code"}


def _token_text(token: dict[str, Any]) -> str:
    """Recursively collect plain text from a mistune 3.x token."""
    if "raw" in token:
        return str(token["raw"])
    children = token.get("children")
    if isinstance(children, list):
        return "".join(_token_text(child) for child in children)
    return ""


class MarkdownParser:
    def parse(self, path: Path) -> list[ParsedFragment]:
        text = path.read_text(encoding="utf-8")
        # renderer=None yields the token list (mistune 3.x).
        md = mistune.create_markdown(renderer=None)
        tokens = md(text)
        fragments: list[ParsedFragment] = []
        for token in tokens:
            if token.get("type") not in _BLOCK_TYPES:
                continue
            content = _token_text(token).strip()
            if not content:
                continue
            fragments.append(
                ParsedFragment(
                    raw_index=len(fragments),
                    extracted_text=content,
                    metadata={"block_type": token.get("type")},
                )
            )
        return fragments
```

> Implementer note: confirm `mistune.create_markdown(renderer=None)` returns a list of token dicts on the installed 3.x version (it does as of 3.0). If the token shape differs, adjust `_token_text`/`_BLOCK_TYPES` accordingly — the tests pin the expected behavior.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_markdown_parser.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Lint, type check, commit**

```bash
.venv/bin/ruff check kernel tests && .venv/bin/mypy kernel
git add kernel/ingestion/markdown_parser.py tests/kernel/ingestion/fixtures/sample.md tests/kernel/ingestion/test_markdown_parser.py
git commit -m "feat: markdown source parser"
```

---

### Task 4: HTML parser

**Files:**
- Create: `kernel/ingestion/html_parser.py`
- Create: `tests/kernel/ingestion/fixtures/sample.html`
- Create: `tests/kernel/ingestion/test_html_parser.py`

**Interfaces:**
- Produces: `HtmlParser.parse(path) -> list[ParsedFragment]`. Uses BeautifulSoup with the stdlib `html.parser` backend (no lxml). Emits one fragment per block-level element in `{p, h1, h2, h3, h4, h5, h6, li, blockquote}` whose stripped text is non-empty, in document order. `script`/`style` text is excluded.

- [ ] **Step 1: Write the fixture**

`tests/kernel/ingestion/fixtures/sample.html`:
```html
<!doctype html>
<html><head><style>.x{color:red}</style></head>
<body>
  <h1>Heading One</h1>
  <p>A paragraph of text.</p>
  <ul><li>Item A</li><li>Item B</li></ul>
  <script>console.log("ignore me")</script>
</body></html>
```

- [ ] **Step 2: Write the failing test**

`tests/kernel/ingestion/test_html_parser.py`:
```python
from pathlib import Path

from kernel.ingestion.html_parser import HtmlParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_block_text_in_order():
    frags = HtmlParser().parse(FIXTURES / "sample.html")
    texts = [f.extracted_text for f in frags]
    assert texts == ["Heading One", "A paragraph of text.", "Item A", "Item B"]
    assert [f.raw_index for f in frags] == [0, 1, 2, 3]


def test_excludes_script_and_style(tmp_path):
    p = tmp_path / "s.html"
    p.write_text(
        "<body><style>a{}</style><p>keep</p><script>x()</script></body>",
        encoding="utf-8",
    )
    frags = HtmlParser().parse(p)
    assert [f.extracted_text for f in frags] == ["keep"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_html_parser.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement**

`kernel/ingestion/html_parser.py`:
```python
from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from kernel.ingestion.base import ParsedFragment

_BLOCK_TAGS = ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"]


class HtmlParser:
    def parse(self, path: Path) -> list[ParsedFragment]:
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        fragments: list[ParsedFragment] = []
        for element in soup.find_all(_BLOCK_TAGS):
            content = element.get_text(separator=" ", strip=True)
            if not content:
                continue
            fragments.append(
                ParsedFragment(
                    raw_index=len(fragments),
                    extracted_text=content,
                    metadata={"tag": element.name},
                )
            )
        return fragments
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_html_parser.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Lint, type check, commit**

```bash
.venv/bin/ruff check kernel tests && .venv/bin/mypy kernel
git add kernel/ingestion/html_parser.py tests/kernel/ingestion/fixtures/sample.html tests/kernel/ingestion/test_html_parser.py
git commit -m "feat: html source parser"
```

---

### Task 5: PDF parser

**Files:**
- Create: `kernel/ingestion/pdf_parser.py`
- Create: `tests/kernel/ingestion/test_pdf_parser.py` (generates a PDF in a tmp dir via `fpdf2`)

**Interfaces:**
- Produces: `PdfParser.parse(path) -> list[ParsedFragment]`. Uses `pdfplumber`; emits one fragment per page whose extracted text is non-empty. `raw_index` = page number (0-based among non-empty pages); `metadata={"page": <1-based page number>}`.

- [ ] **Step 1: Write the failing test (generates its own fixture)**

`tests/kernel/ingestion/test_pdf_parser.py`:
```python
from pathlib import Path

from fpdf import FPDF

from kernel.ingestion.pdf_parser import PdfParser


def _make_pdf(path: Path, pages: list[str]) -> None:
    pdf = FPDF()
    pdf.set_font("helvetica", size=12)
    for text in pages:
        pdf.add_page()
        pdf.multi_cell(0, 10, text)
    pdf.output(str(path))


def test_emits_one_fragment_per_nonempty_page(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, ["Page one content.", "Page two content."])
    frags = PdfParser().parse(pdf_path)
    assert len(frags) == 2
    assert "Page one content." in frags[0].extracted_text
    assert "Page two content." in frags[1].extracted_text
    assert frags[0].metadata == {"page": 1}
    assert frags[1].metadata == {"page": 2}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_pdf_parser.py -v`
Expected: FAIL — `ModuleNotFoundError` for `kernel.ingestion.pdf_parser`

- [ ] **Step 3: Implement**

`kernel/ingestion/pdf_parser.py`:
```python
from __future__ import annotations

from pathlib import Path

import pdfplumber

from kernel.ingestion.base import ParsedFragment


class PdfParser:
    def parse(self, path: Path) -> list[ParsedFragment]:
        fragments: list[ParsedFragment] = []
        with pdfplumber.open(str(path)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                text = (page.extract_text() or "").strip()
                if not text:
                    continue
                fragments.append(
                    ParsedFragment(
                        raw_index=len(fragments),
                        extracted_text=text,
                        metadata={"page": page_number},
                    )
                )
        return fragments
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_pdf_parser.py -v`
Expected: PASS

- [ ] **Step 5: Lint, type check, commit**

```bash
.venv/bin/ruff check kernel tests && .venv/bin/mypy kernel
git add kernel/ingestion/pdf_parser.py tests/kernel/ingestion/test_pdf_parser.py
git commit -m "feat: pdf source parser"
```

---

### Task 6: ChatGPT export parser

**Files:**
- Create: `kernel/ingestion/chatgpt_parser.py`
- Create: `tests/kernel/ingestion/fixtures/conversations.json`
- Create: `tests/kernel/ingestion/test_chatgpt_parser.py`

**Interfaces:**
- Produces: `ChatGptParser.parse(path) -> list[ParsedFragment]`. Parses the ChatGPT `conversations.json` shape: a list of conversations, each with a `mapping` dict of nodes; each node may hold a `message` with `author.role`, `content.parts` (list), and `create_time` (epoch seconds, may be null). Emit one fragment per message that has non-empty joined `parts`, ordered by `create_time` (nulls last, stable). `author` = role; `timestamp` = UTC datetime from `create_time` (or None); `raw_payload` = the message node.

- [ ] **Step 1: Write the fixture**

`tests/kernel/ingestion/fixtures/conversations.json`:
```json
[
  {
    "title": "demo",
    "mapping": {
      "n1": {"message": {"author": {"role": "user"}, "content": {"parts": ["hello there"]}, "create_time": 1700000000}},
      "n2": {"message": {"author": {"role": "assistant"}, "content": {"parts": ["hi, how can I help?"]}, "create_time": 1700000060}},
      "n3": {"message": {"author": {"role": "system"}, "content": {"parts": [""]}, "create_time": 1700000030}}
    }
  }
]
```

- [ ] **Step 2: Write the failing test**

`tests/kernel/ingestion/test_chatgpt_parser.py`:
```python
from datetime import UTC, datetime
from pathlib import Path

from kernel.ingestion.chatgpt_parser import ChatGptParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_messages_in_time_order_skipping_empty():
    frags = ChatGptParser().parse(FIXTURES / "conversations.json")
    # n3 has empty parts -> skipped; remaining ordered by create_time
    assert [f.extracted_text for f in frags] == ["hello there", "hi, how can I help?"]
    assert [f.author for f in frags] == ["user", "assistant"]
    assert frags[0].timestamp == datetime.fromtimestamp(1700000000, tz=UTC)
    assert [f.raw_index for f in frags] == [0, 1]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_chatgpt_parser.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement**

`kernel/ingestion/chatgpt_parser.py`:
```python
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kernel.ingestion.base import ParsedFragment


class ChatGptParser:
    def parse(self, path: Path) -> list[ParsedFragment]:
        conversations = json.loads(path.read_text(encoding="utf-8"))
        messages: list[dict[str, Any]] = []
        for conversation in conversations:
            mapping = conversation.get("mapping", {})
            for node in mapping.values():
                message = node.get("message")
                if message:
                    messages.append(message)

        # Stable sort by create_time, nulls last.
        messages.sort(key=lambda m: (m.get("create_time") is None, m.get("create_time") or 0))

        fragments: list[ParsedFragment] = []
        for message in messages:
            parts = message.get("content", {}).get("parts", []) or []
            text = "\n".join(str(p) for p in parts).strip()
            if not text:
                continue
            create_time = message.get("create_time")
            timestamp = (
                datetime.fromtimestamp(create_time, tz=UTC)
                if isinstance(create_time, (int, float))
                else None
            )
            fragments.append(
                ParsedFragment(
                    raw_index=len(fragments),
                    extracted_text=text,
                    author=message.get("author", {}).get("role"),
                    timestamp=timestamp,
                    raw_payload=message,
                )
            )
        return fragments
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_chatgpt_parser.py -v`
Expected: PASS

- [ ] **Step 6: Lint, type check, commit**

```bash
.venv/bin/ruff check kernel tests && .venv/bin/mypy kernel
git add kernel/ingestion/chatgpt_parser.py tests/kernel/ingestion/fixtures/conversations.json tests/kernel/ingestion/test_chatgpt_parser.py
git commit -m "feat: chatgpt export parser"
```

---

### Task 7: Meta export parser

**Files:**
- Create: `kernel/ingestion/meta_parser.py`
- Create: `tests/kernel/ingestion/fixtures/meta_messages.json`
- Create: `tests/kernel/ingestion/test_meta_parser.py`

**Interfaces:**
- Produces: `MetaParser.parse(path) -> list[ParsedFragment]`. Parses the Meta (Messenger/Instagram) export shape: an object with a `messages` list, each item having `sender_name`, `timestamp_ms` (epoch ms), and `content` (string, optional). Emit one fragment per message with non-empty `content`, ordered by `timestamp_ms` ascending. `author` = `sender_name`; `timestamp` = UTC datetime from `timestamp_ms`; `raw_payload` = the message object.

- [ ] **Step 1: Write the fixture**

`tests/kernel/ingestion/fixtures/meta_messages.json`:
```json
{
  "participants": [{"name": "Alice"}, {"name": "Bob"}],
  "messages": [
    {"sender_name": "Bob", "timestamp_ms": 1700000060000, "content": "second"},
    {"sender_name": "Alice", "timestamp_ms": 1700000000000, "content": "first"},
    {"sender_name": "Alice", "timestamp_ms": 1700000120000, "photos": [{"uri": "x.jpg"}]}
  ]
}
```

- [ ] **Step 2: Write the failing test**

`tests/kernel/ingestion/test_meta_parser.py`:
```python
from datetime import UTC, datetime
from pathlib import Path

from kernel.ingestion.meta_parser import MetaParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_text_messages_in_time_order():
    frags = MetaParser().parse(FIXTURES / "meta_messages.json")
    # third message has no content -> skipped; sorted ascending by timestamp_ms
    assert [f.extracted_text for f in frags] == ["first", "second"]
    assert [f.author for f in frags] == ["Alice", "Bob"]
    assert frags[0].timestamp == datetime.fromtimestamp(1700000000, tz=UTC)
    assert [f.raw_index for f in frags] == [0, 1]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_meta_parser.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement**

`kernel/ingestion/meta_parser.py`:
```python
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from kernel.ingestion.base import ParsedFragment


class MetaParser:
    def parse(self, path: Path) -> list[ParsedFragment]:
        data = json.loads(path.read_text(encoding="utf-8"))
        messages = sorted(
            data.get("messages", []), key=lambda m: m.get("timestamp_ms", 0)
        )
        fragments: list[ParsedFragment] = []
        for message in messages:
            content = (message.get("content") or "").strip()
            if not content:
                continue
            timestamp_ms = message.get("timestamp_ms")
            timestamp = (
                datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
                if isinstance(timestamp_ms, (int, float))
                else None
            )
            fragments.append(
                ParsedFragment(
                    raw_index=len(fragments),
                    extracted_text=content,
                    author=message.get("sender_name"),
                    timestamp=timestamp,
                    raw_payload=message,
                )
            )
        return fragments
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_meta_parser.py -v`
Expected: PASS

- [ ] **Step 6: Lint, type check, commit**

```bash
.venv/bin/ruff check kernel tests && .venv/bin/mypy kernel
git add kernel/ingestion/meta_parser.py tests/kernel/ingestion/fixtures/meta_messages.json tests/kernel/ingestion/test_meta_parser.py
git commit -m "feat: meta export parser"
```

---

### Task 8: Normalizer

**Files:**
- Create: `kernel/ingestion/normalizer.py`
- Create: `tests/kernel/ingestion/test_normalizer.py`

**Interfaces:**
- Consumes: `ParsedFragment`.
- Produces: `Normalizer.normalize(fragments: list[ParsedFragment]) -> list[dict[str, Any]]`. Each output dict (observation row) has: `content` (= fragment.extracted_text), `observed_at` (= fragment.timestamp), `speaker` (= fragment.author), `context_before` (previous fragment's text or None), `context_after` (next fragment's text or None), `confidence` (= 1.0). Fragments with empty/whitespace `extracted_text` are skipped, and the context window is computed over the **kept** fragments.

- [ ] **Step 1: Write the failing test**

`tests/kernel/ingestion/test_normalizer.py`:
```python
from datetime import UTC, datetime

from kernel.ingestion.base import ParsedFragment
from kernel.ingestion.normalizer import Normalizer


def _frag(i, text, author=None, ts=None):
    return ParsedFragment(raw_index=i, extracted_text=text, author=author, timestamp=ts)


def test_normalize_sets_context_window_and_defaults():
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    frags = [_frag(0, "one", "a", ts), _frag(1, "two", "b"), _frag(2, "three")]
    rows = Normalizer().normalize(frags)
    assert [r["content"] for r in rows] == ["one", "two", "three"]
    assert rows[0]["context_before"] is None
    assert rows[0]["context_after"] == "two"
    assert rows[1]["context_before"] == "one"
    assert rows[1]["context_after"] == "three"
    assert rows[2]["context_after"] is None
    assert rows[0]["speaker"] == "a"
    assert rows[0]["observed_at"] == ts
    assert all(r["confidence"] == 1.0 for r in rows)


def test_normalize_skips_empty_and_recomputes_window():
    frags = [_frag(0, "keep1"), _frag(1, "   "), _frag(2, "keep2")]
    rows = Normalizer().normalize(frags)
    assert [r["content"] for r in rows] == ["keep1", "keep2"]
    # window computed over kept fragments only
    assert rows[0]["context_after"] == "keep2"
    assert rows[1]["context_before"] == "keep1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_normalizer.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`kernel/ingestion/normalizer.py`:
```python
from __future__ import annotations

from typing import Any

from kernel.ingestion.base import ParsedFragment

_DEFAULT_CONFIDENCE = 1.0


class Normalizer:
    def normalize(self, fragments: list[ParsedFragment]) -> list[dict[str, Any]]:
        kept = [f for f in fragments if f.extracted_text and f.extracted_text.strip()]
        rows: list[dict[str, Any]] = []
        for i, frag in enumerate(kept):
            rows.append(
                {
                    "content": frag.extracted_text,
                    "observed_at": frag.timestamp,
                    "speaker": frag.author,
                    "context_before": kept[i - 1].extracted_text if i > 0 else None,
                    "context_after": (
                        kept[i + 1].extracted_text if i + 1 < len(kept) else None
                    ),
                    "confidence": _DEFAULT_CONFIDENCE,
                }
            )
        return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_normalizer.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Lint, type check, commit**

```bash
.venv/bin/ruff check kernel tests && .venv/bin/mypy kernel
git add kernel/ingestion/normalizer.py tests/kernel/ingestion/test_normalizer.py
git commit -m "feat: fragment-to-observation normalizer"
```

---

### Task 9: Parser registry + end-to-end ingestion test

**Files:**
- Create: `kernel/ingestion/registry.py`
- Create: `tests/kernel/ingestion/test_registry.py`

**Interfaces:**
- Consumes: all parsers + `SourceType`.
- Produces: `get_parser(source_type: str) -> Parser`. Maps each `SourceType` constant to its parser instance; raises `ValueError` (with the offending value) for unknown types. Every `SourceType.ALL` entry must be routable.

- [ ] **Step 1: Write the failing test**

`tests/kernel/ingestion/test_registry.py`:
```python
from pathlib import Path

import pytest

from kernel.ingestion.base import ParsedFragment, Parser, SourceType
from kernel.ingestion.normalizer import Normalizer
from kernel.ingestion.registry import get_parser

FIXTURES = Path(__file__).parent / "fixtures"


def test_every_source_type_routes_to_a_parser():
    for source_type in SourceType.ALL:
        parser = get_parser(source_type)
        assert isinstance(parser, Parser)


def test_unknown_source_type_raises_valueerror():
    with pytest.raises(ValueError, match="bogus"):
        get_parser("bogus")


def test_end_to_end_parse_then_normalize_json():
    parser = get_parser(SourceType.JSON)
    fragments = parser.parse(FIXTURES / "sample.json")
    rows = Normalizer().normalize(fragments)
    assert len(rows) == 2
    assert all("content" in r and r["confidence"] == 1.0 for r in rows)
    assert rows[0]["context_after"] == fragments[1].extracted_text


def test_end_to_end_chatgpt_fragments_have_authors_and_timestamps():
    parser = get_parser(SourceType.CHATGPT)
    fragments = parser.parse(FIXTURES / "conversations.json")
    rows = Normalizer().normalize(fragments)
    assert [r["speaker"] for r in rows] == ["user", "assistant"]
    assert rows[0]["observed_at"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError` for `kernel.ingestion.registry`

- [ ] **Step 3: Implement**

`kernel/ingestion/registry.py`:
```python
from __future__ import annotations

from kernel.ingestion.base import Parser, SourceType
from kernel.ingestion.chatgpt_parser import ChatGptParser
from kernel.ingestion.html_parser import HtmlParser
from kernel.ingestion.json_parser import JsonParser
from kernel.ingestion.markdown_parser import MarkdownParser
from kernel.ingestion.meta_parser import MetaParser
from kernel.ingestion.pdf_parser import PdfParser

_PARSERS: dict[str, Parser] = {
    SourceType.JSON: JsonParser(),
    SourceType.MARKDOWN: MarkdownParser(),
    SourceType.HTML: HtmlParser(),
    SourceType.PDF: PdfParser(),
    SourceType.CHATGPT: ChatGptParser(),
    SourceType.META: MetaParser(),
}


def get_parser(source_type: str) -> Parser:
    try:
        return _PARSERS[source_type]
    except KeyError:
        raise ValueError(f"unknown source_type: {source_type!r}") from None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/kernel/ingestion/test_registry.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Full suite, lint, types, coverage**

Run:
```bash
.venv/bin/ruff check kernel tests && .venv/bin/mypy kernel
.venv/bin/pytest -q
```
Expected: all PASS; `kernel/ingestion` coverage ≥ 80%.

- [ ] **Step 6: Commit**

```bash
git add kernel/ingestion/registry.py tests/kernel/ingestion/test_registry.py
git commit -m "feat: parser registry and end-to-end ingestion test"
```

---

## Self-Review

**Spec coverage (Phase 0 spec §6 ingestion):**
- Parser protocol + `parse(path) -> fragments` → Task 1 ✓
- Six parsers (json, pdf, html, markdown, chatgpt, meta) → Tasks 2–7 ✓
- Normalizer (Fragment → Observation, content/observed_at/speaker/context window/confidence=1.0) → Task 8 ✓
- `get_parser` routing by source_type → Task 9 ✓
- Source-type constants centralized → Task 1 ✓

**Deliberate deviations from the spec, with rationale:**
- The spec sketched a `Fragment` dataclass in `ingestion/base.py`; Plan 1 already defined a persisted `Fragment` model in `kernel/models.py`. To avoid confusion, the parser output type is named **`ParsedFragment`** (pre-persistence) and converts to repo rows via `to_fragment_row()`. The persisted `Fragment` is unchanged.
- Plan 2 is pure (no DB). Wiring parser → `FragmentRepository`/`ObservationRepository` is Plan 3 (worker), matching the spec's pipeline split.

**Out of scope (correctly deferred to Plan 3):** Dramatiq `ingest_source` task, mime-type validation, checksum/dedup, storage paths, status transitions — all live in the API/worker plan, not the pure ingestion kernel.

**Carry-over note for Plan 3:** `FragmentRepository.bulk_insert` currently ignores `raw_payload`/`metadata` columns. `ParsedFragment.to_fragment_row()` includes `raw_payload` (ignored today, forward-compatible). If provenance persistence is wanted, extend the repo + `_COLUMNS` in Plan 3.

**Placeholder scan:** none — every step has runnable code/fixtures and exact commands.

**Type consistency:** `ParsedFragment` (Task 1) is consumed identically by every parser and the normalizer; `get_parser` (Task 9) returns the `Parser` protocol all six parsers satisfy structurally; `Normalizer.normalize` output keys match `ObservationRepository.bulk_insert`'s expected keys from Plan 1.

**Parallelization note (for execution):** Tasks 2–7 are mutually independent once Task 1 lands (disjoint files), so they can be implemented concurrently; Task 8 is independent too; Task 9 depends on all parsers. Note that several tasks edit the shared `tests/kernel/ingestion/fixtures/` dir but each adds distinct fixture files (no collisions).
```
