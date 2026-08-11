"""Collect CPython documentation sections tied to a specific version's changes."""

import logging
import pickle
import re
import tempfile
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

import click
from docutils import nodes
from sphinx import addnodes
from sphinx.application import ENV_PICKLE_FILENAME, Sphinx

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DOCTREE_CACHE_DIRECTORY = Path(tempfile.gettempdir()) / "satyrn-cpython-sphinx-cache"
MAX_SECTION_LINES = 500


def parse_docs(doc_directory: Path) -> Sphinx:
    """Parse every .rst under doc_directory into a document tree.

    Returns the Sphinx app with every parsed document, keyed by name.
    """
    logger.info("Sphinx reading %s", doc_directory)
    logger.info("Sphinx cache: %s", DOCTREE_CACHE_DIRECTORY)
    with tempfile.TemporaryDirectory() as output_directory:
        app = Sphinx(
            srcdir=str(doc_directory),
            confdir=str(doc_directory),
            outdir=output_directory,
            doctreedir=str(DOCTREE_CACHE_DIRECTORY),
            buildername="dummy",
            freshenv=False,
        )
        app.builder.read()

        # Persist the environment so unchanged files are skipped on the next run.
        with open(DOCTREE_CACHE_DIRECTORY / ENV_PICKLE_FILENAME, "wb") as f:
            pickle.dump(app.env, f, pickle.HIGHEST_PROTOCOL)
    return app


def names_version(node: nodes.Node, target_version: str) -> bool:
    """Return True if node's text names target_version."""
    return re.search(rf"\b{re.escape(target_version)}\b", node.astext()) is not None


def find_version_changes(app: Sphinx, target_version: str) -> Iterator[tuple[str, nodes.Node]]:
    """Yield (document_name, node) for every version-modified node naming target_version."""
    for document_name in sorted(app.env.all_docs):
        doctree = app.env.get_doctree(document_name)
        for node in doctree.findall(addnodes.versionmodified):
            if not names_version(node, target_version):
                continue
            yield document_name, node


def belongs_to_api_entry(node: nodes.Node) -> bool:
    """Return True if node is nested inside a documented class, function or other API docs section."""
    parent = node.parent
    while parent is not None:
        # desc wraps one API entry: a class, function, method, etc.
        if isinstance(parent, addnodes.desc):
            return True
        # section is docutils node for a titled section (heading + body).
        if isinstance(parent, nodes.section):
            return False
        parent = parent.parent
    return False


def get_enclosing_section(node: nodes.Node, is_entry: bool) -> nodes.Element | None:
    """Return node's enclosing API entry or section."""
    section_type = addnodes.desc if is_entry else nodes.section
    section = node.parent
    while section is not None and not isinstance(section, section_type):
        section = section.parent
    return section


def get_shrunk_line_range(line_range: tuple[int, int], node_line: int, half_window: int = 100) -> tuple[int, int]:
    """Return a line range centered on node_line, clamped to line_range."""
    section_start, section_end = line_range
    start = max(section_start, node_line - half_window)
    end = min(section_end, node_line + half_window)
    return start, end


def first_line(node: nodes.Node) -> int | None:
    """Return node's first line, 0-indexed, or None if it has no line-numbered descendant."""
    return next(
        (n.line - 1 for n in node.findall(include_self=True) if n.line is not None),
        None,
    )


def is_synthetic_source(node: nodes.Node) -> bool:
    """Return True if node came from a synthetic source like rst_epilog, not a document file."""
    # docutils wraps synthetic sources in angle brackets, e.g. "<rst_epilog>"
    return node.source is not None and node.source.startswith("<")


def get_line_range(section: nodes.Element) -> tuple[int, int | None]:
    """Return the [start, end) line range covering section in its source file."""
    start = first_line(section)
    if isinstance(section, nodes.section):
        start -= 1  # section.line lands on the title's underline, not the title itself

    siblings = section.parent.children
    for sibling in siblings[siblings.index(section) + 1 :]:
        if is_synthetic_source(sibling):
            continue
        end = first_line(sibling)
        if end is None:
            continue  # e.g. an index node, which carries no source position
        if isinstance(sibling, nodes.section):
            end -= 1
        return start, end

    return start, None


@click.command("collect-doc-changes")
@click.argument("target_version")
@click.argument("doc_directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
def main(target_version: str, doc_directory: Path) -> None:
    """Collect docs tied to a Python version's changes.

    TARGET_VERSION is the Python version to collect changes for, e.g. "3.15".
    DOC_DIRECTORY is the path to a CPython's `cpython/Doc/` directory.
    """
    app = parse_docs(doc_directory)
    logger.info("Read %d documents", len(app.env.all_docs))

    sections_by_document = defaultdict(list)
    processed_sections = set()

    for document_name, node in find_version_changes(app, target_version):
        is_entry = belongs_to_api_entry(node)
        section = get_enclosing_section(node, is_entry)
        if section is None:
            logger.warning("No enclosing section for %s:%s", document_name, node.line)
            continue
        if section in processed_sections:
            continue
        processed_sections.add(section)

        sections_by_document[document_name].append((section, node, is_entry))

    output_directory = Path(__file__).parents[5] / "datasets" / f"python{target_version}" / "input" / "docs" / "changes"
    output_directory.mkdir(parents=True, exist_ok=True)

    for document_name, version_changes in sections_by_document.items():
        lines = Path(app.env.doc2path(document_name)).read_text().splitlines()

        texts = []
        for section, node, is_entry in version_changes:
            start, end = get_line_range(section)
            if end is None:
                end = len(lines)  # no next sibling: section runs to end of file
            if not is_entry and end - start > MAX_SECTION_LINES:
                start, end = get_shrunk_line_range((start, end), first_line(node))
            text = "\n".join(lines[start:end])
            if not text.strip():
                logger.warning("Empty section for %s:%d", document_name, node.line)
            texts.append(text)

        output_path = output_directory / f"{document_name}.rst"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n\n----\n\n".join(texts))
        logger.info("Wrote %s", output_path)

    logger.info("Wrote %d files to %s", len(sections_by_document), output_directory)


if __name__ == "__main__":
    main()
