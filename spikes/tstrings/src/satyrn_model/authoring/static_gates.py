"""Static gates: import allowlist, de-libraryization checks, and intra-corpus
deduplication.  These gates run at build time before any provider call and do
not depend on the provider.

Structural fingerprints are a diversity metric only — they are never a
duplicate proof.
"""

from __future__ import annotations

import ast
import hashlib
import re

from .models import SourceExerciseCandidate

__all__ = [
    "check_imports",
    "check_third_party_names",
    "deduplicate_rows",
]

# Python 3.14 stdlib modules (subset relevant to t-string exercises).
_STDLIB_ALLOWLIST = frozenset(
    {
        "string",
        "string.templatelib",
        "re",
        "math",
        "datetime",
        "json",
        "textwrap",
        "itertools",
        "collections",
        "functools",
        "typing",
        "dataclasses",
        "enum",
        "pathlib",
        "os",
        "os.path",
        "sys",
        "io",
        "csv",
        "sqlite3",
        "hashlib",
    }
)

# Third-party API surface names that signal incomplete de-libraryization.
# These are library-specific class/package names — NOT generic domain words
# like "SQL", "HTML", "DOM", or "Logger", which appear legitimately in
# stdlib-only seeds about those domains.
_DISALLOWED_NAMES = frozenset(
    {
        "TemplateParser",  # tdom's parser class
        "TStringLogger",  # tstringlogger's logger class
        "Ludic",  # ludic package
        "tstr",  # tstr package
        "tdom",  # tdom package
        "pyhtml",  # pyhtml-enhanced package
    }
)


def check_imports(source: str) -> str | None:
    """Return an error string if *source* uses a dynamic or non-stdlib import.

    Returns ``None`` when all imports are safe.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return "syntax error"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _is_stdlib(alias.name):
                    return f"non-stdlib import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module and not _is_stdlib(node.module):
                return f"non-stdlib import: {node.module}"
        elif isinstance(node, ast.Call):
            if _is_dynamic_import_call(node):
                return "dynamic import"

    return None


def check_third_party_names(source: str) -> str | None:
    """Return an error if *source* references a disallowed third-party name.

    These are API surface names that survive after the import is stripped
    during de-libraryization.
    """
    for name in _DISALLOWED_NAMES:
        if re.search(rf"\b{re.escape(name)}\b", source):
            return f"third-party name: {name}"
    return None


def deduplicate_rows(
    rows: list[SourceExerciseCandidate],
) -> tuple[list[SourceExerciseCandidate], list[SourceExerciseCandidate]]:
    """Split *rows* into kept (first occurrence) and dropped (exact duplicates).

    Duplicate detection is by content hash of the full candidate excluding its
    ``id`` field (which differs between otherwise identical rows).
    """
    seen: set[str] = set()
    kept: list[SourceExerciseCandidate] = []
    dropped: list[SourceExerciseCandidate] = []

    for row in rows:
        h = _content_hash(row)
        if h in seen:
            dropped.append(row)
        else:
            seen.add(h)
            kept.append(row)

    return kept, dropped


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _is_stdlib(module: str) -> bool:
    """Check whether *module* is in the allowed stdlib set or a submodule."""
    for allowed in _STDLIB_ALLOWLIST:
        if module == allowed or module.startswith(allowed + "."):
            return True
    return False


def _is_dynamic_import_call(node: ast.Call) -> bool:
    """Check whether *node* is a call to __import__ or importlib.import_module."""
    if isinstance(node.func, ast.Name) and node.func.id == "__import__":
        return True
    if isinstance(node.func, ast.Attribute):
        if node.func.attr == "import_module":
            return True
    return False


def _content_hash(row: SourceExerciseCandidate) -> str:
    """Content hash excluding the row id."""
    payload = (
        f"{row.origin.source_id}\0"
        f"{row.origin.path}\0"
        f"{row.intent.description}\0"
        f"{row.intent.properties}\0"
        f"{row.check_intents}\0"
    )
    return hashlib.sha256(payload.encode()).hexdigest()
