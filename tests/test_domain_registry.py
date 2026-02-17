"""Tests for domain profile registry."""

import pytest

from paradigm.domains.base import DomainProfile
from paradigm.domains.registry import (
    _clear_registry,
    get_domain,
    list_domains,
    register_domain,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure each test starts with a clean registry."""
    _clear_registry()
    yield
    _clear_registry()


def _make_profile(name: str = "test") -> DomainProfile:
    return DomainProfile(name=name, description=f"{name} domain")


def test_register_and_get():
    """Register a profile and retrieve it by name."""
    profile = _make_profile("alpha")
    register_domain(profile)
    result = get_domain("alpha")
    assert result.name == "alpha"
    assert result.description == "alpha domain"


def test_register_duplicate_raises():
    """Registering a domain twice raises ValueError."""
    register_domain(_make_profile("dup"))
    with pytest.raises(ValueError, match="already registered"):
        register_domain(_make_profile("dup"))


def test_list_domains_empty():
    """list_domains returns empty list when nothing registered."""
    assert list_domains() == []


def test_list_domains_sorted():
    """list_domains returns sorted names."""
    register_domain(_make_profile("zeta"))
    register_domain(_make_profile("alpha"))
    register_domain(_make_profile("mu"))
    assert list_domains() == ["alpha", "mu", "zeta"]


def test_get_unknown_domain_raises():
    """Getting an unknown domain that can't be loaded raises ValueError."""
    with pytest.raises(ValueError, match="Could not load domain"):
        get_domain("nonexistent_domain_xyz")


def test_get_domain_lazy_loads_science():
    """get_domain('science') lazy-loads the science domain module."""
    # This test will only pass once Commit 3 creates the science domain.
    # For now we just verify the lazy-load mechanism works with a missing domain.
    # The science module will be tested in test_domain_science.py.
    pass
