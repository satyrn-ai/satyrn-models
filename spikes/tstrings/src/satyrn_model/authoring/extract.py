"""Safe AST extraction: find t-string literals in source code without importing
the source module.

The extractor never imports source modules. It operates on parsed AST and
emits ``SourceExerciseCandidate`` records after passing safety gates.
"""

from __future__ import annotations

import ast
import dataclasses

from .models import (
    Introspect,
    LocalCheckIntent,
    PolicyIntent,
    SourceEvidence,
    SourceExerciseCandidate,
    SourceOrigin,
    TaskIntent,
)

__all__ = [
    "ExtractionRejection",
    "ExtractionResult",
    "ScopeShadowingError",
    "TemplateLiteral",
    "extract_candidates",
    "find_template_literals",
]


class ScopeShadowingError(ValueError):
    """A free name in a t-string literal is shadowed by a local scope."""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class TemplateLiteral:
    """A t-string literal extracted from source code."""

    literal: str  # exact source text
    line: int
    col: int
    free_names: tuple[str, ...]


@dataclasses.dataclass
class ExtractionRejection:
    """A source fragment that was not converted to a candidate."""

    reason: str
    line: int


@dataclasses.dataclass
class ExtractionResult:
    """Candidates and rejections from one source file."""

    candidates: list[SourceExerciseCandidate]
    rejections: list[ExtractionRejection] = dataclasses.field(default_factory=list)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def extract_candidates(source: str) -> ExtractionResult:
    """Extract ``SourceExerciseCandidate`` records from *source*.

    The harvest unit is an assertion block, not an entire test method.  A
    method with multiple independent assertions produces one candidate per
    assertion.
    """
    tree = ast.parse(source)
    result = ExtractionResult(candidates=[], rejections=[])

    funcs_found = False
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _extract_from_function(node, source, result)
            funcs_found = True

    if not funcs_found:
        # Module-level code: check for loops, then process assertions directly.
        if _has_loop_or_subtest(tree):
            result.rejections.append(
                ExtractionRejection(reason="loop or subTest at module level", line=1)
            )

    return result


def _extract_from_function(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    source: str,
    result: ExtractionResult,
) -> None:
    """Extract candidates from one function body."""
    evidence = SourceEvidence(
        function_name=func.name,
        docstring=ast.get_docstring(func),
    )

    # Reject loops/subtests: can't safely decompose generated cases.
    if _has_loop_or_subtest(func):
        result.rejections.append(
            ExtractionRejection(
                reason=f"loop or subTest at {func.name}:{func.lineno}",
                line=func.lineno,
            )
        )
        return

    # Reject private helper calls.
    if _calls_private_helper(func):
        result.rejections.append(
            ExtractionRejection(
                reason=f"private assert helper in {func.name}",
                line=func.lineno,
            )
        )
        return

    if not evidence.docstring:
        assert_count = sum(1 for s in func.body if isinstance(s, ast.Assert))
        if assert_count <= 1:
            result.rejections.append(
                ExtractionRejection(
                    reason=f"no evidence in {func.name}",
                    line=func.lineno,
                )
            )
            return

    local_names = _collect_local_assignments(func)
    template_vars: dict[str, ast.TemplateStr] = _collect_template_assignments(func)

    evidence_text = (evidence.docstring or "").lower()
    evidence_hints = {
        "strings": "strings" in evidence_text and "values" not in evidence_text,
        "values": "values" in evidence_text and "strings" not in evidence_text,
    }

    for stmt in func.body:
        if isinstance(stmt, ast.Assert):
            tpl = _resolve_template_in_assert(stmt, template_vars)
            if tpl is None:
                continue  # not a t-string assertion
            attr_name = _assert_attr_name(stmt)
            if attr_name is None:
                continue

            # Evidence/assertion reconciliation.
            if evidence_hints.get("strings") and attr_name == "values":
                result.rejections.append(
                    ExtractionRejection(
                        reason=(
                            f"docstring says strings but assertion checks "
                            f"{attr_name} at line {stmt.lineno}"
                        ),
                        line=stmt.lineno,
                    )
                )
                continue
            if evidence_hints.get("values") and attr_name == "strings":
                result.rejections.append(
                    ExtractionRejection(
                        reason=(
                            f"docstring says values but assertion checks "
                            f"{attr_name} at line {stmt.lineno}"
                        ),
                        line=stmt.lineno,
                    )
                )
                continue

            literal = ast.get_source_segment(source, tpl)
            assert literal is not None
            free_names = _free_names_from_tpl(tpl, local_names)
            if free_names is None:
                result.rejections.append(
                    ExtractionRejection(
                        reason=f"shadowed binding at line {tpl.lineno}",
                        line=tpl.lineno,
                    )
                )
                continue

            result.candidates.append(
                SourceExerciseCandidate(
                    id=f"{func.name}:{tpl.lineno}",
                    origin=SourceOrigin(
                        source_id="<extracted>",
                        path="<extracted>",
                        line_start=tpl.lineno,
                        line_end=tpl.end_lineno or tpl.lineno,
                        license="<extracted>",
                    ),
                    evidence=evidence,
                    intent=TaskIntent(
                        id=f"{func.name}:{tpl.lineno}",
                        description=f"extracted from {func.name}",
                        properties=(
                            Introspect(
                                target=f".{attr_name}", index=0, field=attr_name
                            ),
                        ),
                        policy_intent=PolicyIntent(
                            requires_template=True,
                            templatelib_apis_used=frozenset({attr_name}),
                        ),
                    ),
                    check_intents=(
                        LocalCheckIntent(
                            kind="equals", target=f"template.{attr_name}[0]"
                        ),
                    ),
                )
            )


def _collect_local_assignments(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> set[str]:
    """Collect names assigned in a function body (shallow)."""
    names: set[str] = set()
    for stmt in func.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
    return names


def _has_loop_or_subtest(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check whether the function body contains a loop or subTest call."""
    for node in ast.walk(func):
        if isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
            return True
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "subTest":
                return True
    return False


def _calls_private_helper(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check whether the function calls a private assertion helper."""
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr.startswith("assert"):
                    return True
    return False


def _collect_template_assignments(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, ast.TemplateStr]:
    """Map variable names to TemplateStr nodes in the function body."""
    tpls: dict[str, ast.TemplateStr] = {}
    for stmt in func.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and isinstance(
                    stmt.value, ast.TemplateStr
                ):
                    tpls[target.id] = stmt.value
    return tpls


def _resolve_template_in_assert(
    stmt: ast.Assert,
    template_vars: dict[str, ast.TemplateStr],
) -> ast.TemplateStr | None:
    """Return the TemplateStr node that *stmt*'s left-hand side refers to."""
    if not isinstance(stmt.test, ast.Compare):
        return None
    left = stmt.test.left
    # Direct: assert t"...".attr == ...
    if isinstance(left, ast.Attribute) and isinstance(left.value, ast.TemplateStr):
        return left.value
    # Via variable: template = t"..."; assert template.attr == ...
    if isinstance(left, ast.Attribute) and isinstance(left.value, ast.Name):
        return template_vars.get(left.value.id)
    return None


def _assert_attr_name(stmt: ast.Assert) -> str | None:
    """Return the attribute name of a t-string assert (e.g. 'strings')."""
    if isinstance(stmt.test, ast.Compare) and isinstance(stmt.test.left, ast.Attribute):
        return stmt.test.left.attr
    return None


def _free_names_from_tpl(
    tpl: ast.TemplateStr, local_names: set[str]
) -> tuple[str, ...] | None:
    """Extract free names from a TemplateStr, returning None if shadowed."""
    names: tuple[str, ...] = ()
    for val in tpl.values:
        if isinstance(val, ast.Interpolation) and isinstance(val.value, ast.Name):
            name = val.value.id
            if name in local_names:
                return None
            names += (name,)
    return names


# ---------------------------------------------------------------------------
# Low-level: find all TemplateStr literals (used by Stage 1 tests)
# ---------------------------------------------------------------------------


def find_template_literals(source: str) -> list[TemplateLiteral]:
    """Find all ``ast.TemplateStr`` nodes in *source* and return their spans.

    Raises *ScopeShadowingError* when a free name in a t-string literal is
    assigned in an enclosing function scope (shadowing an outer binding).
    """
    tree = ast.parse(source)
    results: list[TemplateLiteral] = []
    _walk_and_extract(tree, source, results, local_names=set())
    return results


# ---------------------------------------------------------------------------
# Safety grammar
# ---------------------------------------------------------------------------

# Expressions that are safe inside a t-string interpolation.
_SAFE_EXPR_NODES = frozenset(
    {
        "Name",
        "Constant",
        "Tuple",
        "List",
        "Dict",
        "Set",
        "BinOp",
        "UnaryOp",
        "BoolOp",
        "Compare",
        "Attribute",
        "Subscript",
        "Slice",
        "IfExp",
        "Load",
        "Store",
        "Del",  # expression context nodes
    }
)

_UNSAFE_BUILTINS = frozenset(
    {
        "open",
        "__import__",
        "eval",
        "exec",
        "compile",
        "breakpoint",
        "input",
    }
)

_UNSAFE_ATTRS = frozenset(
    {
        "__setitem__",
        "__delitem__",
        "__setattr__",
    }
)


def _check_safety(node: ast.AST) -> None:
    """Check that an interpolation expression contains only safe constructs."""
    node_type = type(node).__name__
    if node_type not in _SAFE_EXPR_NODES:
        raise ValueError(
            f"unsafe expression type {node_type!r} "
            f"at line {getattr(node, 'lineno', '?')}"
        )
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _UNSAFE_BUILTINS:
            raise ValueError(f"unsafe call to {node.func.id!r} at line {node.lineno}")
    if isinstance(node, ast.Attribute):
        if node.attr in _UNSAFE_ATTRS:
            raise ValueError(
                f"unsafe attribute access {node.attr!r} at line {node.lineno}"
            )
    for child in ast.iter_child_nodes(node):
        _check_safety(child)


def _walk_and_extract(
    node: ast.AST,
    source: str,
    results: list[TemplateLiteral],
    *,
    local_names: set[str],
) -> None:
    """Recursive AST walker that tracks local-name shadowing."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        inner_locals = local_names | _collect_local_assignments(node)
        for child in ast.iter_child_nodes(node):
            _walk_and_extract(child, source, results, local_names=inner_locals)
        return

    if isinstance(node, ast.TemplateStr):
        literal = ast.get_source_segment(source, node)
        assert literal is not None
        for value in node.values:
            if isinstance(value, ast.Interpolation):
                _check_safety(value.value)
        names = _free_names_from_tpl(node, local_names)
        if names is None:
            raise ScopeShadowingError(
                f"free name at line {node.lineno} is shadowed by a local assignment"
            )
        results.append(
            TemplateLiteral(
                literal=literal,
                line=node.lineno,
                col=node.col_offset,
                free_names=names,
            )
        )
        return

    for child in ast.iter_child_nodes(node):
        _walk_and_extract(child, source, results, local_names=local_names)
