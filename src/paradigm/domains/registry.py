"""Domain profile registry — registration, discovery, and lazy loading."""

from __future__ import annotations

import importlib
import sys

from paradigm.domains.base import DomainProfile

# ---------------------------------------------------------------------------
# Internal registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, DomainProfile] = {}


def register_domain(profile: DomainProfile) -> None:
    """Register a domain profile.

    Overwrites any existing registration with the same name (idempotent).

    Args:
        profile: Domain profile to register.
    """
    _REGISTRY[profile.name] = profile


def get_domain(name: str) -> DomainProfile:
    """Get a registered domain profile by name.

    If the domain is not yet registered, attempts to load it via
    ``load_domain(name)`` first.

    Args:
        name: Domain name (e.g. "science", "research").

    Returns:
        The registered DomainProfile.

    Raises:
        ValueError: If the domain cannot be found or loaded.
    """
    if name not in _REGISTRY:
        load_domain(name)
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys())) or "(none)"
        raise ValueError(f"Domain '{name}' not found. Available domains: {available}")
    return _REGISTRY[name]


def list_domains() -> list[str]:
    """List names of all registered domains.

    Returns:
        Sorted list of domain names.
    """
    return sorted(_REGISTRY.keys())


def load_domain(name: str) -> None:
    """Lazy-load a domain module by importing ``paradigm.domains.<name>``.

    The domain module's ``__init__.py`` is expected to call
    ``register_domain()`` during import.

    Args:
        name: Domain name to load.

    Raises:
        ValueError: If the domain module cannot be imported.
    """
    module_path = f"paradigm.domains.{name}"
    try:
        if module_path in sys.modules:
            # Module already imported — reload to re-register
            importlib.reload(sys.modules[module_path])
        else:
            importlib.import_module(module_path)
    except ImportError as e:
        raise ValueError(f"Could not load domain '{name}': no module '{module_path}' found") from e


def _clear_registry() -> None:
    """Clear all registered domains. For testing only."""
    _REGISTRY.clear()
