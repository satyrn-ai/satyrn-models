# Running a Mellum GRPO thinking checkpoint for agentic coding

Notes from evaluating `grpo_mellum_v23_thinking_mix4_nemo72_triton_nofuse-step-200`
(an in-progress **2.1** GRPO checkpoint) alongside released Mellum 2 weights,
plus corrections the Mellum team gave us and the technical report
([arXiv:2605.31268](https://arxiv.org/abs/2605.31268)).

**Scope, stated up front:** we evaluated **code generation**, not tool calling.
We never ran BFCL or any function-calling benchmark. Everything below is a
hazard to rule out, not a measured claim about tool-calling quality — with one
exception, noted as such. Most of our own early findings turned out to be
harness artifacts, which is itself the main lesson.

## The single most likely cause: the reasoning trace never closes

At `max_tokens=1500`, **48% of generations opened `<think>` and never closed
it**, and 44% degenerated into repetition. No answer was emitted at all in
nearly half of trials.

For plain codegen that shows up as a bad score. **For agentic coding it
presents exactly as "tool calling is broken"** — if the trace never terminates,
no `<tool_call>` block is ever reached, so the harness sees no tool call and
reports a parse failure or an empty step.

What the Mellum team told us:

- Use a much larger budget. Qwen's reference evaluations use **32k tokens**;
  1500 is not in the right range for a thinking checkpoint.
- Give it an explicit **reasoning budget** rather than a flat cap, and
  **force-close the trace** when the budget is exhausted — vLLM implements this
  as `thinking-token-budget`, emitting a `</think>` so the answer can follow.
  Treating an exhausted trace as "unterminated" measures your harness.

The report is consistent: LiveCodeBench goes **37.2 (instruct) → 75.1
(SFT-Thinking)**, described as reasoning being "in the model's reach but
requires an explicit thinking budget to be unlocked."

**Check first:** log the raw completion for a failing step. If it ends mid-trace
with no `</think>`, this is your bug and nothing downstream matters.

## Temperature: do not use 0 with a thinking checkpoint

The team's guidance: thinking checkpoints **doom-loop at T=0**; evaluate in
**T ∈ [0.5, 1.0]**, at pass@k. Qwen explicitly documents not using T=0 for
their thinking models.

Be aware of a tension worth knowing about: the **published report evaluates at
T=0 with greedy decoding** (except BFCL at 0.01 and LiveCodeBench at 0.2),
pass@1. The team described sampled/pass@k evaluation as being on their backlog.
So T=0 is the protocol behind the published numbers, while T ∈ [0.5, 1] is the
advice for in-progress thinking checkpoints specifically. For agentic use,
follow the latter.

## The one direct tool-calling observation we do have

On the GRPO step-200 checkpoint we saw **`</tool_call>` and `<|im_end|>`
emitted as literal text in the output stream** rather than terminating
generation, inside a repetition loop:

```
 = "Ari"<|im_end|>
</tool_call>_name = "Ari"<|im_end|>
</tool_call>_name = "Ari"<|im_end|>
```

That is a stop-token / chat-template mismatch in the serving path. If
`</tool_call>` arrives as ordinary text, the tool-call boundary never fires.
This did **not** reproduce on released weights (0/10 occurrences on both
released Instruct and Thinking).

**Check:** confirm the special tokens are registered as special in whatever
stack you are serving from, and that your stop-token set matches the model's
own `chat_template.jinja`.

## Verify the tokenizer config survived your conversion

The **upstream checkpoint ships a correct `tokenizer_config.json`** — 35
`added_tokens_decoder` entries, full `additional_special_tokens`, and a
`special_tokens_map.json`. That is not the problem at source.

Community conversions may strip them. Ours (MLX 8-bit) did. For us that was a
red herring — the *working* released conversions strip them identically and do
not degenerate — so it was not the differentiator for codegen.

**But it is a much more direct hazard for tool calling than for codegen.** If
`<tool_call>` / `</tool_call>` are not registered as special tokens, they
tokenize as ordinary text and will not act as stop tokens, which is precisely
the leakage above. Worth checking even though it did not explain our issue.

## Prefer a released checkpoint unless you are specifically testing the GRPO line

Generation health, 10 greedy generations each:

| | 2.1 GRPO step-200 | released Thinking | released Instruct |
| --- | --- | --- | --- |
| clean-stop rate | ~0.50 | 0.80 | **1.00** |
| unterminated `<think>` | 12/25 (48%) | 0/10 | 0/10 |
| repetition loops | 11/25 (44%) | 1/10 | **0/10** |
| control tokens as literal text | frequent | 0/10 | **0/10** |

An early GRPO step also has not yet accumulated the RL gains that matter most
for agentic work. From the report, RL is exactly where tool use jumps:

| benchmark | SFT | RL |
| --- | --- | --- |
| BFCL v3 (multi-turn function calling) | 43.1 | **66.3** |
| BFCL v4 (agentic: web search, memory) | 31.8 | **44.2** |

"RL is where the largest single-step jumps appear." RL-Thinking leads the
report's panel on BFCL v4 at **45.6**. So a finished RL checkpoint should be
usefully capable at tool calling — **if you are seeing near-zero tool calling,
suspect the harness before the model.**

## Give it tools in the shape it was trained on

The SFT corpus stores every example as `messages` (role/content turns), an
optional **`tools`** list of function-call signatures, and an optional
`reasoning` field. The tool-use split covers "general function-calling formats,
Bash execution, a clarification tool, and search tools," and explicitly teaches
"both schema-faithful tool invocation and **recovery from tool errors**."

Two implications: pass tools through the model's own template rather than
hand-rolling a prompt format, and expect error-recovery behaviour to exist —
so a tool that returns an error should not derail a run.

## Pin your runtime

`mellum` support in `mlx-lm` is **git-main only**; PyPI 0.31.3 raises
`Model type mellum not supported`. We had it installed ad hoc and unpinned, and
a routine dependency sync silently replaced it — which broke model loading
outright and, worse, meant adapters trained in different sessions were not
comparable. Pin to an exact commit.

## Checklist

1. Log a raw failing completion. Unterminated `<think>`? → budget, and
   force-close at exhaustion.
2. Raise the reasoning budget toward the 32k reference; stop using a flat 1500.
3. Move off T=0; try T ∈ [0.5, 1].
4. Grep the output for `</tool_call>` and `<|im_end|>` as literal text → stop
   token / template mismatch.
5. Confirm `added_tokens_decoder` and `additional_special_tokens` survived your
   conversion.
6. Re-run against released Instruct or RL weights as a control. If those work
   and the GRPO step does not, it is the checkpoint, not your harness.
7. Pin the runtime to a commit.
