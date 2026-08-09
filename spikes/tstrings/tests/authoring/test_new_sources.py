"""Task 1: the five new third-party sources for regex/sql/html seeds."""

from satyrn_model.authoring.sources import load_policy, load_sources

NEW_SOURCE_IDS = {
    "regex-template-2026",
    "t-sql-2026",
    "tdom-2026",
    "storyville-2026",
    "tdom-svcs-2026",
}


def test_new_sources_are_registered_and_valid() -> None:
    """Each new source parses, validates, and is a distinct id."""
    policy = load_policy()
    sources = {s.id: s for s in load_sources()}

    missing = NEW_SOURCE_IDS - set(sources)
    assert not missing, f"sources.toml is missing: {missing}"

    for source_id in NEW_SOURCE_IDS:
        source = sources[source_id]
        source.validate(policy=policy)  # raises on bad sha/license
        assert source.source_class == "third-party"
        assert source.extraction_mode == "ast"
        assert source.license == "MIT"


def test_cpython_source_is_unaffected() -> None:
    """Adding third-party sources doesn't disturb the existing CPython one."""
    sources = {s.id: s for s in load_sources()}
    cpython = sources["cpython-v3.14.5"]
    assert cpython.source_class == "cpython"
    assert cpython.tag == "v3.14.5"
