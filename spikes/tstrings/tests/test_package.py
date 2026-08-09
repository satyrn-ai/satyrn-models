"""The provider package must be importable from the src layout."""

import satyrn_model


def test_package_imports_and_has_version() -> None:
    assert isinstance(satyrn_model.__version__, str)
    assert satyrn_model.__version__
