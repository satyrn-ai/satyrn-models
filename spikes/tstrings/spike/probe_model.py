"""Measure generation health, separately from task accuracy.

The GRPO preview snapshot of Mellum2 scored 0/25 on `ood-v1`, but that number
was not a capability measurement: 48% of generations opened ``<think>`` and
never closed it, and 44% degenerated into repetition with ``<|im_end|>`` and
``</tool_call>`` emitted as literal text. Roughly half the trials failed before
the model could be right or wrong.

A score is only interpretable once generation terminates reliably, so this
measures that directly — clean-stop rate, unterminated reasoning traces,
control-token leakage and repetition — and keeps it out of the accuracy path.
It also runs a short knowledge probe, because a model can terminate perfectly
and still hold a stale view of the API.

Run against any MLX-loadable model; `--tasks` accepts any benchmark JSONL.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CONTROL_TOKENS = ("<|im_end|>", "<|endoftext|>", "</tool_call>", "<|im_start|>")

KNOWLEDGE_PROBE = (
    "In Python 3.14 (PEP 750), what type does a t-string literal like "
    "t'Hi {name}' evaluate to, and what are its public attributes? "
    "Answer in two sentences. Do not write code."
)

# Claims that indicate the withdrawn tagged-template draft rather than the
# accepted PEP. `.values` is correct and deliberately absent.
STALE_MARKERS = (
    ".tag",
    ".parts",
    "tagged template",
    "subclass of str",
    "subclass of `str`",
)
CORRECT_MARKERS = (".strings", ".interpolations", "Template", "templatelib")


def looks_repetitive(text: str, window: int = 60, repeats: int = 3) -> bool:
    """True when the tail repeats a short block several times over."""
    tail = text[-window * (repeats + 1) :]
    for size in range(8, window):
        block = tail[-size:]
        if block.strip() and tail.count(block) >= repeats:
            return True
    return False


def answer_of(text: str) -> str:
    """Whatever follows the reasoning trace, which is the only scoreable part."""
    if "</think>" in text:
        return text.split("</think>", 1)[1]
    return "" if "<think>" in text else text


def health(text: str, token_count: int, max_tokens: int) -> dict:
    opened = "<think>" in text
    answer = answer_of(text)
    return {
        "hit_token_cap": token_count >= max_tokens,
        "unterminated_think": opened and "</think>" not in text,
        # The question the GRPO re-probe has to answer is not "did generation
        # stop tidily" but "was there an answer to grade at all". Under a
        # forced close the trace is cut deliberately, so `clean_stop_rate`
        # counts it as unclean while the run is still perfectly scoreable.
        "answered": bool(answer.strip()),
        "control_leak": sum(text.count(t) for t in CONTROL_TOKENS),
        "repetitive": looks_repetitive(text),
        "chars": len(text),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--tasks", type=Path, default=Path("benchmark/ood-v1/tasks.jsonl")
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--max-tokens", type=int, default=1500)
    parser.add_argument(
        "--thinking-budget",
        type=int,
        help="Tokens allowed for reasoning before `--force-close-think` cuts "
        "in. Defaults to the whole of --max-tokens.",
    )
    parser.add_argument(
        "--force-close-think",
        action="store_true",
        help="Inject `</think>` when the reasoning budget runs out and let the "
        "answer follow, as vLLM's thinking-token-budget does.",
    )
    parser.add_argument(
        "--close-answer-tokens",
        type=int,
        default=512,
        help="Answer budget guaranteed after a forced `</think>`.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="The Mellum 2 report evaluates at 0.0 with greedy decoding; its "
        "one exception is LiveCodeBench at 0.2.",
    )
    parser.add_argument("--tag", required=True)
    parser.add_argument("--out", type=Path, default=Path("results/probes"))
    args = parser.parse_args()

    from mlx_lm import generate, load
    from mlx_lm.sample_utils import make_sampler

    model, tokenizer = load(args.model)
    sampler = make_sampler(temp=args.temperature)

    def run(prompt: str) -> tuple[str, int]:
        text = tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            tokenize=False,
            add_generation_prompt=True,
        )
        budget = args.thinking_budget or args.max_tokens
        out = generate(
            model, tokenizer, prompt=text, max_tokens=budget, sampler=sampler
        )
        # A thinking model that spends its whole budget reasoning has not
        # failed — it has run out of room. Treating that as an unterminated
        # trace is what made 48% of the earlier run unscoreable, and it scored
        # the harness rather than the model. vLLM's `thinking-token-budget`
        # closes the trace and lets the answer follow; do the same, and only
        # then judge what comes out.
        forced = False
        if args.force_close_think and "<think>" in out and "</think>" not in out:
            forced = True
            remaining = max(args.max_tokens - budget, args.close_answer_tokens)
            out += "\n</think>\n"
            out += generate(
                model,
                tokenizer,
                prompt=text + out,
                max_tokens=remaining,
                sampler=sampler,
            )
        return out, len(tokenizer.encode(out)), forced

    knowledge, _, _ = run(KNOWLEDGE_PROBE)
    lowered = knowledge.lower()
    report: dict = {
        "tag": args.tag,
        "model": args.model,
        "max_tokens": args.max_tokens,
        "thinking_budget": args.thinking_budget,
        "force_close_think": args.force_close_think,
        "temperature": args.temperature,
        "knowledge_probe": {
            "answer": knowledge.strip()[:1500],
            "stale_markers": [m for m in STALE_MARKERS if m.lower() in lowered],
            "correct_markers": [m for m in CORRECT_MARKERS if m.lower() in lowered],
        },
    }

    tasks = [json.loads(line) for line in args.tasks.read_text().splitlines() if line]
    tasks = tasks[: args.limit]
    rows = []
    for task in tasks:
        text, count, forced = run(task["prompt"])
        rows.append(health(text, count, args.max_tokens) | {"forced_close": forced})

    total = len(rows) or 1
    report["generation_health"] = {
        "n": len(rows),
        "clean_stop_rate": round(
            sum(
                1
                for r in rows
                if not r["hit_token_cap"]
                and not r["unterminated_think"]
                and not r["repetitive"]
            )
            / total,
            3,
        ),
        # The headline for a thinking checkpoint: 48% of the retracted run
        # produced nothing gradeable, which is why its 0/25 was not a
        # capability measurement.
        "answered_rate": round(sum(r["answered"] for r in rows) / total, 3),
        "forced_close": sum(r["forced_close"] for r in rows),
        "hit_token_cap": sum(r["hit_token_cap"] for r in rows),
        "unterminated_think": sum(r["unterminated_think"] for r in rows),
        "repetitive": sum(r["repetitive"] for r in rows),
        "any_control_leak": sum(1 for r in rows if r["control_leak"] > 0),
        "mean_chars": round(sum(r["chars"] for r in rows) / total),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"probe-{args.tag}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["generation_health"], indent=2))
    print("stale markers:", report["knowledge_probe"]["stale_markers"])
    print("correct markers:", report["knowledge_probe"]["correct_markers"])
    print(f"wrote {path}")


if __name__ == "__main__":
    sys.exit(main())
