"""Mine t-string usages from pinned source."""

import ast
import json
import logging
import subprocess
from dataclasses import asdict
from pathlib import Path

import click

from satyrn.tstrings.types import Seed, SourceSpec, load_source_specs

logger = logging.getLogger(__name__)

SOURCES_TOML = Path(__file__).resolve().parents[3] / "sources.toml"


def _enclosing_unit(parent: dict[ast.AST, ast.AST], node: ast.AST) -> ast.AST:
    """Return the nearest enclosing function, else the nearest enclosing statement."""
    cur = node
    while cur in parent:
        cur = parent[cur]
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur
    cur = node
    while cur in parent:
        cur = parent[cur]
        if isinstance(cur, ast.stmt):
            return cur
    raise AssertionError("unreachable: a TemplateStr is always inside a statement")


def mine_seeds(source_root: Path, spec: SourceSpec) -> list[Seed]:
    """Return one Seed per enclosing unit that contains a TemplateStr."""
    seeds: list[Seed] = []
    seen: set[tuple[str, int]] = set()
    for base in spec.paths:
        search_root = source_root / base
        for path in sorted(search_root.rglob("*.py")):
            if any(part.startswith(".") for part in path.relative_to(search_root).parts):
                continue
            try:
                source = path.read_text()
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError) as error:
                logger.warning("Skipping unparseable file %s: %s", path, error)
                continue
            parent: dict[ast.AST, ast.AST] = {}
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    parent[child] = node
            for node in ast.walk(tree):
                if not isinstance(node, ast.TemplateStr):
                    continue
                unit = _enclosing_unit(parent, node)
                key = (str(path), unit.lineno)
                if key in seen:
                    continue
                seen.add(key)
                text = ast.get_source_segment(source, unit)
                if text is None:
                    logger.warning("No source segment for %s:%d", path, unit.lineno)
                    continue
                seeds.append(
                    Seed(
                        text=text,
                        source_id=spec.id,
                        path=str(path.relative_to(source_root)),
                        line=unit.lineno,
                    )
                )
    return seeds


def verify_checkout(source_root: Path, spec: SourceSpec) -> None:
    """Raise a ClickException if source_root's HEAD does not match spec.commit."""
    result = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise click.ClickException(f"{source_root} is not a git checkout")
    head = result.stdout.strip()
    if head != spec.commit:
        raise click.ClickException(f"checkout {source_root} is at {head}, expected {spec.commit} ({spec.tag})")
    status = subprocess.run(
        ["git", "-C", str(source_root), "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
        raise click.ClickException(f"checkout {source_root} is dirty")


@click.command("mine")
@click.option(
    "-i",
    "--input",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Parent dir of per-source checkouts (each <source_id>/ verified + mined).",
)
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default="seeds",
    show_default=True,
    help="Directory to write mined seeds into.",
)
def main(input: Path, output_dir: Path) -> None:
    """Mine t-string usages from pinned source."""
    try:
        specs = load_source_specs(SOURCES_TOML)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    all_seeds: list[Seed] = []
    for spec in specs:
        source_root = input / spec.id
        if not source_root.is_dir():
            raise click.ClickException(f"checkout missing for source {spec.id}: {source_root}")
        verify_checkout(source_root, spec)
        seeds = mine_seeds(source_root, spec)
        if not seeds:
            raise click.ClickException(f"no seeds mined from {spec.id}; check paths={spec.paths}")
        all_seeds.extend(seeds)
        click.echo(f"{spec.id}: {len(seeds)} seeds")
    output_path = output_dir / "mined.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as fh:
        for seed in all_seeds:
            fh.write(json.dumps(asdict(seed)) + "\n")
    click.echo(f"Wrote {len(all_seeds)} seeds to {output_path}")
