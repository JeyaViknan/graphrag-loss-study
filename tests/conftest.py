"""Shared pytest fixtures.

The synthetic index is session-scoped and built once into a temp directory. No
test in this suite touches the real frozen index or the real corpus.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .fixtures import write_fixture_index


@pytest.fixture(scope="session")
def frozen_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A synthetic index using the graphrag 3.1.1 spelling (``relationship_ids``)."""
    return write_fixture_index(tmp_path_factory.mktemp("frozen_singular"), plural_s=False)


@pytest.fixture(scope="session")
def frozen_dir_plural_s(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A synthetic index using the legacy KB §A.3 spelling (``relationships_ids``)."""
    return write_fixture_index(tmp_path_factory.mktemp("frozen_plural"), plural_s=True)
