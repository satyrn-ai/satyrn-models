"""Evaluate the fine-tuned model: generate code from prompts and validate it.

Usage:
  python eval.py                              # run built-in eval prompts
  python eval.py --prompt "... your prompt"   # single ad-hoc prompt
  python eval.py --num-prompts 20             # sample N random combinations
"""

import argparse
import sys
import textwrap

# ---------------------------------------------------------------------------
# Python 3.14 compat shim for `datasets` (same as main.py)
# ---------------------------------------------------------------------------
import dill
import datasets.utils._dill as _hf_dill


def _patched_batch_setitems(self, items, obj=None):
    if getattr(self, "_legacy_no_dict_keys_sorting", False):
        return dill.Pickler._batch_setitems(self, items, obj)
    try:
        items = sorted(items)
    except Exception:
        from datasets.fingerprint import Hasher

        items = sorted(items, key=lambda x: Hasher.hash(x[0]))
    return dill.Pickler._batch_setitems(self, items, obj)


_hf_dill.Pickler._batch_setitems = _patched_batch_setitems
# ---------------------------------------------------------------------------

from unsloth import FastLanguageModel
from make_data import validate_snippet

ADAPTER_DIR = "./qwen2.5-coder-pep750"

# ── built-in eval prompts ────────────────────────────────────────────
# Each is a (label, prompt) pair.  The prompt is fed as-is; the model
# completion is exec'd and checked for errors.
# ---------------------------------------------------------------------
EVAL_PROMPTS: list[tuple[str, str]] = [
    (
        "greet with reusable template",
        "# Python 3.14 t-strings: greet a user by name with a reusable template\n",
    ),
    (
        "parameterized SQL query",
        "# Python 3.14 t-strings: build a parameterized SQL query from a template\n",
    ),
    (
        "HTML escaping",
        "# Python 3.14 t-strings: render HTML with automatic escaping of interpolated values\n",
    ),
    (
        "custom renderer uppercases interpolations",
        "# Python 3.14 t-strings: write a custom renderer that uppercases interpolations\n",
    ),
    (
        "structural pattern matching on interpolations",
        "# Python 3.14 t-strings: match interpolations by value type with structural pattern matching\n",
    ),
    (
        "debug syntax with equals",
        "# Python 3.14 t-strings: use the name= debug syntax in a template\n",
    ),
    (
        "raw template string",
        "# Python 3.14 t-strings: use a raw template string to keep backslashes literal\n",
    ),
    (
        "concatenate two templates",
        "# Python 3.14 t-strings: concatenate two templates with +\n",
    ),
    (
        "inspect template structure",
        "# Python 3.14 t-strings: inspect the structure of a template including strings and interpolations\n",
    ),
    (
        "return reusable template from function",
        "# Python 3.14 t-strings: return a reusable template from a function\n",
    ),
]


def load_model():
    """Load the base model with the fine-tuned LoRA adapter.

    Passing the adapter directory as model_name lets unsloth auto-detect
    adapter_config.json, load the base model, and apply the LoRA weights.
    """
    print(f"Loading model from {ADAPTER_DIR} ...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=ADAPTER_DIR,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=False,
    )
    return model, tokenizer


def generate(model, tokenizer, prompt: str, max_tokens: int = 256) -> str:
    """Run inference and return the decoded completion."""
    output = model.generate(prompt, max_new_tokens=max_tokens)
    return tokenizer.decode(output[0], skip_special_tokens=True)


def strip_prompt(completion: str, prompt: str) -> str:
    """Remove the prompt prefix from a completion, return just the generated code."""
    if completion.startswith(prompt):
        return completion[len(prompt):]
    return completion


def extract_code(text: str) -> str:
    """Extract Python code from generated text that may contain markdown fences
    and explanatory prose.  Returns the longest contiguous code block found.
    """
    import re

    # Prefer ```python fences if present
    pattern = r"```python\s*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        # Return the longest match (most likely the actual code)
        return max(matches, key=len).strip()

    # If no fences, try to strip leading/trailing non-code lines
    # (heuristic: keep lines that don't look like prose)
    lines = text.strip().split("\n")
    # Drop leading lines that are markdown headers, bullet points, or prose
    while lines and (
        lines[0].startswith(("#", "-", "*", ">", "`"))
        or lines[0].startswith("I'm")
        or lines[0].startswith("You")
        or lines[0].startswith("Here")
        or not any(c in lines[0] for c in "=:().\\")
        and len(lines[0].split()) > 10
    ):
        lines.pop(0)
    # Drop trailing non-code lines
    while lines and (
        lines[-1].startswith(("#", "-", "*", ">", "`"))
        or "---" in lines[-1]
        or not any(c in lines[-1] for c in "=:().\\")
        and len(lines[-1].split()) > 10
    ):
        lines.pop()
    return "\n".join(lines).strip()


def main():
    parser = argparse.ArgumentParser(description="Evaluate the fine-tuned PEP 750 model")
    parser.add_argument(
        "-p", "--prompt",
        type=str,
        default=None,
        help="Single ad-hoc prompt to evaluate.",
    )
    parser.add_argument(
        "-n", "--num-prompts",
        type=int,
        default=0,
        help="Number of built-in prompts to evaluate (default: all).",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip validation — just print generated code.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=256,
        help="Max tokens to generate (default: 256).",
    )
    args = parser.parse_args()

    model, tokenizer = load_model()

    def generate_and_validate(prompt: str, label: str) -> tuple[str, bool, str]:
        """Generate, extract code, and validate. Returns (raw, passed, error)."""
        completion = generate(model, tokenizer, prompt, args.max_tokens)
        raw = strip_prompt(completion, prompt)
        code = extract_code(raw)
        if args.no_validate:
            return raw, True, ""
        ok, err = validate_snippet(code, label)
        return raw, ok, err

    # ── single ad-hoc prompt ─────────────────────────────────────────
    if args.prompt:
        raw, ok, err = generate_and_validate(args.prompt, "ad-hoc")
        print("=" * 60)
        print("RAW GENERATED:")
        print(raw)
        if code := extract_code(raw):
            if code != raw:
                print("=" * 60)
                print("EXTRACTED CODE:")
                print(code)
        print("=" * 60)
        if not args.no_validate:
            if ok:
                print("✓  VALIDATION: passed")
            else:
                print(f"✗  VALIDATION: {err}")
        return

    # ── built-in eval prompts ────────────────────────────────────────
    prompts = EVAL_PROMPTS[:args.num_prompts] if args.num_prompts else EVAL_PROMPTS
    passed = 0
    for label, prompt in prompts:
        raw, ok, err = generate_and_validate(prompt, label)
        print(f"\n{'─' * 60}")
        print(f"PROMPT:  {label}")
        print(f"{'─' * 60}")
        code = extract_code(raw)
        if code:
            print(textwrap.indent(code, "  "))
        else:
            print(textwrap.indent(raw[:200], "  "))
        if not args.no_validate:
            if ok:
                print(f"  ✓  VALIDATION: passed")
                passed += 1
            else:
                print(f"  ✗  VALIDATION: {err}")

    if not args.no_validate:
        print(f"\n{'=' * 60}")
        print(f"PASSED: {passed}/{len(prompts)}")


if __name__ == "__main__":
    main()
