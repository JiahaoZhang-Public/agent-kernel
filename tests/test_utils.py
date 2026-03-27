"""Tests for utility functions."""

from agent_os_kernel.utils import set_seed


def test_set_seed_is_deterministic():
    """Verify set_seed produces reproducible random output."""
    import random

    set_seed(123)
    a = random.random()
    set_seed(123)
    b = random.random()
    assert a == b
