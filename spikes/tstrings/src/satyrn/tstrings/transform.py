"""Transform corpus rows into Michał's SFT format."""

import json
from pathlib import Path

import click

_SPIKE_ROOT = Path(__file__).resolve().parents[3]


def to_michal_sft(rows: list[dict], *, system_prompt: str | None = None) -> list[dict]:
    """Map converged rows to Michał's consumable SFT shape."""
    out = []
    for row in rows:
        prompt = []
        if system_prompt is not None:
            prompt.append({"role": "system", "content": system_prompt})
        prompt.append({"role": "user", "content": row["idea"]})
        out.append(
            {
                "prompt": prompt,
                "completion": [{"role": "assistant", "content": f"```python\n{row['code']}\n```"}],
                "filename": row["filename"],
                "python_version": row["python_version"],
                "idea": row["idea"],
                "code": row["code"],
                "trace": row["trace"],
                "expected_output": row["expected_output"],
            }
        )
    return out


@click.command("to-michal")
@click.option(
    "-i",
    "--input",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="corpus-sft directory or a rendered jsonl.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="JSONL file to write Michał-format rows into.",
)
@click.option("--system-prompt", is_flag=True, default=False, help="Prepend the deployment system prompt.")
def main(input: Path, output: Path, system_prompt: bool) -> None:
    """Transform corpus rows into Michał's SFT format."""
    if input.is_dir():
        rows = [
            json.loads(line)
            for name in ("train.jsonl", "valid.jsonl")
            for line in (input / name).read_text().splitlines()
            if line.strip()
        ]
    else:
        rows = [json.loads(line) for line in input.read_text().splitlines() if line.strip()]

    prompt = (_SPIKE_ROOT / "benchmark" / "system-prompt.txt").read_text().strip() if system_prompt else None
    transformed = to_michal_sft(rows, system_prompt=prompt)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(json.dumps(row) for row in transformed) + "\n")
    click.echo(f"Wrote {len(transformed)} rows to {output}")
