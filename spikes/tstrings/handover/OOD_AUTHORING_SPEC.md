# Authoring spec: PEP 750 t-string evaluation tasks

Hand this to an authoring agent working **in a fresh directory with no access to
the repository that will consume the output**. Independence is the point: these
tasks exist to measure whether a model generalises beyond the distribution it
was trained on, and that measurement is void if the author has seen the training
corpus, the existing benchmarks, or the failure modes observed so far.

---

## What you are producing

**100 self-contained Python programming tasks** exercising PEP 750 template
strings (Python 3.14, `string.templatelib`), as a JSONL file — one task per
line.

Each task is a prompt, a reference solution, and the name of the variable
holding the answer. A model will be given the prompt alone and scored on
whether its program produces an answer equivalent to the reference's.

## Rule 1 — every task must be solvable from its prompt alone

This is the requirement that matters most, and the one most easily missed.

**A competent Python programmer who has never seen your reference solution must
be able to produce the expected answer from the prompt text alone.**

Concretely, if your reference contains any of these, the prompt must state it
verbatim:

- the template literal's text, including its static parts
- every input value the program binds
- any marker, separator, prefix or placeholder string the answer contains
- the exact name of the variable that holds the answer

A worked example of the failure. This prompt is **invalid**:

> Build the greeting text a notification service should send, using the
> customer's name. Put it in `greeting`.

...against a reference of `t"Welcome, {name}!"` with `name = "Ari"`. Nothing
tells the solver that the wording is *"Welcome, "*, that it ends in an
exclamation mark, or that the name is *"Ari"*. A perfect solution scores zero
for guessing *"Hello, Ari!"*.

The **valid** form states them:

> Given `name = "Ari"`, build a template string whose text is
> `Welcome, {name}!` and render it to a plain string. Assign the rendered
> string to `greeting`.

You may phrase this any way you like — a table, prose, a code block of
bindings — as long as the information is present. Vary the presentation across
tasks; do not adopt one fixed preamble for all 100.

## Rule 2 — the answer must be checkable by properties, not just equality

Each task will be scored on:

- **type** — the answer's type matches the reference's answer type
- **literals** — the literals your prompt states appear in the answer
- **mechanism** — the program actually constructs a `Template`

So: prefer answers whose type is meaningful (`str`, `tuple`, `dict`), and make
the stated literals genuinely load-bearing in the output. Avoid answers that are
a bare `True`/`False` or a single integer, which almost any program hits by
accident.

## Output schema

One JSON object per line, these five keys, no others:

```json
{
  "prompt": "…the complete, self-contained task statement…",
  "reference": "…a complete Python 3.14 program…",
  "answer_variable": "greeting",
  "domain": "html",
  "notes": "…what this task probes, one line, for human review only…"
}
```

- `reference` must be a **complete, runnable, standalone program**: all imports,
  all inputs bound, no functions left undefined, no I/O, no network, no clock or
  randomness. Running it must bind `answer_variable` at module level.
- `domain` is a free short label (`sql`, `html`, `logging`, `shell`, `csv`,
  `text`, `config`, …). Aim for breadth; do not let one domain exceed ~20% of
  tasks.

## Coverage

Spread the 100 tasks across the public surface of the feature. Roughly equal
weight, and at least four tasks per bullet:

- `Template.strings` — the static parts
- `Template.values` — the interpolated values
- `Template.interpolations` — and the fields of each `Interpolation`:
  `.value`, `.expression`, `.conversion`, `.format_spec`
- iterating a `Template`, which yields `str` and `Interpolation` in order
- rendering a template to a string, including honouring `format_spec` and
  applying `conversion` via `string.templatelib.convert`
- **evaluation timing** — interpolations are evaluated when the template literal
  is written, not when it is later read or rendered
- composing or nesting templates
- transforming interpolations before rendering (escaping, quoting, redacting,
  substituting placeholders)
- returning something other than a rendered string — a `tuple`, a `dict`, a
  parameterised query, a structured record
- cases where a t-string must **not** be replaced by an f-string, because the
  program needs access to the parts

Include a difficulty spread: roughly 30 straightforward, 50 moderate, 20 that
require combining two of the above.

## Style constraints

- Write prompts in natural, varied language. Do not converge on one sentence
  pattern, one instruction verb, or one way of presenting inputs.
- Use a **different answer variable name per task**, chosen to fit the task
  (`greeting`, `statement`, `redacted_line`, `manifest`, …). Never reuse one
  generic name throughout.
- Do not mention this specification, the scoring, or that the task is a
  benchmark item, anywhere in a prompt.
- Do not include the reference solution, or fragments of it, in the prompt
  beyond the literals Rule 1 requires.

## Self-check — run this before delivering

Every task must pass. This is exactly the check whose absence invalidated a
previous task set, so do not skip it or hand-wave the result.

```python
import ast, json, sys

failures = []
for index, line in enumerate(open("tasks.jsonl", encoding="utf-8")):
    if not line.strip():
        continue
    task = json.loads(line)
    prompt, reference = task["prompt"], task["reference"]
    name = task["answer_variable"]

    # 1. the reference runs and binds the answer
    namespace = {"__name__": "__main__"}
    try:
        exec(compile(reference, "<reference>", "exec"), namespace)
    except Exception as exc:
        failures.append((index, f"reference raised {type(exc).__name__}: {exc}"))
        continue
    if name not in namespace:
        failures.append((index, f"reference never bound {name!r}"))
        continue

    # 2. the prompt names the answer variable
    if name not in prompt:
        failures.append((index, f"prompt does not name {name!r}"))

    # 3. THE IMPORTANT ONE: every string literal the reference relies on is
    #    stated in the prompt
    tree = ast.parse(reference)
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and len(node.value.strip()) > 1
    }
    for node in ast.walk(tree):          # static parts of t-strings too
        if isinstance(node, ast.TemplateStr):
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    if len(part.value.strip()) > 1:
                        literals.add(part.value)
    absent = sorted(x for x in literals if x not in prompt)
    if absent:
        failures.append((index, f"literals absent from prompt: {absent[:4]}"))

    # 4. the reference exercises the feature -- either a t-string literal, or
    #    templatelib types constructed by hand, which is a legitimate task shape
    uses_literal = any(isinstance(n, ast.TemplateStr) for n in ast.walk(tree))
    uses_api = any(
        isinstance(n, ast.ImportFrom) and n.module == "string.templatelib"
        for n in ast.walk(tree)
    )
    if not (uses_literal or uses_api):
        failures.append((index, "reference does not use t-strings or templatelib"))

for index, why in failures:
    print(f"task {index}: {why}")
print(f"\n{len(failures)} failing / {index + 1} tasks")
sys.exit(1 if failures else 0)
```

If check 3 fires, **fix the prompt, not the check.** Its whole purpose is to
catch the "solvable only by guessing" defect, and a literal that is genuinely
incidental is rare enough to be worth justifying in `notes` rather than
suppressing.

## Deliverable

- `tasks.jsonl` — 100 lines
- the self-check output, showing zero failures
- a short note on how you distributed coverage and difficulty

Do not tune the tasks against any model. If you try one and it does well or
badly, that is not a reason to change the task.
