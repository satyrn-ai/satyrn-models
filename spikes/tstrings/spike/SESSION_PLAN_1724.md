# Scheduled session plan — 2026-08-05 17:24

Three items, in this order. B is a go/no-go and must not eat C. If time runs
short, **finish C with fewer epochs rather than starting anything new** — one
clean arm beats two truncated ones.

Read [MELLUM2_REFERENCE.md](MELLUM2_REFERENCE.md) first; it is the source for A.

## A. Apply the technical report (~30 min, no GPU)

1. ~~**Training hyperparameters.**~~ **Done 2026-08-05.** `--epochs` already
   existed; added `--lr-schedule` (linear warmup then cosine decay to a tenth
   of peak) and `--lr-warmup`, both opt-in so recorded runs stay byte-identical.
   Verified end to end against `mlx_lm.tuner.utils.build_schedule`.

   Two traps found while testing, both of which would have hit at runtime:
   YAML 1.1 resolves `3e-05` as a **string**, which fails deep inside the
   scheduler — the value must carry a decimal point; and mlx-lm offsets the
   post-warmup schedule by `warmup + 1`, so `decay_steps` must exclude the ramp
   or the rate ends at 7.1e-6 instead of 3e-6.

   Invoke as: `--epochs 3 --learning-rate 3e-5 --lr-schedule`.
   Keep the LoRA `scale: 20.0` fix — do not derive it from rank.
2. **Handover schema.** The report stores every SFT example as `messages`
   (role/content turns) + optional `tools` + optional `reasoning`, and the
   Instruct variant **discards** `reasoning`. Our rows already carry `messages`;
   write `spike/export_sft.py` to emit the corpus in their exact schema, tagged
   for their **single-turn coding** category (not agentic — that split is
   long-horizon repo-edit trajectories).

## B. Restart the Mellum GRPO checkpoint, measured properly (~45 min)

`models--JetBrains--grpo_mellum_v23_thinking_mix4_nemo72_triton_nofuse-step-200`
is in the HF cache. Every prior number on it is retracted: it is a **thinking**
checkpoint measured at `max_tokens=1500`, and 48% of generations opened
`<think>` and never closed.

1. Add `--force-close-think` to `probe_model.py` — on budget exhaustion, inject
   `</think>` and continue, which is what vLLM does and what the team asked for.
   Without this the measurement scores the harness again.
2. Probe at `--max-tokens 8192` and `16384`, `--limit 5`. Small n deliberately:
   this is go/no-go on whether the degeneration survives an adequate budget, not
   a capability measurement. A 12B MoE at q8 is slow; check tok/s on the first
   generation and drop to 8192 only if 16384 is infeasible.
3. Report temperature 0 — that is the report's published protocol
   ("all benchmarks run at 0.0 temperature ... all models use greedy decoding"),
   not a mistake to correct.
4. Update `MELLUM_ISSUES.md` with what survives. If the degeneration is gone at
   an adequate budget, say so plainly — that retires issues 3 and 4 entirely.

## C. The biggest lever: target diversity (rest of the session)

### The finding — **done 2026-08-05, superseded the original diagnosis**

The first draft of this plan said the corpus was defective because 454 rows
carried only 144 distinct assistant targets (31.7%). **That framing was wrong.**
Each answer appears once per prompt family, so textual target diversity is
pinned near 1/3 by design; 31.7% is the expected value, not a defect.

The real defect is **structural**. The pool ships a `skeleton` field —
identifiers anonymised to `x`, literals to `"..."` — so program *shape* can be
counted directly:

| | curriculum used | pool offers |
| --- | --- | --- |
| distinct program shapes | **103** | **270** |
| **render_subskill shapes** | **15** | **81** |
| patterns | 44 | 51 |
| seeds | 48 | 54 |

And the specific cause: **`render-subskill-render_template` was never sampled
at all.** It is approved, has 132 rows over 44 seeds and 14 distinct shapes,
and is the only pattern that practises rendering a whole template. The earlier
repair thinned the render cells because the byte-identical `render_template`
body was over-exposed in 102 of 454 rows — correct about the duplication, but
it took volume and diversity down together and dropped this pattern to zero.
Rendering is then the one capability that failed in every configuration on both
base models, and ~11 of the 25 remaining `ood-v1` failures leave
`answer = template` unrendered.

### The fix — **built, not yet trained**

Two changes to `build_curriculum.py`, both landed:

1. `--diversify` — break allocator ties toward unused *shapes* rather than
   unused seeds. Stratum fill deliberately stays in the lead so the domain and
   source marginals the original repair was about are not traded away.
2. Restored `subskill_render_template` and raised the render subskill cells
   (9 → 18, author-side 6 → 24 to hold the role marginal). Safe now only
   because `--diversify` prevents the byte-identical repetition directly.

`handoff/curriculum-diversity-v1` (fingerprint `ea0f95fb26c1`), 516 train /
57 valid:

| | baseline | diversity-v1 |
| --- | --- | --- |
| rows | 492 | 573 |
| distinct shapes | 103 / 270 | **133 / 270** |
| **render shapes** | 15 / 81 | **39 / 81** |
| render rows | 51 | 132 |
| max shape repeat | 30 | **12** |
| marginals (domain / role / source) | 1.5 / 2.0 / 1.1 pp | 1.4 / 2.8 / 0.1 pp |

Render shape coverage is 2.6x with *less* structural repetition than before.

Two tests added and **verified by sabotage** (both fail when the mechanism is
removed): `test_no_approved_render_pattern_is_left_unsampled` — the existing
unsampled-pattern test checked a hardcoded list of 15 that never named
`render-subskill-render_template`, so the gap was invisible to the suite — and
`test_diversify_widens_program_shape_coverage`.

### Premise falsified — the experiment above is withdrawn

A Fable review, verified independently, found the primary metric could not
move: of the 11 `ood-v1` semantic failures, **7 define and call a correct
renderer** and **all 11** require string literals the prompt never supplies.
One asks to render a diagnostic "with the supplied credentials" and supplies
none; the reference invents `riley`, `swordfish` and `***`. Exact match was
measuring literal-guessing.

Re-scoring all four saved arms offline with `spike/rescore_ood.py` — no GPU,
completions were already on disk — settles it:

| arm | rendered | unrendered `Template` | **undefined renderer** | unbound input |
| --- | --- | --- | --- | --- |
| bare | 13 | 0 | **0** | 3 |
| + LoRA | 11 | 0 | **1** | 4 |
| + docs | 7 | 1 | **0** | 8 |
| + LoRA + docs | 6 | 1 | **6** | 4 |

**Rendering is not the failing capability** (0/0/1/1). The trained-in defect is
*calling the corpus's renderer without defining it* — present only on LoRA
arms. `diversity-v1` raised that body's share from 11.5% to 16.3%, which is
the wrong direction: the adapter that produced the 6 failures was trained at
11.5%. No curriculum row calls a renderer without defining it, so repetition
alone is making the name feel ambient.

### The replacement experiment

`handoff/curriculum-lowbody-v1` — `--diversify --body-scale 0.35`, 486 train
rows, renderer body in **30 rows (6.2%)** against `repair-v2`'s 11.5%. Render
*subskill* cells are untouched: they teach classification, conversion and
formatting without emitting the block.

**Primary metric: `undefined_renderer` on `ood-v1`, baseline 6.** It is
attributable to us rather than to the benchmark, it is zero on the bare model
so it is unambiguously trained in, and unlike the old metric it has room to
move.

Marginals now domain 2.2 / role 2.2 / source 0.6 pp — role was 5.9pp after the
thinning and is fixed with non-body author cells. Role is finally covered by
`test_enforceable_marginals_stay_on_profile`, which had excluded it without
justification.

### What remains — GPU only

- **Run A**: `repair-v2` + new recipe (3 epochs, scheduled LR).
- **Run B**: `curriculum-lowbody-v1` + same recipe.
  The recorded `repair-v2` + old recipe anchors the recipe effect, so
  curriculum effect = B − A. Do not attribute anything to `--diversify` alone:
  its marginal contribution to shape coverage is 35→39 of 81 against
  restoration's 15→35.
- Re-score both with `rescore_ood.py`, not exact match.
- Multi-seed with paired per-task flips before believing any of it: n=25
  single-seed against documented 10–19 point variance is not enough.

### Caveats to carry into the write-up

- Warmup clamps to 48 at 195 iters, so this is **not** the report's 100-step
  ramp.
- `skeleton` regex-replaces every lowercase word, keywords included, and
  collapses all string literals — so it is line-structure coverage, and blind
  to interpolation count, conversions and format specs.
- `ood-v1` exact-match scores are a floor, not a capability measure, until the
  prompts are repaired.

**Primary metric: semantic failures on `ood-v1`, baseline 11.** Do not use
`ood-v1` pass rate — it is too coarse to show progress and using it is what
hid the only real signal we had. Secondary: policy stays at 0/25, `repair-v1`
does not regress from 78/84 (that arm is `+ LoRA + docs`).

Run the same eval arms as the existing Mellum table so the comparison is like
for like: bare / +LoRA / +docs-v3 / +LoRA+docs-v3.

### Hard constraint, unchanged

**Do not author SP5 patterns and do not write to `patterns/approvals.jsonl`.**
That ledger records human review keyed by `pattern_input_fingerprint`; writing
entries for self-authored patterns forges a review that never happened.
Deduplication only *redistributes* among already-approved material. If the
approved corpus cannot supply 454 distinct targets, **report the achievable
ceiling** — that number is itself the finding, and it is the argument for
sending SP5 back for more seeds.

## Reporting

Append to `REPAIR_STATUS.md`, commit on `worktree-spike-tstrings-training`, and
lead the summary with the diversity ceiling and the stage-level table. Do not
lead with a `repair-v1` score; that benchmark is saturated and in-distribution.
