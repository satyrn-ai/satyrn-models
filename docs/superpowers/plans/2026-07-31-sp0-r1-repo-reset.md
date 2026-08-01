# SP0 R1 — Repo Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire the three placeholder scripts, preserve their 24 hand-written examples as quarantined unverified-provenance seed material that cannot enter a corpus, and establish the package layout and test tooling every later rung depends on.

**Architecture:** A `src/`-layout package (`src/satyrn_model/`) replaces the three top-level scripts. The 24 examples move into `corpus/quarantine/legacy-examples-2025-unverified.jsonl` as `QuarantineRecord`s — a type deliberately *without* a hidden test, so it is structurally incapable of passing an oracle or being written as a corpus row. The placeholder scripts are deleted only after a test proves all 24 examples survived the move.

**Tech Stack:** Python 3.14+, uv, pytest, ruff, ty. Hatchling as build backend.

## Global Constraints

- **Python 3.14+ required.** t-strings do not parse on earlier interpreters. `requires-python = ">=3.14"`.
- **The 24 legacy examples are F-CONTAM source material.** Their descriptions are byte-identical to prompts in the retired `eval.py`. They may never silently enter a corpus or a benchmark. Quarantine only.
- **No training dependencies yet.** `unsloth` is dropped; the roadmap specifies mlx-lm directly, and no rung before SP2 R4 trains anything. Add training deps when a training rung needs them.
- **Every quarantine record carries `provenance: "unverified"`.** There is no code path that writes a `QuarantineRecord` to a corpus file.

**Already done — do not redo.** The roadmap's R1 also calls for establishing
`docs/superpowers/{specs,plans,research}/`. Those directories exist and hold
live documents. No task below touches them.

---

### Task 1: Package skeleton and test tooling

**Files:**
- Modify: `pyproject.toml`
- Create: `src/satyrn_model/__init__.py`
- Test: `tests/test_package.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the importable package `satyrn_model` with `__version__: str`. Every later task imports from `satyrn_model.*`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_package.py`:

```python
"""The package imports and reports a version. Guards the src-layout wiring:
without a correct [tool.hatch.build] setting, `import satyrn_model` fails in
an editable install even though the directory exists."""

import satyrn_model


def test_package_imports_and_has_version():
    assert isinstance(satyrn_model.__version__, str)
    assert satyrn_model.__version__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_package.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'satyrn_model'` (or a pytest collection error saying the same).

- [ ] **Step 3: Replace `pyproject.toml`**

Write `pyproject.toml` in full:

```toml
[project]
name = "satyrn-model"
version = "0.1.0"
description = "Training-data pipeline for teaching PEP 750 t-strings to a code model"
readme = "README.md"
requires-python = ">=3.14"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/satyrn_model"]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "ruff>=0.8",
    "ty",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
# Puts the repo root on sys.path so `tests/` can import `scripts.*` (Task 3).
# Without it, pytest's prepend import mode adds only `tests/`, and importing
# the migration script fails with ModuleNotFoundError.
pythonpath = ["."]

[tool.ruff]
target-version = "py314"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 4: Create the package module**

Create `src/satyrn_model/__init__.py`:

```python
"""Training-data pipeline for teaching PEP 750 t-strings to a code model."""

__version__ = "0.1.0"
```

- [ ] **Step 5: Sync and run the test to verify it passes**

Run: `uv sync && uv run pytest tests/test_package.py -v`

Expected: PASS, 1 test.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/satyrn_model/__init__.py tests/test_package.py
git commit -m "SP0 R1: establish src layout and test tooling

Drops the unsloth dependency: the roadmap specifies mlx-lm directly and no
rung before SP2 R4 trains anything."
```

---

### Task 2: The `QuarantineRecord` type

**Files:**
- Create: `src/satyrn_model/quarantine.py`
- Test: `tests/test_quarantine.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `QuarantineRecord` — frozen dataclass with fields `id: str`, `description: str`, `code: str`, `reason: str`, and `provenance: str` (always the literal `"unverified"`).
  - `write_jsonl(path: Path, records: list[QuarantineRecord]) -> None`
  - `read_jsonl(path: Path) -> list[QuarantineRecord]`

  Task 3 uses all three. The type deliberately has **no** `hidden_test` field, so it cannot be verified by an oracle or emitted as a corpus row.

- [ ] **Step 1: Write the failing test**

Create `tests/test_quarantine.py`:

```python
"""QuarantineRecord holds retired, unverified-provenance examples. It exists
to make them inert: no hidden test means no oracle can pass one, so it cannot
become a corpus row by any code path."""

import dataclasses

import pytest

from satyrn_model.quarantine import QuarantineRecord, read_jsonl, write_jsonl


def make_record(id: str = "example-one") -> QuarantineRecord:
    return QuarantineRecord(
        id=id,
        description="create a template string and check its type",
        code='name = "World"\ntemplate = t"Hello {name}"\n',
        reason="legacy hand-written example, F-CONTAM source",
    )


def test_provenance_defaults_to_unverified():
    assert make_record().provenance == "unverified"


def test_record_is_frozen():
    record = make_record()
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.code = "mutated"


def test_record_has_no_hidden_test_field():
    """The structural guarantee: a record with no hidden test cannot be
    verified, so it cannot enter a corpus even by mistake."""
    field_names = {f.name for f in dataclasses.fields(QuarantineRecord)}
    assert "hidden_test" not in field_names


def test_jsonl_round_trip(tmp_path):
    records = [make_record("example-one"), make_record("example-two")]
    path = tmp_path / "quarantine.jsonl"

    write_jsonl(path, records)

    assert read_jsonl(path) == records


def test_read_jsonl_skips_blank_lines(tmp_path):
    path = tmp_path / "quarantine.jsonl"
    write_jsonl(path, [make_record()])
    path.write_text(path.read_text() + "\n\n")

    assert len(read_jsonl(path)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_quarantine.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'satyrn_model.quarantine'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/satyrn_model/quarantine.py`:

```python
"""Retired examples of unverified provenance.

The 24 hand-written examples from the placeholder `make_data.py` are the
F-CONTAM source: their descriptions were byte-identical to prompts in the
retired `eval.py`, so any pass rate measured against them was a memorization
score. They are preserved here as *seed material only*.

`QuarantineRecord` deliberately carries no hidden test. An example without a
hidden test cannot be verified by the oracle, and therefore cannot become a
corpus row through any code path -- the bad state is unrepresentable rather
than merely forbidden by convention.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class QuarantineRecord:
    id: str
    description: str
    code: str
    reason: str
    provenance: str = "unverified"


def write_jsonl(path: Path, records: list[QuarantineRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for record in records:
            fh.write(json.dumps(dataclasses.asdict(record)) + "\n")


def read_jsonl(path: Path) -> list[QuarantineRecord]:
    records = []
    with path.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            records.append(QuarantineRecord(**json.loads(line)))
    return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_quarantine.py -v`

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add src/satyrn_model/quarantine.py tests/test_quarantine.py
git commit -m "SP0 R1: add QuarantineRecord for retired unverified examples

No hidden_test field, so a quarantined example cannot be verified and cannot
become a corpus row by any path."
```

---

### Task 3: Migrate the 24 legacy examples into quarantine

**Files:**
- Create: `scripts/quarantine_legacy_examples.py`
- Create: `corpus/quarantine/legacy-examples-2025-unverified.jsonl` *(generated by running the script)*
- Test: `tests/test_quarantine_migration.py`

**Interfaces:**
- Consumes: `QuarantineRecord`, `write_jsonl` from Task 2.
- Produces:
  - `parse_legacy_line(line: str) -> QuarantineRecord` — splits one `data/pep750.jsonl` row into description and code.
  - `slugify(description: str) -> str` — lowercase, non-alphanumerics collapsed to single hyphens, no leading/trailing hyphen.

**Input format.** Each line of `data/pep750.jsonl` is `{"text": "..."}` where the text is a header line followed by the code:

```
# Python 3.14 t-strings: create a template string and check its type
name = "World"
template = t"Hello {name}"
```

The description is everything after the literal prefix `# Python 3.14 t-strings: ` on the first line. The code is every remaining line.

- [ ] **Step 1: Write the failing test**

Create `tests/test_quarantine_migration.py`:

```python
"""Parsing the retired data/pep750.jsonl format into quarantine records."""

import pytest

from scripts.quarantine_legacy_examples import parse_legacy_line, slugify

LINE = (
    '{"text": "# Python 3.14 t-strings: access the static string parts\\n'
    'name = \\"World\\"\\ntemplate = t\\"Hello {name}!\\""}'
)


def test_parse_extracts_description():
    record = parse_legacy_line(LINE)
    assert record.description == "access the static string parts"


def test_parse_extracts_code_without_header():
    record = parse_legacy_line(LINE)
    assert record.code == 'name = "World"\ntemplate = t"Hello {name}!"'
    assert "# Python 3.14 t-strings" not in record.code


def test_parse_sets_id_from_description():
    assert parse_legacy_line(LINE).id == "access-the-static-string-parts"


def test_parse_marks_provenance_and_reason():
    record = parse_legacy_line(LINE)
    assert record.provenance == "unverified"
    assert "F-CONTAM" in record.reason


def test_parse_rejects_unexpected_header():
    bad = '{"text": "# Some other header\\nx = 1"}'
    with pytest.raises(ValueError, match="unexpected header"):
        parse_legacy_line(bad)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("use a !r conversion", "use-a-r-conversion"),
        ("read the  evaluated value", "read-the-evaluated-value"),
        ("Trailing punctuation!", "trailing-punctuation"),
    ],
)
def test_slugify(description, expected):
    assert slugify(description) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_quarantine_migration.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts'`.

- [ ] **Step 3: Write the migration script**

Create `scripts/__init__.py`, so `scripts` is an importable package for the test:

```python
"""One-shot maintenance scripts. Not part of the shipped package."""
```

Create `scripts/quarantine_legacy_examples.py`:

```python
"""One-shot migration: data/pep750.jsonl -> corpus/quarantine/.

The retired `make_data.py` emitted one JSON object per line of the form
`{"text": "<header>: <description>\\n<code>"}`. This script splits that back
into a description and a code body and writes QuarantineRecords.

Run once, from the repo root:

    uv run python -m scripts.quarantine_legacy_examples
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from satyrn_model.quarantine import QuarantineRecord, write_jsonl

HEADER_PREFIX = "# Python 3.14 t-strings: "

REASON = (
    "Legacy hand-written example from the retired make_data.py. F-CONTAM "
    "source: these descriptions were byte-identical to prompts in the retired "
    "eval.py, so any pass rate measured against them was a memorization score. "
    "Seed material only -- never a corpus row, never a benchmark task."
)

SOURCE = Path("data/pep750.jsonl")
DESTINATION = Path("corpus/quarantine/legacy-examples-2025-unverified.jsonl")


def slugify(description: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", description.lower()).strip("-")


def parse_legacy_line(line: str) -> QuarantineRecord:
    text = json.loads(line)["text"]
    header, _, code = text.partition("\n")
    if not header.startswith(HEADER_PREFIX):
        raise ValueError(f"unexpected header: {header!r}")
    description = header.removeprefix(HEADER_PREFIX)
    return QuarantineRecord(
        id=slugify(description),
        description=description,
        code=code,
        reason=REASON,
    )


def main() -> int:
    records = [
        parse_legacy_line(line)
        for line in SOURCE.read_text().splitlines()
        if line.strip()
    ]

    ids = [record.id for record in records]
    duplicates = {id for id in ids if ids.count(id) > 1}
    if duplicates:
        raise ValueError(f"duplicate quarantine ids: {sorted(duplicates)}")

    write_jsonl(DESTINATION, records)
    print(f"Quarantined {len(records)} records to {DESTINATION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_quarantine_migration.py -v`

Expected: PASS, 8 tests (5 named plus 3 parametrized slugify cases).

- [ ] **Step 5: Run the migration**

Run: `uv run python -m scripts.quarantine_legacy_examples`

Expected output: `Quarantined 24 records to corpus/quarantine/legacy-examples-2025-unverified.jsonl`

If it raises `duplicate quarantine ids`, two descriptions slugify identically. Disambiguate by appending `-2` to the later one in a `SLUG_OVERRIDES: dict[str, str]` mapping description to slug, consulted at the top of `slugify`. Do not silently deduplicate — every one of the 24 must survive.

- [ ] **Step 6: Commit**

```bash
git add scripts/__init__.py scripts/quarantine_legacy_examples.py \
        tests/test_quarantine_migration.py \
        corpus/quarantine/legacy-examples-2025-unverified.jsonl
git commit -m "SP0 R1: quarantine the 24 legacy examples as seed material"
```

---

### Task 4: Retire the placeholder scripts

**Files:**
- Delete: `main.py`, `make_data.py`, `eval.py`, `data/pep750.jsonl`
- Modify: `README.md`
- Test: `tests/test_quarantine_complete.py`

**Interfaces:**
- Consumes: `read_jsonl` from Task 2; the quarantine file from Task 3.
- Produces: nothing later tasks depend on.

The test runs **before** the deletion and is what makes the deletion safe: it proves all 24 examples survived the move.

- [ ] **Step 1: Write the completeness test**

Create `tests/test_quarantine_complete.py`:

```python
"""Proves the quarantine file is complete before the placeholder scripts are
deleted. Deleting the source of the only copy of 24 hand-written examples
without this check would be unrecoverable."""

from pathlib import Path

from satyrn_model.quarantine import read_jsonl

QUARANTINE = Path("corpus/quarantine/legacy-examples-2025-unverified.jsonl")


def test_all_24_examples_are_quarantined():
    assert len(read_jsonl(QUARANTINE)) == 24


def test_every_record_has_unique_id():
    records = read_jsonl(QUARANTINE)
    ids = [record.id for record in records]
    assert len(set(ids)) == len(ids)


def test_every_record_has_content_and_unverified_provenance():
    for record in read_jsonl(QUARANTINE):
        assert record.description.strip(), f"{record.id}: empty description"
        assert record.code.strip(), f"{record.id}: empty code"
        assert record.provenance == "unverified", f"{record.id}: wrong provenance"


def test_no_record_carries_the_contaminating_header():
    """The `# Python 3.14 t-strings:` prefix is B-HEADER, a trigger phrase no
    real user types. It must not survive into anything downstream."""
    for record in read_jsonl(QUARANTINE):
        assert "# Python 3.14 t-strings" not in record.code
```

- [ ] **Step 2: Run it to verify the quarantine is complete**

Run: `uv run pytest tests/test_quarantine_complete.py -v`

Expected: PASS, 4 tests. **If any fail, stop — do not delete anything.** Fix Task 3 first.

- [ ] **Step 3: Delete the placeholder scripts and their output**

```bash
git rm main.py make_data.py eval.py data/pep750.jsonl
```

Expected: four files staged for deletion. `data/` is now empty and git will drop it automatically.

- [ ] **Step 4: Trim `README.md` to match the retirement**

`README.md` already carries a **"Current work: building a corpus that can
actually teach t-strings"** section describing what this project is, why it is
needed, and how it will work. **Keep that section verbatim** — it is the
document's substance. This step removes only what the deletion invalidates.

Delete these parts of `README.md`:

1. The opening two lines describing the repo as "Fine-tune Qwen2.5-Coder-7B ...
   using MLX LoRA on Apple Silicon" — the repo is a data pipeline, and no
   training rung lands before SP2 R4.
2. The `> The scripts documented further down are **placeholders awaiting
   retirement** by SP0 R1 ...` blockquote — no longer true once they are gone.
3. Everything from `## Pipeline` to the end of the file — the `make_data.py`,
   `main.py`, and `eval.py` documentation, including both flag tables.

Then set the opening to:

```markdown
# satyrn-model

Training-data pipeline for teaching a code model Python 3.14's PEP 750
template strings (t-strings).
```

And append these two sections to the end of the file:

```markdown
## Layout

- `src/satyrn_model/` — the package
- `corpus/quarantine/` — retired examples of unverified provenance. Seed
  material only; never corpus rows, never benchmark tasks.
- `docs/superpowers/{specs,plans,research}/` — design record
- `tests/` — pytest suite

## Development

```bash
uv sync
uv run pytest
uv run ruff check
uv run ty check
```

Requires Python 3.14+: t-strings do not parse on earlier interpreters.
```

Verify no dangling references remain:

Run: `grep -n "make_data\|eval\.py\|main\.py\|MLX LoRA" README.md`

Expected: no output.

- [ ] **Step 5: Run the full suite and linters**

Run: `uv run pytest && uv run ruff check && uv run ty check`

Expected: all tests pass (18 total across four test files); ruff and ty report no errors.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "SP0 R1: retire placeholder scripts

main.py, make_data.py, eval.py and data/pep750.jsonl are gone. Their 24
examples survive in corpus/quarantine/, proven complete by
tests/test_quarantine_complete.py before the deletion.

Closes the F-CONTAM source: eval.py's prompts were byte-identical to
make_data.py's training descriptions, so its reported pass rates were
memorization scores."
```

---

## Definition of Done

- `uv run pytest` passes; `uv run ruff check` and `uv run ty check` are clean.
- `main.py`, `make_data.py`, `eval.py`, and `data/pep750.jsonl` no longer exist.
- `corpus/quarantine/legacy-examples-2025-unverified.jsonl` holds exactly 24
  records, each with a unique id, non-empty code, `provenance == "unverified"`,
  and no `# Python 3.14 t-strings:` header.
- `QuarantineRecord` has no `hidden_test` field, so no quarantined example can
  be verified or emitted as a corpus row.
- `import satyrn_model` works from a clean `uv sync`.

## Not in this rung

- **The corpus row schema** (`Example`, `Provenance`) is SP0 R2. `QuarantineRecord`
  is deliberately a separate, weaker type and must not be generalized into it.
- **The oracle** is SP0 R3.
- **Skills** (`harvest-corpus`, `verify-example`, `eval-run`) are SP0 R4, written
  against conventions R2 and R3 actually establish — not speculatively.
- **Deleting the benchmark-quarantine overlap check.** No benchmark exists on
  `main` yet; that check belongs to SP1 R1.
