"""Shared test fixtures."""
from __future__ import annotations

import bcrypt
import pytest

_original_gensalt = bcrypt.gensalt


@pytest.fixture(autouse=True, scope="session")
def _fast_bcrypt():
    """Use minimum bcrypt rounds (4) during tests for speed.

    Default 12 rounds make each hash/verify ~0.2s.  With ~101 bcrypt
    operations across the test suite this adds ~21s of wall-clock time.
    4 rounds reduce each operation to <0.001s while still exercising the
    real bcrypt algorithm (hash/verify roundtrip is preserved).
    """
    original = bcrypt.gensalt
    bcrypt.gensalt = lambda rounds=4: _original_gensalt(rounds=4)
    yield
    bcrypt.gensalt = original
