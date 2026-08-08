# Mellum2 issues observed, for upstream report

Running log of problems found while evaluating Mellum2 as the **target** model
for PEP 750 t-string code generation. These are model and serving issues, kept
separate from anything about our training data.

**Checkpoints tested**

| label | id |
| --- | --- |
| **Mellum 2.1 GRPO, step 200** | `mellum2-grpo-v23-thinking-step-200-mlx-q8` (local q8 conversion of `grpo_mellum_v23_thinking_mix4_nemo72_triton_nofuse-step-200`) — an in-progress checkpoint of the **2.1** line, *not* a preview of released 2.0 |
| released Thinking | `jedisct1/Mellum2-12B-A2.5B-Thinking-mlx-8bit` |
| released Instruct | `jedisct1/Mellum2-12B-A2.5B-Instruct-mlx-8bit` |

**Read this first.** Issues 3 and 4 are **retracted**. They were measured at
`max_tokens=1500` — too small a budget for a thinking model: Qwen's reference
evals use 32k tokens, and the standard handling of an exhausted thinking budget
is a forced `</think>` (as vLLM does) rather than treating the trace as
unterminated. The measurements below are therefore substantially artifacts of
my harness. See [MELLUM21_TRAINING_REPORT.md](MELLUM21_TRAINING_REPORT.md) for
the retraction and what a correct evaluation requires.

*Narrowed after reading the technical report* ([arXiv:2605.31268](https://arxiv.org/abs/2605.31268),
see [MELLUM2_REFERENCE.md](MELLUM2_REFERENCE.md)): the retraction is about the
**token budget only**, not the temperature. The report's own post-training
suite runs "all benchmarks at 0.0 temperature ... all models use greedy
decoding", pass@1, so T=0 is the published protocol rather than a mistake. The
sampling guidance we were given describes the team's eval backlog. The
retraction also covers *thinking* generations only — released Instruct
clean-stops at 1.00 with a 634-char mean, so the budget never bound there.

The **tokenizer question is answered**: the upstream 2.1 checkpoint ships a
correct `tokenizer_config.json` (35 `added_tokens_decoder` entries, full
`additional_special_tokens`, `special_tokens_map.json`). The MLX conversion
strips these — but it strips them from the *released* models too, and those do
not degenerate, so it is not the differentiator.

Nothing in this file about the 2.1 checkpoint's generation behaviour should be
reported upstream. The knowledge observations (issues 1 and 2) are less
affected but still rest on single greedy samples.

---

## The degenerate checkpoint is Mellum 2.1, not a 2.0 preview

An earlier draft of this file described the step-200 checkpoint as a preview of
Mellum2 and treated its failures as stale artifacts to be discarded. That was
wrong in an important direction: it is an in-progress checkpoint of the newer
**2.1** line, so its degeneration is a **live training signal**, not an
irrelevance. Written up separately for upstream in
[MELLUM21_TRAINING_REPORT.md](MELLUM21_TRAINING_REPORT.md).

The comparison below still stands — released 2.0 does not show these symptoms —
but the conclusion changes from "ignore it" to "report it".

## Comparison with released 2.0 weights

Measured against the released weights
(`jedisct1/Mellum2-12B-A2.5B-{Instruct,Thinking}-mlx-8bit`, 10 generations
each, temperature 0):

| generation health | 2.1 step-200 | released Thinking | released Instruct |
| --- | --- | --- | --- |
| clean-stop rate | ~0.5 | 0.80 | **1.00** |
| unterminated `<think>` | 12/25 (48%) | 0/10 | 0/10 |
| repetition loops | 11/25 (44%) | 1/10 | **0/10** |
| control tokens as literal text | frequent | 0/10 | **0/10** |
| mean output | — | 2310 chars | 634 chars |

**Issues 3 and 4 below are not defects of released 2.0.** They are specific to
the 2.1 step-200 checkpoint — which makes them worth reporting to the team
working on 2.1, not discarding.

**Released Instruct is the variant to build on**: perfect termination and 3.6x
shorter outputs than Thinking, at equal knowledge (both wrong, see below).

## The knowledge gap is real, and differs by checkpoint

All three checkpoints confabulate a PEP 750 API, and each invents a *different*
one. None is close to the accepted surface.

| checkpoint | claimed type | claimed attributes |
| --- | --- | --- |
| 2.1 step-200 | "tagged template literal", subclass of `str` | `.tag`, `.parts`, `.values` |
| released Thinking | `t_string` | `prefix` ("the tag"), `f-strings`, `values` |
| released Instruct | `t_string` | `.value`, `.format_args` |
| **actual** | **`string.templatelib.Template`**, not a `str` | **`.strings`, `.values`, `.interpolations`** |

Two observations that matter for the training data:

- The *stale tagged-template draft* is a **2.1-only** artifact. The
  released models do not carry it, so there is less to unlearn than first
  thought — the released gap is confabulation over absence, not a competing
  prior.
- The released models still reach for a *tag* concept (Thinking's `prefix`
  "e.g. `'t'`"), so some draft-era contamination survives into Thinking.

This is a clean target: a specific, reproducible, wrong-API gap in the model
the work is meant to improve.

## 1. (2.1 step-200) Stale PEP 750 knowledge: the withdrawn *tagged template* draft

**Severity:** high for this use case — a confident wrong prior is worse than no
knowledge, because it must be unlearned rather than filled in.

Asked what `t'Hi {name}'` evaluates to and what its public attributes are, the
model answered that PEP 750 "introduces tagged template literals", that the `t`
prefix is "the tag", and that the public attributes are **`.tag`, `.parts` and
`.values`**. It also stated the result "is a subclass of `str`".

Every one of those is from an **earlier draft** of PEP 750. The accepted PEP
dropped tags entirely. The real surface is:

| model believes | actual |
| --- | --- |
| tagged template literal, `t` is the tag | no tags; `t"..."` is its own literal form |
| `.tag` | does not exist |
| `.parts` | `.strings` (static parts) |
| `.values` | `.values` — the one it gets right |
| — | `.interpolations`, each with `.value`, `.expression`, `.conversion`, `.format_spec` |
| subclass of `str` | `string.templatelib.Template`, **not** a `str` |

If the training corpus is intended to teach the accepted API, it will be
fighting this draft-era prior rather than writing on a blank slate.

## 2. "t-string" resolved as "triple-quoted string" in code generation

**Severity:** high, and distinct from issue 1.

In the knowledge probe the model reached for the tagged-template draft. In an
actual code-generation task its reasoning trace instead read:

> "But they said 'Use a t-string'. t-string likely means triple-quoted string
> (`"""..."""`). So we can do..."

and it emitted `answer = f"""Hello, Ari!"""` — an f-string with triple quotes.

So the term is ambiguous to the model, and which reading it picks depends on
context. This is a term-disambiguation failure rather than a stale API, and it
is arguably the more damaging of the two: the model does not recognise that a
t-string is a distinct language feature at all.

## 3. (2.1 step-200) Degenerate repetition and control-token leakage

**Severity:** medium — affects usability irrespective of t-strings.

At `max_tokens=700`, generation entered a repetition loop and never terminated,
emitting roughly:

```
 = "Ari"<|im_end|>
</tool_call>_name = "Ari"<|im_end|>
</tool_call>_name = "Ari"<|im_end|>
... (repeating to the token limit)
```

Two problems visible at once. The loop itself, and `<|im_end|>` and
`</tool_call>` appearing as **literal text in the output stream** rather than
terminating generation. That suggests an EOS / stop-token configuration
mismatch between the chat template and the serving path. Reproduced through
`mlx_lm.generate` with the model's own `chat_template.jinja`.

## 4. (2.1 step-200) Reasoning traces that never close

**Severity:** high. Quantified over a complete 25-task run at
`max_tokens=1500`, temperature 0:

| symptom | rate |
| --- | --- |
| `<think>` opened and **never closed** — no answer emitted at all | **12/25 (48%)** |
| `<|im_end|>` emitted repeatedly as literal text (issue 3) | **11/25 (44%)** |

Nearly half of all generations never produce an answer. This is the single
most damaging issue for evaluating the model, and it is not specific to
t-strings — the task set is ordinary Python string-building work.

**Consequence for any benchmark number:** a score against this checkpoint is
not a clean measure of capability, because roughly half the trials fail before
the model has a chance to be right or wrong. Mellum's 0/25 on our
out-of-distribution set (below) must be read with that caveat, not as a
capability measurement.

## 5. Packaging note (not a JetBrains issue)

`mellum` is supported in `mlx-lm` **git main only**; the newest PyPI release
(0.31.3) does not include it, and reports `Model type mellum not supported`.
Anyone pinning mlx-lm from PyPI cannot load Mellum2 at all. Worth knowing when
telling people how to run it locally.

---

## Resolved since first draft

- Issues 1, 3 and 4 do not reproduce on released weights — preview artifacts.
- **`mlx_lm.lora` trains Mellum2 fine.** Smoke test on released Instruct:
  0.335% trainable (40.65M of 12.15B), two updates, loss 1.094, no MoE routing
  errors. The adapter path for the deliverable exists.

## Still open

- Whether issue 2 (t-string read as "triple-quoted string") reproduces on
  released Instruct in a code-generation context, as opposed to the knowledge
  probe. Being measured now via `ood-v1`.
- Whether the reference (non-MLX) runtime agrees with these numbers.
- **Does the report's method for teaching new API surface exist and is it
  undocumented, or is there none?** Sections 5.1 (SFT) and 5.2 (RLVR) describe
  no path for acquiring a language feature published after pre-training. PEP
  750 is a concrete instance: the model is confidently wrong rather than
  ignorant, and each checkpoint is wrong differently. Worth asking directly —
  it decides whether our corpus is a contribution or a duplication.
- Whether the released Thinking variant's 1-in-10 repetition rate matters in
  practice, or is within normal sampling variation at temperature 0.
