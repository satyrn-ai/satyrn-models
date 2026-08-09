"""SP5 Task 1: source manifest, exact pins, and license policy.

Focused command: ``uv run python -m pytest tests/authoring/test_sources.py -q``.
These tests are hermetic: source validation runs against in-process records and
local ``tmp_path`` git fixtures. Network validation of the committed real
manifest is the default-skipped ``@pytest.mark.network`` test at the bottom.
"""

from pathlib import Path

import pytest

from satyrn_model.authoring.sources import SourceRecord, SourceValidationError


def test_rejects_mutable_ref() -> None:
    """A ``sha`` that is a branch name is not an immutable commit pin."""
    source = SourceRecord(
        id="bad-mutable",
        url="https://github.com/example/repo",
        sha="main",
        license="MIT",
        attribution="Example",
        source_class="third-party",
        extraction_mode="ast",
        expected_contribution={"literals": ">=0"},
    )
    with pytest.raises(SourceValidationError, match="immutable"):
        source.validate(policy=None)


def test_rejects_disallowed_license() -> None:
    """A license outside the allowed SPDX set in sources.toml is rejected."""
    from satyrn_model.authoring.sources import load_policy

    policy = load_policy()
    source = SourceRecord(
        id="bad-license",
        url="https://github.com/example/repo",
        sha="a" * 40,
        license="GPL-3.0-only",
        attribution="Example",
        source_class="third-party",
        extraction_mode="ast",
        expected_contribution={"literals": ">=0"},
    )
    with pytest.raises(SourceValidationError, match="GPL-3.0-only"):
        source.validate(policy=policy)


def test_records_all_source_attribution() -> None:
    """A valid [[source]] record yields a complete inventory entry."""
    from satyrn_model.authoring.sources import emit_inventory, load_sources

    sources = load_sources()
    assert sources, "committed sources.toml must contain at least one source"

    inventory = emit_inventory(sources)
    for source in sources:
        entry = inventory["sources"][source.id]
        assert entry["id"] == source.id
        assert entry["url"] == source.url
        assert entry["sha"] == source.sha
        assert entry["license"] == source.license
        assert entry["attribution"] == source.attribution
        assert entry["source_class"] == source.source_class
        assert entry["extraction_mode"] == source.extraction_mode
        assert entry["expected_contribution"] == source.expected_contribution
        assert "skeletons" in entry  # placeholder, populated in Task 3
    assert "_notice" in inventory


class TestAssertCpythonVerifier:
    """The exact CPython-tag ↔ interpreter check (closes F-STALE-CPYTHON)."""

    def test_rejects_major_minor_mismatch(self) -> None:
        """A tag whose minor version disagrees with the interpreter fails."""
        import sys

        from satyrn_model.authoring.sources import (
            CpythonVerificationError,
            assert_cpython_verifier,
        )

        # Be extra sure: we are actually running 3.14.x in this worktree.
        assert sys.version_info[:2] == (3, 14), "this test assumes CPython 3.14"

        with pytest.raises(CpythonVerificationError, match=r"v3\.13"):
            assert_cpython_verifier("v3.13.0")

    def test_rejects_patch_mismatch(self) -> None:
        """A tag whose patch disagrees with the interpreter fails."""
        import sys

        from satyrn_model.authoring.sources import (
            CpythonVerificationError,
            assert_cpython_verifier,
        )

        # Use a patch number we know is NOT the running interpreter.
        real_patch = sys.version_info.micro  # 5 on 3.14.5
        bad_tag = f"v3.14.{real_patch + 1}"
        with pytest.raises(CpythonVerificationError, match=bad_tag):
            assert_cpython_verifier(bad_tag)

    def test_accepts_exact_match(self) -> None:
        """The exact interpreter tag is accepted."""
        from satyrn_model.authoring.sources import assert_cpython_verifier

        assert_cpython_verifier("v3.14.5")  # must not raise


class TestAssertSourcePin:
    """General immutable-SHA validation via ``git rev-parse HEAD``."""

    @staticmethod
    def _make_repo(root: Path) -> None:
        import subprocess

        root.mkdir()
        subprocess.run(
            ["git", "-C", str(root), "init", "-b", "main"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "config", "user.email", "test@example.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "config", "user.name", "test"],
            check=True,
            capture_output=True,
        )
        (root / "file.txt").write_text("content", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(root), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", "init", "--no-gpg-sign"],
            check=True,
            capture_output=True,
        )

    def test_rejects_mismatched_sha(self, tmp_path: Path) -> None:

        from satyrn_model.authoring.sources import (
            SourceValidationError,
            assert_source_pin,
        )

        repo = tmp_path / "fixture"
        self._make_repo(repo)

        with pytest.raises(SourceValidationError, match="expects"):
            assert_source_pin(repo, "0" * 40)

    def test_accepts_matching_sha(self, tmp_path: Path) -> None:
        import subprocess

        from satyrn_model.authoring.sources import assert_source_pin

        repo = tmp_path / "fixture2"
        self._make_repo(repo)

        actual = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        assert_source_pin(repo, actual)  # must not raise


class TestSharedSkeletonNonRejection:
    """Structural skeletons are a selection metric, never a rejection rule."""

    def test_sources_sharing_skeleton_are_still_accepted(self) -> None:
        """Two valid sources sharing a skeleton placeholder are both accepted."""
        from satyrn_model.authoring.sources import SourcePolicy, SourceRecord

        policy = SourcePolicy(
            allowed_licenses=frozenset({"MIT"}),
        )
        source_a = SourceRecord(
            id="a",
            url="https://example.com/a",
            sha="a" * 40,
            license="MIT",
            attribution="A",
            source_class="third-party",
            extraction_mode="ast",
            expected_contribution={"literals": 1},
        )
        source_b = SourceRecord(
            id="b",
            url="https://example.com/b",
            sha="b" * 40,
            license="MIT",
            attribution="B",
            source_class="third-party",
            extraction_mode="ast",
            expected_contribution={"literals": 1},
        )
        # Neither may be rejected merely because their skeletons (when
        # populated in Task 3) happen to match.
        source_a.validate(policy=policy)
        source_b.validate(policy=policy)


def test_inventory_writes_json_file(tmp_path: Path) -> None:
    """``write_inventory`` emits ``reports/source-inventory.json``."""
    import json

    from satyrn_model.authoring.sources import (
        SourcePolicy,
        SourceRecord,
        write_inventory,
    )

    sources = [
        SourceRecord(
            id="src",
            url="https://example.com/repo",
            sha="d" * 40,
            license="MIT",
            attribution="Example",
            source_class="third-party",
            extraction_mode="ast",
            expected_contribution={"literals": 1},
            notice="NOTICE text",
        ),
    ]
    policy = SourcePolicy(allowed_licenses=frozenset({"MIT"}))
    for source in sources:
        source.validate(policy=policy)

    output_dir = tmp_path / "reports"
    written = write_inventory(sources, output_dir)

    assert written.is_file()
    data = json.loads(written.read_text(encoding="utf-8"))
    assert data["sources"]["src"]["id"] == "src"
    assert data["_notice"] == "NOTICE text"


@pytest.mark.network
class TestRealManifest:
    """Validate the committed ``sources.toml`` records.

    Skipped by default (``pytest --run-network`` to run). At minimum this
    confirms the committed manifest parses and validates; a future clone-cache
    step will additionally verify the real SHA against ``git ls-remote``.
    """

    def test_committed_sources_validate(self) -> None:
        """Every ``[[source]]`` in ``sources.toml`` passes policy validation."""
        from satyrn_model.authoring.sources import (
            load_policy,
            load_sources,
        )

        policy = load_policy()
        sources = load_sources()
        assert sources, "sources.toml must contain at least one [[source]]"

        for source in sources:
            source.validate(policy=policy)

    def test_cpython_source_sets_tag(self) -> None:
        """The CPython source record declares its verifier tag."""
        from satyrn_model.authoring.sources import load_sources

        sources = load_sources()
        cpython = [s for s in sources if s.source_class == "cpython"]
        assert cpython, "sources.toml must include a CPython [[source]]"
        for source in cpython:
            assert source.tag is not None, (
                f"cpython source {source.id!r} must carry a 'tag' field "
                f"for the assert_cpython_verifier gate"
            )

    def test_cpython_sha_matches_remote_tag(self) -> None:
        """The committed CPython SHA resolves to the declared tag on the remote."""
        import subprocess

        from satyrn_model.authoring.sources import load_sources

        sources = load_sources()
        cpython = [s for s in sources if s.source_class == "cpython"]
        assert cpython
        source = cpython[0]
        assert source.tag

        result = subprocess.run(
            ["git", "ls-remote", source.url, f"refs/tags/{source.tag}"],
            capture_output=True,
            text=True,
            check=True,
        )
        remote_sha = result.stdout.strip().split()[0]
        assert remote_sha == source.sha, (
            f"committed SHA {source.sha!r} does not match "
            f"remote tag {source.tag!r} ({remote_sha!r})"
        )
