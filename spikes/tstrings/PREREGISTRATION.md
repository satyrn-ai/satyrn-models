# Pre-registration, 2026-08-06

Two decisions recorded **before** the analyses they govern are run, because
this project has repeatedly produced results that moved when the instrument
changed, and the last headline was withdrawn after a scoring bug was found to
favour the arm we wanted to win.

Committed prior to rescoring or training. If the numbers below disagree with
what these rules produce, the rules stand.

---

## 1. The mixed-usage policy question

### The question

`TStringPolicy` rejects a candidate outright if it contains an f-string,
`.format()`, or `%`-formatting, whenever the reference used a t-string
(`src/satyrn_model/policies/tstring.py:64-78`). A program that builds and
consumes a genuine `Template` but *also* uses an f-string incidentally — for
example quoting one interpolation's value with `f"'{item.value}'"` — is
rejected.

### The decision: **lenient. Mixed usage passes.**

The policy rejects a candidate only when it **fails to construct a `Template`
where the reference constructs one**. Incidental old-form formatting elsewhere
in the program is not a failure.

### Why, and why this is not a preference

This is settled by the benchmark rather than by taste. Scoring the 100 `ood-v2`
**reference solutions** against our own policy:

> **4 of 100 gold answers are rejected** — `51826526` and `10a889bf` for an
> f-string, `220e6588` and `4f7c21f3` for `%`-formatting.

A gate that rejects the correct answer is not measuring correctness. Fifteen
references contain an f-string at all; four of those also build a `Template`,
which is the combination the rule punishes.

The check exists to stop a model scoring while *avoiding* the feature — that
was a live failure mode, with the bare model reaching 17/25 on a type-only
metric while using a t-string in zero tasks. Constructing and consuming a
`Template` is not avoiding the feature, so the narrow rule serves the purpose
and the broad one overshoots.

### What this does not change

The mechanism requirement stays: no `Template` where the reference builds one
is still a failure. The eight `t-string-not-f-string` tasks in the coverage
plan are unaffected, because there the reference's whole point is that the
parts must be reachable, and an f-string cannot produce them.

### Committed expectation

Every arm's score will rise, and the docs arms most, because that is where
mixed-usage rejects concentrate. **A rise in the docs arms is therefore not
evidence against the adapter**, and will not be reported as such. The
comparison of interest — adapter on top of docs — is expected to stay null.

---

## 2. The seed-variance measurement

### What will be run

Two further adapters on **`curriculum-repair-v2`** — the same curriculum as
Run A — under the identical recipe (28 layers, 3 epochs, peak LR 3e-5 with
warmup and cosine decay to 3e-6, batch 8), at **seeds 43 and 44**. Run A is
seed 42. Each is evaluated on `ood-v2` with and without `docs-v3`.

Curriculum is deliberately held fixed. The quantity being measured is how much
a score moves when *only* the training seed changes, which is the number every
adapter comparison in this project has lacked.

### The rule, fixed in advance

Let **s** be the spread in `solved` across seeds 42/43/44 for the `+docs`
adapter arms.

- The observed adapter-on-docs difference is **18 gained / 10 lost, +8 net,
  p = 0.185**.
- **If s ≥ 8**, seed noise alone covers the whole observed effect. The
  adapter-on-docs question is then unanswerable at n = 100 single-seed, and no
  further single-seed comparison will be reported as evidence either way.
- **If s < 8**, the effect is larger than seed noise but still not significant.
  The conclusion remains "not established", and the required next step is more
  seeds or a larger benchmark — not a re-run until it passes.

**Under no outcome does this measurement license claiming the adapter beats
documentation.** It can only tell us whether the question is worth pursuing at
this sample size. Registering that now so a favourable spread cannot be
reinterpreted later.

### Also fixed in advance

- Scoring is `spike/reverify.py` with the lenient policy from part 1, applied
  identically to all arms including the already-recorded ones.
- `base-docs` at **68/100** (post-bugfix) is the baseline. The pre-fix 61 is
  not used for anything.
- Execution is nondeterministic at roughly ±1 task, measured during
  re-verification. Differences of one or two tasks are noise regardless of what
  any test says.

---

## 3. Explanatory content in the corpus (registered 2026-08-06, before the data was built)

### The hypothesis

The corpus is 443 rows of task → code and contains **no description of the
API** — nothing stating what `Template` is, what `.strings` holds, or what
`.expression` returns. The documentation file is 708 words of exactly that.

The seed measurement says the difference shows up as *fragility*, not just
level: over seeds 42/43/44 on one curriculum and recipe,

- adapter alone: 54 / 58 / 48 — **spread 10**
- adapter + docs: 80 / 76 / 80 — **spread 4**

Documentation does not merely raise the score, it stabilises it. That is what
knowledge inferred from examples looks like versus knowledge stated outright:
each initialisation infers something slightly different.

**Hypothesis: adding explanatory rows reduces the seed-to-seed spread of the
adapter-alone arm.**

### What will be built

`curriculum-explained-v1` = the `repair-v2` rows plus explanatory question /
answer rows derived from `spike/pep750-docs-context-v3.md`, which is verbatim
PEP 750 plus a factual API summary. Target 15–20% of the curriculum.

Deliberately excluded: the canonical `render()` body that appears in the docs
file. Renderer over-exposure is a separate lever already isolated and measured
null; re-introducing copies of that block here would confound the two.

Every explanatory row whose answer contains code has that code **executed at
build time**, and rows whose assertions fail are dropped rather than shipped.
The stale `.expr`/`.conv` names in a project skill file — which a task author
caught and we did not — are the reason this is mechanical rather than reviewed
by eye.

### Metrics, fixed now

- **Primary: seed spread of the adapter-alone arm** over seeds 42/43/44.
  Baseline **10**. A fall toward 4 supports the hypothesis; no fall refutes it.
- **Secondary: adapter-alone mean.** Baseline **53.3**, against docs-alone 76.
  Movement toward 76 says the gap was explanatory content.
- **Explicitly not a metric: adapter + docs.** It sits at 78.7 against a
  baseline of 76, is unpowered, and is where a favourable reading would be
  easiest to manufacture. Registered now so it cannot be promoted later.

### Committed in advance

- Three seeds give a usable read on *spread* but will not give significance on
  small differences in *mean*. A mean that rises without the spread falling is
  a weaker result, and will be reported as one.
- If the spread does not fall, the hypothesis is wrong. The response is to say
  so, not to re-run with different row counts until it moves.
- These rows are **spike-only**. They do not enter the approved corpus and
  nothing is written to `patterns/approvals.jsonl`. Whether explanatory content
  belongs in the shipped corpus is a composition decision for its owners; this
  experiment only says whether it is worth deciding.

---

## 4. The Qwen transfer test (registered 2026-08-08, before running)

### Why this and not another Mellum experiment

Four consecutive corpus-*composition* experiments returned null — renderer
over-exposure, program-shape diversity, explanatory content, and the placebo
that showed three quarters of the last "effect" was unrelated to t-strings.
The one *training-side* change was significant (recipe, p = 0.0015). Composition
is not the lever, and further tuning on one model is not worth GPU time.

The deliverable is a **corpus**. Everything measured so far answers "does it
help this MLX quantization of Mellum". The shippability question is **does it
help a different model at all**, and it has never been run.

### What will be run

`curriculum-repair-v2` — the plain corpus, no explanatory rows, no placebo —
trained on **Qwen2.5-Coder-7B-Instruct-8bit** at 28 layers, 3 epochs, peak LR
3e-5 with warmup and cosine decay, batch 8, seeds 42/43/44. Evaluated on
`ood-v2` bare, +docs, adapter, adapter+docs. Scored by `reverify.py` with the
lenient policy.

Note the earlier Qwen adapters in this repo used **8 layers**, not 28. This is
a new configuration, so old Qwen numbers are not comparable and will not be
cited alongside these.

### The decision rule, fixed now

**Transfer is established if the adapter beats bare Qwen on a paired McNemar,
at every one of the three seeds.** Requiring all three rather than a mean
avoids the failure of the last round, where one seed at +16 carried a mean that
two other seeds did not support.

- If it holds: the corpus teaches a second base model, and is worth handing
  over at its current size.
- If it fails: the corpus is fitted to Mellum, and scaling it will not fix
  that. That outcome ends the training line rather than prompting another
  variant.

### Fixed in advance

- **Not a metric: adapter vs docs on Qwen.** Docs already beat the adapter on
  Mellum; re-litigating it on a second model measures nothing new and is where
  a favourable reading would be easiest to find.
- Mellum's numbers are not a baseline for Qwen's. Different base, different
  quantization, different pretraining cutoff.
- Bare Qwen may already know some PEP 750 — its pretraining is more recent than
  Mellum's on this feature. **If bare Qwen scores well, the transfer test is
  weakened, not strengthened**, because there is less to install. That will be
  reported as a limitation rather than as a good result.
