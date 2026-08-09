# SP5 select_result gap: a negative finding, recorded so it isn't re-investigated

Follows up on the select_result/render_subskill patterns design
(`docs/superpowers/specs/2026-08-09-sp5-select-render-patterns-design.md`),
whose own "What this brings" section was honest that its one new
`select_result` pattern barely moved that property's share of the raw
candidate pool (23.4% → 22.5%, an actual drop, against a 43% target). This
doc answers the natural next question — "so close the gap properly" — by
checking whether that's even a real problem, before proposing more work.

**Conclusion: it isn't. There is no further `select_result`-specific
pattern work available, and the "43% target" framing that motivated this
question was never the right thing to chase in the first place.**

## Finding 1: candidate-pool share was never the binding constraint

`composition.toml`'s 43%/45% targets are proportions of a **published**
corpus, and the mechanism that actually enforces them —
`sampling.py`'s selector, via `composition.py`'s `target_counts()` — computes
an absolute row requirement: `target_rows × proportion`, checked against
`sampling.toml`'s committed `target_rows = 500` for the pilot (and the
500 ⊂ 2k ⊂ 5k nested snapshot structure `CORPUS_MACHINERY.md` describes for
larger publishes).

Computed directly, not estimated:

| property | absolute rows needed @ 500-row pilot | rows needed @ largest committed tier (5k) | current raw candidate supply |
| --- | --- | --- | --- |
| `select_result` | 215 | 2,150 | **2,520** |
| `render_subskill` | 225 | 2,250 | **3,024** |

Both properties have had more than enough absolute row supply to satisfy
every publish size this pipeline actually produces — this was true before
the select/render-patterns branch added its 6 patterns, and remains true
now. The "22.5%/27.0% of the candidate pool" numbers from that branch's
design doc are factually correct but answer a question `sampling.py`
doesn't ask. **No amount of candidate-pool-share growth for
`select_result` was ever going to matter to the actual published corpus's
composition**, because it was never capacity-constrained.

## Finding 2: select_result's pattern space is already fully saturated

`select_result` has exactly 2 dimensions: `outcome` (5 values —
`template`, `strings`, `values`, `joined_static`, `rendered`) × `role`
(2 values — `consumer`, `author`). 5 × 2 = 10, and `CATALOG` now has
exactly 10 `select_result` patterns — the select/render-patterns branch's
`contrast-author-template` addition closed the last gap. There is no
unfilled `(outcome, role)` combination left. Unlike `construct` (which had
unfilled `expression`/`conversion`/`format_spec` combinations) or
`render_subskill` before this session's fix (five unfilled `stage`/`role`
combinations), `select_result` has nowhere left to grow *combinatorially*.

## Finding 3: the real ceiling is seed-shape diversity, which is shared infrastructure

Measured directly: every one of `select_result`'s 10 patterns, applied
across the full 84-seed pool, produces exactly 252 candidate rows (84
seeds × 3 prompt variants) that collapse onto exactly **16 distinct
structural skeletons** (identifiers/constants erased, per `diversity.py`'s
`reference_skeleton` — the same metric this project already uses
elsewhere). Across all 10 patterns combined, only **112** distinct
skeletons exist (not 160), meaning skeleton shapes overlap across
different `select_result` patterns too.

This is not a `select_result`-specific ceiling. Since every arity-1
pattern wraps a seed's own interpolation structure in a fixed code
template, the number of distinct output shapes a property can produce is
bounded by how many distinct *seed* shapes exist — not by how many
patterns exist for that property. `select_result` has already exhausted
its pattern-count lever (finding 2); growing its shape diversity further
would require growing seed-shape diversity, which is shared across every
other arity-1 property (`introspect`, `render_subskill`,
`join_static_parts`, `render_template`) and is exactly what this session's
seed-sourcing and floor-closing branches were already doing — not a
`select_result`-specific task.

## What this means going forward

- Don't propose more `select_result` patterns in response to its
  candidate-pool percentage looking low relative to `composition.toml`'s
  target. That percentage was never the enforced constraint; check
  absolute row counts against `sampling.toml`'s `target_rows` instead.
- If `select_result`'s *shape diversity* ever needs to grow beyond 112
  skeletons, that's a seed-corpus question, not a pattern-authoring one —
  revisit only alongside future seed-sourcing work, not in isolation.
- `render_subskill` is in the same position for capacity (finding 1) but
  NOT for pattern-space saturation — it has no more combinatorial gaps
  either now that this session closed its 5 missing author-role patterns
  (6 stages × 2 roles = 12, and `CATALOG` now has exactly 12
  `render_subskill` patterns). The same "no further pattern work, seed
  diversity is the shared bottleneck" conclusion applies to it too.
- `composition.toml`'s 43%/45% targets themselves were not re-examined
  here — this doc only established that current supply already satisfies
  them at every committed publish size. Whether those specific percentages
  are still the right ones to target is a separate, unexplored question.
