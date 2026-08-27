"""Tests for Cycle 1.1: pinned sources and AST-only mining."""

import ast
import json
import subprocess
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from satyrn.tstrings.cli import cli
from satyrn.tstrings.mine import mine_seeds, verify_checkout
from satyrn.tstrings.types import SourceSpec, load_source_specs

SPIKE_ROOT = Path(__file__).resolve().parents[1]


def test_load_source_specs_parses_valid_entry(tmp_path: Path) -> None:
    """A well-formed sources.toml yields one SourceSpec with its fields."""
    toml = tmp_path / "sources.toml"
    toml.write_text(
        "[cpython]\n"
        'repo = "https://github.com/python/cpython"\n'
        'tag = "v3.14.5"\n'
        'commit = "5607950ef232dad16d75c0cf53101d9649d89115"\n'
        'license = "PSF-2.0"\n'
        'paths = ["Lib"]\n'
    )
    specs = load_source_specs(toml)
    assert len(specs) == 1
    spec = specs[0]
    assert spec.id == "cpython"
    assert spec.commit == "5607950ef232dad16d75c0cf53101d9649d89115"
    assert spec.paths == ["Lib"]
    assert spec.license == "PSF-2.0"


def test_source_without_commit_raises(tmp_path: Path) -> None:
    """A source entry missing its commit SHA is a hard error."""
    toml = tmp_path / "sources.toml"
    toml.write_text(
        '[cpython]\nrepo = "https://github.com/python/cpython"\ntag = "v3.14.5"\nlicense = "PSF-2.0"\npaths = ["Lib"]\n'
    )
    with pytest.raises(ValueError, match="commit"):
        load_source_specs(toml)


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


def _line_of(text: str, prefix: str) -> int:
    """Return the 1-based line of the first line starting with prefix."""
    for i, line in enumerate(text.splitlines(), start=1):
        if line.startswith(prefix):
            return i
    raise AssertionError(f"prefix {prefix!r} not found")


def test_mine_seeds_finds_expected_count_and_lines() -> None:
    """The fixture yields one seed per enclosing unit, at the unit's line."""
    spec = load_source_specs(SPIKE_ROOT / "sources.toml")[0]
    seeds = mine_seeds(FIXTURE_ROOT, spec)
    assert len(seeds) == 3
    fixture = (FIXTURE_ROOT / "Lib" / "tstrings_sample.py").read_text()
    expected = [
        _line_of(fixture, "GREETING ="),
        _line_of(fixture, "def greet"),
        _line_of(fixture, "def pair"),
    ]
    assert sorted(seed.line for seed in seeds) == sorted(expected)


def test_mine_never_execs_or_imports() -> None:
    """mine.py and types.py never call exec/eval/compile or import importlib."""
    forbidden_calls = {"exec", "eval", "compile"}
    for module_name in ("mine", "types"):
        module_path = SPIKE_ROOT / "src" / "satyrn" / "tstrings" / f"{module_name}.py"
        tree = ast.parse(module_path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls, f"{module_name}.py calls {node.func.id}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("importlib"), f"{module_name}.py imports {alias.name}"
            if isinstance(node, ast.ImportFrom):
                assert node.module is None or not node.module.startswith("importlib"), (
                    f"{module_name}.py imports {node.module}"
                )


def _git_commit_at(path: Path) -> str:
    """Create a git repo with one commit at path and return its HEAD."""
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True)
    (path / "f.txt").write_text("x")
    subprocess.run(["git", "-C", str(path), "add", "f.txt"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True)
    result = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def test_verify_checkout_accepts_matching_head(tmp_path: Path) -> None:
    """A checkout whose HEAD matches spec.commit passes."""
    head = _git_commit_at(tmp_path)
    spec = SourceSpec(id="t", repo="", tag="v3.14.5", commit=head, license="PSF-2.0", paths=["Lib"])
    verify_checkout(tmp_path, spec)  # must not raise


def test_verify_checkout_rejects_mismatch(tmp_path: Path) -> None:
    """A checkout whose HEAD differs from spec.commit is refused."""
    _git_commit_at(tmp_path)
    spec = SourceSpec(id="t", repo="", tag="v3.14.5", commit="0" * 40, license="PSF-2.0", paths=["Lib"])
    with pytest.raises(click.ClickException, match="expected"):
        verify_checkout(tmp_path, spec)


def test_verify_checkout_rejects_non_git_dir(tmp_path: Path) -> None:
    """A directory that is not a git checkout is refused."""
    spec = SourceSpec(id="t", repo="", tag="v3.14.5", commit="0" * 40, license="PSF-2.0", paths=["Lib"])
    with pytest.raises(click.ClickException, match="not a git checkout"):
        verify_checkout(tmp_path, spec)


def test_verify_checkout_rejects_dirty_tree(tmp_path: Path) -> None:
    """A checkout whose working tree diverges from HEAD is refused."""
    head = _git_commit_at(tmp_path)
    spec = SourceSpec(id="t", repo="", tag="v3.14.5", commit=head, license="PSF-2.0", paths=["Lib"])
    with (tmp_path / "f.txt").open("a") as fh:
        fh.write("dirty")
    with pytest.raises(click.ClickException, match="dirty"):
        verify_checkout(tmp_path, spec)


def _build_all_checkouts(parent: Path) -> None:
    """Create a per-source parent dir where every source yields >=1 seed."""
    specs = load_source_specs(SPIKE_ROOT / "sources.toml")
    for spec in specs:
        source_dir = parent / spec.id
        if spec.paths == ["Lib"]:
            (source_dir / "Lib").mkdir(parents=True)
            target = source_dir / "Lib" / "sample.py"
        else:
            source_dir.mkdir(parents=True)
            target = source_dir / "sample.py"
        target.write_text('x = t"hi"\n')


def test_mine_command_writes_mined_jsonl(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The mine command mines the per-source checkouts and writes one JSON Seed per line."""
    from satyrn.tstrings import mine as mine_module

    _build_all_checkouts(tmp_path)
    out_dir = tmp_path / "seeds"
    monkeypatch.setattr(mine_module, "verify_checkout", lambda source_root, spec: None)

    result = CliRunner().invoke(cli, ["mine", "-i", str(tmp_path), "-o", str(out_dir)])
    assert result.exit_code == 0, result.output
    lines = (out_dir / "mined.jsonl").read_text().splitlines()
    assert len(lines) == 7
    assert {json.loads(line)["source_id"] for line in lines} == {
        spec.id for spec in load_source_specs(SPIKE_ROOT / "sources.toml")
    }


def test_mine_command_fails_loudly_on_empty_mine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A mine that yields zero seeds exits 1 with a clear message, not silent exit 0."""
    from satyrn.tstrings import mine as mine_module

    # Build a per-source parent with an empty cpython checkout (no Lib).
    cpython = tmp_path / "cpython"
    cpython.mkdir()
    out_dir = tmp_path / "seeds"
    monkeypatch.setattr(mine_module, "verify_checkout", lambda source_root, spec: None)

    result = CliRunner().invoke(cli, ["mine", "-i", str(tmp_path), "-o", str(out_dir)])
    assert result.exit_code == 1
    assert "no seeds" in result.output


def test_load_source_specs_has_all_sources() -> None:
    """sources.toml defines cpython plus the six third-party sources."""
    specs = load_source_specs(SPIKE_ROOT / "sources.toml")
    ids = {spec.id for spec in specs}
    assert ids == {
        "cpython",
        "regex-template-2026",
        "t-sql-2026",
        "tdom-2026",
        "storyville-2026",
        "tdom-svcs-2026",
        "pep750-examples-2026",
    }
    for spec in specs:
        if spec.id != "cpython":
            assert spec.license == "MIT"
            assert spec.paths == ["."]


def test_mine_command_surfaces_missing_commit_as_click_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A malformed sources.toml surfaces as a ClickException, not a traceback."""
    from satyrn.tstrings import mine as mine_module

    bad_toml = tmp_path / "sources.toml"
    bad_toml.write_text(
        '[cpython]\nrepo = "https://github.com/python/cpython"\ntag = "v3.14.5"\nlicense = "PSF-2.0"\npaths = ["Lib"]\n'
    )
    monkeypatch.setattr(mine_module, "SOURCES_TOML", bad_toml)

    result = CliRunner().invoke(cli, ["mine", "-i", str(FIXTURE_ROOT), "-o", str(tmp_path / "seeds")])
    assert result.exit_code == 1
    assert "commit" in result.output
