"""Tests that the packages' ``__version__`` matches pyproject.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path

import dspanalyze
import minidsp

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


# --- Version ---

def test_version_matches_pyproject():
    """scripts/version.sh bumps pyproject.toml and both __version__ strings together."""
    with PYPROJECT.open("rb") as f:
        version = tomllib.load(f)["project"]["version"]
    assert minidsp.__version__ == version
    assert dspanalyze.__version__ == version
