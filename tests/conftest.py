"""Shared test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def tmp_output(tmp_path):
    """Provide a temporary output directory for tests."""
    out = tmp_path / "output"
    out.mkdir()
    return out
