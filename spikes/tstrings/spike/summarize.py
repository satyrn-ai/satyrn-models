"""Spike: aggregate eval runs into a summary table."""

import json
from pathlib import Path

RUNS = [
    ("base-7b-instruct", "base", "bench", "mlx-community/Qwen2.5-Coder-7B-Instruct-8bit"),
    ("prior-tuned", "prior-tuned (melly2)", "bench", "omlx"),
    ("v1-newbench", "v1 corpus-only", "bench", "adapters/tstring-v1"),
    ("v2-bench", "v2 +values/+str", "bench", "adapters/tstring-v2"),
    ("v3-bench", "v3 curated", "bench", "adapters/tstring-v3"),
    ("v3-eval2", "v3 curated", "eval2", "adapters/tstring-v3"),
    ("v1-probe", "v1 corpus-only", "probe", "adapters/tstring-v1"),
    ("v2-probe", "v2 +values/+str", "probe", "adapters/tstring-v2"),
    ("v3-probe", "v3 curated", "probe", "adapters/tstring-v3"),
    ("v4-bench", "v4 +join/xstr", "bench", "adapters/tstring-v4"),
    ("v4-probe", "v4 +join/xstr", "probe", "adapters/tstring-v4"),
    ("v4-eval2", "v4 +join/xstr", "eval2", "adapters/tstring-v4"),
    ("v5-bench", "v5 rebalanced", "bench", "adapters/tstring-v5"),
    ("v5-probe", "v5 rebalanced", "probe", "adapters/tstring-v5"),
    ("v5-eval2", "v5 rebalanced", "eval2", "adapters/tstring-v5"),
    ("v5-honestrender", "v5 honest-render", "bench*", "adapters/tstring-v5"),
]

results_dir = Path("results")
rows = []
for tag, label, bench, _model in RUNS:
    path = results_dir / f"eval-{tag}.json"
    if not path.exists():
        continue
    data = json.loads(path.read_text())
    s = data["summary"]
    rows.append(
        f"| {label} | {bench} | {s['passed']}/{s['total']} ({s['score']:.0%}) | "
        f"{', '.join(f'{k}:{v}' for k, v in s['failure_stages'].items())} |"
    )

out = [
    "# Spike results",
    "",
    "30-task benchmark (7 categories), 12-task generalization probe, "
    "15-task fresh eval2 (authored before v4).",
    "",
    "NOTE: bench* = benchmark with corrected real-render references (the",
    "pre-correction bench measured str(template) = Template repr, not",
    "rendering — see REPORT.md). Genuine stdlib-op subset: 15/17 (88%).",
    "",
    "| Model | Eval | Score | Failure stages |",
    "|---|---|---|---|",
    *rows,
    "",
]
(Path("results/summary.md")).write_text("\n".join(out))
print("\n".join(out))
