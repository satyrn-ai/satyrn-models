"""Structural skeletons and the measured diversity floor."""

import ast
import hashlib
import logging

from satyrn.tstrings.types import Task

logger = logging.getLogger(__name__)

UNPARSEABLE = "unparseable"


class _Skeletonizer(ast.NodeTransformer):
    """Normalize identifiers and constants to first-seen placeholders."""

    def __init__(self) -> None:
        self._names: dict[str, str] = {}
        self._values: dict[tuple[type, object], str] = {}

    def _name_placeholder(self, original: str) -> str:
        placeholder = self._names.get(original)
        if placeholder is None:
            placeholder = f"N{len(self._names)}"
            self._names[original] = placeholder
        return placeholder

    def _value_placeholder(self, value: object) -> str:
        key = (type(value), value)
        placeholder = self._values.get(key)
        if placeholder is None:
            placeholder = f"C{len(self._values)}"
            self._values[key] = placeholder
        return placeholder

    def visit_Name(self, node: ast.Name) -> ast.Name:
        """Rename an identifier reference to its placeholder."""
        node.id = self._name_placeholder(node.id)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """Rename a function definition name, then recurse."""
        node.name = self._name_placeholder(node.name)
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        """Rename an async function definition name, then recurse."""
        node.name = self._name_placeholder(node.name)
        return self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> ast.arg:
        """Rename a parameter name, then recurse."""
        node.arg = self._name_placeholder(node.arg)
        return self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        """Replace a literal value with its placeholder."""
        node.value = self._value_placeholder(node.value)
        return node


def skeleton(reference: str) -> str:
    """Return the sha256 of the reference's identifier- and literal-normalized AST."""
    try:
        tree = ast.parse(reference)
    except (SyntaxError, UnicodeDecodeError):
        logger.warning("reference failed to parse; using the unparseable sentinel")
        return UNPARSEABLE
    normalized = _Skeletonizer().visit(tree)
    return hashlib.sha256(ast.dump(normalized).encode()).hexdigest()


def distinct_skeleton_ratio(tasks: list[Task]) -> float:
    """Return the fraction of tasks with distinct structural skeletons."""
    if not tasks:
        return 0.0
    return len({skeleton(task.reference) for task in tasks}) / len(tasks)


def skeleton_floor(measured: float) -> float:
    """Return the diversity floor derived from a measured skeleton ratio."""
    return max(0.25, 0.75 * measured)
