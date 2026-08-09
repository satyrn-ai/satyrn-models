# SP5 data/logging seed floors: closing what Priority 1 left unfinished

Addresses `SP5_SCALE_BRIEF.md` Priority 1's original goal ("bring every
domain to at least 12–15 seeds") for the two domains it never actually
reached, discovered while brainstorming Priority 4.

## Why this redirects away from "new patterns"

Checked the actual current state before scoping Priority 4: 70 seeds, 57
patterns. The brief's own target for reaching 800–1000 distinct shapes was
"~150 seeds and ~70 patterns" — patterns are at 81% of that target, seeds
at only 47%. Broadly adding new patterns now would repeat the exact
duplication risk Priority 4 was gated to avoid ("more patterns over 54
seeds deepens duplication rather than relieving it"), just at a slightly
higher seed count.

More specifically, two domains never reached the floor Priority 1 called
for:

| domain | seeds | note |
| --- | --- | --- |
| logging | 6 | prior branch closed extraction (0→2) but never raised the floor |
| data | 6 | never touched by any prior branch — outside Priority 1's original weighting ("regex, logging, sql, html") |
| regex | 11 | reached |
| html | 15 | reached |
| sql | 15 | reached |
| text | 17 | reached |

This brainstorm closes both remaining gaps, bringing both to 13 seeds, so
the corpus's actual seed:pattern ratio stops drifting further from the
brief's own target before any pattern work resumes.

## Data: pure extraction, zero new sourcing exceptions

`data` domain seeds are the numeric/computational shapes — format specs,
conversions, arithmetic — as opposed to `text`'s name-only greetings (the
existing seed `t'With format {1 / 0.3:.2f}'` is `data`; `t'Hello, {name}'`
is `text`). That's exactly the flavor of `Lib/test/test_tstring.py`, part
of the **already-registered** `cpython-v3.14.5` source in `sources.toml` —
the very first brainstorm of this whole effort found it 69% unmined (later
re-counted precisely at 31 real literals, 26 distinct, via direct AST
parse) and it was never revisited. No new `[[source]]`, no licensing
question — this is finishing extraction on a source already admitted.

Seven candidates, all with real bindings read directly from the
surrounding test code (same rigor as the original `CPYTHON_SEEDS`):

| literal | line | bindings | why |
| --- | --- | --- | --- |
| `t"Sum: {a + b}"` | 38 | `a=10`, `b=20` | binop expression, source: `a = 10; b = 20` above it |
| `t"Pi: {value:.2f}"` | 85 | `value=3.14159` | plain format spec |
| `t"Object: {obj!s}"` | 94 | `obj=42` | `!s` conversion |
| `t"ASCII: {text!a}"` | 105 | `text='Café'` | `!a` conversion on real non-ASCII text, matches upstream's own motivating case |
| `t"Value: {value=}"` | 117 | `value=3.14159` | the self-documenting `=` debug specifier — **absent from the entire corpus today** |
| `t"Value: {value=:.2f}"` | 124 | `value=3.14159` | debug specifier + format combined — also absent |
| `rt"{path}\Documents"` | 145 | `path='C:'` | raw+template string-prefix combination — **also absent from the entire corpus** |

All are real, executed CPython test code — no format-spec validity check
needed the way the third-party sourcing branches required, since these
compiled and ran in CPython's own CI by construction. `kind="extracted"`,
same `source_id="cpython-v3.14.5"`, new `path="Lib/test/test_tstring.py"`.

## Logging: hand-authored, executing the rubric from the first brainstorm

Real logging+t-string usage remains exhausted — re-confirmed nothing
changed since the earlier brainstorm (`pep750-examples`'s 2 real literals
are already seeds; `pR0Ps/tstringlogger` is still LGPL-3.0-only). The first
logging brainstorm drafted a hand-authoring rubric before logging's scope
was narrowed to extraction-only that round; this executes it:

| literal | bindings | covers |
| --- | --- | --- |
| `t"[DEBUG] {msg}"` | `msg='cache miss'` | DEBUG level |
| `t"[WARNING] slow query took {elapsed:.2f}s"` | `elapsed=1.23` | WARNING level, non-string (float) binding, format spec |
| `t"[ERROR] request failed with status {status}"` | `status=500` | ERROR level, non-string (int) binding |
| `t"user={user} action={action} status={status}"` | `user='alice'`, `action='login'`, `status='ok'` | structured multi-field logging idiom |
| `t"retrying={retry}"` | `retry=True` | non-string (bool) binding |
| `t"{event!r}: id={record_id}"` | `event='order_created'`, `record_id=42` | conversion combined with a second, differently-typed binding |
| `t"correlation_id={cid} duration_ms={dur}"` | `cid='abc-123'`, `dur=42` | request-tracing idiom, another int binding |

All format specs are real, valid Python (`.2f` on a float; everything else
bare) — no library-specific convention risk, since these are authored
directly against stdlib `format()` semantics rather than copied from a
third-party renderer. `kind="authored"`, appended to `authored.jsonl` in
the existing `occ-auth-N` style, human review before merge like every
other authored seed.

## What this does not do

No pattern authoring, no `composition.toml`/`sampling.toml` changes. Both
domains land at 13 — inside the brief's 12–15 floor but not at the top of
it, matching how `regex` was accepted at 11 in the prior branch. Priority 4
(new patterns generally) is deferred again, now on firmer ground: once this
lands, every domain is at or above floor and the seed:pattern ratio is
closer to the brief's target proportions.
