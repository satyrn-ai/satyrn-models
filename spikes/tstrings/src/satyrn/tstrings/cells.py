"""Cell table and deterministic operation analysis for mined seeds."""

import ast
from pathlib import Path

import tomllib

CELLS: tuple[tuple[str, str], ...] = (
    ("author", "construct"),
    ("consumer", "read_strings"),
    ("consumer", "read_values"),
    ("consumer", "read_interpolations"),
    ("consumer", "render"),
    ("consumer", "negative_control"),
)


def load_cells(toml_path: Path) -> dict[tuple[str, str], int]:
    """Read min_tasks per cell from a cells.toml file."""
    with toml_path.open("rb") as fh:
        data = tomllib.load(fh)
    cells: dict[tuple[str, str], int] = {}
    for role, ops in data.get("cells", {}).items():
        for operation, entry in ops.items():
            cells[(role, operation)] = int(entry["min_tasks"])
    return cells


def _in_annotation_context(tree: ast.Module, nodes: list[ast.AST]) -> bool:
    """Return True if any TemplateStr sits in a signature annotation/default."""
    parent = {}
    for node in nodes:
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    for node in nodes:
        if not isinstance(node, ast.TemplateStr):
            continue
        cur = node
        while cur in parent:
            cur = parent[cur]
            if isinstance(cur, (ast.arg, ast.AnnAssign)):
                return True
            if (
                isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef))
                and cur.returns
                and node in ast.walk(cur.returns)
            ):
                return True
    return False


def operations_of(seed_text: str) -> set[str]:
    """Return the operations a seed's text demonstrates, deterministically."""
    tree = ast.parse(seed_text)
    nodes = list(ast.walk(tree))
    if not any(isinstance(n, ast.TemplateStr) for n in nodes):
        return set()
    if _in_annotation_context(tree, nodes):
        return set()
    attrs = {n.attr for n in nodes if isinstance(n, ast.Attribute)}
    calls = {n.func.id for n in nodes if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    fstrings = [n for n in nodes if isinstance(n, ast.JoinedStr) and not isinstance(n, ast.TemplateStr)]

    ops: set[str] = {"construct"}
    if "interpolations" in attrs or "conversion" in attrs or "format_spec" in attrs:
        ops.add("read_interpolations")
    if "values" in attrs:
        ops.add("read_values")
    if "fstring" in calls or ("strings" in attrs and "values" in attrs):
        ops.add("render")
        ops.add("read_strings")
        ops.add("read_values")
    elif "strings" in attrs:
        ops.add("read_strings")
    if fstrings:
        ops.add("negative_control")
    return ops
