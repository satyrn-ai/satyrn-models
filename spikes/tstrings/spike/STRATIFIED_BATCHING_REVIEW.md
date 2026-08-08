# Stratified batching review

**Run:** semantic bridge, deployment-aligned system prompt, seed 42, 57
updates, operation-stratified batches.

**Result:** 36/100 (23/70 consumer, 13/30 author). This does not clear the
promotion gate or justify a three-seed ladder.

## What the result establishes

- System-prompt alignment remains necessary: this run had no policy failures.
- Operation-stratified batching changed behavior, but did not create broad,
  reliable capability. Against the unstratified semantic bridge (40/100), it
  gained three advanced rendering tasks and lost seven author-static-parts
  tasks. The paired 3-gain/7-loss change is too small for a score claim.
- It improved `.strings` intent routing without producing executable code. All
  ten answers used the correct `template.strings` result, but imported the
  nonexistent `StaticPart`, producing `ImportError`.
- The model can emit the canonical typed renderer for a few prompts, but it
  does not select it reliably. Basic rendering used `"".join(template)`;
  author renderer tasks returned only the first static string.
- Only direct values, composition, and author values were fully reliable.
  Strict task accuracy therefore overstates practical breadth because each
  benchmark family has near-identical constant variants.
- The adapter ties the PEP-documentation baseline at 36/100 but does not
  dominate it. Documentation retains interpolation-field capability; the
  adapter gains values and a few advanced-rendering tasks.

## What is broken

### Curriculum accounting

Global role and operation totals hide the cells that matter. In the actual
450-row training split there are 7 consumer `.strings` rows versus 44 author
`.strings` rows, 13 consumer `.values` rows versus 41 author values rows, and
15 consumer rendering rows versus 37 author rendering rows. Operation-only
batching cannot fix this mismatch.

The curriculum also lacks direct benchmark-aligned coverage for interpolation
field extraction and does not sufficiently contrast static inspection,
joining static text, and full rendering.

### API-surface knowledge

Failures are concentrated rather than random: 17 import errors, 13 attribute
errors, and 12 type errors. The model hallucinates `StaticPart`, an importable
`static_parts`, `Template.render`, `Template.specs`, and `.static_parts`.
These need explicit valid/invalid API contrasts.

### Batching experiment

The custom trainer guarantees eight distinct *operations*, not distinct
role×operation×prompt-family cells. It therefore mixes incompatible author
and consumer goals inside the same coarse operation.

Further, 450 rows at batch size 8 gives 56 complete batches. Update 57 is the
first batch of a second epoch, while two rows are omitted from each complete
epoch. The final update was six PEP-framed examples out of eight, including
author strings, values, and static joining. This makes the observed mode
especially sensitive to final-batch composition. The standard and custom
trainers omit different rows, so this was not an ordering-only comparison.

### Measurement

The benchmark assigns framing by the same repeating index used to construct
operations. Consequently, each repeated operation family has a fixed prompt
framing. For example, all direct `.strings` tasks share one framing and all
basic renderers share another. The three advanced-rendering passes shared the
third framing. Operation scores therefore partly measure wording response.

Teacher-forced validation loss (0.005) is not a generalization signal here:
validation rows are close variants of training records, while the benchmark
requires free generation under different wording.

## Required repair sequence

1. Preserve the existing benchmark as historical evidence; create a fresh,
   independently reviewed benchmark that balances role × capability × prompt
   framing with fresh constants.
2. Make the trainer consume every row exactly once per epoch, use 56
   epoch-aligned updates (or pad the remainder), record row IDs for every
   batch, and save intermediate checkpoints for generated evaluation.
3. Select exact curriculum cells for consumer and author capabilities,
   including each interpolation field, `.strings`, `.values`, static joining,
   basic/dynamic/conversion rendering, composition, and all three typed
   template-function families.
4. Add paired contrasts that explicitly require: return the tuple; join only
   static strings; or fully render. Include valid API examples and negative
   examples for the observed hallucinated APIs.
5. Replace per-batch operation uniqueness with deterministic interleaving over
   role × capability × prompt-family windows. Compare it with ordinary
   shuffling only after data and measurement are repaired.
6. Run one seed first. Promote to three seeds only if one adapter
   simultaneously passes direct `.strings`, direct `.values`, composition,
   basic rendering, and all three typed authoring families.

## Model cache note

The run uses `mlx-community/Qwen2.5-Coder-7B-Instruct-8bit`, not the
unquantized `Qwen/Qwen2.5-Coder-7B` cache. The latter was moved to Trash on
2026-08-04; it was not required by current adapters or spike runs.
