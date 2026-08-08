# Mellum 2.1 step-200: retraction and corrected status

**Status: the earlier version of this file should not be sent upstream.** Its
three headline symptoms were measured with an evaluation setup the Mellum team
has since identified as wrong for a thinking model. This version records what
was actually established, what was an artifact of my harness, and what a
correct evaluation would require.

## Answer to the question that was asked

> "First thing to check is if the model shipped with correct
> `tokenizer_config.json`."

**Yes — the upstream checkpoint is correct.** The
`grpo_mellum_v23_thinking_mix4_nemo72_triton_nofuse-step-200` snapshot ships:

- `tokenizer_config.json` with **35 `added_tokens_decoder` entries** and a full
  `additional_special_tokens` list (`<assistant>`, `</assistant>`,
  `<commit_before>`, `<fim_prefix>`, …)
- `tokenizer_class: PreTrainedTokenizerFast`
- a `special_tokens_map.json`

Nothing to fix on your side.

**However**, the local MLX q8 conversion drops all of it — 0
`added_tokens_decoder`, no `additional_special_tokens`, no
`special_tokens_map.json`, and `tokenizer_class: TokenizersBackend`.

I initially took that as the cause of the control-token leakage. **It is not.**
The released `Mellum2-12B-A2.5B-{Instruct,Thinking}` MLX conversions have the
*same* stripped config and do not degenerate. So mlx-lm strips special-token
registration on every conversion, and it does not distinguish the well-behaved
models from the degenerate one. Possibly still worth flagging to mlx-lm, but it
is not the explanation here.

## What was wrong with my evaluation

| what I did | why it is wrong |
| --- | --- |
| `max_tokens=1500` | Far too small. Qwen uses **32k** for thinking-model evals. My "48% never close `</think>`" mostly measures my own cap. |
| **temperature 0** | Thinking checkpoints doom-loop at T=0; Qwen explicitly warn against it. My "44% repetition" is likely *induced by this setting*. |
| single greedy sample | Should be **T in [0.5, 1] with pass@k**. |
| no reasoning budget | The standard handling (as in vLLM) is a hard stop that injects a forced `</think>` when the thinking budget is hit. My harness had none, so an over-budget trace became "no answer". |

I also argued in the previous version that T=0 *ruled out* a sampling
pathology. That is backwards — T=0 is what induces the doom-loop. That
inference was simply wrong.

## What survives

Only one observation is independent of the above.

**PEP 750 knowledge is dated in this checkpoint.** Asked what `t'Hi {name}'`
evaluates to, step-200 describes "tagged template literals" with `.tag`,
`.parts`, `.values`, and calls the result a subclass of `str`. That vocabulary
comes from an **early draft of PEP 750 that was withdrawn** before acceptance;
the accepted API is `string.templatelib.Template` (not a `str`) with
`.strings`, `.values`, `.interpolations`.

The released 2.0 models do not reproduce that draft vocabulary — they
confabulate differently (`t_string` with `.value`/`.format_args`, or `prefix` /
`f-strings` / `values`). So if 2.1's corpus drew in more PEP-draft or
mailing-list era material, that may be visible elsewhere too.

This is a knowledge-content observation from a single greedy sample and is
worth re-checking at sane temperature before anyone acts on it.

## Partial re-test at a larger budget

Three tasks at `max_tokens=12000`, still T=0:

| task | tokens | closed `</think>` | hit cap |
| --- | --- | --- | --- |
| 0 | 12000 | yes | yes |
| 1 | 12000 | yes | yes |
| 2 | 12000 | no | yes |

So two of three *did* close the reasoning block at a larger budget, which
supports the budget explanation. All three still ran to the cap, but at T=0
that is expected behaviour rather than evidence of a defect.

## What a correct evaluation needs

1. `max_tokens` at 32k, matching the Qwen reference.
2. Temperature in [0.5, 1], sampled, **pass@k** rather than a single greedy
   sample.
3. A reasoning-budget mechanism that force-closes `</think>` when the thinking
   allowance is exhausted, as vLLM does.
4. Ideally the reference (non-MLX) runtime, to remove the conversion from the
   picture entirely.

Until those are in place there is no defensible claim here about the step-200
checkpoint's generation behaviour, and I would not report one.
