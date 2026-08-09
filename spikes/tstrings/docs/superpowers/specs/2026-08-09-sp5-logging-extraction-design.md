# SP5 logging extraction: closing the last extracted-seed gap

Addresses `SP5_SCALE_BRIEF.md` Priority 2 ("Extraction is confined to two
domains"), scoped narrowly to what's actually still true of that claim
after the prior seed-sourcing branch landed.

## Why this is a small brainstorm, not a repeat of the last one

The prior branch (`docs/superpowers/specs/2026-08-09-sp5-seed-sourcing-design.md`)
added 24 seeds with `kind="extracted"` for regex, sql, and html — the exact
ask Priority 2 makes. Checked directly against the committed seed files
before starting this one:

| domain | extracted seeds | authored seeds |
| --- | --- | --- |
| text | 8 | 9 |
| data | 2 | 4 |
| html | 8 | 7 |
| sql | 8 | 7 |
| regex | 8 | 3 |
| **logging** | **0** | 4 |

Priority 2's complaint — *"Only 10 of 54 seeds supply extracted rows, and
they cover only data and text... Extracted seeds in sql, html and logging
would be worth more than authored ones"* — is now false for sql, html, and
regex. **Logging is the only domain left at zero extracted seeds**, a
direct consequence of the prior branch's decision to skip logging
entirely (real usage was too thin to justify the ~30-seed authoring push).
This brainstorm is scoped to exactly that gap, not a re-litigation of the
whole priority.

## What's available

The prior brainstorm already surveyed logging sources exhaustively before
deferring the domain. Re-checked here rather than assumed stale:

- **CPython's own `logging` module, pinned `v3.14.5`.** Checked directly:
  zero t-string literals in `Lib/logging/__init__.py` or
  `Lib/test/test_logging.py`. Matches the "Template strings in stdlib
  logging" discussion thread found earlier — this is a proposal, not
  shipped code. No stdlib extraction path exists.
- **`t-strings/pep750-examples`** (MIT). Two distinct real literals, one of
  them a genuine `logger.info(t"...")` call. Admissible, small, and this is
  what this design uses.
- **`pR0Ps/tstringlogger`**. Richer shapes (`=` debug specifier + subscript
  + attribute access in one literal) but `pyproject.toml` declares
  `license = "LGPL-3.0-only"` and there's no `LICENSE` file either — same
  blocker as psycopg was for SQL. Explicitly not revisited as an exception
  here (decision: take the two real MIT literals, don't reopen the license
  question).
- **`NMRhub/tstring-logger`**. A logging-integration library with no usage
  examples in the repo to extract from.

## One correction to the prior design doc's record

The prior design doc characterized both `pep750-examples` literals as "both
via `logger.info(t\"...\")`". Checked against the actual pinned source: only
one of the two literals appears in a real `logger.info(t"...")` call. The
other, `t"${amount:0.2f}"`, appears in `TemplateMessage(template,
DecimalEncoder())` — a custom logging-message encoder, not a bare
`logger.X()` call, but still genuinely part of the file's structured-logging
test material. Both are legitimate `logging`-domain seeds; the provenance
detail is just more precise here than it was recorded before.

## The source and the two seeds

**One correction the earlier survey didn't catch**: the locally-vendored
clone's git remote (`davepeck/pep750-examples`) no longer resolves — `git
ls-remote` against it returns "Repository not found." The repository moved
to the `t-strings` GitHub org. Verified the exact commit the earlier survey
used still resolves at the new URL, so the pin is unaffected, but
`sources.toml`'s `url` field must point at the live location:

| id | url | sha | license |
| --- | --- | --- | --- |
| `pep750-examples-2026` | `https://github.com/t-strings/pep750-examples` | `2e644e624f7fafda964d70d2150af4029a8431e2` | MIT |

Both literals verified as real `ast.TemplateStr` nodes at that exact pinned
commit (not local working state), with exact line spans and real call
context:

| literal | line | context | binding |
| --- | --- | --- | --- |
| `t"Hello, {name}!"` | 89 | `logger.info(t"Hello, {name}!")` | `name='Ada'` |
| `t"${amount:0.2f}"` | 61 | `message = TemplateMessage(template, DecimalEncoder())` | `amount=42.5` |

Both format specs re-verified render-eligible against Python's real
`format()` (the class of bug the previous branch's final review caught and
fixed for regex/sql — checked here up front instead of after the fact):
`format("Ada", "")` and `format(42.5, "0.2f")` both succeed trivially, no
library-specific spec involved.

## What this does not do

Same scope boundary as the prior branch: no pattern authoring, no
`composition.toml`/`sampling.toml` changes, no `construct`/
`compose_templates` population. Logging's total seed count only grows by 2
(4 → 6, both extracted) — still well under the eventual 12-15 floor
`SP5_SCALE_BRIEF.md` calls for, but growing logging's authored count back
up is a separate, already-deferred decision, not part of this brainstorm.
